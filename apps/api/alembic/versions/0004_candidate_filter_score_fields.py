"""candidate filter and score fields

Revision ID: 0004_candidates
Revises: 0003_ingest
Create Date: 2026-04-17 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_candidates"
down_revision: str | None = "0003_ingest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("video_candidates", sa.Column("score_version", sa.String(length=80), nullable=True))
    op.add_column("video_candidates", sa.Column("score_label", sa.String(length=40), nullable=True))
    op.add_column("video_candidates", sa.Column("score_breakdown_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("video_candidates", sa.Column("preset_name", sa.String(length=120), nullable=True))
    op.add_column("video_candidates", sa.Column("filter_config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("video_candidates", sa.Column("inclusion_reasons_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("video_candidates", sa.Column("exclusion_reasons_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("video_candidates", sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("video_candidates", sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_video_candidates_score_version"), "video_candidates", ["score_version"])
    op.create_index(op.f("ix_video_candidates_score_label"), "video_candidates", ["score_label"])
    op.create_index(op.f("ix_video_candidates_preset_name"), "video_candidates", ["preset_name"])
    op.create_index(op.f("ix_video_candidates_evaluated_at"), "video_candidates", ["evaluated_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_video_candidates_evaluated_at"), table_name="video_candidates")
    op.drop_index(op.f("ix_video_candidates_preset_name"), table_name="video_candidates")
    op.drop_index(op.f("ix_video_candidates_score_label"), table_name="video_candidates")
    op.drop_index(op.f("ix_video_candidates_score_version"), table_name="video_candidates")
    op.drop_column("video_candidates", "evaluated_at")
    op.drop_column("video_candidates", "warnings_json")
    op.drop_column("video_candidates", "exclusion_reasons_json")
    op.drop_column("video_candidates", "inclusion_reasons_json")
    op.drop_column("video_candidates", "filter_config_json")
    op.drop_column("video_candidates", "preset_name")
    op.drop_column("video_candidates", "score_breakdown_json")
    op.drop_column("video_candidates", "score_label")
    op.drop_column("video_candidates", "score_version")
