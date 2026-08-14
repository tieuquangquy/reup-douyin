"""A crashed run_once must release the job lock immediately.

Without this the job stays RUNNING until the stale-lock sweeper kicks in minutes
later, and with a download concurrency slot of 1 the whole auto queue waits.
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
    """Mimics sessionmaker: callable, and not itself a context manager."""

    def __call__(self) -> FakeSession:
        return FakeSession()


class RuntimeCrashReleaseTests(unittest.TestCase):
    def test_loop_reclaims_stale_locks_with_a_real_session_factory(self) -> None:
        worker = LocalPollingWorker(worker_id="local-worker-1", poll_interval_seconds=0)
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
            patch("runtime.time.sleep"),
        ):
            worker.run_forever()

        self.assertGreaterEqual(
            runner.release_stale_running_locks.call_count,
            2,
            "Stale reclaim must run at startup and inside the poll loop",
        )

    def test_run_once_crash_releases_worker_locks(self) -> None:
        worker = LocalPollingWorker(worker_id="local-worker-1", poll_interval_seconds=0)
        runner = MagicMock()
        runner.release_stale_running_locks.return_value = 0
        runner.release_orphaned_locks.return_value = 1
        runner.release_failed_execution_locks.return_value = 1

        releases_before_crash: list[int] = []

        def crash(_message=None):
            releases_before_crash.append(
                runner.release_failed_execution_locks.call_count
            )
            worker.stop()
            raise RuntimeError("register_assets exploded")

        with (
            patch("runtime.get_session_factory"),
            patch("runtime.JobRunner", return_value=runner),
            patch.object(worker, "run_once", side_effect=crash),
            patch("runtime.time.sleep"),
        ):
            worker.run_forever()

        runner.release_failed_execution_locks.assert_called_once_with(
            "local-worker-1",
            error_type="RuntimeError",
        )
        self.assertGreater(
            runner.release_failed_execution_locks.call_count,
            releases_before_crash[0],
            "The crashed job must be requeued right away, not left RUNNING",
        )


if __name__ == "__main__":
    unittest.main()
