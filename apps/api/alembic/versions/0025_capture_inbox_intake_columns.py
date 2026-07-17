"""add capture inbox intake evaluation columns

Revision ID: 0025_capture_inbox_intake_cols
Revises: 0024_reup_export_handoff
Create Date: 2026-04-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0025_capture_inbox_intake_cols"
down_revision: str | None = "0024_reup_export_handoff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


intake_evaluation_status = postgresql.ENUM(
    "NOT_EVALUATED",
    "MATCHED",
    "FILTERED_OUT",
    "MISSING_REQUIREMENTS",
    "EVALUATION_ERROR",
    name="intake_evaluation_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    intake_evaluation_status.create(bind, checkfirst=True)

    op.add_column(
        "captured_items",
        sa.Column(
            "intake_evaluation_status",
            postgresql.ENUM(name="intake_evaluation_status", create_type=False),
            nullable=False,
            server_default="NOT_EVALUATED",
        ),
    )
    op.add_column("captured_items", sa.Column("matches_intake", sa.Boolean(), nullable=True))
    op.add_column(
        "captured_items",
        sa.Column("intake_failed_rules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "captured_items",
        sa.Column("intake_missing_requirements_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("captured_items", sa.Column("intake_filter_version", sa.String(length=120), nullable=True))
    op.add_column("captured_items", sa.Column("intake_preset_name", sa.String(length=120), nullable=True))
    op.add_column("captured_items", sa.Column("last_intake_evaluated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("captured_items", sa.Column("intake_evaluation_error", sa.Text(), nullable=True))

    op.create_index(
        op.f("ix_captured_items_intake_evaluation_status"),
        "captured_items",
        ["intake_evaluation_status"],
    )
    op.create_index(
        op.f("ix_captured_items_last_intake_evaluated_at"),
        "captured_items",
        ["last_intake_evaluated_at"],
    )

    op.alter_column("captured_items", "intake_evaluation_status", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_captured_items_last_intake_evaluated_at"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_intake_evaluation_status"), table_name="captured_items")

    op.drop_column("captured_items", "intake_evaluation_error")
    op.drop_column("captured_items", "last_intake_evaluated_at")
    op.drop_column("captured_items", "intake_preset_name")
    op.drop_column("captured_items", "intake_filter_version")
    op.drop_column("captured_items", "intake_missing_requirements_json")
    op.drop_column("captured_items", "intake_failed_rules_json")
    op.drop_column("captured_items", "matches_intake")
    op.drop_column("captured_items", "intake_evaluation_status")

    bind = op.get_bind()
    intake_evaluation_status.drop(bind, checkfirst=True)
