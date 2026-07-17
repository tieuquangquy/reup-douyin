from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel
from src.enums import ReupQueueAction, ReupQueueMediaPrepStatus, ReupQueueStatus

if TYPE_CHECKING:
    from src.models.ingestion import SourceVideo
    from src.models.jobs import Job
    from src.models.media import RenderOutput
    from src.models.publish import PublishDraft
    from src.models.review import VideoCandidate


class ReupQueueItem(BaseModel):
    __tablename__ = "reup_queue_items"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "video_candidate_id",
            name="uq_reup_queue_items_workspace_candidate",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    video_candidate_id: Mapped[UUID] = mapped_column(ForeignKey("video_candidates.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    status: Mapped[ReupQueueStatus] = mapped_column(
        Enum(ReupQueueStatus, name="reup_queue_status"),
        default=ReupQueueStatus.READY_FOR_PROCESSING,
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False, index=True)
    queued_reason: Mapped[str | None] = mapped_column(Text)
    operator_note: Mapped[str | None] = mapped_column(Text)
    last_error_code: Mapped[str | None] = mapped_column(String(120), index=True)
    last_error_message: Mapped[str | None] = mapped_column(Text)
    media_prep_status: Mapped[ReupQueueMediaPrepStatus] = mapped_column(
        Enum(ReupQueueMediaPrepStatus, name="reup_queue_media_prep_status"),
        default=ReupQueueMediaPrepStatus.NOT_STARTED,
        nullable=False,
        index=True,
    )
    media_prep_notes: Mapped[str | None] = mapped_column(Text)
    media_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_action: Mapped[ReupQueueAction | None] = mapped_column(
        Enum(ReupQueueAction, name="reup_queue_action"),
        index=True,
    )
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_action_note: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    operator_dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    render_output_id: Mapped[UUID | None] = mapped_column(ForeignKey("render_outputs.id"), index=True)
    publish_draft_id: Mapped[UUID | None] = mapped_column(ForeignKey("publish_drafts.id"), index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    video_candidate: Mapped["VideoCandidate"] = relationship("VideoCandidate")
    source_video: Mapped["SourceVideo"] = relationship("SourceVideo")
    job: Mapped["Job | None"] = relationship("Job")
    render_output: Mapped["RenderOutput | None"] = relationship("RenderOutput")
    publish_draft: Mapped["PublishDraft | None"] = relationship("PublishDraft")
