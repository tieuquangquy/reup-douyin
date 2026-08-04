"""Add workspace-owned uploaded images for Affiliate Product Catalog.

Revision ID: 0047_affiliate_image_assets
Revises: 0046_affiliate_comment_image
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0047_affiliate_image_assets"
down_revision = "0046_affiliate_comment_image"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "affiliate_product_image_assets",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("storage_provider", sa.String(length=40), nullable=False, server_default="local"),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=240), nullable=True),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.String(length=180), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "checksum_sha256",
            name="uq_affiliate_product_image_assets_workspace_checksum",
        ),
    )
    for column in ("workspace_id", "checksum_sha256", "is_active"):
        op.create_index(f"ix_affiliate_product_image_assets_{column}", "affiliate_product_image_assets", [column])


def downgrade() -> None:
    op.drop_table("affiliate_product_image_assets")
