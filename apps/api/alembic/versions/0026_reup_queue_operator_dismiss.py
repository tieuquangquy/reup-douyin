"""reup queue operator dismiss

Revision ID: 0026_reup_queue_operator_dismiss
Revises: 0025_capture_inbox_intake_cols
Create Date: 2026-07-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0026_reup_queue_operator_dismiss"
down_revision: str | None = "0025_capture_inbox_intake_cols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE reup_queue_action ADD VALUE IF NOT EXISTS 'DISMISS'")
    op.add_column("reup_queue_items", sa.Column("operator_dismissed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_reup_queue_items_operator_dismissed_at"), "reup_queue_items", ["operator_dismissed_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_reup_queue_items_operator_dismissed_at"), table_name="reup_queue_items")
    op.drop_column("reup_queue_items", "operator_dismissed_at")
