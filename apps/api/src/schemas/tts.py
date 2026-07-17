from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.enums import JobStatus, TranscriptSegmentStatus


class VoiceConfigRequest(BaseModel):
    voice_id: str = "vi-VN-HoaiMyNeural"
    language_code: str = "vi"
    speaking_rate: float = 1.0


class TtsCreateRequest(BaseModel):
    source_video_id: UUID
    voice_config: VoiceConfigRequest = VoiceConfigRequest()
    force_refresh: bool = False


class TtsCreateResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    source_video_id: UUID


class SubtitleSegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_video_id: UUID
    translation_segment_id: UUID | None
    segment_index: int
    version: int
    start_ms: int
    end_ms: int
    text: str
    status: TranscriptSegmentStatus
    style_json: dict | None
    layout_mode: str | None
    track_kind: str | None
    review_flags_json: dict | None
    subtitle_version: str | None
    created_by_job_id: UUID | None
    is_current: bool
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class SubtitleListResponse(BaseModel):
    source_video_id: UUID
    subtitle_version: str | None
    segments: list[SubtitleSegmentResponse]


class TtsClipFitResponse(BaseModel):
    asset_id: str
    translation_segment_id: str | None = None
    fit_status: str | None = None
    fit_ratio: float | None = None
    duration_seconds: float | None = None
    warnings: list[str] = []


class TtsTimingFitSummaryResponse(BaseModel):
    fits_well: int = 0
    slightly_long: int = 0
    too_long: int = 0
    too_short: int = 0


class TtsSummaryResponse(BaseModel):
    source_video_id: UUID
    tts_asset_count: int
    subtitle_count: int
    warnings: list[str]
    clips: list[TtsClipFitResponse] = []
    timing_fit_summary: TtsTimingFitSummaryResponse = TtsTimingFitSummaryResponse()
    assets: list[dict]
