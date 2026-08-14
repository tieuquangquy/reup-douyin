from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.enums import (
    JobStatus,
    JobStepStatus,
    JobType,
    ReupQueueMediaPrepStatus,
    ReupQueueStatus,
)
from src.services.job_runner import JobRunner, StepHandlerRegistry
from src.services.frontend_core_runtime import bind_job_to_frontend_runtime
from src.services.reup_queue_download_sync import (
    DOWNLOAD_JOB_COMPLETED_METADATA_KEY,
    sync_reup_queue_from_download_job,
)


class FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def unique(self):
        return self

    def all(self):
        return list(self._values)

    def __iter__(self):
        return iter(self._values)


class FakeSyncDb:
    def __init__(self, items):
        self.items = items
        self.flushes = 0

    def scalars(self, _stmt):
        return FakeScalarResult(self.items)

    def flush(self):
        self.flushes += 1


def waiting_queue_item(*, job_id):
    return SimpleNamespace(
        id=uuid4(),
        job_id=job_id,
        status=ReupQueueStatus.WAITING_FOR_MEDIA,
        media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_MEDIA,
        last_error_code=None,
        last_error_message=None,
        failed_at=None,
        blocked_at=None,
        blocked_reason=None,
        last_action_note=None,
        metadata_json=None,
    )


class ReupQueueDownloadSyncTests(unittest.TestCase):
    def test_sync_completed_download_marks_queue_media_confirmable(self) -> None:
        job_id = uuid4()
        item = waiting_queue_item(job_id=job_id)
        job = SimpleNamespace(
            id=job_id,
            job_type=JobType.DOWNLOAD_VIDEO,
            status=JobStatus.COMPLETED,
            error_code=None,
            error_message=None,
        )

        updated = sync_reup_queue_from_download_job(FakeSyncDb([item]), job)

        self.assertEqual(updated, 1)
        self.assertEqual(item.status, ReupQueueStatus.WAITING_FOR_MEDIA)
        self.assertEqual(item.media_prep_status, ReupQueueMediaPrepStatus.WAITING_FOR_MEDIA)
        self.assertTrue(item.metadata_json[DOWNLOAD_JOB_COMPLETED_METADATA_KEY])
        self.assertIsNone(item.last_error_code)
        self.assertIn("confirm", (item.last_action_note or "").lower())

    def test_sync_failed_download_marks_queue_failed(self) -> None:
        job_id = uuid4()
        item = waiting_queue_item(job_id=job_id)
        job = SimpleNamespace(
            id=job_id,
            job_type=JobType.DOWNLOAD_VIDEO,
            status=JobStatus.FAILED,
            error_code="DOWNLOAD_VALIDATION_FAILED",
            error_message="Asset content is empty",
        )

        updated = sync_reup_queue_from_download_job(FakeSyncDb([item]), job)

        self.assertEqual(updated, 1)
        self.assertEqual(item.status, ReupQueueStatus.FAILED_NEEDS_ATTENTION)
        self.assertEqual(item.media_prep_status, ReupQueueMediaPrepStatus.BLOCKED)
        self.assertEqual(item.last_error_code, "DOWNLOAD_VALIDATION_FAILED")
        self.assertIn("empty", item.last_error_message)
        self.assertIsNotNone(item.failed_at)

    def test_sync_ignores_non_download_jobs(self) -> None:
        job = SimpleNamespace(id=uuid4(), job_type=JobType.ANALYZE_AUDIO, status=JobStatus.COMPLETED)
        updated = sync_reup_queue_from_download_job(FakeSyncDb([waiting_queue_item(job_id=job.id)]), job)
        self.assertEqual(updated, 0)


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


def build_download_job(*, attempts: int = 3):
    job_id = uuid4()
    source_video_id = uuid4()
    steps = [
        SimpleNamespace(step_key="validate_input", status=JobStepStatus.COMPLETED, progress_percent=100),
        SimpleNamespace(step_key="resolve_storage", status=JobStepStatus.COMPLETED, progress_percent=100),
        SimpleNamespace(step_key="fetch_primary_video", status=JobStepStatus.COMPLETED, progress_percent=100),
        SimpleNamespace(step_key="fetch_thumbnail", status=JobStepStatus.COMPLETED, progress_percent=100),
        SimpleNamespace(step_key="persist_metadata_mirror", status=JobStepStatus.COMPLETED, progress_percent=100),
        SimpleNamespace(
            step_key="register_assets",
            status=JobStepStatus.PENDING,
            progress_percent=0,
            error_code=None,
            error_message=None,
        ),
        SimpleNamespace(step_key="finalize_manifest", status=JobStepStatus.PENDING, progress_percent=0),
    ]
    job = SimpleNamespace(
        id=job_id,
        job_type=JobType.DOWNLOAD_VIDEO,
        status=JobStatus.RUNNING,
        source_video_id=source_video_id,
        payload_json={"source_video_id": str(source_video_id)},
        steps=steps,
        attempts=attempts,
        max_attempts=3,
        retryable=True,
        locked_by="worker",
        locked_at=datetime.now(UTC),
        error_code=None,
        error_message=None,
        metadata_json={},
    )
    bind_job_to_frontend_runtime(job)
    return job


class JobRunnerDownloadReupQueueSyncTests(unittest.TestCase):
    def test_download_failure_syncs_reup_queue(self) -> None:
        job = build_download_job()
        runner = JobRunner(db=MagicMock(), handlers=StepHandlerRegistry())
        runner.service = FakeJobService(job)

        with (
            patch("src.services.download_service.DownloadService.run_download") as run_download,
            patch("src.services.job_runner.sync_reup_queue_from_download_job") as sync,
        ):
            run_download.side_effect = DownloadError(
                DownloadErrorCode.VALIDATION_FAILED,
                "Asset content is empty: SOURCE_VIDEO_RAW",
            )
            sync.return_value = 1
            result = runner.run_job(job.id)

        self.assertEqual(result.status, JobStatus.FAILED)
        sync.assert_called_once()
        synced_job = sync.call_args.args[1]
        self.assertEqual(synced_job.status, JobStatus.FAILED)

    def test_download_success_syncs_reup_queue(self) -> None:
        job = build_download_job()
        for step in job.steps:
            if step.step_key != "register_assets":
                step.status = JobStepStatus.COMPLETED
        runner = JobRunner(db=MagicMock(), handlers=StepHandlerRegistry())
        runner.service = FakeJobService(job)

        with (
            patch("src.services.download_service.DownloadService.run_download") as run_download,
            patch("src.services.job_runner.sync_reup_queue_from_download_job") as sync,
        ):
            run_download.return_value = {"assets": []}
            sync.return_value = 1
            result = runner.run_job(job.id)

        self.assertEqual(result.status, JobStatus.COMPLETED)
        sync.assert_called_once()
        synced_job = sync.call_args.args[1]
        self.assertEqual(synced_job.status, JobStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
