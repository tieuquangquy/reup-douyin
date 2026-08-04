from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from src.enums import JobStatus, JobStepStatus
from src.services.job_runner import JobRunner, StepHandlerRegistry
from src.services.job_state_machine import validate_job_transition, validate_step_transition


class _PersistingSession:
    """Emulate SQLAlchemy expiration so an uncommitted status is lost on refresh."""

    def __init__(self, job: SimpleNamespace):
        self.job = job
        self.persisted_status = job.status
        self.commit_count = 0

    def commit(self) -> None:
        self.persisted_status = self.job.status
        self.commit_count += 1

    def refresh(self, row: SimpleNamespace) -> None:
        if row is self.job:
            row.status = self.persisted_status


class _StrictJobService:
    def __init__(self, job: SimpleNamespace):
        self.job = job

    def get_job(self, _job_id):
        return self.job

    def transition_job(self, job, status, **_kwargs):
        validate_job_transition(job.status, status)
        job.status = status

    def transition_step(self, step, status, **kwargs):
        validate_step_transition(step.status, status)
        step.status = status
        if kwargs.get("progress_percent") is not None:
            step.progress_percent = kwargs["progress_percent"]
        step.output_json = kwargs.get("output_json")

    def refresh_progress(self, job):
        return job


class QueuedJobStartTests(unittest.TestCase):
    def test_direct_run_persists_running_before_cancel_refresh(self) -> None:
        step = SimpleNamespace(
            step_key="work",
            status=JobStepStatus.PENDING,
            progress_percent=0,
            error_code=None,
            error_message=None,
            output_json=None,
        )
        job = SimpleNamespace(
            id=uuid4(),
            job_type="LOCAL_PILOT",
            status=JobStatus.QUEUED,
            steps=[step],
            payload_json={},
            source_video_id=None,
            render_output_id=None,
            attempts=0,
            max_attempts=1,
            retryable=False,
            locked_by=None,
            locked_at=None,
            scheduled_at=None,
            error_code=None,
            error_message=None,
            metadata_json={},
            crawl_session_id=None,
        )
        db = _PersistingSession(job)
        runner = JobRunner(db, handlers=StepHandlerRegistry())  # type: ignore[arg-type]
        runner.service = _StrictJobService(job)  # type: ignore[assignment]

        with (
            patch("src.services.job_runner.sync_reup_queue_from_download_job"),
            patch("src.services.job_runner.ReupPipelineOrchestrator") as orchestrator,
        ):
            result = runner.run_job(job.id)

        self.assertEqual(result.status, JobStatus.COMPLETED)
        self.assertEqual(result.attempts, 1)
        self.assertIsNone(result.scheduled_at)
        self.assertEqual(step.status, JobStepStatus.COMPLETED)
        self.assertGreaterEqual(db.commit_count, 3)
        orchestrator.return_value.on_job_terminal.assert_called_once_with(job)


if __name__ == "__main__":
    unittest.main()
