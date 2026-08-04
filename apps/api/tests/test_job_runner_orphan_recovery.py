"""Orphan RUNNING jobs must be reclaimable after worker crash/exception."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.enums import JobStatus, JobStepStatus, JobType
from src.services.job_runner import JobRunner, StepHandlerResult


class ReleaseOrphanedLocksTests(unittest.TestCase):
    def test_release_orphaned_locks_requeues_running_job_for_same_worker(self) -> None:
        job_id = uuid4()
        step = SimpleNamespace(
            step_key="persist_outputs",
            status=JobStepStatus.RUNNING,
            progress_percent=25,
            error_code=None,
            error_message=None,
            metadata_json={"ocr_phase": "phase2_ocr"},
            job_id=job_id,
        )
        job = SimpleNamespace(
            id=job_id,
            job_type=JobType.COLLECT_PUBLICATION_METRICS,
            status=JobStatus.RUNNING,
            locked_by="local-worker-1",
            locked_at=datetime.now(UTC),
            scheduled_at=None,
            steps=[step],
            attempts=1,
            max_attempts=3,
            retryable=True,
            error_code=None,
            error_message=None,
            metadata_json={},
        )
        db = MagicMock()
        db.scalars.return_value.all.return_value = [job]
        runner = JobRunner(db)
        runner.service = MagicMock()
        runner.service.refresh_progress.side_effect = lambda j: j

        def _transition_job(j, status, **kwargs):
            j.status = status
            if kwargs.get("error_code"):
                j.error_code = kwargs["error_code"]
            if kwargs.get("error_message"):
                j.error_message = kwargs["error_message"]

        def _transition_step(s, status, **kwargs):
            s.status = status
            if kwargs.get("progress_percent") is not None:
                s.progress_percent = kwargs["progress_percent"]
            if kwargs.get("error_code"):
                s.error_code = kwargs["error_code"]
            if kwargs.get("error_message"):
                s.error_message = kwargs["error_message"]

        runner.service.transition_job.side_effect = _transition_job
        runner.service.transition_step.side_effect = _transition_step
        count = runner.release_orphaned_locks("local-worker-1")
        self.assertEqual(count, 1)
        self.assertEqual(job.status, JobStatus.RETRYABLE)
        self.assertIsNone(job.locked_by)
        self.assertIsNone(job.locked_at)
        self.assertEqual(step.status, JobStepStatus.FAILED)
        self.assertEqual(step.error_code, "WORKER_ORPHANED")
        db.commit.assert_called()

    def test_release_orphaned_locks_stops_when_metric_retry_budget_is_exhausted(self) -> None:
        job_id = uuid4()
        step = SimpleNamespace(
            step_key="collect_and_persist_snapshot",
            status=JobStepStatus.RUNNING,
            progress_percent=50,
            error_code=None,
            error_message=None,
            job_id=job_id,
        )
        job = SimpleNamespace(
            id=job_id,
            job_type=JobType.COLLECT_PUBLICATION_METRICS,
            status=JobStatus.RUNNING,
            locked_by="local-worker-1",
            locked_at=datetime.now(UTC),
            scheduled_at=None,
            steps=[step],
            attempts=5,
            max_attempts=5,
            retryable=True,
            error_code=None,
            error_message=None,
            metadata_json={},
        )
        db = MagicMock()
        db.scalars.return_value.all.return_value = [job]
        runner = JobRunner(db)
        runner.service = MagicMock()
        runner.service.refresh_progress.side_effect = lambda j: j
        runner.service.transition_job.side_effect = lambda j, status, **_kwargs: setattr(j, "status", status)
        runner.service.transition_step.side_effect = lambda s, status, **_kwargs: setattr(s, "status", status)

        count = runner.release_orphaned_locks("local-worker-1")

        self.assertEqual(count, 1)
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(step.status, JobStepStatus.FAILED)
        self.assertFalse(job.metadata_json["metrics_will_auto_retry"])
        self.assertIsNone(job.scheduled_at)


class UnhandledStepExceptionTests(unittest.TestCase):
    def test_run_job_marks_failed_when_step_raises_unexpected(self) -> None:
        job_id = uuid4()
        step = SimpleNamespace(
            step_key="persist_outputs",
            status=JobStepStatus.PENDING,
            progress_percent=0,
            error_code=None,
            error_message=None,
            output_json=None,
            metadata_json=None,
            job_id=job_id,
        )
        job = SimpleNamespace(
            id=job_id,
            job_type="NO_TYPED_HANDLER",
            status=JobStatus.RUNNING,
            locked_by="local-worker-1",
            locked_at=datetime.now(UTC),
            scheduled_at=None,
            steps=[step],
            payload_json={"source_video_id": str(uuid4())},
            source_video_id=None,
            retryable=False,
            attempts=1,
            max_attempts=3,
            error_code=None,
            error_message=None,
            metadata_json={},
            crawl_session_id=None,
            render_output_id=None,
        )

        class BoomHandler:
            def handle(self, _job, _step) -> StepHandlerResult:
                raise RuntimeError("simulated worker crash mid-step")

        db = MagicMock()
        registry = MagicMock()
        registry.get.return_value = BoomHandler()
        runner = JobRunner(db, handlers=registry)
        runner.service = MagicMock()
        runner.service.get_job.return_value = job
        runner.service.refresh_progress.side_effect = lambda j: j

        def _transition_job(j, status, **kwargs):
            j.status = status
            if kwargs.get("error_code"):
                j.error_code = kwargs["error_code"]
            if kwargs.get("error_message"):
                j.error_message = kwargs["error_message"]

        def _transition_step(s, status, **kwargs):
            s.status = status
            if kwargs.get("progress_percent") is not None:
                s.progress_percent = kwargs["progress_percent"]
            if kwargs.get("error_code"):
                s.error_code = kwargs["error_code"]
            if kwargs.get("error_message"):
                s.error_message = kwargs["error_message"]

        runner.service.transition_job.side_effect = _transition_job
        runner.service.transition_step.side_effect = _transition_step

        out = runner.run_job(job_id)
        self.assertEqual(out.status, JobStatus.FAILED)
        self.assertEqual(step.status, JobStepStatus.FAILED)
        self.assertEqual(out.error_code, "STEP_UNHANDLED_ERROR")
        self.assertIn("simulated worker crash", out.error_message or "")


if __name__ == "__main__":
    unittest.main()
