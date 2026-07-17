from __future__ import annotations

from enum import StrEnum


class AudioAnalysisErrorCode(StrEnum):
    MISSING_SOURCE_ASSET = "missing_source_asset"
    AUDIO_EXTRACT_FAILED = "audio_extract_failed"
    SOURCE_SEPARATION_FAILED = "source_separation_failed"
    TRANSCRIPTION_FAILED = "transcription_failed"
    TRANSCRIPT_BUILD_FAILED = "transcript_build_failed"
    TRANSLATION_FAILED = "translation_failed"
    PERSISTENCE_FAILED = "persistence_failed"


class AudioAnalysisError(Exception):
    def __init__(self, code: AudioAnalysisErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
