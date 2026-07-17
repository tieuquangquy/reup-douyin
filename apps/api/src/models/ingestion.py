from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel
from src.enums import (
    CrawlSessionStatus,
    SourcePlatformEnum,
    SourceProfileStatus,
    SourceVideoStatus,
)


class SourceProfile(BaseModel):
    __tablename__ = "source_profiles"
    __table_args__ = (
        UniqueConstraint(
            "source_platform",
            "source_profile_external_id",
            name="uq_source_profiles_platform_external_id",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_platform: Mapped[SourcePlatformEnum] = mapped_column(
        Enum(SourcePlatformEnum, name="source_platform_enum"),
        nullable=False,
    )
    source_profile_external_id: Mapped[str] = mapped_column(String(180), nullable=False)
    profile_url: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(240))
    handle: Mapped[str | None] = mapped_column(String(180))
    status: Mapped[SourceProfileStatus] = mapped_column(
        Enum(SourceProfileStatus, name="source_profile_status"),
        default=SourceProfileStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    raw_payload_json: Mapped[dict | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)

    workspace: Mapped["Workspace"] = relationship(back_populates="source_profiles")
    crawl_sessions: Mapped[list[CrawlSession]] = relationship(back_populates="source_profile")
    source_videos: Mapped[list[SourceVideo]] = relationship(back_populates="source_profile")


class CrawlSession(BaseModel):
    __tablename__ = "crawl_sessions"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_platform: Mapped[SourcePlatformEnum | None] = mapped_column(
        Enum(SourcePlatformEnum, name="source_platform_enum"),
        index=True,
    )
    source_profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_profiles.id"),
        index=True,
    )
    submitted_profile_url: Mapped[str | None] = mapped_column(Text)
    normalized_profile_identifier: Mapped[str | None] = mapped_column(String(180), index=True)
    status: Mapped[CrawlSessionStatus] = mapped_column(
        Enum(CrawlSessionStatus, name="crawl_session_status"),
        default=CrawlSessionStatus.QUEUED,
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    videos_discovered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    videos_created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    videos_updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    snapshots_created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    result_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    raw_payload_json: Mapped[dict | None] = mapped_column(JSONB)

    source_profile: Mapped[SourceProfile | None] = relationship(back_populates="crawl_sessions")
    metric_snapshots: Mapped[list[VideoMetricSnapshot]] = relationship(back_populates="crawl_session")


class SourceVideo(BaseModel):
    __tablename__ = "source_videos"
    __table_args__ = (
        UniqueConstraint(
            "source_platform",
            "source_video_external_id",
            name="uq_source_videos_platform_external_id",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_profiles.id"),
        index=True,
    )
    first_crawl_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("crawl_sessions.id"))
    source_platform: Mapped[SourcePlatformEnum] = mapped_column(
        Enum(SourcePlatformEnum, name="source_platform_enum"),
        nullable=False,
    )
    source_video_external_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    status: Mapped[SourceVideoStatus] = mapped_column(
        Enum(SourceVideoStatus, name="source_video_status"),
        default=SourceVideoStatus.DISCOVERED,
        nullable=False,
        index=True,
    )
    score: Mapped[float | None] = mapped_column(Float)
    language_code: Mapped[str | None] = mapped_column(String(16))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    raw_payload_json: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)

    source_profile: Mapped[SourceProfile] = relationship(back_populates="source_videos")
    metric_snapshots: Mapped[list[VideoMetricSnapshot]] = relationship(back_populates="source_video")
    candidate: Mapped["VideoCandidate | None"] = relationship(
        back_populates="source_video",
        uselist=False,
    )
    media_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="source_video")
    risk_flags: Mapped[list["RiskFlag"]] = relationship(back_populates="source_video")
    transcript_segments: Mapped[list["TranscriptSegment"]] = relationship(back_populates="source_video")
    translation_segments: Mapped[list["TranslationSegment"]] = relationship(back_populates="source_video")
    subtitle_segments: Mapped[list["SubtitleSegment"]] = relationship(back_populates="source_video")
    ocr_text_objects: Mapped[list["OcrTextObject"]] = relationship(back_populates="source_video")
    render_outputs: Mapped[list["RenderOutput"]] = relationship(back_populates="source_video")
    publish_drafts: Mapped[list["PublishDraft"]] = relationship(back_populates="source_video")


class VideoMetricSnapshot(BaseModel):
    __tablename__ = "video_metric_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source_video_id",
            "crawl_session_id",
            name="uq_video_metric_snapshots_video_crawl",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    crawl_session_id: Mapped[UUID] = mapped_column(ForeignKey("crawl_sessions.id"), index=True)
    view_count: Mapped[int | None] = mapped_column(Integer)
    like_count: Mapped[int | None] = mapped_column(Integer)
    comment_count: Mapped[int | None] = mapped_column(Integer)
    share_count: Mapped[int | None] = mapped_column(Integer)
    favorite_count: Mapped[int | None] = mapped_column(Integer)
    raw_payload_json: Mapped[dict | None] = mapped_column(JSONB)

    source_video: Mapped[SourceVideo] = relationship(back_populates="metric_snapshots")
    crawl_session: Mapped[CrawlSession] = relationship(back_populates="metric_snapshots")
