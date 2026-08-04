from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.core.auth import AuthenticatedPrincipal, get_current_principal
from src.db.session import get_db_session
from src.growth_intelligence.services.growth_score_service import GrowthIntelligenceError, GrowthScoreService
from src.schemas.growth_intelligence import (
    AffiliateOpportunityItem,
    AffiliateOpportunityKpis,
    AffiliateOpportunityQueueResponse,
    GrowthScoreJobSummary,
    GrowthScoreRunRequest,
    GrowthScoreRunResponse,
    PublicationGrowthAssessmentResponse,
)
from src.schemas.jobs import JobResponse


router = APIRouter(tags=["growth-intelligence"])


def require_growth_principal(
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
) -> AuthenticatedPrincipal:
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Growth intelligence requires an authenticated operator session",
        )
    return principal


def get_growth_service(db: Session = Depends(get_db_session)) -> GrowthScoreService:
    return GrowthScoreService(db)


def _error(exc: GrowthIntelligenceError) -> HTTPException:
    status_code = status.HTTP_404_NOT_FOUND if exc.code.endswith("_not_found") else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=status_code, detail=str(exc))


def _assessment_response(assessment) -> PublicationGrowthAssessmentResponse:
    return PublicationGrowthAssessmentResponse(
        id=assessment.id,
        workspace_id=assessment.workspace_id,
        platform_publication_id=assessment.platform_publication_id,
        score_version=assessment.score_version,
        input_fingerprint_sha256=assessment.input_fingerprint_sha256,
        latest_metric_snapshot_id=assessment.latest_metric_snapshot_id,
        created_by_job_id=assessment.created_by_job_id,
        status=assessment.status,
        confidence=assessment.confidence,
        growth_score=assessment.growth_score,
        snapshot_count=assessment.snapshot_count,
        observation_hours=assessment.observation_hours,
        measurement_age_seconds=assessment.measurement_age_seconds,
        score_breakdown=dict(assessment.score_breakdown_json or {}),
        evidence=list(assessment.evidence_json or []),
        input_snapshot_ids=list(assessment.input_snapshot_ids_json or []),
        is_current=assessment.is_current,
        metadata_json=assessment.metadata_json,
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


@router.get(
    "/platform-publications/{publication_id}/growth-score",
    response_model=PublicationGrowthAssessmentResponse | None,
)
def get_publication_growth_score(
    publication_id: UUID,
    service: GrowthScoreService = Depends(get_growth_service),
    principal: AuthenticatedPrincipal = Depends(require_growth_principal),
) -> PublicationGrowthAssessmentResponse | None:
    try:
        assessment = service.get_current(publication_id, principal.workspace_id)
    except GrowthIntelligenceError as exc:
        raise _error(exc) from exc
    return _assessment_response(assessment) if assessment else None


@router.post(
    "/platform-publications/{publication_id}/growth-score-jobs",
    response_model=GrowthScoreRunResponse,
)
def enqueue_publication_growth_score(
    publication_id: UUID,
    request: GrowthScoreRunRequest,
    service: GrowthScoreService = Depends(get_growth_service),
    principal: AuthenticatedPrincipal = Depends(require_growth_principal),
) -> GrowthScoreRunResponse:
    try:
        assessment, job, reused = service.enqueue(publication_id, principal.workspace_id, request)
    except GrowthIntelligenceError as exc:
        raise _error(exc) from exc
    return GrowthScoreRunResponse(
        reused=reused,
        growth_assessment=_assessment_response(assessment) if assessment else None,
        job=JobResponse.model_validate(job) if job else None,
    )


@router.get("/affiliate-opportunities/review-queue", response_model=AffiliateOpportunityQueueResponse)
def get_affiliate_opportunity_queue(
    recommendation: Literal["PRIORITY", "MONITOR", "DO_NOT_PLACE", "INSUFFICIENT_DATA"] | None = None,
    q: str | None = Query(default=None, max_length=240),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: GrowthScoreService = Depends(get_growth_service),
    principal: AuthenticatedPrincipal = Depends(require_growth_principal),
) -> AffiliateOpportunityQueueResponse:
    rows, total, kpis = service.opportunity_queue(
        principal.workspace_id,
        recommendation=recommendation,
        query=q,
        limit=limit,
        offset=offset,
    )
    items: list[AffiliateOpportunityItem] = []
    for row in rows:
        publication = row["publication"]
        product_match = row["product_match"]
        account = row["account"]
        product = row["product"]
        assessment = row["assessment"]
        job = row["latest_job"]
        items.append(
            AffiliateOpportunityItem(
                platform_publication_id=publication.id,
                platform_account_id=publication.platform_account_id,
                page_display_name=account.display_name,
                external_reel_id=publication.external_reel_id,
                external_permalink=publication.external_permalink,
                caption=row["caption"],
                thumbnail_url=row["thumbnail_url"],
                published_at=publication.published_at,
                product_match_id=product_match.id,
                product_match_decision=product_match.decision_status,
                selected_product_id=product.id,
                selected_product_name=product.name,
                selected_product_platform=product.platform,
                selected_product_affiliate_url=product.affiliate_url,
                selected_product_image_url=product.image_url,
                selected_product_availability=product.availability_status,
                selected_product_active=product.is_active,
                affiliate_fit_score=product_match.selected_fit_score,
                growth_assessment=_assessment_response(assessment) if assessment else None,
                growth_is_stale=row["growth_is_stale"],
                recommendation=row["recommendation"],
                recommendation_reason=row["recommendation_reason"],
                latest_job=GrowthScoreJobSummary.model_validate(job, from_attributes=True) if job else None,
            )
        )
    return AffiliateOpportunityQueueResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        kpis=AffiliateOpportunityKpis(**kpis),
    )
