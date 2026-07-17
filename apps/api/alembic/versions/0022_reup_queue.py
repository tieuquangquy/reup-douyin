"""reup queue

Revision ID: 0022_reup_queue
Revises: 0021_douyin_capture_inbox
Create Date: 2026-04-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0022_reup_queue"
down_revision: str | None = "0021_douyin_capture_inbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

reup_queue_status = postgresql.ENUM(
    "READY_FOR_PROCESSING",
    "WAITING_FOR_MEDIA",
    "WAITING_FOR_METADATA",
    "PROCESSING",
    "READY_TO_EXPORT",
    "READY_TO_PUBLISH",
    "FAILED_NEEDS_ATTENTION",
    "COMPLETED",
    "CANCELLED",
    name="reup_queue_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    reup_queue_status.create(bind, checkfirst=True)

    op.create_table(
        "reup_queue_items",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("video_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("status", postgresql.ENUM(name="reup_queue_status", create_type=False), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("queued_reason", sa.Text(), nullable=True),
        sa.Column("operator_note", sa.Text(), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("render_output_id", sa.Uuid(), nullable=True),
        sa.Column("publish_draft_id", sa.Uuid(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["video_candidate_id"], ["video_candidates.id"]),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["render_output_id"], ["render_outputs.id"]),
        sa.ForeignKeyConstraint(["publish_draft_id"], ["publish_drafts.id"]),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reup_queue_items")),
        sa.UniqueConstraint("workspace_id", "video_candidate_id", name="uq_reup_queue_items_workspace_candidate"),
    )
    op.create_index(op.f("ix_reup_queue_items_workspace_id"), "reup_queue_items", ["workspace_id"])
    op.create_index(op.f("ix_reup_queue_items_video_candidate_id"), "reup_queue_items", ["video_candidate_id"])
    op.create_index(op.f("ix_reup_queue_items_source_video_id"), "reup_queue_items", ["source_video_id"])
    op.create_index(op.f("ix_reup_queue_items_status"), "reup_queue_items", ["status"])
    op.create_index(op.f("ix_reup_queue_items_priority"), "reup_queue_items", ["priority"])
    op.create_index(op.f("ix_reup_queue_items_last_error_code"), "reup_queue_items", ["last_error_code"])
    op.create_index(op.f("ix_reup_queue_items_queued_at"), "reup_queue_items", ["queued_at"])
    op.create_index(op.f("ix_reup_queue_items_started_at"), "reup_queue_items", ["started_at"])
    op.create_index(op.f("ix_reup_queue_items_completed_at"), "reup_queue_items", ["completed_at"])
    op.create_index(op.f("ix_reup_queue_items_cancelled_at"), "reup_queue_items", ["cancelled_at"])
    op.create_index(op.f("ix_reup_queue_items_job_id"), "reup_queue_items", ["job_id"])
    op.create_index(op.f("ix_reup_queue_items_render_output_id"), "reup_queue_items", ["render_output_id"])
    op.create_index(op.f("ix_reup_queue_items_publish_draft_id"), "reup_queue_items", ["publish_draft_id"])
    op.alter_column("reup_queue_items", "priority", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_reup_queue_items_publish_draft_id"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_render_output_id"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_job_id"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_cancelled_at"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_completed_at"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_started_at"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_queued_at"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_last_error_code"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_priority"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_status"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_source_video_id"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_video_candidate_id"), table_name="reup_queue_items")
    op.drop_index(op.f("ix_reup_queue_items_workspace_id"), table_name="reup_queue_items")
    op.drop_table("reup_queue_items")

    bind = op.get_bind()
    reup_queue_status.drop(bind, checkfirst=True)
