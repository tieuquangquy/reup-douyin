from __future__ import annotations

import json
from ipaddress import ip_address
from pathlib import Path
import re
from urllib import parse, request
from urllib.error import HTTPError, URLError

from src.enums import ExternalPublicationStatus, PublishAttemptStatus, PublishTargetPlatform
from src.publish.connectors.base import PublishConnector, PublishConnectorError
from src.publish.types import PlatformAccountConfig, PublishRequest, PublishResult, PublishStatusSyncResult


class FacebookReelsConnector(PublishConnector):
    graph_base_url = "https://graph.facebook.com"
    request_timeout_seconds = 120

    def validate_account(self, account: PlatformAccountConfig) -> list[str]:
        errors: list[str] = []
        if account.platform != PublishTargetPlatform.FACEBOOK_REELS:
            errors.append("Platform account must target FACEBOOK_REELS")
        if not account.page_id:
            errors.append("Facebook Page id is required")
        if not account.access_token:
            errors.append("Facebook Page access token is required")
        if not account.graph_api_version.startswith("v"):
            errors.append("Meta Graph API version should look like v20.0")
        return errors

    def publish(self, request_payload: PublishRequest) -> PublishResult:
        account = request_payload.account
        media = request_payload.media
        errors = self.validate_account(account)
        if errors:
            raise PublishConnectorError("invalid_platform_account", "; ".join(errors))
        self._validate_media(media.video_path)

        create_response = self._create_reel(account)
        video_id = str(create_response.get("video_id") or "")
        upload_url = str(create_response.get("upload_url") or "")
        if not video_id or not upload_url:
            raise PublishConnectorError("publish_failed", "Facebook did not return video_id/upload_url", _safe_summary(create_response))

        try:
            upload_response = self._upload_local_reel(account, upload_url, media.video_path)
        except PublishConnectorError as exc:
            exc.response_summary = {**exc.response_summary, "video_id": video_id}
            raise
        if not upload_response.get("success"):
            raise PublishConnectorError("upload_failed", "Facebook local upload did not return success", {**_safe_summary(upload_response), "video_id": video_id})

        try:
            finish_response = self._finish_publish(account, video_id, media.title, media.description)
        except PublishConnectorError as exc:
            exc.response_summary = {**exc.response_summary, "video_id": video_id}
            raise
        if not finish_response.get("success"):
            raise PublishConnectorError("publish_failed", "Facebook publish finish did not return success", {**_safe_summary(finish_response), "video_id": video_id})

        permalink = self._extract_permalink(finish_response)

        return PublishResult(
            status=PublishAttemptStatus.SUCCEEDED,
            external_publish_id=video_id,
            external_media_id=video_id,
            external_reel_id=video_id,
            external_permalink=permalink,
            external_status=ExternalPublicationStatus.PUBLISHED,
            response_summary={
                "create": _safe_summary(create_response),
                "upload": _safe_summary(upload_response),
                "finish": _safe_summary(finish_response),
            },
            warnings=[] if permalink else ["facebook_permalink_missing"],
        )

    def refresh_status(
        self,
        *,
        account: PlatformAccountConfig,
        external_publish_id: str | None,
        external_media_id: str | None = None,
        external_reel_id: str | None = None,
    ) -> PublishStatusSyncResult:
        reference_id = external_publish_id or external_reel_id or external_media_id
        if not reference_id:
            raise PublishConnectorError("missing_external_reference", "Cannot refresh Facebook publish status without an external reference")

        url = self._graph_url(account, f"/{reference_id}")
        payload = self._get_json(
            url,
            {
                "fields": "status,permalink_url,id,post_id,published,created_time",
            },
            "platform_status_query_failed",
            token=account.access_token,
        )

        external_status = self._normalize_external_status(payload)
        return PublishStatusSyncResult(
            external_status=external_status,
            external_publish_id=str(payload.get("id") or reference_id),
            external_media_id=str(payload.get("post_id") or external_media_id or "") or None,
            external_reel_id=str(payload.get("id") or external_reel_id or reference_id),
            external_permalink=self._extract_permalink(payload),
            published_at=str(payload.get("created_time") or "") or None,
            response_summary=_safe_summary(payload),
            warnings=[] if external_status != ExternalPublicationStatus.UNKNOWN else ["ambiguous_platform_response"],
            reconciliation_note=self._build_reconciliation_note(external_status),
        )

    def post_affiliate_comment(
        self,
        *,
        account: PlatformAccountConfig,
        external_reel_id: str,
        message: str,
        attachment_image_url: str | None = None,
    ) -> dict:
        """Create one operator-approved comment on an existing Facebook Reel."""

        errors = self.validate_account(account)
        if errors:
            raise PublishConnectorError("invalid_platform_account", "; ".join(errors))
        reel_id = str(external_reel_id or "").strip()
        comment = str(message or "").strip()
        if not reel_id:
            raise PublishConnectorError("missing_external_reference", "Facebook Reel id is required for a comment")
        if not comment:
            raise PublishConnectorError("invalid_comment_message", "Affiliate comment message cannot be empty")
        image_url = str(attachment_image_url or "").strip()
        if image_url and not _is_public_https_url(image_url):
            raise PublishConnectorError(
                "invalid_comment_attachment",
                "Facebook comment images must use a public HTTPS URL",
            )
        payload = {"message": comment}
        if image_url:
            payload["attachment_url"] = image_url
        response = self._post_form(
            self._graph_url(account, f"/{reel_id}/comments"),
            payload,
            token=account.access_token,
        )
        comment_id = str(response.get("id") or response.get("comment_id") or "").strip()
        if not comment_id:
            raise PublishConnectorError(
                "comment_post_failed",
                "Facebook did not return an external comment id",
                _safe_summary(response),
            )
        return {
            "external_comment_id": comment_id,
            "external_comment_permalink": self._extract_permalink(response),
            "response_summary": _safe_summary(response),
        }

    def verify_affiliate_comment(
        self,
        *,
        account: PlatformAccountConfig,
        external_comment_id: str,
    ) -> dict:
        """Read one known comment without creating, editing, or reposting anything."""

        errors = self.validate_account(account)
        if errors:
            raise PublishConnectorError("invalid_platform_account", "; ".join(errors))
        comment_id = str(external_comment_id or "").strip()
        if not comment_id:
            raise PublishConnectorError("missing_external_reference", "Facebook comment id is required")
        try:
            payload = self._get_json(
                self._graph_url(account, f"/{comment_id}"),
                {
                    "fields": "id,message,created_time,from,attachment,permalink_url,is_hidden",
                },
                "comment_verification_failed",
                token=account.access_token,
            )
        except PublishConnectorError as exc:
            graph_error = exc.response_summary.get("error") if isinstance(exc.response_summary, dict) else None
            graph_code = graph_error.get("code") if isinstance(graph_error, dict) else None
            if "HTTP 404" in str(exc) or graph_code in {100}:
                return {"status": "NOT_FOUND", "response_summary": exc.response_summary}
            if exc.code in {
                "facebook_token_invalid",
                "facebook_auth_or_permission_denied",
                "facebook_platform_restriction",
            }:
                return {"status": "PERMISSION_BLOCKED", "error_code": exc.code, "response_summary": exc.response_summary}
            raise

        if not payload.get("id"):
            return {"status": "NOT_FOUND", "response_summary": _safe_summary(payload)}
        attachment = payload.get("attachment")
        return {
            "status": "HIDDEN" if payload.get("is_hidden") is True else "VERIFIED",
            "message": str(payload.get("message") or ""),
            "has_attachment": isinstance(attachment, dict) and bool(attachment),
            "is_hidden": payload.get("is_hidden") is True,
            "permalink": self._extract_permalink(payload),
            "response_summary": {
                "id": str(payload.get("id")),
                "created_time": payload.get("created_time"),
                "is_hidden": payload.get("is_hidden"),
                "has_attachment": isinstance(attachment, dict) and bool(attachment),
            },
        }

    def _create_reel(self, account: PlatformAccountConfig) -> dict:
        url = self._graph_url(account, f"/{account.page_id}/video_reels")
        return self._post_form(
            url,
            {"upload_phase": "start"},
            token=account.access_token,
        )

    def _upload_local_reel(self, account: PlatformAccountConfig, upload_url: str, video_path: Path) -> dict:
        data = video_path.read_bytes()
        req = request.Request(
            upload_url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"OAuth {account.access_token}",
                "offset": "0",
                "file_size": str(len(data)),
                "Content-Type": "application/octet-stream",
                "User-Agent": "reup-douyin/phase1",
            },
        )
        return self._send_json(req, "upload_failed")

    def _finish_publish(self, account: PlatformAccountConfig, video_id: str, title: str, description: str) -> dict:
        url = self._graph_url(account, f"/{account.page_id}/video_reels")
        return self._post_form(
            url,
            {
                "video_id": video_id,
                "upload_phase": "finish",
                "video_state": "PUBLISHED",
                "description": description,
                "title": title,
            },
            token=account.access_token,
        )

    def _post_form(self, url: str, payload: dict[str, str], *, token: str) -> dict:
        body = parse.urlencode(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "reup-douyin/phase1",
            },
        )
        return self._send_json(req, "publish_failed")

    def _get_json(
        self,
        url: str,
        query: dict[str, str],
        error_code: str,
        *,
        token: str,
    ) -> dict:
        req = request.Request(
            f"{url}?{parse.urlencode(query)}",
            method="GET",
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "reup-douyin/phase1",
            },
        )
        return self._send_json(req, error_code)

    def _graph_url(self, account: PlatformAccountConfig, path: str) -> str:
        return f"{self.graph_base_url}/{account.graph_api_version}{path}"

    def _send_json(self, req: request.Request, error_code: str) -> dict:
        try:
            with request.urlopen(req, timeout=self.request_timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            parsed = _parse_json(payload)
            code = _classify_graph_error(exc.code, parsed, fallback=error_code)
            raise PublishConnectorError(code, f"Facebook API HTTP {exc.code}", parsed) from exc
        except URLError as exc:
            raise PublishConnectorError("network_request_failed", f"Facebook API request failed: {exc.reason}") from exc
        try:
            return json.loads(payload) if payload else {}
        except json.JSONDecodeError as exc:
            raise PublishConnectorError(error_code, "Facebook API returned non-JSON response", {"body": payload[:500]}) from exc

    def _extract_permalink(self, payload: dict) -> str | None:
        value = payload.get("permalink_url") or payload.get("permalink")
        return str(value) if value else None

    def _normalize_external_status(self, payload: dict) -> ExternalPublicationStatus:
        status_value = str(payload.get("status") or "").upper()
        if payload.get("error"):
            return ExternalPublicationStatus.FAILED
        if payload.get("published") is True:
            return ExternalPublicationStatus.PUBLISHED
        if status_value in {"READY", "PUBLISHED", "LIVE"}:
            return ExternalPublicationStatus.PUBLISHED
        if status_value in {"IN_PROGRESS", "PROCESSING", "SCHEDULED"}:
            return ExternalPublicationStatus.PROCESSING
        if status_value in {"ERROR", "FAILED"}:
            return ExternalPublicationStatus.FAILED
        if status_value in {"DELETED", "REMOVED"}:
            return ExternalPublicationStatus.REMOVED
        if payload.get("id") and not payload.get("published"):
            return ExternalPublicationStatus.PARTIALLY_CONFIRMED
        return ExternalPublicationStatus.UNKNOWN

    def _build_reconciliation_note(self, external_status: ExternalPublicationStatus) -> str:
        if external_status == ExternalPublicationStatus.PUBLISHED:
            return "Platform confirms the reel is published."
        if external_status == ExternalPublicationStatus.PROCESSING:
            return "Platform still reports the reel as processing."
        if external_status == ExternalPublicationStatus.FAILED:
            return "Platform reports the publish failed."
        if external_status == ExternalPublicationStatus.PARTIALLY_CONFIRMED:
            return "Platform returned a reference but not a fully published state."
        return "Platform response remains ambiguous."

    def _validate_media(self, video_path: Path) -> None:
        if not video_path.exists():
            raise PublishConnectorError("missing_render_output", f"Final render file not found: {video_path}")
        if video_path.stat().st_size <= 0:
            raise PublishConnectorError("invalid_publish_draft", "Final render file is empty")


def _is_public_https_url(value: str) -> bool:
    parsed = parse.urlparse(value)
    hostname = str(parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not hostname:
        return False
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        return False
    try:
        address = ip_address(hostname)
    except ValueError:
        address = None
    return address is None or address.is_global


def _parse_json(payload: str) -> dict:
    try:
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            return {"response_type": type(decoded).__name__}
        return _safe_summary(decoded)
    except json.JSONDecodeError:
        return {"body": payload[:500]}


def _safe_summary(payload: dict) -> dict:
    secret_keys = {
        "access_token",
        "appsecret_proof",
        "client_secret",
        "fb_exchange_token",
        "token",
        "upload_url",
    }

    def scrub(value: object, *, key: str | None = None) -> object:
        if key and key.lower() in secret_keys:
            return "***redacted***"
        if isinstance(value, dict):
            return {str(item_key): scrub(item_value, key=str(item_key)) for item_key, item_value in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, str):
            return re.sub(
                r"(?i)(access_token|client_secret|appsecret_proof)=([^&\s]+)",
                r"\1=***redacted***",
                value,
            )
        return value

    return scrub(payload)  # type: ignore[return-value]


def _classify_graph_error(http_status: int, payload: dict, *, fallback: str) -> str:
    if http_status == 409:
        return "duplicate_publish_request"
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    try:
        graph_code = int(error.get("code"))
    except (TypeError, ValueError):
        graph_code = None
    if http_status == 429 or graph_code in {4, 17, 32, 613}:
        return "facebook_rate_limited"
    if http_status == 401:
        return "facebook_token_invalid"
    if http_status == 403:
        return "facebook_auth_or_permission_denied"
    if graph_code == 190:
        return "facebook_token_invalid"
    if graph_code in {10, 200}:
        return "facebook_auth_or_permission_denied"
    if graph_code == 368:
        return "facebook_platform_restriction"
    return fallback
