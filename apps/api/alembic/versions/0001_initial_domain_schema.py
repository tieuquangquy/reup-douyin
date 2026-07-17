"""initial domain schema

Revision ID: 0001_initial
Revises: None
Create Date: 2026-04-17 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


source_platform_enum = postgresql.ENUM("DOUYIN", name="source_platform_enum", create_type=False)
source_profile_status = postgresql.ENUM("ACTIVE", "PAUSED", "ARCHIVED", "FAILED", name="source_profile_status", create_type=False)
crawl_session_status = postgresql.ENUM("QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", name="crawl_session_status", create_type=False)
source_video_status = postgresql.ENUM("DISCOVERED", "FILTERED_IN", "REJECTED", "APPROVED_FOR_DOWNLOAD", "DOWNLOADED", "AI_ANALYZED", "NEEDS_SCRIPT_REVIEW", "NEEDS_OCR_REVIEW", "READY_FOR_RENDER", "RENDERING", "READY_FINAL_REVIEW", "EXPORTED", "PUBLISH_READY", "FAILED", name="source_video_status", create_type=False)
candidate_status = postgresql.ENUM("NEW", "SHORTLISTED", "IN_REVIEW", "APPROVED", "REJECTED", "ARCHIVED", name="candidate_status", create_type=False)
review_decision_status = postgresql.ENUM("PENDING", "APPROVED", "REJECTED", "NEEDS_CHANGES", "SUPERSEDED", name="review_decision_status", create_type=False)
media_asset_type = postgresql.ENUM("SOURCE_VIDEO", "SOURCE_AUDIO", "THUMBNAIL", "TRANSCRIPT", "TRANSLATION", "SUBTITLE", "OCR_FRAME", "RENDERED_VIDEO", "EXPORT_PACKAGE", name="media_asset_type", create_type=False)
media_asset_status = postgresql.ENUM("PLANNED", "AVAILABLE", "PROCESSING", "FAILED", "ARCHIVED", name="media_asset_status", create_type=False)
job_type = postgresql.ENUM("CRAWL_PROFILE", "DOWNLOAD_VIDEO", "ANALYZE_VIDEO", "OCR_VIDEO", "TRANSCRIBE_AUDIO", "TRANSLATE_TRANSCRIPT", "RENDER_VIDEO", "EXPORT_VIDEO", "PREPARE_PUBLISH", name="job_type", create_type=False)
job_status = postgresql.ENUM("QUEUED", "RUNNING", "WAITING_FOR_REVIEW", "FAILED", "RETRYABLE", "CANCELLED", "COMPLETED", name="job_status", create_type=False)
job_step_status = postgresql.ENUM("QUEUED", "RUNNING", "WAITING_FOR_REVIEW", "FAILED", "RETRYABLE", "CANCELLED", "COMPLETED", name="job_step_status", create_type=False)
transcript_segment_status = postgresql.ENUM("DRAFT", "NEEDS_REVIEW", "APPROVED", "REJECTED", name="transcript_segment_status", create_type=False)
ocr_object_status = postgresql.ENUM("DETECTED", "NEEDS_REVIEW", "APPROVED", "REJECTED", name="ocr_object_status", create_type=False)
render_output_status = postgresql.ENUM("PLANNED", "RENDERING", "READY_FOR_REVIEW", "APPROVED", "FAILED", "ARCHIVED", name="render_output_status", create_type=False)
publish_draft_status = postgresql.ENUM("DRAFT", "READY", "SCHEDULED", "PUBLISHED", "FAILED", "ARCHIVED", name="publish_draft_status", create_type=False)
risk_flag_type = postgresql.ENUM("COPYRIGHT", "WATERMARK", "LOW_QUALITY", "DUPLICATE", "POLICY", "MANUAL_REVIEW", name="risk_flag_type", create_type=False)
risk_severity = postgresql.ENUM("LOW", "MEDIUM", "HIGH", "BLOCKING", name="risk_severity", create_type=False)


def create_enums() -> None:
    bind = op.get_bind()
    for enum_type in (
        source_platform_enum,
        source_profile_status,
        crawl_session_status,
        source_video_status,
        candidate_status,
        review_decision_status,
        media_asset_type,
        media_asset_status,
        job_type,
        job_status,
        job_step_status,
        transcript_segment_status,
        ocr_object_status,
        render_output_status,
        publish_draft_status,
        risk_flag_type,
        risk_severity,
    ):
        enum_type.create(bind, checkfirst=True)


def drop_enums() -> None:
    bind = op.get_bind()
    for enum_type in (
        risk_severity,
        risk_flag_type,
        publish_draft_status,
        render_output_status,
        ocr_object_status,
        transcript_segment_status,
        job_step_status,
        job_status,
        job_type,
        media_asset_status,
        media_asset_type,
        review_decision_status,
        candidate_status,
        source_video_status,
        crawl_session_status,
        source_profile_status,
        source_platform_enum,
    ):
        enum_type.drop(bind, checkfirst=True)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    create_enums()

    op.create_table(
        "workspaces",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
        sa.UniqueConstraint("name", name=op.f("uq_workspaces_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_workspaces_slug")),
    )

    op.create_table(
        "niche_tags",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_niche_tags_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_niche_tags")),
        sa.UniqueConstraint("workspace_id", "name", name="uq_niche_tags_workspace_name"),
    )
    op.create_index(op.f("ix_niche_tags_workspace_id"), "niche_tags", ["workspace_id"])

    op.create_table(
        "workflow_templates",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("definition_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_workflow_templates_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_templates")),
        sa.UniqueConstraint("workspace_id", "name", name="uq_workflow_templates_workspace_name"),
    )
    op.create_index(op.f("ix_workflow_templates_workspace_id"), "workflow_templates", ["workspace_id"])

    op.create_table(
        "source_profiles",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_platform", source_platform_enum, nullable=False),
        sa.Column("source_profile_external_id", sa.String(length=180), nullable=False),
        sa.Column("profile_url", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=True),
        sa.Column("handle", sa.String(length=180), nullable=True),
        sa.Column("status", source_profile_status, nullable=False),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_source_profiles_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_profiles")),
        sa.UniqueConstraint("source_platform", "source_profile_external_id", name="uq_source_profiles_platform_external_id"),
    )
    op.create_index(op.f("ix_source_profiles_workspace_id"), "source_profiles", ["workspace_id"])
    op.create_index(op.f("ix_source_profiles_status"), "source_profiles", ["status"])

    op.create_table(
        "crawl_sessions",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_profile_id", sa.Uuid(), nullable=False),
        sa.Column("status", crawl_session_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("videos_discovered_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["source_profile_id"], ["source_profiles.id"], name=op.f("fk_crawl_sessions_source_profile_id_source_profiles")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_crawl_sessions_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crawl_sessions")),
    )
    op.create_index(op.f("ix_crawl_sessions_source_profile_id"), "crawl_sessions", ["source_profile_id"])
    op.create_index(op.f("ix_crawl_sessions_status"), "crawl_sessions", ["status"])
    op.create_index(op.f("ix_crawl_sessions_workspace_id"), "crawl_sessions", ["workspace_id"])

    op.create_table(
        "source_videos",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_profile_id", sa.Uuid(), nullable=False),
        sa.Column("first_crawl_session_id", sa.Uuid(), nullable=True),
        sa.Column("source_platform", source_platform_enum, nullable=False),
        sa.Column("source_video_external_id", sa.String(length=180), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("status", source_video_status, nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["first_crawl_session_id"], ["crawl_sessions.id"], name=op.f("fk_source_videos_first_crawl_session_id_crawl_sessions")),
        sa.ForeignKeyConstraint(["source_profile_id"], ["source_profiles.id"], name=op.f("fk_source_videos_source_profile_id_source_profiles")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_source_videos_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_videos")),
        sa.UniqueConstraint("source_platform", "source_video_external_id", name="uq_source_videos_platform_external_id"),
    )
    op.create_index(op.f("ix_source_videos_posted_at"), "source_videos", ["posted_at"])
    op.create_index(op.f("ix_source_videos_source_profile_id"), "source_videos", ["source_profile_id"])
    op.create_index(op.f("ix_source_videos_source_video_external_id"), "source_videos", ["source_video_external_id"])
    op.create_index(op.f("ix_source_videos_status"), "source_videos", ["status"])
    op.create_index(op.f("ix_source_videos_workspace_id"), "source_videos", ["workspace_id"])

    op.create_table(
        "video_metric_snapshots",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("crawl_session_id", sa.Uuid(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=True),
        sa.Column("like_count", sa.Integer(), nullable=True),
        sa.Column("comment_count", sa.Integer(), nullable=True),
        sa.Column("share_count", sa.Integer(), nullable=True),
        sa.Column("favorite_count", sa.Integer(), nullable=True),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["crawl_session_id"], ["crawl_sessions.id"], name=op.f("fk_video_metric_snapshots_crawl_session_id_crawl_sessions")),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_video_metric_snapshots_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_video_metric_snapshots_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_video_metric_snapshots")),
        sa.UniqueConstraint("source_video_id", "crawl_session_id", name="uq_video_metric_snapshots_video_crawl"),
    )
    op.create_index(op.f("ix_video_metric_snapshots_crawl_session_id"), "video_metric_snapshots", ["crawl_session_id"])
    op.create_index(op.f("ix_video_metric_snapshots_source_video_id"), "video_metric_snapshots", ["source_video_id"])
    op.create_index(op.f("ix_video_metric_snapshots_workspace_id"), "video_metric_snapshots", ["workspace_id"])

    op.create_table(
        "video_candidates",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("status", candidate_status, nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("score_reason", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_video_candidates_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_video_candidates_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_video_candidates")),
        sa.UniqueConstraint("source_video_id", name=op.f("uq_video_candidates_source_video_id")),
    )
    op.create_index(op.f("ix_video_candidates_source_video_id"), "video_candidates", ["source_video_id"])
    op.create_index(op.f("ix_video_candidates_status"), "video_candidates", ["status"])
    op.create_index(op.f("ix_video_candidates_workspace_id"), "video_candidates", ["workspace_id"])

    op.create_table(
        "media_assets",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("asset_type", media_asset_type, nullable=False),
        sa.Column("status", media_asset_status, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_provider", sa.String(length=40), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_media_assets_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_media_assets_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_assets")),
        sa.UniqueConstraint("source_video_id", "asset_type", "version", name="uq_media_assets_video_type_version"),
        sa.UniqueConstraint("workspace_id", "storage_key", name="uq_media_assets_workspace_storage_key"),
    )
    op.create_index(op.f("ix_media_assets_asset_type"), "media_assets", ["asset_type"])
    op.create_index(op.f("ix_media_assets_source_video_id"), "media_assets", ["source_video_id"])
    op.create_index(op.f("ix_media_assets_status"), "media_assets", ["status"])
    op.create_index(op.f("ix_media_assets_workspace_id"), "media_assets", ["workspace_id"])

    op.create_table(
        "risk_flags",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("flag_type", risk_flag_type, nullable=False),
        sa.Column("severity", risk_severity, nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_risk_flags_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_risk_flags_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_risk_flags")),
    )
    op.create_index(op.f("ix_risk_flags_flag_type"), "risk_flags", ["flag_type"])
    op.create_index(op.f("ix_risk_flags_severity"), "risk_flags", ["severity"])
    op.create_index(op.f("ix_risk_flags_source_video_id"), "risk_flags", ["source_video_id"])
    op.create_index(op.f("ix_risk_flags_status"), "risk_flags", ["status"])
    op.create_index(op.f("ix_risk_flags_workspace_id"), "risk_flags", ["workspace_id"])

    op.create_table(
        "transcript_segments",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("status", transcript_segment_status, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_transcript_segments_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_transcript_segments_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcript_segments")),
        sa.UniqueConstraint("source_video_id", "segment_index", "version", name="uq_transcript_segments_video_index_version"),
    )
    op.create_index(op.f("ix_transcript_segments_source_video_id"), "transcript_segments", ["source_video_id"])
    op.create_index(op.f("ix_transcript_segments_status"), "transcript_segments", ["status"])
    op.create_index(op.f("ix_transcript_segments_workspace_id"), "transcript_segments", ["workspace_id"])

    op.create_table(
        "video_review_decisions",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("video_candidate_id", sa.Uuid(), nullable=False),
        sa.Column("status", review_decision_status, nullable=False),
        sa.Column("reviewer_label", sa.String(length=120), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("checkpoint", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["video_candidate_id"], ["video_candidates.id"], name=op.f("fk_video_review_decisions_video_candidate_id_video_candidates")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_video_review_decisions_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_video_review_decisions")),
    )
    op.create_index(op.f("ix_video_review_decisions_status"), "video_review_decisions", ["status"])
    op.create_index(op.f("ix_video_review_decisions_video_candidate_id"), "video_review_decisions", ["video_candidate_id"])
    op.create_index(op.f("ix_video_review_decisions_workspace_id"), "video_review_decisions", ["workspace_id"])

    op.create_table(
        "ocr_text_objects",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("status", ocr_object_status, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("first_seen_ms", sa.Integer(), nullable=True),
        sa.Column("last_seen_ms", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_ocr_text_objects_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_ocr_text_objects_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ocr_text_objects")),
    )
    op.create_index(op.f("ix_ocr_text_objects_source_video_id"), "ocr_text_objects", ["source_video_id"])
    op.create_index(op.f("ix_ocr_text_objects_status"), "ocr_text_objects", ["status"])
    op.create_index(op.f("ix_ocr_text_objects_workspace_id"), "ocr_text_objects", ["workspace_id"])

    op.create_table(
        "render_outputs",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("media_asset_id", sa.Uuid(), nullable=True),
        sa.Column("status", render_output_status, nullable=False),
        sa.Column("target_platform", sa.String(length=80), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("render_settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["media_asset_id"], ["media_assets.id"], name=op.f("fk_render_outputs_media_asset_id_media_assets")),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_render_outputs_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_render_outputs_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_render_outputs")),
    )
    op.create_index(op.f("ix_render_outputs_media_asset_id"), "render_outputs", ["media_asset_id"])
    op.create_index(op.f("ix_render_outputs_source_video_id"), "render_outputs", ["source_video_id"])
    op.create_index(op.f("ix_render_outputs_status"), "render_outputs", ["status"])
    op.create_index(op.f("ix_render_outputs_target_platform"), "render_outputs", ["target_platform"])
    op.create_index(op.f("ix_render_outputs_workspace_id"), "render_outputs", ["workspace_id"])

    op.create_table(
        "translation_segments",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("transcript_segment_id", sa.Uuid(), nullable=False),
        sa.Column("language_code", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", transcript_segment_status, nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_translation_segments_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["transcript_segment_id"], ["transcript_segments.id"], name=op.f("fk_translation_segments_transcript_segment_id_transcript_segments")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_translation_segments_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_translation_segments")),
        sa.UniqueConstraint("transcript_segment_id", "language_code", "version", name="uq_translation_segments_transcript_language_version"),
    )
    op.create_index(op.f("ix_translation_segments_source_video_id"), "translation_segments", ["source_video_id"])
    op.create_index(op.f("ix_translation_segments_status"), "translation_segments", ["status"])
    op.create_index(op.f("ix_translation_segments_transcript_segment_id"), "translation_segments", ["transcript_segment_id"])
    op.create_index(op.f("ix_translation_segments_workspace_id"), "translation_segments", ["workspace_id"])

    op.create_table(
        "jobs",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", job_type, nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=True),
        sa.Column("crawl_session_id", sa.Uuid(), nullable=True),
        sa.Column("render_output_id", sa.Uuid(), nullable=True),
        sa.Column("reference_type", sa.String(length=80), nullable=True),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=240), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=160), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["crawl_session_id"], ["crawl_sessions.id"], name=op.f("fk_jobs_crawl_session_id_crawl_sessions")),
        sa.ForeignKeyConstraint(["render_output_id"], ["render_outputs.id"], name=op.f("fk_jobs_render_output_id_render_outputs")),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_jobs_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_jobs_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_jobs_workspace_idempotency_key"),
    )
    op.create_index(op.f("ix_jobs_crawl_session_id"), "jobs", ["crawl_session_id"])
    op.create_index(op.f("ix_jobs_job_type"), "jobs", ["job_type"])
    op.create_index(op.f("ix_jobs_reference_id"), "jobs", ["reference_id"])
    op.create_index(op.f("ix_jobs_render_output_id"), "jobs", ["render_output_id"])
    op.create_index(op.f("ix_jobs_scheduled_at"), "jobs", ["scheduled_at"])
    op.create_index(op.f("ix_jobs_source_video_id"), "jobs", ["source_video_id"])
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"])
    op.create_index(op.f("ix_jobs_workspace_id"), "jobs", ["workspace_id"])

    op.create_table(
        "ocr_frame_detections",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("ocr_text_object_id", sa.Uuid(), nullable=False),
        sa.Column("frame_time_ms", sa.Integer(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["ocr_text_object_id"], ["ocr_text_objects.id"], name=op.f("fk_ocr_frame_detections_ocr_text_object_id_ocr_text_objects")),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_ocr_frame_detections_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_ocr_frame_detections_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ocr_frame_detections")),
    )
    op.create_index(op.f("ix_ocr_frame_detections_ocr_text_object_id"), "ocr_frame_detections", ["ocr_text_object_id"])
    op.create_index(op.f("ix_ocr_frame_detections_source_video_id"), "ocr_frame_detections", ["source_video_id"])
    op.create_index(op.f("ix_ocr_frame_detections_workspace_id"), "ocr_frame_detections", ["workspace_id"])

    op.create_table(
        "publish_drafts",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("render_output_id", sa.Uuid(), nullable=True),
        sa.Column("target_platform", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", publish_draft_status, nullable=False),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("hashtags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("platform_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["render_output_id"], ["render_outputs.id"], name=op.f("fk_publish_drafts_render_output_id_render_outputs")),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_publish_drafts_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_publish_drafts_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publish_drafts")),
        sa.UniqueConstraint("source_video_id", "target_platform", "version", name="uq_publish_drafts_video_platform_version"),
    )
    op.create_index(op.f("ix_publish_drafts_render_output_id"), "publish_drafts", ["render_output_id"])
    op.create_index(op.f("ix_publish_drafts_source_video_id"), "publish_drafts", ["source_video_id"])
    op.create_index(op.f("ix_publish_drafts_status"), "publish_drafts", ["status"])
    op.create_index(op.f("ix_publish_drafts_target_platform"), "publish_drafts", ["target_platform"])
    op.create_index(op.f("ix_publish_drafts_workspace_id"), "publish_drafts", ["workspace_id"])

    op.create_table(
        "subtitle_segments",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("translation_segment_id", sa.Uuid(), nullable=True),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", transcript_segment_status, nullable=False),
        sa.Column("style_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_subtitle_segments_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["translation_segment_id"], ["translation_segments.id"], name=op.f("fk_subtitle_segments_translation_segment_id_translation_segments")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_subtitle_segments_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subtitle_segments")),
        sa.UniqueConstraint("source_video_id", "segment_index", "version", name="uq_subtitle_segments_video_index_version"),
    )
    op.create_index(op.f("ix_subtitle_segments_source_video_id"), "subtitle_segments", ["source_video_id"])
    op.create_index(op.f("ix_subtitle_segments_status"), "subtitle_segments", ["status"])
    op.create_index(op.f("ix_subtitle_segments_translation_segment_id"), "subtitle_segments", ["translation_segment_id"])
    op.create_index(op.f("ix_subtitle_segments_workspace_id"), "subtitle_segments", ["workspace_id"])

    op.create_table(
        "job_steps",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("step_key", sa.String(length=120), nullable=False),
        sa.Column("step_name", sa.String(length=180), nullable=False),
        sa.Column("status", job_step_status, nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_job_steps_job_id_jobs")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_job_steps_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_steps")),
        sa.UniqueConstraint("job_id", "step_key", name="uq_job_steps_job_step_key"),
    )
    op.create_index(op.f("ix_job_steps_job_id"), "job_steps", ["job_id"])
    op.create_index(op.f("ix_job_steps_status"), "job_steps", ["status"])
    op.create_index(op.f("ix_job_steps_workspace_id"), "job_steps", ["workspace_id"])


def downgrade() -> None:
    for table_name in (
        "job_steps",
        "subtitle_segments",
        "publish_drafts",
        "ocr_frame_detections",
        "jobs",
        "translation_segments",
        "render_outputs",
        "ocr_text_objects",
        "video_review_decisions",
        "transcript_segments",
        "risk_flags",
        "media_assets",
        "video_candidates",
        "video_metric_snapshots",
        "source_videos",
        "crawl_sessions",
        "source_profiles",
        "workflow_templates",
        "niche_tags",
        "workspaces",
    ):
        op.drop_table(table_name)
    drop_enums()
