from enum import StrEnum


class DownloadFailureReason(StrEnum):
    """Structured reason attached to a stable public download error code."""

    AUTH_EXPIRED = "auth_expired"
    CHALLENGE_BLOCKED = "challenge_blocked"
    NO_CLEAN_STREAM = "no_clean_stream"
    SIGNED_URL_EXPIRED = "signed_url_expired"
    EXTRACTOR_DRIFT = "extractor_drift"
    UNSUPPORTED_POST_TYPE = "unsupported_post_type"
    MEDIA_CORRUPT = "media_corrupt"
    NETWORK_TRANSIENT = "network_transient"


class DownloadErrorCode(StrEnum):
    INVALID_SOURCE_VIDEO = "invalid_source_video"
    MISSING_SOURCE_URL = "missing_source_url"
    RESOLVE_FAILED = "resolve_failed"
    STORAGE_RESOLUTION_FAILED = "storage_resolution_failed"
    DOWNLOAD_FAILED = "download_failed"
    WRITE_FAILED = "write_failed"
    VALIDATION_FAILED = "validation_failed"
    CANCELLED = "cancelled"
    MANIFEST_UPDATE_FAILED = "manifest_update_failed"


class DownloadError(Exception):
    def __init__(
        self,
        code: DownloadErrorCode,
        message: str,
        *,
        reason: DownloadFailureReason | str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.reason = str(reason) if reason is not None else None
