from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


AffiliateCommentTemplatePlatform = Literal["FACEBOOK_REELS"]

DEFAULT_MESSAGE_TEMPLATE = "{{cta}}\n\n{{product_name}}\n{{description}}\n\n{{affiliate_url}}\n\n{{disclosure}}"
DEFAULT_CTA = "Xem sản phẩm phù hợp với video tại:"
DEFAULT_DISCLOSURE = "Đây là liên kết tiếp thị liên kết; tôi có thể nhận hoa hồng nếu bạn mua hàng qua liên kết này."
ALLOWED_TEMPLATE_VARIABLES = {
    "cta",
    "product_name",
    "description",
    "affiliate_url",
    "disclosure",
    "page_name",
    "reel_title",
    "topic_name",
    "product_image",
}


def _clean(value: str) -> str:
    return " ".join(value.strip().split())


class AffiliateCommentTemplateCreateRequest(BaseModel):
    platform: AffiliateCommentTemplatePlatform = "FACEBOOK_REELS"
    name: str = Field(min_length=1, max_length=160)
    message_template: str = Field(default=DEFAULT_MESSAGE_TEMPLATE, min_length=1, max_length=5000)
    default_cta: str = Field(default=DEFAULT_CTA, min_length=1, max_length=500)
    default_disclosure: str = Field(default=DEFAULT_DISCLOSURE, min_length=0, max_length=500)
    attach_product_image: bool = True

    @field_validator("name", "message_template", "default_cta", "default_disclosure")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class AffiliateCommentTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    message_template: str | None = Field(default=None, min_length=1, max_length=5000)
    default_cta: str | None = Field(default=None, min_length=1, max_length=500)
    default_disclosure: str | None = Field(default=None, min_length=0, max_length=500)
    attach_product_image: bool | None = None

    @field_validator("name", "message_template", "default_cta", "default_disclosure")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class AffiliateCommentTemplateResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    platform: str
    name: str
    message_template: str
    default_cta: str
    default_disclosure: str
    attach_product_image: bool
    version: int
    is_active: bool
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class AffiliateCommentTemplateListResponse(BaseModel):
    templates: list[AffiliateCommentTemplateResponse]
    active_template_id: UUID | None
