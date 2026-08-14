from __future__ import annotations

from enum import StrEnum


class TtsPipelineErrorCode(StrEnum):
    MISSING_TRANSLATION_SEGMENTS = "missing_translation_segments"
    TRANSLATION_REVIEW_REQUIRED = "translation_review_required"
    INVALID_SEGMENT_TIMING = "invalid_segment_timing"
    TTS_ACTIVE_SETUP_REQUIRED = "tts_active_setup_required"
    TTS_AUTHORITY_CHANGED = "tts_authority_changed"
    TTS_INPUT_PREFLIGHT_BLOCKED = "tts_input_preflight_blocked"
    TTS_PROVIDER_FAILED = "tts_provider_failed"
    TIMING_FIT_BLOCKED = "timing_fit_blocked"
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
