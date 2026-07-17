"""media download foundation fields

Revision ID: 0005_media
Revises: 0004_candidates
Create Date: 2026-04-17 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_media"
down_revision: str | None = "0004_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_MEDIA_TYPES = (
    "SOURCE_VIDEO",
    "SOURCE_AUDIO",
    "THUMBNAIL",
    "TRANSCRIPT",
    "TRANSLATION",
    "SUBTITLE",
    "OCR_FRAME",
    "RENDERED_VIDEO",
    "EXPORT_PACKAGE",
)

NEW_MEDIA_TYPES = (
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


def replace_media_asset_type(values: tuple[str, ...], using_sql: str) -> None:
    temp_type_name = "media_asset_type_v2"
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
    op.alter_column("media_assets", "size_bytes", type_=sa.BigInteger(), existing_type=sa.Integer())
    op.add_column("media_assets", sa.Column("logical_key", sa.Text(), nullable=True))
    op.add_column("media_assets", sa.Column("relative_path", sa.Text(), nullable=True))
    op.add_column("media_assets", sa.Column("manifest_group", sa.String(length=120), nullable=True))
    op.add_column("media_assets", sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("media_assets", sa.Column("created_by_job_id", sa.Uuid(), nullable=True))
    op.add_column("media_assets", sa.Column("source_url", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_media_assets_created_by_job_id_jobs"),
        "media_assets",
        "jobs",
        ["created_by_job_id"],
        ["id"],
    )
    op.create_index(op.f("ix_media_assets_logical_key"), "media_assets", ["logical_key"])
    op.create_index(op.f("ix_media_assets_manifest_group"), "media_assets", ["manifest_group"])
    op.create_index(op.f("ix_media_assets_is_current"), "media_assets", ["is_current"])
    op.create_index(op.f("ix_media_assets_created_by_job_id"), "media_assets", ["created_by_job_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_media_assets_created_by_job_id"), table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_is_current"), table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_manifest_group"), table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_logical_key"), table_name="media_assets")
    op.drop_constraint(op.f("fk_media_assets_created_by_job_id_jobs"), "media_assets", type_="foreignkey")
    op.drop_column("media_assets", "source_url")
    op.drop_column("media_assets", "created_by_job_id")
    op.drop_column("media_assets", "is_current")
    op.drop_column("media_assets", "manifest_group")
    op.drop_column("media_assets", "relative_path")
    op.drop_column("media_assets", "logical_key")
    op.alter_column("media_assets", "size_bytes", type_=sa.Integer(), existing_type=sa.BigInteger())
    replace_media_asset_type(
        OLD_MEDIA_TYPES,
        """
        CASE asset_type::text
            WHEN 'SOURCE_VIDEO_RAW' THEN 'SOURCE_VIDEO'
            WHEN 'SOURCE_VIDEO_PREVIEW' THEN 'SOURCE_VIDEO'
            WHEN 'SOURCE_AUDIO_EXTRACT' THEN 'SOURCE_AUDIO'
            WHEN 'METADATA_JSON' THEN 'TRANSCRIPT'
            WHEN 'SOURCE_CAPTION_RAW' THEN 'TRANSCRIPT'
            WHEN 'TEMP_FILE' THEN 'EXPORT_PACKAGE'
            WHEN 'RENDER_OUTPUT' THEN 'RENDERED_VIDEO'
            ELSE asset_type::text
        END
        """,
    )
