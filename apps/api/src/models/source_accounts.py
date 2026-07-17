from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import BaseModel
from src.enums import DouyinAccountConnectionStatus, DouyinAccountHealthStatus, DouyinBrowserConnectSessionStatus, DouyinAccountWarningLevel


class DouyinAccountConnection(BaseModel):
    __tablename__ = "douyin_account_connections"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "display_name",
            name="uq_douyin_account_connections_workspace_display",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    douyin_user_id: Mapped[str | None] = mapped_column(String(180), index=True)
    status: Mapped[DouyinAccountConnectionStatus] = mapped_column(
        Enum(DouyinAccountConnectionStatus, name="douyin_account_connection_status"),
        default=DouyinAccountConnectionStatus.INVALID,
        nullable=False,
        index=True,
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    session_secret_blob: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    headers_json: Mapped[dict | None] = mapped_column(JSONB)
    proxy_url: Mapped[str | None] = mapped_column(Text)
    health_status: Mapped[DouyinAccountHealthStatus] = mapped_column(
        Enum(DouyinAccountHealthStatus, name="douyin_account_health_status"),
        default=DouyinAccountHealthStatus.UNKNOWN,
        nullable=False,
        index=True,
    )
    warning_level: Mapped[DouyinAccountWarningLevel] = mapped_column(
        Enum(DouyinAccountWarningLevel, name="douyin_account_warning_level"),
        default=DouyinAccountWarningLevel.INFO,
        nullable=False,
        index=True,
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_validation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_validation_status: Mapped[str | None] = mapped_column(String(80))
    validation_source: Mapped[str | None] = mapped_column(String(80))
    next_validation_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(120))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    warning_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)


class DouyinBrowserConnectSession(BaseModel):
    __tablename__ = "douyin_browser_connect_sessions"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    status: Mapped[DouyinBrowserConnectSessionStatus] = mapped_column(
        Enum(DouyinBrowserConnectSessionStatus, name="douyin_browser_connect_session_status"),
        default=DouyinBrowserConnectSessionStatus.PENDING,
        nullable=False,
        index=True,
    )
    mode: Mapped[str] = mapped_column(String(80), default="browser_assisted", nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(180))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text)
    proxy_url: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    derived_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("douyin_account_connections.id"), index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
