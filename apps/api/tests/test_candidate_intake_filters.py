from __future__ import annotations

from datetime import UTC, datetime
import inspect
from types import SimpleNamespace
import unittest
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from src.api.routes.candidates import list_candidates as list_candidates_route
from src.models.review import VideoCandidate
from src.services.candidate_service import CandidateEvaluationService


def compiled(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


class FakeCountDb:
    """Minimal stand-in for a Session: the count paths only scalar()/execute()."""

    def scalar(self, _stmt):
        return 0

    def execute(self, _stmt):
        return SimpleNamespace(all=lambda: [])


class CandidateIntakeFilterSqlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CandidateEvaluationService(FakeCountDb())
        self.base = select(func.count()).select_from(VideoCandidate)

    def test_capture_session_filter_scopes_to_promoted_candidates(self) -> None:
        sql = compiled(
            self.service._apply_candidate_list_filters(
                self.base,
                capture_session_id=uuid4(),
            )
        )
        self.assertIn("captured_items", sql)
        self.assertIn("promoted_video_candidate_id", sql)
        self.assertIn("capture_session_id", sql)

    def test_capture_session_filter_does_not_join_and_duplicate_rows(self) -> None:
        sql = compiled(
            self.service._apply_candidate_list_filters(
                self.base,
                capture_session_id=uuid4(),
            )
        )
        self.assertIn(
            "IN (SELECT",
            sql,
            "The intake filter must use a subquery so one candidate is never counted twice",
        )

    def test_created_bounds_filter_candidate_creation_time(self) -> None:
        sql = compiled(
            self.service._apply_candidate_list_filters(
                self.base,
                created_after=datetime(2026, 7, 1, tzinfo=UTC),
                created_before=datetime(2026, 7, 26, tzinfo=UTC),
            )
        )
        self.assertIn("video_candidates.created_at >=", sql)
        self.assertIn("video_candidates.created_at <", sql)

    def test_no_intake_filter_leaves_statement_untouched(self) -> None:
        sql = compiled(self.service._apply_candidate_list_filters(self.base))
        self.assertNotIn("captured_items", sql)
        self.assertNotIn("created_at", sql)


class CandidateCountForwardingTests(unittest.TestCase):
    """The tiles and the gallery must agree: every count path takes the same filters."""

    def setUp(self) -> None:
        self.service = CandidateEvaluationService(FakeCountDb())
        self.seen: list[dict] = []
        original = self.service._apply_candidate_list_filters

        def spy(stmt, **kwargs):
            self.seen.append(kwargs)
            return original(stmt, **kwargs)

        self.service._apply_candidate_list_filters = spy  # type: ignore[method-assign]
        self.session_id = uuid4()
        self.after = datetime(2026, 7, 1, tzinfo=UTC)
        self.before = datetime(2026, 7, 26, tzinfo=UTC)

    def test_count_candidates_forwards_intake_filters(self) -> None:
        self.service.count_candidates(
            capture_session_id=self.session_id,
            created_after=self.after,
            created_before=self.before,
        )
        self.assertEqual(self.seen[-1]["capture_session_id"], self.session_id)
        self.assertEqual(self.seen[-1]["created_after"], self.after)
        self.assertEqual(self.seen[-1]["created_before"], self.before)

    def test_status_counts_forward_intake_filters(self) -> None:
        self.service.count_candidates_by_status(
            capture_session_id=self.session_id,
            created_after=self.after,
            created_before=self.before,
        )
        self.assertEqual(self.seen[-1]["capture_session_id"], self.session_id)
        self.assertEqual(self.seen[-1]["created_after"], self.after)
        self.assertEqual(self.seen[-1]["created_before"], self.before)


class CandidateRouteContractTests(unittest.TestCase):
    def test_route_exposes_intake_query_params(self) -> None:
        params = inspect.signature(list_candidates_route).parameters
        for name in ("capture_session_id", "created_after", "created_before"):
            self.assertIn(name, params, f"/candidates must accept {name}")

    def test_route_forwards_intake_filters_to_every_count_path(self) -> None:
        source = inspect.getsource(list_candidates_route)
        for call in (
            "service.count_candidates(",
            "service.count_candidates_by_status(",
            "service.list_candidates(",
        ):
            start = source.index(call)
            block = source[start : start + 400]
            self.assertIn(
                "capture_session_id=capture_session_id",
                block,
                f"{call} must receive the intake filter or the tile counts will disagree",
            )
            self.assertIn("created_after=created_after", block)
            self.assertIn("created_before=created_before", block)


if __name__ == "__main__":
    unittest.main()
