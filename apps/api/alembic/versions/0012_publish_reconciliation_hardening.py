"""publish reconciliation hardening

Revision ID: 0012_pub_reconcile
Revises: 0011_fb_publish
Create Date: 2026-04-18 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0012_pub_reconcile"
down_revision: str | None = "0011_fb_publish"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE publish_draft_status ADD VALUE IF NOT EXISTS 'PUBLISHING'")
    op.execute("ALTER TYPE publish_draft_status ADD VALUE IF NOT EXISTS 'NEEDS_ATTENTION'")
    op.execute("ALTER TYPE publish_attempt_status ADD VALUE IF NOT EXISTS 'NEEDS_RECONCILIATION'")
    op.execute("ALTER TYPE publish_attempt_status ADD VALUE IF NOT EXISTS 'RECONCILING'")
    op.execute("ALTER TYPE publish_attempt_status ADD VALUE IF NOT EXISTS 'RECONCILED'")

    external_publication_status = postgresql.ENUM(
        "UNKNOWN",
        "PROCESSING",
        "PUBLISHED",
        "FAILED",
        "REMOVED",
        "NOT_FOUND",
        "PARTIALLY_CONFIRMED",
        name="external_publication_status",
        create_type=False,
    )
    external_publication_status.create(op.get_bind(), checkfirst=True)
    publish_reconciliation_status = postgresql.ENUM(
        "NOT_REQUIRED",
        "REQUIRED",
        "IN_PROGRESS",
        "RESOLVED_SUCCESS",
        "RESOLVED_FAILURE",
        "UNRESOLVED",
        name="publish_reconciliation_status",
        create_type=False,
    )
    publish_reconciliation_status.create(op.get_bind(), checkfirst=True)

    op.add_column("publish_attempts", sa.Column("external_permalink", sa.Text(), nullable=True))
    op.add_column(
        "publish_attempts",
        sa.Column(
            "external_status",
            external_publication_status,
            nullable=False,
            server_default="UNKNOWN",
        ),
    )
    op.add_column(
        "publish_attempts",
        sa.Column(
            "reconciliation_status",
            publish_reconciliation_status,
            nullable=False,
            server_default="NOT_REQUIRED",
        ),
    )
    op.add_column(
        "publish_attempts",
        sa.Column("reconciliation_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("publish_attempts", sa.Column("last_status_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_attempts", sa.Column("last_status_sync_result_json", postgresql.JSONB(), nullable=True))

    op.add_column("publish_drafts", sa.Column("canonical_publish_attempt_id", sa.Uuid(), nullable=True))
    op.add_column("publish_drafts", sa.Column("latest_publish_attempt_id", sa.Uuid(), nullable=True))
    op.add_column(
        "publish_drafts",
        sa.Column(
            "current_publication_status",
            external_publication_status,
            nullable=False,
            server_default="UNKNOWN",
        ),
    )
    op.add_column("publish_drafts", sa.Column("current_external_publish_id", sa.String(length=240), nullable=True))
    op.add_column("publish_drafts", sa.Column("current_external_permalink", sa.Text(), nullable=True))
    op.add_column("publish_drafts", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_drafts", sa.Column("last_publish_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_drafts", sa.Column("publication_summary_json", postgresql.JSONB(), nullable=True))

    op.create_foreign_key(
        op.f("fk_publish_drafts_canonical_publish_attempt_id_publish_attempts"),
        "publish_drafts",
        "publish_attempts",
        ["canonical_publish_attempt_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_publish_drafts_latest_publish_attempt_id_publish_attempts"),
        "publish_drafts",
        "publish_attempts",
        ["latest_publish_attempt_id"],
        ["id"],
    )

    for table_name, column in [
        ("publish_attempts", "external_status"),
        ("publish_attempts", "reconciliation_status"),
        ("publish_attempts", "reconciliation_required"),
        ("publish_drafts", "canonical_publish_attempt_id"),
        ("publish_drafts", "latest_publish_attempt_id"),
        ("publish_drafts", "current_publication_status"),
        ("publish_drafts", "current_external_publish_id"),
    ]:
        op.create_index(op.f(f"ix_{table_name}_{column}"), table_name, [column])

    op.alter_column("publish_attempts", "external_status", server_default=None)
    op.alter_column("publish_attempts", "reconciliation_status", server_default=None)
    op.alter_column("publish_attempts", "reconciliation_required", server_default=None)
    op.alter_column("publish_drafts", "current_publication_status", server_default=None)


def downgrade() -> None:
    for table_name, column in [
        ("publish_drafts", "current_external_publish_id"),
        ("publish_drafts", "current_publication_status"),
        ("publish_drafts", "latest_publish_attempt_id"),
        ("publish_drafts", "canonical_publish_attempt_id"),
        ("publish_attempts", "reconciliation_required"),
        ("publish_attempts", "reconciliation_status"),
        ("publish_attempts", "external_status"),
    ]:
        op.drop_index(op.f(f"ix_{table_name}_{column}"), table_name=table_name)

    op.drop_constraint(op.f("fk_publish_drafts_latest_publish_attempt_id_publish_attempts"), "publish_drafts", type_="foreignkey")
    op.drop_constraint(op.f("fk_publish_drafts_canonical_publish_attempt_id_publish_attempts"), "publish_drafts", type_="foreignkey")

    op.drop_column("publish_drafts", "publication_summary_json")
    op.drop_column("publish_drafts", "last_publish_synced_at")
    op.drop_column("publish_drafts", "published_at")
    op.drop_column("publish_drafts", "current_external_permalink")
    op.drop_column("publish_drafts", "current_external_publish_id")
    op.drop_column("publish_drafts", "current_publication_status")
    op.drop_column("publish_drafts", "latest_publish_attempt_id")
    op.drop_column("publish_drafts", "canonical_publish_attempt_id")

    op.drop_column("publish_attempts", "last_status_sync_result_json")
    op.drop_column("publish_attempts", "last_status_checked_at")
    op.drop_column("publish_attempts", "reconciliation_required")
    op.drop_column("publish_attempts", "reconciliation_status")
    op.drop_column("publish_attempts", "external_status")
    op.drop_column("publish_attempts", "external_permalink")

    postgresql.ENUM(name="publish_reconciliation_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="external_publication_status").drop(op.get_bind(), checkfirst=True)
