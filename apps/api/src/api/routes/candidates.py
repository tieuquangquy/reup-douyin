from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.db.session import get_db_session
from src.enums import CandidateStatus
from src.schemas.candidates import (
    CandidateBulkStatusRequest,
    CandidateBulkStatusResponse,
    CandidateDeleteResponse,
    CandidateDetailResponse,
    CandidateFilterRequest,
    CandidateFilterResponse,
    CandidateListResponse,
    CandidateScoreResponse,
    CandidateSummaryResponse,
    FilterConfigRequest,
    FilterPresetListResponse,
    FilterPresetResponse,
)
from src.services.candidate_service import CandidateEvaluationService, CandidateNotFound
from src.services.candidate_types import FilterConfig
from src.services.capture_inbox_service import CaptureInboxService
from src.services.filter_presets import list_presets
from src.services.reup_queue_service import ReupQueueService

router = APIRouter(tags=["candidates"])


def get_candidate_service(db: Session = Depends(get_db_session)) -> CandidateEvaluationService:
    return CandidateEvaluationService(db)


def get_reup_queue_service(db: Session = Depends(get_db_session)) -> ReupQueueService:
    return ReupQueueService(db)


def get_capture_inbox_service(db: Session = Depends(get_db_session)) -> CaptureInboxService:
    return CaptureInboxService(db)


def _to_filter_config(request: FilterConfigRequest | None) -> FilterConfig | None:
    if request is None:
        return None
    return FilterConfig(**request.model_dump())


def _candidate_result_response(result) -> CandidateScoreResponse:
    record = result.record
    return CandidateScoreResponse(
        source_video_id=record.source_video_id,
        source_video_external_id=record.source_video_external_id,
        source_url=record.source_url,
        caption=record.caption,
        posted_at=record.posted_at,
        duration_seconds=record.duration_seconds,
        total_score=result.score.total_score,
        score_label=result.score.score_label,
        score_version=result.score.score_version,
        score_breakdown=result.score.breakdown_json(),
        inclusion_reasons=result.inclusion_reasons,
        exclusion_reasons=result.exclusion_reasons,
        warnings=result.warnings,
        metrics=record.metrics.__dict__,
    )


def _filter_response(result) -> CandidateFilterResponse:
    return CandidateFilterResponse(
        total_count=result.total_count,
        matched_count=result.matched_count,
        rejected_count=result.rejected_count,
        rejection_summary=result.rejection_summary,
        results=[_candidate_result_response(item) for item in result.evaluations],
    )


def _candidate_detail_response(candidate, *, reup_queue_membership=None) -> CandidateDetailResponse:
    membership = reup_queue_membership
    return CandidateDetailResponse.model_validate(candidate).model_copy(
        update={
            "in_reup_queue": bool(getattr(membership, "in_reup_queue", False)),
            "reup_queue_item_id": getattr(membership, "reup_queue_item_id", None),
            "reup_queue_status": (
                membership.reup_queue_status.value
                if getattr(membership, "reup_queue_status", None) is not None
                else None
            ),
        }
    )


@router.post("/candidates/filter/preview", response_model=CandidateFilterResponse)
def preview_candidates(
    request: CandidateFilterRequest,
    service: CandidateEvaluationService = Depends(get_candidate_service),
) -> CandidateFilterResponse:
    result = service.preview(
        preset_name=request.preset_name,
        filter_config=_to_filter_config(request.filter_config),
        source_profile_id=request.source_profile_id,
    )
    return _filter_response(result)


@router.post("/candidates/filter/apply", response_model=CandidateFilterResponse)
def apply_candidate_filter(
    request: CandidateFilterRequest,
    service: CandidateEvaluationService = Depends(get_candidate_service),
) -> CandidateFilterResponse:
    result = service.apply(
        preset_name=request.preset_name,
        filter_config=_to_filter_config(request.filter_config),
        source_profile_id=request.source_profile_id,
        persist=request.persist,
    )
    return _filter_response(result)


@router.get("/candidates", response_model=CandidateListResponse)
def list_candidates(
    status_filter: CandidateStatus | None = Query(default=None, alias="status"),
    min_score: float | None = Query(default=None, ge=0),
    max_score: float | None = Query(default=None, le=100),
    source_profile_id: UUID | None = None,
    search: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    view: str = Query(default="summary", pattern="^(summary|detail)$"),
    hydrate: bool = Query(default=False),
    service: CandidateEvaluationService = Depends(get_candidate_service),
    reup_queue_service: ReupQueueService = Depends(get_reup_queue_service),
    capture_inbox_service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CandidateListResponse:
    hydrate_from_capture_inbox = hydrate and view == "detail"
    total_count = service.count_candidates(
        status=status_filter,
        min_score=min_score,
        max_score=max_score,
        source_profile_id=source_profile_id,
        search=search,
    )
    if search and offset == 0 and total_count == 0:
        capture_inbox_service.repair_orphaned_handoffs_for_search(search)
        total_count = service.count_candidates(
            status=status_filter,
            min_score=min_score,
            max_score=max_score,
            source_profile_id=source_profile_id,
            search=search,
        )
    status_counts = service.count_candidates_by_status(
        min_score=min_score,
        max_score=max_score,
        source_profile_id=source_profile_id,
        search=search,
    )
    if status_filter is None:
        total_count = sum(status_counts.values())
    else:
        total_count = status_counts.get(status_filter.value, total_count)
    candidates = service.list_candidates(
        status=status_filter,
        min_score=min_score,
        max_score=max_score,
        source_profile_id=source_profile_id,
        search=search,
        limit=limit,
        offset=offset,
        hydrate_from_capture_inbox=hydrate_from_capture_inbox,
    )
    memberships = reup_queue_service.membership_for_candidates([candidate.id for candidate in candidates])
    if view == "summary":
        serialized_candidates = [
            CandidateSummaryResponse.from_candidate(candidate, reup_queue_membership=memberships.get(candidate.id))
            for candidate in candidates
        ]
        hydration_summary = None
    else:
        serialized_candidates = [
            _candidate_detail_response(candidate, reup_queue_membership=memberships.get(candidate.id))
            for candidate in candidates
        ]
        hydration_summary = service.hydration_summary(candidates)
    return CandidateListResponse(
        view=view,  # type: ignore[arg-type]
        total_count=total_count,
        status_counts=status_counts,
        offset=offset,
        limit=limit,
        candidates=serialized_candidates,
        review_board_api_debug=_review_board_api_debug(service, len(candidates), view=view),
        review_board_hydration_summary=hydration_summary,
    )


def _review_board_api_debug(service: CandidateEvaluationService, candidate_count: int, *, view: str = "summary") -> dict:
    settings = get_settings()
    database_url = make_url(settings.database_url)
    database_path = database_url.database or ""
    if database_url.drivername.startswith("sqlite") and database_path:
        database_path = str(Path(database_path).resolve())
    return {
        "traceVersion": "22F-3A",
        "apiEndpoint": "GET /candidates",
        "listView": view,
        "frontendApiBaseUrl": "/api unless NEXT_PUBLIC_API_BASE_URL overrides it in apps/web/.env.local",
        "backendDatabaseDriver": database_url.drivername,
        "backendDatabaseHost": database_url.host,
        "backendDatabasePath": database_path,
        "candidateCount": candidate_count,
        "candidateSource": "video_candidates joined to source_videos; summary list skips capture hydration unless hydrate=true with view=detail",
    }


@router.post("/candidates/bulk-status", response_model=CandidateBulkStatusResponse)
def bulk_update_candidate_status(
    request: CandidateBulkStatusRequest,
    service: CandidateEvaluationService = Depends(get_candidate_service),
) -> CandidateBulkStatusResponse:
    candidates = service.bulk_update_status(candidate_ids=request.candidate_ids, status=request.status)
    return CandidateBulkStatusResponse(
        updated_count=len(candidates),
        candidates=[CandidateDetailResponse.model_validate(candidate) for candidate in candidates],
    )


@router.get("/candidates/{candidate_id}", response_model=CandidateDetailResponse)
def get_candidate(
    candidate_id: UUID,
    service: CandidateEvaluationService = Depends(get_candidate_service),
    reup_queue_service: ReupQueueService = Depends(get_reup_queue_service),
) -> CandidateDetailResponse:
    try:
        candidate = service.get_candidate(candidate_id)
        membership = reup_queue_service.membership_for_candidates([candidate.id]).get(candidate.id)
        return _candidate_detail_response(candidate, reup_queue_membership=membership)
    except CandidateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/candidates/{candidate_id}", response_model=CandidateDeleteResponse)
def delete_candidate(
    candidate_id: UUID,
    service: CandidateEvaluationService = Depends(get_candidate_service),
) -> CandidateDeleteResponse:
    try:
        candidate = service.remove_from_review_board(candidate_id)
    except CandidateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CandidateDeleteResponse(
        candidate=CandidateDetailResponse.model_validate(candidate),
        message="Candidate removed from Review Board. Source media and upstream records were not deleted.",
    )


@router.get("/filter-presets", response_model=FilterPresetListResponse)
def get_filter_presets() -> FilterPresetListResponse:
    return FilterPresetListResponse(
        presets=[
            FilterPresetResponse(
                name=preset.name,
                description=preset.description,
                use_when=preset.use_when,
                filter_config=preset.filter_config.to_dict(),
                score_weights=preset.score_weights.to_dict(),
            )
            for preset in list_presets()
        ]
    )
