from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.analytics.services.operator_feedback_service import OperatorFeedbackError, OperatorFeedbackService
from src.analytics.services.facebook_insights_live_pilot_service import (
    FacebookInsightsLivePilotError,
    FacebookInsightsLivePilotService,
)
from src.analytics.services.publication_metric_cadence_service import (
    PublicationMetricCadenceError,
    PublicationMetricCadenceService,
)
from src.analytics.services.publication_metric_collection_service import (
    PublicationMetricCollectionError,
    PublicationMetricCollectionService,
)
from src.analytics.services.publication_metrics_service import PublicationMetricsError, PublicationMetricsService
from src.analytics.services.publish_health_service import PublishHealthService
from src.db.session import get_db_session
from src.enums import OperatorFeedbackTargetType, PublishDraftStatus
from src.schemas.analytics import (
    FailureSummaryResponse,
    FacebookInsightsLivePilotPreflightRequest,
    FacebookInsightsLivePilotPreflightResponse,
    OperatorFeedbackCreateRequest,
    OperatorFeedbackListResponse,
    OperatorFeedbackResponse,
    PipelineFeedbackResponse,
    PublicationGrowthSummaryResponse,
    PublicationMetricCollectionEnqueueRequest,
    PublicationMetricSnapshotCreateRequest,
    PublicationMetricSnapshotListResponse,
    PublicationMetricSnapshotResponse,
    PublicationMetricScheduleDispatchRequest,
    PublicationMetricScheduleDispatchResponse,
    PublicationMetricScheduleListResponse,
    PublicationMetricScheduleResponse,
    PublicationMetricScheduleUpsertRequest,
    PublicationMetricTrackingMonitorResponse,
    PublicationOutcomeItem,
    PublishHealthDashboardResponse,
)
from src.schemas.jobs import JobResponse

router = APIRouter(tags=["analytics"])


def get_publish_health_service(db: Session = Depends(get_db_session)) -> PublishHealthService:
    return PublishHealthService(db)


def get_operator_feedback_service(db: Session = Depends(get_db_session)) -> OperatorFeedbackService:
    return OperatorFeedbackService(db)


def get_publication_metrics_service(db: Session = Depends(get_db_session)) -> PublicationMetricsService:
    return PublicationMetricsService(db)


def get_publication_metric_collection_service(
    db: Session = Depends(get_db_session),
) -> PublicationMetricCollectionService:
    return PublicationMetricCollectionService(db)


def get_publication_metric_cadence_service(
    db: Session = Depends(get_db_session),
) -> PublicationMetricCadenceService:
    return PublicationMetricCadenceService(db)


def get_facebook_insights_live_pilot_service(
    db: Session = Depends(get_db_session),
) -> FacebookInsightsLivePilotService:
    return FacebookInsightsLivePilotService(db)


def _raise_publication_metrics_http_error(exc: PublicationMetricsError) -> None:
    if exc.code == "publication_not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == "metric_snapshot_idempotency_conflict":
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc


def _raise_metric_collection_http_error(exc: PublicationMetricCollectionError) -> None:
    if exc.code in {"publication_not_found", "metrics_account_not_found", "metrics_job_not_found"}:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        "metrics_collection_idempotency_conflict",
        "metrics_account_inactive",
        "metrics_account_on_hold",
        "metrics_publication_not_published",
    }:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc


def _raise_metric_cadence_http_error(exc: PublicationMetricCadenceError) -> None:
    if exc.code in {"publication_not_found", "metric_schedule_not_found"}:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {"metrics_publication_not_published", "metric_schedule_completed"}:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc


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


@router.post(
    "/platform-publications/{platform_publication_id}/metric-snapshots",
    response_model=PublicationMetricSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_publication_metric_snapshot(
    platform_publication_id: UUID,
    request: PublicationMetricSnapshotCreateRequest,
    service: PublicationMetricsService = Depends(get_publication_metrics_service),
) -> PublicationMetricSnapshotResponse:
    try:
        snapshot = service.record_snapshot(platform_publication_id, request)
    except PublicationMetricsError as exc:
        _raise_publication_metrics_http_error(exc)
    return PublicationMetricSnapshotResponse.model_validate(snapshot)


@router.get(
    "/platform-publications/{platform_publication_id}/metric-snapshots",
    response_model=PublicationMetricSnapshotListResponse,
)
def list_publication_metric_snapshots(
    platform_publication_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: PublicationMetricsService = Depends(get_publication_metrics_service),
) -> PublicationMetricSnapshotListResponse:
    try:
        snapshots, total = service.list_snapshots(
            platform_publication_id,
            limit=limit,
            offset=offset,
        )
    except PublicationMetricsError as exc:
        _raise_publication_metrics_http_error(exc)
    return PublicationMetricSnapshotListResponse(
        snapshots=[PublicationMetricSnapshotResponse.model_validate(item) for item in snapshots],
        total=total,
    )


@router.get(
    "/platform-publications/{platform_publication_id}/growth-summary",
    response_model=PublicationGrowthSummaryResponse,
)
def get_publication_growth_summary(
    platform_publication_id: UUID,
    service: PublicationMetricsService = Depends(get_publication_metrics_service),
) -> PublicationGrowthSummaryResponse:
    try:
        summary = service.growth_summary(platform_publication_id)
    except PublicationMetricsError as exc:
        _raise_publication_metrics_http_error(exc)
    return PublicationGrowthSummaryResponse.model_validate(summary)


@router.post(
    "/platform-publications/{platform_publication_id}/metric-collection-jobs",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
def enqueue_publication_metric_collection(
    platform_publication_id: UUID,
    request: PublicationMetricCollectionEnqueueRequest,
    service: PublicationMetricCollectionService = Depends(
        get_publication_metric_collection_service
    ),
) -> JobResponse:
    try:
        job = service.enqueue(platform_publication_id, request)
    except PublicationMetricCollectionError as exc:
        _raise_metric_collection_http_error(exc)
    return JobResponse.model_validate(job)


@router.post(
    "/platform-publications/{platform_publication_id}/facebook-insights-live-preflight",
    response_model=FacebookInsightsLivePilotPreflightResponse,
)
def preflight_facebook_insights_live_pilot(
    platform_publication_id: UUID,
    request: FacebookInsightsLivePilotPreflightRequest,
    service: FacebookInsightsLivePilotService = Depends(
        get_facebook_insights_live_pilot_service
    ),
) -> FacebookInsightsLivePilotPreflightResponse:
    try:
        return service.preflight(platform_publication_id, request)
    except FacebookInsightsLivePilotError as exc:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if exc.code in {"publication_not_found", "metrics_account_not_found"}
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


@router.put(
    "/platform-publications/{platform_publication_id}/metric-schedule",
    response_model=PublicationMetricScheduleResponse,
)
def upsert_publication_metric_schedule(
    platform_publication_id: UUID,
    request: PublicationMetricScheduleUpsertRequest,
    service: PublicationMetricCadenceService = Depends(get_publication_metric_cadence_service),
) -> PublicationMetricScheduleResponse:
    try:
        schedule = service.upsert_schedule(platform_publication_id, request)
    except PublicationMetricCadenceError as exc:
        _raise_metric_cadence_http_error(exc)
    return PublicationMetricScheduleResponse.model_validate(schedule)


@router.get(
    "/platform-publications/{platform_publication_id}/metric-schedule",
    response_model=PublicationMetricScheduleResponse,
)
def get_publication_metric_schedule(
    platform_publication_id: UUID,
    service: PublicationMetricCadenceService = Depends(get_publication_metric_cadence_service),
) -> PublicationMetricScheduleResponse:
    try:
        schedule = service.get_for_publication(platform_publication_id)
    except PublicationMetricCadenceError as exc:
        _raise_metric_cadence_http_error(exc)
    return PublicationMetricScheduleResponse.model_validate(schedule)


@router.get(
    "/analytics/metric-schedules",
    response_model=PublicationMetricScheduleListResponse,
)
def list_publication_metric_schedules(
    schedule_status: str | None = Query(default=None, alias="status", pattern="^(ACTIVE|PAUSED|COMPLETED|BLOCKED)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: PublicationMetricCadenceService = Depends(get_publication_metric_cadence_service),
) -> PublicationMetricScheduleListResponse:
    schedules, total = service.list_schedules(
        status=schedule_status,
        limit=limit,
        offset=offset,
    )
    return PublicationMetricScheduleListResponse(
        schedules=[PublicationMetricScheduleResponse.model_validate(item) for item in schedules],
        total=total,
    )


@router.get(
    "/analytics/metric-tracking-monitor",
    response_model=PublicationMetricTrackingMonitorResponse,
)
def get_publication_metric_tracking_monitor(
    schedule_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(ACTIVE|PAUSED|COMPLETED|BLOCKED)$",
    ),
    health: str | None = Query(
        default=None,
        pattern="^(HEALTHY|WAITING|DELAYED|COOLDOWN|BLOCKED|PAUSED|COMPLETED)$",
    ),
    platform_account_id: UUID | None = None,
    query: str | None = Query(default=None, alias="q", max_length=180),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: PublicationMetricCadenceService = Depends(get_publication_metric_cadence_service),
) -> PublicationMetricTrackingMonitorResponse:
    payload = service.tracking_monitor(
        status=schedule_status,
        health=health,
        platform_account_id=platform_account_id,
        query=query,
        limit=limit,
        offset=offset,
    )
    return PublicationMetricTrackingMonitorResponse.model_validate(payload)


@router.post(
    "/publication-metric-schedules/{schedule_id}/pause",
    response_model=PublicationMetricScheduleResponse,
)
def pause_publication_metric_schedule(
    schedule_id: UUID,
    service: PublicationMetricCadenceService = Depends(get_publication_metric_cadence_service),
) -> PublicationMetricScheduleResponse:
    try:
        schedule = service.pause(schedule_id)
    except PublicationMetricCadenceError as exc:
        _raise_metric_cadence_http_error(exc)
    return PublicationMetricScheduleResponse.model_validate(schedule)


@router.post(
    "/publication-metric-schedules/{schedule_id}/resume",
    response_model=PublicationMetricScheduleResponse,
)
def resume_publication_metric_schedule(
    schedule_id: UUID,
    resume_at: datetime | None = None,
    service: PublicationMetricCadenceService = Depends(get_publication_metric_cadence_service),
) -> PublicationMetricScheduleResponse:
    if resume_at is not None and (resume_at.tzinfo is None or resume_at.utcoffset() is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="resume_at must include a timezone",
        )
    try:
        schedule = service.resume(schedule_id, resume_at=resume_at)
    except PublicationMetricCadenceError as exc:
        _raise_metric_cadence_http_error(exc)
    return PublicationMetricScheduleResponse.model_validate(schedule)


@router.post(
    "/analytics/metric-schedules/dispatch-due",
    response_model=PublicationMetricScheduleDispatchResponse,
)
def dispatch_due_publication_metric_schedules(
    request: PublicationMetricScheduleDispatchRequest,
    service: PublicationMetricCadenceService = Depends(get_publication_metric_cadence_service),
) -> PublicationMetricScheduleDispatchResponse:
    summary = service.dispatch_due(now=request.now, limit=request.limit)
    return PublicationMetricScheduleDispatchResponse.model_validate(summary)
