from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from src.enums import JobStatus, JobStepStatus
from src.services.job_service import JobService


class ManualJobRetryTests(unittest.TestCase):
    def test_operator_retry_grants_one_attempt_after_auto_budget_exhausted(self) -> None:
        step = SimpleNamespace(
            job_id=uuid4(),
            step_key="persist_outputs",
            status=JobStepStatus.FAILED,
            error_code="narration_assembly_failed",
            error_message="invalid WAV",
            progress_percent=0,
            started_at=None,
            finished_at=None,
            output_json=None,
            result_json=None,
        )
        job = SimpleNamespace(
            id=step.job_id,
            status=JobStatus.FAILED,
            attempts=3,
            max_attempts=3,
            retryable=True,
            error_code="narration_assembly_failed",
            error_message="invalid WAV",
            started_at=None,
            finished_at=None,
            steps=[step],
        )
        db = MagicMock()
        service = JobService(db)
        service.get_job = MagicMock(return_value=job)
        service.refresh_progress = MagicMock(return_value=job)

        retried = service.retry_job(job.id)

        self.assertIs(retried, job)
        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertEqual(job.max_attempts, 4)
        self.assertIsNone(job.error_code)
        self.assertEqual(step.status, JobStepStatus.PENDING)
        self.assertIsNone(step.error_code)
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
