"""douyin account health job types

Revision ID: 0019_douyin_health_jobs
Revises: 0018_douyin_account_health
Create Date: 2026-04-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_douyin_health_jobs"
down_revision: str | None = "0018_douyin_account_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'VALIDATE_DOUYIN_ACCOUNT'")
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'REVALIDATE_STALE_DOUYIN_ACCOUNTS'")


def downgrade() -> None:
    # PostgreSQL enum values are intentionally retained on downgrade.
    pass
