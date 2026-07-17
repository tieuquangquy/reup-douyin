from enum import StrEnum


class DownloadErrorCode(StrEnum):
    INVALID_SOURCE_VIDEO = "invalid_source_video"
    MISSING_SOURCE_URL = "missing_source_url"
    RESOLVE_FAILED = "resolve_failed"
    STORAGE_RESOLUTION_FAILED = "storage_resolution_failed"
    DOWNLOAD_FAILED = "download_failed"
    WRITE_FAILED = "write_failed"
    VALIDATION_FAILED = "validation_failed"
    MANIFEST_UPDATE_FAILED = "manifest_update_failed"


class DownloadError(Exception):
    def __init__(self, code: DownloadErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

