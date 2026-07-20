"""Async TTS preview job — must return before long OmniVoice synthesize finishes."""

from __future__ import annotations

import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from src.tts_pipeline.preview_job import (
    get_tts_preview_job,
    reset_tts_preview_jobs_for_tests,
    start_tts_preview_job,
)


class TtsPreviewJobTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_tts_preview_jobs_for_tests()

    def tearDown(self) -> None:
        reset_tts_preview_jobs_for_tests()

    def test_start_returns_running_before_synthesize_finishes(self) -> None:
        workspace_id = uuid4()
        started = time.time()

        def slow_preview(**_kwargs):  # noqa: ANN003
            time.sleep(0.6)
            return {
                "ok": True,
                "provider": "omnivoice",
                "detail": "Preview ready (8 chars)",
                "mime_type": "audio/wav",
                "duration_seconds": 0.5,
                "audio_base64": "UklGRg==",
                "warnings": [],
                "text": "Xin chào",
            }

        cfg = SimpleNamespace(provider="omnivoice", enabled=True)
        with patch("src.tts_pipeline.preview.preview_tts_speech", side_effect=slow_preview):
            job = start_tts_preview_job(
                workspace_id=workspace_id,
                workspace_tts=cfg,
                text="Xin chào",
            )
            self.assertLess(time.time() - started, 0.4)
            self.assertEqual(job.status, "running")
            self.assertFalse(job.ok)

            with self.assertRaises(RuntimeError):
                start_tts_preview_job(
                    workspace_id=workspace_id,
                    workspace_tts=cfg,
                    text="again",
                    replace_if_running=False,
                )

            deadline = time.time() + 3.0
            final = get_tts_preview_job(workspace_id)
            while final and final.status == "running" and time.time() < deadline:
                time.sleep(0.05)
                final = get_tts_preview_job(workspace_id)
            self.assertIsNotNone(final)
            assert final is not None
            self.assertEqual(final.status, "succeeded")
            self.assertTrue(final.ok)
            self.assertEqual(final.provider, "omnivoice")
            self.assertTrue(final.audio_base64)

    def test_route_source_starts_background_preview(self) -> None:
        source = Path(__file__).resolve().parents[1] / "src" / "api" / "routes" / "operations.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("start_tts_preview_job", text)
        self.assertIn("/tts-ai/preview/status", text)
        self.assertIn("get_tts_preview_job", text)


if __name__ == "__main__":
    unittest.main()
