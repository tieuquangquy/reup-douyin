"""publish preparation foundation

Revision ID: 0009_publish_prep
Revises: 0008_render
Create Date: 2026-04-17 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009_publish_prep"
down_revision: str | None = "0008_render"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("publish_drafts", sa.Column("platform_account_ref", sa.String(length=180), nullable=True))
    op.add_column("publish_drafts", sa.Column("cta_text", sa.Text(), nullable=True))
    op.add_column("publish_drafts", sa.Column("language_code", sa.String(length=16), nullable=True))
    op.add_column("publish_drafts", sa.Column("caption_draft_json", postgresql.JSONB(), nullable=True))
    op.add_column("publish_drafts", sa.Column("cta_draft_json", postgresql.JSONB(), nullable=True))
    op.add_column("publish_drafts", sa.Column("schedule_json", postgresql.JSONB(), nullable=True))
    op.add_column("publish_drafts", sa.Column("planned_publish_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_drafts", sa.Column("timezone", sa.String(length=80), nullable=True))
    op.add_column("publish_drafts", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_drafts", sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_drafts", sa.Column("generation_source", sa.String(length=120), nullable=True))
    op.add_column("publish_drafts", sa.Column("metadata_json", postgresql.JSONB(), nullable=True))
    op.add_column("publish_drafts", sa.Column("platform_notes", sa.Text(), nullable=True))
    op.add_column("publish_drafts", sa.Column("scheduling_notes", sa.Text(), nullable=True))
    op.create_index(op.f("ix_publish_drafts_platform_account_ref"), "publish_drafts", ["platform_account_ref"])
    op.create_index(op.f("ix_publish_drafts_planned_publish_at"), "publish_drafts", ["planned_publish_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_publish_drafts_planned_publish_at"), table_name="publish_drafts")
    op.drop_index(op.f("ix_publish_drafts_platform_account_ref"), table_name="publish_drafts")
    for column in [
        "scheduling_notes",
        "platform_notes",
        "metadata_json",
        "generation_source",
        "ready_at",
        "scheduled_at",
        "timezone",
        "planned_publish_at",
        "schedule_json",
        "cta_draft_json",
        "caption_draft_json",
        "language_code",
        "cta_text",
        "platform_account_ref",
    ]:
        op.drop_column("publish_drafts", column)
