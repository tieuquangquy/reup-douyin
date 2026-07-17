"""Add operators table for durable local auth.

Revision ID: 0028_operators
Revises: 0027_ocr_clean
Create Date: 2026-07-17 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_operators"
down_revision: str | None = "0027_ocr_clean"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operators",
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("roles_csv", sa.String(length=255), nullable=False, server_default="operator"),
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_operators_workspace_id_workspaces"),
        sa.PrimaryKeyConstraint("id", name="pk_operators"),
        sa.UniqueConstraint("email", name="uq_operators_email"),
    )
    op.create_index("ix_operators_workspace_id", "operators", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_operators_workspace_id", table_name="operators")
    op.drop_table("operators")
