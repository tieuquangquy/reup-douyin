"""OCR / hard-sub analysis API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.enums import JobStatus
from src.media_pipeline.frame_sampling.ffmpeg_engine import normalize_sample_fps
from src.media_pipeline.frame_sampling.errors import FrameSamplingError
from src.ocr_pipeline.errors import OcrPipelineError, OcrPipelineErrorCode
from src.ocr_pipeline.services.ocr_service import OcrPipelineService
from src.ocr_pipeline.types import OcrRequest

router = APIRouter(tags=["ocr"])


class OcrCreateRequest(BaseModel):
    source_video_id: UUID
    force_refresh: bool = False
    # STRICT: only 1 or 2 fps (media_pipeline.frame_sampling).
    sample_fps: float = Field(default=1.0)
    hard_sub_band_ratio: float = Field(default=0.28, ge=0.1, le=0.5)
    clean_hardsub: bool = True

    @field_validator("sample_fps")
    @classmethod
    def _strict_sample_fps(cls, value: float) -> float:
        try:
            return float(normalize_sample_fps(value))
        except FrameSamplingError as exc:
            raise ValueError(exc.message) from exc


class OcrCreateResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    source_video_id: UUID


class OcrSummaryResponse(BaseModel):
    source_video_id: UUID
    pipeline_version: str | None = None
    provider: str | None = None
    text_object_count: int = 0
    frame_detection_count: int = 0
    hardsub_events: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    cleaned_video_asset_id: str | None = None
    ocr_events_asset_id: str | None = None
    visual_approved: bool = False


def get_ocr_service(db: Session = Depends(get_db_session)) -> OcrPipelineService:
    return OcrPipelineService(db)


@router.post("/ocr", response_model=OcrCreateResponse, status_code=status.HTTP_201_CREATED)
def create_ocr_job(
    request: OcrCreateRequest,
    service: OcrPipelineService = Depends(get_ocr_service),
) -> OcrCreateResponse:
    try:
        job = service.create_ocr_job(
            OcrRequest(
                source_video_id=request.source_video_id,
                force_refresh=request.force_refresh,
                sample_fps=request.sample_fps,
                hard_sub_band_ratio=request.hard_sub_band_ratio,
                clean_hardsub=request.clean_hardsub,
            )
        )
    except OcrPipelineError as exc:
        raise _ocr_http_error(exc) from exc
    return OcrCreateResponse(job_id=job.id, status=job.status, source_video_id=request.source_video_id)


@router.get("/source-videos/{source_video_id}/ocr-summary", response_model=OcrSummaryResponse)
def get_ocr_summary(
    source_video_id: UUID,
    service: OcrPipelineService = Depends(get_ocr_service),
) -> OcrSummaryResponse:
    summary = service.get_ocr_summary(source_video_id)
    return OcrSummaryResponse(
        source_video_id=UUID(summary["source_video_id"]),
        pipeline_version=summary.get("pipeline_version"),
        provider=summary.get("provider"),
        text_object_count=summary.get("text_object_count") or 0,
        frame_detection_count=summary.get("frame_detection_count") or 0,
        hardsub_events=summary.get("hardsub_events") or [],
        warnings=summary.get("warnings") or [],
        cleaned_video_asset_id=summary.get("cleaned_video_asset_id"),
        ocr_events_asset_id=summary.get("ocr_events_asset_id"),
        visual_approved=bool(summary.get("visual_approved")),
    )


@router.post("/source-videos/{source_video_id}/ocr-visual-approve", response_model=OcrSummaryResponse)
def approve_ocr_visual(
    source_video_id: UUID,
    service: OcrPipelineService = Depends(get_ocr_service),
) -> OcrSummaryResponse:
    try:
        summary = service.approve_visual(source_video_id)
    except OcrPipelineError as exc:
        raise _ocr_http_error(exc) from exc
    return OcrSummaryResponse(
        source_video_id=UUID(summary["source_video_id"]),
        pipeline_version=summary.get("pipeline_version"),
        provider=summary.get("provider"),
        text_object_count=summary.get("text_object_count") or 0,
        frame_detection_count=summary.get("frame_detection_count") or 0,
        hardsub_events=summary.get("hardsub_events") or [],
        warnings=summary.get("warnings") or [],
        cleaned_video_asset_id=summary.get("cleaned_video_asset_id"),
        ocr_events_asset_id=summary.get("ocr_events_asset_id"),
        visual_approved=bool(summary.get("visual_approved")),
    )


def _ocr_http_error(exc: OcrPipelineError) -> HTTPException:
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    if exc.code in {
        OcrPipelineErrorCode.FRAME_SAMPLE_FAILED,
        OcrPipelineErrorCode.OCR_PROVIDER_FAILED,
        OcrPipelineErrorCode.CLEAN_HARD_SUB_FAILED,
        OcrPipelineErrorCode.PERSISTENCE_FAILED,
    }:
        http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    return HTTPException(status_code=http_status, detail={"code": exc.code, "message": exc.message})
