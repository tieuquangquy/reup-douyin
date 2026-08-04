from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel


class AffiliateProduct(BaseModel):
    """Workspace-owned product available for reviewed affiliate matching."""

    __tablename__ = "affiliate_products"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "fingerprint_sha256",
            name="uq_affiliate_products_workspace_fingerprint",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    catalog_version: Mapped[str] = mapped_column(String(80), default="AFFILIATE_CATALOG_V1", nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    external_product_id: Mapped[str | None] = mapped_column(String(240), index=True)
    merchant_name: Mapped[str | None] = mapped_column(String(240), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    product_url: Mapped[str | None] = mapped_column(Text)
    affiliate_url: Mapped[str] = mapped_column(Text, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(12), default="VND", nullable=False)
    price_amount: Mapped[float | None] = mapped_column(Float)
    commission_rate_percent: Mapped[float | None] = mapped_column(Float)
    commission_amount: Mapped[float | None] = mapped_column(Float)
    availability_status: Mapped[str] = mapped_column(String(40), default="UNKNOWN", nullable=False, index=True)
    keywords_json: Mapped[list | None] = mapped_column(JSONB)
    supported_platforms_json: Mapped[list | None] = mapped_column(JSONB)
    fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    topic_mappings: Mapped[list["AffiliateProductTopicMapping"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )


class AffiliateProductImageAsset(BaseModel):
    """Workspace-owned image uploaded for use by affiliate products/comments."""

    __tablename__ = "affiliate_product_image_assets"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "checksum_sha256",
            name="uq_affiliate_product_image_assets_workspace_checksum",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    storage_provider: Mapped[str] = mapped_column(String(40), nullable=False, default="local")
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(240))
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    uploaded_by: Mapped[str] = mapped_column(String(180), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)


class AffiliateCommentTemplate(BaseModel):
    """Versioned workspace template for Facebook Reel affiliate comments."""

    __tablename__ = "affiliate_comment_templates"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "platform",
            "name",
            "version",
            name="uq_affiliate_comment_templates_workspace_platform_name_version",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform: Mapped[str] = mapped_column(String(80), nullable=False, default="FACEBOOK_REELS", index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    message_template: Mapped[str] = mapped_column(Text, nullable=False)
    default_cta: Mapped[str] = mapped_column(Text, nullable=False)
    default_disclosure: Mapped[str] = mapped_column(String(500), nullable=False)
    attach_product_image: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)


class AffiliateProductTopicMapping(BaseModel):
    """Explicit operator-owned product-to-taxonomy mapping."""

    __tablename__ = "affiliate_product_topic_mappings"
    __table_args__ = (
        UniqueConstraint(
            "affiliate_product_id",
            "topic_category_id",
            name="uq_affiliate_product_topic_mapping",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    affiliate_product_id: Mapped[UUID] = mapped_column(ForeignKey("affiliate_products.id"), index=True)
    topic_category_id: Mapped[UUID] = mapped_column(ForeignKey("content_topic_categories.id"), index=True)
    relevance_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="OPERATOR", nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    product: Mapped[AffiliateProduct] = relationship(back_populates="topic_mappings")


class AffiliateProductMatch(BaseModel):
    """Versioned, reviewable product suggestions for one approved classification."""

    __tablename__ = "affiliate_product_matches"
    __table_args__ = (
        UniqueConstraint(
            "platform_publication_id",
            "content_classification_id",
            "matcher_version",
            "catalog_fingerprint_sha256",
            name="uq_affiliate_product_matches_input_version",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform_publication_id: Mapped[UUID] = mapped_column(ForeignKey("platform_publications.id"), index=True)
    content_classification_id: Mapped[UUID] = mapped_column(ForeignKey("content_classifications.id"), index=True)
    matcher_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    catalog_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    catalog_fingerprint_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    decision_status: Mapped[str] = mapped_column(String(40), default="NEEDS_REVIEW", nullable=False, index=True)
    suggestions_json: Mapped[list | None] = mapped_column(JSONB)
    selected_product_id: Mapped[UUID | None] = mapped_column(ForeignKey("affiliate_products.id"), index=True)
    selected_fit_score: Mapped[float | None] = mapped_column(Float)
    created_by_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(180))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)


class AffiliateCommentPlacement(BaseModel):
    """Operator-approved Facebook affiliate comment placement attempt."""

    __tablename__ = "affiliate_comment_placements"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_affiliate_comment_placements_workspace_idempotency",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    platform_publication_id: Mapped[UUID] = mapped_column(ForeignKey("platform_publications.id"), index=True)
    platform_account_id: Mapped[UUID] = mapped_column(ForeignKey("platform_accounts.id"), index=True)
    affiliate_product_match_id: Mapped[UUID] = mapped_column(ForeignKey("affiliate_product_matches.id"), index=True)
    selected_product_id: Mapped[UUID] = mapped_column(ForeignKey("affiliate_products.id"), index=True)
    growth_assessment_id: Mapped[UUID] = mapped_column(ForeignKey("publication_growth_assessments.id"), index=True)
    post_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    message_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    comment_message: Mapped[str] = mapped_column(Text, nullable=False)
    cta_text: Mapped[str] = mapped_column(Text, nullable=False)
    disclosure_text: Mapped[str] = mapped_column(String(500), nullable=False)
    affiliate_url: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_image_url: Mapped[str | None] = mapped_column(Text)
    template_id: Mapped[UUID | None] = mapped_column(ForeignKey("affiliate_comment_templates.id"), index=True)
    template_version: Mapped[int | None] = mapped_column(Integer)
    attach_product_image: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    external_reel_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    external_comment_id: Mapped[str | None] = mapped_column(String(240), index=True)
    external_comment_permalink: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(180), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(180))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(120), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    response_summary_json: Mapped[dict | None] = mapped_column(JSONB)
    gate_snapshot_json: Mapped[dict | None] = mapped_column(JSONB)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
