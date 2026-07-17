from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.enums import JobStatus, JobStepStatus, JobType
from src.services.job_runner import JobRunner, StepHandlerRegistry


class FakeJobService:
    def __init__(self, job):
        self.job = job
        self.job_status = job.status
        self.step_statuses = {step.step_key: step.status for step in job.steps}

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


def build_download_job():
    job_id = uuid4()
    source_video_id = uuid4()
    steps = [
        SimpleNamespace(step_key="validate_input", status=JobStepStatus.PENDING, progress_percent=0, error_code=None, error_message=None),
        SimpleNamespace(step_key="resolve_storage", status=JobStepStatus.PENDING, progress_percent=0, error_code=None, error_message=None),
        SimpleNamespace(step_key="fetch_primary_video", status=JobStepStatus.PENDING, progress_percent=0, error_code=None, error_message=None),
        SimpleNamespace(step_key="fetch_thumbnail", status=JobStepStatus.PENDING, progress_percent=0, error_code=None, error_message=None),
        SimpleNamespace(step_key="persist_metadata_mirror", status=JobStepStatus.PENDING, progress_percent=0, error_code=None, error_message=None),
        SimpleNamespace(step_key="register_assets", status=JobStepStatus.PENDING, progress_percent=0, error_code=None, error_message=None),
        SimpleNamespace(step_key="finalize_manifest", status=JobStepStatus.PENDING, progress_percent=0, error_code=None, error_message=None),
    ]
    job = SimpleNamespace(
        id=job_id,
        job_type=JobType.DOWNLOAD_VIDEO,
        status=JobStatus.RUNNING,
        source_video_id=source_video_id,
        payload_json={"source_video_id": str(source_video_id)},
        steps=steps,
        attempts=3,
        max_attempts=3,
        retryable=True,
        locked_by="worker",
        locked_at=None,
        error_code=None,
        error_message=None,
    )
    return job


class JobRunnerDownloadErrorTests(unittest.TestCase):
    def test_register_assets_download_error_marks_job_failed(self):
        job = build_download_job()
        service = FakeJobService(job)
        db = MagicMock()
        db.scalars.return_value.unique.return_value = []
        runner = JobRunner(db=db, handlers=StepHandlerRegistry())
        runner.service = service

        with patch("src.services.download_service.DownloadService.run_download") as run_download:
            run_download.side_effect = DownloadError(
                DownloadErrorCode.VALIDATION_FAILED,
                "Asset content is empty: SOURCE_VIDEO_RAW",
            )
            result = runner.run_job(job.id)

        self.assertEqual(result.status, JobStatus.FAILED)
        register_step = next(step for step in job.steps if step.step_key == "register_assets")
        self.assertEqual(register_step.status, JobStepStatus.FAILED)
        self.assertEqual(register_step.error_code, DownloadErrorCode.VALIDATION_FAILED)
        self.assertIn("SOURCE_VIDEO_RAW", register_step.error_message)

    def test_register_assets_unexpected_exception_marks_job_failed(self):
        job = build_download_job()
        service = FakeJobService(job)
        db = MagicMock()
        db.scalars.return_value.unique.return_value = []
        runner = JobRunner(db=db, handlers=StepHandlerRegistry())
        runner.service = service

        with patch("src.services.download_service.DownloadService.run_download") as run_download:
            run_download.side_effect = TimeoutError("timed out")
            result = runner.run_job(job.id)

        self.assertIn(result.status, {JobStatus.FAILED, JobStatus.RETRYABLE})
        register_step = next(step for step in job.steps if step.step_key == "register_assets")
        self.assertEqual(register_step.status, JobStepStatus.FAILED)
        self.assertEqual(register_step.error_code, "download_unhandled_error")
        self.assertIn("timed out", (register_step.error_message or "").lower())


if __name__ == "__main__":
    unittest.main()
