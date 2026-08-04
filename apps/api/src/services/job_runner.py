from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Protocol
from uuid import UUID

from sqlalchemy import case, func, literal, or_, select, text
from sqlalchemy.orm import Session, aliased, selectinload

from src.core.settings import get_settings
from src.enums import JobStatus, JobStepStatus, JobType, SourcePlatformEnum
from src.models.jobs import Job, JobStep
from src.services.disk_guard import DISK_HEAVY_JOB_TYPES, check_disk_headroom, min_free_bytes
from src.services.job_service import JobService
from src.services.reup_queue_download_sync import sync_reup_queue_from_download_job
from src.services.reup_pipeline_orchestrator import ReupPipelineOrchestrator

logger = logging.getLogger(__name__)


PIPELINE_RETRY_JOB_TYPES: frozenset[str] = frozenset(
    {
        JobType.ANALYZE_AUDIO.value,
        JobType.BUILD_TRANSLATION_DRAFT.value,
        JobType.SYNTHESIZE_TTS.value,
        JobType.ANALYZE_OCR.value,
        JobType.RENDER_PREVIEW.value,
        JobType.RENDER_FINAL.value,
    }
)


@dataclass(frozen=True)
class FailureOutcome:
    """How a failed step should settle: give up, or requeue with backoff."""

    status: JobStatus
    scheduled_at: datetime | None
    operator_message: str
    metadata: dict[str, object]


def resolve_failure_outcome(
    *,
    job_type: object,
    attempts: int,
    retryable: bool,
    max_attempts: int,
    error_code: str | None,
    error_message: str | None,
    retry_after_seconds: int | None = None,
    now: datetime | None = None,
) -> FailureOutcome:
    """Single decision point for what happens after a step fails.

    Download keeps its Douyin-specific policy; the localization stages share a transient
    vs terminal classifier so full-auto recovers from flaky IO without paging the operator,
    yet stops instantly on a deterministic defect.
    """
    type_value = job_type.value if hasattr(job_type, "value") else str(job_type)
    attempts = int(attempts or 0)

    if type_value == JobType.DOWNLOAD_VIDEO.value:
        from src.downloaders.download_error_policy import (
            classify_download_failure,
            download_failure_operator_message,
            next_download_retry_at,
            should_auto_retry_download_failure,
        )

        failure_class = classify_download_failure(error_code, error_message)
        will_retry = bool(retryable) and should_auto_retry_download_failure(
            failure_class=failure_class,
            attempts=attempts,
        )
        return FailureOutcome(
            status=JobStatus.RETRYABLE if will_retry else JobStatus.FAILED,
            scheduled_at=next_download_retry_at(attempts=max(1, attempts), now=now) if will_retry else None,
            operator_message=download_failure_operator_message(
                failure_class=failure_class,
                error_message=error_message,
                will_retry=will_retry,
            ),
            metadata={
                "download_failure_class": str(failure_class),
                "download_will_auto_retry": will_retry,
            },
        )

    if type_value == JobType.COLLECT_PUBLICATION_METRICS.value:
        from src.analytics.services.publication_metric_retry_policy import (
            MetricCollectionFailureClass,
            classify_metric_collection_failure,
            metric_collection_operator_message,
            next_metric_collection_retry_at,
        )

        failure_class = classify_metric_collection_failure(error_code)
        will_retry = (
            bool(retryable)
            and failure_class != MetricCollectionFailureClass.TERMINAL
            and attempts < int(max_attempts or 0)
        )
        return FailureOutcome(
            status=JobStatus.RETRYABLE if will_retry else JobStatus.FAILED,
            scheduled_at=(
                next_metric_collection_retry_at(
                    attempts=max(1, attempts),
                    retry_after_seconds=retry_after_seconds,
                    now=now,
                )
                if will_retry
                else None
            ),
            operator_message=metric_collection_operator_message(
                failure_class=failure_class,
                error_message=error_message,
                will_retry=will_retry,
            ),
            metadata={
                "metrics_failure_class": failure_class.value,
                "metrics_will_auto_retry": will_retry,
                "metrics_retry_after_seconds": retry_after_seconds,
            },
        )

    if type_value in PIPELINE_RETRY_JOB_TYPES:
        from src.services.pipeline_retry_policy import (
            classify_pipeline_failure,
            next_pipeline_retry_at,
            pipeline_failure_operator_message,
            pipeline_transient_max_attempts,
            should_auto_retry_pipeline_failure,
        )

        failure_class = classify_pipeline_failure(error_code, error_message)
        # Jobs are created with a small max_attempts; transient IO deserves the policy budget.
        cap = max(int(max_attempts or 0), pipeline_transient_max_attempts())
        will_retry = bool(retryable) and should_auto_retry_pipeline_failure(
            failure_class=failure_class,
            attempts=attempts,
            max_attempts=cap,
        )
        message_lower = str(error_message or "").lower()
        provider_rate_limited = "http_429" in message_lower or "http 429" in message_lower
        return FailureOutcome(
            status=JobStatus.RETRYABLE if will_retry else JobStatus.FAILED,
            scheduled_at=(
                next_pipeline_retry_at(
                    attempts=max(1, attempts),
                    now=now,
                    base_seconds=60 if provider_rate_limited else None,
                    max_seconds=300 if provider_rate_limited else None,
                )
                if will_retry
                else None
            ),
            operator_message=pipeline_failure_operator_message(
                failure_class=failure_class,
                error_message=error_message,
                will_retry=will_retry,
            ),
            metadata={
                "pipeline_failure_class": str(failure_class),
                "pipeline_will_auto_retry": will_retry,
                "pipeline_provider_rate_limited": provider_rate_limited,
            },
        )

    will_retry = bool(retryable) and attempts < int(max_attempts or 0)
    return FailureOutcome(
        status=JobStatus.RETRYABLE if will_retry else JobStatus.FAILED,
        scheduled_at=None,
        operator_message=(error_message or "Job step failed"),
        metadata={},
    )


_CONCURRENCY_SETTING_BY_TYPE: dict[str, tuple[str, int]] = {
    JobType.DOWNLOAD_VIDEO.value: ("download_video_max_concurrent_running", 1),
    JobType.ANALYZE_AUDIO.value: ("analyze_audio_max_concurrent_running", 1),
    JobType.SYNTHESIZE_TTS.value: ("synthesize_tts_max_concurrent_running", 2),
    JobType.ANALYZE_OCR.value: ("analyze_ocr_max_concurrent_running", 1),
    JobType.RENDER_FINAL.value: ("render_final_max_concurrent_running", 1),
    JobType.COLLECT_PUBLICATION_METRICS.value: ("metrics_collection_max_concurrent_running", 2),
    JobType.CLASSIFY_CONTENT.value: ("classification_max_concurrent_running", 2),
    JobType.MATCH_AFFILIATE_PRODUCTS.value: ("affiliate_matching_max_concurrent_running", 2),
    JobType.CALCULATE_GROWTH_SCORE.value: ("growth_score_max_concurrent_running", 2),
    JobType.POST_AFFILIATE_COMMENT.value: ("affiliate_comment_max_concurrent_running", 1),
    JobType.VERIFY_AFFILIATE_COMMENT.value: ("affiliate_comment_verification_max_concurrent_running", 2),
}


def job_type_concurrency_limits(settings: object | None = None) -> dict[str, int]:
    """Running-job cap per workspace for the stages that saturate the machine.

    Types absent from the result run unlimited.
    """
    cfg = settings if settings is not None else get_settings()
    limits: dict[str, int] = {}
    for type_value, (attribute, fallback) in _CONCURRENCY_SETTING_BY_TYPE.items():
        raw = getattr(cfg, attribute, fallback)
        try:
            limits[type_value] = max(1, int(raw))
        except (TypeError, ValueError):
            limits[type_value] = fallback
    return limits


def job_type_claim_allowed(job_type: object, *, running_same_type: int, limits: dict[str, int]) -> bool:
    """Whether a job may be claimed given how many of its own type already run."""
    type_value = job_type.value if hasattr(job_type, "value") else str(job_type)
    limit = limits.get(type_value)
    if limit is None:
        return True
    return int(running_same_type) < limit


# Advisory lock id shared by every worker claiming a job. Arbitrary but must stay stable.
CLAIM_ADVISORY_LOCK_KEY = 771_204_881

# Stages that put a model or an encoder on the GPU. They share one physical card, so their
# per-type slots are not enough on their own — this group is the real machine budget.
GPU_JOB_TYPES: frozenset[str] = frozenset(
    {
        JobType.ANALYZE_AUDIO.value,
        JobType.SYNTHESIZE_TTS.value,
        JobType.ANALYZE_OCR.value,
        JobType.RENDER_PREVIEW.value,
        JobType.RENDER_FINAL.value,
    }
)


def gpu_max_concurrent_running(settings: object | None = None) -> int:
    cfg = settings if settings is not None else get_settings()
    try:
        return max(1, int(getattr(cfg, "gpu_max_concurrent_running", 1)))
    except (TypeError, ValueError):
        return 1


def gpu_claim_allowed(job_type: object, *, running_in_group: int, limit: int) -> bool:
    """Whether a job may claim the shared GPU budget. Non-GPU work is never blocked."""
    type_value = job_type.value if hasattr(job_type, "value") else str(job_type)
    if type_value not in GPU_JOB_TYPES:
        return True
    return int(running_in_group) < max(1, int(limit))


_STALE_SETTING_BY_TYPE: dict[str, tuple[str, int]] = {
    JobType.ANALYZE_AUDIO.value: ("analyze_audio_stale_running_seconds", 2_700),
    JobType.BUILD_TRANSLATION_DRAFT.value: ("build_translation_draft_stale_running_seconds", 1_800),
    JobType.SYNTHESIZE_TTS.value: ("synthesize_tts_stale_running_seconds", 2_700),
    JobType.ANALYZE_OCR.value: ("analyze_ocr_stale_running_seconds", 5_400),
    JobType.RENDER_PREVIEW.value: ("render_preview_stale_running_seconds", 3_600),
    JobType.RENDER_FINAL.value: ("render_final_stale_running_seconds", 5_400),
    JobType.COLLECT_PUBLICATION_METRICS.value: ("metrics_collection_stale_running_seconds", 300),
    JobType.CLASSIFY_CONTENT.value: ("classification_stale_running_seconds", 1_800),
    JobType.MATCH_AFFILIATE_PRODUCTS.value: ("affiliate_matching_stale_running_seconds", 1_800),
    JobType.CALCULATE_GROWTH_SCORE.value: ("growth_score_stale_running_seconds", 300),
    JobType.POST_AFFILIATE_COMMENT.value: ("affiliate_comment_stale_running_seconds", 300),
    JobType.VERIFY_AFFILIATE_COMMENT.value: ("affiliate_comment_verification_stale_running_seconds", 300),
}

# Below this a threshold is more likely a typo than a policy, and would kill healthy work.
_STALE_FLOOR_SECONDS = 120


def job_type_stale_seconds(job_type: object, settings: object | None = None) -> int:
    """How long a job of this type may hold its lock without a heartbeat.

    Media stages legitimately run for tens of minutes; judging them by the download budget
    requeues healthy work forever. Dead workers are caught immediately by
    ``release_orphaned_locks`` instead — this is only the backstop.
    """
    type_value = job_type.value if hasattr(job_type, "value") else str(job_type)
    cfg = settings if settings is not None else get_settings()
    if type_value == JobType.DOWNLOAD_VIDEO.value:
        return download_stale_running_seconds(cfg)

    entry = _STALE_SETTING_BY_TYPE.get(type_value)
    if entry is None:
        raw = getattr(cfg, "job_stale_running_seconds_default", 1_800)
        fallback = 1_800
    else:
        attribute, fallback = entry
        raw = getattr(cfg, attribute, fallback)
    try:
        return max(_STALE_FLOOR_SECONDS, int(raw))
    except (TypeError, ValueError):
        return fallback


def download_stale_running_seconds(settings: object | None = None) -> int:
    """Wall-clock age after which a RUNNING job is treated as stuck and requeued.

    Covers Playwright bridge (~2.5× playwright timeout) + yt-dlp budget with margin.
    Override with ``download_video_stale_running_seconds``.
    """
    cfg = settings if settings is not None else get_settings()
    override = getattr(cfg, "download_video_stale_running_seconds", None)
    if override is not None:
        try:
            return max(120, int(override))
        except (TypeError, ValueError):
            pass
    playwright_ms = float(getattr(cfg, "douyin_playwright_download_timeout_ms", 90_000) or 90_000)
    yt_s = float(getattr(cfg, "douyin_yt_dlp_timeout_seconds", 180) or 180)
    bridge_s = max(180.0, (playwright_ms / 1000.0) * 2.5 + 30.0)
    return max(600, int(bridge_s + yt_s + 120))


class JobCancelledAbort(Exception):
    """Raised from long-running step heartbeats when the operator cancels the job."""


@dataclass(frozen=True)
class StepHandlerResult:
    status: JobStepStatus = JobStepStatus.COMPLETED
    progress_percent: int = 100
    output_json: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_after_seconds: int | None = None


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

    def _settle_recovered_running_job(
        self,
        job: Job,
        *,
        error_code: str,
        error_message: str,
    ) -> FailureOutcome:
        """Apply the normal retry policy when a worker loses a running job.

        Lock recovery is a failure boundary too. It must not blindly requeue a job
        forever: an orphaned attempt still consumes the job's retry budget.
        """
        outcome = resolve_failure_outcome(
            job_type=job.job_type,
            attempts=int(getattr(job, "attempts", 0) or 0),
            retryable=bool(getattr(job, "retryable", True)),
            max_attempts=int(getattr(job, "max_attempts", 0) or 0),
            error_code=error_code,
            error_message=error_message,
        )
        if outcome.metadata:
            job.metadata_json = {
                **(getattr(job, "metadata_json", None) or {}),
                **outcome.metadata,
            }
        self.service.transition_job(
            job,
            outcome.status,
            error_code=error_code,
            error_message=outcome.operator_message[:500],
        )
        job.scheduled_at = outcome.scheduled_at
        job.locked_by = None
        job.locked_at = None
        self.service.refresh_progress(job)
        return outcome

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
            outcome = self._settle_recovered_running_job(
                job,
                error_code="WORKER_ORPHANED",
                error_message=(
                    "Worker restarted or crashed while job was RUNNING; "
                    "the retry policy will decide whether to requeue it."
                ),
            )
            logger.warning(
                "job_orphan_lock_released",
                extra={
                    "job_id": str(job.id),
                    "worker_id": worker_id,
                    "next_status": outcome.status.value,
                    "attempts": int(getattr(job, "attempts", 0) or 0),
                },
            )
        self.db.commit()
        return len(jobs)

    def release_stale_running_locks(self, *, max_age_seconds: int | None = None) -> int:
        """Requeue RUNNING jobs whose lock is older than the stale threshold.

        A hung ``register_assets`` download can sit at ~71% forever with no heartbeat.
        With download concurrency=1 that single zombie blocks the whole auto queue.
        """
        settings = get_settings()
        override = None if max_age_seconds is None else max(_STALE_FLOOR_SECONDS, int(max_age_seconds))
        # The shortest patience decides the SQL cutoff so no type is filtered out too early;
        # each candidate is then judged against its own budget below.
        shortest = override if override is not None else min(
            job_type_stale_seconds(job_type, settings=settings) for job_type in JobType
        )
        now = datetime.now(UTC)
        stmt = (
            select(Job)
            .where(Job.status == JobStatus.RUNNING)
            .where(Job.locked_at.is_not(None))
            .where(Job.locked_at < now - timedelta(seconds=shortest))
            .options(selectinload(Job.steps))
        )
        candidates = list(self.db.scalars(stmt).all())
        if not candidates:
            return 0

        released = 0
        for job in candidates:
            age = override if override is not None else job_type_stale_seconds(job.job_type, settings=settings)
            locked_at = getattr(job, "locked_at", None)
            if locked_at is None or (now - locked_at).total_seconds() < age:
                continue
            released += 1
            for step in job.steps or []:
                if step.status == JobStepStatus.RUNNING:
                    self.service.transition_step(
                        step,
                        JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code="WORKER_STALE_RUNNING",
                        error_message=(
                            f"Job held its lock for over {age}s without a heartbeat; "
                            "requeued automatically (worker likely died mid-step)."
                        ),
                    )
            outcome = self._settle_recovered_running_job(
                job,
                error_code="WORKER_STALE_RUNNING",
                error_message=(
                    f"Job held its lock for over {age}s without a heartbeat; "
                    "the retry policy will decide whether to requeue it."
                ),
            )
            logger.warning(
                "job_stale_lock_released",
                extra={
                    "job_id": str(job.id),
                    "job_type": str(job.job_type),
                    "max_age_seconds": age,
                    "next_status": outcome.status.value,
                    "attempts": int(getattr(job, "attempts", 0) or 0),
                },
            )
        if released:
            self.db.commit()
        return released

    def _serialize_claim(self) -> None:
        """Hold a transaction-scoped lock so concurrent workers count slots truthfully.

        The caps below are subqueries. Without this, two workers can both count zero running
        GPU jobs and claim two different ones, defeating the budget. A claim takes
        milliseconds, so serialising it costs far less than an OOM render.
        """
        try:
            dialect = self.db.bind.dialect.name
        except Exception:  # noqa: BLE001 — unit tests and non-ORM sessions have no bind
            return
        if dialect != "postgresql":
            return
        try:
            self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CLAIM_ADVISORY_LOCK_KEY})
        except Exception:  # noqa: BLE001 — a missing lock must not stop work entirely
            logger.warning("job_claim_advisory_lock_failed", exc_info=True)

    def claim_next_job(self, worker_id: str) -> Job | None:
        now = datetime.now(UTC)
        self._serialize_claim()
        limits = job_type_concurrency_limits()

        # Cap concurrent running jobs per type per workspace so a Start-auto batch queues
        # instead of storming Douyin/Playwright on download or pinning the box on render.
        running_same_type = aliased(Job)
        running_same_type_count = (
            select(func.count())
            .select_from(running_same_type)
            .where(
                running_same_type.workspace_id == Job.workspace_id,
                running_same_type.job_type == Job.job_type,
                running_same_type.status == JobStatus.RUNNING,
            )
            .correlate(Job)
            .scalar_subquery()
        )
        type_limit = case(
            *[(Job.job_type == type_value, literal(limit)) for type_value, limit in limits.items()],
            else_=literal(None),
        )
        type_slot_ok = or_(type_limit.is_(None), running_same_type_count < type_limit)

        # Per-type slots still let OCR + TTS + render land on one card together, which on a
        # small GPU means OOM or a silent fallback to CPU. The heavy stages share one budget.
        gpu_limit = gpu_max_concurrent_running()
        running_gpu = aliased(Job)
        running_gpu_count = (
            select(func.count())
            .select_from(running_gpu)
            .where(
                running_gpu.workspace_id == Job.workspace_id,
                running_gpu.job_type.in_(sorted(GPU_JOB_TYPES)),
                running_gpu.status == JobStatus.RUNNING,
            )
            .correlate(Job)
            .scalar_subquery()
        )
        gpu_slot_ok = or_(
            Job.job_type.notin_(sorted(GPU_JOB_TYPES)),
            running_gpu_count < literal(gpu_limit),
        )

        stmt = (
            select(Job)
            .where(Job.status.in_([JobStatus.QUEUED, JobStatus.RETRYABLE]))
            .where(or_(Job.scheduled_at.is_(None), Job.scheduled_at <= now))
            .where(type_slot_ok)
            .where(gpu_slot_ok)
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
        # A new attempt must not present the previous retry's failure as the
        # current RUNNING state. Keep historical evidence in attempts/steps,
        # while the top-level fields describe the active attempt.
        job.error_code = None
        job.error_message = None
        self.service.refresh_progress(job)
        self.db.commit()
        logger.info(
            "job_claimed",
            extra={
                "job_id": str(job.id),
                "worker_id": worker_id,
                "job_type": str(job.job_type),
                "type_max_concurrent": limits.get(str(getattr(job.job_type, "value", job.job_type))),
                "gpu_max_concurrent": gpu_limit,
            },
        )
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

    def _disk_block_reason(self, job: Job) -> str | None:
        """Why this job must not start now, when the storage volume is nearly full."""
        type_value = str(getattr(job.job_type, "value", job.job_type))
        if type_value not in DISK_HEAVY_JOB_TYPES:
            return None
        settings = get_settings()
        status = check_disk_headroom(
            str(getattr(settings, "local_storage_root", "./data/storage")),
            required_bytes=min_free_bytes(settings),
        )
        if status.ok:
            return None
        logger.warning(
            "job_blocked_low_disk",
            extra={
                "job_id": str(job.id),
                "job_type": type_value,
                "free_bytes": status.free_bytes,
                "required_bytes": status.required_bytes,
            },
        )
        return status.message

    def _fail_job_before_start(self, job: Job, *, error_code: str, error_message: str) -> Job:
        """Record a precondition failure and let the retry policy decide what happens next."""
        for step in job.steps:
            if step.status in {JobStepStatus.PENDING, JobStepStatus.RUNNING}:
                self.service.transition_step(
                    step,
                    JobStepStatus.FAILED,
                    progress_percent=0,
                    error_code=error_code,
                    error_message=error_message[:500],
                )
                break
        outcome = resolve_failure_outcome(
            job_type=job.job_type,
            attempts=int(getattr(job, "attempts", 0) or 0),
            retryable=bool(getattr(job, "retryable", True)),
            max_attempts=int(getattr(job, "max_attempts", 0) or 0),
            error_code=error_code,
            error_message=error_message,
        )
        self.service.transition_job(
            job,
            outcome.status,
            error_code=error_code,
            error_message=outcome.operator_message[:500],
        )
        job.scheduled_at = outcome.scheduled_at
        job.locked_by = None
        job.locked_at = None
        self.service.refresh_progress(job)
        self.db.commit()
        return self.service.get_job(job.id)

    def run_job(self, job_id: UUID) -> Job:
        job = self.service.get_job(job_id)
        if job.status == JobStatus.QUEUED:
            self.service.transition_job(job, JobStatus.RUNNING)
            job.attempts = int(job.attempts or 0) + 1
            job.scheduled_at = None
            job.error_code = None
            job.error_message = None
            # ``_is_cancelled`` refreshes the ORM row before every step. Persist a
            # direct QUEUED -> RUNNING transition first, otherwise that refresh can
            # restore QUEUED from the database and the final transition becomes the
            # illegal QUEUED -> COMPLETED. Normal workers already commit this state in
            # ``claim_next_job``; attempts/schedule above keep direct execution's audit
            # fields equivalent to a normal worker claim.
            self.service.refresh_progress(job)
            self.db.commit()
        if job.status == JobStatus.CANCELLED:
            return self._abort_cancelled_job(job)
        if job.status != JobStatus.RUNNING:
            raise ValueError(f"Job must be RUNNING before execution, got {job.status}")

        disk_reason = self._disk_block_reason(job)
        if disk_reason is not None:
            return self._fail_job_before_start(job, error_code="DISK_SPACE_LOW", error_message=disk_reason)

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
                # A DB error aborts the transaction; without this rollback the failure
                # write below raises too and the job stays RUNNING forever.
                try:
                    self.db.rollback()
                except Exception:
                    logger.exception("job_step_rollback_failed", extra={"job_id": str(job.id)})
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
                from src.services.job_service import utc_now

                source_video_id = (job.payload_json or {}).get("source_video_id")
                if source_video_id is None and job.source_video_id is not None:
                    source_video_id = str(job.source_video_id)
                if source_video_id is not None:
                    def _tts_heartbeat(phase: str, progress_percent: int | None) -> None:
                        if self._is_cancelled(job):
                            raise JobCancelledAbort()
                        job.updated_at = utc_now()
                        meta = dict(step.metadata_json or {})
                        meta["tts_phase"] = phase
                        step.metadata_json = meta
                        if progress_percent is not None:
                            step.progress_percent = max(0, min(99, int(progress_percent)))
                            self.service.refresh_progress(job)
                        self.db.commit()

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
                                runtime_authority=(job.payload_json or {}).get(
                                    "runtime_authority"
                                ),
                            ),
                            job_id=job.id,
                            on_progress=_tts_heartbeat,
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
                    except JobCancelledAbort:
                        return self._abort_cancelled_job(job)
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
                        if self._is_cancelled(job):
                            raise JobCancelledAbort()
                        job.updated_at = utc_now()
                        meta = dict(step.metadata_json or {})
                        phase_parts = str(phase).split("|")
                        meta["ocr_phase"] = phase_parts[0]
                        if len(phase_parts) == 3:
                            try:
                                meta["ocr_frame_current"] = int(phase_parts[1])
                                meta["ocr_frame_total"] = int(phase_parts[2])
                            except ValueError:
                                pass
                        step.metadata_json = meta
                        if progress_percent is not None:
                            step.progress_percent = max(0, min(99, int(progress_percent)))
                            self.service.refresh_progress(job)
                        self.db.commit()

                    try:
                        payload = job.payload_json or {}
                        from src.services.pipeline_recipe_runtime import (
                            RuntimeRecipeError,
                            assert_job_recipe_workflow_contract,
                        )

                        assert_job_recipe_workflow_contract(job)
                        if payload.get("workflow_version") == "QUALITY_LOCALIZATION_V24_1":
                            from src.services.quality_localization_service import (
                                QualityLocalizationService,
                            )

                            workflow = QualityLocalizationService(self.db).run_phase12(
                                source_video_id=UUID(str(source_video_id)),
                                job_id=job.id,
                                action=str(payload.get("workflow_action") or "analyze"),
                                decisions=list(payload.get("review_decisions") or []),
                                operator_id=str(payload.get("operator_id") or "frontend_operator"),
                                force_refresh=bool(payload.get("force_refresh")),
                                on_progress=_ocr_heartbeat,
                            )
                            result = StepHandlerResult(output_json=workflow)
                        else:
                            ocr_summary = OcrPipelineService(self.db).run_pipeline(
                                OcrRequest(
                                    source_video_id=UUID(str(source_video_id)),
                                    force_refresh=bool(payload.get("force_refresh")),
                                    sample_fps=float(payload.get("sample_fps") or 1.0),
                                    hard_sub_band_ratio=float(payload.get("hard_sub_band_ratio") or 0.28),
                                    clean_hardsub=bool(payload.get("clean_hardsub", True)),
                                    use_master_phase1=(
                                        bool(payload.get("use_master_phase1"))
                                        if payload.get("use_master_phase1") is not None
                                        else None
                                    ),
                                    workflow_version="legacy_media_e2e_v1",
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
                    except JobCancelledAbort:
                        return self._abort_cancelled_job(job)
                    except RuntimeRecipeError as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code="PIPELINE_RECIPE_WORKFLOW_MISMATCH",
                            error_message=str(exc),
                            output_json={"source_video_id": str(source_video_id)},
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
                        from src.services.quality_localization_service import (
                            QualityLocalizationError,
                        )

                        if isinstance(exc, QualityLocalizationError):
                            result = StepHandlerResult(
                                status=JobStepStatus.FAILED,
                                progress_percent=0,
                                error_code="QUALITY_LOCALIZATION_FAILED",
                                error_message=str(exc),
                                output_json={"source_video_id": str(source_video_id)},
                            )
                        else:
                            import traceback

                            logger.exception(
                                "job_step_unhandled_error",
                                extra={"job_id": str(job.id), "step_key": step.step_key},
                            )
                            tb = traceback.format_exc()
                            meta = dict(step.metadata_json or {})
                            meta["unhandled_traceback"] = tb[-4000:]
                            step.metadata_json = meta
                            result = StepHandlerResult(
                                status=JobStepStatus.FAILED,
                                progress_percent=0,
                                error_code="STEP_UNHANDLED_ERROR",
                                error_message=f"{type(exc).__name__}: {exc}"[:500],
                                output_json={"source_video_id": str(source_video_id)},
                            )

            if str(job.job_type) == "RENDER_PREVIEW" and step.step_key == "render_preview":
                from src.services.job_service import utc_now
                from src.services.quality_localization_service import (
                    QualityLocalizationError,
                    QualityLocalizationService,
                )

                payload = job.payload_json or {}
                source_video_id = payload.get("source_video_id") or job.source_video_id

                def _preview_heartbeat(phase: str, progress_percent: int | None) -> None:
                    if self._is_cancelled(job):
                        raise JobCancelledAbort()
                    job.updated_at = utc_now()
                    meta = dict(step.metadata_json or {})
                    meta["quality_phase"] = phase
                    step.metadata_json = meta
                    if progress_percent is not None:
                        step.progress_percent = max(0, min(99, int(progress_percent)))
                        self.service.refresh_progress(job)
                    self.db.commit()

                try:
                    if payload.get("workflow_version") != "QUALITY_LOCALIZATION_V24_1":
                        raise QualityLocalizationError(
                            "RENDER_PREVIEW requires the quality-localization workflow"
                        )
                    quality = QualityLocalizationService(self.db)
                    action = str(
                        payload.get("workflow_action")
                        or "translation_review_and_preview"
                    )
                    if action in {
                        "build_residual_proposal",
                        "approve_residual_proposal",
                    }:
                        workflow = quality.run_residual_review(
                            source_video_id=UUID(str(source_video_id)),
                            job_id=job.id,
                            action=action,
                            suggestions=list(payload.get("suggestions") or []),
                            proposal_sha256=str(payload.get("proposal_sha256") or ""),
                            operator_id=str(payload.get("operator_id") or "frontend_operator"),
                            on_progress=_preview_heartbeat,
                        )
                    else:
                        workflow = quality.run_translation_and_preview(
                            source_video_id=UUID(str(source_video_id)),
                            job_id=job.id,
                            translations=list(payload.get("translations") or []),
                            operator_id=str(payload.get("operator_id") or "frontend_operator"),
                            on_progress=_preview_heartbeat,
                        )
                    result = StepHandlerResult(output_json=workflow)
                except JobCancelledAbort:
                    return self._abort_cancelled_job(job)
                except QualityLocalizationError as exc:
                    message = str(exc)
                    error_code = (
                        "QUALITY_REVIEW_VALIDATION_FAILED"
                        if "translation review validation failed" in message.lower()
                        else "QUALITY_PREFLIGHT_BLOCKED"
                        if "preflight blocked" in message.lower()
                        or "BLOCKED_" in message
                        else "QUALITY_OUTPUT_QA_FAILED"
                        if "output qa failed" in message.lower()
                        else "QUALITY_LOCALIZATION_FAILED"
                    )
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code=error_code,
                        error_message=message,
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
                        from src.services.pipeline_recipe_runtime import (
                            RuntimeRecipeError,
                            assert_job_recipe_workflow_contract,
                        )

                        assert_job_recipe_workflow_contract(job)
                        render_result = RenderService(self.db).run_render(
                            RenderRequest(
                                source_video_id=UUID(str(source_video_id)),
                                render_mode=(job.payload_json or {}).get("render_mode", "final"),
                                force_refresh=bool((job.payload_json or {}).get("force_refresh")),
                                workflow_version=str(
                                    (job.payload_json or {}).get("workflow_version")
                                    or "legacy_render_v1"
                                ),
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
                    except RuntimeRecipeError as exc:
                        result = StepHandlerResult(
                            status=JobStepStatus.FAILED,
                            progress_percent=0,
                            error_code="PIPELINE_RECIPE_WORKFLOW_MISMATCH",
                            error_message=str(exc),
                            output_json={"source_video_id": str(source_video_id)},
                        )

            if str(job.job_type) == "PUBLISH_CONTENT" and step.step_key == "persist_result":
                from src.enums import PublishAttemptStatus
                from src.publish.services.publish_attempt_service import PublishAttemptError, PublishAttemptService
                from src.schemas.publish import PublishDraftPublishRequest

                publish_attempt_id = (job.payload_json or {}).get("publish_attempt_id")
                publish_draft_id = (job.payload_json or {}).get("publish_draft_id")
                platform_account_id = (job.payload_json or {}).get("platform_account_id")
                if publish_attempt_id:
                    try:
                        attempt = PublishAttemptService(self.db).execute_attempt(UUID(str(publish_attempt_id)))
                        if attempt.status == PublishAttemptStatus.FAILED:
                            result = StepHandlerResult(
                                status=JobStepStatus.FAILED,
                                progress_percent=0,
                                error_code=attempt.error_code or "publish_failed",
                                error_message=attempt.error_message or "Publish attempt failed",
                                output_json={
                                    "publish_attempt_id": str(attempt.id),
                                    "status": attempt.status.value,
                                },
                            )
                        else:
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
                            output_json={"publish_attempt_id": str(publish_attempt_id)},
                        )
                elif publish_draft_id and platform_account_id:
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

            if (
                str(job.job_type) == "COLLECT_PUBLICATION_METRICS"
                and step.step_key == "collect_and_persist_snapshot"
            ):
                from src.analytics.services.publication_metric_collection_service import (
                    PublicationMetricCollectionError,
                    PublicationMetricCollectionService,
                )

                try:
                    snapshot = PublicationMetricCollectionService(self.db).execute_job(job.id)
                    result = StepHandlerResult(
                        output_json={
                            "metric_snapshot_id": str(snapshot.id),
                            "platform_publication_id": str(snapshot.platform_publication_id),
                            "observed_at": snapshot.observed_at.isoformat(),
                        }
                    )
                except PublicationMetricCollectionError as exc:
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code=exc.code,
                        error_message=str(exc),
                        retry_after_seconds=exc.retry_after_seconds,
                    )
                except Exception as exc:
                    # The metric boundary must never escape ``run_job`` and look like a
                    # worker crash. Keep the persisted message generic so provider
                    # payloads/credential errors cannot reach the operator UI.
                    logger.error(
                        "publication_metric_collection_runner_boundary_error",
                        extra={
                            "job_id": str(job.id),
                            "step_key": step.step_key,
                            "exception_type": type(exc).__name__,
                        },
                        exc_info=True,
                    )
                    try:
                        self.db.rollback()
                    except Exception:
                        logger.error(
                            "publication_metric_collection_runner_rollback_failed",
                            extra={"job_id": str(job.id)},
                            exc_info=True,
                        )
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code="metrics_unhandled_error",
                        error_message=(
                            "Insights collection failed unexpectedly inside the worker; "
                            "no credential data was exposed"
                        ),
                    )

            if str(job.job_type) == "CLASSIFY_CONTENT" and step.step_key == "classify_and_persist":
                from src.content_intelligence.services.content_classification_service import (
                    ContentIntelligenceError,
                    ContentClassificationService,
                )

                try:
                    classification = ContentClassificationService(self.db).execute_job(job.id)
                    result = StepHandlerResult(
                        output_json={
                            "content_classification_id": str(classification.id),
                            "primary_topic_code": classification.primary_topic_code,
                            "confidence": classification.confidence,
                            "network_used": bool((classification.metadata_json or {}).get("network_used")),
                            "provider": (classification.metadata_json or {}).get("provider"),
                            "prompt_version": (classification.metadata_json or {}).get("prompt_version"),
                        }
                    )
                except ContentIntelligenceError as exc:
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code=exc.code,
                        error_message=str(exc),
                    )
                except Exception:
                    logger.error(
                        "content_classification_runner_boundary_error",
                        extra={"job_id": str(job.id), "step_key": step.step_key},
                        exc_info=True,
                    )
                    try:
                        self.db.rollback()
                    except Exception:
                        logger.error(
                            "content_classification_runner_rollback_failed",
                            extra={"job_id": str(job.id)},
                            exc_info=True,
                        )
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code="classification_unhandled_error",
                        error_message="Content classification failed unexpectedly; no provider payload was exposed",
                    )

            if str(job.job_type) == "MATCH_AFFILIATE_PRODUCTS" and step.step_key == "match_and_persist":
                from src.affiliate_intelligence.services.affiliate_product_service import (
                    AffiliateIntelligenceError,
                    AffiliateProductMatchingService,
                )

                try:
                    product_match = AffiliateProductMatchingService(self.db).execute_job(job.id)
                    result = StepHandlerResult(
                        output_json={
                            "affiliate_product_match_id": str(product_match.id),
                            "suggestion_count": len(product_match.suggestions_json or []),
                            "score_version": (product_match.metadata_json or {}).get("score_version"),
                            "auto_placement": False,
                        }
                    )
                except AffiliateIntelligenceError as exc:
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code=exc.code,
                        error_message=str(exc),
                    )
                except Exception:
                    logger.error(
                        "affiliate_product_match_runner_boundary_error",
                        extra={"job_id": str(job.id), "step_key": step.step_key},
                        exc_info=True,
                    )
                    try:
                        self.db.rollback()
                    except Exception:
                        logger.error(
                            "affiliate_product_match_runner_rollback_failed",
                            extra={"job_id": str(job.id)},
                            exc_info=True,
                        )
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code="affiliate_match_unhandled_error",
                        error_message="Affiliate product matching failed unexpectedly; no catalog secret was exposed",
                    )

            if str(job.job_type) == "CALCULATE_GROWTH_SCORE" and step.step_key == "calculate_and_persist":
                from src.growth_intelligence.services.growth_score_service import (
                    GrowthIntelligenceError,
                    GrowthScoreService,
                )

                try:
                    assessment = GrowthScoreService(self.db).execute_job(job.id)
                    result = StepHandlerResult(
                        output_json={
                            "publication_growth_assessment_id": str(assessment.id),
                            "growth_score": assessment.growth_score,
                            "status": assessment.status,
                            "confidence": assessment.confidence,
                            "score_version": assessment.score_version,
                            "combined_with_affiliate_fit": False,
                            "auto_placement": False,
                        }
                    )
                except GrowthIntelligenceError as exc:
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code=exc.code,
                        error_message=str(exc),
                    )
                except Exception:
                    logger.error(
                        "growth_score_runner_boundary_error",
                        extra={"job_id": str(job.id), "step_key": step.step_key},
                        exc_info=True,
                    )
                    try:
                        self.db.rollback()
                    except Exception:
                        logger.error(
                            "growth_score_runner_rollback_failed",
                            extra={"job_id": str(job.id)},
                            exc_info=True,
                        )
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code="growth_score_unhandled_error",
                        error_message="Growth Score failed unexpectedly; no provider payload was exposed",
                    )

            if str(job.job_type) == "POST_AFFILIATE_COMMENT" and step.step_key == "post_comment":
                from src.affiliate_intelligence.services.affiliate_comment_service import (
                    AffiliateCommentError,
                    AffiliateCommentService,
                )

                try:
                    placement = AffiliateCommentService(self.db).execute_job(job.id)
                    result = StepHandlerResult(
                        output_json={
                            "affiliate_comment_placement_id": str(placement.id),
                            "external_comment_id": placement.external_comment_id,
                            "status": placement.status,
                            "automatic_placement": False,
                        }
                    )
                except AffiliateCommentError as exc:
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code=exc.code,
                        error_message=str(exc),
                    )
                except Exception:
                    logger.error(
                        "affiliate_comment_runner_boundary_error",
                        extra={"job_id": str(job.id), "step_key": step.step_key},
                        exc_info=True,
                    )
                    try:
                        self.db.rollback()
                    except Exception:
                        logger.error(
                            "affiliate_comment_runner_rollback_failed",
                            extra={"job_id": str(job.id)},
                            exc_info=True,
                        )
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code="affiliate_comment_unhandled_error",
                        error_message="Affiliate comment posting failed unexpectedly; no credential data was exposed",
                    )

            if str(job.job_type) == "VERIFY_AFFILIATE_COMMENT" and step.step_key == "verify_comment_and_link":
                from src.affiliate_intelligence.services.affiliate_comment_verification_service import (
                    AffiliateCommentVerificationError,
                    AffiliateCommentVerificationService,
                )

                try:
                    placement = AffiliateCommentVerificationService(self.db).execute_job(job.id)
                    verification = dict((placement.metadata_json or {}).get("verification") or {})
                    result = StepHandlerResult(
                        output_json={
                            "affiliate_comment_placement_id": str(placement.id),
                            "verification_status": verification.get("status"),
                            "checked_at": verification.get("checked_at"),
                            "automatic_repost": False,
                        }
                    )
                except AffiliateCommentVerificationError as exc:
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code=exc.code,
                        error_message=str(exc),
                    )
                except Exception:
                    logger.error(
                        "affiliate_comment_verification_runner_boundary_error",
                        extra={"job_id": str(job.id), "step_key": step.step_key},
                        exc_info=True,
                    )
                    try:
                        self.db.rollback()
                    except Exception:
                        logger.error(
                            "affiliate_comment_verification_runner_rollback_failed",
                            extra={"job_id": str(job.id)},
                            exc_info=True,
                        )
                    result = StepHandlerResult(
                        status=JobStepStatus.FAILED,
                        progress_percent=0,
                        error_code="affiliate_comment_verification_unhandled_error",
                        error_message="Comment verification failed unexpectedly; no credential data was exposed",
                    )

            # Operator Pause/cancel can flip the job while a long step (e.g. download) runs.
            if self._is_cancelled(job):
                return self._abort_cancelled_job(job)

            if result.status == JobStepStatus.FAILED:
                outcome = resolve_failure_outcome(
                    job_type=job.job_type,
                    attempts=int(job.attempts or 0),
                    retryable=bool(job.retryable),
                    max_attempts=int(job.max_attempts or 0),
                    error_code=result.error_code,
                    error_message=result.error_message,
                    retry_after_seconds=result.retry_after_seconds,
                )
                operator_message = outcome.operator_message
                next_status = outcome.status
                scheduled_at = outcome.scheduled_at
                if outcome.metadata:
                    metadata = dict(getattr(job, "metadata_json", None) or {})
                    metadata.update(outcome.metadata)
                    job.metadata_json = metadata
                    logger.warning(
                        "job_step_failed_policy",
                        extra={
                            "job_id": str(job.id),
                            "job_type": str(job.job_type),
                            "step_key": step.step_key,
                            "attempts": job.attempts,
                            "next_status": str(next_status),
                            **{key: str(value) for key, value in outcome.metadata.items()},
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
                    job.locked_by = None
                    job.locked_at = None
                self.service.refresh_progress(job)
                if next_status == JobStatus.FAILED:
                    sync_reup_queue_from_download_job(self.db, job)
                    ReupPipelineOrchestrator(self.db).on_job_terminal(job)
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
        job.error_code = None
        job.error_message = None
        job.locked_by = None
        job.locked_at = None
        self.service.refresh_progress(job)
        sync_reup_queue_from_download_job(self.db, job)
        ReupPipelineOrchestrator(self.db).on_job_terminal(job)
        self.db.commit()
        return self.service.get_job(job.id)
