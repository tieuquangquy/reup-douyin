from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
from uuid import UUID


TTS_PIPELINE_VERSION = "TTS_TEMPORAL_V6"


class TimingFitStatus(StrEnum):
    FITS_WELL = "fits_well"
    SLIGHTLY_LONG = "slightly_long"
    TOO_LONG = "too_long"
    TOO_SHORT = "too_short"


@dataclass(frozen=True)
class VoiceConfig:
    voice_id: str = "instruct:vi_female_north"
    language_code: str = "vi"
    speaking_rate: float = 1.0


@dataclass(frozen=True)
class VoiceBible:
    """Provider-neutral voice direction recipe, never a model-training artifact."""

    schema_version: str = "tts-voice-bible-v1"
    voice_id: str = ""
    language_code: str = "vi"
    provider: str = ""
    model_id: str = ""
    persona: str = ""
    accent: str = ""
    speaking_style: str = "natural conversational narration"
    baseline_pace: float = 1.0
    energy: float = 0.5
    articulation: str = "clear natural articulation"
    breathing_behavior: str = "natural breathing"
    pause_behavior: str = "short natural pauses at phrase boundaries"
    director_rules: tuple[str, ...] = field(default_factory=tuple)
    recipe_version: str = "tts-director-v1"

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "voice_id": self.voice_id,
            "language_code": self.language_code,
            "provider": self.provider,
            "model_id": self.model_id,
            "persona": self.persona,
            "accent": self.accent,
            "speaking_style": self.speaking_style,
            "baseline_pace": round(float(self.baseline_pace), 6),
            "energy": round(float(self.energy), 6),
            "articulation": self.articulation,
            "breathing_behavior": self.breathing_behavior,
            "pause_behavior": self.pause_behavior,
            "director_rules": list(self.director_rules),
            "recipe_version": self.recipe_version,
        }


@dataclass(frozen=True)
class ProsodyState:
    """Explicit continuity state passed between performance chunks."""

    speaker: str = "narrator_01"
    current_emotion: str = "neutral"
    energy: float = 0.5
    pace: float = 1.0
    pitch_state: str = "mid"
    previous_intent: str = "continuing"

    def to_dict(self) -> dict:
        return {
            "speaker": self.speaker,
            "current_emotion": self.current_emotion,
            "energy": round(float(self.energy), 6),
            "pace": round(float(self.pace), 6),
            "pitch_state": self.pitch_state,
            "previous_intent": self.previous_intent,
        }


@dataclass(frozen=True)
class ProsodySpan:
    """Clause-level delivery direction inside one immutable timeline segment."""

    text: str
    emotion: str = "neutral"
    intensity: float = 0.4
    pace: float = 1.0
    pause_after_ms: int = 120
    emphasis: tuple[str, ...] = field(default_factory=tuple)
    audio_tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "emotion": self.emotion,
            "intensity": round(float(self.intensity), 6),
            "pace": round(float(self.pace), 6),
            "pause_after_ms": int(self.pause_after_ms),
            "emphasis": list(self.emphasis),
            "audio_tags": list(self.audio_tags),
        }


@dataclass(frozen=True)
class ProsodySegment:
    """Provider-neutral performance direction for one timeline segment."""

    translation_segment_id: UUID
    segment_index: int
    start_ms: int
    end_ms: int
    emotion: str = "neutral"
    intensity: float = 0.4
    pace: float = 1.0
    pause_before_ms: int = 0
    pause_after_ms: int = 0
    emphasis: tuple[str, ...] = field(default_factory=tuple)
    breath: str = "natural"
    transition: str = "continue"
    semantic_weight: float = 0.5
    speaker_state: str = "engaged"
    audio_tags: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.5
    previous_state: ProsodyState = field(default_factory=ProsodyState)
    target_state: ProsodyState = field(default_factory=ProsodyState)
    source: str = "local_director"
    spans: tuple[ProsodySpan, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "translation_segment_id": str(self.translation_segment_id),
            "segment_index": int(self.segment_index),
            "start_ms": int(self.start_ms),
            "end_ms": int(self.end_ms),
            "emotion": self.emotion,
            "intensity": round(float(self.intensity), 6),
            "pace": round(float(self.pace), 6),
            "pause_before_ms": int(self.pause_before_ms),
            "pause_after_ms": int(self.pause_after_ms),
            "emphasis": list(self.emphasis),
            "breath": self.breath,
            "transition": self.transition,
            "semantic_weight": round(float(self.semantic_weight), 6),
            "speaker_state": self.speaker_state,
            "audio_tags": list(self.audio_tags),
            "confidence": round(float(self.confidence), 6),
            "previous_state": self.previous_state.to_dict(),
            "target_state": self.target_state.to_dict(),
            "source": self.source,
            "spans": [span.to_dict() for span in self.spans],
        }


@dataclass(frozen=True)
class PerformanceChunk:
    """Semantic/prosodic unit that still maps losslessly to timeline members."""

    chunk_id: str
    source_video_id: UUID
    start_ms: int
    end_ms: int
    translated_text: str
    member_translation_segment_ids: tuple[UUID, ...] = field(default_factory=tuple)
    member_segment_indices: tuple[int, ...] = field(default_factory=tuple)
    speaker_label: str | None = None
    prosody_segments: tuple[ProsodySegment, ...] = field(default_factory=tuple)
    previous_state: ProsodyState = field(default_factory=ProsodyState)
    target_state: ProsodyState = field(default_factory=ProsodyState)
    boundary_reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source_video_id": str(self.source_video_id),
            "start_ms": int(self.start_ms),
            "end_ms": int(self.end_ms),
            "translated_text": self.translated_text,
            "member_translation_segment_ids": [str(value) for value in self.member_translation_segment_ids],
            "member_segment_indices": list(self.member_segment_indices),
            "speaker_label": self.speaker_label,
            "prosody_segments": [row.to_dict() for row in self.prosody_segments],
            "previous_state": self.previous_state.to_dict(),
            "target_state": self.target_state.to_dict(),
            "boundary_reasons": list(self.boundary_reasons),
        }


@dataclass(frozen=True)
class TtsDirectorPlan:
    source_video_id: UUID
    voice_bible: VoiceBible
    prosody_segments: tuple[ProsodySegment, ...]
    source_context_sha256: str
    schema_version: str = "tts-director-plan-v1"
    director_version: str = "context-aware-tts-director-v1"

    def to_dict(self) -> dict:
        payload = {
            "schema_version": self.schema_version,
            "director_version": self.director_version,
            "source_video_id": str(self.source_video_id),
            "voice_bible": self.voice_bible.to_dict(),
            "source_context_sha256": self.source_context_sha256,
            "prosody_segments": [row.to_dict() for row in self.prosody_segments],
        }
        payload["voice_bible_sha256"] = _sha256_tts_json(payload["voice_bible"])
        payload["plan_sha256"] = _sha256_tts_json(payload)
        return payload


def _sha256_tts_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class TtsRequest:
    source_video_id: UUID
    voice_config: VoiceConfig = field(default_factory=VoiceConfig)
    force_refresh: bool = False
    # Secret-free snapshot of the one enabled Ops setup. create_tts_job
    # binds it; workers verify it again before synthesis. Preview is separate.
    runtime_authority: dict | None = None
    # Immutable Translation Draft handoff. Legacy jobs may omit these fields,
    # but newly-created jobs always bind both and workers fail closed if the
    # current database state no longer matches them.
    translation_input_sha256: str | None = None
    translation_authority_sha256: str | None = None


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
    translation_status: str = ""
    source_text: str = ""
    speaker_label: str | None = None
    member_translation_segment_ids: tuple[UUID, ...] = field(default_factory=tuple)
    member_transcript_segment_ids: tuple[UUID, ...] = field(default_factory=tuple)
    member_segment_indices: tuple[int, ...] = field(default_factory=tuple)
    candidate_texts: tuple[str, ...] = field(default_factory=tuple)
    original_start_ms: int | None = None
    original_end_ms: int | None = None
    repair_actions: tuple[str, ...] = field(default_factory=tuple)
    source_prosody: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TtsProviderInput:
    text: str
    language_code: str
    voice_config: VoiceConfig
    target_duration_seconds: float | None = None
    voice_direction: str | None = None
    sample_context: str | None = None
    audio_tags: tuple[str, ...] = field(default_factory=tuple)
    prosody_state: dict | None = None
    performance_chunk_id: str | None = None
    ssml_text: str | None = None
    expressive_mode: str = "best_effort"
    requested_features: tuple[str, ...] = field(default_factory=tuple)


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
