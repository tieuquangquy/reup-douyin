from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from src.enums import CrawlSessionStatus
from src.services.intake_run_history_service import IntakeRunHistoryError, IntakeRunHistoryService


class IntakeRunHistoryServiceTests(unittest.TestCase):
    def test_get_run_raises_not_found(self) -> None:
        db = Mock()
        db.scalar.return_value = None
        service = IntakeRunHistoryService(db)

        with self.assertRaisesRegex(IntakeRunHistoryError, "not found"):
            service.get_run(uuid4())

    def test_troubleshooting_non_failed_returns_no_failure(self) -> None:
        service = IntakeRunHistoryService(Mock())
        run = SimpleNamespace(
            status=CrawlSessionStatus.COMPLETED,
            error_code=None,
            error_message=None,
            metadata_json={},
        )

        summary = service.troubleshooting_for(run)

        self.assertEqual(summary.category, "NO_FAILURE")
        self.assertEqual(summary.severity, "info")

    def test_troubleshooting_account_unusable(self) -> None:
        service = IntakeRunHistoryService(Mock())
        run = SimpleNamespace(
            status=CrawlSessionStatus.FAILED,
            error_code="douyin_account_unavailable",
            error_message="selected_account_unusable",
            metadata_json={},
        )

        summary = service.troubleshooting_for(run)

        self.assertEqual(summary.category, "ACCOUNT_UNUSABLE")
        self.assertEqual(summary.severity, "high")
        self.assertGreaterEqual(len(summary.recommended_actions), 1)

    def test_troubleshooting_fetch_blocked_auth_from_observability(self) -> None:
        service = IntakeRunHistoryService(Mock())
        run = SimpleNamespace(
            status=CrawlSessionStatus.FAILED,
            error_code="adapter_fetch_failed",
            error_message="fetch blocked",
            metadata_json={
                "fetch_observability": {
                    "blocked_reason": "login_required",
                    "stages": {"normalize_payload": {"result": "failed"}},
                }
            },
        )

        summary = service.troubleshooting_for(run)

        self.assertEqual(summary.category, "FETCH_BLOCKED_AUTH")
        self.assertEqual(summary.severity, "high")

    def test_compare_runs_returns_expected_deltas(self) -> None:
        service = IntakeRunHistoryService(Mock())
        left = SimpleNamespace(
            status=CrawlSessionStatus.COMPLETED,
            started_at=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
            finished_at=datetime(2026, 4, 22, 10, 2, tzinfo=UTC),
            videos_discovered_count=5,
            videos_created_count=3,
            videos_updated_count=1,
            error_code=None,
            metadata_json={"candidates_total_count": 4, "candidates_matched_count": 2},
        )
        right = SimpleNamespace(
            status=CrawlSessionStatus.FAILED,
            started_at=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
            finished_at=datetime(2026, 4, 22, 10, 4, tzinfo=UTC),
            videos_discovered_count=7,
            videos_created_count=5,
            videos_updated_count=2,
            error_code="timeout",
            metadata_json={"candidates_total_count": 6, "candidates_matched_count": 1},
        )

        with patch.object(service, "get_run", side_effect=[left, right]):
            _, _, delta = service.compare_runs(left_run_id=uuid4(), right_run_id=uuid4())

        self.assertTrue(delta["status_changed"])
        self.assertEqual(delta["duration_seconds_delta"], 120)
        self.assertEqual(delta["videos_discovered_delta"], 2)
        self.assertEqual(delta["candidates_total_delta"], 2)
        self.assertEqual(delta["candidates_matched_delta"], -1)
        self.assertTrue(delta["error_code_changed"])

    def test_list_runs_resolves_default_workspace(self) -> None:
        workspace_id = uuid4()
        db = Mock()
        db.scalars.return_value = []
        service = IntakeRunHistoryService(db)

        with patch("src.services.intake_run_history_service.ensure_default_workspace", return_value=SimpleNamespace(id=workspace_id)):
            service.list_runs(workspace_id=None, limit=12)

        db.scalars.assert_called_once()


if __name__ == "__main__":
    unittest.main()
