from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from src.enums import MediaAssetType


# V5 keeps Target Speech as soft acoustic evidence, runs one high-recall primary
# ASR path, selectively verifies only uncertain spans, and applies a global
# dialogue decoder before any unit can become a DialogueBeat.
AUDIO_ANALYSIS_VERSION = "AUDIO_ANALYSIS_V5"
AUDIO_ANALYSIS_RECIPE_VERSION = "audio-analysis-v5-selective-dialogue-validation1-asr-evidence1-adaptive-separation2"
AUTHORITY_MANIFEST_SCHEMA_VERSION = "audio-analysis-authority-manifest-v1"


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
    # SHA of the bytes that were actually resolved.  Older test doubles and
    # legacy rows may not provide it, so the field is optional and appended.
    source_checksum_sha256: str | None = None
    canonicalized: bool = False


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
    metrics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AudioAnalysisAuthorityManifest:
    """Hash-bound contract consumed by translation, TTS and render stages."""

    schema_version: str
    analysis_version: str
    analysis_fingerprint: str
    source_audio_checksum_sha256: str | None
    canonical_audio_checksum_sha256: str | None
    transcript_sha256: str
    target_speech_authority_sha256: str
    semantic_dialogue_authority_sha256: str | None
    dialogue_quality_complete: bool
    semantic_translation_ready: bool
    machine_approval_state: str
    operator_review_required: bool
    translation_ready: bool

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "analysis_version": self.analysis_version,
            "analysis_fingerprint": self.analysis_fingerprint,
            "source_audio_checksum_sha256": self.source_audio_checksum_sha256,
            "canonical_audio_checksum_sha256": self.canonical_audio_checksum_sha256,
            "transcript_sha256": self.transcript_sha256,
            "target_speech_authority_sha256": self.target_speech_authority_sha256,
            "semantic_dialogue_authority_sha256": self.semantic_dialogue_authority_sha256,
            "dialogue_quality_complete": self.dialogue_quality_complete,
            "semantic_translation_ready": self.semantic_translation_ready,
            "machine_approval_state": self.machine_approval_state,
            "operator_review_required": self.operator_review_required,
            "translation_ready": self.translation_ready,
        }
