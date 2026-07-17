"""OCR filtering errors (Python 3.10+ compatible)."""

from __future__ import annotations

from enum import Enum


class OcrFilteringErrorCode(str, Enum):
    EMPTY_INPUT = "EMPTY_INPUT"
    FRAME_MISSING = "FRAME_MISSING"
    OCR_PROVIDER_FAILED = "OCR_PROVIDER_FAILED"
    OCR_PROVIDER_UNAVAILABLE = "OCR_PROVIDER_UNAVAILABLE"


class OcrFilteringError(Exception):
    def __init__(self, code: OcrFilteringErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
