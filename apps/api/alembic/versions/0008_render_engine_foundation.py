"""render engine foundation

Revision ID: 0008_render
Revises: 0007_tts_prep
Create Date: 2026-04-17 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_render"
down_revision: str | None = "0007_tts_prep"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_MEDIA_TYPES = (
    "SOURCE_VIDEO", "SOURCE_VIDEO_RAW", "SOURCE_VIDEO_PREVIEW", "SOURCE_AUDIO", "SOURCE_AUDIO_EXTRACT",
    "AUDIO_VOCAL_STEM", "AUDIO_BACKGROUND_STEM", "AUDIO_ANALYSIS_METADATA", "THUMBNAIL", "METADATA_JSON",
    "SOURCE_CAPTION_RAW", "TRANSCRIPT_JSON", "TRANSLATION_DRAFT_JSON", "TTS_AUDIO_CLIP", "TTS_AUDIO_JOINED",
    "SUBTITLE_JSON", "SUBTITLE_SRT", "SUBTITLE_ASS", "RENDER_PREP_MANIFEST", "TRANSCRIPT", "TRANSLATION",
    "SUBTITLE", "OCR_FRAME", "TEMP_FILE", "RENDER_OUTPUT", "RENDERED_VIDEO", "EXPORT_PACKAGE",
)

NEW_MEDIA_TYPES = (
    "SOURCE_VIDEO", "SOURCE_VIDEO_RAW", "SOURCE_VIDEO_PREVIEW", "SOURCE_AUDIO", "SOURCE_AUDIO_EXTRACT",
    "AUDIO_VOCAL_STEM", "AUDIO_BACKGROUND_STEM", "AUDIO_ANALYSIS_METADATA", "THUMBNAIL", "METADATA_JSON",
    "SOURCE_CAPTION_RAW", "TRANSCRIPT_JSON", "TRANSLATION_DRAFT_JSON", "TTS_AUDIO_CLIP", "TTS_AUDIO_JOINED",
    "SUBTITLE_JSON", "SUBTITLE_SRT", "SUBTITLE_ASS", "RENDER_PREP_MANIFEST", "FINAL_RENDER_VIDEO",
    "RENDER_LOG", "RENDER_DEBUG_JSON", "RENDER_MANIFEST", "TRANSCRIPT", "TRANSLATION", "SUBTITLE",
    "OCR_FRAME", "TEMP_FILE", "RENDER_OUTPUT", "RENDERED_VIDEO", "EXPORT_PACKAGE",
)


def replace_media_asset_type(values: tuple[str, ...], using_sql: str) -> None:
    temp_type_name = "media_asset_type_v5"
    enum_type = postgresql.ENUM(*values, name=temp_type_name)
    enum_type.create(op.get_bind(), checkfirst=True)
    op.execute(
        "ALTER TABLE media_assets ALTER COLUMN asset_type "
        f"TYPE {temp_type_name} USING ({using_sql})::{temp_type_name}"
    )
    op.execute("DROP TYPE media_asset_type")
    op.execute(f"ALTER TYPE {temp_type_name} RENAME TO media_asset_type")


def upgrade() -> None:
    replace_media_asset_type(NEW_MEDIA_TYPES, "asset_type::text")
    op.add_column("render_outputs", sa.Column("render_type", sa.String(length=80), nullable=True))
    op.add_column("render_outputs", sa.Column("output_format", sa.String(length=40), nullable=True))
    op.add_column("render_outputs", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("render_outputs", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("render_outputs", sa.Column("fps", sa.Float(), nullable=True))
    op.add_column("render_outputs", sa.Column("duration_seconds", sa.Float(), nullable=True))
    op.add_column("render_outputs", sa.Column("video_codec", sa.String(length=80), nullable=True))
    op.add_column("render_outputs", sa.Column("audio_codec", sa.String(length=80), nullable=True))
    op.add_column("render_outputs", sa.Column("subtitle_burned", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("render_outputs", sa.Column("audio_strategy", sa.String(length=120), nullable=True))
    op.add_column("render_outputs", sa.Column("render_version", sa.String(length=80), nullable=True))
    op.add_column("render_outputs", sa.Column("created_by_job_id", sa.Uuid(), nullable=True))
    op.add_column("render_outputs", sa.Column("warning_summary_json", postgresql.JSONB(), nullable=True))
    op.add_column("render_outputs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("render_outputs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(op.f("fk_render_outputs_created_by_job_id_jobs"), "render_outputs", "jobs", ["created_by_job_id"], ["id"])
    op.create_index(op.f("ix_render_outputs_render_type"), "render_outputs", ["render_type"])
    op.create_index(op.f("ix_render_outputs_audio_strategy"), "render_outputs", ["audio_strategy"])
    op.create_index(op.f("ix_render_outputs_render_version"), "render_outputs", ["render_version"])
    op.create_index(op.f("ix_render_outputs_created_by_job_id"), "render_outputs", ["created_by_job_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_render_outputs_created_by_job_id"), table_name="render_outputs")
    op.drop_index(op.f("ix_render_outputs_render_version"), table_name="render_outputs")
    op.drop_index(op.f("ix_render_outputs_audio_strategy"), table_name="render_outputs")
    op.drop_index(op.f("ix_render_outputs_render_type"), table_name="render_outputs")
    op.drop_constraint(op.f("fk_render_outputs_created_by_job_id_jobs"), "render_outputs", type_="foreignkey")
    for column in [
        "finished_at", "started_at", "warning_summary_json", "created_by_job_id", "render_version",
        "audio_strategy", "subtitle_burned", "audio_codec", "video_codec", "duration_seconds",
        "fps", "height", "width", "output_format", "render_type",
    ]:
        op.drop_column("render_outputs", column)
    replace_media_asset_type(
        OLD_MEDIA_TYPES,
        """
        CASE asset_type::text
            WHEN 'FINAL_RENDER_VIDEO' THEN 'RENDERED_VIDEO'
            WHEN 'RENDER_LOG' THEN 'RENDER_OUTPUT'
            WHEN 'RENDER_DEBUG_JSON' THEN 'RENDER_OUTPUT'
            WHEN 'RENDER_MANIFEST' THEN 'RENDER_OUTPUT'
            ELSE asset_type::text
        END
        """,
    )
