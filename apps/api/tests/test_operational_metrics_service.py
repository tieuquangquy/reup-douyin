from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from uuid import uuid4

from src.services.operational_metrics import OperationalMetricsService


class _Rows:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class OperationalMetricsServiceTests(unittest.TestCase):
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
