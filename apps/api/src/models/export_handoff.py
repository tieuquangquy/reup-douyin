from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel
from src.enums import ExportPackageStatus, PublishHandoffStatus, PublishTargetPlatform

if TYPE_CHECKING:
    from src.models.reup_queue import ReupQueueItem


class ExportPackage(BaseModel):
    __tablename__ = "export_packages"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    status: Mapped[ExportPackageStatus] = mapped_column(
        Enum(ExportPackageStatus, name="export_package_status"),
        default=ExportPackageStatus.DRAFT,
        nullable=False,
        index=True,
    )
    label: Mapped[str | None] = mapped_column(String(180), index=True)
    operator_note: Mapped[str | None] = mapped_column(Text)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manifest_json: Mapped[dict | None] = mapped_column(JSONB)
    diagnostics_json: Mapped[dict | None] = mapped_column(JSONB)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    items: Mapped[list["ExportPackageItem"]] = relationship(
        "ExportPackageItem",
        back_populates="export_package",
        cascade="all, delete-orphan",
    )
    publish_handoffs: Mapped[list["PublishHandoff"]] = relationship("PublishHandoff", back_populates="export_package")


class ExportPackageItem(BaseModel):
    __tablename__ = "export_package_items"
    __table_args__ = (
        UniqueConstraint(
            "export_package_id",
            "reup_queue_item_id",
            name="uq_export_package_items_package_queue_item",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    export_package_id: Mapped[UUID] = mapped_column(ForeignKey("export_packages.id"), index=True)
    reup_queue_item_id: Mapped[UUID] = mapped_column(ForeignKey("reup_queue_items.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    video_candidate_id: Mapped[UUID] = mapped_column(ForeignKey("video_candidates.id"), index=True)
    render_output_id: Mapped[UUID | None] = mapped_column(ForeignKey("render_outputs.id"), index=True)
    publish_draft_id: Mapped[UUID | None] = mapped_column(ForeignKey("publish_drafts.id"), index=True)
    item_status: Mapped[str] = mapped_column(String(80), default="INCLUDED", nullable=False, index=True)
    manifest_json: Mapped[dict | None] = mapped_column(JSONB)
    diagnostics_json: Mapped[dict | None] = mapped_column(JSONB)

    export_package: Mapped[ExportPackage] = relationship("ExportPackage", back_populates="items")
    reup_queue_item: Mapped["ReupQueueItem"] = relationship("ReupQueueItem")


class PublishHandoff(BaseModel):
    __tablename__ = "publish_handoffs"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    export_package_id: Mapped[UUID] = mapped_column(ForeignKey("export_packages.id"), index=True)
    target_platform: Mapped[PublishTargetPlatform] = mapped_column(
        Enum(PublishTargetPlatform, name="publish_target_platform"),
        nullable=False,
        index=True,
    )
    status: Mapped[PublishHandoffStatus] = mapped_column(
        Enum(PublishHandoffStatus, name="publish_handoff_status"),
        default=PublishHandoffStatus.DRAFT,
        nullable=False,
        index=True,
    )
    operator_note: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[dict | None] = mapped_column(JSONB)
    diagnostics_json: Mapped[dict | None] = mapped_column(JSONB)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    export_package: Mapped[ExportPackage] = relationship("ExportPackage", back_populates="publish_handoffs")
