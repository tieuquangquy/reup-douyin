from __future__ import annotations

from datetime import UTC, datetime
import logging
from uuid import UUID

from sqlalchemy import Select, String, cast, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from src.db.bootstrap import ensure_default_workspace
from src.db.base import Base
from src.enums import JobStatus, JobStepStatus, JobType
from src.models.jobs import Job, JobStep
from src.services.job_factory import build_job
from src.services.job_progress import apply_job_progress
from src.services.job_state_machine import (
    can_cancel_job,
    can_delete_job,
    can_resume_job,
    can_retry_job,
    validate_job_transition,
    validate_step_transition,
)

logger = logging.getLogger(__name__)


class JobNotFound(LookupError):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


class JobService:
    def __init__(self, db: Session):
        self.db = db

    def create_job(
        self,
        *,
        job_type: JobType,
        workspace_id: UUID | None = None,
        payload_json: dict | None = None,
        source_video_id: UUID | None = None,
        crawl_session_id: UUID | None = None,
        render_output_id: UUID | None = None,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
        idempotency_key: str | None = None,
        priority: int = 0,
        max_attempts: int = 3,
        context_json: dict | None = None,
        metadata_json: dict | None = None,
        scheduled_at: datetime | None = None,
        commit: bool = True,
    ) -> Job:
        workspace = None
        if workspace_id is None:
            workspace = ensure_default_workspace(self.db)
            workspace_id = workspace.id

        job = build_job(
            workspace_id=workspace_id,
            job_type=job_type,
            payload_json=payload_json,
            source_video_id=source_video_id,
            crawl_session_id=crawl_session_id,
            render_output_id=render_output_id,
            reference_type=reference_type,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            priority=priority,
            max_attempts=max_attempts,
            context_json=context_json,
            metadata_json=metadata_json,
            scheduled_at=scheduled_at,
        )
        if job_type in {
            JobType.DOWNLOAD_VIDEO,
            JobType.ANALYZE_AUDIO,
            JobType.BUILD_TRANSLATION_DRAFT,
            JobType.SYNTHESIZE_TTS,
            JobType.ANALYZE_OCR,
            JobType.RENDER_PREVIEW,
            JobType.RENDER_FINAL,
        }:
            # One binding point covers manual frontend actions and the Reup Queue
            # orchestrator. Product services cannot accidentally enqueue a core
            # stage without recording the exact runtime that the worker must use.
            from src.services.frontend_core_runtime import (
                bind_job_to_frontend_runtime,
            )

            bind_job_to_frontend_runtime(job)
        self.db.add(job)
        if commit:
            self.db.commit()
            self.db.refresh(job)
        else:
            # Queue orchestration binds the new job to its item in the same unit
            # of work, closing the race where a worker could finish an unlinked job.
            self.db.flush()
        logger.info("job_created", extra={"job_id": str(job.id), "job_type": job.job_type})
        return self.get_job(job.id) if commit else job

    def list_jobs(
        self,
        *,
        status: JobStatus | None = None,
        job_type: JobType | None = None,
        source_video_id: UUID | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        stmt: Select[tuple[Job]] = select(Job).options(selectinload(Job.steps))
        count_stmt = select(func.count()).select_from(Job)
        if status is not None:
            stmt = stmt.where(Job.status == status)
            count_stmt = count_stmt.where(Job.status == status)
        if job_type is not None:
            stmt = stmt.where(Job.job_type == job_type)
            count_stmt = count_stmt.where(Job.job_type == job_type)
        if source_video_id is not None:
            stmt = stmt.where(Job.source_video_id == source_video_id)
            count_stmt = count_stmt.where(Job.source_video_id == source_video_id)
        cleaned_query = (query or "").strip()
        if cleaned_query:
            pattern = f"%{cleaned_query}%"
            search_clause = or_(
                cast(Job.id, String).ilike(pattern),
                cast(Job.source_video_id, String).ilike(pattern),
                cast(Job.job_type, String).ilike(pattern),
                Job.current_step_key.ilike(pattern),
                Job.error_code.ilike(pattern),
                Job.error_message.ilike(pattern),
            )
            stmt = stmt.where(search_clause)
            count_stmt = count_stmt.where(search_clause)
        stmt = stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)
        jobs = list(self.db.scalars(stmt).unique())
        total = int(self.db.scalar(count_stmt) or 0)
        return jobs, total

    def get_job(self, job_id: UUID) -> Job:
        job = self.db.scalar(
            select(Job)
            .where(Job.id == job_id)
            .options(selectinload(Job.steps))
        )
        if job is None:
            raise JobNotFound(f"Job not found: {job_id}")
        return job

    def transition_job(
        self,
        job: Job,
        to_status: JobStatus,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> Job:
        from_status = job.status
        validate_job_transition(from_status, to_status)
        job.status = to_status
        if to_status == JobStatus.RUNNING:
            job.started_at = job.started_at or utc_now()
            job.finished_at = None
        if to_status in {JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED}:
            job.finished_at = utc_now()
        if to_status in {JobStatus.FAILED, JobStatus.RETRYABLE}:
            job.error_code = error_code
            job.error_message = error_message
        logger.info(
            "job_transition",
            extra={"job_id": str(job.id), "from_status": from_status, "to_status": to_status},
        )
        return job

    def transition_step(
        self,
        step: JobStep,
        to_status: JobStepStatus,
        *,
        progress_percent: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        output_json: dict | None = None,
    ) -> JobStep:
        from_status = step.status
        validate_step_transition(from_status, to_status)
        step.status = to_status
        if progress_percent is not None:
            step.progress_percent = max(0, min(100, progress_percent))
        if to_status == JobStepStatus.RUNNING:
            step.started_at = step.started_at or utc_now()
            step.finished_at = None
        if to_status in {JobStepStatus.COMPLETED, JobStepStatus.SKIPPED}:
            step.progress_percent = 100
            step.finished_at = utc_now()
        if to_status == JobStepStatus.FAILED:
            step.finished_at = utc_now()
            step.error_code = error_code
            step.error_message = error_message
        if output_json is not None:
            step.output_json = output_json
            step.result_json = output_json
        logger.info(
            "job_step_transition",
            extra={
                "job_id": str(step.job_id),
                "step_key": step.step_key,
                "from_status": from_status,
                "to_status": to_status,
            },
        )
        return step

    def refresh_progress(self, job: Job) -> Job:
        apply_job_progress(job)
        return job

    def retry_job(self, job_id: UUID) -> Job:
        job = self.get_job(job_id)
        if not can_retry_job(job.status, job.attempts, job.max_attempts, job.retryable):
            raise ValueError("Job is not retryable")
        if job.status == JobStatus.FAILED and job.attempts >= job.max_attempts:
            job.max_attempts = int(job.attempts) + 1
        self.transition_job(job, JobStatus.QUEUED)
        job.error_code = None
        job.error_message = None
        for step in job.steps:
            if step.status == JobStepStatus.FAILED:
                self.transition_step(step, JobStepStatus.PENDING)
                step.error_code = None
                step.error_message = None
                step.progress_percent = 0
        self.refresh_progress(job)
        self.db.commit()
        logger.info("job_retry", extra={"job_id": str(job.id)})
        return self.get_job(job.id)

    def cancel_job(self, job_id: UUID) -> Job:
        job = self.get_job(job_id)
        if not can_cancel_job(job.status):
            raise ValueError("Job cannot be cancelled")
        self.transition_job(job, JobStatus.CANCELLED)
        for step in job.steps:
            if step.status in {JobStepStatus.PENDING, JobStepStatus.RUNNING, JobStepStatus.WAITING_FOR_INPUT}:
                self.transition_step(step, JobStepStatus.SKIPPED)
        self.refresh_progress(job)
        self.db.commit()
        logger.info("job_cancel", extra={"job_id": str(job.id)})
        return self.get_job(job.id)

    def resume_job(self, job_id: UUID) -> Job:
        job = self.get_job(job_id)
        if not can_resume_job(job.status):
            raise ValueError("Job cannot be resumed")
        self.transition_job(job, JobStatus.QUEUED if job.status == JobStatus.RETRYABLE else JobStatus.RUNNING)
        for step in job.steps:
            if step.status == JobStepStatus.FAILED:
                self.transition_step(step, JobStepStatus.PENDING)
                step.error_code = None
                step.error_message = None
                step.progress_percent = 0
            if step.status == JobStepStatus.WAITING_FOR_INPUT:
                self.transition_step(step, JobStepStatus.RUNNING)
                break
        self.refresh_progress(job)
        self.db.commit()
        logger.info("job_resume", extra={"job_id": str(job.id)})
        return self.get_job(job.id)

    def delete_job(self, job_id: UUID) -> None:
        job = self.get_job(job_id)
        if not can_delete_job(job.status):
            raise ValueError("Job cannot be deleted")
        # A worker may still hold this row in another transaction.  Deleting an
        # actively claimed job would leave the worker with an orphaned execution
        # and can make it recreate/overwrite state on its next heartbeat.
        if job.status == JobStatus.RUNNING and getattr(job, "locked_by", None):
            raise ValueError("Running job is locked by a worker; cancel it and wait for the lock to clear before deleting")

        job_status = job.status
        try:
            self._preserve_job_id_in_metadata(job_id)
            self._clear_job_references(job_id)
            for step in list(job.steps):
                self.db.delete(step)
            self.db.delete(job)
            self.db.commit()
        except SQLAlchemyError as exc:
            # The UI must never treat a failed transaction as a successful
            # deletion.  Roll back so the request-scoped session remains usable.
            self.db.rollback()
            logger.exception("job_delete_failed", extra={"job_id": str(job_id)})
            raise ValueError("Job could not be deleted because linked data could not be detached") from exc
        logger.info("job_deleted", extra={"job_id": str(job_id), "status": job_status})

    def _preserve_job_id_in_metadata(self, job_id: UUID) -> None:
        """Keep a durable string job id on renders before FK columns are cleared."""
        from src.models.media import RenderOutput

        job_s = str(job_id)
        renders = list(
            self.db.scalars(select(RenderOutput).where(RenderOutput.created_by_job_id == job_id))
        )
        for render in renders:
            meta = dict(render.metadata_json or {})
            nested = dict(meta.get("manifest") or {})
            if meta.get("created_by_job_id") != job_s:
                meta["created_by_job_id"] = job_s
            if nested.get("job_id") != job_s:
                nested["job_id"] = job_s
            meta["manifest"] = nested
            render.metadata_json = meta
        if renders:
            self.db.flush()

    def _clear_job_references(self, job_id: UUID) -> None:
        """Detach every nullable FK pointing at ``jobs.id`` before deleting.

        Job provenance is intentionally retained on artifacts as metadata, but
        the relational FK must be cleared.  Discovering the columns from the
        mapped metadata prevents newer modules (analytics, affiliate, etc.) from
        silently reintroducing a delete failure when they add another job FK.
        ``job_steps.job_id`` is non-null and is deleted explicitly by the caller.
        """
        for table in Base.metadata.tables.values():
            if table.name in {"jobs", "job_steps"}:
                continue
            for column in table.columns:
                if not column.nullable:
                    continue
                if not any(
                    fk.target_fullname in {"jobs.id", "public.jobs.id"}
                    for fk in column.foreign_keys
                ):
                    continue
                self.db.execute(update(table).where(column == job_id).values({column.key: None}))
