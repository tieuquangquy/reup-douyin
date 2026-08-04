from __future__ import annotations

from datetime import datetime
import json
from typing import Protocol
from urllib import parse, request
from urllib.error import HTTPError, URLError
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.settings import Settings, get_settings
from src.enums import PlatformAccountStatus, PublishTargetPlatform
from src.models.publish import PlatformAccount, PlatformPublication
from src.publish.services.platform_account_service import PlatformAccountService


FACEBOOK_REEL_FIELDS = "id,description,created_time,permalink_url,thumbnails"


class FacebookReelCatalogError(ValueError):
    def __init__(self, code: str, message: str, *, http_status: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class FacebookReelCatalogTransport(Protocol):
    def fetch_reels(
        self,
        *,
        page_id: str,
        access_token: str,
        graph_api_version: str,
        limit: int,
        after: str | None,
    ) -> dict: ...


class GraphFacebookReelCatalogTransport:
    """Read-only bounded Page Reel discovery boundary."""

    graph_base_url = "https://graph.facebook.com"

    def __init__(self, *, timeout_seconds: float = 20.0):
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    def fetch_reels(
        self,
        *,
        page_id: str,
        access_token: str,
        graph_api_version: str,
        limit: int,
        after: str | None,
    ) -> dict:
        query: dict[str, str] = {
            "fields": FACEBOOK_REEL_FIELDS,
            "limit": str(max(1, min(50, limit))),
        }
        if after:
            query["after"] = after
        url = (
            f"{self.graph_base_url}/{graph_api_version}/{page_id}/video_reels?"
            + parse.urlencode(query)
        )
        req = request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": "reup-douyin/facebook-reel-catalog-v1",
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error = _decode_graph_error(exc)
            code = int(error.get("code") or 0)
            if code in {10, 190, 200}:
                raise FacebookReelCatalogError(
                    "facebook_reel_catalog_permission_denied",
                    "Meta rejected the Page token or Reel read permission; reconnect the Page",
                    http_status=403,
                ) from exc
            if code in {4, 17, 32, 613}:
                raise FacebookReelCatalogError(
                    "facebook_reel_catalog_rate_limited",
                    "Meta rate-limited Reel discovery; wait before refreshing again",
                    http_status=429,
                ) from exc
            raise FacebookReelCatalogError(
                "facebook_reel_catalog_rejected",
                "Meta rejected the Reel discovery request",
                http_status=502,
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise FacebookReelCatalogError(
                "facebook_reel_catalog_unreachable",
                "Meta Reel discovery could not be reached",
                http_status=502,
            ) from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise FacebookReelCatalogError(
                "facebook_reel_catalog_invalid_response",
                "Meta returned an invalid Reel discovery response",
                http_status=502,
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise FacebookReelCatalogError(
                "facebook_reel_catalog_invalid_response",
                "Meta Reel discovery response is missing data[]",
                http_status=502,
            )
        return payload


class FacebookReelCatalogService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        transport: FacebookReelCatalogTransport | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.transport = transport or GraphFacebookReelCatalogTransport(
            timeout_seconds=self.settings.facebook_oauth_request_timeout_seconds
        )

    def discover(
        self,
        account_id: UUID,
        *,
        workspace_id: UUID,
        limit: int = 25,
        after: str | None = None,
    ) -> dict:
        account = self.db.get(PlatformAccount, account_id)
        if account is None or account.workspace_id != workspace_id:
            raise FacebookReelCatalogError(
                "facebook_page_not_found",
                "Facebook Page account was not found",
                http_status=404,
            )
        if account.platform != PublishTargetPlatform.FACEBOOK_REELS:
            raise FacebookReelCatalogError(
                "facebook_page_platform_invalid",
                "Reel discovery requires a Facebook Reels account",
            )
        if account.status in {PlatformAccountStatus.INVALID, PlatformAccountStatus.ARCHIVED}:
            raise FacebookReelCatalogError(
                "facebook_page_unavailable",
                "Facebook Page account is unavailable",
            )
        token = PlatformAccountService(
            self.db,
            settings=self.settings,
        ).resolve_access_token(account)
        if not token:
            raise FacebookReelCatalogError(
                "facebook_page_credential_unavailable",
                "Facebook Page credential could not be resolved; reconnect the Page",
                http_status=503,
            )
        metadata = account.metadata_json or {}
        version = str(metadata.get("graph_api_version") or self.settings.facebook_graph_api_version)
        payload = self.transport.fetch_reels(
            page_id=account.external_account_id,
            access_token=token,
            graph_api_version=version,
            limit=limit,
            after=after,
        )
        raw_rows = payload.get("data") or []
        normalized: list[dict] = []
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            reel_id = str(raw.get("id") or "").strip()
            if not reel_id:
                continue
            normalized.append(
                {
                    "reel_id": reel_id,
                    "description": str(raw.get("description") or "").strip() or None,
                    "created_time": _parse_datetime(raw.get("created_time")),
                    "permalink_url": _normalize_facebook_permalink(raw.get("permalink_url")),
                    "thumbnail_url": _thumbnail_url(raw.get("thumbnails")),
                }
            )
        reel_ids = [item["reel_id"] for item in normalized]
        existing = {}
        if reel_ids:
            publications = self.db.scalars(
                select(PlatformPublication).where(
                    PlatformPublication.workspace_id == workspace_id,
                    PlatformPublication.platform_account_id == account.id,
                    PlatformPublication.external_reel_id.in_(reel_ids),
                )
            )
            existing = {item.external_reel_id: item.id for item in publications}
        for item in normalized:
            publication_id = existing.get(item["reel_id"])
            item["already_imported"] = publication_id is not None
            item["platform_publication_id"] = publication_id
        cursors = (payload.get("paging") or {}).get("cursors") or {}
        next_cursor = str(cursors.get("after") or "").strip() or None
        if not (payload.get("paging") or {}).get("next"):
            next_cursor = None
        return {
            "platform_account_id": account.id,
            "items": normalized,
            "next_cursor": next_cursor,
            "network_used": True,
        }


def _decode_graph_error(exc: HTTPError) -> dict:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    error = payload.get("error") if isinstance(payload, dict) else None
    return error if isinstance(error, dict) else {}


def _thumbnail_url(raw: object) -> str | None:
    rows = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return None
    for row in rows:
        uri = str(row.get("uri") or "").strip() if isinstance(row, dict) else ""
        if uri:
            return uri
    return None


def _normalize_facebook_permalink(raw: object) -> str | None:
    """Return an absolute Facebook URL even when Graph sends a relative path."""

    value = str(raw or "").strip()
    if not value:
        return None
    if value.startswith("/") and not value.startswith("//"):
        return f"https://www.facebook.com{value}"
    return value


def _parse_datetime(raw: object) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
