from __future__ import annotations

import logging
import math
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.enums import CaptureSessionStatus, CapturedItemStatus
from src.schemas.capture_inbox import (
    CapturedItemListResponse,
    CapturedItemResponse,
    CaptureInboxActionRequest,
    CaptureInboxActionResponse,
    CaptureInboxItemsVerifyRequest,
    CaptureInboxItemsVerifyResponse,
    CaptureInboxItemQueryRequest,
    CaptureInboxProfileItemResponse,
    CaptureInboxProfileItemsResponse,
    CaptureInboxProfileSummaryResponse,
    CaptureInboxReconciliationResponse,
    CaptureSessionCountsResponse,
    CaptureSessionDebugEventResponse,
    CaptureSessionDebugResponse,
    CaptureSessionDetailResponse,
    CaptureSessionItemsBySessionResponse,
    CaptureSessionListResponse,
    CaptureSessionResponse,
)
from src.services.capture_inbox_engagement_backfill_service import resolve_engagement_count_for_display
from src.services.capture_inbox_service import CaptureInboxError, CaptureInboxService, TARGET_DEBUG_AWEME_IDS, TARGET_DEBUG_FIELDS, reconciliation_from_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["capture-inbox"])
# Browser <img> tags cannot attach Bearer tokens; thumbnail proxy is read-only by item UUID.
public_router = APIRouter(tags=["capture-inbox"])


def get_capture_inbox_service(db: Session = Depends(get_db_session)) -> CaptureInboxService:
    return CaptureInboxService(db)


def _http_error(exc: CaptureInboxError) -> HTTPException:
    status_code = 404 if exc.code in {"capture_session_not_found", "captured_item_not_found"} else 400
    return HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message})


@router.get("/capture-inbox/sessions", response_model=CaptureSessionListResponse)
def list_capture_sessions(
    status: CaptureSessionStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CaptureSessionListResponse:
    sessions, total_count = service.list_sessions(status=status, limit=limit, offset=offset)
    return CaptureSessionListResponse(sessions=[CaptureSessionResponse.model_validate(session) for session in sessions], total_count=total_count)


@router.get("/capture-inbox/sessions/{capture_session_id}", response_model=CaptureSessionDetailResponse)
def get_capture_session(
    capture_session_id: UUID,
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CaptureSessionDetailResponse:
    try:
        session = service.get_session(capture_session_id)
    except CaptureInboxError as exc:
        raise _http_error(exc) from exc
    item_responses = [CapturedItemResponse.model_validate(item) for item in session.items]
    _log_capture_inbox_response_exposure(
        route="get_capture_session",
        capture_session_id=capture_session_id,
        item_count=len(item_responses),
        items=item_responses,
    )
    return CaptureSessionDetailResponse(
        **CaptureSessionResponse.model_validate(session).model_dump(),
        items=item_responses,
        reconciliation=CaptureInboxReconciliationResponse(**reconciliation_from_session(session)),
    )


@router.delete("/capture-inbox/sessions/{capture_session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_capture_session(
    capture_session_id: UUID,
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> Response:
    try:
        service.delete_session(capture_session_id)
    except CaptureInboxError as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/capture-inbox/items", response_model=CapturedItemListResponse)
def list_captured_items(
    capture_session_id: UUID | None = None,
    profile_url: str | None = None,
    status: CapturedItemStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CapturedItemListResponse:
    try:
        items, total_count = service.list_items(
            capture_session_id=capture_session_id,
            profile_url=profile_url,
            status=status,
            search=None,
            advanced_filter=None,
            limit=limit,
            offset=offset,
        )
    except CaptureInboxError as exc:
        raise _http_error(exc) from exc
    item_responses = [CapturedItemResponse.model_validate(item) for item in items]
    _log_capture_inbox_response_exposure(
        route="list_captured_items",
        capture_session_id=capture_session_id,
        item_count=len(item_responses),
        items=item_responses,
    )
    return CapturedItemListResponse(items=item_responses, total_count=total_count)


@router.get("/capture-inbox/items/{item_id}", response_model=CapturedItemResponse)
def get_captured_item(
    item_id: UUID,
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CapturedItemResponse:
    try:
        item = service.get_item(item_id)
    except CaptureInboxError as exc:
        raise _http_error(exc) from exc
    response = CapturedItemResponse.model_validate(item)
    _log_capture_inbox_response_exposure(
        route="get_captured_item",
        capture_session_id=item.capture_session_id,
        item_count=1,
        items=[response],
    )
    return response


@public_router.get("/capture-inbox/items/{item_id}/thumbnail")
def stream_captured_item_thumbnail(
    item_id: UUID,
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> Response:
    try:
        data, content_type = service.stream_item_thumbnail(item_id)
    except CaptureInboxError as exc:
        raise _http_error(exc) from exc
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})


@router.post("/capture-inbox/items/query", response_model=CapturedItemListResponse)
def query_captured_items(
    request: CaptureInboxItemQueryRequest,
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CapturedItemListResponse:
    try:
        items, total_count = service.list_items(
            capture_session_id=request.capture_session_id,
            status=request.status,
            search=request.search,
            advanced_filter=request.advanced_filter,
            limit=request.limit,
            offset=request.offset,
        )
    except CaptureInboxError as exc:
        raise _http_error(exc) from exc
    item_responses = [CapturedItemResponse.model_validate(item) for item in items]
    _log_capture_inbox_response_exposure(
        route="query_captured_items",
        capture_session_id=request.capture_session_id,
        item_count=len(item_responses),
        items=item_responses,
    )
    return CapturedItemListResponse(items=item_responses, total_count=total_count)


@router.get("/douyin-extension/capture-sessions/{capture_session_id}/items", response_model=CaptureSessionItemsBySessionResponse)
def list_capture_session_items_by_session_id(
    capture_session_id: UUID,
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CaptureSessionItemsBySessionResponse:
    try:
        session = service.get_session(capture_session_id)
    except CaptureInboxError as exc:
        raise _http_error(exc) from exc
    items = [CapturedItemResponse.model_validate(item) for item in session.items]
    return CaptureSessionItemsBySessionResponse(
        session_id=session.id,
        items_count=len(items),
        items=items,
        counts=_counts_from_session(session),
    )


@router.get("/douyin-extension/capture-inbox/profile-items", response_model=CaptureInboxProfileItemsResponse)
def list_capture_inbox_profile_items(
    profile_url: str = Query(..., min_length=1),
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CaptureInboxProfileItemsResponse:
    try:
        profile_identifier, normalized_profile_url, items, total_count, unique_video_count = service.list_profile_items(
            profile_url=profile_url,
            limit=limit,
            offset=offset,
        )
        _, _, counts, _, _ = service.get_profile_summary(profile_url=profile_url)
    except CaptureInboxError as exc:
        raise _http_error(exc) from exc
    safe_items = [_safe_profile_item_response(item, normalized_profile_url=normalized_profile_url) for item in items]
    return CaptureInboxProfileItemsResponse(
        profile_identifier=profile_identifier,
        normalized_profile_url=normalized_profile_url,
        total_count=total_count,
        unique_video_count=unique_video_count,
        offset=offset,
        items_count=len(safe_items),
        counts=counts,
        items=safe_items,
    )


@router.get("/douyin-extension/capture-inbox/profile-summary", response_model=CaptureInboxProfileSummaryResponse)
def get_capture_inbox_profile_summary(
    profile_url: str = Query(..., min_length=1),
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CaptureInboxProfileSummaryResponse:
    try:
        profile_identifier, normalized_profile_url, counts, total_count, unique_video_count = service.get_profile_summary(profile_url=profile_url)
    except CaptureInboxError as exc:
        raise _http_error(exc) from exc
    return CaptureInboxProfileSummaryResponse(
        profile_identifier=profile_identifier,
        normalized_profile_url=normalized_profile_url,
        total_count=total_count,
        unique_video_count=unique_video_count,
        counts=counts,
    )


@router.post("/douyin-extension/capture-inbox/items/verify", response_model=CaptureInboxItemsVerifyResponse)
def verify_capture_inbox_items(
    request: CaptureInboxItemsVerifyRequest,
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CaptureInboxItemsVerifyResponse:
    items = service.verify_items_by_external_ids(
        aweme_ids=request.aweme_ids,
        source_video_external_ids=request.source_video_external_ids,
        capture_session_id=request.capture_session_id,
        profile_url=request.profile_url,
        limit=request.limit,
    )
    safe_items = [_safe_profile_item_response(item, normalized_profile_url=None) for item in items]
    found_ids = {str(item.source_video_external_id) for item in items if item.source_video_external_id}
    requested_ids = _ordered_unique([*request.aweme_ids, *request.source_video_external_ids])
    return CaptureInboxItemsVerifyResponse(
        requested_count=len(requested_ids),
        found_count=len(safe_items),
        missing_count=max(0, len(requested_ids) - len(found_ids)),
        items=safe_items,
    )


@router.get("/douyin-extension/capture-sessions/{capture_session_id}/debug", response_model=CaptureSessionDebugResponse)
def get_capture_session_debug(
    capture_session_id: UUID,
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CaptureSessionDebugResponse:
    try:
        session = service.get_session(capture_session_id)
    except CaptureInboxError as exc:
        raise _http_error(exc) from exc
    metadata = session.metadata_json if isinstance(session.metadata_json, dict) else {}
    raw_events = metadata.get("last_ingest_events") if isinstance(metadata.get("last_ingest_events"), list) else []
    debug_events: list[CaptureSessionDebugEventResponse] = []
    for event in raw_events[-10:]:
        if not isinstance(event, dict):
            continue
        debug_events.append(
            CaptureSessionDebugEventResponse(
                time=str(event.get("time")) if event.get("time") is not None else None,
                aweme_id=str(event.get("aweme_id")) if event.get("aweme_id") is not None else None,
                stage=str(event.get("stage")) if event.get("stage") is not None else None,
                status=str(event.get("status")) if event.get("status") is not None else None,
                item_created_or_updated=bool(event.get("item_created_or_updated")) if event.get("item_created_or_updated") is not None else None,
                capture_inbox_item_id=str(event.get("capture_inbox_item_id")) if event.get("capture_inbox_item_id") is not None else None,
                error_code=str(event.get("error_code")) if event.get("error_code") is not None else None,
            )
        )
    item_responses = [CapturedItemResponse.model_validate(item) for item in session.items[:10]]
    return CaptureSessionDebugResponse(
        session_id=session.id,
        session_exists=True,
        session=CaptureSessionResponse.model_validate(session),
        counts=_counts_from_session(session),
        items_count=len(session.items),
        items_sample=item_responses,
        last_ingest_events=debug_events,
    )


@router.post("/capture-inbox/sessions/{capture_session_id}/actions", response_model=CaptureInboxActionResponse)
def run_capture_inbox_action(
    capture_session_id: UUID,
    request: CaptureInboxActionRequest,
    service: CaptureInboxService = Depends(get_capture_inbox_service),
) -> CaptureInboxActionResponse:
    try:
        if request.action == "retry_enrich":
            items = service.retry_enrich(capture_session_id, item_ids=request.item_ids or None)
            session = service.get_session(capture_session_id)
            return CaptureInboxActionResponse(
                action=request.action,
                capture_session_id=capture_session_id,
                affected_item_ids=[item.id for item in items],
                message="Enrichment retried for selected Capture Inbox items.",
                session=CaptureSessionResponse.model_validate(session),
                items=[CapturedItemResponse.model_validate(item) for item in items],
            )
        if request.action == "retry_preview":
            items = service.retry_preview(capture_session_id, item_ids=request.item_ids or None)
            session = service.get_session(capture_session_id)
            return CaptureInboxActionResponse(
                action=request.action,
                capture_session_id=capture_session_id,
                affected_item_ids=[item.id for item in items],
                message="Preview readiness retried for selected Capture Inbox items.",
                session=CaptureSessionResponse.model_validate(session),
                items=[CapturedItemResponse.model_validate(item) for item in items],
            )
        if request.action == "exclude":
            if not request.item_ids:
                raise CaptureInboxError("captured_item_ids_required", "Select at least one captured item to exclude.")
            items = service.exclude_items(capture_session_id, item_ids=request.item_ids, reason=request.exclude_reason)
            session = service.get_session(capture_session_id)
            return CaptureInboxActionResponse(
                action=request.action,
                capture_session_id=capture_session_id,
                affected_item_ids=[item.id for item in items],
                message="Selected Capture Inbox items were excluded.",
                session=CaptureSessionResponse.model_validate(session),
                items=[CapturedItemResponse.model_validate(item) for item in items],
            )
        if request.action == "delete_items":
            if not request.item_ids:
                raise CaptureInboxError("captured_item_ids_required", "Select at least one captured item to delete.")
            result = service.delete_items(capture_session_id, item_ids=request.item_ids)
            message = f"Deleted {len(result.deleted_item_ids)} staged Capture Inbox item(s)."
            if result.skipped_promoted_item_ids:
                message = f"{message} Skipped {len(result.skipped_promoted_item_ids)} promoted item(s)."
            return CaptureInboxActionResponse(
                action=request.action,
                capture_session_id=capture_session_id,
                affected_item_ids=result.deleted_item_ids,
                message=message,
                session=CaptureSessionResponse.model_validate(result.session),
                items=[],
            )
        if request.action == "promote_now":
            result = service.promote(
                capture_session_id,
                item_ids=request.item_ids or None,
                preset_name=request.preset_name,
                filter_config=None,
                persist=request.persist,
            )
            message = _promotion_message(result.promoted_item_count, result.skipped, result.failed)
            return CaptureInboxActionResponse(
                action=request.action,
                capture_session_id=capture_session_id,
                affected_item_ids=[item.id for item in result.items],
                promoted_item_count=result.promoted_item_count,
                candidate_created_count=result.candidate_created_count,
                candidate_updated_count=result.candidate_updated_count,
                message=message,
                session=CaptureSessionResponse.model_validate(result.session),
                items=[CapturedItemResponse.model_validate(item) for item in result.items],
                skipped=[{"item_id": item.item_id, "reason": item.reason} for item in result.skipped],
                failed=[{"item_id": item.item_id, "reason": item.reason} for item in result.failed],
                raw_details=[_promotion_raw_detail(item) for item in result.items]
                + [{"item_id": str(item.item_id), "action": "skipped", "reason": item.reason} for item in result.skipped]
                + [{"item_id": str(item.item_id), "action": "failed", "reason": item.reason} for item in result.failed],
            )
        if request.action == "re_evaluate_intake":
            items = service.re_evaluate_intake(capture_session_id, item_ids=request.item_ids or None, preset_name=request.preset_name)
            session = service.get_session(capture_session_id)
            return CaptureInboxActionResponse(
                action=request.action,
                capture_session_id=capture_session_id,
                affected_item_ids=[item.id for item in items],
                message="Intake evaluation rerun for selected Capture Inbox items.",
                session=CaptureSessionResponse.model_validate(session),
                items=[CapturedItemResponse.model_validate(item) for item in items],
            )
        session = service.get_session(capture_session_id)
        selected_items = [item for item in session.items if not request.item_ids or item.id in request.item_ids]
        if request.action == "open_source":
            return CaptureInboxActionResponse(
                action=request.action,
                capture_session_id=capture_session_id,
                affected_item_ids=[item.id for item in selected_items],
                message="Source URLs returned for operator inspection.",
                session=CaptureSessionResponse.model_validate(session),
                items=[CapturedItemResponse.model_validate(item) for item in selected_items],
                source_urls=[item.source_url for item in selected_items if item.source_url],
            )
        if request.action == "view_raw_details":
            return CaptureInboxActionResponse(
                action=request.action,
                capture_session_id=capture_session_id,
                affected_item_ids=[item.id for item in selected_items],
                message="Raw safe Capture Inbox details returned.",
                session=CaptureSessionResponse.model_validate(session),
                items=[CapturedItemResponse.model_validate(item) for item in selected_items],
                raw_details=[item.raw_payload_json for item in selected_items],
            )
    except CaptureInboxError as exc:
        raise _http_error(exc) from exc
    raise HTTPException(status_code=400, detail={"code": "unsupported_capture_inbox_action", "message": "Unsupported Capture Inbox action."})


def _promotion_raw_detail(item) -> dict[str, Any]:
    metadata = item.metadata_json or {}
    duplicate_detected = bool(metadata.get("review_board_duplicate_detected"))
    snapshot = metadata.get("source_metadata") if isinstance(metadata.get("source_metadata"), dict) else metadata
    return {
        "item_id": str(item.id),
        "aweme_id": item.source_video_external_id or snapshot.get("source_video_external_id"),
        "action": "updated_existing" if duplicate_detected else "created",
        "candidate_id": str(item.promoted_video_candidate_id) if item.promoted_video_candidate_id else None,
        "metadata_updated": True,
        "metadata_snapshot_created": bool(metadata.get("metadata_snapshot_created") or isinstance(metadata.get("source_metadata"), dict)),
        "source_metadata_version": snapshot.get("source_metadata_version"),
        "reup_score": snapshot.get("reup_score"),
        "estimated_views_display": snapshot.get("estimated_views_display"),
        "like_count": snapshot.get("like_count"),
        "comment_count": snapshot.get("comment_count"),
        "share_count": snapshot.get("share_count"),
        "duration_seconds": snapshot.get("duration_seconds") if snapshot.get("duration_seconds") is not None else item.duration_seconds,
        "posted_display": snapshot.get("posted_display"),
        "traceVersion": "22F-1F",
    }


def _promotion_message(promoted_count: int, skipped: list, failed: list) -> str:
    skipped_count = len(skipped)
    failed_count = len(failed)
    if promoted_count == 0 and skipped_count == 0 and failed_count == 0:
        return "No eligible items to promote."
    parts: list[str] = []
    if promoted_count:
        parts.append(f"Promoted {promoted_count} item(s) to Review Board.")
    else:
        parts.append("No eligible items to promote.")
    if skipped_count:
        reason_counts: dict[str, int] = {}
        for item in skipped:
            reason_counts[item.reason] = reason_counts.get(item.reason, 0) + 1
        reason_summary = ", ".join(f"{count} {reason.replace('_', ' ')}" for reason, count in sorted(reason_counts.items()))
        parts.append(f"Skipped {skipped_count}: {reason_summary}.")
    if failed_count:
        parts.append(f"Failed {failed_count} item(s).")
    return " ".join(parts)



def _counts_from_session(session) -> CaptureSessionCountsResponse:
    return CaptureSessionCountsResponse(
        captured=int(getattr(session, "captured_item_count", 0) or 0),
        ready=int(getattr(session, "ready_item_count", 0) or 0),
        needs_action=max(
            0,
            int(getattr(session, "captured_item_count", 0) or 0)
            - int(getattr(session, "ready_item_count", 0) or 0)
            - int(getattr(session, "duplicate_item_count", 0) or 0)
            - int(getattr(session, "failed_item_count", 0) or 0)
            - int(getattr(session, "skipped_item_count", 0) or 0),
        ),
        dup=int(getattr(session, "duplicate_item_count", 0) or 0),
        fail=int(getattr(session, "failed_item_count", 0) or 0),
    )


def _counts_from_items(items: list) -> CaptureSessionCountsResponse:
    ready = sum(1 for item in items if item.status == CapturedItemStatus.READY)
    dup = sum(1 for item in items if item.status == CapturedItemStatus.DUPLICATE)
    fail = sum(1 for item in items if item.status == CapturedItemStatus.FAILED)
    skipped = sum(1 for item in items if item.status == CapturedItemStatus.EXCLUDED)
    captured = len(items)
    return CaptureSessionCountsResponse(captured=captured, ready=ready, needs_action=max(0, captured - ready - dup - fail - skipped), dup=dup, fail=fail)


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result



def _safe_profile_item_response(item, *, normalized_profile_url: str | None) -> CaptureInboxProfileItemResponse:
    metadata_json = getattr(item, "metadata_json", None)
    metadata = metadata_json if isinstance(metadata_json, dict) else {}
    raw_payload_json = getattr(item, "raw_payload_json", None)
    raw_payload = raw_payload_json if isinstance(raw_payload_json, dict) else {}
    title = _safe_title_from_sources(item, metadata, raw_payload)
    return CaptureInboxProfileItemResponse(
        id=item.id,
        capture_inbox_item_id=item.id,
        found=True,
        capture_session_id=item.capture_session_id,
        status=item.status,
        source_profile_external_id=getattr(item, "source_profile_external_id", None),
        profile_url=getattr(item, "profile_url", None),
        normalized_profile_url=normalized_profile_url,
        source_video_external_id=getattr(item, "source_video_external_id", None),
        aweme_id=getattr(item, "source_video_external_id", None),
        metadata_status=_safe_metadata_status(item),
        review_status=str(metadata.get("review_status")) if metadata.get("review_status") is not None else None,
        title=title,
        caption=title,
        duration_seconds=_safe_float_from_sources(item, metadata, raw_payload, "duration_seconds"),
        like_count=_safe_int_from_sources(item, metadata, raw_payload, "like_count"),
        comment_count=resolve_engagement_count_for_display(
            metric="comment",
            existing_count=_safe_int_from_sources(item, metadata, raw_payload, "comment_count"),
            metadata=metadata,
            raw_payload=raw_payload,
        ),
        favorite_count=_safe_int_from_sources(item, metadata, raw_payload, "favorite_count"),
        share_count=resolve_engagement_count_for_display(
            metric="share",
            existing_count=_safe_int_from_sources(item, metadata, raw_payload, "share_count"),
            metadata=metadata,
            raw_payload=raw_payload,
        ),
        posted_at=_safe_datetime_from_sources(item, metadata, raw_payload, "posted_at"),
        thumbnail_url=_safe_str_from_sources(item, metadata, raw_payload, "thumbnail_url"),
        estimated_views=_safe_int_metadata(metadata, "estimated_views"),
        estimated_views_formula=str(metadata.get("estimated_views_formula")) if metadata.get("estimated_views_formula") is not None else None,
        view_count=_safe_int_from_sources(item, metadata, raw_payload, "view_count"),
        real_view_count_data_quality=str(metadata.get("real_view_count_data_quality")) if metadata.get("real_view_count_data_quality") is not None else None,
        finalized_metadata_source=str(metadata.get("finalized_metadata_source")) if metadata.get("finalized_metadata_source") is not None else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )



def _safe_metadata_status(item) -> str | None:
    metadata_json = getattr(item, "metadata_json", None)
    metadata = metadata_json if isinstance(metadata_json, dict) else {}
    status = metadata.get("metadata_status")
    return str(status) if status is not None else None


def _safe_int_metadata(metadata: dict[str, Any], key: str) -> int | None:
    value = metadata.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _safe_int_from_sources(item, metadata: dict[str, Any], raw_payload: dict[str, Any], key: str) -> int | None:
    value = getattr(item, key, None)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return _safe_int_metadata(metadata, key) or _safe_int_metadata(raw_payload, key)


def _safe_float_from_sources(item, metadata: dict[str, Any], raw_payload: dict[str, Any], key: str) -> float | None:
    value = getattr(item, key, None)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    for source in (metadata, raw_payload):
        candidate = source.get(key)
        if isinstance(candidate, bool):
            continue
        if isinstance(candidate, int | float):
            return float(candidate)
    return None


def _safe_str_from_sources(item, metadata: dict[str, Any], raw_payload: dict[str, Any], key: str) -> str | None:
    value = getattr(item, key, None)
    if isinstance(value, str) and value:
        return value
    for source in (metadata, raw_payload):
        candidate = source.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _safe_nested_record(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _safe_title_from_sources(item, metadata: dict[str, Any], raw_payload: dict[str, Any]) -> str | None:
    aweme_id = str(getattr(item, "source_video_external_id", "") or "").strip() or None
    blocked = {aweme_id} if aweme_id else set()
    metadata_evidence = _safe_nested_record(metadata, "profile_card_evidence")
    metadata_dom = _safe_nested_record(metadata, "raw_dom_detail_metrics")
    raw_evidence = _safe_nested_record(raw_payload, "profile_card_evidence")
    raw_dom = _safe_nested_record(raw_payload, "raw_dom_detail_metrics")
    for value in (
        getattr(item, "caption", None),
        raw_payload.get("title"),
        raw_payload.get("desc"),
        metadata.get("title"),
        metadata_evidence.get("title"),
        metadata_evidence.get("caption"),
        metadata_evidence.get("desc"),
        metadata_evidence.get("description"),
        metadata_dom.get("title"),
        raw_evidence.get("title"),
        raw_evidence.get("caption"),
        raw_evidence.get("desc"),
        raw_evidence.get("description"),
        raw_dom.get("title"),
    ):
        if isinstance(value, str):
            title = value.strip()
            if title and title not in blocked:
                return title
    return None


def _safe_datetime_from_sources(item, metadata: dict[str, Any], raw_payload: dict[str, Any], key: str):
    value = getattr(item, key, None)
    if value is not None:
        return value
    for source in (metadata, raw_payload):
        candidate = source.get(key)
        if candidate is not None:
            return candidate
    return None


def _log_capture_inbox_response_exposure(*, route: str, capture_session_id: UUID | None, item_count: int, items: list[CapturedItemResponse]) -> None:
    logger.info(
        "capture_inbox_canonical_metadata_response_exposed",
        extra={
            "route": route,
            "capture_session_id": str(capture_session_id) if capture_session_id else None,
            "item_count": item_count,
            "thumbnail_item_count": sum(1 for item in items if item.thumbnail_url),
            "duration_item_count": sum(1 for item in items if item.duration_seconds is not None or item.duration_text),
            "posted_item_count": sum(1 for item in items if item.posted_at is not None or item.posted_text),
            "metric_item_count": sum(1 for item in items if item.view_count is not None or item.like_count is not None or item.comment_count is not None),
            "preview_status_counts": _status_counts(item.preview_status for item in items),
            "source_link_status_counts": _status_counts(item.source_link_status for item in items),
            "media_asset_status_counts": _status_counts(item.media_asset_status for item in items),
            "media_status_counts": _status_counts(item.media_status for item in items),
        },
    )
    targeted_items = [item for item in items if item.source_video_external_id in TARGET_DEBUG_AWEME_IDS]
    if targeted_items:
        logger.info(
            "targeted_aweme_checkpoint4_api_response",
            extra={
                "route": route,
                "capture_session_id": str(capture_session_id) if capture_session_id else None,
                "items": [
                    {
                        "aweme_id": item.source_video_external_id,
                        "checkpoint4": {field: getattr(item, field) for field in TARGET_DEBUG_FIELDS},
                    }
                    for item in targeted_items
                ],
            },
        )


def _status_counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts
