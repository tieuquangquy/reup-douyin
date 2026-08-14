from datetime import datetime
from uuid import UUID

from src.enums import JobStatus, JobStepStatus, JobType
from src.models.jobs import Job, JobStep
from src.services.job_progress import apply_job_progress
from src.services.job_templates import get_step_templates


def build_job(
    *,
    workspace_id: UUID,
    job_type: JobType,
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
) -> Job:
    steps = [
        JobStep(
            workspace_id=workspace_id,
            step_key=template.key,
            step_name=template.name,
            status=JobStepStatus.PENDING,
            sequence_index=template.order,
            step_order=template.order,
            progress_percent=0,
            input_json={},
        )
        for template in get_step_templates(job_type)
    ]
    job = Job(
        workspace_id=workspace_id,
        job_type=job_type,
        status=JobStatus.QUEUED,
        source_video_id=source_video_id,
        crawl_session_id=crawl_session_id,
        render_output_id=render_output_id,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        priority=priority,
        max_attempts=max_attempts,
        retryable=True,
        payload_json=payload_json,
        input_json=payload_json,
        context_json=context_json,
        metadata_json=metadata_json,
        scheduled_at=scheduled_at,
        steps=steps,
    )
    apply_job_progress(job)
    return job
