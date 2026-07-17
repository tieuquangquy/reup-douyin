"""audio analysis foundation

Revision ID: 0006_audio
Revises: 0005_media
Create Date: 2026-04-17 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_audio"
down_revision: str | None = "0005_media"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_MEDIA_TYPES = (
    "SOURCE_VIDEO",
    "SOURCE_VIDEO_RAW",
    "SOURCE_VIDEO_PREVIEW",
    "SOURCE_AUDIO",
    "SOURCE_AUDIO_EXTRACT",
    "THUMBNAIL",
    "METADATA_JSON",
    "SOURCE_CAPTION_RAW",
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
    temp_type_name = "media_asset_type_v3"
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

    op.add_column("transcript_segments", sa.Column("normalized_text", sa.Text(), nullable=True))
    op.add_column("transcript_segments", sa.Column("speaker_label", sa.String(length=80), nullable=True))
    op.add_column("transcript_segments", sa.Column("difficulty_flags_json", postgresql.JSONB(), nullable=True))
    op.add_column("transcript_segments", sa.Column("analysis_version", sa.String(length=80), nullable=True))
    op.add_column("transcript_segments", sa.Column("created_by_job_id", sa.Uuid(), nullable=True))
    op.add_column("transcript_segments", sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.create_foreign_key(
        op.f("fk_transcript_segments_created_by_job_id_jobs"),
        "transcript_segments",
        "jobs",
        ["created_by_job_id"],
        ["id"],
    )
    op.create_index(op.f("ix_transcript_segments_analysis_version"), "transcript_segments", ["analysis_version"])
    op.create_index(op.f("ix_transcript_segments_created_by_job_id"), "transcript_segments", ["created_by_job_id"])
    op.create_index(op.f("ix_transcript_segments_is_current"), "transcript_segments", ["is_current"])

    op.add_column("translation_segments", sa.Column("segment_index", sa.Integer(), nullable=True))
    op.add_column("translation_segments", sa.Column("translation_preset", sa.String(length=80), nullable=True))
    op.add_column("translation_segments", sa.Column("duration_budget_ms", sa.Integer(), nullable=True))
    op.add_column("translation_segments", sa.Column("estimated_tts_duration_ms", sa.Integer(), nullable=True))
    op.add_column("translation_segments", sa.Column("quality_flags_json", postgresql.JSONB(), nullable=True))
    op.add_column("translation_segments", sa.Column("created_by_job_id", sa.Uuid(), nullable=True))
    op.add_column("translation_segments", sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.create_foreign_key(
        op.f("fk_translation_segments_created_by_job_id_jobs"),
        "translation_segments",
        "jobs",
        ["created_by_job_id"],
        ["id"],
    )
    op.create_index(op.f("ix_translation_segments_segment_index"), "translation_segments", ["segment_index"])
    op.create_index(op.f("ix_translation_segments_translation_preset"), "translation_segments", ["translation_preset"])
    op.create_index(op.f("ix_translation_segments_created_by_job_id"), "translation_segments", ["created_by_job_id"])
    op.create_index(op.f("ix_translation_segments_is_current"), "translation_segments", ["is_current"])


def downgrade() -> None:
    op.drop_index(op.f("ix_translation_segments_is_current"), table_name="translation_segments")
    op.drop_index(op.f("ix_translation_segments_created_by_job_id"), table_name="translation_segments")
    op.drop_index(op.f("ix_translation_segments_translation_preset"), table_name="translation_segments")
    op.drop_index(op.f("ix_translation_segments_segment_index"), table_name="translation_segments")
    op.drop_constraint(op.f("fk_translation_segments_created_by_job_id_jobs"), "translation_segments", type_="foreignkey")
    op.drop_column("translation_segments", "is_current")
    op.drop_column("translation_segments", "created_by_job_id")
    op.drop_column("translation_segments", "quality_flags_json")
    op.drop_column("translation_segments", "estimated_tts_duration_ms")
    op.drop_column("translation_segments", "duration_budget_ms")
    op.drop_column("translation_segments", "translation_preset")
    op.drop_column("translation_segments", "segment_index")

    op.drop_index(op.f("ix_transcript_segments_is_current"), table_name="transcript_segments")
    op.drop_index(op.f("ix_transcript_segments_created_by_job_id"), table_name="transcript_segments")
    op.drop_index(op.f("ix_transcript_segments_analysis_version"), table_name="transcript_segments")
    op.drop_constraint(op.f("fk_transcript_segments_created_by_job_id_jobs"), "transcript_segments", type_="foreignkey")
    op.drop_column("transcript_segments", "is_current")
    op.drop_column("transcript_segments", "created_by_job_id")
    op.drop_column("transcript_segments", "analysis_version")
    op.drop_column("transcript_segments", "difficulty_flags_json")
    op.drop_column("transcript_segments", "speaker_label")
    op.drop_column("transcript_segments", "normalized_text")

    replace_media_asset_type(
        OLD_MEDIA_TYPES,
        """
        CASE asset_type::text
            WHEN 'AUDIO_VOCAL_STEM' THEN 'SOURCE_AUDIO_EXTRACT'
            WHEN 'AUDIO_BACKGROUND_STEM' THEN 'SOURCE_AUDIO_EXTRACT'
            WHEN 'AUDIO_ANALYSIS_METADATA' THEN 'METADATA_JSON'
            WHEN 'TRANSCRIPT_JSON' THEN 'TRANSCRIPT'
            WHEN 'TRANSLATION_DRAFT_JSON' THEN 'TRANSLATION'
            ELSE asset_type::text
        END
        """,
    )
