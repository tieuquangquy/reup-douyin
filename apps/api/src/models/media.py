from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel
from src.enums import MediaAssetStatus, MediaAssetType, RenderOutputStatus


class MediaAsset(BaseModel):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint(
            "source_video_id",
            "asset_type",
            "version",
            name="uq_media_assets_video_type_version",
        ),
        UniqueConstraint(
            "workspace_id",
            "storage_key",
            name="uq_media_assets_workspace_storage_key",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    asset_type: Mapped[MediaAssetType] = mapped_column(
        Enum(MediaAssetType, name="media_asset_type"),
        nullable=False,
        index=True,
    )
    status: Mapped[MediaAssetStatus] = mapped_column(
        Enum(MediaAssetStatus, name="media_asset_status"),
        default=MediaAssetStatus.PLANNED,
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(40), default="local", nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    logical_key: Mapped[str | None] = mapped_column(Text, index=True)
    relative_path: Mapped[str | None] = mapped_column(Text)
    manifest_group: Mapped[str | None] = mapped_column(String(120), index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)

    source_video: Mapped["SourceVideo"] = relationship(back_populates="media_assets")
    render_outputs: Mapped[list[RenderOutput]] = relationship(back_populates="media_asset")


class RenderOutput(BaseModel):
    __tablename__ = "render_outputs"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    media_asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("media_assets.id"), index=True)
    status: Mapped[RenderOutputStatus] = mapped_column(
        Enum(RenderOutputStatus, name="render_output_status"),
        default=RenderOutputStatus.PLANNED,
        nullable=False,
        index=True,
    )
    target_platform: Mapped[str | None] = mapped_column(String(80), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    render_type: Mapped[str | None] = mapped_column(String(80), index=True)
    output_format: Mapped[str | None] = mapped_column(String(40))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    video_codec: Mapped[str | None] = mapped_column(String(80))
    audio_codec: Mapped[str | None] = mapped_column(String(80))
    subtitle_burned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audio_strategy: Mapped[str | None] = mapped_column(String(120), index=True)
    render_version: Mapped[str | None] = mapped_column(String(80), index=True)
    created_by_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    warning_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    render_settings_json: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)

    source_video: Mapped["SourceVideo"] = relationship(back_populates="render_outputs")
    media_asset: Mapped[MediaAsset | None] = relationship(back_populates="render_outputs")
    publish_drafts: Mapped[list["PublishDraft"]] = relationship(back_populates="render_output")
