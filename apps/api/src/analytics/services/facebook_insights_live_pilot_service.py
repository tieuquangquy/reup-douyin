from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.orm import Session

from src.enums import ExternalPublicationStatus, PlatformAccountStatus, PublishTargetPlatform
from src.models.publish import PlatformAccount, PlatformPublication
from src.publish.services.platform_account_service import PlatformAccountService
from src.schemas.analytics import (
    FacebookInsightsLivePilotCheck,
    FacebookInsightsLivePilotPreflightRequest,
    FacebookInsightsLivePilotPreflightResponse,
)


REQUIRED_FACEBOOK_INSIGHTS_SCOPES = frozenset(
    {"read_insights", "pages_read_engagement"}
)
VERIFICATION_MAX_AGE = timedelta(days=30)
_GRAPH_VERSION_PATTERN = re.compile(r"^v\d+\.\d+$")


class FacebookInsightsLivePilotError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class FacebookInsightsLivePilotService:
    """Read-only gate for the first real Facebook insights call.

    The service deliberately does not resolve credentials or perform network I/O. Token
    resolution remains inside the durable collector job after every identity and scope
    attestation below has passed.
    """

    def __init__(self, db: Session):
        self.db = db

    def preflight(
        self,
        platform_publication_id: UUID,
        request: FacebookInsightsLivePilotPreflightRequest,
    ) -> FacebookInsightsLivePilotPreflightResponse:
        publication = self.db.get(PlatformPublication, platform_publication_id)
        if publication is None:
            raise FacebookInsightsLivePilotError(
                "publication_not_found", "Platform publication not found"
            )
        account = self.db.get(PlatformAccount, publication.platform_account_id)
        if account is None:
            raise FacebookInsightsLivePilotError(
                "metrics_account_not_found", "Platform account not found"
            )

        checks: list[FacebookInsightsLivePilotCheck] = []

        def check(code: str, passed: bool, message: str) -> None:
            checks.append(
                FacebookInsightsLivePilotCheck(
                    code=code,
                    passed=bool(passed),
                    blocking=not bool(passed),
                    message=message,
                )
            )

        account_metadata = account.metadata_json or {}
        publication_metadata = publication.metadata_json or {}
        now = datetime.now(UTC)

        check(
            "operator_confirmation",
            request.operator_confirmation == "FACEBOOK_INSIGHTS_LIVE_PILOT_APPROVED",
            "Exact one-time live-pilot confirmation is present",
        )
        check(
            "publication_platform",
            publication.platform == PublishTargetPlatform.FACEBOOK_REELS,
            "Publication platform is FACEBOOK_REELS",
        )
        check(
            "publication_published",
            publication.status == ExternalPublicationStatus.PUBLISHED,
            "Publication is confirmed PUBLISHED",
        )
        check(
            "exact_account_id",
            publication.platform_account_id == request.expected_platform_account_id,
            "Expected platform account matches the publication authority",
        )
        check(
            "account_platform",
            account.platform == PublishTargetPlatform.FACEBOOK_REELS,
            "Account platform is FACEBOOK_REELS",
        )
        check(
            "account_active",
            account.status == PlatformAccountStatus.ACTIVE and not account.is_on_hold,
            "Account is ACTIVE and not on hold",
        )
        check(
            "account_not_in_cooldown",
            account.cooldown_until is None or account.cooldown_until <= now,
            "Account has no active global cooldown",
        )
        check(
            "exact_external_account_id",
            account.external_account_id == request.expected_external_account_id,
            "Expected Facebook Page/account id matches persisted authority",
        )
        check(
            "production_account_identity",
            not _looks_placeholder(account.external_account_id),
            "Facebook Page/account id is not a demo or local placeholder",
        )
        check(
            "token_reference",
            PlatformAccountService.is_safe_token_reference(str(account.token_reference or "")),
            "A safe environment or encrypted OAuth credential reference is configured",
        )
        check(
            "page_token_type",
            account_metadata.get("facebook_insights_token_type") == "PAGE_ACCESS_TOKEN",
            "Token type is attested as PAGE_ACCESS_TOKEN",
        )
        check(
            "insights_capability",
            account_metadata.get("metrics_insights_enabled") is True,
            "Facebook insights capability is explicitly enabled on this account",
        )
        check(
            "verified_account_binding",
            account_metadata.get("facebook_insights_verified_external_account_id")
            == account.external_account_id,
            "Insights verification is bound to the same external Page/account id",
        )

        verified_scopes = {
            str(value).strip()
            for value in (account_metadata.get("facebook_verified_insights_scopes") or [])
            if str(value).strip()
        }
        required_scopes = set(request.required_scopes) | set(REQUIRED_FACEBOOK_INSIGHTS_SCOPES)
        check(
            "verified_scopes",
            required_scopes.issubset(verified_scopes),
            "Verified scopes include read_insights, pages_read_engagement and every requested scope",
        )
        account_verified_at = _parse_aware_datetime(
            account_metadata.get("facebook_insights_scopes_verified_at")
        )
        check(
            "scope_verification_fresh",
            account_verified_at is not None
            and now - VERIFICATION_MAX_AGE <= account_verified_at <= now + timedelta(minutes=5),
            "Scope verification is timezone-aware and no older than 30 days",
        )

        graph_api_version = str(account_metadata.get("graph_api_version") or "v20.0")
        check(
            "graph_api_version",
            bool(_GRAPH_VERSION_PATTERN.fullmatch(graph_api_version)),
            "Graph API version uses the v<major>.<minor> format",
        )

        media_source, media_id = _resolve_publication_media_reference(publication, account_metadata)
        check(
            "exact_media_reference",
            bool(media_id) and media_id == request.expected_media_id,
            "Expected media id matches the configured publication reference",
        )
        check(
            "production_media_identity",
            bool(media_id) and not _looks_placeholder(media_id),
            "Facebook media id is not a demo or local placeholder",
        )
        check(
            "verified_media_binding",
            publication_metadata.get("facebook_insights_verified_media_id") == media_id,
            "Media verification is bound to the same Facebook object id",
        )
        media_verified_at = _parse_aware_datetime(
            publication_metadata.get("facebook_insights_object_verified_at")
        )
        check(
            "media_verification_fresh",
            media_verified_at is not None
            and now - VERIFICATION_MAX_AGE <= media_verified_at <= now + timedelta(minutes=5),
            "Media-object verification is timezone-aware and no older than 30 days",
        )
        check(
            "facebook_permalink",
            _is_facebook_permalink(publication.external_permalink),
            "Publication permalink belongs to facebook.com or fb.watch",
        )
        check(
            "publication_identity_not_placeholder",
            not _looks_placeholder(publication.external_publish_id),
            "External publication id is not a demo or local placeholder",
        )
        blockers = [item.code for item in checks if item.blocking]
        return FacebookInsightsLivePilotPreflightResponse(
            ready_for_live_job=not blockers,
            network_used=False,
            platform_publication_id=publication.id,
            platform_account_id=account.id,
            media_reference_source=media_source,
            graph_api_version=graph_api_version,
            token_resolution_deferred_to_worker=True,
            checks=checks,
            blocker_codes=blockers,
        )


def _resolve_publication_media_reference(
    publication: PlatformPublication,
    account_metadata: dict,
) -> tuple[str, str | None]:
    source = account_metadata.get("facebook_insights_object_id_source")
    by_source = {
        "external_publish_id": publication.external_publish_id,
        "external_media_id": publication.external_media_id,
        "external_reel_id": publication.external_reel_id,
    }
    if source in by_source:
        return str(source), by_source[str(source)]
    if source is not None:
        return "invalid_configuration", None
    for name in ("external_media_id", "external_reel_id", "external_publish_id"):
        if by_source[name]:
            return name, by_source[name]
    return "missing", None


def _parse_aware_datetime(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(UTC)


def _looks_placeholder(raw: object) -> bool:
    value = str(raw or "").strip().lower()
    if not value:
        return True
    markers = ("local", "demo", "fixture", "example", "invalid", "mock", "test")
    return any(marker in value for marker in markers)


def _is_facebook_permalink(raw: object) -> bool:
    try:
        host = (urlparse(str(raw or "")).hostname or "").lower()
    except ValueError:
        return False
    return host == "fb.watch" or host == "facebook.com" or host.endswith(".facebook.com")
