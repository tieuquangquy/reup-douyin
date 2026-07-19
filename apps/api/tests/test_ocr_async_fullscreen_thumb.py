"""Async OCR batch + full-frame keep + thumbnail cover wiring."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.media_pipeline.ocr_filtering.async_batch import process_all_frames
from src.media_pipeline.ocr_filtering.pipeline import run_ocr_filtering
from src.media_pipeline.ocr_filtering.providers import MockOcrProvider
from src.media_pipeline.ocr_filtering.types import DetectedTextBox, FrameOcrDetection
from src.media_pipeline.video_renderer.filter_graph import build_single_render_filter
from src.media_pipeline.video_renderer.overlays import OverlaySegment


class FullFrameKeepTests(unittest.TestCase):
    def test_run_ocr_filtering_keeps_top_mid_and_bottom_boxes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame = root / "frame_000001.jpg"
            frame.write_bytes(b"fake")
            provider = MockOcrProvider(
                boxes_by_stem={
                    "frame_000001": [
                        DetectedTextBox(0.1, 0.05, 0.2, 0.04, "TOP", 0.9),
                        DetectedTextBox(0.2, 0.40, 0.5, 0.08, "MID", 0.9),
                        DetectedTextBox(0.1, 0.80, 0.7, 0.1, "BOTTOM", 0.95),
                    ],
                },
                frame_size=(1000, 1000),
            )
            result = run_ocr_filtering(
                [frame],
                ocr_provider=provider,
                frame_time_ms=[0],
                crop_band=False,
                concurrency=1,
                probe_stride=1,
            )
            texts = [b["text"] for b in result.to_dict()["frames"][0]["boxes"]]
            self.assertEqual(texts, ["TOP", "MID", "BOTTOM"])


class AsyncBatchContractTests(unittest.TestCase):
    def test_process_all_frames_uses_semaphore_and_gather(self) -> None:
        async def _run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = []
                from PIL import Image

                for i in range(3):
                    p = root / f"f{i}.jpg"
                    Image.new("RGB", (120, 160), color=(i + 1, 2, 3)).save(p, format="JPEG")
                    paths.append(p)

                fake_session = MagicMock()
                fake_response = MagicMock()
                fake_response.status = 200
                fake_response.read = AsyncMock(return_value=b"[]")
                fake_response.json = AsyncMock(return_value=[])
                fake_response.__aenter__ = AsyncMock(return_value=fake_response)
                fake_response.__aexit__ = AsyncMock(return_value=None)
                fake_session.post = MagicMock(return_value=fake_response)
                fake_session.__aenter__ = AsyncMock(return_value=fake_session)
                fake_session.__aexit__ = AsyncMock(return_value=None)

                with patch(
                    "aiohttp.ClientSession", return_value=fake_session
                ), patch(
                    "aiohttp.TCPConnector", return_value=MagicMock()
                ):
                    detections = await process_all_frames(
                        paths,
                        endpoint_url="https://example.test/predict",
                        timeout_seconds=30,
                        concurrency=10,
                    )
                self.assertEqual(len(detections), 3)
                self.assertEqual(fake_session.post.call_count, 3)

        asyncio.run(_run())


class AttachedPicFilterTests(unittest.TestCase):
    def test_delogo_filter_builds_for_thumbnail_overlays(self) -> None:
        overlays = [OverlaySegment(0, 500, 0.2, 0.4, 0.5, 0.08, "Title VI", kind="title")]
        vf = build_single_render_filter(
            overlays,
            fontfile=Path("C:/Windows/Fonts/arial.ttf"),
            frame_width=1080,
            frame_height=1920,
            hold_ms=0,
            anti_seed=1,
        )
        self.assertIn("delogo=", vf)
        self.assertIn("drawtext=", vf)


if __name__ == "__main__":
    unittest.main()
