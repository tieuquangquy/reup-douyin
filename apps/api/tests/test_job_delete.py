from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.enums import JobStatus, JobStepStatus
from src.services.job_service import JobNotFound, JobService


class JobDeleteTests(unittest.TestCase):
    def test_delete_job_clears_references_and_removes_rows(self) -> None:
        job_id = uuid4()
        step = SimpleNamespace(id=uuid4())
        job = SimpleNamespace(
            id=job_id,
            status=JobStatus.RUNNING,
            steps=[step],
        )
        db = MagicMock()
        service = JobService(db)
        service.get_job = MagicMock(return_value=job)

        service.delete_job(job_id)

        self.assertGreaterEqual(db.execute.call_count, 1)
        db.delete.assert_any_call(step)
        db.delete.assert_any_call(job)
        db.commit.assert_called_once()

    def test_delete_job_not_found(self) -> None:
        db = MagicMock()
        service = JobService(db)
        service.get_job = MagicMock(side_effect=JobNotFound("missing"))

        with self.assertRaises(JobNotFound):
            service.delete_job(uuid4())

        db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
