"""Two workers counting free slots at the same time both see a free slot.

The type and GPU caps are subqueries evaluated inside each claim transaction. `FOR UPDATE
SKIP LOCKED` stops two workers taking the *same* job, but nothing stops them taking two
*different* GPU jobs after both counted zero running — which is exactly the collision the
GPU budget exists to prevent. Claims are milliseconds long, so serialising them with a
Postgres advisory lock costs nothing and makes the counts true.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.services.job_runner import CLAIM_ADVISORY_LOCK_KEY, JobRunner, StepHandlerRegistry


def _runner(dialect: str) -> tuple[JobRunner, MagicMock]:
    db = MagicMock()
    db.scalar.return_value = None
    db.bind.dialect.name = dialect
    return JobRunner(db=db, handlers=StepHandlerRegistry()), db


class ClaimSerializationTests(unittest.TestCase):
    def test_postgres_claim_takes_an_advisory_lock_first(self) -> None:
        runner, db = _runner("postgresql")

        runner.claim_next_job("worker-1")

        self.assertTrue(db.execute.called, "The claim must serialise against other workers")
        statement = str(db.execute.call_args_list[0].args[0]).lower()
        self.assertIn("pg_advisory_xact_lock", statement)

    def test_lock_key_is_stable(self) -> None:
        self.assertIsInstance(CLAIM_ADVISORY_LOCK_KEY, int)
        self.assertEqual(CLAIM_ADVISORY_LOCK_KEY, abs(CLAIM_ADVISORY_LOCK_KEY))

    def test_sqlite_skips_the_lock_instead_of_crashing(self) -> None:
        runner, db = _runner("sqlite")

        runner.claim_next_job("worker-1")

        for call in db.execute.call_args_list:
            self.assertNotIn("pg_advisory", str(call.args[0]).lower())

    def test_an_unknown_bind_does_not_break_claiming(self) -> None:
        db = MagicMock()
        db.scalar.return_value = None
        type(db).bind = property(lambda _self: (_ for _ in ()).throw(RuntimeError("no bind")))
        runner = JobRunner(db=db, handlers=StepHandlerRegistry())

        self.assertIsNone(runner.claim_next_job("worker-1"))


if __name__ == "__main__":
    unittest.main()
