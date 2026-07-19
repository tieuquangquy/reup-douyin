"""Async OCR fail-fast contracts: Semaphore(3), 120s timeout, tenacity retry."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.media_pipeline.ocr_filtering.async_batch import (
    ASYNC_OCR_CONCURRENCY,
    ASYNC_OCR_TIMEOUT_SECONDS,
    post_ocr_predict,
    process_all_frames,
)


class AsyncOcrHardeningTests(unittest.TestCase):
    def test_semaphore_hardcoded_to_three_for_cloud_run_concurrency_two(self) -> None:
        # Matches Cloud Run --concurrency 2 (+ light scale-out headroom).
        self.assertEqual(ASYNC_OCR_CONCURRENCY, 3)

    def test_fail_fast_timeout_is_one_hundred_twenty_seconds(self) -> None:
        self.assertEqual(ASYNC_OCR_TIMEOUT_SECONDS, 120)

    def test_post_ocr_predict_retries_timeout_then_succeeds(self) -> None:
        async def _run() -> None:
            session = MagicMock()
            ok_response = MagicMock()
            ok_response.status = 200
            ok_response.read = AsyncMock(return_value=b"[]")
            ok_response.json = AsyncMock(return_value=[])
            ok_response.__aenter__ = AsyncMock(return_value=ok_response)
            ok_response.__aexit__ = AsyncMock(return_value=None)

            call_count = {"n": 0}

            def _post(*_a, **_k):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise asyncio.TimeoutError()
                return ok_response

            session.post = MagicMock(side_effect=_post)

            with patch("asyncio.sleep", new_callable=AsyncMock):
                payload = await post_ocr_predict(
                    session,
                    endpoint="https://example.test/predict",
                    filename="frame.jpg",
                    content=b"\xff\xd8\xff\xd9",
                )
            self.assertEqual(payload, [])
            self.assertEqual(call_count["n"], 2)

        asyncio.run(_run())

    def test_process_all_frames_forces_semaphore_three_and_retries_503(self) -> None:
        async def _run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "f0.jpg"
                from PIL import Image

                Image.new("RGB", (100, 200), color=(1, 2, 3)).save(path, format="JPEG")

                fail = MagicMock()
                fail.status = 503
                fail.read = AsyncMock(return_value=b"unavailable")
                fail.__aenter__ = AsyncMock(return_value=fail)
                fail.__aexit__ = AsyncMock(return_value=None)

                ok = MagicMock()
                ok.status = 200
                ok.read = AsyncMock(return_value=b"[]")
                ok.json = AsyncMock(return_value=[])
                ok.__aenter__ = AsyncMock(return_value=ok)
                ok.__aexit__ = AsyncMock(return_value=None)

                session = MagicMock()
                session.post = MagicMock(side_effect=[fail, ok])
                session.__aenter__ = AsyncMock(return_value=session)
                session.__aexit__ = AsyncMock(return_value=None)

                with (
                    patch("aiohttp.ClientSession", return_value=session),
                    patch("aiohttp.TCPConnector", return_value=MagicMock()) as connector,
                    patch("asyncio.sleep", new_callable=AsyncMock),
                ):
                    detections = await process_all_frames(
                        [path],
                        endpoint_url="https://example.test/predict",
                        concurrency=99,  # ignored — hardcap 3
                    )
                self.assertEqual(len(detections), 1)
                self.assertEqual(detections[0].frame_width, 100)
                self.assertEqual(detections[0].frame_height, 200)
                self.assertEqual(session.post.call_count, 2)
                connector.assert_called_with(limit=3)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
