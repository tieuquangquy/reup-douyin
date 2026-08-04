from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

WORKER_SRC = Path(__file__).resolve().parents[1] / "src"
if str(WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(WORKER_SRC))

from runtime import LocalPollingWorker  # noqa: E402


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _SessionFactory:
    def __call__(self):
        return _Session()


class MetricScheduleSweepTests(unittest.TestCase):
    def _worker(self) -> LocalPollingWorker:
        return LocalPollingWorker(worker_id="local-worker-1", poll_interval_seconds=0)

    def test_disabled_scheduler_never_touches_database(self) -> None:
        worker = self._worker()
        with (
            patch(
                "runtime.get_settings",
                return_value=SimpleNamespace(metrics_scheduler_enabled=False),
            ),
            patch("runtime.get_session_factory") as session_factory,
        ):
            worker.maybe_dispatch_metric_schedules(now=1000, interval_seconds=60)
        session_factory.assert_not_called()

    def test_enabled_scheduler_dispatches_once_per_interval(self) -> None:
        worker = self._worker()
        settings = SimpleNamespace(
            metrics_scheduler_enabled=True,
            metrics_scheduler_sweep_interval_seconds=60,
            metrics_scheduler_dispatch_limit=7,
        )
        with (
            patch("runtime.get_settings", return_value=settings),
            patch("runtime.get_session_factory", return_value=_SessionFactory()),
            patch("runtime.PublicationMetricCadenceService") as cadence,
        ):
            cadence.return_value.dispatch_due.return_value = {
                "evaluated_count": 0,
                "enqueued_count": 0,
                "blocked_count": 0,
                "completed_count": 0,
                "job_ids": [],
            }
            worker.maybe_dispatch_metric_schedules(now=1000, interval_seconds=60)
            worker.maybe_dispatch_metric_schedules(now=1030, interval_seconds=60)

        cadence.return_value.dispatch_due.assert_called_once_with(limit=7)

    def test_scheduler_failure_does_not_interrupt_worker(self) -> None:
        worker = self._worker()
        settings = SimpleNamespace(
            metrics_scheduler_enabled=True,
            metrics_scheduler_sweep_interval_seconds=60,
            metrics_scheduler_dispatch_limit=20,
        )
        with (
            patch("runtime.get_settings", return_value=settings),
            patch("runtime.get_session_factory", return_value=_SessionFactory()),
            patch(
                "runtime.PublicationMetricCadenceService",
                side_effect=RuntimeError("database unavailable"),
            ),
        ):
            worker.maybe_dispatch_metric_schedules(now=1000, interval_seconds=60)


if __name__ == "__main__":
    unittest.main()
