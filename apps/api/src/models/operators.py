"""Durable local operator identity (Phase A auth)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel


class Operator(BaseModel):
    """Local operator account bound to one workspace."""

    __tablename__ = "operators"
    __table_args__ = (UniqueConstraint("email", name="uq_operators_email"),)

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    roles_csv: Mapped[str] = mapped_column(String(255), default="operator", nullable=False)

    workspace = relationship("Workspace")

    @property
    def roles(self) -> list[str]:
        return [part.strip() for part in self.roles_csv.split(",") if part.strip()]
