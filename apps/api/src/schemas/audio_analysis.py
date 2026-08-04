from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.audio_pipeline.types import TranslationPreset
from src.enums import JobStatus, TranscriptSegmentStatus


class AudioAnalysisCreateRequest(BaseModel):
    source_video_id: UUID
    translation_preset: TranslationPreset = TranslationPreset.LITERAL_SAFE
    force_refresh: bool = False
    skip_translation: bool = True


class ApproveSourceTranscriptResponse(BaseModel):
    source_video_id: UUID
    approved_segments: int
    dialogue_phase: str


class ApproveTranslationDraftRequest(BaseModel):
    operator_id: str = "frontend_operator"


class ApproveTranslationDraftResponse(BaseModel):
    source_video_id: UUID
    approved_segments: int
    binding_sha256: str
    resumed_queue_items: int = 0
    job_id: UUID | None = None


class AudioAnalysisCreateResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    source_video_id: UUID
    translation_preset: TranslationPreset


class SegmentEditRequest(BaseModel):
    transcript_segment_id: UUID
    translation_segment_id: UUID | None = None
    start_ms: int
    end_ms: int
    source_text: str
    translated_text: str
    status: TranscriptSegmentStatus = TranscriptSegmentStatus.NEEDS_REVIEW


class SaveTranscriptDraftRequest(BaseModel):
    segments: list[SegmentEditRequest]


class TranscriptEditSummaryResponse(BaseModel):
    source_video_id: UUID
    updated_segments: int = 0
    message: str


class MergeSegmentsRequest(BaseModel):
    left_transcript_segment_id: UUID
    right_transcript_segment_id: UUID


class SplitSegmentRequest(BaseModel):
    transcript_segment_id: UUID
    split_ms: int
    left_source_text: str
    right_source_text: str
    left_translated_text: str
    right_translated_text: str


class RerunTranslationDraftRequest(BaseModel):
    translation_preset: TranslationPreset = TranslationPreset.LITERAL_SAFE
    force_refresh: bool = True
    require_source_approved: bool = True


class TranscriptSegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_video_id: UUID
    segment_index: int
    version: int
    start_ms: int
    end_ms: int
    text: str
    normalized_text: str | None
    language_code: str | None
    status: TranscriptSegmentStatus
    confidence: float | None
    speaker_label: str | None
    difficulty_flags_json: dict | None
    analysis_version: str | None
    created_by_job_id: UUID | None
    is_current: bool
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class TranslationSegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_video_id: UUID
    transcript_segment_id: UUID
    segment_index: int | None
    language_code: str
    version: int
    text: str
    status: TranscriptSegmentStatus
    translation_preset: str | None
    duration_budget_ms: int | None
    estimated_tts_duration_ms: int | None
    quality_flags_json: dict | None
    created_by_job_id: UUID | None
    is_current: bool
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class TranscriptListResponse(BaseModel):
    source_video_id: UUID
    analysis_version: str | None
    segments: list[TranscriptSegmentResponse]


class TranslationDraftListResponse(BaseModel):
    source_video_id: UUID
    translation_preset: str | None
    segments: list[TranslationSegmentResponse]


class AudioAnalysisSummaryResponse(BaseModel):
    source_video_id: UUID
    analysis_version: str | None
    transcript_count: int
    translation_count: int
    asset_count: int
    manifest: dict
    has_speech: bool | None = None
    dialogue_phase: str | None = None
