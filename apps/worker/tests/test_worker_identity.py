"""Each worker process needs its own id.

Orphan/crash recovery requeues jobs by ``locked_by``, so two processes sharing an
id would steal each other's in-flight jobs (duplicate downloads, lost progress).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WORKER_SRC = Path(__file__).resolve().parents[1] / "src"
if str(WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(WORKER_SRC))

from main import resolve_worker_id  # noqa: E402


class WorkerIdentityTests(unittest.TestCase):
    def test_explicit_worker_id_is_respected(self) -> None:
        with patch.dict(os.environ, {"WORKER_ID": "render-worker"}, clear=False):
            self.assertEqual(resolve_worker_id(), "render-worker")

    def test_default_worker_id_is_unique_per_process(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "WORKER_ID"}
        with patch.dict(os.environ, env, clear=True):
            worker_id = resolve_worker_id()

        self.assertIn(str(os.getpid()), worker_id, "Default id must be process-scoped")
        self.assertTrue(worker_id.startswith("local-worker-"))


if __name__ == "__main__":
    unittest.main()
