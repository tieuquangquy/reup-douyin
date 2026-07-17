"""Add auth client (web | api-ui) to refresh tokens for audience continuity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_auth_client"
down_revision: str | None = "0029_auth_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operator_refresh_tokens",
        sa.Column("client", sa.String(length=32), nullable=False, server_default="web"),
    )


def downgrade() -> None:
    op.drop_column("operator_refresh_tokens", "client")
