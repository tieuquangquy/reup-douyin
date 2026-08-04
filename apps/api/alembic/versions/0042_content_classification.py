"""Add versioned topic taxonomy and durable content classification.

Revision ID: 0042_content_classification
Revises: 0041_publication_discovery
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0042_content_classification"
down_revision: str | None = "0041_publication_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'CLASSIFY_CONTENT'")

    op.create_table(
        "content_topic_categories",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("taxonomy_version", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("keywords_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["content_topic_categories.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "taxonomy_version",
            "code",
            name="uq_content_topic_categories_workspace_version_code",
        ),
    )
    op.create_index("ix_content_topic_categories_workspace_id", "content_topic_categories", ["workspace_id"])
    op.create_index("ix_content_topic_categories_taxonomy_version", "content_topic_categories", ["taxonomy_version"])
    op.create_index("ix_content_topic_categories_parent_id", "content_topic_categories", ["parent_id"])
    op.create_index("ix_content_topic_categories_is_active", "content_topic_categories", ["is_active"])

    op.create_table(
        "content_classifications",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("platform_publication_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=True),
        sa.Column("taxonomy_version", sa.String(length=80), nullable=False),
        sa.Column("classifier_version", sa.String(length=80), nullable=False),
        sa.Column("input_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision_status", sa.String(length=40), nullable=False, server_default="NEEDS_REVIEW"),
        sa.Column("primary_topic_id", sa.Uuid(), nullable=True),
        sa.Column("primary_topic_code", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("secondary_topics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_by_job_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=180), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["platform_publication_id"], ["platform_publications.id"]),
        sa.ForeignKeyConstraint(["primary_topic_id"], ["content_topic_categories.id"]),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform_publication_id",
            "taxonomy_version",
            "classifier_version",
            "input_fingerprint_sha256",
            name="uq_content_classifications_publication_input_version",
        ),
    )
    for column in (
        "workspace_id",
        "platform_publication_id",
        "source_video_id",
        "taxonomy_version",
        "classifier_version",
        "input_fingerprint_sha256",
        "decision_status",
        "primary_topic_id",
        "primary_topic_code",
        "confidence",
        "created_by_job_id",
        "is_current",
    ):
        op.create_index(f"ix_content_classifications_{column}", "content_classifications", [column])


def downgrade() -> None:
    op.drop_table("content_classifications")
    op.drop_table("content_topic_categories")
    # PostgreSQL enum values are intentionally retained. Removing one safely requires
    # rebuilding the type and can break durable historical job rows.
