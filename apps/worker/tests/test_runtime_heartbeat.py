"""A running job must keep its lock warm while a long step executes.

Render and OCR run for tens of minutes. Without a heartbeat their lock ages from the claim
timestamp, so the stale sweeper eventually requeues healthy work and the same clip renders
forever without ever finishing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

WORKER_SRC = Path(__file__).resolve().parents[1] / "src"
if str(WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(WORKER_SRC))

from runtime import LocalPollingWorker  # noqa: E402


class FakeSession:
    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *_exc) -> bool:
        return False


class FakeSessionFactory:
    def __call__(self) -> FakeSession:
        return FakeSession()


class RuntimeHeartbeatTests(unittest.TestCase):
    def test_run_once_wraps_execution_in_a_heartbeat(self) -> None:
        worker = LocalPollingWorker(worker_id="local-worker-1", poll_interval_seconds=0)
        job = MagicMock(id=uuid4())
        runner = MagicMock()
        runner.claim_next_job.return_value = job
        order: list[str] = []
        runner.run_job.side_effect = lambda _job_id: order.append("run")

        heartbeat = MagicMock()
        heartbeat.__enter__ = lambda _self: order.append("start") or heartbeat
        heartbeat.__exit__ = lambda *_args: order.append("stop")

        with (
            patch("runtime.get_session_factory", return_value=FakeSessionFactory()),
            patch("runtime.JobRunner", return_value=runner),
            patch("runtime.JobHeartbeat", return_value=heartbeat) as factory,
        ):
            self.assertTrue(worker.run_once())

        factory.assert_called_once()
        kwargs = factory.call_args.kwargs
        self.assertEqual(kwargs["job_id"], job.id)
        self.assertEqual(kwargs["worker_id"], "local-worker-1")
        self.assertEqual(order, ["start", "run", "stop"], "The beat must cover the whole step")

    def test_no_heartbeat_when_there_is_nothing_to_run(self) -> None:
        worker = LocalPollingWorker(worker_id="local-worker-1", poll_interval_seconds=0)
        runner = MagicMock()
        runner.claim_next_job.return_value = None

        with (
            patch("runtime.get_session_factory", return_value=FakeSessionFactory()),
            patch("runtime.JobRunner", return_value=runner),
            patch("runtime.JobHeartbeat") as factory,
        ):
            self.assertFalse(worker.run_once())

        factory.assert_not_called()

    def test_heartbeat_stops_even_when_the_step_raises(self) -> None:
        worker = LocalPollingWorker(worker_id="local-worker-1", poll_interval_seconds=0)
        runner = MagicMock()
        runner.claim_next_job.return_value = MagicMock(id=uuid4())
        runner.run_job.side_effect = RuntimeError("ffmpeg exploded")
        stopped: list[bool] = []

        heartbeat = MagicMock()
        heartbeat.__enter__ = lambda _self: heartbeat
        heartbeat.__exit__ = lambda *_args: stopped.append(True)

        with (
            patch("runtime.get_session_factory", return_value=FakeSessionFactory()),
            patch("runtime.JobRunner", return_value=runner),
            patch("runtime.JobHeartbeat", return_value=heartbeat),
        ):
            with self.assertRaises(RuntimeError):
                worker.run_once()

        self.assertEqual(stopped, [True], "A dead step must not leave a beating heart behind")


if __name__ == "__main__":
    unittest.main()
