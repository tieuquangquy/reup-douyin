from types import SimpleNamespace
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from src.services.operational_metrics import OperationalMetricsService


class _Rows:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class OperationalMetricsServiceTests(unittest.TestCase):
    def test_queue_backlog_exposes_oldest_queue_and_worker_lock_authority(self) -> None:
        db = Mock()
        oldest = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)
        db.scalar.side_effect = [oldest, 2, 1]
        service = OperationalMetricsService(db, workspace_id=uuid4())

        with patch.object(service, "_status_counts", return_value={"QUEUED": 4, "RUNNING": 3, "RETRYABLE": 1}), patch.object(
            service, "_stale_running_authority", return_value=(1, ["stale-job"])
        ):
            summary = service._queue_backlog()

        self.assertEqual(summary.oldest_queued_at, oldest)
        self.assertEqual(summary.running_with_lock, 2)
        self.assertEqual(summary.running_without_lock, 1)
        self.assertEqual(summary.active_worker_count, 1)
        self.assertEqual(summary.stale_running, 1)
        self.assertEqual(summary.stale_running_job_ids, ["stale-job"])

    def test_stale_running_authority_uses_per_job_type_heartbeat_budget(self) -> None:
        db = Mock()
        now = datetime.now(UTC)
        stale_id = uuid4()
        fresh_id = uuid4()
        db.execute.return_value = _Rows(
            [
                (stale_id, "ANALYZE_OCR", now - timedelta(seconds=120)),
                (fresh_id, "ANALYZE_OCR", now - timedelta(seconds=10)),
            ]
        )
        service = OperationalMetricsService(db, workspace_id=uuid4())
        with patch("src.services.operational_metrics.job_type_stale_seconds", return_value=60):
            count, ids = service._stale_running_authority()

        self.assertEqual(count, 1)
        self.assertEqual(ids, [str(stale_id)])

    def test_douyin_fetch_health_aggregates_blocked_parse_and_failed(self) -> None:
        db = Mock()
        db.execute.return_value = _Rows(
            [
                (
                    {
                        "resolved_douyin_account_connection_id": "acc-1",
                        "fetch_observability": {
                            "blocked_reason": "login_required",
                            "stages": {"normalize_payload": {"result": "warning"}},
                        },
                    },
                    "FAILED",
                ),
                (
                    {
                        "resolved_douyin_account_connection_id": "acc-1",
                        "fetch_observability": {
                            "stages": {"normalize_payload": {"result": "ok"}},
                        },
                    },
                    "COMPLETED",
                ),
                (
                    {
                        "resolved_douyin_account_connection_id": "acc-2",
                        "fetch_observability": {
                            "blocked_reason": "challenge_required",
                            "stages": {"normalize_payload": {"result": "failed"}},
                        },
                    },
                    "FAILED",
                ),
            ]
        )
        service = OperationalMetricsService(db, workspace_id=uuid4())

        summary = service._douyin_fetch_health()

        self.assertEqual(summary.window_runs, 3)
        self.assertEqual(summary.blocked_runs, 2)
        self.assertEqual(summary.parse_warning_runs, 2)
        self.assertEqual(summary.failed_runs, 2)
        self.assertEqual(summary.blocked_ratio_percent, 66.67)
        self.assertEqual([(item.reason, item.count) for item in summary.top_blocked_reasons], [("login_required", 1), ("challenge_required", 1)])
        self.assertEqual(summary.by_account[0].douyin_account_connection_id, "acc-1")
        self.assertEqual(summary.by_account[0].runs_total, 2)
        self.assertEqual(summary.by_account[0].blocked_runs, 1)


if __name__ == "__main__":
    unittest.main()
