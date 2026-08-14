from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from src.core.settings import get_settings
from src.downloaders.errors import DownloadErrorCode, DownloadFailureReason


class DownloadFailureClass(StrEnum):
    TRANSIENT = "transient"
    AUTH = "auth"
    TERMINAL = "terminal"


_AUTH_MARKERS = (
    "refresh download session",
    "login required",
    "login_required",
    "not authenticated",
    "authenticated cookies missing",
    "no usable douyin download cookies",
    "cookie store",
    "cookies missing",
    "session expired",
    "playwright auto-open is disabled",
)

_TERMINAL_MARKERS = (
    "has been deleted",
    "aweme not found",
    "video not found",
    "no download url",
    "missing aweme",
    "asset content is empty",
    "ffprobe is unavailable",
    "cannot be validated",
    "media_probe_unavailable",
    "no usable video stream",
    "non-video content type",
    "playlist requires",
    "manifest requires",
    "hls/dash manifest",
    "exceeds configured limit",
    "unsupported media",
    "photo/slideshow",
    "selected douyin account is missing",
    "invalid douyin account binding",
    "http 404",
    "http 410",
)

_TRANSIENT_MARKERS = (
    "targetclosed",
    "browser_context_lost",
    "timeout",
    "timed out",
    "http 403",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "temporarily",
    "connection reset",
    "network",
    "orphan",
    "profile_locked",
)


def classify_download_failure(
    error_code: str | None,
    error_message: str | None,
    *,
    reason: str | None = None,
) -> DownloadFailureClass:
    code = str(error_code or "").strip().lower()
    message = str(error_message or "").strip().lower()
    structured_reason = str(reason or "").strip().lower()

    if structured_reason == DownloadFailureReason.AUTH_EXPIRED.value:
        return DownloadFailureClass.AUTH
    if structured_reason in {
        DownloadFailureReason.NO_CLEAN_STREAM.value,
        DownloadFailureReason.UNSUPPORTED_POST_TYPE.value,
        DownloadFailureReason.MEDIA_CORRUPT.value,
    }:
        return DownloadFailureClass.TERMINAL
    if structured_reason in {
        DownloadFailureReason.SIGNED_URL_EXPIRED.value,
        DownloadFailureReason.EXTRACTOR_DRIFT.value,
        DownloadFailureReason.NETWORK_TRANSIENT.value,
        DownloadFailureReason.CHALLENGE_BLOCKED.value,
    }:
        return DownloadFailureClass.TRANSIENT

    if code in {
        DownloadErrorCode.MISSING_SOURCE_URL,
        DownloadErrorCode.INVALID_SOURCE_VIDEO,
        DownloadErrorCode.STORAGE_RESOLUTION_FAILED,
        DownloadErrorCode.WRITE_FAILED,
        DownloadErrorCode.MANIFEST_UPDATE_FAILED,
    }:
        return DownloadFailureClass.TERMINAL

    if code == DownloadErrorCode.VALIDATION_FAILED and any(marker in message for marker in _TERMINAL_MARKERS):
        return DownloadFailureClass.TERMINAL

    if any(marker in message for marker in _AUTH_MARKERS):
        return DownloadFailureClass.AUTH

    if any(marker in message for marker in _TERMINAL_MARKERS):
        return DownloadFailureClass.TERMINAL

    if code in {DownloadErrorCode.DOWNLOAD_FAILED, DownloadErrorCode.RESOLVE_FAILED}:
        if any(marker in message for marker in _TRANSIENT_MARKERS):
            return DownloadFailureClass.TRANSIENT
        # Prefer retry for ambiguous resolve/download failures (CDN/Playwright flakiness).
        return DownloadFailureClass.TRANSIENT

    if any(marker in message for marker in _TRANSIENT_MARKERS):
        return DownloadFailureClass.TRANSIENT

    return DownloadFailureClass.TRANSIENT


def should_auto_retry_download_failure(
    *,
    failure_class: DownloadFailureClass,
    attempts: int,
    transient_max_attempts: int | None = None,
    auth_max_attempts: int | None = None,
) -> bool:
    settings = get_settings()
    transient_cap = int(
        transient_max_attempts
        if transient_max_attempts is not None
        else getattr(settings, "douyin_download_transient_max_attempts", 8)
    )
    auth_cap = int(
        auth_max_attempts if auth_max_attempts is not None else getattr(settings, "douyin_download_auth_max_attempts", 2)
    )
    if failure_class == DownloadFailureClass.TERMINAL:
        return False
    if failure_class == DownloadFailureClass.AUTH:
        return attempts < max(1, auth_cap)
    return attempts < max(1, transient_cap)


def next_download_retry_at(*, attempts: int, now: datetime | None = None) -> datetime:
    settings = get_settings()
    base = max(1, int(getattr(settings, "douyin_download_retry_backoff_base_seconds", 5)))
    cap = max(base, int(getattr(settings, "douyin_download_retry_backoff_max_seconds", 120)))
    safe_attempts = max(1, int(attempts))
    delay = min(cap, base * (2 ** max(0, safe_attempts - 1)))
    return (now or datetime.now(UTC)) + timedelta(seconds=delay)


def download_failure_operator_message(
    *,
    failure_class: DownloadFailureClass,
    error_message: str | None,
    will_retry: bool,
) -> str:
    base = (error_message or "Download failed").strip()
    if failure_class == DownloadFailureClass.AUTH:
        if will_retry:
            return f"{base} [auth · auto-retry once]. If this keeps failing, refresh the Douyin download session then retry."
        return (
            f"{base} [auth · needs manual check]. Refresh download session: open the app-managed Douyin Chromium, "
            "log in once so cookies sync, then retry Start processing."
        )
    if failure_class == DownloadFailureClass.TERMINAL:
        return f"{base} [terminal · needs manual check]. Retry will not fix this item — inspect source/video data or cancel."
    if will_retry:
        return f"{base} [transient · auto-retry scheduled]."
    return f"{base} [transient · retries exhausted · needs manual check]."
