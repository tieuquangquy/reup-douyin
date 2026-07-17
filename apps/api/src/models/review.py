from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel
from src.enums import (
    CandidateStatus,
    OperatorRiskDecisionType,
    ReviewDecisionStatus,
    RiskFlagStatus,
    RiskFlagType,
    RiskSeverity,
    RiskTargetType,
)


class VideoCandidate(BaseModel):
    __tablename__ = "video_candidates"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_videos.id"),
        unique=True,
        index=True,
    )
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, name="candidate_status"),
        default=CandidateStatus.NEW,
        nullable=False,
        index=True,
    )
    score: Mapped[float | None] = mapped_column(Float)
    score_version: Mapped[str | None] = mapped_column(String(80), index=True)
    score_label: Mapped[str | None] = mapped_column(String(40), index=True)
    score_breakdown_json: Mapped[dict | None] = mapped_column(JSONB)
    score_reason: Mapped[str | None] = mapped_column(Text)
    preset_name: Mapped[str | None] = mapped_column(String(120), index=True)
    filter_config_json: Mapped[dict | None] = mapped_column(JSONB)
    inclusion_reasons_json: Mapped[list | None] = mapped_column(JSONB)
    exclusion_reasons_json: Mapped[list | None] = mapped_column(JSONB)
    warnings_json: Mapped[list | None] = mapped_column(JSONB)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    priority: Mapped[int] = mapped_column(default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    source_video: Mapped["SourceVideo"] = relationship(back_populates="candidate")
    review_decisions: Mapped[list[VideoReviewDecision]] = relationship(back_populates="candidate")


class VideoReviewDecision(BaseModel):
    __tablename__ = "video_review_decisions"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    video_candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("video_candidates.id"),
        index=True,
    )
    status: Mapped[ReviewDecisionStatus] = mapped_column(
        Enum(ReviewDecisionStatus, name="review_decision_status"),
        default=ReviewDecisionStatus.PENDING,
        nullable=False,
        index=True,
    )
    reviewer_label: Mapped[str | None] = mapped_column(String(120))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    checkpoint: Mapped[str | None] = mapped_column(String(120))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    candidate: Mapped[VideoCandidate] = relationship(back_populates="review_decisions")


class RiskFlag(BaseModel):
    __tablename__ = "risk_flags"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    target_type: Mapped[RiskTargetType] = mapped_column(
        Enum(RiskTargetType, name="risk_target_type"),
        default=RiskTargetType.SOURCE_VIDEO,
        nullable=False,
        index=True,
    )
    target_id: Mapped[UUID | None] = mapped_column(index=True)
    scan_run_id: Mapped[UUID | None] = mapped_column(index=True)
    flag_type: Mapped[RiskFlagType] = mapped_column(
        Enum(RiskFlagType, name="risk_flag_type"),
        nullable=False,
        index=True,
    )
    severity: Mapped[RiskSeverity] = mapped_column(
        Enum(RiskSeverity, name="risk_severity"),
        nullable=False,
        index=True,
    )
    status: Mapped[RiskFlagStatus] = mapped_column(
        Enum(RiskFlagStatus, name="risk_flag_status"),
        default=RiskFlagStatus.OPEN,
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    evidence_summary: Mapped[str | None] = mapped_column(Text)
    scan_source: Mapped[str | None] = mapped_column(String(120), index=True)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    evidence_json: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    source_video: Mapped["SourceVideo"] = relationship(back_populates="risk_flags")


class OperatorRiskDecision(BaseModel):
    __tablename__ = "operator_risk_decisions"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    target_type: Mapped[RiskTargetType] = mapped_column(
        Enum(RiskTargetType, name="risk_target_type"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[UUID] = mapped_column(index=True)
    decision_type: Mapped[OperatorRiskDecisionType] = mapped_column(
        Enum(OperatorRiskDecisionType, name="operator_risk_decision_type"),
        nullable=False,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(String(120))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    gate_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
