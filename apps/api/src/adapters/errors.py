from enum import StrEnum


class SourceAdapterErrorCode(StrEnum):
    INVALID_URL = "invalid_url"
    UNSUPPORTED_PROFILE = "unsupported_profile"
    ADAPTER_FETCH_FAILED = "adapter_fetch_failed"
    NORMALIZATION_FAILED = "normalization_failed"
    PERSISTENCE_FAILED = "persistence_failed"
    RATE_LIMITED = "rate_limited"


class SourceAdapterError(Exception):
    def __init__(
        self,
        code: SourceAdapterErrorCode,
        message: str,
        *,
        raw_payload: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.raw_payload = raw_payload

