from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.enums import PlatformAccountStatus, PublishAttemptStatus, PublishDraftStatus, PublishTargetPlatform
from src.schemas.publish import (
    PublishDraftCreateRequest,
    PublishDraftListResponse,
    PublishDraftResponse,
    PublishDraftScheduleRequest,
    PublishDraftUpdateRequest,
    PublishDraftPublishRequest,
    PublishAttemptListResponse,
    PublishAttemptResponse,
    PublishStatusResponse,
    PublicationSummaryResponse,
    PublishHistoryResponse,
    PublishReconcileResponse,
    PlatformAccountCreateRequest,
    PlatformAccountListResponse,
    PlatformAccountResponse,
    PlatformAccountUpdateRequest,
    PublishTargetResponse,
)
from src.publish.services.platform_account_service import PlatformAccountError, PlatformAccountService
from src.publish.services.publish_attempt_service import PublishAttemptError, PublishAttemptService
from src.publish.services.publish_reconciliation_service import PublishReconciliationError, PublishReconciliationService
from src.services.publish_service import PublishDraftError, PublishDraftService
from src.services.publish_targets import list_target_configs

router = APIRouter(tags=["publish"])


def get_publish_service(db: Session = Depends(get_db_session)) -> PublishDraftService:
    return PublishDraftService(db)


def get_platform_account_service(db: Session = Depends(get_db_session)) -> PlatformAccountService:
    return PlatformAccountService(db)


def get_publish_attempt_service(db: Session = Depends(get_db_session)) -> PublishAttemptService:
    return PublishAttemptService(db)


def get_publish_reconciliation_service(db: Session = Depends(get_db_session)) -> PublishReconciliationService:
    return PublishReconciliationService(db)


@router.get("/publish-targets", response_model=list[PublishTargetResponse])
def list_publish_targets() -> list[PublishTargetResponse]:
    return [
        PublishTargetResponse(
            platform=config.platform,
            label=config.label,
            caption_max_length=config.caption_max_length,
            hashtag_limit=config.hashtag_limit,
            supports_scheduling=config.supports_scheduling,
            account_ref_required=config.account_ref_required,
        )
        for config in list_target_configs()
    ]


@router.post("/platform-accounts", response_model=PlatformAccountResponse, status_code=status.HTTP_201_CREATED)
def create_platform_account(
    request: PlatformAccountCreateRequest,
    service: PlatformAccountService = Depends(get_platform_account_service),
) -> PlatformAccountResponse:
    try:
        return PlatformAccountResponse.model_validate(service.create_account(request))
    except PlatformAccountError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/platform-accounts", response_model=PlatformAccountListResponse)
def list_platform_accounts(
    platform: PublishTargetPlatform | None = Query(default=None),
    status_filter: PlatformAccountStatus | None = Query(default=None, alias="status"),
    service: PlatformAccountService = Depends(get_platform_account_service),
) -> PlatformAccountListResponse:
    accounts = service.list_accounts(platform=platform, status=status_filter)
    return PlatformAccountListResponse(accounts=[PlatformAccountResponse.model_validate(account) for account in accounts])


@router.get("/platform-accounts/{platform_account_id}", response_model=PlatformAccountResponse)
def get_platform_account(
    platform_account_id: UUID,
    service: PlatformAccountService = Depends(get_platform_account_service),
) -> PlatformAccountResponse:
    try:
        return PlatformAccountResponse.model_validate(service.get_account(platform_account_id))
    except PlatformAccountError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/platform-accounts/{platform_account_id}", response_model=PlatformAccountResponse)
def update_platform_account(
    platform_account_id: UUID,
    request: PlatformAccountUpdateRequest,
    service: PlatformAccountService = Depends(get_platform_account_service),
) -> PlatformAccountResponse:
    try:
        return PlatformAccountResponse.model_validate(service.update_account(platform_account_id, request))
    except PlatformAccountError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/publish-drafts", response_model=PublishDraftResponse, status_code=status.HTTP_201_CREATED)
def create_publish_draft(
    request: PublishDraftCreateRequest,
    service: PublishDraftService = Depends(get_publish_service),
) -> PublishDraftResponse:
    try:
        return PublishDraftResponse.model_validate(service.create_draft(request))
    except PublishDraftError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/publish-drafts", response_model=PublishDraftListResponse)
def list_publish_drafts(
    status_filter: PublishDraftStatus | None = Query(default=None, alias="status"),
    platform: PublishTargetPlatform | None = Query(default=None),
    source_video_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: PublishDraftService = Depends(get_publish_service),
) -> PublishDraftListResponse:
    drafts = service.list_drafts(status=status_filter, platform=platform, source_video_id=source_video_id, limit=limit, offset=offset)
    return PublishDraftListResponse(drafts=[PublishDraftResponse.model_validate(draft) for draft in drafts])


@router.get("/publish-drafts/{publish_draft_id}", response_model=PublishDraftResponse)
def get_publish_draft(
    publish_draft_id: UUID,
    service: PublishDraftService = Depends(get_publish_service),
) -> PublishDraftResponse:
    try:
        return PublishDraftResponse.model_validate(service.get_draft(publish_draft_id))
    except PublishDraftError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/publish-drafts/{publish_draft_id}", response_model=PublishDraftResponse)
def update_publish_draft(
    publish_draft_id: UUID,
    request: PublishDraftUpdateRequest,
    service: PublishDraftService = Depends(get_publish_service),
) -> PublishDraftResponse:
    try:
        return PublishDraftResponse.model_validate(service.update_draft(publish_draft_id, request))
    except PublishDraftError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/publish-drafts/{publish_draft_id}/schedule", response_model=PublishDraftResponse)
def schedule_publish_draft(
    publish_draft_id: UUID,
    request: PublishDraftScheduleRequest,
    service: PublishDraftService = Depends(get_publish_service),
) -> PublishDraftResponse:
    try:
        return PublishDraftResponse.model_validate(service.schedule_draft(publish_draft_id, request))
    except PublishDraftError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/publish-drafts/{publish_draft_id}/unschedule", response_model=PublishDraftResponse)
def unschedule_publish_draft(
    publish_draft_id: UUID,
    service: PublishDraftService = Depends(get_publish_service),
) -> PublishDraftResponse:
    try:
        return PublishDraftResponse.model_validate(service.unschedule_draft(publish_draft_id))
    except PublishDraftError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/publish-drafts/{publish_draft_id}/mark-ready", response_model=PublishDraftResponse)
def mark_publish_draft_ready(
    publish_draft_id: UUID,
    service: PublishDraftService = Depends(get_publish_service),
) -> PublishDraftResponse:
    try:
        return PublishDraftResponse.model_validate(service.mark_ready(publish_draft_id))
    except PublishDraftError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/publish-drafts/{publish_draft_id}/publish", response_model=PublishAttemptResponse, status_code=status.HTTP_201_CREATED)
def publish_draft_now(
    publish_draft_id: UUID,
    request: PublishDraftPublishRequest,
    service: PublishAttemptService = Depends(get_publish_attempt_service),
) -> PublishAttemptResponse:
    try:
        return PublishAttemptResponse.model_validate(service.publish_now(publish_draft_id, request))
    except PublishAttemptError as exc:
        detail = str(exc)
        status_code = status.HTTP_409_CONFLICT if "duplicate_active_attempt" in detail else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/publish-attempts", response_model=PublishAttemptListResponse)
def list_publish_attempts(
    publish_draft_id: UUID | None = None,
    status_filter: PublishAttemptStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: PublishAttemptService = Depends(get_publish_attempt_service),
) -> PublishAttemptListResponse:
    attempts = service.list_attempts(publish_draft_id=publish_draft_id, status=status_filter, limit=limit, offset=offset)
    return PublishAttemptListResponse(attempts=[PublishAttemptResponse.model_validate(attempt) for attempt in attempts])


@router.get("/publish-attempts/{publish_attempt_id}", response_model=PublishAttemptResponse)
def get_publish_attempt(
    publish_attempt_id: UUID,
    service: PublishAttemptService = Depends(get_publish_attempt_service),
) -> PublishAttemptResponse:
    try:
        return PublishAttemptResponse.model_validate(service.get_attempt(publish_attempt_id))
    except PublishAttemptError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/publish-attempts/{publish_attempt_id}/refresh-status", response_model=PublishAttemptResponse)
def refresh_publish_attempt_status(
    publish_attempt_id: UUID,
    service: PublishReconciliationService = Depends(get_publish_reconciliation_service),
) -> PublishAttemptResponse:
    try:
        return PublishAttemptResponse.model_validate(service.refresh_attempt(publish_attempt_id))
    except (PublishAttemptError, PublishReconciliationError, ValueError) as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/publish-drafts/{publish_draft_id}/reconcile", response_model=PublishReconcileResponse)
def reconcile_publish_draft(
    publish_draft_id: UUID,
    service: PublishReconciliationService = Depends(get_publish_reconciliation_service),
) -> PublishReconcileResponse:
    try:
        return PublishReconcileResponse.model_validate(service.reconcile_draft(publish_draft_id))
    except PublishReconciliationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/publish-drafts/{publish_draft_id}/publication-summary", response_model=PublicationSummaryResponse)
def get_publication_summary(
    publish_draft_id: UUID,
    service: PublishReconciliationService = Depends(get_publish_reconciliation_service),
) -> PublicationSummaryResponse:
    try:
        return PublicationSummaryResponse.model_validate(service.build_publication_summary(publish_draft_id))
    except PublishReconciliationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/publish-drafts/{publish_draft_id}/publish-history", response_model=PublishHistoryResponse)
def get_publish_history(
    publish_draft_id: UUID,
    attempt_service: PublishAttemptService = Depends(get_publish_attempt_service),
    reconciliation_service: PublishReconciliationService = Depends(get_publish_reconciliation_service),
) -> PublishHistoryResponse:
    try:
        attempts = attempt_service.attempts_for_draft(publish_draft_id)
        latest = attempts[0] if attempts else None
        canonical = attempt_service.canonical_for_draft(publish_draft_id)
        return PublishHistoryResponse(
            publish_draft_id=publish_draft_id,
            summary=PublicationSummaryResponse.model_validate(reconciliation_service.build_publication_summary(publish_draft_id)),
            attempts=[PublishAttemptResponse.model_validate(attempt) for attempt in attempts],
            latest_attempt=PublishAttemptResponse.model_validate(latest) if latest else None,
            canonical_attempt=PublishAttemptResponse.model_validate(canonical) if canonical else None,
        )
    except (PublishAttemptError, PublishReconciliationError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/publish-drafts/{publish_draft_id}/publish-status", response_model=PublishStatusResponse)
def get_publish_status(
    publish_draft_id: UUID,
    service: PublishAttemptService = Depends(get_publish_attempt_service),
) -> PublishStatusResponse:
    try:
        draft = service.get_draft_for_status(publish_draft_id)
    except PublishAttemptError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    latest = service.latest_for_draft(publish_draft_id)
    canonical = service.canonical_for_draft(publish_draft_id)
    return PublishStatusResponse(
        publish_draft_id=publish_draft_id,
        status=draft.status,
        latest_attempt=PublishAttemptResponse.model_validate(latest) if latest else None,
        canonical_attempt=PublishAttemptResponse.model_validate(canonical) if canonical else None,
        is_published=canonical is not None,
        current_publication_status=draft.current_publication_status,
        current_external_publish_id=draft.current_external_publish_id,
        current_external_permalink=draft.current_external_permalink,
        published_at=draft.published_at,
        last_publish_synced_at=draft.last_publish_synced_at,
        publication_summary_json=draft.publication_summary_json,
    )
