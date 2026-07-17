"""douyin capture inbox

Revision ID: 0021_douyin_capture_inbox
Revises: 0020_intake_saved_presets
Create Date: 2026-04-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0021_douyin_capture_inbox"
down_revision: str | None = "0020_intake_saved_presets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

capture_session_status = postgresql.ENUM(
    "RECEIVED",
    "ENRICHING",
    "READY_FOR_REVIEW",
    "PARTIALLY_PROMOTED",
    "PROMOTED",
    "FAILED",
    name="capture_session_status",
)

captured_item_status = postgresql.ENUM(
    "RAW",
    "ENRICHED",
    "READY",
    "NEEDS_ENRICHMENT",
    "PREVIEW_MISSING",
    "DUPLICATE",
    "EXCLUDED",
    "PROMOTED",
    "FAILED",
    name="captured_item_status",
)


def upgrade() -> None:
    bind = op.get_bind()
    capture_session_status.create(bind, checkfirst=True)
    captured_item_status.create(bind, checkfirst=True)

    op.create_table(
        "capture_sessions",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.String(length=120), nullable=True),
        sa.Column("source_platform", postgresql.ENUM("DOUYIN", name="source_platform_enum", create_type=False), nullable=False),
        sa.Column("capture_source", sa.String(length=120), nullable=False),
        sa.Column("status", postgresql.ENUM(name="capture_session_status", create_type=False), nullable=False),
        sa.Column("detected_page_type", sa.String(length=80), nullable=True),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column("page_title", sa.Text(), nullable=True),
        sa.Column("submitted_profile_url", sa.Text(), nullable=True),
        sa.Column("normalized_profile_identifier", sa.String(length=180), nullable=True),
        sa.Column("visible_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("captured_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("normalized_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ready_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("promoted_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("diagnostics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capture_sessions")),
        sa.UniqueConstraint("workspace_id", "capture_id", name="uq_capture_sessions_workspace_capture_id"),
    )
    op.create_index(op.f("ix_capture_sessions_workspace_id"), "capture_sessions", ["workspace_id"])
    op.create_index(op.f("ix_capture_sessions_capture_id"), "capture_sessions", ["capture_id"])
    op.create_index(op.f("ix_capture_sessions_source_platform"), "capture_sessions", ["source_platform"])
    op.create_index(op.f("ix_capture_sessions_capture_source"), "capture_sessions", ["capture_source"])
    op.create_index(op.f("ix_capture_sessions_status"), "capture_sessions", ["status"])
    op.create_index(op.f("ix_capture_sessions_detected_page_type"), "capture_sessions", ["detected_page_type"])
    op.create_index(op.f("ix_capture_sessions_normalized_profile_identifier"), "capture_sessions", ["normalized_profile_identifier"])

    op.create_table(
        "captured_items",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("capture_session_id", sa.Uuid(), nullable=False),
        sa.Column("source_platform", postgresql.ENUM("DOUYIN", name="source_platform_enum", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM(name="captured_item_status", create_type=False), nullable=False),
        sa.Column("raw_item_index", sa.Integer(), nullable=False),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_profile_external_id", sa.String(length=180), nullable=True),
        sa.Column("profile_url", sa.Text(), nullable=True),
        sa.Column("source_video_external_id", sa.String(length=180), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("share_url", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("preview_url", sa.Text(), nullable=True),
        sa.Column("preview_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("media_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("readiness_reasons_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dedupe_key", sa.String(length=300), nullable=True),
        sa.Column("duplicate_of_item_id", sa.Uuid(), nullable=True),
        sa.Column("existing_source_video_id", sa.Uuid(), nullable=True),
        sa.Column("promoted_source_video_id", sa.Uuid(), nullable=True),
        sa.Column("promoted_video_candidate_id", sa.Uuid(), nullable=True),
        sa.Column("promoted_crawl_session_id", sa.Uuid(), nullable=True),
        sa.Column("enrichment_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("excluded_reason", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["capture_session_id"], ["capture_sessions.id"]),
        sa.ForeignKeyConstraint(["duplicate_of_item_id"], ["captured_items.id"]),
        sa.ForeignKeyConstraint(["existing_source_video_id"], ["source_videos.id"]),
        sa.ForeignKeyConstraint(["promoted_source_video_id"], ["source_videos.id"]),
        sa.ForeignKeyConstraint(["promoted_video_candidate_id"], ["video_candidates.id"]),
        sa.ForeignKeyConstraint(["promoted_crawl_session_id"], ["crawl_sessions.id"]),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_captured_items")),
        sa.UniqueConstraint("capture_session_id", "dedupe_key", name="uq_captured_items_session_dedupe_key"),
    )
    op.create_index(op.f("ix_captured_items_workspace_id"), "captured_items", ["workspace_id"])
    op.create_index(op.f("ix_captured_items_capture_session_id"), "captured_items", ["capture_session_id"])
    op.create_index(op.f("ix_captured_items_source_platform"), "captured_items", ["source_platform"])
    op.create_index(op.f("ix_captured_items_status"), "captured_items", ["status"])
    op.create_index(op.f("ix_captured_items_source_profile_external_id"), "captured_items", ["source_profile_external_id"])
    op.create_index(op.f("ix_captured_items_source_video_external_id"), "captured_items", ["source_video_external_id"])
    op.create_index(op.f("ix_captured_items_posted_at"), "captured_items", ["posted_at"])
    op.create_index(op.f("ix_captured_items_dedupe_key"), "captured_items", ["dedupe_key"])
    op.create_index(op.f("ix_captured_items_duplicate_of_item_id"), "captured_items", ["duplicate_of_item_id"])
    op.create_index(op.f("ix_captured_items_existing_source_video_id"), "captured_items", ["existing_source_video_id"])
    op.create_index(op.f("ix_captured_items_promoted_source_video_id"), "captured_items", ["promoted_source_video_id"])
    op.create_index(op.f("ix_captured_items_promoted_video_candidate_id"), "captured_items", ["promoted_video_candidate_id"])
    op.create_index(op.f("ix_captured_items_promoted_crawl_session_id"), "captured_items", ["promoted_crawl_session_id"])

    for column_name in (
        "visible_item_count",
        "captured_item_count",
        "normalized_item_count",
        "duplicate_item_count",
        "ready_item_count",
        "skipped_item_count",
        "promoted_item_count",
        "candidate_created_count",
        "failed_item_count",
    ):
        op.alter_column("capture_sessions", column_name, server_default=None)

    for column_name in ("preview_ready", "media_ready"):
        op.alter_column("captured_items", column_name, server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_captured_items_promoted_crawl_session_id"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_promoted_video_candidate_id"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_promoted_source_video_id"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_existing_source_video_id"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_duplicate_of_item_id"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_dedupe_key"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_posted_at"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_source_video_external_id"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_source_profile_external_id"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_status"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_source_platform"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_capture_session_id"), table_name="captured_items")
    op.drop_index(op.f("ix_captured_items_workspace_id"), table_name="captured_items")
    op.drop_table("captured_items")

    op.drop_index(op.f("ix_capture_sessions_normalized_profile_identifier"), table_name="capture_sessions")
    op.drop_index(op.f("ix_capture_sessions_detected_page_type"), table_name="capture_sessions")
    op.drop_index(op.f("ix_capture_sessions_status"), table_name="capture_sessions")
    op.drop_index(op.f("ix_capture_sessions_capture_source"), table_name="capture_sessions")
    op.drop_index(op.f("ix_capture_sessions_source_platform"), table_name="capture_sessions")
    op.drop_index(op.f("ix_capture_sessions_capture_id"), table_name="capture_sessions")
    op.drop_index(op.f("ix_capture_sessions_workspace_id"), table_name="capture_sessions")
    op.drop_table("capture_sessions")

    bind = op.get_bind()
    captured_item_status.drop(bind, checkfirst=True)
    capture_session_status.drop(bind, checkfirst=True)
