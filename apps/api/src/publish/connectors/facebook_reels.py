from __future__ import annotations

import json
from pathlib import Path
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
                "access_token": account.access_token,
                "fields": "status,permalink_url,id,post_id,published,created_time",
            },
            "platform_status_query_failed",
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

    def _create_reel(self, account: PlatformAccountConfig) -> dict:
        url = self._graph_url(account, f"/{account.page_id}/video_reels")
        return self._post_form(url, {"upload_phase": "start", "access_token": account.access_token})

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
                "access_token": account.access_token,
                "video_id": video_id,
                "upload_phase": "finish",
                "video_state": "PUBLISHED",
                "description": description,
                "title": title,
            },
        )

    def _post_form(self, url: str, payload: dict[str, str]) -> dict:
        body = parse.urlencode(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "reup-douyin/phase1",
            },
        )
        return self._send_json(req, "publish_failed")

    def _get_json(self, url: str, query: dict[str, str], error_code: str) -> dict:
        req = request.Request(
            f"{url}?{parse.urlencode(query)}",
            method="GET",
            headers={"User-Agent": "reup-douyin/phase1"},
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
            code = "duplicate_publish_request" if exc.code == 409 else error_code
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


def _parse_json(payload: str) -> dict:
    try:
        return _safe_summary(json.loads(payload))
    except json.JSONDecodeError:
        return {"body": payload[:500]}


def _safe_summary(payload: dict) -> dict:
    redacted = dict(payload)
    for key in ["access_token", "token"]:
        if key in redacted:
            redacted[key] = "***redacted***"
    return redacted
