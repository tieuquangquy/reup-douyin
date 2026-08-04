"""Add versioned workspace affiliate comment templates.

Revision ID: 0048_affiliate_comment_templates
Revises: 0047_affiliate_image_assets
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0048_affiliate_comment_templates"
down_revision = "0047_affiliate_image_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "affiliate_comment_templates",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=False, server_default="FACEBOOK_REELS"),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("message_template", sa.Text(), nullable=False),
        sa.Column("default_cta", sa.Text(), nullable=False),
        sa.Column("default_disclosure", sa.String(length=500), nullable=False),
        sa.Column("attach_product_image", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "platform",
            "name",
            "version",
            name="uq_affiliate_comment_templates_workspace_platform_name_version",
        ),
    )
    for column in ("workspace_id", "platform", "is_active"):
        op.create_index(f"ix_affiliate_comment_templates_{column}", "affiliate_comment_templates", [column])


def downgrade() -> None:
    op.drop_table("affiliate_comment_templates")
