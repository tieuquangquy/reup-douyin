from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.audio_pipeline.errors import AudioAnalysisError, AudioAnalysisErrorCode
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.services.transcript_edit_service import SegmentEdit, TranscriptEditService
from src.audio_pipeline.types import AudioAnalysisRequest
from src.db.session import get_db_session
from src.schemas.audio_analysis import (
    ApproveSourceTranscriptResponse,
    AudioAnalysisCreateRequest,
    AudioAnalysisCreateResponse,
    AudioAnalysisSummaryResponse,
    MergeSegmentsRequest,
    RerunTranslationDraftRequest,
    SaveTranscriptDraftRequest,
    SplitSegmentRequest,
    TranscriptEditSummaryResponse,
    TranscriptListResponse,
    TranscriptSegmentResponse,
    TranslationDraftListResponse,
    TranslationSegmentResponse,
)

router = APIRouter(tags=["audio-analysis"])


def get_audio_analysis_service(db: Session = Depends(get_db_session)) -> AudioAnalysisService:
    return AudioAnalysisService(db)


def get_transcript_edit_service(db: Session = Depends(get_db_session)) -> TranscriptEditService:
    return TranscriptEditService(db)


@router.post("/audio-analysis", response_model=AudioAnalysisCreateResponse, status_code=status.HTTP_201_CREATED)
def create_audio_analysis(
    request: AudioAnalysisCreateRequest,
    service: AudioAnalysisService = Depends(get_audio_analysis_service),
) -> AudioAnalysisCreateResponse:
    try:
        job = service.create_analysis_job(
            AudioAnalysisRequest(
                source_video_id=request.source_video_id,
                translation_preset=request.translation_preset,
                force_refresh=request.force_refresh,
                skip_translation=request.skip_translation,
            )
        )
    except AudioAnalysisError as exc:
        raise _audio_http_error(exc) from exc
    return AudioAnalysisCreateResponse(
        job_id=job.id,
        status=job.status,
        source_video_id=request.source_video_id,
        translation_preset=request.translation_preset,
    )


@router.get("/source-videos/{source_video_id}/transcript", response_model=TranscriptListResponse)
def get_source_video_transcript(
    source_video_id: UUID,
    service: AudioAnalysisService = Depends(get_audio_analysis_service),
) -> TranscriptListResponse:
    segments = service.get_transcript_segments(source_video_id)
    return TranscriptListResponse(
        source_video_id=source_video_id,
        analysis_version=segments[0].analysis_version if segments else None,
        segments=[TranscriptSegmentResponse.model_validate(segment) for segment in segments],
    )


@router.get("/source-videos/{source_video_id}/translation-draft", response_model=TranslationDraftListResponse)
def get_source_video_translation_draft(
    source_video_id: UUID,
    service: AudioAnalysisService = Depends(get_audio_analysis_service),
) -> TranslationDraftListResponse:
    segments = service.get_translation_segments(source_video_id)
    return TranslationDraftListResponse(
        source_video_id=source_video_id,
        translation_preset=segments[0].translation_preset if segments else None,
        segments=[TranslationSegmentResponse.model_validate(segment) for segment in segments],
    )


@router.get("/source-videos/{source_video_id}/audio-analysis-summary", response_model=AudioAnalysisSummaryResponse)
def get_source_video_audio_analysis_summary(
    source_video_id: UUID,
    service: AudioAnalysisService = Depends(get_audio_analysis_service),
) -> AudioAnalysisSummaryResponse:
    try:
        summary = service.get_summary(source_video_id)
    except AudioAnalysisError as exc:
        raise _audio_http_error(exc) from exc
    return AudioAnalysisSummaryResponse(
        source_video_id=UUID(summary["source_video_id"]),
        analysis_version=summary["analysis_version"],
        transcript_count=summary["transcript_count"],
        translation_count=summary["translation_count"],
        asset_count=summary["asset_count"],
        manifest=summary["manifest"],
    )


@router.put("/source-videos/{source_video_id}/transcript-draft", response_model=TranscriptEditSummaryResponse)
def save_source_video_transcript_draft(
    source_video_id: UUID,
    request: SaveTranscriptDraftRequest,
    service: TranscriptEditService = Depends(get_transcript_edit_service),
) -> TranscriptEditSummaryResponse:
    try:
        result = service.save_draft(
            source_video_id,
            [
                SegmentEdit(
                    transcript_segment_id=segment.transcript_segment_id,
                    translation_segment_id=segment.translation_segment_id,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    source_text=segment.source_text,
                    translated_text=segment.translated_text,
                    status=segment.status,
                )
                for segment in request.segments
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return TranscriptEditSummaryResponse(
        source_video_id=source_video_id,
        updated_segments=result["updated_segments"],
        message="draft_saved",
    )


@router.post("/source-videos/{source_video_id}/transcript-draft/merge", response_model=TranscriptEditSummaryResponse)
def merge_source_video_transcript_segments(
    source_video_id: UUID,
    request: MergeSegmentsRequest,
    service: TranscriptEditService = Depends(get_transcript_edit_service),
) -> TranscriptEditSummaryResponse:
    try:
        service.merge_segments(
            source_video_id,
            request.left_transcript_segment_id,
            request.right_transcript_segment_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return TranscriptEditSummaryResponse(source_video_id=source_video_id, updated_segments=2, message="segments_merged")


@router.post("/source-videos/{source_video_id}/transcript-draft/split", response_model=TranscriptEditSummaryResponse)
def split_source_video_transcript_segment(
    source_video_id: UUID,
    request: SplitSegmentRequest,
    service: TranscriptEditService = Depends(get_transcript_edit_service),
) -> TranscriptEditSummaryResponse:
    try:
        service.split_segment(
            source_video_id,
            request.transcript_segment_id,
            split_ms=request.split_ms,
            left_source_text=request.left_source_text,
            right_source_text=request.right_source_text,
            left_translated_text=request.left_translated_text,
            right_translated_text=request.right_translated_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return TranscriptEditSummaryResponse(source_video_id=source_video_id, updated_segments=2, message="segment_split")


@router.post("/source-videos/{source_video_id}/transcript-draft/approve-source", response_model=ApproveSourceTranscriptResponse)
def approve_source_video_transcript(
    source_video_id: UUID,
    service: AudioAnalysisService = Depends(get_audio_analysis_service),
) -> ApproveSourceTranscriptResponse:
    try:
        result = service.approve_source_transcript(source_video_id)
    except AudioAnalysisError as exc:
        raise _audio_http_error(exc) from exc
    return ApproveSourceTranscriptResponse(
        source_video_id=source_video_id,
        approved_segments=int(result["approved_segments"]),
        dialogue_phase=str(result["dialogue_phase"]),
    )


@router.post("/source-videos/{source_video_id}/translation-draft/rerun", response_model=AudioAnalysisCreateResponse)
def rerun_source_video_translation_draft(
    source_video_id: UUID,
    request: RerunTranslationDraftRequest,
    service: TranscriptEditService = Depends(get_transcript_edit_service),
) -> AudioAnalysisCreateResponse:
    try:
        job = service.create_rerun_job(
            source_video_id,
            translation_preset=request.translation_preset,
            force_refresh=request.force_refresh,
            require_source_approved=request.require_source_approved,
        )
    except AudioAnalysisError as exc:
        raise _audio_http_error(exc) from exc
    return AudioAnalysisCreateResponse(
        job_id=job.id,
        status=job.status,
        source_video_id=source_video_id,
        translation_preset=request.translation_preset,
    )


def _audio_http_error(exc: AudioAnalysisError) -> HTTPException:
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    if exc.code in {
        AudioAnalysisErrorCode.AUDIO_EXTRACT_FAILED,
        AudioAnalysisErrorCode.SOURCE_SEPARATION_FAILED,
        AudioAnalysisErrorCode.TRANSCRIPTION_FAILED,
        AudioAnalysisErrorCode.TRANSLATION_FAILED,
        AudioAnalysisErrorCode.PERSISTENCE_FAILED,
    }:
        http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    return HTTPException(status_code=http_status, detail={"code": exc.code, "message": exc.message})
