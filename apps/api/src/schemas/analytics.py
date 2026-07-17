from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.enums import (
    ExternalPublicationStatus,
    OperatorFeedbackQualityLabel,
    OperatorFeedbackRootCause,
    OperatorFeedbackTargetType,
    PublishAttemptStatus,
    PublishConfidenceLabel,
    PublishDraftStatus,
    PublishTargetPlatform,
)


class PublishHealthOverview(BaseModel):
    total_attempts: int = 0
    succeeded_attempts: int = 0
    failed_attempts: int = 0
    needs_reconciliation_attempts: int = 0
    canonical_published_count: int = 0
    drafts_ready_not_published: int = 0
    drafts_blocked_by_risk: int = 0
    success_rate_percent: float = 0.0


class PublishDayStats(BaseModel):
    day: str
    attempts: int = 0
    succeeded: int = 0
    failed: int = 0
    needs_reconciliation: int = 0


class AccountHealthSummary(BaseModel):
    platform_account_id: UUID | None = None
    display_name: str
    platform: PublishTargetPlatform | str
    attempts: int = 0
    succeeded: int = 0
    failed: int = 0
    needs_reconciliation: int = 0
    success_rate_percent: float = 0.0
    recent_error_code: str | None = None


class FailureCategorySummary(BaseModel):
    error_code: str
    count: int
    label: str


class PublicationOutcomeItem(BaseModel):
    publish_draft_id: UUID
    source_video_id: UUID
    render_output_id: UUID | None = None
    platform: str
    status: PublishDraftStatus
    external_status: ExternalPublicationStatus
    external_publish_id: str | None = None
    external_permalink: str | None = None
    canonical_publish_attempt_id: UUID | None = None
    platform_account_id: UUID | None = None
    source_profile_name: str | None = None
    preset_name: str | None = None
    niche_label: str | None = None
    score: float | None = None
    published_at: datetime | None = None
    last_publish_synced_at: datetime | None = None
    feedback_quality_label: OperatorFeedbackQualityLabel | None = None
    feedback_confidence: PublishConfidenceLabel | None = None


class PipelineFeedbackGroup(BaseModel):
    group_key: str
    label: str
    published_count: int = 0
    good_feedback_count: int = 0
    weak_feedback_count: int = 0
    needs_reconciliation_count: int = 0
    average_score: float | None = None


class OperatorActionQueue(BaseModel):
    needs_reconciliation: list[PublicationOutcomeItem] = Field(default_factory=list)
    drafts_ready: list[PublicationOutcomeItem] = Field(default_factory=list)
    blocked_by_risk_count: int = 0
    recent_successes: list[PublicationOutcomeItem] = Field(default_factory=list)


class PublishHealthDashboardResponse(BaseModel):
    generated_at: datetime
    window: str
    window_start: datetime
    window_end: datetime
    overview: PublishHealthOverview
    by_day: list[PublishDayStats]
    account_health: list[AccountHealthSummary]
    failure_categories: list[FailureCategorySummary]
    action_queue: OperatorActionQueue
    pipeline_feedback: dict[str, list[PipelineFeedbackGroup]]


class OperatorFeedbackCreateRequest(BaseModel):
    target_type: OperatorFeedbackTargetType
    target_id: UUID
    quality_label: OperatorFeedbackQualityLabel
    publish_confidence: PublishConfidenceLabel
    root_cause: OperatorFeedbackRootCause | None = None
    note: str | None = None
    created_by: str | None = "local_operator"
    metadata_json: dict | None = None


class OperatorFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    target_type: OperatorFeedbackTargetType
    target_id: UUID
    source_video_id: UUID | None
    render_output_id: UUID | None
    publish_draft_id: UUID | None
    publish_attempt_id: UUID | None
    quality_label: OperatorFeedbackQualityLabel
    publish_confidence: PublishConfidenceLabel
    root_cause: OperatorFeedbackRootCause | None
    note: str | None
    created_by: str | None
    feedback_at: datetime
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class OperatorFeedbackListResponse(BaseModel):
    feedback: list[OperatorFeedbackResponse]


class FailureSummaryResponse(BaseModel):
    generated_at: datetime
    window: str
    failure_categories: list[FailureCategorySummary]
    recent_failed_attempts: list[PublicationOutcomeItem]
    reconciliation_needed: list[PublicationOutcomeItem]


class PipelineFeedbackResponse(BaseModel):
    generated_at: datetime
    window: str
    by_source_profile: list[PipelineFeedbackGroup]
    by_niche: list[PipelineFeedbackGroup]
    by_preset: list[PipelineFeedbackGroup]
