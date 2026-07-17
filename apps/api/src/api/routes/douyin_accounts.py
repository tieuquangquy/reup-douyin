from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.enums import DouyinAccountConnectionStatus, JobType
from src.schemas.douyin_accounts import (
    DouyinAccountChallengeActionResponse,
    DouyinAccountCreateRequest,
    DouyinAccountDeleteResponse,
    DouyinAccountListResponse,
    DouyinAccountResponse,
    DouyinAccountRevalidateJobResponse,
    DouyinAccountRevalidateRequest,
    DouyinAccountRevalidateResponse,
    DouyinAccountUpdateRequest,
    DouyinAccountValidateRequest,
    DouyinAccountValidationResponse,
    DouyinBrowserConnectActiveSessionResponse,
    DouyinBrowserConnectResetRequest,
    DouyinBrowserConnectResetResponse,
    DouyinBrowserConnectSessionResponse,
    DouyinBrowserConnectStartRequest,
    DouyinCurrentPageCaptureRequest,
    DouyinCurrentPageCaptureResponse,
    DouyinCurrentPageDetectionResponse,
    DouyinProfileCleanupRequest,
    DouyinProfileCleanupResponse,
)
from src.services.candidate_types import FilterConfig
from src.services.douyin_account_service import DouyinAccountError, DouyinAccountService
from src.services.douyin_browser_connect_service import DouyinBrowserConnectError, DouyinBrowserConnectService
from src.services.douyin_current_page_capture_service import DouyinCurrentPageCaptureError, DouyinCurrentPageCaptureService
from src.services.douyin_profile_cleanup_service import DouyinProfileCleanupService
from src.services.filter_presets import filter_config_from_dict, get_preset
from src.services.job_service import JobService

router = APIRouter(tags=["douyin-accounts"])


def _account_http_detail(exc: DouyinAccountError) -> dict[str, str]:
    code = getattr(exc, "code", None) or str(exc)
    return {"code": code, "message": str(exc)}


def get_douyin_account_service(db: Session = Depends(get_db_session)) -> DouyinAccountService:
    return DouyinAccountService(db)


def get_douyin_browser_connect_service(db: Session = Depends(get_db_session)) -> DouyinBrowserConnectService:
    return DouyinBrowserConnectService(db)


def get_douyin_profile_cleanup_service(db: Session = Depends(get_db_session)) -> DouyinProfileCleanupService:
    return DouyinProfileCleanupService(db)


def get_job_service(db: Session = Depends(get_db_session)) -> JobService:
    return JobService(db)


def get_douyin_current_page_capture_service(db: Session = Depends(get_db_session)) -> DouyinCurrentPageCaptureService:
    return DouyinCurrentPageCaptureService(db)


def _to_current_page_filter_config(request: DouyinCurrentPageCaptureRequest) -> FilterConfig | None:
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


@router.get("/douyin-accounts", response_model=DouyinAccountListResponse)
def list_douyin_accounts(
    workspace_id: UUID | None = None,
    status_filter: DouyinAccountConnectionStatus | None = Query(default=None, alias="status"),
    service: DouyinAccountService = Depends(get_douyin_account_service),
) -> DouyinAccountListResponse:
    accounts = service.list_accounts(workspace_id=workspace_id, status=status_filter)
    return DouyinAccountListResponse(accounts=[service.to_response(account) for account in accounts])


@router.post("/douyin-accounts", response_model=DouyinAccountResponse, status_code=status.HTTP_201_CREATED)
def create_douyin_account(
    request: DouyinAccountCreateRequest,
    service: DouyinAccountService = Depends(get_douyin_account_service),
) -> DouyinAccountResponse:
    try:
        return service.to_response(service.create_account(request))
    except DouyinAccountError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_account_http_detail(exc)) from exc


@router.post("/douyin-accounts/revalidate-due", response_model=DouyinAccountRevalidateResponse)
def revalidate_due_douyin_accounts(
    request: DouyinAccountRevalidateRequest,
    service: DouyinAccountService = Depends(get_douyin_account_service),
) -> DouyinAccountRevalidateResponse:
    try:
        due_accounts = service.due_for_revalidation(workspace_id=request.workspace_id, due_only=request.due_only)
        accounts = service.revalidate_due_accounts(
            workspace_id=request.workspace_id,
            due_only=request.due_only,
            validation_source="manual_sweep",
        )
        return DouyinAccountRevalidateResponse(
            accounts_checked=len(due_accounts),
            accounts_updated=len(accounts),
            accounts=[service.to_response(account) for account in accounts],
        )
    except DouyinAccountError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/douyin-accounts/revalidate-due/job", response_model=DouyinAccountRevalidateJobResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_revalidate_due_douyin_accounts(
    request: DouyinAccountRevalidateRequest,
    account_service: DouyinAccountService = Depends(get_douyin_account_service),
    job_service: JobService = Depends(get_job_service),
) -> DouyinAccountRevalidateJobResponse:
    due_accounts = account_service.due_for_revalidation(workspace_id=request.workspace_id, due_only=request.due_only)
    job = job_service.create_job(
        job_type=JobType.REVALIDATE_STALE_DOUYIN_ACCOUNTS,
        workspace_id=request.workspace_id,
        payload_json={"workspace_id": str(request.workspace_id) if request.workspace_id else None, "due_only": request.due_only},
        reference_type="douyin_account_health_sweep",
    )
    return DouyinAccountRevalidateJobResponse(
        job_id=job.id,
        job_type=job.job_type.value,
        queued_accounts_count=len(due_accounts),
    )


@router.post("/douyin-accounts/browser-connect/start", response_model=DouyinBrowserConnectSessionResponse, status_code=status.HTTP_202_ACCEPTED)
def start_douyin_browser_connect(
    request: DouyinBrowserConnectStartRequest,
    service: DouyinBrowserConnectService = Depends(get_douyin_browser_connect_service),
) -> DouyinBrowserConnectSessionResponse:
    try:
        return service.to_response(service.start_connect(request))
    except DouyinBrowserConnectError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/douyin-accounts/browser-connect/active", response_model=DouyinBrowserConnectActiveSessionResponse)
def get_active_douyin_browser_connect(
    workspace_id: UUID | None = None,
    service: DouyinBrowserConnectService = Depends(get_douyin_browser_connect_service),
) -> DouyinBrowserConnectActiveSessionResponse:
    return service.to_active_response(service.get_active_session(workspace_id=workspace_id))


@router.post("/douyin-accounts/browser-connect/reset", response_model=DouyinBrowserConnectResetResponse)
def reset_douyin_browser_connect_state(
    request: DouyinBrowserConnectResetRequest | None = None,
    service: DouyinBrowserConnectService = Depends(get_douyin_browser_connect_service),
) -> DouyinBrowserConnectResetResponse:
    return service.reset_connect_state(workspace_id=request.workspace_id if request else None)


@router.get("/douyin-accounts/browser-connect/{connect_session_id}", response_model=DouyinBrowserConnectSessionResponse)
def get_douyin_browser_connect(
    connect_session_id: UUID,
    service: DouyinBrowserConnectService = Depends(get_douyin_browser_connect_service),
) -> DouyinBrowserConnectSessionResponse:
    try:
        return service.to_response(service.get_session(connect_session_id))
    except DouyinBrowserConnectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/douyin-accounts/browser-connect/{connect_session_id}/restart", response_model=DouyinBrowserConnectSessionResponse, status_code=status.HTTP_202_ACCEPTED)
def restart_douyin_browser_connect(
    connect_session_id: UUID,
    request: DouyinBrowserConnectStartRequest,
    service: DouyinBrowserConnectService = Depends(get_douyin_browser_connect_service),
) -> DouyinBrowserConnectSessionResponse:
    try:
        return service.to_response(service.restart_session(connect_session_id, request))
    except DouyinBrowserConnectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/douyin-accounts/browser-connect/{connect_session_id}/retry-validation", response_model=DouyinBrowserConnectSessionResponse)
def retry_douyin_browser_connect_validation(
    connect_session_id: UUID,
    service: DouyinBrowserConnectService = Depends(get_douyin_browser_connect_service),
) -> DouyinBrowserConnectSessionResponse:
    try:
        return service.to_response(service.retry_validation(connect_session_id))
    except DouyinBrowserConnectError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/douyin-accounts/browser-connect/{connect_session_id}/cancel", response_model=DouyinBrowserConnectSessionResponse)
def cancel_douyin_browser_connect(
    connect_session_id: UUID,
    service: DouyinBrowserConnectService = Depends(get_douyin_browser_connect_service),
) -> DouyinBrowserConnectSessionResponse:
    try:
        return service.to_response(service.cancel_session(connect_session_id))
    except DouyinBrowserConnectError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/douyin-accounts/browser-profiles/cleanup", response_model=DouyinProfileCleanupResponse)
def scan_douyin_browser_profiles(
    service: DouyinProfileCleanupService = Depends(get_douyin_profile_cleanup_service),
) -> DouyinProfileCleanupResponse:
    return service.scan(apply=False)


@router.post("/douyin-accounts/browser-profiles/cleanup", response_model=DouyinProfileCleanupResponse)
def cleanup_douyin_browser_profiles(
    request: DouyinProfileCleanupRequest,
    service: DouyinProfileCleanupService = Depends(get_douyin_profile_cleanup_service),
) -> DouyinProfileCleanupResponse:
    return service.scan(apply=bool(request.apply and not request.dry_run))


@router.get("/douyin-accounts/{account_id}", response_model=DouyinAccountResponse)
def get_douyin_account(
    account_id: UUID,
    service: DouyinAccountService = Depends(get_douyin_account_service),
) -> DouyinAccountResponse:
    try:
        return service.to_response(service.get_account(account_id))
    except DouyinAccountError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/douyin-accounts/{account_id}", response_model=DouyinAccountResponse)
def update_douyin_account(
    account_id: UUID,
    request: DouyinAccountUpdateRequest,
    service: DouyinAccountService = Depends(get_douyin_account_service),
) -> DouyinAccountResponse:
    try:
        return service.to_response(service.update_account(account_id, request))
    except DouyinAccountError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_account_http_detail(exc)) from exc


@router.get("/douyin-accounts/{account_id}/current-page", response_model=DouyinCurrentPageDetectionResponse)
def detect_douyin_current_page(
    account_id: UUID,
    service: DouyinCurrentPageCaptureService = Depends(get_douyin_current_page_capture_service),
) -> DouyinCurrentPageDetectionResponse:
    summary = service.detect_current_page(account_id)
    return DouyinCurrentPageDetectionResponse(**summary.__dict__)


@router.post("/douyin-accounts/{account_id}/current-page/capture", response_model=DouyinCurrentPageCaptureResponse)
def capture_douyin_current_page(
    account_id: UUID,
    request: DouyinCurrentPageCaptureRequest,
    service: DouyinCurrentPageCaptureService = Depends(get_douyin_current_page_capture_service),
) -> DouyinCurrentPageCaptureResponse:
    try:
        summary = service.capture_current_page(
            account_connection_id=account_id,
            workspace_id=request.workspace_id,
            preset_name=request.preset_name,
            filter_config=_to_current_page_filter_config(request),
            persist=request.persist,
            max_videos=request.max_videos,
        )
        return DouyinCurrentPageCaptureResponse(**summary.__dict__)
    except ValueError as exc:
        if isinstance(exc, DouyinCurrentPageCaptureError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": exc.code, "message": exc.message, "stage": exc.stage, "diagnostics_id": exc.diagnostics_id},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_filter_config", "message": str(exc)},
        ) from exc


@router.post("/douyin-accounts/{account_id}/validate", response_model=DouyinAccountValidationResponse)
def validate_douyin_account(
    account_id: UUID,
    request: DouyinAccountValidateRequest | None = None,
    service: DouyinAccountService = Depends(get_douyin_account_service),
) -> DouyinAccountValidationResponse:
    try:
        account, valid, reason = service.validate_account(
            account_id,
            validation_url=request.validation_url if request else None,
            validation_source="manual_validate",
        )
        response = service.to_response(account)
        return DouyinAccountValidationResponse(
            account=response,
            valid=valid,
            status=account.status,
            reason=reason,
            douyin_user_id=account.douyin_user_id,
        )
    except DouyinAccountError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_account_http_detail(exc)) from exc


@router.post("/douyin-accounts/{account_id}/challenge-solved", response_model=DouyinAccountChallengeActionResponse)
def mark_douyin_account_challenge_solved(
    account_id: UUID,
    request: DouyinAccountValidateRequest | None = None,
    service: DouyinAccountService = Depends(get_douyin_account_service),
) -> DouyinAccountChallengeActionResponse:
    try:
        result = service.mark_challenge_solved(
            account_id,
            validation_url=request.validation_url if request else None,
        )
        response = service.to_response(result.account)
        alignment = response.browser_health_alignment
        return DouyinAccountChallengeActionResponse(
            account=response,
            action="challenge_solved_postcheck_completed",
            challenge_state=alignment.challenge_state if alignment else None,
            challenge_category=alignment.challenge_category if alignment else None,
            recommended_next_action=alignment.recommended_next_action if alignment else None,
            valid=result.valid,
            reason=result.reason,
            post_challenge_recheck_result=result.post_check_result,
            same_profile_reused=result.same_profile_reused,
            same_runtime_reused=result.same_runtime_reused,
            runtime_reopened_for_recheck=result.runtime_reopened_for_recheck,
            intake_ready_after_recheck=result.intake_ready_after_recheck,
        )
    except DouyinAccountError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_account_http_detail(exc)) from exc


@router.post("/douyin-accounts/{account_id}/challenge-recheck", response_model=DouyinAccountChallengeActionResponse)
def recheck_douyin_account_challenge(
    account_id: UUID,
    request: DouyinAccountValidateRequest | None = None,
    service: DouyinAccountService = Depends(get_douyin_account_service),
) -> DouyinAccountChallengeActionResponse:
    try:
        result = service.recheck_challenge_after_solve(
            account_id,
            validation_url=request.validation_url if request else None,
        )
        response = service.to_response(result.account)
        alignment = response.browser_health_alignment
        return DouyinAccountChallengeActionResponse(
            account=response,
            action="challenge_rechecked",
            challenge_state=alignment.challenge_state if alignment else None,
            challenge_category=alignment.challenge_category if alignment else None,
            recommended_next_action=alignment.recommended_next_action if alignment else None,
            valid=result.valid,
            reason=result.reason,
            post_challenge_recheck_result=result.post_check_result,
            same_profile_reused=result.same_profile_reused,
            same_runtime_reused=result.same_runtime_reused,
            runtime_reopened_for_recheck=result.runtime_reopened_for_recheck,
            intake_ready_after_recheck=result.intake_ready_after_recheck,
        )
    except DouyinAccountError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_account_http_detail(exc)) from exc


@router.post("/douyin-accounts/{account_id}/revalidate-job", response_model=DouyinAccountRevalidateJobResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_revalidate_douyin_account(
    account_id: UUID,
    job_service: JobService = Depends(get_job_service),
) -> DouyinAccountRevalidateJobResponse:
    job = job_service.create_job(
        job_type=JobType.VALIDATE_DOUYIN_ACCOUNT,
        payload_json={"douyin_account_connection_id": str(account_id)},
        reference_type="douyin_account_connection",
        reference_id=account_id,
    )
    return DouyinAccountRevalidateJobResponse(job_id=job.id, job_type=job.job_type.value, queued_accounts_count=1)


@router.post("/douyin-accounts/{account_id}/disable", response_model=DouyinAccountResponse)
def disable_douyin_account(
    account_id: UUID,
    service: DouyinAccountService = Depends(get_douyin_account_service),
) -> DouyinAccountResponse:
    try:
        return service.to_response(service.disable_account(account_id))
    except DouyinAccountError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/douyin-accounts/{account_id}", response_model=DouyinAccountDeleteResponse)
def delete_douyin_account(
    account_id: UUID,
    service: DouyinAccountService = Depends(get_douyin_account_service),
) -> DouyinAccountDeleteResponse:
    try:
        return service.delete_account(account_id)
    except DouyinAccountError as exc:
        detail = str(exc)
        if detail == "account_delete_blocked_active_browser_connect_session":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail) from exc
