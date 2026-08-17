"""OCR / hard-sub analysis API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from src.db.session import get_db_session
from src.enums import JobStatus, JobType
from src.media_pipeline.frame_sampling.ffmpeg_engine import normalize_sample_fps
from src.media_pipeline.frame_sampling.errors import FrameSamplingError
from src.ocr_pipeline.errors import OcrPipelineError, OcrPipelineErrorCode
from src.ocr_pipeline.services.ocr_service import OcrPipelineService
from src.ocr_pipeline.types import OcrRequest
from src.services.quality_localization_service import (
    QUALITY_ANALYSIS_ENGINE,
    QUALITY_WORKFLOW_VERSION,
    QualityLocalizationError,
    QualityLocalizationService,
)
from src.services.frontend_core_runtime import (
    FrontendCoreRuntimeError,
    assert_expected_stage_version,
)

router = APIRouter(tags=["ocr"])
OCR_RUNTIME_VERSION = assert_expected_stage_version(JobType.ANALYZE_OCR, None)


class OcrCreateRequest(BaseModel):
    source_video_id: UUID
    force_refresh: bool = False
    # STRICT: only 1 or 2 fps (media_pipeline.frame_sampling).
    sample_fps: float = Field(default=1.0)
    hard_sub_band_ratio: float = Field(default=0.28, ge=0.1, le=0.5)
    clean_hardsub: bool = True
    analysis_engine: str = QUALITY_ANALYSIS_ENGINE
    expected_stage_version: str | None = None

    @field_validator("analysis_engine")
    @classmethod
    def _supported_analysis_engine(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if normalized != QUALITY_ANALYSIS_ENGINE:
            raise ValueError("Unsupported local OCR analysis engine")
        return normalized

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
    runtime_version: str = OCR_RUNTIME_VERSION


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
    clean_produced: bool = False
    workflow_version: str | None = None
    workflow_stage: str = "NOT_STARTED"
    artifact_run_id: str | None = None
    phase1_tracks: int = 0
    phase2_model_version: str | None = None
    phase2_content_object_count: int = 0
    phase2_handoff_status: str = "NOT_STAGED"
    phase2_blocked_reasons: list[str] = Field(default_factory=list)
    dialogue_translation_blocked_count: int = 0
    requires_dialogue_translation_approval: bool = False
    local_recovery_summary: dict = Field(default_factory=dict)
    provenance_counts: dict[str, int] = Field(default_factory=dict)
    protected_source_tracks: int = 0
    provenance_artifact_path: str | None = None
    review_required: int = 0
    translation_review_required: int = 0
    review_objects: list[dict] = Field(default_factory=list)
    translation_objects: list[dict] = Field(default_factory=list)
    visual_preview_asset_id: str | None = None
    visual_preview_status: str = "NOT_STARTED"
    visual_preview_error_code: str | None = None
    visual_preview_error_message: str | None = None
    visual_preview_retryable: bool = False
    can_render_final: bool = False
    audio_review_status: str = "NOT_STAGED"
    audio_mix_review_status: str = "NOT_STAGED"
    audio_mix_preview_path: str | None = None
    audio_warnings: list[str] = Field(default_factory=list)
    timing_fit_summary: dict[str, int] = Field(default_factory=dict)
    residual_review_objects: list[dict] = Field(default_factory=list)
    residual_proposal_objects: list[dict] = Field(default_factory=list)
    residual_proposal_sha256: str | None = None
    residual_authority_sha256: str | None = None
    residual_translation_status: str = "NOT_REQUIRED"
    residual_translation_input_sha256: str | None = None
    residual_translation_suggestion_count: int = 0
    residual_normalization: dict = Field(default_factory=dict)
    analysis_engine: str | None = None
    analysis_recipe_release: str | None = None
    analysis_recipe_sha256: str | None = None
    pipeline_recipe_release: str | None = None
    pipeline_recipe_sha256: str | None = None
    analysis_metrics: dict = Field(default_factory=dict)
    analysis_mode: str | None = None
    audio_window_count: int = 0
    visual_trigger_count: int = 0
    all_frame_proxy_size: list[int] | None = None
    candidate_window_count: int = 0
    detector_frame_count: int = 0
    analysis_elapsed_s: float | None = None
    analysis_fallback_used: bool = False


class OcrDecision(BaseModel):
    content_id: str
    decision: str = "APPROVE"
    ocr_text_approved: str | None = None
    vi_text_approved: str | None = None


class OcrReviewRequest(BaseModel):
    decisions: list[OcrDecision]
    operator_id: str = "frontend_operator"
    expected_stage_version: str | None = None


class TranslationDecision(BaseModel):
    content_id: str
    vi_text: str


class TranslationReviewRequest(BaseModel):
    translations: list[TranslationDecision] = Field(default_factory=list)
    operator_id: str = "frontend_operator"
    expected_stage_version: str | None = None


class AudioReviewRequest(BaseModel):
    operator_id: str = "frontend_operator"


class ResidualSuggestion(BaseModel):
    content_id: str | None = None
    ocr_text: str
    ocr_text_corrected: str
    vi_text_suggested: str


class ResidualTriageRequest(BaseModel):
    suggestions: list[ResidualSuggestion]
    operator_id: str = "frontend_operator"
    expected_stage_version: str | None = None


class ResidualTranslationSuggestionRequest(BaseModel):
    operator_id: str = "frontend_operator"
    expected_stage_version: str | None = None


class ResidualApprovalRequest(BaseModel):
    proposal_sha256: str
    operator_id: str = "frontend_operator"
    expected_stage_version: str | None = None


def _summary_response(summary: dict) -> OcrSummaryResponse:
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
        clean_produced=bool(summary.get("clean_produced")),
        workflow_version=summary.get("workflow_version"),
        workflow_stage=str(summary.get("workflow_stage") or "NOT_STARTED"),
        artifact_run_id=summary.get("artifact_run_id"),
        phase1_tracks=int(summary.get("phase1_tracks") or 0),
        phase2_model_version=summary.get("phase2_model_version"),
        phase2_content_object_count=int(
            summary.get("phase2_content_object_count") or 0
        ),
        phase2_handoff_status=str(
            summary.get("phase2_handoff_status") or "NOT_STAGED"
        ),
        phase2_blocked_reasons=list(
            summary.get("phase2_blocked_reasons") or []
        ),
        dialogue_translation_blocked_count=int(
            summary.get("dialogue_translation_blocked_count") or 0
        ),
        requires_dialogue_translation_approval=bool(
            summary.get("requires_dialogue_translation_approval")
        ),
        local_recovery_summary=dict(
            summary.get("local_recovery_summary") or {}
        ),
        provenance_counts={
            str(key): int(value)
            for key, value in dict(summary.get("provenance_counts") or {}).items()
        },
        protected_source_tracks=int(summary.get("protected_source_tracks") or 0),
        provenance_artifact_path=summary.get("provenance_artifact_path"),
        review_required=int(summary.get("review_required") or 0),
        translation_review_required=int(
            summary.get("translation_review_required") or 0
        ),
        review_objects=list(summary.get("review_objects") or []),
        translation_objects=list(summary.get("translation_objects") or []),
        visual_preview_asset_id=summary.get("visual_preview_asset_id"),
        visual_preview_status=str(
            summary.get("visual_preview_status") or "NOT_STARTED"
        ),
        visual_preview_error_code=summary.get("visual_preview_error_code"),
        visual_preview_error_message=summary.get("visual_preview_error_message"),
        visual_preview_retryable=bool(summary.get("visual_preview_retryable")),
        can_render_final=bool(summary.get("can_render_final")),
        audio_review_status=str(summary.get("audio_review_status") or "NOT_STAGED"),
        audio_mix_review_status=str(
            summary.get("audio_mix_review_status") or "NOT_STAGED"
        ),
        audio_mix_preview_path=summary.get("audio_mix_preview_path"),
        audio_warnings=list(summary.get("audio_warnings") or []),
        timing_fit_summary=dict(summary.get("timing_fit_summary") or {}),
        residual_review_objects=list(summary.get("residual_review_objects") or []),
        residual_proposal_objects=list(summary.get("residual_proposal_objects") or []),
        residual_proposal_sha256=summary.get("residual_proposal_sha256"),
        residual_authority_sha256=summary.get("residual_authority_sha256"),
        residual_translation_status=str(
            summary.get("residual_translation_status") or "NOT_REQUIRED"
        ),
        residual_translation_input_sha256=summary.get(
            "residual_translation_input_sha256"
        ),
        residual_translation_suggestion_count=int(
            summary.get("residual_translation_suggestion_count") or 0
        ),
        residual_normalization=dict(summary.get("residual_normalization") or {}),
        analysis_engine=summary.get("analysis_engine"),
        analysis_recipe_release=summary.get("analysis_recipe_release"),
        analysis_recipe_sha256=summary.get("analysis_recipe_sha256"),
        pipeline_recipe_release=summary.get("pipeline_recipe_release"),
        pipeline_recipe_sha256=summary.get("pipeline_recipe_sha256"),
        analysis_metrics=dict(summary.get("analysis_metrics") or {}),
        analysis_mode=summary.get("analysis_mode"),
        audio_window_count=int(summary.get("audio_window_count") or 0),
        visual_trigger_count=int(summary.get("visual_trigger_count") or 0),
        all_frame_proxy_size=(
            [int(value) for value in summary.get("all_frame_proxy_size")]
            if isinstance(summary.get("all_frame_proxy_size"), list)
            and len(summary["all_frame_proxy_size"]) == 2
            else None
        ),
        candidate_window_count=int(summary.get("candidate_window_count") or 0),
        detector_frame_count=int(summary.get("detector_frame_count") or 0),
        analysis_elapsed_s=summary.get("analysis_elapsed_s"),
        analysis_fallback_used=bool(summary.get("analysis_fallback_used")),
    )


def get_ocr_service(db: Session = Depends(get_db_session)) -> OcrPipelineService:
    return OcrPipelineService(db)


@router.post("/ocr", response_model=OcrCreateResponse, status_code=status.HTTP_201_CREATED)
def create_ocr_job(
    request: OcrCreateRequest,
    service: OcrPipelineService = Depends(get_ocr_service),
) -> OcrCreateResponse:
    try:
        runtime_version = assert_expected_stage_version(
            JobType.ANALYZE_OCR, request.expected_stage_version
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    service_db = getattr(service, "db", None)
    if not request.force_refresh and service_db is not None:
        quality = QualityLocalizationService(service_db).summary(
            request.source_video_id
        )
        if quality.get("requires_dialogue_translation_approval"):
            blocked = int(
                quality.get("dialogue_translation_blocked_count") or 0
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"OCR analysis is already complete. Approve {blocked} "
                    "dialogue translation object(s) to resume Phase 2; "
                    "re-analysis is not required."
                ),
            )
    try:
        job = service.create_ocr_job(
            OcrRequest(
                source_video_id=request.source_video_id,
                force_refresh=request.force_refresh,
                sample_fps=request.sample_fps,
                hard_sub_band_ratio=request.hard_sub_band_ratio,
                clean_hardsub=request.clean_hardsub,
                use_master_phase1=True,
                workflow_version=QUALITY_WORKFLOW_VERSION,
                analysis_engine=request.analysis_engine,
            )
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except OcrPipelineError as exc:
        raise _ocr_http_error(exc) from exc
    return OcrCreateResponse(
        job_id=job.id,
        status=job.status,
        source_video_id=request.source_video_id,
        runtime_version=runtime_version,
    )


@router.get("/source-videos/{source_video_id}/ocr-summary", response_model=OcrSummaryResponse)
def get_ocr_summary(
    source_video_id: UUID,
    service: OcrPipelineService = Depends(get_ocr_service),
) -> OcrSummaryResponse:
    summary = service.get_ocr_summary(source_video_id)
    quality = QualityLocalizationService(service.db).summary(source_video_id)
    summary.update(quality)
    return _summary_response(summary)


def _validate_ocr_review_decisions(decisions: list[OcrDecision]) -> None:
    """Reject impossible OCR approvals before creating a durable worker job."""

    allowed = {"APPROVE", "EDIT", "PRESERVE_SOURCE", "REJECT_UI"}
    for row in decisions:
        content_id = str(row.content_id or "").strip() or "unknown"
        decision = str(row.decision or "APPROVE").strip().upper()
        if decision not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported OCR decision {decision!r} for {content_id}",
            )
        approved_text = str(row.ocr_text_approved or "").strip()
        if decision in {"APPROVE", "EDIT"} and not approved_text:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"OCR decision {decision} for {content_id} requires non-empty approved text. "
                    "Use EDIT with corrected text, PRESERVE_SOURCE, or REJECT_UI."
                ),
            )


@router.post(
    "/source-videos/{source_video_id}/ocr-review",
    response_model=OcrCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_ocr_review(
    source_video_id: UUID,
    request: OcrReviewRequest,
    service: OcrPipelineService = Depends(get_ocr_service),
) -> OcrCreateResponse:
    _validate_ocr_review_decisions(request.decisions)
    try:
        runtime_version = assert_expected_stage_version(
            JobType.ANALYZE_OCR, request.expected_stage_version
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    try:
        job = service.create_ocr_job(
            OcrRequest(
                source_video_id=source_video_id,
                force_refresh=False,
                clean_hardsub=False,
                use_master_phase1=True,
                workflow_version=QUALITY_WORKFLOW_VERSION,
                workflow_action="approve_ocr",
                review_decisions=[row.model_dump() for row in request.decisions],
                operator_id=request.operator_id,
                analysis_engine=QUALITY_ANALYSIS_ENGINE,
            )
        )
    except (OcrPipelineError, QualityLocalizationError) as exc:
        if isinstance(exc, OcrPipelineError):
            raise _ocr_http_error(exc) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OcrCreateResponse(
        job_id=job.id,
        status=job.status,
        source_video_id=source_video_id,
        runtime_version=runtime_version,
    )


@router.post(
    "/source-videos/{source_video_id}/translation-review",
    response_model=OcrCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_translation_review(
    source_video_id: UUID,
    request: TranslationReviewRequest,
    db: Session = Depends(get_db_session),
) -> OcrCreateResponse:
    try:
        runtime_version = assert_expected_stage_version(
            JobType.RENDER_PREVIEW, request.expected_stage_version
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    try:
        job = QualityLocalizationService(db).create_preview_job(
            source_video_id,
            translations=[row.model_dump() for row in request.translations],
            operator_id=request.operator_id,
        )
    except QualityLocalizationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OcrCreateResponse(
        job_id=job.id,
        status=job.status,
        source_video_id=source_video_id,
        runtime_version=runtime_version,
    )


@router.post("/source-videos/{source_video_id}/ocr-visual-approve", response_model=OcrSummaryResponse)
def approve_ocr_visual(
    source_video_id: UUID,
    service: OcrPipelineService = Depends(get_ocr_service),
) -> OcrSummaryResponse:
    try:
        summary = service.get_ocr_summary(source_video_id)
        quality = QualityLocalizationService(service.db)
        quality_summary = quality.summary(source_video_id)
        if quality_summary.get("workflow_stage") != "NOT_STARTED":
            quality.approve_visual(source_video_id, operator_id="frontend_operator")
            service.db.commit()
            summary.update(quality.summary(source_video_id))
        else:
            summary = service.approve_visual(source_video_id)
    except QualityLocalizationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _summary_response(summary)


@router.post(
    "/source-videos/{source_video_id}/audio-review-approve",
    response_model=OcrSummaryResponse,
)
def approve_quality_audio_review(
    source_video_id: UUID,
    request: AudioReviewRequest,
    db: Session = Depends(get_db_session),
) -> OcrSummaryResponse:
    try:
        quality = QualityLocalizationService(db)
        summary = quality.approve_audio_review(
            source_video_id, operator_id=request.operator_id
        )
        from src.services.reup_pipeline_orchestrator import ReupPipelineOrchestrator

        ReupPipelineOrchestrator(db).resume_quality_approved_items(
            source_video_id=source_video_id
        )
        db.commit()
        return _summary_response(summary)
    except QualityLocalizationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/source-videos/{source_video_id}/residual-translation-suggestions",
    response_model=OcrCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_residual_translation_suggestions(
    source_video_id: UUID,
    request: ResidualTranslationSuggestionRequest,
    db: Session = Depends(get_db_session),
) -> OcrCreateResponse:
    try:
        runtime_version = assert_expected_stage_version(
            JobType.RENDER_PREVIEW, request.expected_stage_version
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    try:
        job = QualityLocalizationService(db).create_residual_review_job(
            source_video_id,
            action="suggest_residual_translation",
            operator_id=request.operator_id,
        )
        return OcrCreateResponse(
            job_id=job.id,
            status=job.status,
            source_video_id=source_video_id,
            runtime_version=runtime_version,
        )
    except QualityLocalizationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/source-videos/{source_video_id}/residual-triage",
    response_model=OcrCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_residual_triage(
    source_video_id: UUID,
    request: ResidualTriageRequest,
    db: Session = Depends(get_db_session),
) -> OcrCreateResponse:
    try:
        runtime_version = assert_expected_stage_version(
            JobType.RENDER_PREVIEW, request.expected_stage_version
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    try:
        job = QualityLocalizationService(db).create_residual_review_job(
            source_video_id,
            action="build_residual_proposal",
            suggestions=[row.model_dump() for row in request.suggestions],
            operator_id=request.operator_id,
        )
        return OcrCreateResponse(
            job_id=job.id,
            status=job.status,
            source_video_id=source_video_id,
            runtime_version=runtime_version,
        )
    except QualityLocalizationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/source-videos/{source_video_id}/residual-review-approve",
    response_model=OcrCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def approve_residual_review(
    source_video_id: UUID,
    request: ResidualApprovalRequest,
    db: Session = Depends(get_db_session),
) -> OcrCreateResponse:
    try:
        runtime_version = assert_expected_stage_version(
            JobType.RENDER_PREVIEW, request.expected_stage_version
        )
    except FrontendCoreRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    try:
        job = QualityLocalizationService(db).create_residual_review_job(
            source_video_id,
            action="approve_residual_proposal",
            proposal_sha256=request.proposal_sha256,
            operator_id=request.operator_id,
        )
        return OcrCreateResponse(
            job_id=job.id,
            status=job.status,
            source_video_id=source_video_id,
            runtime_version=runtime_version,
        )
    except QualityLocalizationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/source-videos/{source_video_id}/localization-artifacts/{artifact_path:path}")
def get_localization_artifact(
    source_video_id: UUID,
    artifact_path: str,
    db: Session = Depends(get_db_session),
):
    try:
        path = QualityLocalizationService(db).artifact_path(
            source_video_id, artifact_path
        )
    except QualityLocalizationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path)


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
