"""Add workspace-scoped platform integration configuration.

Revision ID: 0040_platform_integration_config
Revises: 0039_facebook_publish_guardrails
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0040_platform_integration_config"
down_revision: str | None = "0039_facebook_publish_guardrails"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_integration_configurations",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("app_id", sa.String(length=240), nullable=False),
        sa.Column("encrypted_app_secret", sa.Text(), nullable=False),
        sa.Column("oauth_redirect_uri", sa.String(length=1000), nullable=False),
        sa.Column("graph_api_version", sa.String(length=40), nullable=False),
        sa.Column("requested_scopes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("configured_by_subject", sa.String(length=240), nullable=False),
        sa.Column("key_version", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_platform_integration_configurations_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_integration_configurations")),
        sa.UniqueConstraint(
            "workspace_id",
            "provider",
            name="uq_platform_integration_configs_workspace_provider",
        ),
    )
    op.create_index(
        op.f("ix_platform_integration_configurations_workspace_id"),
        "platform_integration_configurations",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_platform_integration_configurations_provider"),
        "platform_integration_configurations",
        ["provider"],
    )
    op.create_index(
        op.f("ix_platform_integration_configurations_enabled"),
        "platform_integration_configurations",
        ["enabled"],
    )


def downgrade() -> None:
    op.drop_table("platform_integration_configurations")
