from __future__ import annotations

from enum import StrEnum


class TtsPipelineErrorCode(StrEnum):
    MISSING_TRANSLATION_SEGMENTS = "missing_translation_segments"
    INVALID_SEGMENT_TIMING = "invalid_segment_timing"
    TTS_PROVIDER_FAILED = "tts_provider_failed"
    CLIP_PERSIST_FAILED = "clip_persist_failed"
    NARRATION_ASSEMBLY_FAILED = "narration_assembly_failed"
    SUBTITLE_BUILD_FAILED = "subtitle_build_failed"
    MANIFEST_BUILD_FAILED = "manifest_build_failed"
    PERSISTENCE_FAILED = "persistence_failed"


class TtsPipelineError(Exception):
    def __init__(self, code: TtsPipelineErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
