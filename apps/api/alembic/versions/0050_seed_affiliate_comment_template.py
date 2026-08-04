"""Seed one active Facebook Reel affiliate comment template per workspace.

Revision ID: 0050_seed_affiliate_template
Revises: 0049_affiliate_template_snapshot
"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "0050_seed_affiliate_template"
down_revision = "0049_affiliate_template_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    workspaces = bind.execute(sa.text("SELECT id FROM workspaces")).fetchall()
    for (workspace_id,) in workspaces:
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM affiliate_comment_templates "
                "WHERE workspace_id = :workspace_id AND platform = 'FACEBOOK_REELS' AND is_active = true LIMIT 1"
            ),
            {"workspace_id": workspace_id},
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO affiliate_comment_templates "
                "(id, workspace_id, platform, name, message_template, default_cta, default_disclosure, attach_product_image, version, is_active, metadata_json) "
                "VALUES (:id, :workspace_id, 'FACEBOOK_REELS', :name, :message_template, :default_cta, :default_disclosure, true, 1, true, CAST(:metadata_json AS jsonb))"
            ),
            {
                "id": uuid4(),
                "workspace_id": workspace_id,
                "name": "Facebook Reel affiliate default",
                "message_template": "{{cta}}\n\n{{product_name}}\n{{description}}\n\n{{affiliate_url}}\n\n{{disclosure}}",
                "default_cta": "Xem sản phẩm phù hợp với video tại:",
                "default_disclosure": "Đây là liên kết tiếp thị liên kết; tôi có thể nhận hoa hồng nếu bạn mua hàng qua liên kết này.",
                "metadata_json": '{"source":"SYSTEM_DEFAULT"}',
            },
        )


def downgrade() -> None:
    op.execute("DELETE FROM affiliate_comment_templates WHERE metadata_json->>'source' = 'SYSTEM_DEFAULT'")
