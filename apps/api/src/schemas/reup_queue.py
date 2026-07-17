from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.enums import ReupQueueAction, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.schemas.candidates import CandidateSourceVideoSummary


class ReupQueueAvailableActionResponse(BaseModel):
    action: ReupQueueAction
    label: str
    description: str
    requires_note: bool = False


class ReupQueueItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    video_candidate_id: UUID
    source_video_id: UUID
    status: ReupQueueStatus
    bucket: str
    next_action: str
    priority: int
    queued_reason: str | None
    operator_note: str | None
    last_error_code: str | None
    last_error_message: str | None
    media_prep_status: ReupQueueMediaPrepStatus
    media_prep_notes: str | None
    media_ready_at: datetime | None
    blocked_reason: str | None
    blocked_at: datetime | None
    held_at: datetime | None
    failed_at: datetime | None
    last_action: ReupQueueAction | None
    last_action_at: datetime | None
    last_action_note: str | None
    available_actions: list[ReupQueueAvailableActionResponse] = Field(default_factory=list)
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    operator_dismissed_at: datetime | None = None
    job_id: UUID | None
    job_type: str | None = None
    job_status: str | None = None
    job_progress_percent: int | None = None
    job_error_code: str | None = None
    job_error_message: str | None = None
    render_output_id: UUID | None
    publish_draft_id: UUID | None
    metadata_json: dict | None
    source_video: CandidateSourceVideoSummary | None = None
    # DialogueBeat summary from ANALYZE_AUDIO (SourceVideo.metadata_json + beat count).
    has_speech: bool | None = None
    dialogue_phase: str | None = None
    transcript_count: int | None = None
    created_at: datetime
    updated_at: datetime


class ReupQueueListResponse(BaseModel):
    items: list[ReupQueueItemResponse]
    total_count: int
    limit: int
    offset: int
    status_counts: dict[str, int] = Field(default_factory=dict)


class ReupQueueActionRequest(BaseModel):
    action: ReupQueueAction
    note: str | None = Field(default=None, max_length=1000)
    blocked_reason: str | None = Field(default=None, max_length=1000)
    media_prep_notes: str | None = Field(default=None, max_length=1000)
    media_prep_status: ReupQueueMediaPrepStatus | None = None


class ReupQueueEnqueueRequest(BaseModel):
    candidate_ids: list[UUID] = Field(min_length=1, max_length=500)
    priority: int = Field(default=100, ge=0, le=1000)
    queued_reason: str | None = Field(default="review_board_approved", max_length=500)
    operator_note: str | None = Field(default=None, max_length=1000)


class ReupQueueActionResponse(BaseModel):
    item: ReupQueueItemResponse


class ReupQueueEnqueueResponse(BaseModel):
    requested_count: int
    queued_count: int
    already_queued_count: int
    skipped_count: int
    items: list[ReupQueueItemResponse]
    skipped_candidate_ids: list[UUID] = Field(default_factory=list)


class ReupQueuePurgeRequest(BaseModel):
    item_ids: list[UUID] | None = Field(default=None, max_length=500)
    scope: str = Field(default="clearable", pattern="^(clearable|selected)$")


class ReupQueuePurgeResponse(BaseModel):
    requested_count: int
    purged_count: int
    skipped_count: int
    skipped_item_ids: list[UUID] = Field(default_factory=list)
