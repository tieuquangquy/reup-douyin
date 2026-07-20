"""Async TTS preview cancel — unlocks workspace so a new Preview can start."""

from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from src.tts_pipeline.preview_job import (
    cancel_tts_preview_job,
    get_tts_preview_job,
    reset_tts_preview_jobs_for_tests,
    start_tts_preview_job,
)


class TtsPreviewCancelTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_tts_preview_jobs_for_tests()

    def tearDown(self) -> None:
        reset_tts_preview_jobs_for_tests()

    def test_cancel_unlocks_workspace_for_new_preview(self) -> None:
        workspace_id = uuid4()
        gate = threading.Event()

        def slow_preview(**_kwargs):  # noqa: ANN003
            gate.wait(timeout=5.0)
            time.sleep(0.05)
            return {
                "ok": True,
                "provider": "omnivoice",
                "detail": "should be ignored after cancel",
                "mime_type": "audio/wav",
                "duration_seconds": 0.5,
                "audio_base64": "UklGRg==",
                "warnings": [],
                "text": "Xin chào",
            }

        cfg = SimpleNamespace(provider="omnivoice", enabled=True)
        with patch("src.tts_pipeline.preview.preview_tts_speech", side_effect=slow_preview):
            first = start_tts_preview_job(
                workspace_id=workspace_id,
                workspace_tts=cfg,
                text="Xin chào",
            )
            self.assertEqual(first.status, "running")

            cancelled = cancel_tts_preview_job(workspace_id)
            self.assertIsNotNone(cancelled)
            assert cancelled is not None
            self.assertEqual(cancelled.status, "cancelled")
            self.assertFalse(cancelled.ok)

            second = start_tts_preview_job(
                workspace_id=workspace_id,
                workspace_tts=cfg,
                text="Lần hai",
            )
            self.assertEqual(second.status, "running")
            gate.set()

            deadline = time.time() + 2.0
            final = get_tts_preview_job(workspace_id)
            while final and final.status == "running" and time.time() < deadline:
                time.sleep(0.05)
                final = get_tts_preview_job(workspace_id)
            self.assertIsNotNone(final)
            assert final is not None
            self.assertIn(final.status, {"succeeded", "running", "failed"})
            self.assertNotEqual(final.status, "cancelled")

    def test_start_replaces_running_preview_by_default(self) -> None:
        workspace_id = uuid4()
        gate = threading.Event()

        def slow_preview(**_kwargs):  # noqa: ANN003
            gate.wait(timeout=5.0)
            return {
                "ok": True,
                "provider": "omnivoice",
                "detail": "ok",
                "mime_type": "audio/wav",
                "duration_seconds": 0.2,
                "audio_base64": "UklGRg==",
                "warnings": [],
                "text": "hi",
            }

        cfg = SimpleNamespace(provider="omnivoice", enabled=True)
        with patch("src.tts_pipeline.preview.preview_tts_speech", side_effect=slow_preview):
            first = start_tts_preview_job(
                workspace_id=workspace_id,
                workspace_tts=cfg,
                text="one",
            )
            self.assertEqual(first.status, "running")
            # Clicking Preview again must not raise — replaces the stuck/running job.
            second = start_tts_preview_job(
                workspace_id=workspace_id,
                workspace_tts=cfg,
                text="two",
            )
            self.assertEqual(second.status, "running")
            self.assertEqual(second.text, "two")
            gate.set()

    def test_route_exposes_cancel(self) -> None:
        source = Path(__file__).resolve().parents[1] / "src" / "api" / "routes" / "operations.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("cancel_tts_preview_job", text)
        self.assertIn("/tts-ai/preview/cancel", text)


if __name__ == "__main__":
    unittest.main()
