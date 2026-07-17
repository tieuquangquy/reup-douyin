"""Add CLEANED_VIDEO and OCR_EVENTS media asset types.

Revision ID: 0027_ocr_clean
Revises: 0026_reup_queue_operator_dismiss
Create Date: 2026-07-16 00:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027_ocr_clean"
down_revision: str | None = "0026_reup_queue_operator_dismiss"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE media_asset_type ADD VALUE IF NOT EXISTS 'OCR_EVENTS'")
    op.execute("ALTER TYPE media_asset_type ADD VALUE IF NOT EXISTS 'CLEANED_VIDEO'")


def downgrade() -> None:
    # PostgreSQL cannot easily remove enum values; leave as no-op.
    pass
