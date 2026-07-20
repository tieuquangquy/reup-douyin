"""OCR batch heartbeat: map frame completions into phase2 progress 26–54."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.media_pipeline.ocr_filtering.async_batch import (
    ocr_frame_progress_percent,
    process_all_frames,
)


class OcrFrameProgressTests(unittest.TestCase):
    def test_progress_maps_completed_frames_into_26_to_54(self) -> None:
        self.assertEqual(ocr_frame_progress_percent(0, 10), 26)
        self.assertEqual(ocr_frame_progress_percent(5, 10), 40)
        self.assertEqual(ocr_frame_progress_percent(10, 10), 54)
        self.assertEqual(ocr_frame_progress_percent(1, 1), 54)
        self.assertEqual(ocr_frame_progress_percent(0, 0), 26)

    def test_process_all_frames_reports_each_completion(self) -> None:
        async def _run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                paths = []
                from PIL import Image

                for i in range(3):
                    path = Path(tmp) / f"f{i}.jpg"
                    Image.new("RGB", (40, 60), color=(i, 2, 3)).save(path, format="JPEG")
                    paths.append(path)

                ok = MagicMock()
                ok.status = 200
                ok.read = AsyncMock(return_value=b"[]")
                ok.json = AsyncMock(return_value=[])
                ok.__aenter__ = AsyncMock(return_value=ok)
                ok.__aexit__ = AsyncMock(return_value=None)

                session = MagicMock()
                session.post = MagicMock(return_value=ok)
                session.__aenter__ = AsyncMock(return_value=session)
                session.__aexit__ = AsyncMock(return_value=None)

                seen: list[tuple[int, int]] = []

                def _on_frame_done(completed: int, total: int) -> None:
                    seen.append((completed, total))

                with (
                    patch("aiohttp.ClientSession", return_value=session),
                    patch("aiohttp.TCPConnector", return_value=MagicMock()),
                ):
                    detections = await process_all_frames(
                        paths,
                        endpoint_url="https://example.test/predict",
                        on_frame_done=_on_frame_done,
                    )

                self.assertEqual(len(detections), 3)
                self.assertEqual(len(seen), 3)
                self.assertEqual([c for c, _ in seen], [1, 2, 3])
                self.assertTrue(all(t == 3 for _, t in seen))

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
