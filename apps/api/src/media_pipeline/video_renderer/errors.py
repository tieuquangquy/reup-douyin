"""Phase 3+4 Single Render errors."""

from __future__ import annotations

from enum import Enum


class VideoRendererErrorCode(str, Enum):
    EMPTY_OVERLAYS = "EMPTY_OVERLAYS"
    SOURCE_MISSING = "SOURCE_MISSING"
    FFMPEG_MISSING = "FFMPEG_MISSING"
    FONT_MISSING = "FONT_MISSING"
    FFMPEG_FAILED = "FFMPEG_FAILED"
    INVALID_INPUT = "INVALID_INPUT"


class VideoRendererError(Exception):
    def __init__(self, code: VideoRendererErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
