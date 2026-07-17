from collections.abc import Sequence

from src.enums import JobStepStatus


TERMINAL_PROGRESS_STATUSES = {JobStepStatus.COMPLETED, JobStepStatus.SKIPPED}


def clamp_percent(value: int | float) -> int:
    return max(0, min(100, int(round(value))))


def calculate_job_progress(steps: Sequence[object]) -> dict[str, int | str | None]:
    total_steps = len(steps)
    if total_steps == 0:
        return {
            "progress_percent": 0,
            "total_steps": 0,
            "completed_steps": 0,
            "failed_steps": 0,
            "current_step_key": None,
            "current_step_index": 0,
        }

    completed_steps = sum(1 for step in steps if step.status == JobStepStatus.COMPLETED)
    skipped_steps = sum(1 for step in steps if step.status == JobStepStatus.SKIPPED)
    failed_steps = sum(1 for step in steps if step.status == JobStepStatus.FAILED)
    current_step = next(
        (
            step
            for step in steps
            if step.status
            in {
                JobStepStatus.RUNNING,
                JobStepStatus.WAITING_FOR_INPUT,
                JobStepStatus.FAILED,
                JobStepStatus.PENDING,
            }
        ),
        None,
    )
    completed_weight = completed_steps + skipped_steps
    active_step_progress = 0
    if current_step is not None and current_step.status == JobStepStatus.RUNNING:
        active_step_progress = clamp_percent(current_step.progress_percent)

    progress_percent = clamp_percent(
        ((completed_weight * 100) + active_step_progress) / total_steps
    )
    if completed_steps + skipped_steps == total_steps:
        progress_percent = 100

    return {
        "progress_percent": progress_percent,
        "total_steps": total_steps,
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "current_step_key": current_step.step_key if current_step is not None else None,
        "current_step_index": current_step.step_order if current_step is not None else total_steps,
    }


def apply_job_progress(job: object) -> None:
    progress = calculate_job_progress(list(job.steps))
    job.progress_percent = progress["progress_percent"]
    job.total_steps = progress["total_steps"]
    job.completed_steps = progress["completed_steps"]
    job.failed_steps = progress["failed_steps"]
    job.current_step_key = progress["current_step_key"]
    job.current_step_index = progress["current_step_index"]

