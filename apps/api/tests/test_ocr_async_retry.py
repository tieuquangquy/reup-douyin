"""Async OCR fail-fast contracts: Semaphore via OCR_ASYNC_CONCURRENCY, 300s timeout."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.media_pipeline.ocr_filtering.async_batch import (
    ASYNC_OCR_CONCURRENCY,
    ASYNC_OCR_TIMEOUT_SECONDS,
    post_ocr_predict,
    process_all_frames,
    resolve_async_ocr_concurrency,
)


class AsyncOcrHardeningTests(unittest.TestCase):
    def test_default_client_concurrency_matches_cloud_run(self) -> None:
        # Per-instance Cloud Run --concurrency 2; client default must not exceed that
        # without explicit scale-out (else 429 Rate exceeded).
        self.assertEqual(ASYNC_OCR_CONCURRENCY, 2)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OCR_ASYNC_CONCURRENCY", None)
            with patch(
                "src.media_pipeline.ocr_filtering.async_batch._ensure_ocr_async_env_loaded",
                lambda: None,
            ):
                self.assertEqual(resolve_async_ocr_concurrency(), 2)

    def test_env_overrides_client_concurrency(self) -> None:
        with patch.dict(os.environ, {"OCR_ASYNC_CONCURRENCY": "2"}, clear=False):
            self.assertEqual(resolve_async_ocr_concurrency(), 2)

    def test_dotenv_file_sets_concurrency_when_os_environ_unset(self) -> None:
        """Worker Settings loads .env into pydantic only — OCR_ASYNC must still apply."""
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("OCR_ASYNC_CONCURRENCY=2\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("OCR_ASYNC_CONCURRENCY", None)
                with patch(
                    "src.media_pipeline.ocr_filtering.async_batch._ocr_dotenv_candidates",
                    return_value=[env_path],
                ):
                    self.assertEqual(resolve_async_ocr_concurrency(), 2)

    def test_post_ocr_predict_retries_429_then_succeeds(self) -> None:
        async def _run() -> None:
            session = MagicMock()
            rate = MagicMock()
            rate.status = 429
            rate.read = AsyncMock(return_value=b"Rate exceeded.")
            rate.__aenter__ = AsyncMock(return_value=rate)
            rate.__aexit__ = AsyncMock(return_value=None)

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
                    return rate
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

    def test_client_timeout_matches_cloud_run_timeout_300s(self) -> None:
        self.assertEqual(ASYNC_OCR_TIMEOUT_SECONDS, 300)

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

    def test_process_all_frames_uses_resolved_semaphore_limit(self) -> None:
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
                    patch.dict(os.environ, {"OCR_ASYNC_CONCURRENCY": "8"}, clear=False),
                ):
                    detections = await process_all_frames(
                        [path],
                        endpoint_url="https://example.test/predict",
                    )
                self.assertEqual(len(detections), 1)
                self.assertEqual(detections[0].frame_width, 100)
                self.assertEqual(detections[0].frame_height, 200)
                self.assertEqual(session.post.call_count, 2)
                connector.assert_called_with(limit=8)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
