"""job orchestration foundation

Revision ID: 0002_jobs
Revises: 0001_initial
Create Date: 2026-04-17 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_jobs"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_JOB_TYPES = (
    "CRAWL_PROFILE",
    "SCORE_CANDIDATES",
    "DOWNLOAD_VIDEO",
    "ANALYZE_AUDIO",
    "ANALYZE_OCR",
    "BUILD_TRANSLATION_DRAFT",
    "SYNTHESIZE_TTS",
    "RENDER_PREVIEW",
    "RENDER_FINAL",
)

NEW_STEP_STATUSES = (
    "PENDING",
    "RUNNING",
    "WAITING_FOR_INPUT",
    "FAILED",
    "SKIPPED",
    "COMPLETED",
)

OLD_JOB_TYPES = (
    "CRAWL_PROFILE",
    "DOWNLOAD_VIDEO",
    "ANALYZE_VIDEO",
    "OCR_VIDEO",
    "TRANSCRIBE_AUDIO",
    "TRANSLATE_TRANSCRIPT",
    "RENDER_VIDEO",
    "EXPORT_VIDEO",
    "PREPARE_PUBLISH",
)

OLD_STEP_STATUSES = (
    "QUEUED",
    "RUNNING",
    "WAITING_FOR_REVIEW",
    "FAILED",
    "RETRYABLE",
    "CANCELLED",
    "COMPLETED",
)


def replace_enum_type(table_name: str, column_name: str, type_name: str, values: tuple[str, ...], using_sql: str) -> None:
    temp_type_name = f"{type_name}_v2"
    enum_type = postgresql.ENUM(*values, name=temp_type_name)
    enum_type.create(op.get_bind(), checkfirst=True)
    op.execute(
        f"ALTER TABLE {table_name} ALTER COLUMN {column_name} "
        f"TYPE {temp_type_name} USING ({using_sql})::{temp_type_name}"
    )
    op.execute(f"DROP TYPE {type_name}")
    op.execute(f"ALTER TYPE {temp_type_name} RENAME TO {type_name}")


def upgrade() -> None:
    replace_enum_type(
        "jobs",
        "job_type",
        "job_type",
        NEW_JOB_TYPES,
        """
        CASE job_type::text
            WHEN 'ANALYZE_VIDEO' THEN 'ANALYZE_AUDIO'
            WHEN 'OCR_VIDEO' THEN 'ANALYZE_OCR'
            WHEN 'TRANSCRIBE_AUDIO' THEN 'ANALYZE_AUDIO'
            WHEN 'TRANSLATE_TRANSCRIPT' THEN 'BUILD_TRANSLATION_DRAFT'
            WHEN 'RENDER_VIDEO' THEN 'RENDER_FINAL'
            WHEN 'EXPORT_VIDEO' THEN 'RENDER_FINAL'
            WHEN 'PREPARE_PUBLISH' THEN 'RENDER_FINAL'
            ELSE job_type::text
        END
        """,
    )
    replace_enum_type(
        "job_steps",
        "status",
        "job_step_status",
        NEW_STEP_STATUSES,
        """
        CASE status::text
            WHEN 'QUEUED' THEN 'PENDING'
            WHEN 'WAITING_FOR_REVIEW' THEN 'WAITING_FOR_INPUT'
            WHEN 'RETRYABLE' THEN 'FAILED'
            WHEN 'CANCELLED' THEN 'SKIPPED'
            ELSE status::text
        END
        """,
    )

    op.add_column("jobs", sa.Column("current_step_key", sa.String(length=120), nullable=True))
    op.add_column("jobs", sa.Column("current_step_index", sa.Integer(), server_default="0", nullable=False))
    op.add_column("jobs", sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False))
    op.add_column("jobs", sa.Column("total_steps", sa.Integer(), server_default="0", nullable=False))
    op.add_column("jobs", sa.Column("completed_steps", sa.Integer(), server_default="0", nullable=False))
    op.add_column("jobs", sa.Column("failed_steps", sa.Integer(), server_default="0", nullable=False))
    op.add_column("jobs", sa.Column("retryable", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("jobs", sa.Column("error_code", sa.String(length=120), nullable=True))
    op.add_column("jobs", sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("jobs", sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index(op.f("ix_jobs_current_step_key"), "jobs", ["current_step_key"])

    op.add_column("job_steps", sa.Column("step_order", sa.Integer(), server_default="0", nullable=False))
    op.add_column("job_steps", sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False))
    op.add_column("job_steps", sa.Column("error_code", sa.String(length=120), nullable=True))
    op.add_column("job_steps", sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.execute("UPDATE job_steps SET step_order = sequence_index")


def downgrade() -> None:
    op.drop_column("job_steps", "output_json")
    op.drop_column("job_steps", "error_code")
    op.drop_column("job_steps", "progress_percent")
    op.drop_column("job_steps", "step_order")

    op.drop_index(op.f("ix_jobs_current_step_key"), table_name="jobs")
    op.drop_column("jobs", "context_json")
    op.drop_column("jobs", "payload_json")
    op.drop_column("jobs", "error_code")
    op.drop_column("jobs", "retryable")
    op.drop_column("jobs", "failed_steps")
    op.drop_column("jobs", "completed_steps")
    op.drop_column("jobs", "total_steps")
    op.drop_column("jobs", "progress_percent")
    op.drop_column("jobs", "current_step_index")
    op.drop_column("jobs", "current_step_key")

    replace_enum_type(
        "job_steps",
        "status",
        "job_step_status",
        OLD_STEP_STATUSES,
        """
        CASE status::text
            WHEN 'PENDING' THEN 'QUEUED'
            WHEN 'WAITING_FOR_INPUT' THEN 'WAITING_FOR_REVIEW'
            WHEN 'SKIPPED' THEN 'CANCELLED'
            ELSE status::text
        END
        """,
    )
    replace_enum_type(
        "jobs",
        "job_type",
        "job_type",
        OLD_JOB_TYPES,
        """
        CASE job_type::text
            WHEN 'SCORE_CANDIDATES' THEN 'ANALYZE_VIDEO'
            WHEN 'ANALYZE_AUDIO' THEN 'TRANSCRIBE_AUDIO'
            WHEN 'ANALYZE_OCR' THEN 'OCR_VIDEO'
            WHEN 'BUILD_TRANSLATION_DRAFT' THEN 'TRANSLATE_TRANSCRIPT'
            WHEN 'SYNTHESIZE_TTS' THEN 'ANALYZE_VIDEO'
            WHEN 'RENDER_PREVIEW' THEN 'RENDER_VIDEO'
            WHEN 'RENDER_FINAL' THEN 'RENDER_VIDEO'
            ELSE job_type::text
        END
        """,
    )
