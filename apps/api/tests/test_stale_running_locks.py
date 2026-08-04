"""Stale RUNNING jobs must be requeued so one hung download cannot block the worker forever."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import JobStatus, JobStepStatus, JobType
from src.services.job_runner import JobRunner, download_stale_running_seconds


class StaleRunningLockTests(unittest.TestCase):
    def test_download_stale_threshold_covers_bridge_budget(self) -> None:
        settings = SimpleNamespace(
            douyin_playwright_download_timeout_ms=90_000,
            douyin_yt_dlp_timeout_seconds=180,
            download_video_stale_running_seconds=None,
        )
        # Must exceed ~255s bridge budget so healthy downloads are not requeued early.
        self.assertGreaterEqual(download_stale_running_seconds(settings), 600)

    def test_release_stale_running_locks_requeues_old_running_job(self) -> None:
        job_id = uuid4()
        step = SimpleNamespace(
            step_key="register_assets",
            status=JobStepStatus.RUNNING,
            progress_percent=71,
            error_code=None,
            error_message=None,
            job_id=job_id,
        )
        job = SimpleNamespace(
            id=job_id,
            job_type=JobType.DOWNLOAD_VIDEO,
            status=JobStatus.RUNNING,
            locked_by="local-worker-1",
            locked_at=datetime.now(UTC) - timedelta(minutes=20),
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
            j.error_code = kwargs.get("error_code")
            j.error_message = kwargs.get("error_message")

        def _transition_step(s, status, **kwargs):
            s.status = status
            if kwargs.get("error_code"):
                s.error_code = kwargs["error_code"]

        runner.service.transition_job.side_effect = _transition_job
        runner.service.transition_step.side_effect = _transition_step

        with patch(
            "src.services.job_runner.download_stale_running_seconds",
            return_value=600,
        ):
            count = runner.release_stale_running_locks()

        self.assertEqual(count, 1)
        self.assertEqual(job.status, JobStatus.RETRYABLE)
        self.assertEqual(job.error_code, "WORKER_STALE_RUNNING")
        self.assertIsNone(job.locked_by)
        self.assertEqual(step.status, JobStepStatus.FAILED)
        db.commit.assert_called()


if __name__ == "__main__":
    unittest.main()
