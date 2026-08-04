"""Add canonical platform publication authority.

Revision ID: 0033_publication_authority
Revises: 0032_reup_queue_auto_pipeline
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0033_publication_authority"
down_revision: str | None = "0032_reup_queue_auto_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    publish_target_platform = postgresql.ENUM(
        "TIKTOK",
        "FACEBOOK_REELS",
        "YOUTUBE_SHORTS",
        name="publish_target_platform",
        create_type=False,
    )
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

    op.create_table(
        "platform_publications",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("publish_draft_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("render_output_id", sa.Uuid(), nullable=True),
        sa.Column("platform", publish_target_platform, nullable=False),
        sa.Column("platform_account_id", sa.Uuid(), nullable=False),
        sa.Column("publish_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("external_publish_id", sa.String(length=240), nullable=False),
        sa.Column("external_media_id", sa.String(length=240), nullable=True),
        sa.Column("external_reel_id", sa.String(length=240), nullable=True),
        sa.Column("external_permalink", sa.Text(), nullable=True),
        sa.Column("status", external_publication_status, nullable=False),
        sa.Column("is_canonical", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_fingerprint_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "native_product_placement_status",
            sa.String(length=80),
            server_default="NOT_EVALUATED",
            nullable=False,
        ),
        sa.Column(
            "affiliate_comment_status",
            sa.String(length=80),
            server_default="NOT_PLANNED",
            nullable=False,
        ),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name=op.f("fk_platform_publications_workspace_id_workspaces")
        ),
        sa.ForeignKeyConstraint(
            ["publish_draft_id"],
            ["publish_drafts.id"],
            name=op.f("fk_platform_publications_publish_draft_id_publish_drafts"),
        ),
        sa.ForeignKeyConstraint(
            ["source_video_id"],
            ["source_videos.id"],
            name=op.f("fk_platform_publications_source_video_id_source_videos"),
        ),
        sa.ForeignKeyConstraint(
            ["render_output_id"],
            ["render_outputs.id"],
            name=op.f("fk_platform_publications_render_output_id_render_outputs"),
        ),
        sa.ForeignKeyConstraint(
            ["platform_account_id"],
            ["platform_accounts.id"],
            name=op.f("fk_platform_publications_platform_account_id_platform_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["publish_attempt_id"],
            ["publish_attempts.id"],
            name=op.f("fk_platform_publications_publish_attempt_id_publish_attempts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_publications")),
        sa.UniqueConstraint(
            "workspace_id",
            "platform",
            "platform_account_id",
            "external_publish_id",
            name="uq_platform_publications_external_identity",
        ),
        sa.UniqueConstraint(
            "publish_attempt_id",
            name="uq_platform_publications_publish_attempt",
        ),
    )
    for column in [
        "workspace_id",
        "publish_draft_id",
        "source_video_id",
        "render_output_id",
        "platform",
        "platform_account_id",
        "publish_attempt_id",
        "external_publish_id",
        "external_media_id",
        "external_reel_id",
        "status",
        "is_canonical",
        "published_at",
        "last_synced_at",
        "content_fingerprint_sha256",
        "native_product_placement_status",
        "affiliate_comment_status",
    ]:
        op.create_index(op.f(f"ix_platform_publications_{column}"), "platform_publications", [column])

    op.create_index(
        "uq_publish_attempts_one_active_per_draft",
        "publish_attempts",
        ["publish_draft_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('QUEUED', 'RUNNING', 'UPLOADING', 'PUBLISHING', "
            "'AWAITING_PLATFORM_CONFIRMATION', 'RECONCILING')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_publish_attempts_one_active_per_draft", table_name="publish_attempts")
    op.drop_table("platform_publications")
