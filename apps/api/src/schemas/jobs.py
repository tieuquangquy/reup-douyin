from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.enums import JobStatus, JobStepStatus, JobType


class JobCreateRequest(BaseModel):
    job_type: JobType
    workspace_id: UUID | None = None
    source_video_id: UUID | None = None
    crawl_session_id: UUID | None = None
    render_output_id: UUID | None = None
    reference_type: str | None = None
    reference_id: UUID | None = None
    idempotency_key: str | None = None
    priority: int = 0
    max_attempts: int = Field(default=3, ge=1, le=20)
    payload_json: dict | None = None
    context_json: dict | None = None


class JobStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    step_key: str
    step_name: str
    step_order: int
    status: JobStepStatus
    progress_percent: int
    attempts: int
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    output_json: dict | None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    job_type: JobType
    status: JobStatus
    source_video_id: UUID | None
    crawl_session_id: UUID | None
    render_output_id: UUID | None
    reference_type: str | None
    reference_id: UUID | None
    current_step_key: str | None
    current_step_index: int
    progress_percent: int
    total_steps: int
    completed_steps: int
    failed_steps: int
    priority: int
    attempts: int
    max_attempts: int
    retryable: bool
    locked_by: str | None = None
    locked_at: datetime | None = None
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    steps: list[JobStepResponse] = []


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total_count: int
    limit: int
    offset: int
