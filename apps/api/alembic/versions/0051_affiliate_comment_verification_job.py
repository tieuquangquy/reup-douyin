"""Add durable affiliate comment verification jobs."""

from alembic import op


revision = "0051_aff_comment_verification"
down_revision = "0050_seed_affiliate_template"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'VERIFY_AFFILIATE_COMMENT'")


def downgrade() -> None:
    # PostgreSQL enums cannot safely remove a value while rows may reference it.
    pass
