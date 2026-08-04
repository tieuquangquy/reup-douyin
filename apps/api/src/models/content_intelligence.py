from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel


class TopicCategory(BaseModel):
    """Versioned, workspace-scoped taxonomy node used by content classification."""

    __tablename__ = "content_topic_categories"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "taxonomy_version",
            "code",
            name="uq_content_topic_categories_workspace_version_code",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("content_topic_categories.id"),
        index=True,
    )
    keywords_json: Mapped[list | None] = mapped_column(JSONB)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    parent: Mapped[TopicCategory | None] = relationship(
        remote_side="TopicCategory.id",
        back_populates="children",
    )
    children: Mapped[list[TopicCategory]] = relationship(back_populates="parent")


class ContentClassification(BaseModel):
    """One deterministic classification result for one publication/evidence version."""

    __tablename__ = "content_classifications"
    __table_args__ = (
        UniqueConstraint(
            "platform_publication_id",
            "taxonomy_version",
            "classifier_version",
            "input_fingerprint_sha256",
            name="uq_content_classifications_publication_input_version",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform_publication_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_publications.id"),
        index=True,
    )
    source_video_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_videos.id"), index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    classifier_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    input_fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    decision_status: Mapped[str] = mapped_column(
        String(40),
        default="NEEDS_REVIEW",
        nullable=False,
        index=True,
    )
    primary_topic_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("content_topic_categories.id"),
        index=True,
    )
    primary_topic_code: Mapped[str | None] = mapped_column(String(100), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    secondary_topics_json: Mapped[list | None] = mapped_column(JSONB)
    evidence_json: Mapped[list | None] = mapped_column(JSONB)
    rationale: Mapped[str | None] = mapped_column(Text)
    created_by_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(180))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    override_reason: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    platform_publication: Mapped["PlatformPublication"] = relationship(
        back_populates="content_classifications",
    )
    primary_topic: Mapped[TopicCategory | None] = relationship(foreign_keys=[primary_topic_id])
