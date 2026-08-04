from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from src.schemas.jobs import JobResponse


CommentPlacementStatus = Literal["DRAFT", "QUEUED", "POSTING", "POSTED", "FAILED", "CANCELLED", "BLOCKED"]
CommentSource = Literal["SHARED_TEMPLATE", "ITEM_CUSTOM"]


class AffiliateCommentPreviewRequest(BaseModel):
    cta_text: str = Field(default="Xem sản phẩm phù hợp với video tại:", min_length=1, max_length=500)
    disclosure_text: str = Field(default="", max_length=500)
    comment_source: CommentSource = "SHARED_TEMPLATE"
    comment_message_template_override: str | None = Field(default=None, min_length=1, max_length=5000)
    comment_message_override: str | None = Field(default=None, min_length=1, max_length=5000)
    replaces_placement_id: UUID | None = None
    template_id: UUID | None = None
    attach_product_image: bool | None = None
    create_another_comment: bool = False
    previous_posted_placement_id: UUID | None = None

    @field_validator("cta_text", "disclosure_text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("comment_message_template_override", "comment_message_override")
    @classmethod
    def normalize_comment_override(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Comment message override cannot be empty")
        return cleaned

    @model_validator(mode="after")
    def validate_create_another_contract(self) -> "AffiliateCommentPreviewRequest":
        if self.create_another_comment and self.previous_posted_placement_id is None:
            raise ValueError("previous_posted_placement_id is required when creating another comment")
        if not self.create_another_comment and self.previous_posted_placement_id is not None:
            raise ValueError("previous_posted_placement_id is only allowed when creating another comment")
        if self.create_another_comment and self.replaces_placement_id is not None:
            raise ValueError("A new comment cannot replace an existing preview revision")
        return self


class AffiliateCommentPlacementResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    platform_publication_id: UUID
    platform_account_id: UUID
    affiliate_product_match_id: UUID
    selected_product_id: UUID
    growth_assessment_id: UUID
    post_job_id: UUID | None
    status: CommentPlacementStatus
    idempotency_key: str
    message_sha256: str
    comment_message: str
    cta_text: str
    disclosure_text: str
    affiliate_url: str
    attachment_image_url: str | None
    template_id: UUID | None
    template_version: int | None
    attach_product_image: bool
    external_reel_id: str
    external_comment_id: str | None
    external_comment_permalink: str | None
    created_by: str
    approved_by: str | None
    approved_at: datetime | None
    posted_at: datetime | None
    error_code: str | None
    error_message: str | None
    response_summary_json: dict | None
    gate_snapshot_json: dict | None
    is_current: bool
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class AffiliateCommentPreviewResponse(BaseModel):
    reused: bool
    placement: AffiliateCommentPlacementResponse


class AffiliateCommentHistoryResponse(BaseModel):
    placements: list[AffiliateCommentPlacementResponse]
    can_create_another: bool
    can_post_now: bool
    posted_count_24h: int
    max_posts_per_24h: int
    cooldown_hours: int
    next_allowed_at: datetime | None = None
    blocked_reason: Literal["ACTIVE_PLACEMENT", "COOLDOWN", "DAILY_LIMIT"] | None = None


class AffiliateCommentApproveResponse(BaseModel):
    placement: AffiliateCommentPlacementResponse
    job: JobResponse | None = None


class AffiliateCommentVerificationRequest(BaseModel):
    authorize_network: bool = False


class AffiliateCommentVerificationJobResponse(BaseModel):
    placement: AffiliateCommentPlacementResponse
    job: JobResponse
    reused: bool
