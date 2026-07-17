"""tts subtitle render prep foundation

Revision ID: 0007_tts_prep
Revises: 0006_audio
Create Date: 2026-04-17 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_tts_prep"
down_revision: str | None = "0006_audio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_MEDIA_TYPES = (
    "SOURCE_VIDEO",
    "SOURCE_VIDEO_RAW",
    "SOURCE_VIDEO_PREVIEW",
    "SOURCE_AUDIO",
    "SOURCE_AUDIO_EXTRACT",
    "AUDIO_VOCAL_STEM",
    "AUDIO_BACKGROUND_STEM",
    "AUDIO_ANALYSIS_METADATA",
    "THUMBNAIL",
    "METADATA_JSON",
    "SOURCE_CAPTION_RAW",
    "TRANSCRIPT_JSON",
    "TRANSLATION_DRAFT_JSON",
    "TRANSCRIPT",
    "TRANSLATION",
    "SUBTITLE",
    "OCR_FRAME",
    "TEMP_FILE",
    "RENDER_OUTPUT",
    "RENDERED_VIDEO",
    "EXPORT_PACKAGE",
)

NEW_MEDIA_TYPES = (
    "SOURCE_VIDEO",
    "SOURCE_VIDEO_RAW",
    "SOURCE_VIDEO_PREVIEW",
    "SOURCE_AUDIO",
    "SOURCE_AUDIO_EXTRACT",
    "AUDIO_VOCAL_STEM",
    "AUDIO_BACKGROUND_STEM",
    "AUDIO_ANALYSIS_METADATA",
    "THUMBNAIL",
    "METADATA_JSON",
    "SOURCE_CAPTION_RAW",
    "TRANSCRIPT_JSON",
    "TRANSLATION_DRAFT_JSON",
    "TTS_AUDIO_CLIP",
    "TTS_AUDIO_JOINED",
    "SUBTITLE_JSON",
    "SUBTITLE_SRT",
    "SUBTITLE_ASS",
    "RENDER_PREP_MANIFEST",
    "TRANSCRIPT",
    "TRANSLATION",
    "SUBTITLE",
    "OCR_FRAME",
    "TEMP_FILE",
    "RENDER_OUTPUT",
    "RENDERED_VIDEO",
    "EXPORT_PACKAGE",
)


def replace_media_asset_type(values: tuple[str, ...], using_sql: str) -> None:
    temp_type_name = "media_asset_type_v4"
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
    op.add_column("subtitle_segments", sa.Column("layout_mode", sa.String(length=80), nullable=True))
    op.add_column("subtitle_segments", sa.Column("track_kind", sa.String(length=80), nullable=True))
    op.add_column("subtitle_segments", sa.Column("review_flags_json", postgresql.JSONB(), nullable=True))
    op.add_column("subtitle_segments", sa.Column("subtitle_version", sa.String(length=80), nullable=True))
    op.add_column("subtitle_segments", sa.Column("created_by_job_id", sa.Uuid(), nullable=True))
    op.add_column("subtitle_segments", sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.create_foreign_key(
        op.f("fk_subtitle_segments_created_by_job_id_jobs"),
        "subtitle_segments",
        "jobs",
        ["created_by_job_id"],
        ["id"],
    )
    op.create_index(op.f("ix_subtitle_segments_layout_mode"), "subtitle_segments", ["layout_mode"])
    op.create_index(op.f("ix_subtitle_segments_track_kind"), "subtitle_segments", ["track_kind"])
    op.create_index(op.f("ix_subtitle_segments_subtitle_version"), "subtitle_segments", ["subtitle_version"])
    op.create_index(op.f("ix_subtitle_segments_created_by_job_id"), "subtitle_segments", ["created_by_job_id"])
    op.create_index(op.f("ix_subtitle_segments_is_current"), "subtitle_segments", ["is_current"])


def downgrade() -> None:
    op.drop_index(op.f("ix_subtitle_segments_is_current"), table_name="subtitle_segments")
    op.drop_index(op.f("ix_subtitle_segments_created_by_job_id"), table_name="subtitle_segments")
    op.drop_index(op.f("ix_subtitle_segments_subtitle_version"), table_name="subtitle_segments")
    op.drop_index(op.f("ix_subtitle_segments_track_kind"), table_name="subtitle_segments")
    op.drop_index(op.f("ix_subtitle_segments_layout_mode"), table_name="subtitle_segments")
    op.drop_constraint(op.f("fk_subtitle_segments_created_by_job_id_jobs"), "subtitle_segments", type_="foreignkey")
    op.drop_column("subtitle_segments", "is_current")
    op.drop_column("subtitle_segments", "created_by_job_id")
    op.drop_column("subtitle_segments", "subtitle_version")
    op.drop_column("subtitle_segments", "review_flags_json")
    op.drop_column("subtitle_segments", "track_kind")
    op.drop_column("subtitle_segments", "layout_mode")
    replace_media_asset_type(
        OLD_MEDIA_TYPES,
        """
        CASE asset_type::text
            WHEN 'TTS_AUDIO_CLIP' THEN 'SOURCE_AUDIO'
            WHEN 'TTS_AUDIO_JOINED' THEN 'SOURCE_AUDIO'
            WHEN 'SUBTITLE_JSON' THEN 'SUBTITLE'
            WHEN 'SUBTITLE_SRT' THEN 'SUBTITLE'
            WHEN 'SUBTITLE_ASS' THEN 'SUBTITLE'
            WHEN 'RENDER_PREP_MANIFEST' THEN 'RENDER_OUTPUT'
            ELSE asset_type::text
        END
        """,
    )
