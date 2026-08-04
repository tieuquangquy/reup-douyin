"""Add encrypted platform credentials and durable OAuth sessions.

Revision ID: 0038_facebook_oauth
Revises: 0037_publication_origin
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0038_facebook_oauth"
down_revision: str | None = "0037_publication_origin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_oauth_sessions",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("created_by_subject", sa.String(length=240), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("redirect_uri", sa.String(length=1000), nullable=False),
        sa.Column("requested_scopes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("granted_scopes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_platform_oauth_sessions_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_oauth_sessions")),
        sa.UniqueConstraint("state_hash", name=op.f("uq_platform_oauth_sessions_state_hash")),
    )
    for column in ("workspace_id", "provider", "created_by_subject", "state_hash", "status", "error_code", "expires_at", "completed_at"):
        op.create_index(op.f(f"ix_platform_oauth_sessions_{column}"), "platform_oauth_sessions", [column])

    op.create_table(
        "platform_credentials",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("platform_account_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("credential_kind", sa.String(length=80), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("key_version", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["platform_account_id"], ["platform_accounts.id"], name=op.f("fk_platform_credentials_platform_account_id_platform_accounts")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name=op.f("fk_platform_credentials_workspace_id_workspaces")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_credentials")),
        sa.UniqueConstraint("platform_account_id", "provider", "credential_kind", name="uq_platform_credentials_account_provider_kind"),
    )
    for column in ("workspace_id", "platform_account_id", "provider", "credential_kind", "expires_at"):
        op.create_index(op.f(f"ix_platform_credentials_{column}"), "platform_credentials", [column])


def downgrade() -> None:
    op.drop_table("platform_credentials")
    op.drop_table("platform_oauth_sessions")
