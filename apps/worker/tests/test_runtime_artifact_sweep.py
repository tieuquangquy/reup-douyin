"""Housekeeping runs on a slow clock, not on every poll.

Reclaiming artifacts scans finished clips and touches the filesystem. Doing that every five
seconds would compete with the very jobs it is meant to protect, so the worker runs it on
its own interval and never lets a housekeeping error interrupt job execution.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class ArtifactSweepTests(unittest.TestCase):
    def _worker(self) -> LocalPollingWorker:
        return LocalPollingWorker(worker_id="local-worker-1", poll_interval_seconds=0)

    def test_first_poll_sweeps(self) -> None:
        worker = self._worker()

        with (
            patch("runtime.get_session_factory", return_value=FakeSessionFactory()),
            patch("runtime.sweep_reclaimable_artifacts", return_value=0) as sweep,
        ):
            worker.maybe_sweep_artifacts(now=1_000.0, interval_seconds=900)

        sweep.assert_called_once()

    def test_a_second_poll_moments_later_does_not_sweep_again(self) -> None:
        worker = self._worker()

        with (
            patch("runtime.get_session_factory", return_value=FakeSessionFactory()),
            patch("runtime.sweep_reclaimable_artifacts", return_value=0) as sweep,
        ):
            worker.maybe_sweep_artifacts(now=1_000.0, interval_seconds=900)
            worker.maybe_sweep_artifacts(now=1_030.0, interval_seconds=900)

        self.assertEqual(sweep.call_count, 1)

    def test_it_sweeps_again_after_the_interval(self) -> None:
        worker = self._worker()

        with (
            patch("runtime.get_session_factory", return_value=FakeSessionFactory()),
            patch("runtime.sweep_reclaimable_artifacts", return_value=0) as sweep,
        ):
            worker.maybe_sweep_artifacts(now=1_000.0, interval_seconds=900)
            worker.maybe_sweep_artifacts(now=2_000.0, interval_seconds=900)

        self.assertEqual(sweep.call_count, 2)

    def test_a_sweep_failure_is_swallowed(self) -> None:
        worker = self._worker()

        with (
            patch("runtime.get_session_factory", return_value=FakeSessionFactory()),
            patch("runtime.sweep_reclaimable_artifacts", side_effect=RuntimeError("db gone")),
        ):
            worker.maybe_sweep_artifacts(now=1_000.0, interval_seconds=900)

    def test_the_poll_loop_calls_it(self) -> None:
        worker = self._worker()
        runner = MagicMock()
        runner.release_stale_running_locks.return_value = 0
        runner.release_orphaned_locks.return_value = 0

        def stop_after_one(_message=None):
            worker.stop()
            return False

        with (
            patch("runtime.get_session_factory", return_value=FakeSessionFactory()),
            patch("runtime.JobRunner", return_value=runner),
            patch.object(worker, "run_once", side_effect=stop_after_one),
            patch.object(worker, "maybe_sweep_artifacts") as sweep,
            patch("runtime.time.sleep"),
        ):
            worker.run_forever()

        sweep.assert_called()


if __name__ == "__main__":
    unittest.main()
