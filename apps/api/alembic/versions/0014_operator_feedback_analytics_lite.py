"""operator feedback analytics lite

Revision ID: 0014_feedback
Revises: 0013_pub_jobs
Create Date: 2026-04-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0014_feedback"
down_revision: str | None = "0013_pub_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    target_type = postgresql.ENUM(
        "SOURCE_VIDEO",
        "RENDER_OUTPUT",
        "PUBLISH_DRAFT",
        "PUBLISH_ATTEMPT",
        name="operator_feedback_target_type",
        create_type=False,
    )
    quality_label = postgresql.ENUM("GOOD", "ACCEPTABLE", "WEAK", name="operator_feedback_quality_label", create_type=False)
    confidence_label = postgresql.ENUM(
        "SCALABLE",
        "NEEDS_IMPROVEMENT",
        "DO_NOT_REUSE_PATTERN",
        name="publish_confidence_label",
        create_type=False,
    )
    root_cause = postgresql.ENUM(
        "SOURCE_SELECTION_ISSUE",
        "TRANSCRIPT_QUALITY_ISSUE",
        "TTS_ISSUE",
        "SUBTITLE_ISSUE",
        "RENDER_ISSUE",
        "PUBLISH_ISSUE",
        "RISK_FALSE_POSITIVE",
        "CTA_CAPTION_ISSUE",
        "OTHER",
        name="operator_feedback_root_cause",
        create_type=False,
    )
    for enum_type in [target_type, quality_label, confidence_label, root_cause]:
        enum_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "operator_feedback",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", target_type, nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=True),
        sa.Column("render_output_id", sa.Uuid(), nullable=True),
        sa.Column("publish_draft_id", sa.Uuid(), nullable=True),
        sa.Column("publish_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("quality_label", quality_label, nullable=False),
        sa.Column("publish_confidence", confidence_label, nullable=False),
        sa.Column("root_cause", root_cause, nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["publish_attempt_id"], ["publish_attempts.id"], name=op.f("fk_operator_feedback_publish_attempt_id_publish_attempts")),
        sa.ForeignKeyConstraint(["publish_draft_id"], ["publish_drafts.id"], name=op.f("fk_operator_feedback_publish_draft_id_publish_drafts")),
        sa.ForeignKeyConstraint(["render_output_id"], ["render_outputs.id"], name=op.f("fk_operator_feedback_render_output_id_render_outputs")),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_operator_feedback_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_operator_feedback_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operator_feedback")),
    )
    for column in [
        "workspace_id",
        "target_type",
        "target_id",
        "source_video_id",
        "render_output_id",
        "publish_draft_id",
        "publish_attempt_id",
        "quality_label",
        "publish_confidence",
        "root_cause",
        "feedback_at",
    ]:
        op.create_index(op.f(f"ix_operator_feedback_{column}"), "operator_feedback", [column])


def downgrade() -> None:
    op.drop_table("operator_feedback")
    for enum_name in [
        "operator_feedback_root_cause",
        "publish_confidence_label",
        "operator_feedback_quality_label",
        "operator_feedback_target_type",
    ]:
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)
