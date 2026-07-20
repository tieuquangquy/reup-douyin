"""Frame sampling errors."""

from __future__ import annotations

from enum import Enum


class FrameSamplingErrorCode(str, Enum):
    """str Enum for Python 3.10+ (Alpine Cloud Run image uses 3.10)."""

    INVALID_SAMPLE_FPS = "INVALID_SAMPLE_FPS"
    FFMPEG_MISSING = "FFMPEG_MISSING"
    SOURCE_MISSING = "SOURCE_MISSING"
    SOURCE_RESOLVE_FAILED = "SOURCE_RESOLVE_FAILED"
    FFMPEG_FAILED = "FFMPEG_FAILED"
    NO_FRAMES = "NO_FRAMES"
    ONNX_MISSING = "ONNX_MISSING"
    ONNX_LOAD_FAILED = "ONNX_LOAD_FAILED"
    ONNX_INFER_FAILED = "ONNX_INFER_FAILED"
    MODEL_DOWNLOAD_FAILED = "MODEL_DOWNLOAD_FAILED"
    INVALID_BACKEND = "INVALID_BACKEND"


class FrameSamplingError(Exception):
    def __init__(self, code: FrameSamplingErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
