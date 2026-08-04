"""Persist the image snapshot used by an affiliate comment placement.

Revision ID: 0046_affiliate_comment_image
Revises: 0045_affiliate_comment_placement
"""

from alembic import op
import sqlalchemy as sa


revision = "0046_affiliate_comment_image"
down_revision = "0045_affiliate_comment_placement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "affiliate_comment_placements",
        sa.Column("attachment_image_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("affiliate_comment_placements", "attachment_image_url")
