"""publish multi account routing

Revision ID: 0015_multi_account
Revises: 0014_feedback
Create Date: 2026-04-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0015_multi_account"
down_revision: str | None = "0014_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    assignment_status = postgresql.ENUM("UNASSIGNED", "ASSIGNED", "OVERRIDDEN", name="publish_account_assignment_status", create_type=False)
    routing_rule_status = postgresql.ENUM("ACTIVE", "PAUSED", "ARCHIVED", name="publish_routing_rule_status", create_type=False)
    assignment_status.create(op.get_bind(), checkfirst=True)
    routing_rule_status.create(op.get_bind(), checkfirst=True)

    op.add_column("platform_accounts", sa.Column("priority", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("platform_accounts", sa.Column("is_on_hold", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("platform_accounts", sa.Column("hold_reason", sa.Text(), nullable=True))
    op.add_column("platform_accounts", sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("platform_accounts", sa.Column("allowed_niches_json", postgresql.JSONB(), nullable=True))
    op.add_column("platform_accounts", sa.Column("routing_notes", sa.Text(), nullable=True))
    for column in ["priority", "is_on_hold", "cooldown_until"]:
        op.create_index(op.f(f"ix_platform_accounts_{column}"), "platform_accounts", [column])

    op.add_column("publish_drafts", sa.Column("assigned_platform_account_id", sa.Uuid(), nullable=True))
    op.add_column("publish_drafts", sa.Column("assignment_status", assignment_status, nullable=False, server_default="UNASSIGNED"))
    op.add_column("publish_drafts", sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_drafts", sa.Column("assigned_reason", sa.Text(), nullable=True))
    op.add_column("publish_drafts", sa.Column("assigned_by", sa.String(length=120), nullable=True))
    op.add_column("publish_drafts", sa.Column("assignment_metadata_json", postgresql.JSONB(), nullable=True))
    op.create_foreign_key(
        op.f("fk_publish_drafts_assigned_platform_account_id_platform_accounts"),
        "publish_drafts",
        "platform_accounts",
        ["assigned_platform_account_id"],
        ["id"],
    )
    for column in ["assigned_platform_account_id", "assignment_status", "assigned_at"]:
        op.create_index(op.f(f"ix_publish_drafts_{column}"), "publish_drafts", [column])

    publish_target_platform = postgresql.ENUM("TIKTOK", "FACEBOOK_REELS", "YOUTUBE_SHORTS", name="publish_target_platform", create_type=False)
    op.create_table(
        "publish_routing_rules",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("platform", publish_target_platform, nullable=False),
        sa.Column("rule_name", sa.String(length=160), nullable=False),
        sa.Column("status", routing_rule_status, nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("match_json", postgresql.JSONB(), nullable=True),
        sa.Column("action_json", postgresql.JSONB(), nullable=True),
        sa.Column("fallback_behavior", sa.String(length=80), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_publish_routing_rules_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publish_routing_rules")),
        sa.UniqueConstraint("workspace_id", "rule_name", name="uq_publish_routing_rules_workspace_name"),
    )
    for column in ["workspace_id", "platform", "status", "priority"]:
        op.create_index(op.f(f"ix_publish_routing_rules_{column}"), "publish_routing_rules", [column])

    op.alter_column("platform_accounts", "priority", server_default=None)
    op.alter_column("platform_accounts", "is_on_hold", server_default=None)
    op.alter_column("publish_drafts", "assignment_status", server_default=None)
    op.alter_column("publish_routing_rules", "priority", server_default=None)


def downgrade() -> None:
    op.drop_table("publish_routing_rules")
    for column in ["assigned_at", "assignment_status", "assigned_platform_account_id"]:
        op.drop_index(op.f(f"ix_publish_drafts_{column}"), table_name="publish_drafts")
    op.drop_constraint(op.f("fk_publish_drafts_assigned_platform_account_id_platform_accounts"), "publish_drafts", type_="foreignkey")
    for column in [
        "assignment_metadata_json",
        "assigned_by",
        "assigned_reason",
        "assigned_at",
        "assignment_status",
        "assigned_platform_account_id",
    ]:
        op.drop_column("publish_drafts", column)
    for column in ["cooldown_until", "is_on_hold", "priority"]:
        op.drop_index(op.f(f"ix_platform_accounts_{column}"), table_name="platform_accounts")
    for column in ["routing_notes", "allowed_niches_json", "cooldown_until", "hold_reason", "is_on_hold", "priority"]:
        op.drop_column("platform_accounts", column)
    postgresql.ENUM(name="publish_routing_rule_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="publish_account_assignment_status").drop(op.get_bind(), checkfirst=True)
