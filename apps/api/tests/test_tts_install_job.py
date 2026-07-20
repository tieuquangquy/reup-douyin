"""Async TTS install job registry."""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from src.tts_pipeline.install_job import (
    get_tts_install_job,
    reset_tts_install_jobs_for_tests,
    start_tts_install_job,
)
from src.tts_pipeline.install_runner import TtsInstallResult, build_tts_install_plan


class TtsInstallJobTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_tts_install_jobs_for_tests()

    def tearDown(self) -> None:
        reset_tts_install_jobs_for_tests()

    def test_start_returns_running_and_rejects_duplicate(self) -> None:
        plan = build_tts_install_plan(package="edge-tts")
        workspace_id = uuid4()
        started = time.time()

        def fake_run(plan_arg, timeout_seconds=300.0, runner=None):
            time.sleep(0.5)
            return TtsInstallResult(
                ok=True,
                detail="Package installed into the API/worker Python environment.",
                command=plan_arg.display_command,
                log_tail="Successfully installed edge-tts",
            )

        with patch("src.tts_pipeline.install_job.run_tts_install", side_effect=fake_run):
            job = start_tts_install_job(
                workspace_id=workspace_id,
                plan=plan,
                package_name="edge-tts",
                provider="edge",
                profile_id=None,
                timeout_seconds=60,
            )
            # Must return before the fake pip sleep finishes.
            self.assertLess(time.time() - started, 1.0)
            self.assertEqual(job.status, "running")
            self.assertEqual(job.command, "pip install edge-tts")

            with self.assertRaises(RuntimeError):
                start_tts_install_job(
                    workspace_id=workspace_id,
                    plan=plan,
                    package_name="edge-tts",
                    provider="edge",
                    profile_id=None,
                    timeout_seconds=60,
                )

            still = get_tts_install_job(workspace_id)
            self.assertIsNotNone(still)
            assert still is not None
            self.assertEqual(still.status, "running")

    def test_route_source_starts_background_job(self) -> None:
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "src" / "api" / "routes" / "operations.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("start_tts_install_job", text)
        self.assertIn("/tts-ai/install/status", text)
        self.assertIn("get_tts_install_job", text)


if __name__ == "__main__":
    unittest.main()
