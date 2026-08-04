"""Persist the template snapshot on affiliate comment placements.

Revision ID: 0049_affiliate_template_snapshot
Revises: 0048_affiliate_comment_templates
"""

from alembic import op
import sqlalchemy as sa


revision = "0049_affiliate_template_snapshot"
down_revision = "0048_affiliate_comment_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliate_comment_placements", sa.Column("template_id", sa.Uuid(), nullable=True))
    op.add_column("affiliate_comment_placements", sa.Column("template_version", sa.Integer(), nullable=True))
    op.add_column("affiliate_comment_placements", sa.Column("attach_product_image", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_foreign_key(
        "fk_affiliate_comment_placements_template_id",
        "affiliate_comment_placements",
        "affiliate_comment_templates",
        ["template_id"],
        ["id"],
    )
    op.create_index("ix_affiliate_comment_placements_template_id", "affiliate_comment_placements", ["template_id"])


def downgrade() -> None:
    op.drop_index("ix_affiliate_comment_placements_template_id", table_name="affiliate_comment_placements")
    op.drop_constraint("fk_affiliate_comment_placements_template_id", "affiliate_comment_placements", type_="foreignkey")
    op.drop_column("affiliate_comment_placements", "attach_product_image")
    op.drop_column("affiliate_comment_placements", "template_version")
    op.drop_column("affiliate_comment_placements", "template_id")
