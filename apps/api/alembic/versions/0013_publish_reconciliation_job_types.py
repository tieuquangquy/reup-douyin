"""add publish reconciliation job types

Revision ID: 0013_pub_jobs
Revises: 0012_pub_reconcile
Create Date: 2026-04-21
"""

from alembic import op


revision = "0013_pub_jobs"
down_revision = "0012_pub_reconcile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'REFRESH_PUBLISH_STATUS'")
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'RECONCILE_PUBLISH_ATTEMPT'")


def downgrade() -> None:
    # PostgreSQL enum values are intentionally not removed in downgrade.
    pass
