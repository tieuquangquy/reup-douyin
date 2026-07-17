"""source ingest crawl session fields

Revision ID: 0003_ingest
Revises: 0002_jobs
Create Date: 2026-04-17 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_ingest"
down_revision: str | None = "0002_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crawl_sessions",
        sa.Column(
            "source_platform",
            postgresql.ENUM("DOUYIN", name="source_platform_enum", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("crawl_sessions", sa.Column("submitted_profile_url", sa.Text(), nullable=True))
    op.add_column("crawl_sessions", sa.Column("normalized_profile_identifier", sa.String(length=180), nullable=True))
    op.add_column("crawl_sessions", sa.Column("videos_created_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("crawl_sessions", sa.Column("videos_updated_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("crawl_sessions", sa.Column("snapshots_created_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("crawl_sessions", sa.Column("error_code", sa.String(length=120), nullable=True))
    op.add_column("crawl_sessions", sa.Column("raw_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("crawl_sessions", sa.Column("result_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.alter_column("crawl_sessions", "source_profile_id", existing_type=sa.Uuid(), nullable=True)
    op.create_index(op.f("ix_crawl_sessions_source_platform"), "crawl_sessions", ["source_platform"])
    op.create_index(
        op.f("ix_crawl_sessions_normalized_profile_identifier"),
        "crawl_sessions",
        ["normalized_profile_identifier"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_crawl_sessions_normalized_profile_identifier"), table_name="crawl_sessions")
    op.drop_index(op.f("ix_crawl_sessions_source_platform"), table_name="crawl_sessions")
    op.alter_column("crawl_sessions", "source_profile_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("crawl_sessions", "result_summary_json")
    op.drop_column("crawl_sessions", "raw_summary_json")
    op.drop_column("crawl_sessions", "error_code")
    op.drop_column("crawl_sessions", "snapshots_created_count")
    op.drop_column("crawl_sessions", "videos_updated_count")
    op.drop_column("crawl_sessions", "videos_created_count")
    op.drop_column("crawl_sessions", "normalized_profile_identifier")
    op.drop_column("crawl_sessions", "submitted_profile_url")
    op.drop_column("crawl_sessions", "source_platform")
