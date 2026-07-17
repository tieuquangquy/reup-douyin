"""intake saved presets

Revision ID: 0020_intake_saved_presets
Revises: 0019_douyin_health_jobs
Create Date: 2026-04-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0020_intake_saved_presets"
down_revision: str | None = "0019_douyin_health_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intake_saved_presets",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("profile_url", sa.Text(), nullable=False),
        sa.Column("preset_name", sa.String(length=120), nullable=True),
        sa.Column("filter_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("douyin_account_connection_id", sa.Uuid(), nullable=True),
        sa.Column("force_live_refresh", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["douyin_account_connection_id"], ["douyin_account_connections.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intake_saved_presets")),
        sa.UniqueConstraint("workspace_id", "name", name="uq_intake_saved_presets_workspace_name"),
    )
    op.create_index(op.f("ix_intake_saved_presets_workspace_id"), "intake_saved_presets", ["workspace_id"])
    op.create_index(
        op.f("ix_intake_saved_presets_douyin_account_connection_id"),
        "intake_saved_presets",
        ["douyin_account_connection_id"],
    )
    op.alter_column("intake_saved_presets", "force_live_refresh", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_intake_saved_presets_douyin_account_connection_id"), table_name="intake_saved_presets")
    op.drop_index(op.f("ix_intake_saved_presets_workspace_id"), table_name="intake_saved_presets")
    op.drop_table("intake_saved_presets")
