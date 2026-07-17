from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from src.enums import MediaAssetType


AUDIO_ANALYSIS_VERSION = "AUDIO_ANALYSIS_V1"


class TranslationPreset(StrEnum):
    LITERAL_SAFE = "literal_safe"
    NATURAL_VIRAL = "natural_viral"
    AFFILIATE_SOFT_SELL = "affiliate_soft_sell"


@dataclass(frozen=True)
class AudioAnalysisRequest:
    source_video_id: UUID
    translation_preset: TranslationPreset = TranslationPreset.LITERAL_SAFE
    force_refresh: bool = False
    # Phase A (DialogueBeat): ASR + timed source only. Phase B translates after approve.
    skip_translation: bool = True


@dataclass(frozen=True)
class ResolvedAudioInput:
    source_video_id: UUID
    input_asset_id: UUID
    input_asset_type: MediaAssetType
    storage_key: str
    source_video_duration_seconds: float | None
    source_caption: str | None = None


@dataclass(frozen=True)
class AudioExtractionResult:
    audio_asset_id: UUID | None
    storage_key: str
    generated_asset: bool
    fallback_used: bool
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SourceSeparationResult:
    vocal_asset_id: UUID | None
    background_asset_id: UUID | None
    transcription_storage_key: str
    fallback_used: bool
    difficulty_flags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VadResult:
    has_speech: bool
    speech_ratio: float | None = None
    difficulty_flags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TranscriptionUnit:
    text: str
    start_seconds: float
    end_seconds: float
    confidence: float | None = None
    speaker_label: str | None = None
    flags: list[str] = field(default_factory=list)
    raw_payload: dict | None = None


@dataclass(frozen=True)
class TranscriptDraftSegment:
    segment_index: int
    start_seconds: float
    end_seconds: float
    source_text: str
    normalized_source_text: str
    confidence: float | None
    speaker_label: str | None
    difficulty_flags: list[str]
    metadata: dict = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_seconds - self.start_seconds)


@dataclass(frozen=True)
class TranslationDraftSegment:
    segment_index: int
    translated_text: str
    translation_preset: TranslationPreset
    duration_budget_seconds: float
    estimated_tts_duration_seconds: float | None
    quality_flags: list[str]
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AudioAnalysisResult:
    source_video_id: UUID
    analysis_version: str
    transcript_count: int
    translation_count: int
    asset_count: int
    flags_summary: dict[str, int]
    manifest: dict
