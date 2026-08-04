"""Add durable publication metrics collector job type.

Revision ID: 0035_metric_collector_job
Revises: 0034_publication_metrics
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0035_metric_collector_job"
down_revision: str | None = "0034_publication_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'COLLECT_PUBLICATION_METRICS'")


def downgrade() -> None:
    # PostgreSQL cannot safely remove one enum value while rows may still reference it.
    pass
