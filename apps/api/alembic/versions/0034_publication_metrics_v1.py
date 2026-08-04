"""Add publication engagement metric snapshots.

Revision ID: 0034_publication_metrics
Revises: 0033_publication_authority
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0034_publication_metrics"
down_revision: str | None = "0033_publication_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publication_metric_snapshots",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("platform_publication_id", sa.Uuid(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collection_source", sa.String(length=80), nullable=False),
        sa.Column("provider_schema_version", sa.String(length=120), nullable=True),
        sa.Column("idempotency_key", sa.String(length=240), nullable=False),
        sa.Column("payload_hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("view_count", sa.BigInteger(), nullable=True),
        sa.Column("like_count", sa.BigInteger(), nullable=True),
        sa.Column("comment_count", sa.BigInteger(), nullable=True),
        sa.Column("share_count", sa.BigInteger(), nullable=True),
        sa.Column("save_count", sa.BigInteger(), nullable=True),
        sa.Column("impression_count", sa.BigInteger(), nullable=True),
        sa.Column("reach_count", sa.BigInteger(), nullable=True),
        sa.Column("follower_gain_count", sa.BigInteger(), nullable=True),
        sa.Column("total_watch_time_seconds", sa.Float(), nullable=True),
        sa.Column("average_watch_time_seconds", sa.Float(), nullable=True),
        sa.Column("completion_rate_percent", sa.Float(), nullable=True),
        sa.Column("is_estimated", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("data_quality", sa.String(length=40), server_default="UNKNOWN", nullable=False),
        sa.Column("unavailable_metrics_json", postgresql.JSONB(), nullable=True),
        sa.Column("provider_summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("delta_view_count", sa.BigInteger(), nullable=True),
        sa.Column("delta_like_count", sa.BigInteger(), nullable=True),
        sa.Column("delta_comment_count", sa.BigInteger(), nullable=True),
        sa.Column("delta_share_count", sa.BigInteger(), nullable=True),
        sa.Column("delta_save_count", sa.BigInteger(), nullable=True),
        sa.Column("views_per_hour", sa.Float(), nullable=True),
        sa.Column("engagement_rate_percent", sa.Float(), nullable=True),
        sa.Column("engagement_delta_rate_percent", sa.Float(), nullable=True),
        sa.Column("counter_regression_detected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("derivation_version", sa.String(length=80), server_default="PUBLICATION_METRICS_V1", nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("view_count IS NULL OR view_count >= 0", name=op.f("ck_publication_metric_snapshots_publication_metrics_view_nonnegative")),
        sa.CheckConstraint("like_count IS NULL OR like_count >= 0", name=op.f("ck_publication_metric_snapshots_publication_metrics_like_nonnegative")),
        sa.CheckConstraint("comment_count IS NULL OR comment_count >= 0", name=op.f("ck_publication_metric_snapshots_publication_metrics_comment_nonnegative")),
        sa.CheckConstraint("share_count IS NULL OR share_count >= 0", name=op.f("ck_publication_metric_snapshots_publication_metrics_share_nonnegative")),
        sa.CheckConstraint("save_count IS NULL OR save_count >= 0", name=op.f("ck_publication_metric_snapshots_publication_metrics_save_nonnegative")),
        sa.CheckConstraint("impression_count IS NULL OR impression_count >= 0", name=op.f("ck_publication_metric_snapshots_publication_metrics_impression_nonnegative")),
        sa.CheckConstraint("reach_count IS NULL OR reach_count >= 0", name=op.f("ck_publication_metric_snapshots_publication_metrics_reach_nonnegative")),
        sa.CheckConstraint("follower_gain_count IS NULL OR follower_gain_count >= 0", name=op.f("ck_publication_metric_snapshots_publication_metrics_follower_gain_nonnegative")),
        sa.CheckConstraint("total_watch_time_seconds IS NULL OR total_watch_time_seconds >= 0", name=op.f("ck_publication_metric_snapshots_publication_metrics_watch_time_nonnegative")),
        sa.CheckConstraint("average_watch_time_seconds IS NULL OR average_watch_time_seconds >= 0", name=op.f("ck_publication_metric_snapshots_publication_metrics_average_watch_nonnegative")),
        sa.CheckConstraint("completion_rate_percent IS NULL OR (completion_rate_percent >= 0 AND completion_rate_percent <= 100)", name=op.f("ck_publication_metric_snapshots_publication_metrics_completion_rate_range")),
        sa.CheckConstraint("interval_seconds IS NULL OR interval_seconds >= 0", name=op.f("ck_publication_metric_snapshots_publication_metrics_interval_nonnegative")),
        sa.ForeignKeyConstraint(["platform_publication_id"], ["platform_publications.id"], name=op.f("fk_publication_metric_snapshots_platform_publication_id_platform_publications")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_publication_metric_snapshots_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publication_metric_snapshots")),
        sa.UniqueConstraint(
            "platform_publication_id",
            "idempotency_key",
            name="uq_publication_metric_snapshots_publication_idempotency",
        ),
    )
    for column in [
        "workspace_id",
        "platform_publication_id",
        "observed_at",
        "collection_source",
        "payload_hash_sha256",
        "is_estimated",
        "data_quality",
        "counter_regression_detected",
    ]:
        op.create_index(op.f(f"ix_publication_metric_snapshots_{column}"), "publication_metric_snapshots", [column])

    op.create_index(
        "ix_publication_metric_snapshots_publication_observed",
        "publication_metric_snapshots",
        ["platform_publication_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_table("publication_metric_snapshots")
