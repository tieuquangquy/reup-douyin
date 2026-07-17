"""douyin account connections

Revision ID: 0016_douyin_accounts
Revises: 0015_multi_account
Create Date: 2026-04-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0016_douyin_accounts"
down_revision: str | None = "0015_multi_account"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status_enum = postgresql.ENUM(
        "ACTIVE",
        "INVALID",
        "EXPIRED",
        "DISABLED",
        "BLOCKED",
        name="douyin_account_connection_status",
        create_type=False,
    )
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "douyin_account_connections",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=180), nullable=False),
        sa.Column("douyin_user_id", sa.String(length=180), nullable=True),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("session_secret_blob", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("headers_json", postgresql.JSONB(), nullable=True),
        sa.Column("proxy_url", sa.Text(), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validation_status", sa.String(length=80), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_douyin_account_connections_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_douyin_account_connections")),
        sa.UniqueConstraint("workspace_id", "display_name", name="uq_douyin_account_connections_workspace_display"),
    )
    for column in ["workspace_id", "douyin_user_id", "status", "is_default"]:
        op.create_index(op.f(f"ix_douyin_account_connections_{column}"), "douyin_account_connections", [column])
    op.alter_column("douyin_account_connections", "is_default", server_default=None)


def downgrade() -> None:
    for column in ["is_default", "status", "douyin_user_id", "workspace_id"]:
        op.drop_index(op.f(f"ix_douyin_account_connections_{column}"), table_name="douyin_account_connections")
    op.drop_table("douyin_account_connections")
    postgresql.ENUM(name="douyin_account_connection_status").drop(op.get_bind(), checkfirst=True)
