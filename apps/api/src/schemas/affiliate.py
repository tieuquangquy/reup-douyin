from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from src.schemas.jobs import JobResponse


AffiliatePlatform = Literal["FACEBOOK", "TIKTOK_SHOP", "SHOPEE", "OTHER"]
AvailabilityStatus = Literal["IN_STOCK", "OUT_OF_STOCK", "UNKNOWN"]


def _normalize_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value).strip().split())
        key = cleaned.casefold()
        if cleaned and key not in seen:
            result.append(cleaned)
            seen.add(key)
    return result


def _validate_image_url(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    if not cleaned.lower().startswith(("http://", "https://")):
        raise ValueError("Product image URL must start with http:// or https://")
    return cleaned


class AffiliateProductCreateRequest(BaseModel):
    catalog_version: str = Field(default="AFFILIATE_CATALOG_V1", min_length=1, max_length=80)
    platform: AffiliatePlatform = "OTHER"
    external_product_id: str | None = Field(default=None, max_length=240)
    merchant_name: str | None = Field(default=None, max_length=240)
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    image_url: str | None = Field(default=None, max_length=2000)
    product_url: str | None = Field(default=None, max_length=2000)
    affiliate_url: str = Field(min_length=8, max_length=2000)
    currency_code: str = Field(default="VND", min_length=3, max_length=12)
    price_amount: float | None = Field(default=None, ge=0)
    commission_rate_percent: float | None = Field(default=None, ge=0, le=100)
    commission_amount: float | None = Field(default=None, ge=0)
    availability_status: AvailabilityStatus = "UNKNOWN"
    keywords: list[str] = Field(default_factory=list, max_length=100)
    supported_platforms: list[str] = Field(default_factory=lambda: ["FACEBOOK_REELS"], max_length=20)
    topic_ids: list[UUID] = Field(default_factory=list, max_length=30)
    is_active: bool = True

    @field_validator("keywords", "supported_platforms")
    @classmethod
    def normalize_list(cls, values: list[str]) -> list[str]:
        return _normalize_strings(values)

    @field_validator("affiliate_url", "product_url")
    @classmethod
    def validate_urls(cls, value: str | None) -> str | None:
        cleaned = (value or "").strip()
        if not cleaned:
            return None
        if not cleaned.lower().startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return cleaned

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str | None) -> str | None:
        return _validate_image_url(value)

    @field_validator("currency_code")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class AffiliateProductUpdateRequest(BaseModel):
    platform: AffiliatePlatform | None = None
    external_product_id: str | None = Field(default=None, max_length=240)
    merchant_name: str | None = Field(default=None, max_length=240)
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    image_url: str | None = Field(default=None, max_length=2000)
    product_url: str | None = Field(default=None, max_length=2000)
    affiliate_url: str | None = Field(default=None, min_length=8, max_length=2000)
    currency_code: str | None = Field(default=None, min_length=3, max_length=12)
    price_amount: float | None = Field(default=None, ge=0)
    commission_rate_percent: float | None = Field(default=None, ge=0, le=100)
    commission_amount: float | None = Field(default=None, ge=0)
    availability_status: AvailabilityStatus | None = None
    keywords: list[str] | None = Field(default=None, max_length=100)
    supported_platforms: list[str] | None = Field(default=None, max_length=20)
    topic_ids: list[UUID] | None = Field(default=None, max_length=30)
    is_active: bool | None = None

    @field_validator("keywords", "supported_platforms")
    @classmethod
    def normalize_list(cls, values: list[str] | None) -> list[str] | None:
        return _normalize_strings(values) if values is not None else None

    @field_validator("affiliate_url", "product_url")
    @classmethod
    def validate_urls(cls, value: str | None) -> str | None:
        return AffiliateProductCreateRequest.validate_urls(value)

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str | None) -> str | None:
        return _validate_image_url(value)

    @field_validator("currency_code")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class AffiliateProductResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    catalog_version: str
    platform: str
    external_product_id: str | None
    merchant_name: str | None
    name: str
    description: str | None
    image_url: str | None
    product_url: str | None
    affiliate_url: str
    currency_code: str
    price_amount: float | None
    commission_rate_percent: float | None
    commission_amount: float | None
    availability_status: str
    keywords: list[str] = Field(default_factory=list)
    supported_platforms: list[str] = Field(default_factory=list)
    topic_ids: list[UUID] = Field(default_factory=list)
    topic_codes: list[str] = Field(default_factory=list)
    topic_names: list[str] = Field(default_factory=list)
    fingerprint_sha256: str
    is_active: bool
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class AffiliateProductListResponse(BaseModel):
    products: list[AffiliateProductResponse]
    total: int
    limit: int
    offset: int
    active_count: int
    out_of_stock_count: int


class AffiliateProductImageUploadResponse(BaseModel):
    id: UUID
    image_url: str
    public_path: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    created_at: datetime


class AffiliateProductBulkImportRequest(BaseModel):
    products: list[AffiliateProductCreateRequest] = Field(min_length=1, max_length=500)


class AffiliateProductBulkImportResponse(BaseModel):
    created_count: int
    updated_count: int
    skipped_count: int
    products: list[AffiliateProductResponse]


class AffiliateProductMatchSuggestion(BaseModel):
    rank: int
    product_id: UUID
    product_name: str
    merchant_name: str | None = None
    platform: str
    affiliate_url: str
    image_url: str | None = None
    price_amount: float | None = None
    currency_code: str
    commission_rate_percent: float | None = None
    availability_status: str
    affiliate_fit_score: float
    score_breakdown: dict[str, float]
    evidence: list[str] = Field(default_factory=list)


class AffiliateProductMatchResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    platform_publication_id: UUID
    content_classification_id: UUID
    matcher_version: str
    catalog_version: str
    catalog_fingerprint_sha256: str
    decision_status: Literal["NEEDS_REVIEW", "APPROVED", "REJECTED", "OVERRIDDEN"]
    suggestions: list[AffiliateProductMatchSuggestion] = Field(default_factory=list)
    selected_product_id: UUID | None
    selected_fit_score: float | None
    created_by_job_id: UUID | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    decision_reason: str | None
    is_current: bool
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class AffiliateProductMatchRunRequest(BaseModel):
    matcher_version: str = Field(default="AFFILIATE_MATCHER_V1", min_length=1, max_length=80)
    max_suggestions: int = Field(default=5, ge=1, le=10)


class AffiliateProductMatchRunResponse(BaseModel):
    reused: bool
    product_match: AffiliateProductMatchResponse | None = None
    job: JobResponse | None = None


class AffiliateProductMatchDecisionRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "OVERRIDDEN"]
    selected_product_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_decision(self) -> "AffiliateProductMatchDecisionRequest":
        if self.decision in {"APPROVED", "OVERRIDDEN"} and self.selected_product_id is None:
            raise ValueError("selected_product_id is required for an approved product match")
        if self.decision in {"REJECTED", "OVERRIDDEN"} and not (self.reason or "").strip():
            raise ValueError("reason is required when rejecting or overriding product suggestions")
        return self


class AffiliateProductMatchJobSummary(BaseModel):
    id: UUID
    status: str
    progress_percent: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class AffiliateProductMatchQueueItem(BaseModel):
    platform_publication_id: UUID
    platform_account_id: UUID
    page_display_name: str
    external_reel_id: str | None = None
    external_permalink: str | None = None
    caption: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    classification_id: UUID
    classification_status: str
    primary_topic_code: str | None = None
    primary_topic_name: str | None = None
    product_match: AffiliateProductMatchResponse | None = None
    latest_job: AffiliateProductMatchJobSummary | None = None


class AffiliateProductMatchQueueKpis(BaseModel):
    eligible_publications: int
    unmatched_count: int
    needs_review_count: int
    approved_count: int
    rejected_count: int
    stale_count: int


class AffiliateProductMatchQueueResponse(BaseModel):
    items: list[AffiliateProductMatchQueueItem]
    total: int
    limit: int
    offset: int
    kpis: AffiliateProductMatchQueueKpis
