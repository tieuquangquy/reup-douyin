"""Add adaptive publication metric cadence schedules.

Revision ID: 0036_metric_cadence
Revises: 0035_metric_collector_job
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0036_metric_cadence"
down_revision: str | None = "0035_metric_collector_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publication_metric_schedules",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("platform_publication_id", sa.Uuid(), nullable=False),
        sa.Column("collector_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="ACTIVE", nullable=False),
        sa.Column("policy_version", sa.String(length=80), server_default="METRICS_CADENCE_V1", nullable=False),
        sa.Column("next_collection_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_collection_job_id", sa.Uuid(), nullable=True),
        sa.Column("last_metric_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("collection_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("consecutive_flat_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_age_hours", sa.Integer(), server_default="168", nullable=False),
        sa.Column("collector_config_json", postgresql.JSONB(), nullable=True),
        sa.Column("last_decision_json", postgresql.JSONB(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'PAUSED', 'COMPLETED', 'BLOCKED')", name=op.f("ck_publication_metric_schedules_publication_metric_schedule_status_valid")),
        sa.CheckConstraint("collection_count >= 0", name=op.f("ck_publication_metric_schedules_publication_metric_schedule_collection_count_nonnegative")),
        sa.CheckConstraint("consecutive_flat_count >= 0", name=op.f("ck_publication_metric_schedules_publication_metric_schedule_flat_count_nonnegative")),
        sa.CheckConstraint("max_age_hours > 0", name=op.f("ck_publication_metric_schedules_publication_metric_schedule_max_age_positive")),
        sa.ForeignKeyConstraint(["last_collection_job_id"], ["jobs.id"], name=op.f("fk_publication_metric_schedules_last_collection_job_id_jobs")),
        sa.ForeignKeyConstraint(["last_metric_snapshot_id"], ["publication_metric_snapshots.id"], name=op.f("fk_publication_metric_schedules_last_metric_snapshot_id_publication_metric_snapshots")),
        sa.ForeignKeyConstraint(["platform_publication_id"], ["platform_publications.id"], name=op.f("fk_publication_metric_schedules_platform_publication_id_platform_publications")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_publication_metric_schedules_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publication_metric_schedules")),
        sa.UniqueConstraint("platform_publication_id", name="uq_publication_metric_schedules_publication"),
    )
    for column in [
        "workspace_id",
        "platform_publication_id",
        "collector_name",
        "status",
        "next_collection_at",
        "last_collection_job_id",
        "last_metric_snapshot_id",
    ]:
        op.create_index(op.f(f"ix_publication_metric_schedules_{column}"), "publication_metric_schedules", [column])
    op.create_index(
        "ix_publication_metric_schedules_due",
        "publication_metric_schedules",
        ["status", "next_collection_at"],
    )


def downgrade() -> None:
    op.drop_table("publication_metric_schedules")
