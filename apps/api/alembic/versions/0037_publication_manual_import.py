"""Add explicit origin for connector and manually registered publications.

Revision ID: 0037_publication_origin
Revises: 0036_metric_cadence
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0037_publication_origin"
down_revision: str | None = "0036_metric_cadence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_publications",
        sa.Column(
            "origin",
            sa.String(length=40),
            nullable=False,
            server_default="CONNECTOR_PUBLISH",
        ),
    )
    op.create_index(
        op.f("ix_platform_publications_origin"),
        "platform_publications",
        ["origin"],
    )
    op.alter_column("platform_publications", "origin", server_default=None)


def downgrade() -> None:
    op.drop_index(
        op.f("ix_platform_publications_origin"),
        table_name="platform_publications",
    )
    op.drop_column("platform_publications", "origin")
