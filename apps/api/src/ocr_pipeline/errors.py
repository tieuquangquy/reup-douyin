"""OCR pipeline errors."""

from __future__ import annotations

from enum import StrEnum


class OcrPipelineErrorCode(StrEnum):
    MISSING_SOURCE_VIDEO = "MISSING_SOURCE_VIDEO"
    MISSING_SOURCE_VIDEO_ASSET = "MISSING_SOURCE_VIDEO_ASSET"
    FRAME_SAMPLE_FAILED = "FRAME_SAMPLE_FAILED"
    OCR_PROVIDER_FAILED = "OCR_PROVIDER_FAILED"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    CLEAN_HARD_SUB_FAILED = "CLEAN_HARD_SUB_FAILED"


class OcrPipelineError(Exception):
    def __init__(self, code: OcrPipelineErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
