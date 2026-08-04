from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.schemas.jobs import JobResponse


GrowthAssessmentStatus = Literal["INSUFFICIENT_DATA", "READY", "STALE", "COUNTER_REGRESSION"]
GrowthConfidence = Literal["LOW", "MEDIUM", "HIGH"]
OpportunityRecommendation = Literal["PRIORITY", "MONITOR", "DO_NOT_PLACE", "INSUFFICIENT_DATA"]


class GrowthScoreRunRequest(BaseModel):
    score_version: str = Field(default="GROWTH_SCORE_V1", min_length=1, max_length=80)


class PublicationGrowthAssessmentResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    platform_publication_id: UUID
    score_version: str
    input_fingerprint_sha256: str
    latest_metric_snapshot_id: UUID | None = None
    created_by_job_id: UUID | None = None
    status: GrowthAssessmentStatus
    confidence: GrowthConfidence
    growth_score: float | None = None
    snapshot_count: int
    observation_hours: float | None = None
    measurement_age_seconds: int | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    input_snapshot_ids: list[UUID] = Field(default_factory=list)
    is_current: bool
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class GrowthScoreRunResponse(BaseModel):
    reused: bool
    growth_assessment: PublicationGrowthAssessmentResponse | None = None
    job: JobResponse | None = None


class GrowthScoreJobSummary(BaseModel):
    id: UUID
    status: str
    progress_percent: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class AffiliateOpportunityItem(BaseModel):
    platform_publication_id: UUID
    platform_account_id: UUID
    page_display_name: str
    external_reel_id: str | None = None
    external_permalink: str | None = None
    caption: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    product_match_id: UUID
    product_match_decision: str
    selected_product_id: UUID
    selected_product_name: str
    selected_product_platform: str
    selected_product_affiliate_url: str
    selected_product_image_url: str | None
    selected_product_availability: str
    selected_product_active: bool
    affiliate_fit_score: float | None = None
    growth_assessment: PublicationGrowthAssessmentResponse | None = None
    growth_is_stale: bool = False
    recommendation: OpportunityRecommendation
    recommendation_reason: str
    latest_job: GrowthScoreJobSummary | None = None


class AffiliateOpportunityKpis(BaseModel):
    eligible_count: int
    priority_count: int
    monitor_count: int
    do_not_place_count: int
    insufficient_data_count: int
    stale_count: int


class AffiliateOpportunityQueueResponse(BaseModel):
    items: list[AffiliateOpportunityItem]
    total: int
    limit: int
    offset: int
    kpis: AffiliateOpportunityKpis
