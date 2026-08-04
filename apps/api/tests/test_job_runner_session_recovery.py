"""A crashing step must never leave a job stuck as RUNNING.

When a handler raises a database error the session is poisoned, so the runner has
to roll back before writing the failure state. Otherwise the failure write raises
too and the job stays RUNNING forever (Ops shows a zombie at ~71%).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from src.enums import JobStatus, JobStepStatus
from src.services.job_runner import JobRunner


class PoisonedSessionDb(MagicMock):
    """Rejects work while the transaction is aborted, like psycopg does."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aborted = False
        self.calls: list[str] = []

    def poison(self) -> None:
        self.aborted = True

    def commit(self) -> None:  # type: ignore[override]
        self.calls.append("commit")
        if self.aborted:
            raise IntegrityError("commit", None, Exception("current transaction is aborted"))

    def rollback(self) -> None:  # type: ignore[override]
        self.calls.append("rollback")
        self.aborted = False

    def refresh(self, _obj) -> None:  # type: ignore[override]
        if self.aborted:
            raise IntegrityError("refresh", None, Exception("current transaction is aborted"))


def _job_with_one_step() -> tuple[SimpleNamespace, SimpleNamespace]:
    step = SimpleNamespace(
        step_key="register_assets",
        status=JobStepStatus.PENDING,
        progress_percent=0,
        error_code=None,
        error_message=None,
        output_json=None,
    )
    job = SimpleNamespace(
        id=uuid4(),
        job_type="GENERIC_JOB",
        status=JobStatus.RUNNING,
        steps=[step],
        attempts=1,
        max_attempts=8,
        retryable=True,
        payload_json={},
        metadata_json={},
        scheduled_at=None,
        locked_by="local-worker-1",
        locked_at=object(),
    )
    return job, step


class JobRunnerSessionRecoveryTests(unittest.TestCase):
    def test_poisoned_session_is_rolled_back_and_job_leaves_running(self) -> None:
        db = PoisonedSessionDb()
        job, step = _job_with_one_step()

        def explode(_job, _step):
            db.poison()
            raise IntegrityError("insert", None, Exception("duplicate key value violates unique constraint"))

        handlers = MagicMock()
        handlers.get.return_value = SimpleNamespace(handle=explode)

        runner = JobRunner(db=db, handlers=handlers)
        transitions: list[JobStatus] = []
        runner.service = MagicMock()
        runner.service.get_job.return_value = job
        runner.service.transition_job.side_effect = lambda j, status, **_: transitions.append(status)

        runner.run_job(job.id)

        self.assertIn("rollback", db.calls, "Runner must roll back the aborted transaction")
        self.assertLess(
            db.calls.index("rollback"),
            len(db.calls) - 1,
            "Rollback must happen before the failure state is committed",
        )
        self.assertIn(
            JobStatus.RETRYABLE,
            transitions,
            "A crashed step must requeue the job instead of leaving it RUNNING",
        )
        self.assertIsNone(job.locked_by, "A requeued job must release its worker lock")


if __name__ == "__main__":
    unittest.main()
