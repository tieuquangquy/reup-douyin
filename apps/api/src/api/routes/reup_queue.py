from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.enums import ReupQueueStatus
from src.models.reup_queue import ReupQueueItem
from src.schemas.export_handoff import BatchItemResultResponse, BatchOperationResponse, ReupQueueBatchActionRequest
from src.schemas.reup_queue import (
    ReupQueueActionRequest,
    ReupQueueActionResponse,
    ReupQueueAvailableActionResponse,
    ReupQueueEnqueueRequest,
    ReupQueueEnqueueResponse,
    ReupQueueItemResponse,
    ReupQueueListResponse,
    ReupQueuePurgeRequest,
    ReupQueuePurgeResponse,
)
from src.schemas.candidates import CandidateSourceVideoSummary
from src.schemas.capture_inbox import CaptureSessionListResponse, CaptureSessionResponse
from src.services.export_handoff_service import BatchOperationResult, ExportHandoffError, ExportHandoffService
from src.services.frontend_core_runtime import (
    FrontendCoreRuntimeError,
    assert_expected_stage_versions,
)
from src.services.reup_queue_download_sync import next_action_for_item
from src.services.reup_queue_service import (
    ReupQueueError,
    ReupQueueIntakeSession,
    ReupQueueService,
    available_actions_for_item,
    bucket_for_status,
)

router = APIRouter(tags=["reup-queue"])


def get_reup_queue_service(db: Session = Depends(get_db_session)) -> ReupQueueService:
    return ReupQueueService(db)


def get_export_handoff_service(db: Session = Depends(get_db_session)) -> ExportHandoffService:
    return ExportHandoffService(db)


def _intake_session_response(entry: ReupQueueIntakeSession) -> CaptureSessionResponse:
    session = entry.session
    payload = CaptureSessionResponse.model_validate(session, from_attributes=True)
    # Remap the count the shared picker label reads so it shows queue membership.
    return payload.model_copy(update={"promoted_item_count": entry.queued_item_count})


def _batch_response(result: BatchOperationResult) -> BatchOperationResponse:
    return BatchOperationResponse(
        requested_count=result.requested_count,
        succeeded_count=result.succeeded_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
        export_package_id=result.export_package_id,
        publish_handoff_id=result.publish_handoff_id,
        results=[BatchItemResultResponse(**item.__dict__) for item in result.results],
    )


def _job_type_value(job: object | None) -> str | None:
    if job is None:
        return None
    job_type = getattr(job, "job_type", None)
    if job_type is None:
        return None
    return job_type.value if hasattr(job_type, "value") else str(job_type)


def _dialogue_summary_from_source_video(source_video: object | None) -> dict:
    """Read ANALYZE_AUDIO outcomes for worklist CTAs (no Chinese literacy required)."""
    if source_video is None:
        return {"has_speech": None, "dialogue_phase": None, "transcript_count": None}
    meta = getattr(source_video, "metadata_json", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    dialogue_phase = meta.get("dialogue_phase")
    if dialogue_phase is not None:
        dialogue_phase = str(dialogue_phase)
    has_speech = meta.get("has_speech")
    if has_speech is not None:
        has_speech = bool(has_speech)
    transcript_count = meta.get("transcript_count")
    if transcript_count is not None:
        try:
            transcript_count = int(transcript_count)
        except (TypeError, ValueError):
            transcript_count = None
    if dialogue_phase == "no_dialogue" or has_speech is False:
        transcript_count = 0
        has_speech = False
    return {
        "has_speech": has_speech,
        "dialogue_phase": dialogue_phase,
        "transcript_count": transcript_count,
    }


def _queue_item_response(
    item: ReupQueueItem,
    *,
    display_job: object | None = None,
) -> ReupQueueItemResponse:
    """Serialize a queue row.

    ``display_job`` overrides ``item.job`` when callers resolve analyze-audio authority
    from ``metadata_json.analyze_audio_job_id`` (e.g. after pause left a stale download link).
    """
    source_video = item.source_video
    linked = getattr(item, "job", None)
    job = display_job if display_job is not None else linked
    dialogue = _dialogue_summary_from_source_video(source_video)
    job_id = getattr(job, "id", None) if job is not None else item.job_id
    job_status = None
    job_phase = None
    job_phase_current = None
    job_phase_total = None
    if job is not None:
        status = getattr(job, "status", None)
        job_status = status.value if status is not None and hasattr(status, "value") else status
        current_step_key = getattr(job, "current_step_key", None)
        for step in list(getattr(job, "steps", None) or []):
            if current_step_key and getattr(step, "step_key", None) != current_step_key:
                continue
            metadata = dict(getattr(step, "metadata_json", None) or {})
            for key in (
                "download_phase",
                "analysis_phase",
                "translation_phase",
                "tts_phase",
                "ocr_phase",
                "quality_phase",
            ):
                value = metadata.get(key)
                if value:
                    job_phase = str(value)
                    job_phase_current = metadata.get(f"{key}_current")
                    job_phase_total = metadata.get(f"{key}_total")
                    break
            if job_phase:
                break
    return ReupQueueItemResponse.model_validate(
        {
            "id": item.id,
            "workspace_id": item.workspace_id,
            "video_candidate_id": item.video_candidate_id,
            "source_video_id": item.source_video_id,
            "status": item.status,
            "bucket": bucket_for_status(item.status),
            "next_action": next_action_for_item(item),
            "priority": item.priority,
            "queued_reason": item.queued_reason,
            "operator_note": item.operator_note,
            "last_error_code": item.last_error_code,
            "last_error_message": item.last_error_message,
            "media_prep_status": item.media_prep_status,
            "media_prep_notes": item.media_prep_notes,
            "media_ready_at": item.media_ready_at,
            "blocked_reason": item.blocked_reason,
            "blocked_at": item.blocked_at,
            "held_at": item.held_at,
            "failed_at": item.failed_at,
            "last_action": item.last_action,
            "last_action_at": item.last_action_at,
            "last_action_note": item.last_action_note,
            "available_actions": [
                ReupQueueAvailableActionResponse.model_validate(action, from_attributes=True)
                for action in available_actions_for_item(item)
            ],
            "queued_at": item.queued_at,
            "started_at": item.started_at,
            "completed_at": item.completed_at,
            "cancelled_at": item.cancelled_at,
            "operator_dismissed_at": item.operator_dismissed_at,
            "job_id": job_id,
            "job_type": _job_type_value(job),
            "job_status": job_status,
            "job_progress_percent": int(job.progress_percent) if job is not None else None,
            "job_phase": job_phase,
            "job_phase_current": job_phase_current,
            "job_phase_total": job_phase_total,
            "job_error_code": job.error_code if job is not None else None,
            "job_error_message": job.error_message if job is not None else None,
            "render_output_id": item.render_output_id,
            "publish_draft_id": item.publish_draft_id,
            "metadata_json": item.metadata_json,
            "source_video": CandidateSourceVideoSummary.model_validate(source_video, from_attributes=True)
            if source_video is not None
            else None,
            "has_speech": dialogue["has_speech"],
            "dialogue_phase": dialogue["dialogue_phase"],
            "transcript_count": dialogue["transcript_count"],
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
    )


def _queue_item_response_for_service(service: ReupQueueService, item: ReupQueueItem) -> ReupQueueItemResponse:
    return _queue_item_response(item, display_job=service.resolve_display_job(item))


@router.get("/reup-queue/intake-sessions", response_model=CaptureSessionListResponse)
def list_reup_queue_intake_sessions(
    include_dismissed: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    service: ReupQueueService = Depends(get_reup_queue_service),
) -> CaptureSessionListResponse:
    sessions = service.list_intake_sessions(include_dismissed=include_dismissed, limit=limit)
    return CaptureSessionListResponse(
        sessions=[_intake_session_response(entry) for entry in sessions],
        total_count=len(sessions),
    )


@router.get("/reup-queue/items", response_model=ReupQueueListResponse)
def list_reup_queue_items(
    status_filter: ReupQueueStatus | None = Query(default=None, alias="status"),
    statuses: list[ReupQueueStatus] | None = Query(default=None),
    include_dismissed: bool = Query(default=False),
    sort: str | None = Query(default="active_first"),
    capture_session_id: UUID | None = Query(default=None),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    service: ReupQueueService = Depends(get_reup_queue_service),
) -> ReupQueueListResponse:
    items, total, status_counts = service.list_items(
        status=status_filter,
        statuses=statuses,
        include_dismissed=include_dismissed,
        sort=sort,
        capture_session_id=capture_session_id,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return ReupQueueListResponse(
        items=[_queue_item_response_for_service(service, item) for item in items],
        total_count=total,
        limit=limit,
        offset=offset,
        status_counts=status_counts,
    )


@router.get("/reup-queue/items/{item_id}", response_model=ReupQueueItemResponse)
def get_reup_queue_item(
    item_id: UUID,
    service: ReupQueueService = Depends(get_reup_queue_service),
) -> ReupQueueItemResponse:
    try:
        item = service.get_item(item_id)
    except ReupQueueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": exc.code, "message": exc.message}) from exc
    return _queue_item_response_for_service(service, item)


@router.post("/reup-queue/items/{item_id}/actions", response_model=ReupQueueActionResponse)
def run_reup_queue_action(
    item_id: UUID,
    request: ReupQueueActionRequest,
    service: ReupQueueService = Depends(get_reup_queue_service),
) -> ReupQueueActionResponse:
    try:
        assert_expected_stage_versions(request.expected_stage_versions)
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    try:
        item = service.apply_action(
            item_id,
            action=request.action,
            note=request.note,
            blocked_reason=request.blocked_reason,
            media_prep_notes=request.media_prep_notes,
            media_prep_status=request.media_prep_status,
            pipeline_mode=request.pipeline_mode,
        )
    except ReupQueueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": exc.code, "message": exc.message}) from exc
    return ReupQueueActionResponse(item=_queue_item_response_for_service(service, item))


@router.post("/reup-queue/batch-actions", response_model=BatchOperationResponse)
def run_reup_queue_batch_action(
    request: ReupQueueBatchActionRequest,
    service: ExportHandoffService = Depends(get_export_handoff_service),
) -> BatchOperationResponse:
    try:
        assert_expected_stage_versions(request.expected_stage_versions)
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    try:
        result = service.run_batch_action(
            action=request.action,
            item_ids=request.item_ids,
            note=request.note,
            target_platform=request.target_platform,
            pipeline_mode=request.pipeline_mode,
        )
    except ExportHandoffError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": exc.code, "message": exc.message}) from exc
    return _batch_response(result)


@router.post("/reup-queue/enqueue-candidates", response_model=ReupQueueEnqueueResponse, status_code=status.HTTP_201_CREATED)
def enqueue_reup_candidates(
    request: ReupQueueEnqueueRequest,
    service: ReupQueueService = Depends(get_reup_queue_service),
) -> ReupQueueEnqueueResponse:
    try:
        result = service.enqueue_candidates(
            candidate_ids=request.candidate_ids,
            priority=request.priority,
            queued_reason=request.queued_reason,
            operator_note=request.operator_note,
        )
    except ReupQueueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": exc.code, "message": exc.message}) from exc
    return ReupQueueEnqueueResponse(
        requested_count=result.requested_count,
        queued_count=result.queued_count,
        already_queued_count=result.already_queued_count,
        skipped_count=result.skipped_count,
        items=[_queue_item_response_for_service(service, item) for item in result.items],
        skipped_candidate_ids=result.skipped_candidate_ids,
    )


@router.post("/reup-queue/purge-clearable", response_model=ReupQueuePurgeResponse)
def purge_clearable_reup_queue_items(
    request: ReupQueuePurgeRequest,
    service: ReupQueueService = Depends(get_reup_queue_service),
) -> ReupQueuePurgeResponse:
    item_ids = request.item_ids if request.scope == "selected" else None
    result = service.purge_clearable_items(item_ids=item_ids)
    return ReupQueuePurgeResponse(
        requested_count=result.requested_count,
        purged_count=result.purged_count,
        skipped_count=result.skipped_count,
        skipped_item_ids=result.skipped_item_ids,
    )
