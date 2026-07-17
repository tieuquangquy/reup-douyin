from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.schemas.tts import (
    SubtitleListResponse,
    SubtitleSegmentResponse,
    TtsCreateRequest,
    TtsCreateResponse,
    TtsSummaryResponse,
)
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.services.tts_service import TtsPipelineService
from src.tts_pipeline.types import TtsRequest, VoiceConfig

router = APIRouter(tags=["tts"])


def get_tts_service(db: Session = Depends(get_db_session)) -> TtsPipelineService:
    return TtsPipelineService(db)


@router.post("/tts", response_model=TtsCreateResponse, status_code=status.HTTP_201_CREATED)
def create_tts_job(
    request: TtsCreateRequest,
    service: TtsPipelineService = Depends(get_tts_service),
) -> TtsCreateResponse:
    try:
        job = service.create_tts_job(
            TtsRequest(
                source_video_id=request.source_video_id,
                voice_config=VoiceConfig(
                    voice_id=request.voice_config.voice_id,
                    language_code=request.voice_config.language_code,
                    speaking_rate=request.voice_config.speaking_rate,
                ),
                force_refresh=request.force_refresh,
            )
        )
    except TtsPipelineError as exc:
        raise _tts_http_error(exc) from exc
    return TtsCreateResponse(job_id=job.id, status=job.status, source_video_id=request.source_video_id)


@router.get("/source-videos/{source_video_id}/subtitle", response_model=SubtitleListResponse)
def get_source_video_subtitle(
    source_video_id: UUID,
    service: TtsPipelineService = Depends(get_tts_service),
) -> SubtitleListResponse:
    segments = service.get_subtitle_segments(source_video_id)
    return SubtitleListResponse(
        source_video_id=source_video_id,
        subtitle_version=segments[0].subtitle_version if segments else None,
        segments=[SubtitleSegmentResponse.model_validate(segment) for segment in segments],
    )


@router.get("/source-videos/{source_video_id}/tts-summary", response_model=TtsSummaryResponse)
def get_source_video_tts_summary(
    source_video_id: UUID,
    service: TtsPipelineService = Depends(get_tts_service),
) -> TtsSummaryResponse:
    summary = service.get_tts_summary(source_video_id)
    return TtsSummaryResponse(
        source_video_id=UUID(summary["source_video_id"]),
        tts_asset_count=summary["tts_asset_count"],
        subtitle_count=summary["subtitle_count"],
        warnings=summary["warnings"],
        clips=summary.get("clips") or [],
        timing_fit_summary=summary.get("timing_fit_summary") or {},
        assets=summary["assets"],
    )


@router.get("/source-videos/{source_video_id}/render-prep-manifest")
def get_source_video_render_prep_manifest(
    source_video_id: UUID,
    service: TtsPipelineService = Depends(get_tts_service),
) -> dict:
    return service.get_render_prep_manifest(source_video_id)


def _tts_http_error(exc: TtsPipelineError) -> HTTPException:
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    if exc.code in {
        TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
        TtsPipelineErrorCode.CLIP_PERSIST_FAILED,
        TtsPipelineErrorCode.NARRATION_ASSEMBLY_FAILED,
        TtsPipelineErrorCode.SUBTITLE_BUILD_FAILED,
        TtsPipelineErrorCode.MANIFEST_BUILD_FAILED,
        TtsPipelineErrorCode.PERSISTENCE_FAILED,
    }:
        http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    return HTTPException(status_code=http_status, detail={"code": exc.code, "message": exc.message})
