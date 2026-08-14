from dataclasses import dataclass

from src.enums import JobStatus, JobStepStatus


class InvalidJobTransition(ValueError):
    pass


class InvalidJobStepTransition(ValueError):
    pass


JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {
        JobStatus.WAITING_FOR_REVIEW,
        JobStatus.FAILED,
        JobStatus.RETRYABLE,
        JobStatus.CANCELLED,
        JobStatus.COMPLETED,
    },
    JobStatus.WAITING_FOR_REVIEW: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.FAILED: {JobStatus.RETRYABLE, JobStatus.QUEUED},
    JobStatus.RETRYABLE: {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.CANCELLED: set(),
    JobStatus.COMPLETED: set(),
}

JOB_STEP_TRANSITIONS: dict[JobStepStatus, set[JobStepStatus]] = {
    JobStepStatus.PENDING: {JobStepStatus.RUNNING, JobStepStatus.SKIPPED},
    JobStepStatus.RUNNING: {
        JobStepStatus.WAITING_FOR_INPUT,
        JobStepStatus.FAILED,
        JobStepStatus.SKIPPED,
        JobStepStatus.COMPLETED,
    },
    JobStepStatus.WAITING_FOR_INPUT: {JobStepStatus.RUNNING, JobStepStatus.SKIPPED},
    JobStepStatus.FAILED: {JobStepStatus.PENDING, JobStepStatus.RUNNING, JobStepStatus.SKIPPED},
    JobStepStatus.SKIPPED: set(),
    JobStepStatus.COMPLETED: set(),
}


@dataclass(frozen=True)
class Transition:
    from_status: str
    to_status: str


def validate_job_transition(from_status: JobStatus, to_status: JobStatus) -> Transition:
    if from_status == to_status:
        return Transition(from_status=from_status, to_status=to_status)
    if to_status not in JOB_TRANSITIONS[from_status]:
        raise InvalidJobTransition(f"Invalid job transition: {from_status} -> {to_status}")
    return Transition(from_status=from_status, to_status=to_status)


def validate_step_transition(from_status: JobStepStatus, to_status: JobStepStatus) -> Transition:
    if from_status == to_status:
        return Transition(from_status=from_status, to_status=to_status)
    if to_status not in JOB_STEP_TRANSITIONS[from_status]:
        raise InvalidJobStepTransition(f"Invalid job step transition: {from_status} -> {to_status}")
    return Transition(from_status=from_status, to_status=to_status)


def can_retry_job(status: JobStatus, attempts: int, max_attempts: int, retryable: bool = True) -> bool:
    if not retryable or status not in {JobStatus.FAILED, JobStatus.RETRYABLE}:
        return False
    # RETRYABLE is an automatic scheduling state and stays within its budget.
    # FAILED is terminal for automation, but an explicit operator retry may
    # grant one additional attempt after the original budget is exhausted.
    return status == JobStatus.FAILED or attempts < max_attempts


def can_cancel_job(status: JobStatus) -> bool:
    return status not in {JobStatus.CANCELLED, JobStatus.COMPLETED}


def can_resume_job(status: JobStatus) -> bool:
    return status in {JobStatus.WAITING_FOR_REVIEW, JobStatus.RETRYABLE}


def can_delete_job(status: JobStatus) -> bool:
    """Local ops cleanup: allow removing stale or terminal jobs from the monitor."""
    return status in {
        JobStatus.QUEUED,
        JobStatus.RUNNING,
        JobStatus.WAITING_FOR_REVIEW,
        JobStatus.FAILED,
        JobStatus.RETRYABLE,
        JobStatus.CANCELLED,
        JobStatus.COMPLETED,
    }
