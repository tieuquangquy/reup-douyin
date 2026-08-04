from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


PUBLICATION_METRIC_INPUT_FIELDS = (
    "view_count",
    "like_count",
    "comment_count",
    "share_count",
    "save_count",
    "impression_count",
    "reach_count",
    "follower_gain_count",
    "total_watch_time_seconds",
    "average_watch_time_seconds",
    "completion_rate_percent",
)


class PublicationMetricSnapshotCreateRequest(BaseModel):
    observed_at: datetime
    collection_source: Literal["MANUAL", "PLATFORM_API", "IMPORT", "LOCAL_MOCK"] = "MANUAL"
    provider_schema_version: str | None = Field(default=None, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=240)
    view_count: int | None = Field(default=None, ge=0)
    like_count: int | None = Field(default=None, ge=0)
    comment_count: int | None = Field(default=None, ge=0)
    share_count: int | None = Field(default=None, ge=0)
    save_count: int | None = Field(default=None, ge=0)
    impression_count: int | None = Field(default=None, ge=0)
    reach_count: int | None = Field(default=None, ge=0)
    follower_gain_count: int | None = Field(default=None, ge=0)
    total_watch_time_seconds: float | None = Field(default=None, ge=0)
    average_watch_time_seconds: float | None = Field(default=None, ge=0)
    completion_rate_percent: float | None = Field(default=None, ge=0, le=100)
    is_estimated: bool = False
    data_quality: Literal["UNKNOWN", "PARTIAL", "COMPLETE", "SUSPECT"] = "UNKNOWN"
    unavailable_metrics: list[str] | None = None
    provider_summary_json: dict | None = None
    metadata_json: dict | None = None

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_at_least_one_metric(self):
        if not any(getattr(self, field) is not None for field in PUBLICATION_METRIC_INPUT_FIELDS):
            raise ValueError("At least one publication metric is required")
        return self


class PublicationMetricSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    platform_publication_id: UUID
    observed_at: datetime
    collection_source: str
    provider_schema_version: str | None
    idempotency_key: str
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    share_count: int | None
    save_count: int | None
    impression_count: int | None
    reach_count: int | None
    follower_gain_count: int | None
    total_watch_time_seconds: float | None
    average_watch_time_seconds: float | None
    completion_rate_percent: float | None
    is_estimated: bool
    data_quality: str
    unavailable_metrics_json: list | None
    provider_summary_json: dict | None
    interval_seconds: int | None
    delta_view_count: int | None
    delta_like_count: int | None
    delta_comment_count: int | None
    delta_share_count: int | None
    delta_save_count: int | None
    views_per_hour: float | None
    engagement_rate_percent: float | None
    engagement_delta_rate_percent: float | None
    counter_regression_detected: bool
    derivation_version: str
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class PublicationMetricSnapshotListResponse(BaseModel):
    snapshots: list[PublicationMetricSnapshotResponse]
    total: int


class PublicationGrowthSummaryResponse(BaseModel):
    platform_publication_id: UUID
    snapshot_count: int
    first_observed_at: datetime | None = None
    latest_observed_at: datetime | None = None
    observation_hours: float | None = None
    measurement_age_seconds: int | None = None
    trend_label: Literal[
        "NO_DATA",
        "BASELINE_ONLY",
        "INSUFFICIENT_DATA",
        "GROWING",
        "FLAT",
        "COUNTER_REGRESSION",
    ]
    velocity_status: Literal[
        "NO_DATA",
        "BASELINE_ONLY",
        "INSUFFICIENT_INTERVAL",
        "STABLE",
        "COUNTER_REGRESSION",
    ]
    minimum_velocity_interval_seconds: int
    velocity_observation_seconds: int | None = None
    next_stable_measurement_at: datetime | None = None
    latest_view_count: int | None = None
    latest_like_count: int | None = None
    latest_comment_count: int | None = None
    latest_share_count: int | None = None
    latest_save_count: int | None = None
    absolute_view_growth: int | None = None
    absolute_like_growth: int | None = None
    absolute_comment_growth: int | None = None
    absolute_share_growth: int | None = None
    absolute_save_growth: int | None = None
    views_per_hour_since_first: float | None = None
    recent_views_per_hour: float | None = None
    latest_engagement_rate_percent: float | None = None
    latest_engagement_delta_rate_percent: float | None = None
    latest_data_quality: str | None = None
    latest_is_estimated: bool | None = None
    counter_regression_detected: bool = False


class PublicationMetricMockPayload(BaseModel):
    observed_at: datetime | None = None
    view_count: int | None = Field(default=None, ge=0)
    like_count: int | None = Field(default=None, ge=0)
    comment_count: int | None = Field(default=None, ge=0)
    share_count: int | None = Field(default=None, ge=0)
    save_count: int | None = Field(default=None, ge=0)
    impression_count: int | None = Field(default=None, ge=0)
    reach_count: int | None = Field(default=None, ge=0)
    follower_gain_count: int | None = Field(default=None, ge=0)
    total_watch_time_seconds: float | None = Field(default=None, ge=0)
    average_watch_time_seconds: float | None = Field(default=None, ge=0)
    completion_rate_percent: float | None = Field(default=None, ge=0, le=100)
    is_estimated: bool = False
    data_quality: Literal["UNKNOWN", "PARTIAL", "COMPLETE", "SUSPECT"] = "COMPLETE"
    unavailable_metrics: list[str] | None = None

    @field_validator("observed_at")
    @classmethod
    def optional_observed_at_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("mock_metrics.observed_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_at_least_one_metric(self):
        if not any(getattr(self, field) is not None for field in PUBLICATION_METRIC_INPUT_FIELDS):
            raise ValueError("At least one mock publication metric is required")
        return self


class PublicationMetricCollectionEnqueueRequest(BaseModel):
    collection_key: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    collector: Literal["LOCAL_MOCK", "FACEBOOK_GRAPH"] = "LOCAL_MOCK"
    external_network_authorized: bool = False
    scheduled_at: datetime | None = None
    max_attempts: int = Field(default=5, ge=1, le=10)
    mock_metrics: PublicationMetricMockPayload | None = None

    @field_validator("scheduled_at")
    @classmethod
    def scheduled_at_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("scheduled_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_collector_payload(self):
        if self.collector == "LOCAL_MOCK" and self.mock_metrics is None:
            raise ValueError("LOCAL_MOCK requires mock_metrics")
        if self.collector == "FACEBOOK_GRAPH" and self.mock_metrics is not None:
            raise ValueError("FACEBOOK_GRAPH does not accept mock_metrics")
        return self


class PublicationMetricMockGrowthProfile(BaseModel):
    view_count_per_hour: float | None = Field(default=None, ge=0)
    like_count_per_hour: float | None = Field(default=None, ge=0)
    comment_count_per_hour: float | None = Field(default=None, ge=0)
    share_count_per_hour: float | None = Field(default=None, ge=0)
    save_count_per_hour: float | None = Field(default=None, ge=0)
    impression_count_per_hour: float | None = Field(default=None, ge=0)
    reach_count_per_hour: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_at_least_one_growth_rate(self):
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("At least one LOCAL_MOCK growth rate is required")
        return self


class PublicationMetricScheduleUpsertRequest(BaseModel):
    collector: Literal["LOCAL_MOCK", "FACEBOOK_GRAPH"] = "LOCAL_MOCK"
    external_network_authorized: bool = False
    operator_confirmation: Literal["FACEBOOK_INSIGHTS_AUTO_TRACKING_APPROVED"] | None = None
    start_at: datetime | None = None
    max_age_hours: int = Field(default=168, ge=1, le=24 * 90)
    mock_growth_per_hour: PublicationMetricMockGrowthProfile | None = None
    mock_baseline_metrics: PublicationMetricMockPayload | None = None

    @field_validator("start_at")
    @classmethod
    def start_at_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("start_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_schedule_collector_config(self):
        if self.collector == "LOCAL_MOCK" and self.mock_growth_per_hour is None:
            raise ValueError("LOCAL_MOCK schedule requires mock_growth_per_hour")
        if self.collector == "FACEBOOK_GRAPH" and (
            self.mock_growth_per_hour is not None or self.mock_baseline_metrics is not None
        ):
            raise ValueError("FACEBOOK_GRAPH schedule does not accept mock configuration")
        if self.collector == "FACEBOOK_GRAPH" and (
            not self.external_network_authorized
            or self.operator_confirmation != "FACEBOOK_INSIGHTS_AUTO_TRACKING_APPROVED"
        ):
            raise ValueError(
                "FACEBOOK_GRAPH auto tracking requires explicit recurring read authorization"
            )
        return self


class PublicationMetricScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    platform_publication_id: UUID
    collector_name: str
    status: str
    policy_version: str
    next_collection_at: datetime | None
    last_enqueued_at: datetime | None
    last_completed_at: datetime | None
    last_collection_job_id: UUID | None
    last_metric_snapshot_id: UUID | None
    collection_count: int
    consecutive_flat_count: int
    max_age_hours: int
    tracking_started_at: datetime | None = None
    tracking_ends_at: datetime | None = None
    collector_config_json: dict | None
    last_decision_json: dict | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class PublicationMetricScheduleListResponse(BaseModel):
    schedules: list[PublicationMetricScheduleResponse]
    total: int


class PublicationMetricTrackingJobSummary(BaseModel):
    id: UUID
    status: str
    progress_percent: int
    attempts: int
    max_attempts: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class PublicationMetricTrackingMonitorItem(BaseModel):
    schedule: PublicationMetricScheduleResponse
    platform_account_id: UUID
    page_display_name: str
    external_reel_id: str | None = None
    external_permalink: str | None = None
    caption: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    health_status: Literal[
        "HEALTHY",
        "WAITING",
        "DELAYED",
        "COOLDOWN",
        "BLOCKED",
        "PAUSED",
        "COMPLETED",
    ]
    health_reason: str
    growth: PublicationGrowthSummaryResponse
    last_job: PublicationMetricTrackingJobSummary | None = None


class PublicationMetricTrackingMonitorKpis(BaseModel):
    active_count: int = 0
    due_soon_count: int = 0
    needs_attention_count: int = 0
    paused_count: int = 0
    completed_count: int = 0
    snapshots_today_count: int = 0


class PublicationMetricTrackingMonitorResponse(BaseModel):
    items: list[PublicationMetricTrackingMonitorItem]
    total: int
    limit: int
    offset: int
    kpis: PublicationMetricTrackingMonitorKpis


class PublicationMetricScheduleDispatchRequest(BaseModel):
    now: datetime | None = None
    limit: int = Field(default=20, ge=1, le=200)

    @field_validator("now")
    @classmethod
    def now_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("now must include a timezone")
        return value


class PublicationMetricScheduleDispatchResponse(BaseModel):
    evaluated_count: int
    enqueued_count: int
    blocked_count: int
    completed_count: int
    job_ids: list[UUID] = Field(default_factory=list)


class FacebookInsightsLivePilotPreflightRequest(BaseModel):
    operator_confirmation: Literal["FACEBOOK_INSIGHTS_LIVE_PILOT_APPROVED"]
    expected_platform_account_id: UUID
    expected_external_account_id: str = Field(min_length=1, max_length=180)
    expected_media_id: str = Field(min_length=1, max_length=240)
    required_scopes: list[str] = Field(
        default_factory=lambda: ["read_insights", "pages_read_engagement"],
        min_length=1,
        max_length=20,
    )

    @field_validator("required_scopes")
    @classmethod
    def normalize_required_scopes(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in values:
            value = str(raw).strip()
            if not value or not value.replace("_", "").isalnum():
                raise ValueError("required_scopes must contain simple permission names")
            if value not in normalized:
                normalized.append(value)
        return normalized


class FacebookInsightsLivePilotCheck(BaseModel):
    code: str
    passed: bool
    blocking: bool
    message: str


class FacebookInsightsLivePilotPreflightResponse(BaseModel):
    ready_for_live_job: bool
    network_used: bool = False
    platform_publication_id: UUID
    platform_account_id: UUID
    media_reference_source: str
    graph_api_version: str
    token_resolution_deferred_to_worker: bool = True
    checks: list[FacebookInsightsLivePilotCheck]
    blocker_codes: list[str]
