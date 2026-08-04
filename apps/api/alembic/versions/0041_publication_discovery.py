"""Allow discovered platform publications before internal draft linkage.

Revision ID: 0041_publication_discovery
Revises: 0040_platform_integration_config
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0041_publication_discovery"
down_revision: str | None = "0040_platform_integration_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("platform_publications", "publish_draft_id", nullable=True)
    op.alter_column("platform_publications", "source_video_id", nullable=True)
    op.alter_column("platform_publications", "publish_attempt_id", nullable=True)


def downgrade() -> None:
    op.alter_column("platform_publications", "publish_attempt_id", nullable=False)
    op.alter_column("platform_publications", "source_video_id", nullable=False)
    op.alter_column("platform_publications", "publish_draft_id", nullable=False)
