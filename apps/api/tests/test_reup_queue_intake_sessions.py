from __future__ import annotations

import inspect
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from src.api.routes import reup_queue as reup_queue_routes
from src.services.reup_queue_service import ReupQueueIntakeSession, ReupQueueService


class ReupQueueIntakeSessionsContractTests(unittest.TestCase):
    def test_service_exposes_intake_sessions_helper(self) -> None:
        self.assertTrue(
            hasattr(ReupQueueService, "list_intake_sessions"),
            "The queue must know which Capture Inbox batches actually have items waiting",
        )

    def test_route_exposes_intake_sessions_endpoint(self) -> None:
        source = inspect.getsource(reup_queue_routes)
        self.assertIn(
            "/reup-queue/intake-sessions",
            source,
            "Operators need a dedicated endpoint so the picker never offers empty batches",
        )
        self.assertIn("list_intake_sessions", source)


class ReupQueueIntakeSessionsUnitTests(unittest.TestCase):
    def test_intake_session_exposes_queued_count_as_promoted_for_labels(self) -> None:
        """Shared option labels read ``promoted_item_count``; on this surface that must be
        the number of clips still in the queue, not the Review Board promote total.
        """
        session = SimpleNamespace(
            id=uuid4(),
            created_at=datetime(2026, 7, 26, tzinfo=UTC),
            promoted_item_count=20,
            normalized_profile_identifier="abc",
            submitted_profile_url=None,
            metadata_json={},
        )
        wrapped = ReupQueueIntakeSession(session=session, queued_item_count=5)
        self.assertEqual(wrapped.promoted_item_count, 5)
        self.assertEqual(wrapped.queued_item_count, 5)
        self.assertEqual(wrapped.id, session.id)

    def test_list_intake_sessions_maps_sql_rows_newest_first(self) -> None:
        older = SimpleNamespace(
            id=uuid4(),
            created_at=datetime(2026, 7, 13, tzinfo=UTC),
            promoted_item_count=1008,
            normalized_profile_identifier="old",
            submitted_profile_url=None,
            metadata_json={},
        )
        newer = SimpleNamespace(
            id=uuid4(),
            created_at=datetime(2026, 7, 26, tzinfo=UTC),
            promoted_item_count=20,
            normalized_profile_identifier="new",
            submitted_profile_url=None,
            metadata_json={},
        )

        class FakeResult:
            def all(self):
                # SQL already orders newest first; the service must preserve that order.
                return [(newer, 5), (older, 40)]

        class FakeDb:
            def execute(self, _stmt):
                return FakeResult()

        sessions = ReupQueueService(FakeDb()).list_intake_sessions(limit=10)
        self.assertEqual([entry.id for entry in sessions], [newer.id, older.id])
        self.assertEqual(sessions[0].promoted_item_count, 5)
        self.assertEqual(sessions[1].promoted_item_count, 40)


if __name__ == "__main__":
    unittest.main()
