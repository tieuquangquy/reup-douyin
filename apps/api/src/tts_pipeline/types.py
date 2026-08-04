from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID


TTS_PIPELINE_VERSION = "TTS_PIPELINE_V2"


class TimingFitStatus(StrEnum):
    FITS_WELL = "fits_well"
    SLIGHTLY_LONG = "slightly_long"
    TOO_LONG = "too_long"
    TOO_SHORT = "too_short"


@dataclass(frozen=True)
class VoiceConfig:
    voice_id: str = "vi-VN-HoaiMyNeural"
    language_code: str = "vi"
    speaking_rate: float = 1.0


@dataclass(frozen=True)
class TtsRequest:
    source_video_id: UUID
    voice_config: VoiceConfig = field(default_factory=VoiceConfig)
    force_refresh: bool = False
    # Immutable auto-queue recipe authority. Manual Preview/Generate requests
    # leave this unset and continue using the active Ops workspace profile.
    runtime_authority: dict | None = None


@dataclass(frozen=True)
class TranslationInputSegment:
    translation_segment_id: UUID
    transcript_segment_id: UUID
    source_video_id: UUID
    segment_index: int
    start_ms: int
    end_ms: int
    translated_text: str
    duration_budget_ms: int
    translation_version: int
    translation_preset: str | None
    quality_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TtsProviderInput:
    text: str
    language_code: str
    voice_config: VoiceConfig
    target_duration_seconds: float | None = None


@dataclass(frozen=True)
class TtsProviderOutput:
    audio_bytes: bytes
    duration_seconds: float
    mime_type: str
    file_extension: str
    provider_metadata: dict
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SynthesizedSegment:
    input_segment: TranslationInputSegment
    audio_bytes: bytes
    duration_seconds: float
    mime_type: str
    file_extension: str
    provider_metadata: dict
    warnings: list[str]
    fit_status: TimingFitStatus
    fit_ratio: float


@dataclass(frozen=True)
class SubtitleDraftSegment:
    translation_segment_id: UUID
    segment_index: int
    start_ms: int
    end_ms: int
    text: str
    layout_mode: str
    track_kind: str
    review_flags: list[str]
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RenderPrepResult:
    source_video_id: UUID
    pipeline_version: str
    subtitle_count: int
    tts_clip_count: int
    asset_count: int
    timing_fit_summary: dict[str, int]
    warnings: list[str]
    manifest: dict
