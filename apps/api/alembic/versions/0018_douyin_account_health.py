"""douyin account health

Revision ID: 0018_douyin_account_health
Revises: 0017_douyin_browser_connect
Create Date: 2026-04-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0018_douyin_account_health"
down_revision: str | None = "0017_douyin_browser_connect"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    health_enum = postgresql.ENUM(
        "HEALTHY",
        "STALE",
        "EXPIRING_SOON",
        "INVALID",
        "EXPIRED",
        "BLOCKED",
        "DISABLED",
        "UNKNOWN",
        name="douyin_account_health_status",
        create_type=False,
    )
    warning_enum = postgresql.ENUM(
        "NONE",
        "INFO",
        "WARN",
        "BLOCK",
        name="douyin_account_warning_level",
        create_type=False,
    )
    health_enum.create(op.get_bind(), checkfirst=True)
    warning_enum.create(op.get_bind(), checkfirst=True)

    op.add_column("douyin_account_connections", sa.Column("health_status", health_enum, nullable=False, server_default="UNKNOWN"))
    op.add_column("douyin_account_connections", sa.Column("warning_level", warning_enum, nullable=False, server_default="INFO"))
    op.add_column("douyin_account_connections", sa.Column("last_successful_validation_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("douyin_account_connections", sa.Column("validation_source", sa.String(length=80), nullable=True))
    op.add_column("douyin_account_connections", sa.Column("next_validation_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("douyin_account_connections", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("douyin_account_connections", sa.Column("last_error_code", sa.String(length=120), nullable=True))
    op.add_column("douyin_account_connections", sa.Column("warning_summary_json", postgresql.JSONB(), nullable=True))
    for column in ["health_status", "warning_level", "last_successful_validation_at", "next_validation_due_at", "expires_at"]:
        op.create_index(op.f(f"ix_douyin_account_connections_{column}"), "douyin_account_connections", [column])
    op.alter_column("douyin_account_connections", "health_status", server_default=None)
    op.alter_column("douyin_account_connections", "warning_level", server_default=None)


def downgrade() -> None:
    for column in ["expires_at", "next_validation_due_at", "last_successful_validation_at", "warning_level", "health_status"]:
        op.drop_index(op.f(f"ix_douyin_account_connections_{column}"), table_name="douyin_account_connections")
    for column in [
        "warning_summary_json",
        "last_error_code",
        "expires_at",
        "next_validation_due_at",
        "validation_source",
        "last_successful_validation_at",
        "warning_level",
        "health_status",
    ]:
        op.drop_column("douyin_account_connections", column)
    postgresql.ENUM(name="douyin_account_warning_level").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="douyin_account_health_status").drop(op.get_bind(), checkfirst=True)
