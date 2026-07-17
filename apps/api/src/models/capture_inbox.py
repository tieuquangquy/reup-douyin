from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel
from src.enums import CaptureSessionStatus, CapturedItemStatus, IntakeEvaluationStatus, SourcePlatformEnum


class CaptureSession(BaseModel):
    __tablename__ = "capture_sessions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "capture_id", name="uq_capture_sessions_workspace_capture_id"),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    capture_id: Mapped[str | None] = mapped_column(String(120), index=True)
    source_platform: Mapped[SourcePlatformEnum] = mapped_column(Enum(SourcePlatformEnum, name="source_platform_enum"), nullable=False, index=True)
    capture_source: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[CaptureSessionStatus] = mapped_column(
        Enum(CaptureSessionStatus, name="capture_session_status"),
        default=CaptureSessionStatus.RECEIVED,
        nullable=False,
        index=True,
    )
    detected_page_type: Mapped[str | None] = mapped_column(String(80), index=True)
    page_url: Mapped[str | None] = mapped_column(Text)
    page_title: Mapped[str | None] = mapped_column(Text)
    submitted_profile_url: Mapped[str | None] = mapped_column(Text)
    normalized_profile_identifier: Mapped[str | None] = mapped_column(String(180), index=True)
    visible_item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    captured_item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    normalized_item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ready_item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    promoted_item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidate_created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    diagnostics_json: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    raw_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    result_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list[CapturedItem]] = relationship(back_populates="capture_session", cascade="all, delete-orphan")


class CapturedItem(BaseModel):
    __tablename__ = "captured_items"
    __table_args__ = (
        UniqueConstraint("capture_session_id", "dedupe_key", name="uq_captured_items_session_dedupe_key"),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    capture_session_id: Mapped[UUID] = mapped_column(ForeignKey("capture_sessions.id"), index=True)
    source_platform: Mapped[SourcePlatformEnum] = mapped_column(Enum(SourcePlatformEnum, name="source_platform_enum"), nullable=False, index=True)
    status: Mapped[CapturedItemStatus] = mapped_column(
        Enum(CapturedItemStatus, name="captured_item_status"),
        default=CapturedItemStatus.RAW,
        nullable=False,
        index=True,
    )
    raw_item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_profile_external_id: Mapped[str | None] = mapped_column(String(180), index=True)
    profile_url: Mapped[str | None] = mapped_column(Text)
    source_video_external_id: Mapped[str | None] = mapped_column(String(180), index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    share_url: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    preview_url: Mapped[str | None] = mapped_column(Text)
    preview_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    media_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    readiness_reasons_json: Mapped[list | None] = mapped_column(JSONB)
    dedupe_key: Mapped[str | None] = mapped_column(String(300), index=True)
    duplicate_of_item_id: Mapped[UUID | None] = mapped_column(ForeignKey("captured_items.id"), index=True)
    existing_source_video_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_videos.id"), index=True)
    promoted_source_video_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_videos.id"), index=True)
    promoted_video_candidate_id: Mapped[UUID | None] = mapped_column(ForeignKey("video_candidates.id"), index=True)
    promoted_crawl_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("crawl_sessions.id"), index=True)
    enrichment_json: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    intake_evaluation_status: Mapped[IntakeEvaluationStatus] = mapped_column(
        Enum(IntakeEvaluationStatus, name="intake_evaluation_status"),
        default=IntakeEvaluationStatus.MISSING_REQUIREMENTS,
        nullable=False,
        index=True,
    )
    matches_intake: Mapped[bool | None] = mapped_column(Boolean)
    intake_failed_rules_json: Mapped[list | None] = mapped_column(JSONB)
    intake_missing_requirements_json: Mapped[list | None] = mapped_column(JSONB)
    intake_filter_version: Mapped[str | None] = mapped_column(String(120))
    intake_preset_name: Mapped[str | None] = mapped_column(String(120))
    last_intake_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    intake_evaluation_error: Mapped[str | None] = mapped_column(Text)
    excluded_reason: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)

    capture_session: Mapped[CaptureSession] = relationship(back_populates="items")
