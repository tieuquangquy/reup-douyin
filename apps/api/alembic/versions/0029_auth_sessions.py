"""Add refresh tokens, workspace memberships, and operator invites.

Revision ID: 0029_auth_sessions
Revises: 0028_operators
Create Date: 2026-07-17 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_auth_sessions"
down_revision: str | None = "0028_operators"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operator_refresh_tokens",
        sa.Column("operator_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_hash", sa.String(length=128), nullable=True),
        sa.Column("user_agent", sa.String(length=320), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["operator_id"], ["operators.id"], name="fk_operator_refresh_tokens_operator_id_operators"),
        sa.PrimaryKeyConstraint("id", name="pk_operator_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_operator_refresh_tokens_token_hash"),
    )
    op.create_index("ix_operator_refresh_tokens_operator_id", "operator_refresh_tokens", ["operator_id"])

    op.create_table(
        "workspace_memberships",
        sa.Column("operator_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False, server_default="operator"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["operator_id"], ["operators.id"], name="fk_workspace_memberships_operator_id_operators"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_workspace_memberships_workspace_id_workspaces"),
        sa.PrimaryKeyConstraint("id", name="pk_workspace_memberships"),
        sa.UniqueConstraint("operator_id", "workspace_id", name="uq_workspace_memberships_operator_workspace"),
    )
    op.create_index("ix_workspace_memberships_operator_id", "workspace_memberships", ["operator_id"])
    op.create_index("ix_workspace_memberships_workspace_id", "workspace_memberships", ["workspace_id"])

    # Backfill memberships from existing operators.home workspace_id
    op.execute(
        """
        INSERT INTO workspace_memberships (id, operator_id, workspace_id, role, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), o.id, o.workspace_id, COALESCE(NULLIF(split_part(o.roles_csv, ',', 1), ''), 'operator'),
               o.is_active, now(), now()
        FROM operators o
        WHERE NOT EXISTS (
          SELECT 1 FROM workspace_memberships m
          WHERE m.operator_id = o.id AND m.workspace_id = o.workspace_id
        )
        """
    )

    op.create_table(
        "operator_invites",
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False, server_default="operator"),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("invited_by_operator_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_operator_invites_workspace_id_workspaces"),
        sa.ForeignKeyConstraint(
            ["invited_by_operator_id"], ["operators.id"], name="fk_operator_invites_invited_by_operator_id_operators"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_operator_invites"),
        sa.UniqueConstraint("token_hash", name="uq_operator_invites_token_hash"),
    )
    op.create_index("ix_operator_invites_workspace_id", "operator_invites", ["workspace_id"])
    op.create_index("ix_operator_invites_email", "operator_invites", ["email"])


def downgrade() -> None:
    op.drop_index("ix_operator_invites_email", table_name="operator_invites")
    op.drop_index("ix_operator_invites_workspace_id", table_name="operator_invites")
    op.drop_table("operator_invites")
    op.drop_index("ix_workspace_memberships_workspace_id", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_operator_id", table_name="workspace_memberships")
    op.drop_table("workspace_memberships")
    op.drop_index("ix_operator_refresh_tokens_operator_id", table_name="operator_refresh_tokens")
    op.drop_table("operator_refresh_tokens")
