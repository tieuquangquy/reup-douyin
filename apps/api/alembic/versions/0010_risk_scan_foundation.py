"""risk scan foundation

Revision ID: 0010_risk
Revises: 0009_publish_prep
Create Date: 2026-04-17 00:00:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010_risk"
down_revision: str | None = "0009_publish_prep"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_RISK_TYPES = ("COPYRIGHT", "WATERMARK", "LOW_QUALITY", "DUPLICATE", "POLICY", "MANUAL_REVIEW")
NEW_RISK_TYPES = (
    "COPYRIGHT", "WATERMARK", "LOW_QUALITY", "DUPLICATE", "POLICY", "MANUAL_REVIEW",
    "AUDIO_COPYRIGHT_RISK", "WATERMARK_RISK", "BRAND_LOGO_RISK", "CELEBRITY_PERSONA_RISK",
    "OCR_DENSITY_RISK", "SPEECH_QUALITY_RISK", "PROCESSING_COMPLEXITY_RISK",
    "PLATFORM_POLICY_RISK", "MANUAL_REVIEW_REQUIRED",
)
OLD_SEVERITIES = ("LOW", "MEDIUM", "HIGH", "BLOCKING")
NEW_SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL", "BLOCKING")


def replace_enum(type_name: str, temp_name: str, values: tuple[str, ...], table: str, column: str, using_sql: str) -> None:
    enum_type = postgresql.ENUM(*values, name=temp_name)
    enum_type.create(op.get_bind(), checkfirst=True)
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {temp_name} USING ({using_sql})::{temp_name}")
    op.execute(f"DROP TYPE {type_name}")
    op.execute(f"ALTER TYPE {temp_name} RENAME TO {type_name}")


def upgrade() -> None:
    replace_enum("risk_flag_type", "risk_flag_type_v2", NEW_RISK_TYPES, "risk_flags", "flag_type", "flag_type::text")
    replace_enum("risk_severity", "risk_severity_v2", NEW_SEVERITIES, "risk_flags", "severity", "severity::text")

    risk_target_type = postgresql.ENUM("SOURCE_VIDEO", "RENDER_OUTPUT", "PUBLISH_DRAFT", name="risk_target_type", create_type=False)
    risk_target_type.create(op.get_bind(), checkfirst=True)
    risk_flag_status = postgresql.ENUM("OPEN", "ACKNOWLEDGED", "RESOLVED", "WAIVED", "REJECTED", name="risk_flag_status", create_type=False)
    risk_flag_status.create(op.get_bind(), checkfirst=True)
    operator_decision_type = postgresql.ENUM("CONTINUE", "NEEDS_FIX", "REJECT", "ACCEPT_WITH_WARNING", name="operator_risk_decision_type", create_type=False)
    operator_decision_type.create(op.get_bind(), checkfirst=True)

    op.add_column("risk_flags", sa.Column("target_type", risk_target_type, server_default="SOURCE_VIDEO", nullable=False))
    op.add_column("risk_flags", sa.Column("target_id", sa.Uuid(), nullable=True))
    op.add_column("risk_flags", sa.Column("scan_run_id", sa.Uuid(), nullable=True))
    op.add_column("risk_flags", sa.Column("title", sa.String(length=180), nullable=True))
    op.add_column("risk_flags", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("risk_flags", sa.Column("evidence_summary", sa.Text(), nullable=True))
    op.add_column("risk_flags", sa.Column("scan_source", sa.String(length=120), nullable=True))
    op.add_column("risk_flags", sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("risk_flags", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("risk_flags", sa.Column("resolution_note", sa.Text(), nullable=True))
    op.add_column("risk_flags", sa.Column("metadata_json", postgresql.JSONB(), nullable=True))
    op.add_column("risk_flags", sa.Column("status_v2", risk_flag_status, server_default="OPEN", nullable=False))
    op.execute("UPDATE risk_flags SET target_id = source_video_id")
    op.drop_column("risk_flags", "status")
    op.alter_column("risk_flags", "status_v2", new_column_name="status")
    for column in ["target_type", "target_id", "scan_run_id", "scan_source", "detected_at", "status"]:
        op.create_index(op.f(f"ix_risk_flags_{column}"), "risk_flags", [column])

    op.create_table(
        "operator_risk_decisions",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_video_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", risk_target_type, nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("decision_type", operator_decision_type, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gate_summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["source_video_id"], ["source_videos.id"], name=op.f("fk_operator_risk_decisions_source_video_id_source_videos")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_operator_risk_decisions_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operator_risk_decisions")),
    )
    for column in ["workspace_id", "source_video_id", "target_type", "target_id", "decision_type", "decided_at"]:
        op.create_index(op.f(f"ix_operator_risk_decisions_{column}"), "operator_risk_decisions", [column])


def downgrade() -> None:
    op.drop_table("operator_risk_decisions")
    for column in ["status", "detected_at", "scan_source", "scan_run_id", "target_id", "target_type"]:
        op.drop_index(op.f(f"ix_risk_flags_{column}"), table_name="risk_flags")
    op.add_column("risk_flags", sa.Column("status_old", sa.String(length=40), server_default="OPEN", nullable=False))
    op.drop_column("risk_flags", "status")
    op.alter_column("risk_flags", "status_old", new_column_name="status")
    for column in ["metadata_json", "resolution_note", "resolved_at", "detected_at", "scan_source", "evidence_summary", "description", "title", "scan_run_id", "target_id", "target_type"]:
        op.drop_column("risk_flags", column)
    postgresql.ENUM(name="operator_risk_decision_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="risk_flag_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="risk_target_type").drop(op.get_bind(), checkfirst=True)
    replace_enum("risk_severity", "risk_severity_v1", OLD_SEVERITIES, "risk_flags", "severity", "CASE severity::text WHEN 'CRITICAL' THEN 'BLOCKING' ELSE severity::text END")
    replace_enum("risk_flag_type", "risk_flag_type_v1", OLD_RISK_TYPES, "risk_flags", "flag_type", "CASE flag_type::text WHEN 'AUDIO_COPYRIGHT_RISK' THEN 'COPYRIGHT' WHEN 'WATERMARK_RISK' THEN 'WATERMARK' WHEN 'PLATFORM_POLICY_RISK' THEN 'POLICY' ELSE 'MANUAL_REVIEW' END")
