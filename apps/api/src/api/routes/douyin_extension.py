from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
import logging
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.schemas.douyin_extension import (
    DouyinExtensionCaptureSessionRequest,
    DouyinExtensionCaptureSessionResponse,
    DouyinExtensionCaptureRequest,
    DouyinExtensionCaptureResponse,
    DouyinExtensionDetectPageRequest,
    DouyinExtensionDetectPageResponse,
    DouyinExtensionFullModalHarvestRequest,
    DouyinExtensionFullModalHarvestResponse,
    DouyinExtensionHandshakeRequest,
    DouyinExtensionHarvestPlanRequest,
    DouyinExtensionHarvestPlanResponse,
    DouyinExtensionManagerHistoryResponse,
    DouyinExtensionStatusResponse,
    DouyinExtensionTargetClassificationRequest,
    DouyinExtensionTargetClassificationResponse,
    DouyinProfileVideoClassificationRequest,
    DouyinProfileVideoClassificationResponse,
    DouyinExtensionShadowEstimatedViewsRequest,
    DouyinExtensionShadowEstimatedViewsResponse,
)
from src.services.candidate_types import FilterConfig
from src.services.douyin_extension_capture_service import DouyinExtensionCaptureError, DouyinExtensionCaptureService
from src.services.douyin_extension_setup_service import DouyinExtensionSetupError, DouyinExtensionSetupService
from src.services.douyin_profile_classification_service import build_douyin_profile_video_classification_response
from src.services.filter_presets import filter_config_from_dict, get_preset

router = APIRouter(tags=["douyin-extension"])
logger = logging.getLogger(__name__)


def get_douyin_extension_capture_service(db: Session = Depends(get_db_session)) -> DouyinExtensionCaptureService:
    return DouyinExtensionCaptureService(db)


def get_douyin_extension_setup_service() -> DouyinExtensionSetupService:
    return DouyinExtensionSetupService()


def _to_filter_config(request: DouyinExtensionCaptureRequest) -> FilterConfig | None:
    if request.filter_config is None:
        return None
    explicit_overrides = dict(request.filter_config)
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


def _extension_http_detail(exc: DouyinExtensionCaptureError) -> dict[str, str | None]:
    return {
        "code": exc.code,
        "message": exc.message,
        "stage": exc.stage,
        "diagnostics_id": exc.diagnostics_id,
    }


def _capture_error_status(exc: DouyinExtensionCaptureError) -> int:
    if exc.code in {"schema_missing", "migration_mismatch", "capture_session_persist_failed", "captured_item_persist_failed", "backend_version_mismatch"}:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_422_UNPROCESSABLE_ENTITY


def _validation_http_detail(exc: ValueError) -> dict[str, str | None]:
    return {
        "code": "extension_capture_validation_error",
        "message": str(exc),
        "stage": "request_validation_failed",
        "diagnostics_id": None,
    }


@router.post("/douyin-extension/handshake", response_model=DouyinExtensionStatusResponse)
def handshake_douyin_extension(
    request: DouyinExtensionHandshakeRequest,
    service: DouyinExtensionSetupService = Depends(get_douyin_extension_setup_service),
) -> DouyinExtensionStatusResponse:
    return service.record_handshake(request)


@router.get("/douyin-extension/status", response_model=DouyinExtensionStatusResponse)
def get_douyin_extension_status(
    service: DouyinExtensionSetupService = Depends(get_douyin_extension_setup_service),
) -> DouyinExtensionStatusResponse:
    return service.status()


@router.get("/douyin-extension/history", response_model=DouyinExtensionManagerHistoryResponse)
def get_douyin_extension_history(
    limit: int = 10,
    service: DouyinExtensionSetupService = Depends(get_douyin_extension_setup_service),
) -> DouyinExtensionManagerHistoryResponse:
    return service.history(limit=limit)


@router.get("/douyin-extension/download")
def download_douyin_extension(
    service: DouyinExtensionSetupService = Depends(get_douyin_extension_setup_service),
) -> Response:
    try:
        content, filename = service.build_download_zip()
    except DouyinExtensionSetupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code, "message": exc.message}) from exc
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/douyin-extension/detect-page", response_model=DouyinExtensionDetectPageResponse)
def detect_douyin_extension_page(
    request: DouyinExtensionDetectPageRequest,
    service: DouyinExtensionCaptureService = Depends(get_douyin_extension_capture_service),
    setup_service: DouyinExtensionSetupService = Depends(get_douyin_extension_setup_service),
) -> DouyinExtensionDetectPageResponse:
    try:
        response = DouyinExtensionDetectPageResponse(**service.detect_page(request).__dict__)
        setup_service.record_detect_result(response)
        return response
    except DouyinExtensionCaptureError as exc:
        setup_service.record_failure(
            event_type="detect",
            error_code=exc.code,
            error_message=exc.message,
            page_type=request.page.page_type,
            diagnostics_id=exc.diagnostics_id,
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_extension_http_detail(exc)) from exc


@router.post("/douyin-extension/capture-current-page", response_model=DouyinExtensionCaptureResponse)
def capture_douyin_extension_current_page(
    request: DouyinExtensionCaptureRequest,
    service: DouyinExtensionCaptureService = Depends(get_douyin_extension_capture_service),
    setup_service: DouyinExtensionSetupService = Depends(get_douyin_extension_setup_service),
) -> DouyinExtensionCaptureResponse:
    try:
        response = DouyinExtensionCaptureResponse(**service.capture_current_page(request, filter_config=_to_filter_config(request)).__dict__)
        setup_service.record_capture_result(response)
        return response
    except ValueError as exc:
        if isinstance(exc, DouyinExtensionCaptureError):
            setup_service.record_failure(
                event_type="capture",
                error_code=exc.code,
                error_message=exc.message,
                page_type=request.page.page_type,
                diagnostics_id=exc.diagnostics_id,
            )
            raise HTTPException(status_code=_capture_error_status(exc), detail=_extension_http_detail(exc)) from exc
        setup_service.record_failure(
            event_type="capture",
            error_code="extension_capture_validation_error",
            error_message=str(exc),
            page_type=request.page.page_type,
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_validation_http_detail(exc)) from exc


@router.post("/douyin-extension/capture-session", response_model=DouyinExtensionCaptureSessionResponse)
def create_douyin_extension_capture_session(
    request: DouyinExtensionCaptureSessionRequest,
    service: DouyinExtensionCaptureService = Depends(get_douyin_extension_capture_service),
) -> DouyinExtensionCaptureSessionResponse:
    try:
        return DouyinExtensionCaptureSessionResponse(**service.create_capture_session(request).__dict__)
    except DouyinExtensionCaptureError as exc:
        raise HTTPException(status_code=_capture_error_status(exc), detail=_extension_http_detail(exc)) from exc


@router.post("/douyin-extension/harvest-plan", response_model=DouyinExtensionHarvestPlanResponse)
def create_douyin_extension_harvest_plan(
    request: DouyinExtensionHarvestPlanRequest,
    service: DouyinExtensionCaptureService = Depends(get_douyin_extension_capture_service),
) -> DouyinExtensionHarvestPlanResponse:
    try:
        return DouyinExtensionHarvestPlanResponse(**service.create_harvest_plan(request).__dict__)
    except DouyinExtensionCaptureError as exc:
        raise HTTPException(status_code=_capture_error_status(exc), detail=_extension_http_detail(exc)) from exc


@router.post("/douyin-extension/full-modal-harvest", response_model=DouyinExtensionFullModalHarvestResponse)
def ingest_douyin_extension_full_modal_harvest(
    request: DouyinExtensionFullModalHarvestRequest,
    service: DouyinExtensionCaptureService = Depends(get_douyin_extension_capture_service),
) -> DouyinExtensionFullModalHarvestResponse:
    try:
        return DouyinExtensionFullModalHarvestResponse(**service.ingest_full_modal_harvest(request).__dict__)
    except DouyinExtensionCaptureError as exc:
        logger.warning(
            "full_modal_harvest_error",
            extra={
                "error_code": exc.code,
                "stage": exc.stage,
                "diagnostics_id": exc.diagnostics_id,
                "capture_session_id": str(request.capture_session_id) if request.capture_session_id else None,
            },
        )
        raise HTTPException(status_code=_capture_error_status(exc), detail=_extension_http_detail(exc)) from exc


@router.post("/douyin-extension/capture-inbox/shadow-items", response_model=DouyinExtensionShadowEstimatedViewsResponse)
def validate_douyin_extension_shadow_items(
    request: DouyinExtensionShadowEstimatedViewsRequest,
) -> DouyinExtensionShadowEstimatedViewsResponse:
    item_results = []
    accepted_count = 0
    rejected_count = 0
    for index, item in enumerate(request.items):
        reasons: list[str] = []
        if item.estimated_views is None or item.estimated_views_formula != "tiered_like_multiplier_v1":
            reasons.append("estimated_views_missing_or_formula_missing")
        if item.view_count is not None and item.view_count == item.estimated_views:
            reasons.append("estimated_views_copied_to_view_count")
        if item.real_view_count_data_quality == "trusted_zero_only_low_confidence" and item.view_count == 0:
            reasons.append("low_confidence_zero_view_count_sent_as_real")
        if item.real_view_count_data_quality == "trusted_zero_only_low_confidence" and item.real_view_count_available:
            reasons.append("low_confidence_zero_real_view_count_marked_available")
        if item.real_view_count_data_quality == "trusted_zero_only_low_confidence" and item.real_view_count_value is not None:
            reasons.append("low_confidence_zero_real_view_count_value_not_null")
        status_value = "rejected" if reasons else "accepted"
        if reasons:
            rejected_count += 1
        else:
            accepted_count += 1
        item_results.append(
            {
                "index": index,
                "aweme_id": item.aweme_id,
                "status": status_value,
                "reasons": reasons,
                "view_count_received": item.view_count,
                "estimated_views_received": item.estimated_views,
                "real_view_count_data_quality": item.real_view_count_data_quality,
            }
        )
    return DouyinExtensionShadowEstimatedViewsResponse(
        ok=rejected_count == 0,
        safe_shadow_endpoint_available="yes",
        backend_call_attempted="yes",
        write_mode=request.write_mode,
        production_mutation_allowed=request.production_mutation_allowed,
        accepted_count=accepted_count,
        rejected_count=rejected_count,
        item_count=len(request.items),
        items=item_results,
        production_mutation_detected="no",
        production_collect_state_mutated="no",
        production_counters_mutated="no",
        collect_job_mutated="no",
        queue_items_marked_complete="no",
    )


@router.post("/douyin-extension/capture-inbox/classify-targets", response_model=DouyinExtensionTargetClassificationResponse)
def classify_douyin_extension_targets(
    request: DouyinExtensionTargetClassificationRequest,
    service: DouyinExtensionCaptureService = Depends(get_douyin_extension_capture_service),
) -> DouyinExtensionTargetClassificationResponse:
    try:
        return DouyinExtensionTargetClassificationResponse(**service.classify_targets(request))
    except DouyinExtensionCaptureError as exc:
        raise HTTPException(status_code=_capture_error_status(exc), detail=_extension_http_detail(exc)) from exc


@router.post("/douyin-extension/profile-video-classification", response_model=DouyinProfileVideoClassificationResponse)
def classify_douyin_profile_videos(
    request: DouyinProfileVideoClassificationRequest,
    db: Session = Depends(get_db_session),
) -> DouyinProfileVideoClassificationResponse:
    try:
        return build_douyin_profile_video_classification_response(
            db=db,
            profile_url=request.profile_url,
            sec_uid=request.sec_uid,
            collection_mode=request.collection_mode,
            candidates=request.candidates,
            include_unknown=request.include_unknown,
        )
    except Exception as exc:
        logger.exception("profile_video_classification_lookup_failed", extra={"profile_url": request.profile_url})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail={"code": "profile_video_classification_lookup_failed"}) from exc
