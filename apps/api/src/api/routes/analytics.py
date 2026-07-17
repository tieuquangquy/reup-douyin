from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.analytics.services.operator_feedback_service import OperatorFeedbackError, OperatorFeedbackService
from src.analytics.services.publish_health_service import PublishHealthService
from src.db.session import get_db_session
from src.enums import OperatorFeedbackTargetType, PublishDraftStatus
from src.schemas.analytics import (
    FailureSummaryResponse,
    OperatorFeedbackCreateRequest,
    OperatorFeedbackListResponse,
    OperatorFeedbackResponse,
    PipelineFeedbackResponse,
    PublicationOutcomeItem,
    PublishHealthDashboardResponse,
)

router = APIRouter(tags=["analytics"])


def get_publish_health_service(db: Session = Depends(get_db_session)) -> PublishHealthService:
    return PublishHealthService(db)


def get_operator_feedback_service(db: Session = Depends(get_db_session)) -> OperatorFeedbackService:
    return OperatorFeedbackService(db)


@router.get("/analytics/publish-health", response_model=PublishHealthDashboardResponse)
def get_publish_health(
    window: str = Query(default="last_7_days", pattern="^(today|last_7_days|last_30_days|custom)$"),
    start: datetime | None = None,
    end: datetime | None = None,
    service: PublishHealthService = Depends(get_publish_health_service),
) -> PublishHealthDashboardResponse:
    return service.dashboard_snapshot(window=window, start=start, end=end)


@router.get("/analytics/dashboard-snapshot", response_model=PublishHealthDashboardResponse)
def get_dashboard_snapshot(
    window: str = Query(default="last_7_days", pattern="^(today|last_7_days|last_30_days|custom)$"),
    service: PublishHealthService = Depends(get_publish_health_service),
) -> PublishHealthDashboardResponse:
    return service.dashboard_snapshot(window=window)


@router.get("/analytics/publication-outcomes", response_model=list[PublicationOutcomeItem])
def list_publication_outcomes(
    account_id: UUID | None = None,
    status_filter: PublishDraftStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    service: PublishHealthService = Depends(get_publish_health_service),
) -> list[PublicationOutcomeItem]:
    return service.publication_outcomes(account_id=account_id, status=status_filter, limit=limit)


@router.get("/analytics/failure-summary", response_model=FailureSummaryResponse)
def get_failure_summary(
    window: str = Query(default="last_7_days", pattern="^(today|last_7_days|last_30_days)$"),
    service: PublishHealthService = Depends(get_publish_health_service),
) -> FailureSummaryResponse:
    return service.failure_summary(window=window)


@router.get("/analytics/pipeline-feedback", response_model=PipelineFeedbackResponse)
def get_pipeline_feedback(
    window: str = Query(default="last_7_days", pattern="^(today|last_7_days|last_30_days)$"),
    service: PublishHealthService = Depends(get_publish_health_service),
) -> PipelineFeedbackResponse:
    return service.pipeline_feedback(window=window)


@router.post("/operator-feedback", response_model=OperatorFeedbackResponse, status_code=status.HTTP_201_CREATED)
def create_operator_feedback(
    request: OperatorFeedbackCreateRequest,
    service: OperatorFeedbackService = Depends(get_operator_feedback_service),
) -> OperatorFeedbackResponse:
    try:
        return OperatorFeedbackResponse.model_validate(service.create_feedback(request))
    except OperatorFeedbackError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/operator-feedback", response_model=OperatorFeedbackListResponse)
def list_operator_feedback(
    target_type: OperatorFeedbackTargetType | None = None,
    target_id: UUID | None = None,
    source_video_id: UUID | None = None,
    publish_draft_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    service: OperatorFeedbackService = Depends(get_operator_feedback_service),
) -> OperatorFeedbackListResponse:
    feedback = service.list_feedback(
        target_type=target_type,
        target_id=target_id,
        source_video_id=source_video_id,
        publish_draft_id=publish_draft_id,
        limit=limit,
    )
    return OperatorFeedbackListResponse(feedback=[OperatorFeedbackResponse.model_validate(item) for item in feedback])
