"""reup queue start auto pipeline action

Revision ID: 0032_reup_queue_auto_pipeline
Revises: 0031_operator_profile_fields
Create Date: 2026-07-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0032_reup_queue_auto_pipeline"
down_revision: str | None = "0031_operator_profile_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE reup_queue_action ADD VALUE IF NOT EXISTS 'START_AUTO_PIPELINE'")


def downgrade() -> None:
    # PostgreSQL cannot drop enum values safely; leave START_AUTO_PIPELINE in place.
    pass
