from __future__ import annotations

from datetime import UTC, datetime
import inspect
from types import SimpleNamespace
import unittest
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from src.api.routes.reup_queue import list_reup_queue_items as list_route
from src.services.reup_queue_service import ReupQueueService


def compiled(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


class RecordingDb:
    """Captures every statement the list path runs so no branch can skip a filter."""

    def __init__(self) -> None:
        self.statements: list = []

    def scalars(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(unique=lambda: [])

    def scalar(self, stmt):
        self.statements.append(stmt)
        return 0

    def execute(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(all=lambda: [])


class ReupQueueIntakeFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = RecordingDb()
        self.service = ReupQueueService(self.db)

    def test_capture_session_filter_scopes_to_promoted_candidates(self) -> None:
        self.service.list_items(capture_session_id=uuid4())
        self.assertTrue(self.db.statements, "list_items must run at least one statement")
        for stmt in self.db.statements:
            sql = compiled(stmt)
            self.assertIn("captured_items", sql)
            self.assertIn("promoted_video_candidate_id", sql)
            self.assertIn(
                "IN (SELECT",
                sql,
                "Use a subquery so a candidate referenced twice is not counted twice",
            )

    def test_created_bounds_apply_to_every_statement(self) -> None:
        self.service.list_items(
            created_after=datetime(2026, 7, 1, tzinfo=UTC),
            created_before=datetime(2026, 7, 26, tzinfo=UTC),
        )
        for stmt in self.db.statements:
            sql = compiled(stmt)
            self.assertIn("reup_queue_items.created_at >=", sql)
            self.assertIn("reup_queue_items.created_at <", sql)

    def test_counts_and_gallery_share_the_same_filter(self) -> None:
        """The status tiles read a separate query; a filter applied to only one lies."""
        self.service.list_items(capture_session_id=uuid4())
        self.assertGreaterEqual(
            len(self.db.statements),
            3,
            "list_items should run the page query, the total count, and the status counts",
        )

    def test_no_intake_filter_leaves_statements_untouched(self) -> None:
        self.service.list_items()
        for stmt in self.db.statements:
            self.assertNotIn("captured_items", compiled(stmt))


class ReupQueueRouteContractTests(unittest.TestCase):
    def test_route_exposes_intake_query_params(self) -> None:
        params = inspect.signature(list_route).parameters
        for name in ("capture_session_id", "created_after", "created_before"):
            self.assertIn(name, params, f"/reup-queue/items must accept {name}")

    def test_route_forwards_intake_filters(self) -> None:
        source = inspect.getsource(list_route)
        for name in ("capture_session_id", "created_after", "created_before"):
            self.assertIn(f"{name}={name}", source, f"{name} must reach the service")


if __name__ == "__main__":
    unittest.main()
