from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel


class Workspace(BaseModel):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    settings_json: Mapped[dict | None] = mapped_column(JSONB)

    niche_tags: Mapped[list[NicheTag]] = relationship(back_populates="workspace")
    workflow_templates: Mapped[list[WorkflowTemplate]] = relationship(back_populates="workspace")
    source_profiles: Mapped[list["SourceProfile"]] = relationship(back_populates="workspace")


class NicheTag(BaseModel):
    __tablename__ = "niche_tags"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_niche_tags_workspace_name"),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    workspace: Mapped[Workspace] = relationship(back_populates="niche_tags")


class WorkflowTemplate(BaseModel):
    __tablename__ = "workflow_templates"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_workflow_templates_workspace_name"),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    definition_json: Mapped[dict | None] = mapped_column(JSONB)

    workspace: Mapped[Workspace] = relationship(back_populates="workflow_templates")
