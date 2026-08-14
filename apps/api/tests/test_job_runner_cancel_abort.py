from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import JobStatus, JobStepStatus, JobType
from src.services.frontend_core_runtime import bind_job_to_frontend_runtime
from src.services.job_runner import JobRunner, StepHandlerRegistry
from src.services.job_state_machine import InvalidJobStepTransition, validate_job_transition, validate_step_transition


class StrictFakeJobService:
    """Mirrors JobService transition validation so cancel mid-flight can reproduce worker crashes."""

    def __init__(self, job):
        self.job = job

    def get_job(self, _job_id):
        return self.job

    def transition_job(self, job, status, **kwargs):
        validate_job_transition(job.status, status)
        job.status = status
        if kwargs.get("error_code"):
            job.error_code = kwargs["error_code"]
        if kwargs.get("error_message"):
            job.error_message = kwargs["error_message"]

    def transition_step(self, step, status, **kwargs):
        validate_step_transition(step.status, status)
        step.status = status
        if kwargs.get("progress_percent") is not None:
            step.progress_percent = kwargs["progress_percent"]
        if kwargs.get("error_code"):
            step.error_code = kwargs["error_code"]
        if kwargs.get("error_message"):
            step.error_message = kwargs["error_message"]

    def refresh_progress(self, job):
        return job


def build_download_job_at_register_assets():
    job_id = uuid4()
    source_video_id = uuid4()
    steps = [
        SimpleNamespace(
            step_key="validate_input",
            status=JobStepStatus.COMPLETED,
            progress_percent=100,
            error_code=None,
            error_message=None,
            job_id=job_id,
        ),
        SimpleNamespace(
            step_key="resolve_storage",
            status=JobStepStatus.COMPLETED,
            progress_percent=100,
            error_code=None,
            error_message=None,
            job_id=job_id,
        ),
        SimpleNamespace(
            step_key="fetch_primary_video",
            status=JobStepStatus.COMPLETED,
            progress_percent=100,
            error_code=None,
            error_message=None,
            job_id=job_id,
        ),
        SimpleNamespace(
            step_key="fetch_thumbnail",
            status=JobStepStatus.COMPLETED,
            progress_percent=100,
            error_code=None,
            error_message=None,
            job_id=job_id,
        ),
        SimpleNamespace(
            step_key="persist_metadata_mirror",
            status=JobStepStatus.COMPLETED,
            progress_percent=100,
            error_code=None,
            error_message=None,
            job_id=job_id,
        ),
        SimpleNamespace(
            step_key="register_assets",
            status=JobStepStatus.RUNNING,
            progress_percent=40,
            error_code=None,
            error_message=None,
            job_id=job_id,
        ),
        SimpleNamespace(
            step_key="finalize_manifest",
            status=JobStepStatus.PENDING,
            progress_percent=0,
            error_code=None,
            error_message=None,
            job_id=job_id,
        ),
    ]
    job = SimpleNamespace(
        id=job_id,
        job_type=JobType.DOWNLOAD_VIDEO,
        status=JobStatus.RUNNING,
        source_video_id=source_video_id,
        payload_json={"source_video_id": str(source_video_id)},
        steps=steps,
        attempts=1,
        max_attempts=3,
        retryable=True,
        locked_by="local-worker-1",
        locked_at=None,
        error_code=None,
        error_message=None,
        metadata_json={},
    )
    bind_job_to_frontend_runtime(job)
    return job


def simulate_operator_cancel(job) -> None:
    job.status = JobStatus.CANCELLED
    for step in job.steps:
        if step.status in {JobStepStatus.PENDING, JobStepStatus.RUNNING, JobStepStatus.WAITING_FOR_INPUT}:
            step.status = JobStepStatus.SKIPPED
            step.progress_percent = 100


class JobRunnerCancelAbortTests(unittest.TestCase):
    def test_run_job_aborts_cleanly_when_cancelled_during_download(self) -> None:
        job = build_download_job_at_register_assets()
        service = StrictFakeJobService(job)
        db = MagicMock()
        runner = JobRunner(db=db, handlers=StepHandlerRegistry())
        runner.service = service

        def cancel_mid_download(*_args, **_kwargs):
            simulate_operator_cancel(job)
            return {"assets": []}

        with (
            patch("src.services.download_service.DownloadService.run_download", side_effect=cancel_mid_download),
            patch("src.services.job_runner.sync_reup_queue_from_download_job"),
        ):
            result = runner.run_job(job.id)

        self.assertEqual(result.status, JobStatus.CANCELLED)
        self.assertIsNone(result.locked_by)
        register_step = next(step for step in job.steps if step.step_key == "register_assets")
        self.assertEqual(register_step.status, JobStepStatus.SKIPPED)
        finalize_step = next(step for step in job.steps if step.step_key == "finalize_manifest")
        self.assertEqual(finalize_step.status, JobStepStatus.SKIPPED)

    def test_run_job_without_abort_would_raise_on_skipped_step_complete(self) -> None:
        """Documents the pre-fix failure mode: SKIPPED -> COMPLETED is illegal."""
        job = build_download_job_at_register_assets()
        simulate_operator_cancel(job)
        register_step = next(step for step in job.steps if step.step_key == "register_assets")
        with self.assertRaises(InvalidJobStepTransition):
            validate_step_transition(register_step.status, JobStepStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
