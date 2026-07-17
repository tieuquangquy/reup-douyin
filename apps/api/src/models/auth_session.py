"""Auth session tables: refresh tokens, memberships, invites (Phase B/C)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import BaseModel


class OperatorRefreshToken(BaseModel):
    """Opaque refresh token (store hash only)."""

    __tablename__ = "operator_refresh_tokens"

    operator_id: Mapped[UUID] = mapped_column(ForeignKey("operators.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_hash: Mapped[str | None] = mapped_column(String(128))
    user_agent: Mapped[str | None] = mapped_column(String(320))
    client: Mapped[str] = mapped_column(String(32), nullable=False, default="web")


class WorkspaceMembership(BaseModel):
    """Operator ↔ workspace role (SaaS-ready tenancy)."""

    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("operator_id", "workspace_id", name="uq_workspace_memberships_operator_workspace"),
    )

    operator_id: Mapped[UUID] = mapped_column(ForeignKey("operators.id"), index=True, nullable=False)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="operator")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class OperatorInvite(BaseModel):
    """Email invite into a workspace (accept with token)."""

    __tablename__ = "operator_invites"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="operator")
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    invited_by_operator_id: Mapped[UUID | None] = mapped_column(ForeignKey("operators.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
