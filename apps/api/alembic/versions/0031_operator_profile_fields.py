"""Add operator profile fields: phone, address, notes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_operator_profile_fields"
down_revision: str | None = "0030_auth_client"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("operators", sa.Column("phone", sa.String(length=40), nullable=True))
    op.add_column("operators", sa.Column("address", sa.String(length=320), nullable=True))
    op.add_column("operators", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("operators", "notes")
    op.drop_column("operators", "address")
    op.drop_column("operators", "phone")
