from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.enums import JobStatus, JobStepStatus
from src.services.job_service import JobService


def _step(
    *,
    job_id,
    step_key: str,
    step_order: int,
    status: JobStepStatus,
    progress_percent: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        job_id=job_id,
        step_key=step_key,
        step_order=step_order,
        status=status,
        progress_percent=progress_percent,
        started_at=None,
        finished_at=None,
        error_code=None,
        error_message=None,
        output_json=None,
        result_json=None,
    )


class JobCancelProgressTests(unittest.TestCase):
    def test_cancel_job_sets_job_progress_to_zero(self) -> None:
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            status=JobStatus.RUNNING,
            steps=[
                _step(job_id=job_id, step_key="download", step_order=0, status=JobStepStatus.RUNNING, progress_percent=45),
                _step(job_id=job_id, step_key="process", step_order=1, status=JobStepStatus.PENDING),
            ],
            progress_percent=22,
            total_steps=2,
            completed_steps=0,
            failed_steps=0,
            current_step_key="download",
            current_step_index=0,
            finished_at=None,
            error_code=None,
            error_message=None,
        )
        db = MagicMock()
        service = JobService(db)
        service.get_job = MagicMock(return_value=job)

        service.cancel_job(job_id)

        self.assertEqual(job.status, JobStatus.CANCELLED)
        self.assertEqual(job.progress_percent, 0)


if __name__ == "__main__":
    unittest.main()
