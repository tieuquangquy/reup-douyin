"""Persist versioned Growth Score assessments.

Revision ID: 0044_growth_score_v1
Revises: 0043_affiliate_product_matching
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0044_growth_score_v1"
down_revision = "0043_affiliate_product_matching"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'CALCULATE_GROWTH_SCORE'")
    op.create_table(
        "publication_growth_assessments",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("platform_publication_id", sa.Uuid(), nullable=False),
        sa.Column("score_version", sa.String(length=80), nullable=False),
        sa.Column("input_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("latest_metric_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_job_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("growth_score", sa.Float(), nullable=True),
        sa.Column("snapshot_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observation_hours", sa.Float(), nullable=True),
        sa.Column("measurement_age_seconds", sa.Integer(), nullable=True),
        sa.Column("score_breakdown_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("input_snapshot_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["platform_publication_id"], ["platform_publications.id"]),
        sa.ForeignKeyConstraint(["latest_metric_snapshot_id"], ["publication_metric_snapshots.id"]),
        sa.ForeignKeyConstraint(["created_by_job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform_publication_id",
            "score_version",
            "input_fingerprint_sha256",
            name="uq_publication_growth_assessments_input_version",
        ),
        sa.CheckConstraint(
            "growth_score IS NULL OR (growth_score >= 0 AND growth_score <= 100)",
            name="publication_growth_score_range",
        ),
    )
    for column in (
        "workspace_id",
        "platform_publication_id",
        "score_version",
        "input_fingerprint_sha256",
        "latest_metric_snapshot_id",
        "created_by_job_id",
        "status",
        "confidence",
        "is_current",
    ):
        op.create_index(f"ix_publication_growth_assessments_{column}", "publication_growth_assessments", [column])


def downgrade() -> None:
    op.drop_table("publication_growth_assessments")
