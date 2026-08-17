from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

WORKER_SRC = Path(__file__).resolve().parents[1] / "src"
if str(WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(WORKER_SRC))

from instance_lock import WorkerInstanceLockError, worker_instance_lock  # noqa: E402


class WorkerInstanceLockTests(unittest.TestCase):
    def test_rejects_duplicate_process_for_same_stable_worker_id(self) -> None:
        with TemporaryDirectory() as tmp:
            lock_dir = Path(tmp)
            with worker_instance_lock("local-worker-1", lock_dir=lock_dir):
                with self.assertRaises(WorkerInstanceLockError):
                    with worker_instance_lock("local-worker-1", lock_dir=lock_dir):
                        self.fail("duplicate worker identity acquired the lock")

    def test_allows_different_worker_ids(self) -> None:
        with TemporaryDirectory() as tmp:
            lock_dir = Path(tmp)
            with worker_instance_lock("local-worker-1", lock_dir=lock_dir):
                with worker_instance_lock("local-worker-2", lock_dir=lock_dir):
                    self.assertTrue((lock_dir / "local-worker-2.lock").is_file())


if __name__ == "__main__":
    unittest.main()
