from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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
