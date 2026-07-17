"""douyin browser connect sessions

Revision ID: 0017_douyin_browser_connect
Revises: 0016_douyin_accounts
Create Date: 2026-04-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0017_douyin_browser_connect"
down_revision: str | None = "0016_douyin_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status_enum = postgresql.ENUM(
        "PENDING",
        "LAUNCHING_BROWSER",
        "WAITING_FOR_LOGIN",
        "CAPTURING_SESSION",
        "VALIDATING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        name="douyin_browser_connect_session_status",
        create_type=False,
    )
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "douyin_browser_connect_sessions",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("mode", sa.String(length=80), nullable=False, server_default="browser_assisted"),
        sa.Column("display_name", sa.String(length=180), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("proxy_url", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("derived_account_id", sa.Uuid(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["derived_account_id"], ["douyin_account_connections.id"], name=op.f("fk_douyin_browser_connect_sessions_derived_account_id_douyin_account_connections")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_douyin_browser_connect_sessions_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_douyin_browser_connect_sessions")),
    )
    for column in ["workspace_id", "status", "derived_account_id"]:
        op.create_index(op.f(f"ix_douyin_browser_connect_sessions_{column}"), "douyin_browser_connect_sessions", [column])
    op.alter_column("douyin_browser_connect_sessions", "mode", server_default=None)
    op.alter_column("douyin_browser_connect_sessions", "is_default", server_default=None)


def downgrade() -> None:
    for column in ["derived_account_id", "status", "workspace_id"]:
        op.drop_index(op.f(f"ix_douyin_browser_connect_sessions_{column}"), table_name="douyin_browser_connect_sessions")
    op.drop_table("douyin_browser_connect_sessions")
    postgresql.ENUM(name="douyin_browser_connect_session_status").drop(op.get_bind(), checkfirst=True)
