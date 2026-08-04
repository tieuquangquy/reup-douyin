from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel
from src.enums import (
    OperatorFeedbackQualityLabel,
    OperatorFeedbackRootCause,
    OperatorFeedbackTargetType,
    PublishConfidenceLabel,
)


class OperatorFeedback(BaseModel):
    __tablename__ = "operator_feedback"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    target_type: Mapped[OperatorFeedbackTargetType] = mapped_column(
        Enum(OperatorFeedbackTargetType, name="operator_feedback_target_type"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[UUID] = mapped_column(index=True)
    source_video_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_videos.id"), index=True)
    render_output_id: Mapped[UUID | None] = mapped_column(ForeignKey("render_outputs.id"), index=True)
    publish_draft_id: Mapped[UUID | None] = mapped_column(ForeignKey("publish_drafts.id"), index=True)
    publish_attempt_id: Mapped[UUID | None] = mapped_column(ForeignKey("publish_attempts.id"), index=True)
    quality_label: Mapped[OperatorFeedbackQualityLabel] = mapped_column(
        Enum(OperatorFeedbackQualityLabel, name="operator_feedback_quality_label"),
        nullable=False,
        index=True,
    )
    publish_confidence: Mapped[PublishConfidenceLabel] = mapped_column(
        Enum(PublishConfidenceLabel, name="publish_confidence_label"),
        nullable=False,
        index=True,
    )
    root_cause: Mapped[OperatorFeedbackRootCause | None] = mapped_column(
        Enum(OperatorFeedbackRootCause, name="operator_feedback_root_cause"),
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(120))
    feedback_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)


class PublicationMetricSnapshot(BaseModel):
    """One cumulative platform measurement for a confirmed external publication."""

    __tablename__ = "publication_metric_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "platform_publication_id",
            "idempotency_key",
            name="uq_publication_metric_snapshots_publication_idempotency",
        ),
        CheckConstraint("view_count IS NULL OR view_count >= 0", name="publication_metrics_view_nonnegative"),
        CheckConstraint("like_count IS NULL OR like_count >= 0", name="publication_metrics_like_nonnegative"),
        CheckConstraint("comment_count IS NULL OR comment_count >= 0", name="publication_metrics_comment_nonnegative"),
        CheckConstraint("share_count IS NULL OR share_count >= 0", name="publication_metrics_share_nonnegative"),
        CheckConstraint("save_count IS NULL OR save_count >= 0", name="publication_metrics_save_nonnegative"),
        CheckConstraint("impression_count IS NULL OR impression_count >= 0", name="publication_metrics_impression_nonnegative"),
        CheckConstraint("reach_count IS NULL OR reach_count >= 0", name="publication_metrics_reach_nonnegative"),
        CheckConstraint("follower_gain_count IS NULL OR follower_gain_count >= 0", name="publication_metrics_follower_gain_nonnegative"),
        CheckConstraint("total_watch_time_seconds IS NULL OR total_watch_time_seconds >= 0", name="publication_metrics_watch_time_nonnegative"),
        CheckConstraint("average_watch_time_seconds IS NULL OR average_watch_time_seconds >= 0", name="publication_metrics_average_watch_nonnegative"),
        CheckConstraint(
            "completion_rate_percent IS NULL OR (completion_rate_percent >= 0 AND completion_rate_percent <= 100)",
            name="publication_metrics_completion_rate_range",
        ),
        CheckConstraint("interval_seconds IS NULL OR interval_seconds >= 0", name="publication_metrics_interval_nonnegative"),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform_publication_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_publications.id"),
        nullable=False,
        index=True,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    collection_source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_schema_version: Mapped[str | None] = mapped_column(String(120))
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    payload_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    view_count: Mapped[int | None] = mapped_column(BigInteger)
    like_count: Mapped[int | None] = mapped_column(BigInteger)
    comment_count: Mapped[int | None] = mapped_column(BigInteger)
    share_count: Mapped[int | None] = mapped_column(BigInteger)
    save_count: Mapped[int | None] = mapped_column(BigInteger)
    impression_count: Mapped[int | None] = mapped_column(BigInteger)
    reach_count: Mapped[int | None] = mapped_column(BigInteger)
    follower_gain_count: Mapped[int | None] = mapped_column(BigInteger)
    total_watch_time_seconds: Mapped[float | None] = mapped_column(Float)
    average_watch_time_seconds: Mapped[float | None] = mapped_column(Float)
    completion_rate_percent: Mapped[float | None] = mapped_column(Float)

    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    data_quality: Mapped[str] = mapped_column(String(40), default="UNKNOWN", nullable=False, index=True)
    unavailable_metrics_json: Mapped[list | None] = mapped_column(JSONB)
    provider_summary_json: Mapped[dict | None] = mapped_column(JSONB)

    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    delta_view_count: Mapped[int | None] = mapped_column(BigInteger)
    delta_like_count: Mapped[int | None] = mapped_column(BigInteger)
    delta_comment_count: Mapped[int | None] = mapped_column(BigInteger)
    delta_share_count: Mapped[int | None] = mapped_column(BigInteger)
    delta_save_count: Mapped[int | None] = mapped_column(BigInteger)
    views_per_hour: Mapped[float | None] = mapped_column(Float)
    engagement_rate_percent: Mapped[float | None] = mapped_column(Float)
    engagement_delta_rate_percent: Mapped[float | None] = mapped_column(Float)
    counter_regression_detected: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    derivation_version: Mapped[str] = mapped_column(
        String(80),
        default="PUBLICATION_METRICS_V2",
        nullable=False,
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    platform_publication: Mapped["PlatformPublication"] = relationship(back_populates="metric_snapshots")


class PublicationMetricSchedule(BaseModel):
    """Durable adaptive cadence state for one confirmed platform publication."""

    __tablename__ = "publication_metric_schedules"
    __table_args__ = (
        UniqueConstraint(
            "platform_publication_id",
            name="uq_publication_metric_schedules_publication",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'BLOCKED')",
            name="publication_metric_schedule_status_valid",
        ),
        CheckConstraint("collection_count >= 0", name="publication_metric_schedule_collection_count_nonnegative"),
        CheckConstraint("consecutive_flat_count >= 0", name="publication_metric_schedule_flat_count_nonnegative"),
        CheckConstraint("max_age_hours > 0", name="publication_metric_schedule_max_age_positive"),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform_publication_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_publications.id"),
        nullable=False,
        index=True,
    )
    collector_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default="ACTIVE", nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(
        String(80),
        default="METRICS_CADENCE_V2",
        nullable=False,
    )
    next_collection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_collection_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    last_metric_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("publication_metric_snapshots.id"),
        index=True,
    )
    collection_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consecutive_flat_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_age_hours: Mapped[int] = mapped_column(Integer, default=168, nullable=False)
    collector_config_json: Mapped[dict | None] = mapped_column(JSONB)
    last_decision_json: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    @property
    def tracking_started_at(self) -> datetime | None:
        return self._metadata_datetime("tracking_started_at")

    @property
    def tracking_ends_at(self) -> datetime | None:
        return self._metadata_datetime("tracking_ends_at")

    def _metadata_datetime(self, key: str) -> datetime | None:
        raw = (self.metadata_json or {}).get(key)
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        return value if value.tzinfo is not None and value.utcoffset() is not None else None


class PublicationGrowthAssessment(BaseModel):
    """Versioned Growth Score derived only from publication metric evidence."""

    __tablename__ = "publication_growth_assessments"
    __table_args__ = (
        UniqueConstraint(
            "platform_publication_id",
            "score_version",
            "input_fingerprint_sha256",
            name="uq_publication_growth_assessments_input_version",
        ),
        CheckConstraint(
            "growth_score IS NULL OR (growth_score >= 0 AND growth_score <= 100)",
            name="publication_growth_score_range",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform_publication_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_publications.id"), nullable=False, index=True
    )
    score_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    input_fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    latest_metric_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("publication_metric_snapshots.id"), index=True
    )
    created_by_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    growth_score: Mapped[float | None] = mapped_column(Float)
    snapshot_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    observation_hours: Mapped[float | None] = mapped_column(Float)
    measurement_age_seconds: Mapped[int | None] = mapped_column(Integer)
    score_breakdown_json: Mapped[dict | None] = mapped_column(JSONB)
    evidence_json: Mapped[list | None] = mapped_column(JSONB)
    input_snapshot_ids_json: Mapped[list | None] = mapped_column(JSONB)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
