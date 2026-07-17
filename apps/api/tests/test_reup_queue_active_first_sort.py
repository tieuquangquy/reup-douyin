from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.enums import JobStatus, ReupQueueStatus
from src.services.reup_queue_list_sort import active_first_list_rank, normalize_reup_queue_sort
from src.services.reup_queue_service import ReupQueueService


class ReupQueueActiveFirstSortTests(unittest.TestCase):
    def test_normalize_accepts_web_and_api_tokens(self) -> None:
        self.assertEqual(normalize_reup_queue_sort("active-first"), "active_first")
        self.assertEqual(normalize_reup_queue_sort("active_first"), "active_first")
        self.assertEqual(normalize_reup_queue_sort(None), "active_first")
        self.assertEqual(normalize_reup_queue_sort("newest"), "newest")

    def test_rank_pins_running_ahead_of_confirm_ready_and_idle(self) -> None:
        running = active_first_list_rank(
            queue_status=ReupQueueStatus.WAITING_FOR_MEDIA,
            held_at=False,
            job_status=JobStatus.RUNNING,
            blocked=False,
        )
        queued = active_first_list_rank(
            queue_status=ReupQueueStatus.WAITING_FOR_MEDIA,
            held_at=False,
            job_status=JobStatus.QUEUED,
            blocked=False,
        )
        paused = active_first_list_rank(
            queue_status=ReupQueueStatus.WAITING_FOR_MEDIA,
            held_at=True,
            job_status=JobStatus.CANCELLED,
            blocked=False,
        )
        confirm = active_first_list_rank(
            queue_status=ReupQueueStatus.WAITING_FOR_MEDIA,
            held_at=False,
            job_status=JobStatus.COMPLETED,
            blocked=False,
        )
        idle = active_first_list_rank(
            queue_status=ReupQueueStatus.WAITING_FOR_MEDIA,
            held_at=False,
            job_status=None,
            blocked=False,
        )
        self.assertLess(running, queued)
        self.assertLess(queued, paused)
        self.assertLess(paused, confirm)
        self.assertEqual(confirm, idle)

    def test_list_items_active_first_orders_via_job_join(self) -> None:
        db = MagicMock()
        db.scalars.return_value.unique.return_value = []
        db.scalar.return_value = 0
        db.execute.return_value.all.return_value = []

        ReupQueueService(db).list_items(sort="active_first", limit=25, offset=0)

        stmt = db.scalars.call_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()
        self.assertIn("jobs", compiled)
        self.assertIn("case", compiled)
        self.assertIn("progress_percent", compiled)


if __name__ == "__main__":
    unittest.main()
