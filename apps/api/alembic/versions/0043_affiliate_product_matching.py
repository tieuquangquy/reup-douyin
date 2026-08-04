"""Add affiliate catalog and reviewed product matching.

Revision ID: 0043_affiliate_product_matching
Revises: 0042_content_classification
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0043_affiliate_product_matching"
down_revision: str | None = "0042_content_classification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'MATCH_AFFILIATE_PRODUCTS'")

    op.create_table(
        "affiliate_products",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_version", sa.String(length=80), nullable=False, server_default="AFFILIATE_CATALOG_V1"),
        sa.Column("platform", sa.String(length=80), nullable=False),
        sa.Column("external_product_id", sa.String(length=240), nullable=True),
        sa.Column("merchant_name", sa.String(length=240), nullable=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("product_url", sa.Text(), nullable=True),
        sa.Column("affiliate_url", sa.Text(), nullable=False),
        sa.Column("currency_code", sa.String(length=12), nullable=False, server_default="VND"),
        sa.Column("price_amount", sa.Float(), nullable=True),
        sa.Column("commission_rate_percent", sa.Float(), nullable=True),
        sa.Column("commission_amount", sa.Float(), nullable=True),
        sa.Column("availability_status", sa.String(length=40), nullable=False, server_default="UNKNOWN"),
        sa.Column("keywords_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("supported_platforms_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "fingerprint_sha256", name="uq_affiliate_products_workspace_fingerprint"),
    )
    for column in ("workspace_id", "catalog_version", "platform", "external_product_id", "merchant_name", "name", "availability_status", "fingerprint_sha256", "is_active"):
        op.create_index(f"ix_affiliate_products_{column}", "affiliate_products", [column])

    op.create_table(
        "affiliate_product_topic_mappings",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("affiliate_product_id", sa.Uuid(), nullable=False),
        sa.Column("topic_category_id", sa.Uuid(), nullable=False),
        sa.Column("relevance_weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="OPERATOR"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["affiliate_product_id"], ["affiliate_products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_category_id"], ["content_topic_categories.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("affiliate_product_id", "topic_category_id", name="uq_affiliate_product_topic_mapping"),
    )
    for column in ("workspace_id", "affiliate_product_id", "topic_category_id"):
        op.create_index(f"ix_affiliate_product_topic_mappings_{column}", "affiliate_product_topic_mappings", [column])

    op.create_table(
        "affiliate_product_matches",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("platform_publication_id", sa.Uuid(), nullable=False),
        sa.Column("content_classification_id", sa.Uuid(), nullable=False),
        sa.Column("matcher_version", sa.String(length=80), nullable=False),
        sa.Column("catalog_version", sa.String(length=80), nullable=False),
        sa.Column("catalog_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision_status", sa.String(length=40), nullable=False, server_default="NEEDS_REVIEW"),
        sa.Column("suggestions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("selected_product_id", sa.Uuid(), nullable=True),
        sa.Column("selected_fit_score", sa.Float(), nullable=True),
        sa.Column("created_by_job_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=180), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["platform_publication_id"], ["platform_publications.id"]),
        sa.ForeignKeyConstraint(["content_classification_id"], ["content_classifications.id"]),
        sa.ForeignKeyConstraint(["selected_product_id"], ["affiliate_products.id"]),
        sa.ForeignKeyConstraint(["created_by_job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_publication_id", "content_classification_id", "matcher_version", "catalog_fingerprint_sha256", name="uq_affiliate_product_matches_input_version"),
    )
    for column in ("workspace_id", "platform_publication_id", "content_classification_id", "matcher_version", "catalog_version", "catalog_fingerprint_sha256", "decision_status", "selected_product_id", "created_by_job_id", "is_current"):
        op.create_index(f"ix_affiliate_product_matches_{column}", "affiliate_product_matches", [column])


def downgrade() -> None:
    op.drop_table("affiliate_product_matches")
    op.drop_table("affiliate_product_topic_mappings")
    op.drop_table("affiliate_products")
