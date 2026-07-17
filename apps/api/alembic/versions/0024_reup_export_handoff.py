"""reup export package and publish handoff

Revision ID: 0024_reup_export_handoff
Revises: 0023_reup_queue_lifecycle
Create Date: 2026-04-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0024_reup_export_handoff"
down_revision: str | None = "0023_reup_queue_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

export_package_status = postgresql.ENUM(
    "DRAFT",
    "READY_FOR_HANDOFF",
    "HANDOFF_CREATED",
    "FAILED_NEEDS_ATTENTION",
    "CANCELLED",
    name="export_package_status",
)

publish_handoff_status = postgresql.ENUM(
    "DRAFT",
    "READY_FOR_OPERATOR",
    "ACCEPTED",
    "FAILED_NEEDS_ATTENTION",
    "CANCELLED",
    name="publish_handoff_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    export_package_status.create(bind, checkfirst=True)
    publish_handoff_status.create(bind, checkfirst=True)

    op.execute("ALTER TYPE reup_queue_status ADD VALUE IF NOT EXISTS 'EXPORT_PACKAGE_CREATED'")
    op.execute("ALTER TYPE reup_queue_status ADD VALUE IF NOT EXISTS 'PUBLISH_HANDOFF_CREATED'")

    op.create_table(
        "export_packages",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("status", postgresql.ENUM(name="export_package_status", create_type=False), nullable=False),
        sa.Column("label", sa.String(length=180), nullable=True),
        sa.Column("operator_note", sa.Text(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("diagnostics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_export_packages")),
    )
    op.create_index(op.f("ix_export_packages_workspace_id"), "export_packages", ["workspace_id"])
    op.create_index(op.f("ix_export_packages_status"), "export_packages", ["status"])
    op.create_index(op.f("ix_export_packages_label"), "export_packages", ["label"])
    op.create_index(op.f("ix_export_packages_ready_at"), "export_packages", ["ready_at"])
    op.create_index(op.f("ix_export_packages_failed_at"), "export_packages", ["failed_at"])
    op.create_index(op.f("ix_export_packages_cancelled_at"), "export_packages", ["cancelled_at"])
    op.alter_column("export_packages", "item_count", server_default=None)

    op.create_table(
        "export_package_items",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("export_package_id", sa.Uuid(), nullable=False),
        sa.Column("reup_queue_item_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("video_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("render_output_id", sa.Uuid(), nullable=True),
        sa.Column("publish_draft_id", sa.Uuid(), nullable=True),
        sa.Column("item_status", sa.String(length=80), nullable=False, server_default="INCLUDED"),
        sa.Column("manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("diagnostics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["export_package_id"], ["export_packages.id"]),
        sa.ForeignKeyConstraint(["reup_queue_item_id"], ["reup_queue_items.id"]),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"]),
        sa.ForeignKeyConstraint(["video_candidate_id"], ["video_candidates.id"]),
        sa.ForeignKeyConstraint(["render_output_id"], ["render_outputs.id"]),
        sa.ForeignKeyConstraint(["publish_draft_id"], ["publish_drafts.id"]),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_export_package_items")),
        sa.UniqueConstraint("export_package_id", "reup_queue_item_id", name="uq_export_package_items_package_queue_item"),
    )
    for column in ["workspace_id", "export_package_id", "reup_queue_item_id", "source_video_id", "video_candidate_id", "render_output_id", "publish_draft_id", "item_status"]:
        op.create_index(op.f(f"ix_export_package_items_{column}"), "export_package_items", [column])
    op.alter_column("export_package_items", "item_status", server_default=None)

    op.create_table(
        "publish_handoffs",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("export_package_id", sa.Uuid(), nullable=False),
        sa.Column("target_platform", postgresql.ENUM(name="publish_target_platform", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM(name="publish_handoff_status", create_type=False), nullable=False),
        sa.Column("operator_note", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("diagnostics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["export_package_id"], ["export_packages.id"]),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publish_handoffs")),
    )
    for column in ["workspace_id", "export_package_id", "target_platform", "status", "ready_at", "accepted_at", "failed_at", "cancelled_at"]:
        op.create_index(op.f(f"ix_publish_handoffs_{column}"), "publish_handoffs", [column])


def downgrade() -> None:
    for column in ["workspace_id", "export_package_id", "target_platform", "status", "ready_at", "accepted_at", "failed_at", "cancelled_at"]:
        op.drop_index(op.f(f"ix_publish_handoffs_{column}"), table_name="publish_handoffs")
    op.drop_table("publish_handoffs")

    for column in ["workspace_id", "export_package_id", "reup_queue_item_id", "source_video_id", "video_candidate_id", "render_output_id", "publish_draft_id", "item_status"]:
        op.drop_index(op.f(f"ix_export_package_items_{column}"), table_name="export_package_items")
    op.drop_table("export_package_items")

    op.drop_index(op.f("ix_export_packages_cancelled_at"), table_name="export_packages")
    op.drop_index(op.f("ix_export_packages_failed_at"), table_name="export_packages")
    op.drop_index(op.f("ix_export_packages_ready_at"), table_name="export_packages")
    op.drop_index(op.f("ix_export_packages_label"), table_name="export_packages")
    op.drop_index(op.f("ix_export_packages_status"), table_name="export_packages")
    op.drop_index(op.f("ix_export_packages_workspace_id"), table_name="export_packages")
    op.drop_table("export_packages")

    bind = op.get_bind()
    publish_handoff_status.drop(bind, checkfirst=True)
    export_package_status.drop(bind, checkfirst=True)
