from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.render_pipeline.errors import RenderPipelineError, RenderPipelineErrorCode
from src.render_pipeline.services.render_service import RenderService
from src.render_pipeline.types import RenderRequest
from src.schemas.renders import RenderCreateRequest, RenderCreateResponse, RenderListResponse, RenderOutputResponse

router = APIRouter(tags=["renders"])


def get_render_service(db: Session = Depends(get_db_session)) -> RenderService:
    return RenderService(db)


def _render_response(service: RenderService, render) -> RenderOutputResponse:
    return service.to_render_response(render)


@router.post("/renders", response_model=RenderCreateResponse, status_code=status.HTTP_201_CREATED)
def create_render_job(request: RenderCreateRequest, service: RenderService = Depends(get_render_service)) -> RenderCreateResponse:
    try:
        job = service.create_render_job(
            RenderRequest(source_video_id=request.source_video_id, render_mode=request.render_mode, force_refresh=request.force_refresh)
        )
    except RenderPipelineError as exc:
        raise _render_http_error(exc) from exc
    return RenderCreateResponse(job_id=job.id, status=job.status, source_video_id=request.source_video_id)


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
