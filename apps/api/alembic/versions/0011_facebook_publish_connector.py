"""facebook publish connector foundation

Revision ID: 0011_fb_publish
Revises: 0010_risk
Create Date: 2026-04-17 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011_fb_publish"
down_revision: str | None = "0010_risk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'PUBLISH_CONTENT'")

    publish_target_platform = postgresql.ENUM("TIKTOK", "FACEBOOK_REELS", "YOUTUBE_SHORTS", name="publish_target_platform", create_type=False)
    publish_target_platform.create(op.get_bind(), checkfirst=True)
    platform_account_status = postgresql.ENUM("ACTIVE", "PAUSED", "INVALID", "ARCHIVED", name="platform_account_status", create_type=False)
    platform_account_status.create(op.get_bind(), checkfirst=True)
    publish_attempt_status = postgresql.ENUM(
        "QUEUED",
        "RUNNING",
        "UPLOADING",
        "PUBLISHING",
        "AWAITING_PLATFORM_CONFIRMATION",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        name="publish_attempt_status",
        create_type=False,
    )
    publish_attempt_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "platform_accounts",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("platform", publish_target_platform, nullable=False),
        sa.Column("display_name", sa.String(length=180), nullable=False),
        sa.Column("external_account_id", sa.String(length=180), nullable=False),
        sa.Column("token_reference", sa.String(length=240), nullable=True),
        sa.Column("status", platform_account_status, nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_platform_accounts_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_accounts")),
        sa.UniqueConstraint("workspace_id", "platform", "external_account_id", name="uq_platform_accounts_workspace_platform_external"),
    )
    for column in ["workspace_id", "platform", "external_account_id", "status"]:
        op.create_index(op.f(f"ix_platform_accounts_{column}"), "platform_accounts", [column])

    op.create_table(
        "publish_attempts",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("publish_draft_id", sa.Uuid(), nullable=False),
        sa.Column("platform", publish_target_platform, nullable=False),
        sa.Column("platform_account_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", publish_attempt_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_publish_id", sa.String(length=240), nullable=True),
        sa.Column("external_media_id", sa.String(length=240), nullable=True),
        sa.Column("external_reel_id", sa.String(length=240), nullable=True),
        sa.Column("request_summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("response_summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("warning_summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_job_id", sa.Uuid(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_job_id"], ["jobs.id"], name=op.f("fk_publish_attempts_created_by_job_id_jobs")),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"], name=op.f("fk_publish_attempts_platform_account_id_platform_accounts")),
        sa.ForeignKeyConstraint(["publish_draft_id"], ["publish_drafts.id"], name=op.f("fk_publish_attempts_publish_draft_id_publish_drafts")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_publish_attempts_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publish_attempts")),
        sa.UniqueConstraint("publish_draft_id", "attempt_number", name="uq_publish_attempts_draft_attempt_number"),
    )
    for column in [
        "workspace_id",
        "publish_draft_id",
        "platform",
        "platform_account_id",
        "status",
        "external_publish_id",
        "external_media_id",
        "external_reel_id",
        "error_code",
        "created_by_job_id",
    ]:
        op.create_index(op.f(f"ix_publish_attempts_{column}"), "publish_attempts", [column])


def downgrade() -> None:
    op.drop_table("publish_attempts")
    op.drop_table("platform_accounts")
    postgresql.ENUM(name="publish_attempt_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="platform_account_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="publish_target_platform").drop(op.get_bind(), checkfirst=True)
