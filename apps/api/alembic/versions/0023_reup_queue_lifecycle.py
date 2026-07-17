"""reup queue lifecycle fields

Revision ID: 0023_reup_queue_lifecycle
Revises: 0022_reup_queue
Create Date: 2026-04-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0023_reup_queue_lifecycle"
down_revision: str | None = "0022_reup_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

reup_queue_action = postgresql.ENUM(
    "START_PROCESSING",
    "MARK_MEDIA_READY",
    "MARK_BLOCKED",
    "HOLD",
    "RESUME",
    "RETRY",
    "CANCEL",
    "MARK_COMPLETED",
    name="reup_queue_action",
)

reup_queue_media_prep_status = postgresql.ENUM(
    "NOT_STARTED",
    "WAITING_FOR_MEDIA",
    "WAITING_FOR_METADATA",
    "READY_FOR_EXPORT",
    "BLOCKED",
    name="reup_queue_media_prep_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    reup_queue_action.create(bind, checkfirst=True)
    reup_queue_media_prep_status.create(bind, checkfirst=True)

    op.add_column("reup_queue_items", sa.Column("media_prep_status", postgresql.ENUM(name="reup_queue_media_prep_status", create_type=False), nullable=False, server_default="NOT_STARTED"))
    op.add_column("reup_queue_items", sa.Column("media_prep_notes", sa.Text(), nullable=True))
    op.add_column("reup_queue_items", sa.Column("media_ready_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reup_queue_items", sa.Column("blocked_reason", sa.Text(), nullable=True))
    op.add_column("reup_queue_items", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reup_queue_items", sa.Column("held_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reup_queue_items", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reup_queue_items", sa.Column("last_action", postgresql.ENUM(name="reup_queue_action", create_type=False), nullable=True))
    op.add_column("reup_queue_items", sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reup_queue_items", sa.Column("last_action_note", sa.Text(), nullable=True))

    op.create_index(op.f("ix_reup_queue_items_media_prep_status"), "reup_queue_items", ["media_prep_status"])
    op.create_index(op.f("ix_reup_queue_items_media_ready_at"), "reup_queue_items", ["media_ready_at"])
    op.create_index(op.f("ix_reup_queue_items_blocked_at"), "reup_queue_items", ["blocked_at"])
    op.create_index(op.f("ix_reup_queue_items_held_at"), "reup_queue_items", ["held_at"])
    op.create_index(op.f("ix_reup_queue_items_failed_at"), "reup_queue_items", ["failed_at"])
    op.create_index(op.f("ix_reup_queue_items_last_action"), "reup_queue_items", ["last_action"])
    op.create_index(op.f("ix_reup_queue_items_last_action_at"), "reup_queue_items", ["last_action_at"])
    op.alter_column("reup_queue_items", "media_prep_status", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_reup_queue_items_last_action_at"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_last_action"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_failed_at"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_held_at"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_blocked_at"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_media_ready_at"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_media_prep_status"), table_name="reup_queue_items")

    op.drop_column("reup_queue_items", "last_action_note")
    op.drop_column("reup_queue_items", "last_action_at")
    op.drop_column("reup_queue_items", "last_action")
    op.drop_column("reup_queue_items", "failed_at")
    op.drop_column("reup_queue_items", "held_at")
    op.drop_column("reup_queue_items", "blocked_at")
    op.drop_column("reup_queue_items", "blocked_reason")
    op.drop_column("reup_queue_items", "media_ready_at")
    op.drop_column("reup_queue_items", "media_prep_notes")
    op.drop_column("reup_queue_items", "media_prep_status")

    bind = op.get_bind()
    reup_queue_media_prep_status.drop(bind, checkfirst=True)
    reup_queue_action.drop(bind, checkfirst=True)
