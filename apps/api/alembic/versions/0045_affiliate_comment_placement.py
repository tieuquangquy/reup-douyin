"""Add operator-approved Facebook affiliate comment placements.

Revision ID: 0045_affiliate_comment_placement
Revises: 0044_growth_score_v1
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0045_affiliate_comment_placement"
down_revision = "0044_growth_score_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'POST_AFFILIATE_COMMENT'")
    op.create_table(
        "affiliate_comment_placements",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("platform_publication_id", sa.Uuid(), nullable=False),
        sa.Column("platform_account_id", sa.Uuid(), nullable=False),
        sa.Column("affiliate_product_match_id", sa.Uuid(), nullable=False),
        sa.Column("selected_product_id", sa.Uuid(), nullable=False),
        sa.Column("growth_assessment_id", sa.Uuid(), nullable=False),
        sa.Column("post_job_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="DRAFT"),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("message_sha256", sa.String(length=64), nullable=False),
        sa.Column("comment_message", sa.Text(), nullable=False),
        sa.Column("cta_text", sa.Text(), nullable=False),
        sa.Column("disclosure_text", sa.String(length=500), nullable=False),
        sa.Column("affiliate_url", sa.Text(), nullable=False),
        sa.Column("external_reel_id", sa.String(length=240), nullable=False),
        sa.Column("external_comment_id", sa.String(length=240), nullable=True),
        sa.Column("external_comment_permalink", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=180), nullable=False),
        sa.Column("approved_by", sa.String(length=180), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("response_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("gate_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["platform_publication_id"], ["platform_publications.id"]),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"]),
        sa.ForeignKeyConstraint(["affiliate_product_match_id"], ["affiliate_product_matches.id"]),
        sa.ForeignKeyConstraint(["selected_product_id"], ["affiliate_products.id"]),
        sa.ForeignKeyConstraint(["growth_assessment_id"], ["publication_growth_assessments.id"]),
        sa.ForeignKeyConstraint(["post_job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_affiliate_comment_placements_workspace_idempotency"),
    )
    for column in (
        "workspace_id",
        "platform_publication_id",
        "platform_account_id",
        "affiliate_product_match_id",
        "selected_product_id",
        "growth_assessment_id",
        "post_job_id",
        "status",
        "idempotency_key",
        "message_sha256",
        "external_reel_id",
        "external_comment_id",
        "error_code",
        "is_current",
    ):
        op.create_index(f"ix_affiliate_comment_placements_{column}", "affiliate_comment_placements", [column])


def downgrade() -> None:
    op.drop_table("affiliate_comment_placements")
