from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import BaseModel


class IntakeSavedPreset(BaseModel):
    __tablename__ = "intake_saved_presets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_intake_saved_presets_workspace_name"),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    profile_url: Mapped[str] = mapped_column(Text, nullable=False)
    preset_name: Mapped[str | None] = mapped_column(String(120))
    filter_config_json: Mapped[dict | None] = mapped_column(JSONB)
    douyin_account_connection_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("douyin_account_connections.id"),
        index=True,
    )
    force_live_refresh: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
