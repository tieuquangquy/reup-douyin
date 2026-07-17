from uuid import UUID
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from src.adapters.errors import SourceAdapterErrorCode
from src.db.session import get_db_session
from src.schemas.intake import (
    IntakeBootstrapResponse,
    IntakeDiscoverRequest,
    IntakeDiscoverResponse,
    IntakeReadyCheckRequest,
    IntakeReadyCheckResponse,
    IntakeRunCompareResponse,
    IntakeRunDetailResponse,
    IntakeRunListResponse,
    IntakeRunSummaryResponse,
    IntakeSavedPresetCreateRequest,
    IntakeSavedPresetListResponse,
    IntakeSavedPresetResponse,
    IntakeSavedPresetUpdateRequest,
    IntakeTroubleshootingSummaryResponse,
)
from src.services.candidate_types import FilterConfig
from src.services.filter_presets import filter_config_from_dict, get_preset
from src.services.intake_discovery_service import IntakeDiscoveryError, IntakeDiscoveryService
from src.services.intake_productivity_service import IntakeProductivityError, IntakeProductivityService
from src.services.intake_run_history_service import IntakeRunHistoryError, IntakeRunHistoryService

router = APIRouter(tags=["intake"])


def get_intake_discovery_service(db: Session = Depends(get_db_session)) -> IntakeDiscoveryService:
    return IntakeDiscoveryService(db)


def get_intake_productivity_service(db: Session = Depends(get_db_session)) -> IntakeProductivityService:
    return IntakeProductivityService(db)


def get_intake_run_history_service(db: Session = Depends(get_db_session)) -> IntakeRunHistoryService:
    return IntakeRunHistoryService(db)


def _to_filter_config(request: IntakeDiscoverRequest) -> FilterConfig | None:
    if request.filter_config is None:
        return None
    explicit_overrides = request.filter_config.model_dump(exclude_unset=True, exclude_none=True)
    if explicit_overrides.get("has_speech") is True:
        explicit_overrides["require_speech"] = True
        explicit_overrides["allow_no_speech"] = False
    elif explicit_overrides.get("has_speech") is False:
        explicit_overrides["require_speech"] = False
        explicit_overrides["allow_no_speech"] = True
    if request.preset_name:
        base = get_preset(request.preset_name).filter_config.to_dict()
        return filter_config_from_dict({**base, **explicit_overrides})
    return FilterConfig(**explicit_overrides)


@router.post("/intake/ready-check", response_model=IntakeReadyCheckResponse)
def ready_check_intake(
    request: IntakeReadyCheckRequest,
    service: IntakeDiscoveryService = Depends(get_intake_discovery_service),
) -> IntakeReadyCheckResponse:
    summary = service.ready_check(
        workspace_id=request.workspace_id,
        requested_account_id=request.douyin_account_connection_id,
        profile_url=request.profile_url,
    )
    return IntakeReadyCheckResponse(**summary.__dict__)


@router.post("/intake/discover", response_model=IntakeDiscoverResponse)
def discover_intake_candidates(
    request: IntakeDiscoverRequest,
    service: IntakeDiscoveryService = Depends(get_intake_discovery_service),
) -> IntakeDiscoverResponse:
    try:
        summary = service.discover(
            workspace_id=request.workspace_id,
            profile_url=request.profile_url,
            source_platform=request.source_platform,
            preset_name=request.preset_name,
            filter_config=_to_filter_config(request),
            persist=request.persist,
            force_live_refresh=request.force_live_refresh,
            douyin_account_connection_id=request.douyin_account_connection_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_filter_config", "message": str(exc)},
        ) from exc
    except IntakeDiscoveryError as exc:
        http_status = (
            status.HTTP_422_UNPROCESSABLE_ENTITY
            if exc.code
            in {
                str(SourceAdapterErrorCode.INVALID_URL),
                str(SourceAdapterErrorCode.UNSUPPORTED_PROFILE),
                "unsupported_platform",
                "account_resolution_failed",
                "imported_session_missing_cookie",
                "imported_session_invalid",
                "missing_required_headers",
                "missing_user_agent",
                "fetch_client_construction_failed",
                "account_not_fetch_ready",
                "account_missing_fetch_material",
                "browser_profile_unavailable",
                "fetch_preflight_failed",
            }
            else status.HTTP_502_BAD_GATEWAY
        )
        detail = {
            "code": exc.code,
            "message": exc.message,
            "stage": exc.stage,
            "diagnostics_id": exc.diagnostics_id,
        }
        if exc.details:
            detail["details"] = exc.details
        raise HTTPException(
            status_code=http_status,
            detail=detail,
        ) from exc
    except Exception as exc:
        diagnostics_id = str(uuid4())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "unknown_server_error",
                "message": "Unexpected intake discovery error.",
                "stage": "unknown",
                "diagnostics_id": diagnostics_id,
            },
        ) from exc
    return IntakeDiscoverResponse(**summary.__dict__)


@router.get("/intake/bootstrap", response_model=IntakeBootstrapResponse)
def get_intake_bootstrap(
    workspace_id: UUID | None = None,
    service: IntakeProductivityService = Depends(get_intake_productivity_service),
) -> IntakeBootstrapResponse:
    return service.bootstrap(workspace_id=workspace_id)


@router.get("/intake/saved-presets", response_model=IntakeSavedPresetListResponse)
def list_intake_saved_presets(
    workspace_id: UUID | None = None,
    service: IntakeProductivityService = Depends(get_intake_productivity_service),
) -> IntakeSavedPresetListResponse:
    return service.list_saved_presets(workspace_id=workspace_id)


@router.post("/intake/saved-presets", response_model=IntakeSavedPresetResponse, status_code=status.HTTP_201_CREATED)
def create_intake_saved_preset(
    request: IntakeSavedPresetCreateRequest,
    service: IntakeProductivityService = Depends(get_intake_productivity_service),
) -> IntakeSavedPresetResponse:
    try:
        return service.create_saved_preset(request)
    except IntakeProductivityError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.patch("/intake/saved-presets/{preset_id}", response_model=IntakeSavedPresetResponse)
def update_intake_saved_preset(
    preset_id: UUID,
    request: IntakeSavedPresetUpdateRequest,
    service: IntakeProductivityService = Depends(get_intake_productivity_service),
) -> IntakeSavedPresetResponse:
    try:
        return service.update_saved_preset(preset_id, request)
    except IntakeProductivityError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/intake/saved-presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_intake_saved_preset(
    preset_id: UUID,
    service: IntakeProductivityService = Depends(get_intake_productivity_service),
) -> Response:
    try:
        service.delete_saved_preset(preset_id)
    except IntakeProductivityError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _run_to_summary_response(run) -> IntakeRunSummaryResponse:
    metadata = run.metadata_json if isinstance(run.metadata_json, dict) else {}
    duration_seconds = None
    if run.started_at is not None and run.finished_at is not None:
        duration_seconds = max(int((run.finished_at - run.started_at).total_seconds()), 0)

    return IntakeRunSummaryResponse(
        crawl_session_id=run.id,
        source_profile_id=run.source_profile_id,
        submitted_profile_url=run.submitted_profile_url,
        normalized_profile_identifier=run.normalized_profile_identifier,
        source_profile_display_name=run.source_profile.display_name if run.source_profile is not None else None,
        status=str(run.status),
        fetch_mode=metadata.get("fetch_mode") if isinstance(metadata.get("fetch_mode"), str) else None,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_seconds=duration_seconds,
        videos_discovered_count=run.videos_discovered_count,
        videos_created_count=run.videos_created_count,
        videos_updated_count=run.videos_updated_count,
        candidates_total_count=metadata.get("candidates_total_count") if isinstance(metadata.get("candidates_total_count"), int) else 0,
        candidates_matched_count=metadata.get("candidates_matched_count")
        if isinstance(metadata.get("candidates_matched_count"), int)
        else 0,
        error_code=run.error_code,
        error_message=run.error_message,
        fetch_observability=metadata.get("fetch_observability") if isinstance(metadata.get("fetch_observability"), dict) else {},
    )


@router.get("/intake/runs", response_model=IntakeRunListResponse)
def list_intake_runs(
    workspace_id: UUID | None = None,
    limit: int = 12,
    service: IntakeRunHistoryService = Depends(get_intake_run_history_service),
) -> IntakeRunListResponse:
    runs = service.list_runs(workspace_id=workspace_id, limit=limit)
    return IntakeRunListResponse(runs=[_run_to_summary_response(run) for run in runs])


@router.get("/intake/runs/{crawl_session_id}", response_model=IntakeRunDetailResponse)
def get_intake_run(
    crawl_session_id: UUID,
    service: IntakeRunHistoryService = Depends(get_intake_run_history_service),
) -> IntakeRunDetailResponse:
    try:
        run = service.get_run(crawl_session_id)
    except IntakeRunHistoryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    troubleshooting = service.troubleshooting_for(run)
    summary = _run_to_summary_response(run)
    return IntakeRunDetailResponse(
        **summary.model_dump(),
        troubleshooting=IntakeTroubleshootingSummaryResponse(
            category=troubleshooting.category,
            severity=troubleshooting.severity,
            why=troubleshooting.why,
            recommended_actions=troubleshooting.recommended_actions,
        ),
    )


@router.get("/intake/runs/compare", response_model=IntakeRunCompareResponse)
def compare_intake_runs(
    left_run_id: UUID,
    right_run_id: UUID,
    service: IntakeRunHistoryService = Depends(get_intake_run_history_service),
) -> IntakeRunCompareResponse:
    try:
        left, right, delta = service.compare_runs(left_run_id=left_run_id, right_run_id=right_run_id)
    except IntakeRunHistoryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return IntakeRunCompareResponse(
        left=_run_to_summary_response(left),
        right=_run_to_summary_response(right),
        status_changed=delta["status_changed"],
        duration_seconds_delta=delta["duration_seconds_delta"],
        videos_discovered_delta=delta["videos_discovered_delta"],
        videos_created_delta=delta["videos_created_delta"],
        videos_updated_delta=delta["videos_updated_delta"],
        error_code_changed=delta["error_code_changed"],
        left_error_code=delta["left_error_code"],
        right_error_code=delta["right_error_code"],
        left_candidates_total=delta["left_candidates_total"],
        right_candidates_total=delta["right_candidates_total"],
        candidates_total_delta=delta["candidates_total_delta"],
        left_candidates_matched=delta["left_candidates_matched"],
        right_candidates_matched=delta["right_candidates_matched"],
        candidates_matched_delta=delta["candidates_matched_delta"],
    )
