from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from src.audio_pipeline.errors import AudioAnalysisError, AudioAnalysisErrorCode
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.services.transcript_edit_service import SegmentEdit, TranscriptEditService
from src.audio_pipeline.types import AudioAnalysisRequest
from src.db.session import get_db_session
from src.enums import JobType
from src.schemas.audio_analysis import (
    ApproveSourceTranscriptResponse,
    ApproveTranslationDraftRequest,
    ApproveTranslationDraftResponse,
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
from src.services.frontend_core_runtime import (
    FrontendCoreRuntimeError,
    assert_expected_stage_version,
)

router = APIRouter(tags=["audio-analysis"])


def get_audio_analysis_service(db: Session = Depends(get_db_session)) -> AudioAnalysisService:
    return AudioAnalysisService(db)


def get_transcript_edit_service(db: Session = Depends(get_db_session)) -> TranscriptEditService:
    return TranscriptEditService(db)


@router.post("/audio-analysis", response_model=AudioAnalysisCreateResponse, status_code=status.HTTP_201_CREATED)
def create_audio_analysis(
    request: AudioAnalysisCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    service: AudioAnalysisService = Depends(get_audio_analysis_service),
) -> AudioAnalysisCreateResponse:
    try:
        runtime_version = assert_expected_stage_version(
            JobType.ANALYZE_AUDIO, request.expected_stage_version
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    supplied_key = (idempotency_key or "").strip()
    if len(supplied_key) > 240:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Idempotency-Key is too long",
        )
    try:
        job = service.create_analysis_job(
            AudioAnalysisRequest(
                source_video_id=request.source_video_id,
                translation_preset=request.translation_preset,
                force_refresh=request.force_refresh,
                skip_translation=request.skip_translation,
            ),
            idempotency_key=supplied_key or None,
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AudioAnalysisError as exc:
        raise _audio_http_error(exc) from exc
    return AudioAnalysisCreateResponse(
        job_id=job.id,
        status=job.status,
        source_video_id=request.source_video_id,
        translation_preset=request.translation_preset,
        runtime_version=runtime_version,
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
    quality_contract = service.get_translation_quality_contract(source_video_id)
    return TranslationDraftListResponse(
        source_video_id=source_video_id,
        translation_preset=segments[0].translation_preset if segments else None,
        segments=[TranslationSegmentResponse.model_validate(segment) for segment in segments],
        recipe_version=str(quality_contract.get("recipe_version") or "") or None,
        quality_contract=quality_contract or None,
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
        has_speech=summary.get("has_speech"),
        dialogue_phase=summary.get("dialogue_phase"),
        audio_recipe_version=summary.get("audio_recipe_version"),
        analysis_metrics=dict(summary.get("analysis_metrics") or {}),
        target_speech_authority=dict(summary.get("target_speech_authority") or {}),
        dialogue_quality_contract=dict(summary.get("dialogue_quality_contract") or {}),
        semantic_dialogue_segmentation=dict(
            summary.get("semantic_dialogue_segmentation") or {}
        ),
        translation_recipe_version=summary.get("translation_recipe_version"),
        downstream_authority_invalidations=list(
            summary.get("downstream_authority_invalidations") or []
        ),
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    service: TranscriptEditService = Depends(get_transcript_edit_service),
) -> AudioAnalysisCreateResponse:
    try:
        runtime_version = assert_expected_stage_version(
            JobType.BUILD_TRANSLATION_DRAFT, request.expected_stage_version
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    supplied_key = (idempotency_key or "").strip()
    if len(supplied_key) > 240:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Idempotency-Key is too long",
        )
    try:
        job = service.create_rerun_job(
            source_video_id,
            translation_preset=request.translation_preset,
            force_refresh=request.force_refresh,
            require_source_approved=request.require_source_approved,
            idempotency_key=supplied_key or None,
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AudioAnalysisError as exc:
        raise _audio_http_error(exc) from exc
    return AudioAnalysisCreateResponse(
        job_id=job.id,
        status=job.status,
        source_video_id=source_video_id,
        translation_preset=request.translation_preset,
        runtime_version=runtime_version,
    )


@router.post(
    "/source-videos/{source_video_id}/translation-draft/approve",
    response_model=ApproveTranslationDraftResponse,
)
def approve_source_video_translation_draft(
    source_video_id: UUID,
    request: ApproveTranslationDraftRequest,
    db: Session = Depends(get_db_session),
) -> ApproveTranslationDraftResponse:
    service = TranscriptEditService(db)
    try:
        result = service.approve_translation_draft(
            source_video_id,
            operator_id=request.operator_id,
            commit=False,
        )
        from src.services.reup_pipeline_orchestrator import ReupPipelineOrchestrator

        resumed, job_id = ReupPipelineOrchestrator(db).resume_translation_approved_items(
            source_video_id=source_video_id
        )
        # Analyze OCR may already have completed its expensive Phase 1 while
        # waiting for approved dialogue meaning.  Resume only the hash-bound
        # Phase-2 handoff after approval; do not force another video scan.
        from src.ocr_pipeline.services.ocr_service import OcrPipelineService
        from src.ocr_pipeline.types import OcrRequest
        from src.services.quality_localization_service import (
            QUALITY_ANALYSIS_ENGINE,
            QUALITY_WORKFLOW_VERSION,
            QualityLocalizationService,
        )

        quality = QualityLocalizationService(db).summary(source_video_id)
        ocr_resume_job_id = None
        if quality.get("requires_dialogue_translation_approval"):
            ocr_job = OcrPipelineService(db).create_ocr_job(
                OcrRequest(
                    source_video_id=source_video_id,
                    force_refresh=False,
                    clean_hardsub=True,
                    use_master_phase1=True,
                    workflow_version=QUALITY_WORKFLOW_VERSION,
                    workflow_action="resume_dialogue_translation",
                    analysis_engine=QUALITY_ANALYSIS_ENGINE,
                ),
                commit=False,
            )
            ocr_resume_job_id = ocr_job.id
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return ApproveTranslationDraftResponse(
        source_video_id=source_video_id,
        approved_segments=int(result["approved_segments"]),
        binding_sha256=str(result["binding_sha256"]),
        resumed_queue_items=resumed,
        job_id=job_id,
        ocr_resume_job_id=ocr_resume_job_id,
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
