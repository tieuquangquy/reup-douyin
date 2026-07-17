from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.download_error_policy import (
    DownloadFailureClass,
    classify_download_failure,
    download_failure_operator_message,
    next_download_retry_at,
    should_auto_retry_download_failure,
)
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.enums import JobStatus, JobStepStatus, JobType
from src.services.job_runner import JobRunner, StepHandlerRegistry


class DownloadErrorPolicyTests(unittest.TestCase):
    def test_classifies_transient_auth_terminal(self) -> None:
        self.assertEqual(
            classify_download_failure("download_failed", "Playwright media download HTTP 403"),
            DownloadFailureClass.TRANSIENT,
        )
        self.assertEqual(
            classify_download_failure("download_failed", "browser_context_lost:TargetClosedError"),
            DownloadFailureClass.TRANSIENT,
        )
        self.assertEqual(
            classify_download_failure("resolve_failed", "Refresh download session: open the app-managed"),
            DownloadFailureClass.AUTH,
        )
        self.assertEqual(
            classify_download_failure("missing_source_url", "Source video has no download URL"),
            DownloadFailureClass.TERMINAL,
        )
        self.assertEqual(
            classify_download_failure("validation_failed", "Asset content is empty: SOURCE_VIDEO_RAW"),
            DownloadFailureClass.TERMINAL,
        )

    def test_auto_retry_respects_class_and_attempt_caps(self) -> None:
        self.assertTrue(
            should_auto_retry_download_failure(
                failure_class=DownloadFailureClass.TRANSIENT,
                attempts=3,
                transient_max_attempts=8,
                auth_max_attempts=2,
            )
        )
        self.assertFalse(
            should_auto_retry_download_failure(
                failure_class=DownloadFailureClass.TERMINAL,
                attempts=1,
                transient_max_attempts=8,
                auth_max_attempts=2,
            )
        )
        self.assertTrue(
            should_auto_retry_download_failure(
                failure_class=DownloadFailureClass.AUTH,
                attempts=1,
                transient_max_attempts=8,
                auth_max_attempts=2,
            )
        )
        self.assertFalse(
            should_auto_retry_download_failure(
                failure_class=DownloadFailureClass.AUTH,
                attempts=2,
                transient_max_attempts=8,
                auth_max_attempts=2,
            )
        )

    def test_backoff_increases_and_operator_message_has_cta(self) -> None:
        first = next_download_retry_at(attempts=1, now=datetime(2026, 7, 14, 12, 0, tzinfo=UTC))
        second = next_download_retry_at(attempts=2, now=datetime(2026, 7, 14, 12, 0, tzinfo=UTC))
        self.assertGreater(second, first)
        msg = download_failure_operator_message(
            failure_class=DownloadFailureClass.AUTH,
            error_message="cookies missing",
            will_retry=False,
        )
        self.assertIn("Refresh download session", msg)
        self.assertIn("manual check", msg.lower())


class FakeJobService:
    def __init__(self, job):
        self.job = job

    def get_job(self, job_id):
        return self.job

    def transition_job(self, job, status, **kwargs):
        job.status = status
        if kwargs.get("error_code"):
            job.error_code = kwargs["error_code"]
        if kwargs.get("error_message"):
            job.error_message = kwargs["error_message"]

    def transition_step(self, step, status, **kwargs):
        step.status = status
        if kwargs.get("error_code"):
            step.error_code = kwargs["error_code"]
        if kwargs.get("error_message"):
            step.error_message = kwargs["error_message"]

    def refresh_progress(self, job):
        return None


def build_download_job(*, attempts: int = 1, max_attempts: int = 8):
    source_video_id = uuid4()
    steps = [
        SimpleNamespace(
            step_key="register_assets",
            status=JobStepStatus.PENDING,
            progress_percent=0,
            error_code=None,
            error_message=None,
        ),
    ]
    return SimpleNamespace(
        id=uuid4(),
        job_type=JobType.DOWNLOAD_VIDEO,
        status=JobStatus.RUNNING,
        source_video_id=source_video_id,
        payload_json={"source_video_id": str(source_video_id)},
        steps=steps,
        attempts=attempts,
        max_attempts=max_attempts,
        retryable=True,
        locked_by="worker",
        locked_at=None,
        scheduled_at=None,
        error_code=None,
        error_message=None,
        metadata_json={},
    )


class JobRunnerDownloadRetryPolicyTests(unittest.TestCase):
    def test_terminal_download_error_fails_immediately(self) -> None:
        job = build_download_job(attempts=1, max_attempts=8)
        runner = JobRunner(db=MagicMock(), handlers=StepHandlerRegistry())
        runner.service = FakeJobService(job)

        with patch("src.services.download_service.DownloadService.run_download") as run_download:
            run_download.side_effect = DownloadError(
                DownloadErrorCode.VALIDATION_FAILED,
                "Asset content is empty: SOURCE_VIDEO_RAW",
            )
            result = runner.run_job(job.id)

        self.assertEqual(result.status, JobStatus.FAILED)
        self.assertIn("manual check", (result.error_message or "").lower())

    def test_transient_download_error_marks_retryable_with_backoff(self) -> None:
        job = build_download_job(attempts=1, max_attempts=8)
        runner = JobRunner(db=MagicMock(), handlers=StepHandlerRegistry())
        runner.service = FakeJobService(job)
        runner.db.commit = MagicMock()

        with (
            patch("src.services.download_service.DownloadService.run_download") as run_download,
            patch("src.services.job_runner.sync_reup_queue_from_download_job"),
        ):
            run_download.side_effect = DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                "Playwright media download HTTP 403",
            )
            result = runner.run_job(job.id)

        self.assertEqual(result.status, JobStatus.RETRYABLE)
        self.assertIsNotNone(job.scheduled_at)
        self.assertGreater(job.scheduled_at, datetime.now(UTC) - timedelta(seconds=1))
        self.assertIn("auto-retry", (result.error_message or "").lower())

    def test_auth_download_error_stops_after_auth_cap(self) -> None:
        job = build_download_job(attempts=2, max_attempts=8)
        runner = JobRunner(db=MagicMock(), handlers=StepHandlerRegistry())
        runner.service = FakeJobService(job)

        with (
            patch("src.services.download_service.DownloadService.run_download") as run_download,
            patch("src.services.job_runner.sync_reup_queue_from_download_job"),
        ):
            run_download.side_effect = DownloadError(
                DownloadErrorCode.RESOLVE_FAILED,
                "Refresh download session: open the app-managed Douyin Chromium",
            )
            result = runner.run_job(job.id)

        self.assertEqual(result.status, JobStatus.FAILED)
        self.assertIn("Refresh download session", result.error_message or "")

    def test_claim_skips_jobs_scheduled_in_future(self) -> None:
        db = MagicMock()
        db.scalar.return_value = None
        runner = JobRunner(db=db, handlers=StepHandlerRegistry())
        claimed = runner.claim_next_job("worker-1")
        self.assertIsNone(claimed)
        self.assertTrue(db.scalar.called)
        stmt = db.scalar.call_args.args[0]
        where_sql = str(stmt.whereclause).lower()
        self.assertIn("scheduled_at", where_sql)


if __name__ == "__main__":
    unittest.main()
