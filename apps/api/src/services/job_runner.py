from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from src.enums import JobStatus, JobStepStatus, SourcePlatformEnum
from src.models.jobs import Job, JobStep
from src.services.job_service import JobService
from src.services.reup_queue_download_sync import sync_reup_queue_from_download_job

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StepHandlerResult:
    status: JobStepStatus = JobStepStatus.COMPLETED
    progress_percent: int = 100
    output_json: dict | None = None
    error_code: str | None = None
    error_message: str | None = None


class StepHandler(Protocol):
    def handle(self, job: Job, step: JobStep) -> StepHandlerResult:
        ...


class PlaceholderStepHandler:
    def handle(self, job: Job, step: JobStep) -> StepHandlerResult:
        return StepHandlerResult(
            output_json={
                "placeholder": True,
                "job_type": job.job_type,
                "step_key": step.step_key,
            }
        )


class StepHandlerRegistry:
    def __init__(self, default_handler: StepHandler | None = None):
        self.default_handler = default_handler or PlaceholderStepHandler()
        self._handlers: dict[tuple[str, str], StepHandler] = {}

    def register(self, job_type: str, step_key: str, handler: StepHandler) -> None:
        self._handlers[(job_type, step_key)] = handler

    def get(self, job_type: str, step_key: str) -> StepHandler:
        return self._handlers.get((job_type, step_key), self.default_handler)


class JobRunner:
    def __init__(self, db: Session, handlers: StepHandlerRegistry | None = None):
        self.db = db
        self.handlers = handlers or StepHandlerRegistry()
        self.service = JobService(db)

    def release_orphaned_locks(self, worker_id: str) -> int:
        """
        Requeue RUNNING jobs still locked by this worker after a crash/restart.

        claim_next only picks QUEUED/RETRYABLE — without this, a mid-step crash leaves
        the job stuck in Ops as Running forever while the worker idles.
        """
        stmt = (
            select(Job)
            .where(Job.status == JobStatus.RUNNING)
            .where(Job.locked_by == worker_id)
            .options(selectinload(Job.steps))
        )
        jobs = list(self.db.scalars(stmt).all())
        if not jobs:
            return 0
        for job in jobs:
            for step in job.steps or []:
                if step.status == JobStepStatus.RUNNING:
                    self.service.transition_step(
                        step,
                        JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code="WORKER_ORPHANED",
                        error_message=(
                            "Worker restarted or crashed while this step was RUNNING; "
                            "job requeued automatically."
                        ),
                    )
            self.service.transition_job(
                job,
                JobStatus.RETRYABLE,
                error_code="WORKER_ORPHANED",
                error_message=(
                    "Worker restarted or crashed while job was RUNNING; "
                    "requeued for another attempt."
                ),
            )
            job.locked_by = None
            job.locked_at = None
            job.scheduled_at = None
            self.service.refresh_progress(job)
            logger.warning(
                "job_orphan_lock_released",
                extra={"job_id": str(job.id), "worker_id": worker_id},
            )
        self.db.commit()
        return len(jobs)

    def claim_next_job(self, worker_id: str) -> Job | None:
        now = datetime.now(UTC)
        stmt = (
            select(Job)
            .where(Job.status.in_([JobStatus.QUEUED, JobStatus.RETRYABLE]))
            .where(or_(Job.scheduled_at.is_(None), Job.scheduled_at <= now))
            .options(selectinload(Job.steps))
            .order_by(Job.priority.desc(), Job.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = self.db.scalar(stmt)
        if job is None:
            return None

        self.service.transition_job(job, JobStatus.RUNNING)
        for step in job.steps:
            if step.status == JobStepStatus.FAILED:
                self.service.transition_step(step, JobStepStatus.PENDING)
                step.error_code = None
                step.error_message = None
                step.progress_percent = 0
        job.locked_by = worker_id
        job.locked_at = now
        job.scheduled_at = None
        job.attempts += 1
        self.service.refresh_progress(job)
        self.db.commit()
        logger.info("job_claimed", extra={"job_id": str(job.id), "worker_id": worker_id})
        return self.service.get_job(job.id)

    def _is_cancelled(self, job: Job) -> bool:
        try:
            self.db.refresh(job)
        except Exception:
            # Unit tests and non-ORM objects still expose .status.
            pass
        return job.status == JobStatus.CANCELLED

    def _abort_cancelled_job(self, job: Job) -> Job:
        logger.info("job_aborted_cancelled", extra={"job_id": str(job.id)})
        job.locked_by = None
        job.locked_at = None
        self.service.refresh_progress(job)
        self.db.commit()
        return self.service.get_job(job.id)

    def run_job(self, job_id: UUID) -> Job:
        job = self.service.get_job(job_id)
        if job.status == JobStatus.QUEUED:
            self.service.transition_job(job, JobStatus.RUNNING)
        if job.status == JobStatus.CANCELLED:
            return self._abort_cancelled_job(job)
        if job.status != JobStatus.RUNNING:
            raise ValueError(f"Job must be RUNNING before execution, got {job.status}")

        for step in job.steps:
            if self._is_cancelled(job):
                return self._abort_cancelled_job(job)
            if step.status in {JobStepStatus.COMPLETED, JobStepStatus.SKIPPED}:
                continue
            if step.status == JobStepStatus.PENDING:
                self.service.transition_step(step, JobStepStatus.RUNNING, progress_percent=0)
                self.service.refresh_progress(job)
                self.db.commit()

            logger.info("job_step_start", extra={"job_id": str(job.id), "step_key": step.step_key})
            try:
                result = self.handlers.get(job.job_type, step.step_key).handle(job, step)
            except Exception as exc:
                logger.exception(
                    "job_step_unhandled_error",
                    extra={"job_id": str(job.id), "step_key": step.step_key},
                )
                result = StepHandlerResult(
                    status=JobStepStatus.FAILED,
                    progress_percent=0,
                    error_code="STEP_UNHANDLED_ERROR",
                    error_message=f"{type(exc).__name__}: {exc}"[:500],
                    output_json={"step_key": step.step_key},
                )

            if result.status == JobStepStatus.WAITING_FOR_INPUT:
                self.service.transition_step(step, JobStepStatus.WAITING_FOR_INPUT, progress_percent=result.progress_percent)
                self.service.transition_job(job, JobStatus.WAITING_FOR_REVIEW)
                self.service.refresh_progress(job)
                self.db.commit()
                return self.service.get_job(job.id)

            if str(job.job_type) == "CRAWL_PROFILE" and step.step_key == "finalize_session":
                from src.services.source_ingest_service import SourceIngestError, SourceIngestService

                payload = job.payload_json or {}
                profile_url = payload.get("profile_url")
                if not profile_url:
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code="missing_profile_url",
                        error_message="CRAWL_PROFILE job payload requires profile_url",
                    )
                else:
                    try:
                        source_platform = SourcePlatformEnum(payload.get("source_platform", SourcePlatformEnum.DOUYIN))
                        summary = SourceIngestService(self.db).ingest_profile(
                            workspace_id=job.workspace_id,
                            profile_url=str(profile_url),
                            source_platform=source_platform,
                            crawl_mode=payload.get("crawl_mode") or "worker_crawl_profile",
                            adapter_payload_json=payload.get("adapter_payload_json"),
                        )
                        job.crawl_session_id = UUID(str(summary.crawl_session_id))
                        result = StepHandlerResult(
                            output_json={
                                "crawl_session_id": str(summary.crawl_session_id),
                                "source_profile_id": str(summary.source_profile_id) if summary.source_profile_id else None,
                                "videos_discovered_count": summary.videos_discovered_count,
                                "videos_created_count": summary.videos_created_count,
                                "videos_updated_count": summary.videos_updated_count,
                                "snapshots_created_count": summary.snapshots_created_count,
                            }
                        )
                    except (SourceIngestError, ValueError) as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code=str(getattr(exc, "code", "crawl_profile_failed")),
                            error_message=getattr(exc, "message", str(exc)),
                            output_json={"profile_url": str(profile_url)},
                        )

            if str(job.job_type) == "VALIDATE_DOUYIN_ACCOUNT" and step.step_key == "validate_account":
                from src.services.douyin_account_service import DouyinAccountError, DouyinAccountService

                account_id = (job.payload_json or {}).get("douyin_account_connection_id")
                if account_id is None and job.reference_id is not None:
                    account_id = str(job.reference_id)
                if account_id is None:
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code="missing_douyin_account_connection_id",
                        error_message="VALIDATE_DOUYIN_ACCOUNT requires douyin_account_connection_id",
                    )
                else:
                    try:
                        account, valid, reason = DouyinAccountService(self.db).validate_account(
                            UUID(str(account_id)),
                            validation_source="auto_revalidate",
                        )
                        result = StepHandlerResult(
                            output_json={
                                "douyin_account_connection_id": str(account.id),
                                "valid": valid,
                                "status": account.status.value,
                                "health_status": account.health_status.value,
                                "reason": reason,
                            }
                        )
                    except DouyinAccountError as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code="douyin_account_validation_failed",
                            error_message=str(exc),
                        )

            if str(job.job_type) == "REVALIDATE_STALE_DOUYIN_ACCOUNTS" and step.step_key == "validate_accounts":
                from src.services.douyin_account_service import DouyinAccountService

                payload = job.payload_json or {}
                workspace_id = payload.get("workspace_id")
                accounts = DouyinAccountService(self.db).revalidate_due_accounts(
                    workspace_id=UUID(str(workspace_id)) if workspace_id else job.workspace_id,
                    due_only=bool(payload.get("due_only", True)),
                    validation_source="auto_revalidate",
                )
                result = StepHandlerResult(
                    output_json={
                        "accounts_updated": len(accounts),
                        "accounts": [
                            {
                                "douyin_account_connection_id": str(account.id),
                                "status": account.status.value,
                                "health_status": account.health_status.value,
                                "last_validation_status": account.last_validation_status,
                            }
                            for account in accounts
                        ],
                    }
                )

            if str(job.job_type) == "DOWNLOAD_VIDEO" and step.step_key == "register_assets":
                from src.downloaders.errors import DownloadError
                from src.services.download_service import DownloadService

                source_video_id = (job.payload_json or {}).get("source_video_id")
                if source_video_id is None and job.source_video_id is not None:
                    source_video_id = str(job.source_video_id)
                if source_video_id is not None:
                    try:
                        manifest = DownloadService(self.db).run_download(
                            UUID(str(source_video_id)),
                            job_id=job.id,
                            force_refresh=bool((job.payload_json or {}).get("force_refresh")),
                        )
                        result = StepHandlerResult(output_json={"manifest": manifest})
                    except DownloadError as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code=str(exc.code),
                            error_message=exc.message,
                            output_json={"source_video_id": str(source_video_id)},
                        )
                    except Exception as exc:
                        logger.exception(
                            "download_register_assets_unhandled_error",
                            extra={"job_id": str(job.id), "source_video_id": str(source_video_id)},
                        )
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code="download_unhandled_error",
                            error_message=f"{type(exc).__name__}: {exc}",
                            output_json={"source_video_id": str(source_video_id)},
                        )

            if str(job.job_type) == "ANALYZE_AUDIO" and step.step_key == "persist_outputs":
                from src.audio_pipeline.errors import AudioAnalysisError
                from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
                from src.audio_pipeline.types import AudioAnalysisRequest, TranslationPreset
                from src.services.job_service import utc_now

                source_video_id = (job.payload_json or {}).get("source_video_id")
                if source_video_id is None and job.source_video_id is not None:
                    source_video_id = str(job.source_video_id)
                if source_video_id is not None:
                    def _analysis_heartbeat(phase: str, progress_percent: int | None) -> None:
                        # Keep Ops Jobs "Updated" moving during long FunASR download/infer.
                        job.updated_at = utc_now()
                        meta = dict(step.metadata_json or {})
                        meta["analysis_phase"] = phase
                        step.metadata_json = meta
                        if progress_percent is not None:
                            step.progress_percent = max(0, min(99, int(progress_percent)))
                            self.service.refresh_progress(job)
                        self.db.commit()

                    try:
                        payload = job.payload_json or {}
                        analysis = AudioAnalysisService(self.db).run_analysis(
                            AudioAnalysisRequest(
                                source_video_id=UUID(str(source_video_id)),
                                translation_preset=TranslationPreset(
                                    payload.get("translation_preset", TranslationPreset.LITERAL_SAFE)
                                ),
                                force_refresh=bool(payload.get("force_refresh")),
                                skip_translation=bool(payload.get("skip_translation", True)),
                            ),
                            job_id=job.id,
                            on_phase=_analysis_heartbeat,
                        )
                        result = StepHandlerResult(
                            output_json={
                                "analysis_version": analysis.analysis_version,
                                "transcript_count": analysis.transcript_count,
                                "translation_count": analysis.translation_count,
                                "flags_summary": analysis.flags_summary,
                            }
                        )
                    except AudioAnalysisError as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code=exc.code,
                            error_message=exc.message,
                            output_json={"source_video_id": str(source_video_id)},
                        )

            if str(job.job_type) == "BUILD_TRANSLATION_DRAFT" and step.step_key == "translate_segments":
                from src.audio_pipeline.errors import AudioAnalysisError
                from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
                from src.audio_pipeline.types import TranslationPreset
                from src.services.job_service import utc_now

                source_video_id = (job.payload_json or {}).get("source_video_id")
                if source_video_id is None and job.source_video_id is not None:
                    source_video_id = str(job.source_video_id)
                if source_video_id is not None:
                    def _translation_heartbeat(phase: str, progress_percent: int | None) -> None:
                        job.updated_at = utc_now()
                        meta = dict(step.metadata_json or {})
                        meta["translation_phase"] = phase
                        step.metadata_json = meta
                        if progress_percent is not None:
                            step.progress_percent = max(0, min(99, int(progress_percent)))
                            self.service.refresh_progress(job)
                        self.db.commit()

                    try:
                        payload = job.payload_json or {}
                        analysis = AudioAnalysisService(self.db).run_translation_only(
                            UUID(str(source_video_id)),
                            translation_preset=TranslationPreset(
                                payload.get("translation_preset", TranslationPreset.LITERAL_SAFE)
                            ),
                            require_source_approved=bool(payload.get("require_source_approved", True)),
                            job_id=job.id,
                            on_progress=_translation_heartbeat,
                        )
                        if int(analysis.translation_count or 0) <= 0:
                            result = StepHandlerResult(
                                status=JobStepStatus.FAILED,
                                progress_percent=0,
                                error_code="translation_failed",
                                error_message=(
                                    "BUILD_TRANSLATION_DRAFT wrote 0 translation segments. "
                                    "Restart worker and verify translate_segments handler + LLM provider."
                                ),
                                output_json={"source_video_id": str(source_video_id)},
                            )
                        else:
                            result = StepHandlerResult(
                                output_json={
                                    "analysis_version": analysis.analysis_version,
                                    "transcript_count": analysis.transcript_count,
                                    "translation_count": analysis.translation_count,
                                    "flags_summary": analysis.flags_summary,
                                }
                            )
                    except AudioAnalysisError as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code=exc.code,
                            error_message=exc.message,
                            output_json={"source_video_id": str(source_video_id)},
                        )

            if str(job.job_type) == "SYNTHESIZE_TTS" and step.step_key == "persist_outputs":
                from src.tts_pipeline.errors import TtsPipelineError
                from src.tts_pipeline.services.tts_service import TtsPipelineService
                from src.tts_pipeline.types import TtsRequest, VoiceConfig

                source_video_id = (job.payload_json or {}).get("source_video_id")
                if source_video_id is None and job.source_video_id is not None:
                    source_video_id = str(job.source_video_id)
                if source_video_id is not None:
                    try:
                        voice_config_json = (job.payload_json or {}).get("voice_config") or {}
                        result_summary = TtsPipelineService(self.db).run_pipeline(
                            TtsRequest(
                                source_video_id=UUID(str(source_video_id)),
                                voice_config=VoiceConfig(
                                    voice_id=voice_config_json.get("voice_id", "vi_female_placeholder"),
                                    language_code=voice_config_json.get("language_code", "vi"),
                                    speaking_rate=float(voice_config_json.get("speaking_rate", 1.0)),
                                ),
                                force_refresh=bool((job.payload_json or {}).get("force_refresh")),
                            ),
                            job_id=job.id,
                        )
                        result = StepHandlerResult(
                            output_json={
                                "pipeline_version": result_summary.pipeline_version,
                                "subtitle_count": result_summary.subtitle_count,
                                "tts_clip_count": result_summary.tts_clip_count,
                                "timing_fit_summary": result_summary.timing_fit_summary,
                                "warnings": result_summary.warnings,
                            }
                        )
                    except TtsPipelineError as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code=exc.code,
                            error_message=exc.message,
                            output_json={"source_video_id": str(source_video_id)},
                        )

            if str(job.job_type) == "ANALYZE_OCR" and step.step_key == "persist_outputs":
                from src.ocr_pipeline.errors import OcrPipelineError
                from src.ocr_pipeline.services.ocr_service import OcrPipelineService
                from src.ocr_pipeline.types import OcrRequest
                from src.services.job_service import utc_now

                source_video_id = (job.payload_json or {}).get("source_video_id")
                if source_video_id is None and job.source_video_id is not None:
                    source_video_id = str(job.source_video_id)
                if source_video_id is not None:
                    def _ocr_heartbeat(phase: str, progress_percent: int | None) -> None:
                        job.updated_at = utc_now()
                        meta = dict(step.metadata_json or {})
                        meta["ocr_phase"] = phase
                        step.metadata_json = meta
                        if progress_percent is not None:
                            step.progress_percent = max(0, min(99, int(progress_percent)))
                            self.service.refresh_progress(job)
                        self.db.commit()

                    try:
                        payload = job.payload_json or {}
                        ocr_summary = OcrPipelineService(self.db).run_pipeline(
                            OcrRequest(
                                source_video_id=UUID(str(source_video_id)),
                                force_refresh=bool(payload.get("force_refresh")),
                                sample_fps=float(payload.get("sample_fps") or 1.0),
                                hard_sub_band_ratio=float(payload.get("hard_sub_band_ratio") or 0.28),
                                clean_hardsub=bool(payload.get("clean_hardsub", True)),
                            ),
                            job_id=job.id,
                            on_progress=_ocr_heartbeat,
                        )
                        result = StepHandlerResult(
                            output_json={
                                "pipeline_version": ocr_summary.pipeline_version,
                                "frame_count": ocr_summary.frame_count,
                                "detection_count": ocr_summary.detection_count,
                                "hardsub_event_count": ocr_summary.hardsub_event_count,
                                "cleaned_video_asset_id": ocr_summary.cleaned_video_asset_id,
                                "clean_produced": ocr_summary.clean_produced,
                                "warnings": ocr_summary.warnings,
                            }
                        )
                    except OcrPipelineError as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code=exc.code,
                            error_message=exc.message,
                            output_json={"source_video_id": str(source_video_id)},
                        )
                    except Exception as exc:
                        logger.exception(
                            "job_step_unhandled_error",
                            extra={"job_id": str(job.id), "step_key": step.step_key},
                        )
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code="STEP_UNHANDLED_ERROR",
                            error_message=f"{type(exc).__name__}: {exc}"[:500],
                            output_json={"source_video_id": str(source_video_id)},
                        )

            if str(job.job_type) == "RENDER_FINAL" and step.step_key == "persist_render_output":
                from src.render_pipeline.errors import RenderPipelineError
                from src.render_pipeline.services.render_service import RenderService
                from src.render_pipeline.types import RenderRequest

                source_video_id = (job.payload_json or {}).get("source_video_id")
                if source_video_id is None and job.source_video_id is not None:
                    source_video_id = str(job.source_video_id)
                if source_video_id is not None:
                    try:
                        render_result = RenderService(self.db).run_render(
                            RenderRequest(
                                source_video_id=UUID(str(source_video_id)),
                                render_mode=(job.payload_json or {}).get("render_mode", "final"),
                                force_refresh=bool((job.payload_json or {}).get("force_refresh")),
                            ),
                            job_id=job.id,
                        )
                        result = StepHandlerResult(
                            output_json={
                                "render_output_id": str(render_result.render_output_id),
                                "output_asset_id": str(render_result.output_asset_id),
                                "render_version": render_result.render_version,
                                "warnings": render_result.warnings,
                            }
                        )
                    except RenderPipelineError as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code=exc.code,
                            error_message=exc.message,
                            output_json={"source_video_id": str(source_video_id)},
                        )

            if str(job.job_type) == "PUBLISH_CONTENT" and step.step_key == "persist_result":
                from src.publish.services.publish_attempt_service import PublishAttemptError, PublishAttemptService
                from src.schemas.publish import PublishDraftPublishRequest

                publish_draft_id = (job.payload_json or {}).get("publish_draft_id")
                platform_account_id = (job.payload_json or {}).get("platform_account_id")
                if publish_draft_id and platform_account_id:
                    try:
                        attempt = PublishAttemptService(self.db).publish_now(
                            UUID(str(publish_draft_id)),
                            PublishDraftPublishRequest(
                                platform_account_id=UUID(str(platform_account_id)),
                                publish_mode=(job.payload_json or {}).get("publish_mode", "publish_now"),
                            ),
                        )
                        result = StepHandlerResult(
                            output_json={
                                "publish_attempt_id": str(attempt.id),
                                "status": attempt.status.value,
                                "external_reel_id": attempt.external_reel_id,
                            }
                        )
                    except PublishAttemptError as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code="publish_failed",
                            error_message=str(exc),
                            output_json={"publish_draft_id": str(publish_draft_id)},
                        )

            if str(job.job_type) == "REFRESH_PUBLISH_STATUS" and step.step_key == "persist_updates":
                from src.publish.services.publish_reconciliation_service import PublishReconciliationService

                publish_attempt_id = (job.payload_json or {}).get("publish_attempt_id")
                if publish_attempt_id:
                    try:
                        attempt = PublishReconciliationService(self.db).refresh_attempt(UUID(str(publish_attempt_id)))
                        result = StepHandlerResult(
                            output_json={
                                "publish_attempt_id": str(attempt.id),
                                "status": attempt.status.value,
                                "external_status": attempt.external_status.value,
                                "reconciliation_status": attempt.reconciliation_status.value,
                            }
                        )
                    except ValueError as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code="publish_status_refresh_failed",
                            error_message=str(exc),
                            output_json={"publish_attempt_id": str(publish_attempt_id)},
                        )

            if str(job.job_type) == "RECONCILE_PUBLISH_ATTEMPT" and step.step_key == "persist_updates":
                from src.publish.services.publish_reconciliation_service import PublishReconciliationService

                publish_draft_id = (job.payload_json or {}).get("publish_draft_id")
                publish_attempt_id = (job.payload_json or {}).get("publish_attempt_id")
                try:
                    if publish_draft_id:
                        summary = PublishReconciliationService(self.db).reconcile_draft(UUID(str(publish_draft_id)))
                        result = StepHandlerResult(output_json=summary)
                    elif publish_attempt_id:
                        attempt = PublishReconciliationService(self.db).refresh_attempt(UUID(str(publish_attempt_id)))
                        result = StepHandlerResult(
                            output_json={
                                "publish_attempt_id": str(attempt.id),
                                "status": attempt.status.value,
                                "external_status": attempt.external_status.value,
                                "reconciliation_status": attempt.reconciliation_status.value,
                            }
                        )
                    else:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code="invalid_reconciliation_target",
                            error_message="publish_draft_id or publish_attempt_id is required",
                        )
                except ValueError as exc:
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code="publish_reconciliation_failed",
                        error_message=str(exc),
                    )

            # Operator Pause/cancel can flip the job while a long step (e.g. download) runs.
            if self._is_cancelled(job):
                return self._abort_cancelled_job(job)

            if result.status == JobStepStatus.FAILED:
                operator_message = result.error_message
                next_status = JobStatus.RETRYABLE if job.attempts < job.max_attempts and job.retryable else JobStatus.FAILED
                scheduled_at = None
                if str(job.job_type) == "DOWNLOAD_VIDEO":
                    from src.downloaders.download_error_policy import (
                        classify_download_failure,
                        download_failure_operator_message,
                        next_download_retry_at,
                        should_auto_retry_download_failure,
                    )

                    failure_class = classify_download_failure(result.error_code, result.error_message)
                    will_retry = bool(job.retryable) and should_auto_retry_download_failure(
                        failure_class=failure_class,
                        attempts=int(job.attempts or 0),
                    )
                    next_status = JobStatus.RETRYABLE if will_retry else JobStatus.FAILED
                    operator_message = download_failure_operator_message(
                        failure_class=failure_class,
                        error_message=result.error_message,
                        will_retry=will_retry,
                    )
                    if will_retry:
                        scheduled_at = next_download_retry_at(attempts=int(job.attempts or 1))
                    metadata = dict(getattr(job, "metadata_json", None) or {})
                    metadata["download_failure_class"] = str(failure_class)
                    metadata["download_will_auto_retry"] = will_retry
                    job.metadata_json = metadata
                    logger.warning(
                        "download_job_step_failed",
                        extra={
                            "job_id": str(job.id),
                            "step_key": step.step_key,
                            "failure_class": str(failure_class),
                            "attempts": job.attempts,
                            "next_status": str(next_status),
                        },
                    )

                self.service.transition_step(
                    step,
                    JobStepStatus.FAILED,
                    progress_percent=result.progress_percent,
                    error_code=result.error_code,
                    error_message=operator_message,
                    output_json=result.output_json,
                )
                self.service.transition_job(
                    job,
                    next_status,
                    error_code=result.error_code,
                    error_message=operator_message,
                )
                if next_status == JobStatus.RETRYABLE:
                    job.scheduled_at = scheduled_at
                    job.locked_by = None
                    job.locked_at = None
                else:
                    job.scheduled_at = None
                self.service.refresh_progress(job)
                if next_status == JobStatus.FAILED:
                    sync_reup_queue_from_download_job(self.db, job)
                self.db.commit()
                return self.service.get_job(job.id)

            self.service.transition_step(
                step,
                JobStepStatus.COMPLETED,
                progress_percent=100,
                output_json=result.output_json,
            )
            self.service.refresh_progress(job)
            self.db.commit()
            logger.info("job_step_complete", extra={"job_id": str(job.id), "step_key": step.step_key})

        self.service.transition_job(job, JobStatus.COMPLETED)
        job.locked_by = None
        job.locked_at = None
        self.service.refresh_progress(job)
        sync_reup_queue_from_download_job(self.db, job)
        self.db.commit()
        return self.service.get_job(job.id)
