from __future__ import annotations

from uuid import UUID
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.enums import JobType
from src.render_pipeline.errors import RenderPipelineError, RenderPipelineErrorCode
from src.render_pipeline.services.render_service import RenderService
from src.render_pipeline.types import RenderRequest
from src.schemas.renders import RenderCreateRequest, RenderCreateResponse, RenderListResponse, RenderOutputResponse
from src.services.frontend_core_runtime import (
    FrontendCoreRuntimeError,
    assert_expected_stage_version,
)

router = APIRouter(tags=["renders"])


class QualityHandoffResponse(BaseModel):
    source_video_id: str
    workflow_version: str
    artifact_run_id: str | None = None
    final_approval_status: str
    metadata_status: str
    rights_status: str
    manual_export_status: str
    handoff_status: str
    next_gate: str | None = None
    publish_authorization_status: str | None = None
    external_publish_triggered: bool = False
    publish_draft: dict[str, Any] | None = None
    archive_path: str | None = None
    archive_sha256: str | None = None
    archive_size_bytes: int | None = None
    export_package_id: str | None = None
    publish_handoff_id: str | None = None


class QualityOperatorRequest(BaseModel):
    operator_id: str = "frontend_operator"


class QualityMetadataApprovalRequest(QualityOperatorRequest):
    target_platform: str = "FACEBOOK_REELS"
    title: str = Field(min_length=1)
    caption: str = ""
    cta_text: str = ""
    hashtags: list[str] = Field(default_factory=list)


class QualityRightsApprovalRequest(QualityOperatorRequest):
    source_video_reuse_authorized: bool
    retained_music_use_authorized: bool
    operator_accepts_responsibility: bool


def get_render_service(db: Session = Depends(get_db_session)) -> RenderService:
    return RenderService(db)


def _render_response(service: RenderService, render) -> RenderOutputResponse:
    return service.to_render_response(render)


@router.post("/renders", response_model=RenderCreateResponse, status_code=status.HTTP_201_CREATED)
def create_render_job(request: RenderCreateRequest, service: RenderService = Depends(get_render_service)) -> RenderCreateResponse:
    try:
        runtime_version = assert_expected_stage_version(
            JobType.RENDER_FINAL, request.expected_stage_version
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    try:
        job = service.create_render_job(
            RenderRequest(source_video_id=request.source_video_id, render_mode=request.render_mode, force_refresh=request.force_refresh)
        )
    except RenderPipelineError as exc:
        raise _render_http_error(exc) from exc
    return RenderCreateResponse(
        job_id=job.id,
        status=job.status,
        source_video_id=request.source_video_id,
        runtime_version=runtime_version,
    )


@router.get("/source-videos/{source_video_id}/renders", response_model=RenderListResponse)
def list_source_video_renders(source_video_id: UUID, service: RenderService = Depends(get_render_service)) -> RenderListResponse:
    return RenderListResponse(
        source_video_id=source_video_id,
        renders=[_render_response(service, render) for render in service.list_renders(source_video_id)],
    )


@router.get("/renders/{render_id}", response_model=RenderOutputResponse)
def get_render(render_id: UUID, service: RenderService = Depends(get_render_service)) -> RenderOutputResponse:
    try:
        return _render_response(service, service.get_render(render_id))
    except RenderPipelineError as exc:
        raise _render_http_error(exc) from exc


@router.post("/renders/{render_id}/approve", response_model=RenderOutputResponse)
def approve_render(render_id: UUID, service: RenderService = Depends(get_render_service)) -> RenderOutputResponse:
    try:
        return _render_response(service, service.approve_render(render_id))
    except RenderPipelineError as exc:
        raise _render_http_error(exc) from exc


@router.post("/renders/{render_id}/mark-publish-ready", response_model=RenderOutputResponse)
def mark_render_publish_ready(render_id: UUID, service: RenderService = Depends(get_render_service)) -> RenderOutputResponse:
    try:
        return _render_response(service, service.mark_publish_ready(render_id))
    except RenderPipelineError as exc:
        raise _render_http_error(exc) from exc


@router.get(
    "/source-videos/{source_video_id}/quality-handoff",
    response_model=QualityHandoffResponse,
)
def get_quality_handoff(
    source_video_id: UUID,
    db: Session = Depends(get_db_session),
) -> QualityHandoffResponse:
    from src.services.quality_handoff_service import QualityHandoffService

    return QualityHandoffResponse.model_validate(
        QualityHandoffService(db).summary(source_video_id)
    )


@router.post(
    "/source-videos/{source_video_id}/quality-handoff/final-approve",
    response_model=QualityHandoffResponse,
)
def approve_quality_final_handoff(
    source_video_id: UUID,
    request: QualityOperatorRequest,
    db: Session = Depends(get_db_session),
) -> QualityHandoffResponse:
    from src.services.quality_handoff_service import (
        QualityHandoffError,
        QualityHandoffService,
    )

    try:
        value = QualityHandoffService(db).approve_final(
            source_video_id, operator_id=request.operator_id
        )
    except QualityHandoffError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return QualityHandoffResponse.model_validate(value)


@router.post(
    "/source-videos/{source_video_id}/quality-handoff/metadata-approve",
    response_model=QualityHandoffResponse,
)
def approve_quality_metadata(
    source_video_id: UUID,
    request: QualityMetadataApprovalRequest,
    db: Session = Depends(get_db_session),
) -> QualityHandoffResponse:
    from src.services.quality_handoff_service import (
        QualityHandoffError,
        QualityHandoffService,
    )

    try:
        value = QualityHandoffService(db).approve_metadata(
            source_video_id,
            operator_id=request.operator_id,
            target_platform=request.target_platform,
            title=request.title,
            caption=request.caption,
            cta_text=request.cta_text,
            hashtags=request.hashtags,
        )
    except QualityHandoffError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return QualityHandoffResponse.model_validate(value)


@router.post(
    "/source-videos/{source_video_id}/quality-handoff/rights-approve",
    response_model=QualityHandoffResponse,
)
def approve_quality_rights(
    source_video_id: UUID,
    request: QualityRightsApprovalRequest,
    db: Session = Depends(get_db_session),
) -> QualityHandoffResponse:
    from src.services.quality_handoff_service import (
        QualityHandoffError,
        QualityHandoffService,
    )

    try:
        value = QualityHandoffService(db).approve_rights(
            source_video_id,
            operator_id=request.operator_id,
            source_video_reuse_authorized=request.source_video_reuse_authorized,
            retained_music_use_authorized=request.retained_music_use_authorized,
            operator_accepts_responsibility=request.operator_accepts_responsibility,
        )
    except QualityHandoffError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return QualityHandoffResponse.model_validate(value)


@router.post(
    "/source-videos/{source_video_id}/quality-handoff/manual-export",
    response_model=QualityHandoffResponse,
)
def finalize_quality_manual_export(
    source_video_id: UUID,
    request: QualityOperatorRequest,
    db: Session = Depends(get_db_session),
) -> QualityHandoffResponse:
    from src.services.quality_handoff_service import (
        QualityHandoffError,
        QualityHandoffService,
    )

    try:
        value = QualityHandoffService(db).finalize_manual_export(
            source_video_id, operator_id=request.operator_id
        )
    except QualityHandoffError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return QualityHandoffResponse.model_validate(value)


@router.get("/source-videos/{source_video_id}/latest-render", response_model=RenderOutputResponse | None)
def get_latest_source_video_render(source_video_id: UUID, service: RenderService = Depends(get_render_service)) -> RenderOutputResponse | None:
    render = service.latest_render(source_video_id)
    return _render_response(service, render) if render else None


def _render_http_error(exc: RenderPipelineError) -> HTTPException:
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    if exc.code in {
        RenderPipelineErrorCode.PROBE_FAILED,
        RenderPipelineErrorCode.AUDIO_PREPARE_FAILED,
        RenderPipelineErrorCode.SUBTITLE_BURN_PREPARE_FAILED,
        RenderPipelineErrorCode.EXPORT_FAILED,
        RenderPipelineErrorCode.OUTPUT_VALIDATION_FAILED,
        RenderPipelineErrorCode.PERSISTENCE_FAILED,
    }:
        http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    return HTTPException(status_code=http_status, detail={"code": exc.code, "message": exc.message})
