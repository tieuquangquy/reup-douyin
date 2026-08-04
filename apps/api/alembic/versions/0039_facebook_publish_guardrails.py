"""Add a database backstop for one active publish per platform account.

Revision ID: 0039_facebook_publish_guardrails
Revises: 0038_facebook_oauth
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "0039_facebook_publish_guardrails"
down_revision = "0038_facebook_oauth"
branch_labels = None
depends_on = None


ACTIVE_STATUS_PREDICATE = sa.text(
    "status IN ('QUEUED', 'RUNNING', 'UPLOADING', 'PUBLISHING', "
    "'AWAITING_PLATFORM_CONFIRMATION', 'RECONCILING')"
)


def upgrade() -> None:
    op.create_index(
        "uq_publish_attempts_one_active_per_account",
        "publish_attempts",
        ["platform_account_id"],
        unique=True,
        postgresql_where=ACTIVE_STATUS_PREDICATE,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_publish_attempts_one_active_per_account",
        table_name="publish_attempts",
    )
