"""Unit tests for CloudOCRAnalyzer (sharpen, clean_ocr_data, async mock)."""

from __future__ import annotations

import asyncio
import base64
import os
import unittest
from unittest.mock import AsyncMock, patch

import cv2
import numpy as np

from src.media_pipeline.ocr_filtering.analyze_ocr import (
    NOISE_SINGLE_CHARS,
    CloudOCRAnalyzer,
    RetryableHttpError,
    clean_ocr_data,
    format_timestamp_key,
    original_box_to_quad,
    prepare_recognition_crop,
    preprocess_crop_to_jpeg_b64,
)


class ConcurrencyPromptTests(unittest.TestCase):
    def test_default_semaphore_is_four_without_env(self) -> None:
        """Prompt 2 default: Semaphore(4) when OCR_ASYNC_CONCURRENCY unset."""
        env = {k: v for k, v in os.environ.items() if k != "OCR_ASYNC_CONCURRENCY"}
        with patch.dict(os.environ, env, clear=True):
            analyzer = CloudOCRAnalyzer(endpoint_url="http://example.test/predict")
            self.assertEqual(analyzer.concurrency, 4)

    def test_env_overrides_concurrency_for_local(self) -> None:
        with patch.dict(os.environ, {"OCR_ASYNC_CONCURRENCY": "2"}, clear=False):
            analyzer = CloudOCRAnalyzer(endpoint_url="http://127.0.0.1:8080/predict")
            self.assertEqual(analyzer.concurrency, 2)


class PreprocessTests(unittest.TestCase):
    def test_preprocess_emits_color_jpeg_base64(self) -> None:
        """Long Chinese lines need color/CLAHE JPEG — not BW-only."""
        crop = np.full((40, 80, 3), 120, dtype=np.uint8)
        crop[10:30, 20:60] = (40, 80, 200)  # colored glyph-like region
        b64, jpeg = preprocess_crop_to_jpeg_b64(crop)
        self.assertTrue(isinstance(b64, str) and len(b64) > 20)
        decoded = base64.b64decode(b64)
        self.assertEqual(decoded, jpeg)
        self.assertTrue(jpeg[:2] == b"\xff\xd8")
        arr = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(arr)
        assert arr is not None
        self.assertEqual(arr.ndim, 3)

    def test_preprocess_accepts_already_gray(self) -> None:
        gray = np.full((32, 48), 90, dtype=np.uint8)
        b64, _jpeg = preprocess_crop_to_jpeg_b64(gray)
        self.assertGreater(len(b64), 10)

    def test_prepare_recognition_crop_pads_and_keeps_color(self) -> None:
        frame = np.full((200, 400, 3), 30, dtype=np.uint8)
        frame[80:120, 50:300] = (240, 240, 240)
        crop = prepare_recognition_crop(frame, 50, 80, 300, 120)
        self.assertEqual(crop.ndim, 3)
        # Padded beyond tight box.
        self.assertGreater(crop.shape[0], 40)
        self.assertGreater(crop.shape[1], 250)
        # Tiny crops are upscaled for recognizer.
        tiny = prepare_recognition_crop(frame, 50, 80, 90, 95)
        self.assertGreaterEqual(tiny.shape[0], 48)


class CleanOcrDataTests(unittest.TestCase):
    def test_low_score_dropped(self) -> None:
        self.assertIsNone(clean_ocr_data("你好", 0.69, [0, 0, 100, 0, 100, 40, 0, 40]))

    def test_tiny_box_height_dropped(self) -> None:
        # height = 9
        self.assertIsNone(clean_ocr_data("你好", 0.9, [0, 0, 50, 0, 50, 9, 0, 9]))

    def test_noise_single_char_dropped(self) -> None:
        for ch in ("一", "丨", "丶", "-", ".", ",", "!", "l", "I"):
            self.assertIn(ch, NOISE_SINGLE_CHARS)
            self.assertIsNone(clean_ocr_data(ch, 0.99, [0, 0, 40, 0, 40, 20, 0, 20]))

    def test_special_only_single_dropped(self) -> None:
        self.assertIsNone(clean_ocr_data("@", 0.99, [0, 0, 40, 0, 40, 20, 0, 20]))

    def test_valid_kept(self) -> None:
        box = [10, 20, 110, 20, 110, 50, 10, 50]
        got = clean_ocr_data("减脂餐", 0.85, box)
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got["text"], "减脂餐")
        self.assertEqual(got["box"], box)

    def test_question_mark_garbage_dropped(self) -> None:
        box = [10, 20, 200, 20, 200, 50, 10, 50]
        self.assertIsNone(clean_ocr_data("????", 0.95, box))
        self.assertIsNone(clean_ocr_data("??(?", 0.92, box))
        self.assertIsNone(clean_ocr_data("?4?1502.0?", 0.91, box))
        # Mixed but mostly readable CJK/digits still kept.
        kept = clean_ocr_data("豆腐(南", 0.9, box)
        self.assertIsNotNone(kept)

    def test_original_coords_not_mutated(self) -> None:
        box = [1, 2, 3, 4, 5, 6, 7, 8]
        before = list(box)
        clean_ocr_data("ok文字", 0.9, box)
        self.assertEqual(box, before)


class TimestampAndBoxHelpersTests(unittest.TestCase):
    def test_format_timestamp(self) -> None:
        self.assertEqual(format_timestamp_key(5.5), "00:05.500")
        self.assertEqual(format_timestamp_key(65.0), "01:05.000")

    def test_xyxy_to_quad(self) -> None:
        self.assertEqual(
            original_box_to_quad([10, 20, 100, 60]),
            [10, 20, 100, 20, 100, 60, 10, 60],
        )


class AnalyzeAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_analyze_groups_by_timestamp_keeps_original_box(self) -> None:
        crop = np.full((48, 96, 3), 180, dtype=np.uint8)
        crop[8:40, 10:86] = 30
        items = [
            {
                "timestamp": 5.5,
                "original_box_coords": [100, 200, 400, 260],
                "image_crop": crop,
            },
            {
                "timestamp": 5.5,
                "original_box_coords": [10, 10, 80, 40],
                "image_crop": crop,
            },
        ]
        analyzer = CloudOCRAnalyzer(
            endpoint_url="http://example.test/predict",
            concurrency=4,
            max_retries=2,
        )

        async def fake_post(_session, **_kwargs):  # noqa: ANN001
            content = _kwargs["content"]
            self.assertTrue(content[:2] == b"\xff\xd8")
            return [{"text": "虾仁豆腐", "score": 0.92, "bbox": [[0, 0], [10, 0], [10, 10], [0, 10]]}]

        with patch(
            "src.media_pipeline.ocr_filtering.analyze_ocr.post_predict_jpeg",
            new=AsyncMock(side_effect=fake_post),
        ):
            grouped = await analyzer.analyze(items)

        self.assertIn("00:05.500", grouped)
        self.assertEqual(len(grouped["00:05.500"]), 2)
        first = grouped["00:05.500"][0]
        self.assertEqual(first["text"], "虾仁豆腐")
        # Must be original frame coords as quad — not OCR crop-local bbox.
        self.assertEqual(first["box"], [100, 200, 400, 200, 400, 260, 100, 260])

    async def test_analyze_retries_on_http_503(self) -> None:
        crop = np.full((40, 60, 3), 100, dtype=np.uint8)
        items = [
            {
                "timestamp": 1.0,
                "original_box_coords": [0, 0, 50, 30],
                "image_crop": crop,
            }
        ]
        analyzer = CloudOCRAnalyzer(
            endpoint_url="http://example.test/predict",
            concurrency=4,
            max_retries=2,
            retry_delay_s=0.01,
        )
        calls = {"n": 0}

        async def flaky(_session, **_kwargs):  # noqa: ANN001
            calls["n"] += 1
            if calls["n"] < 3:
                raise RetryableHttpError(503, "boom")
            return [{"text": "OK文字", "score": 0.95, "bbox": [[0, 0], [1, 0], [1, 1], [0, 1]]}]

        with patch(
            "src.media_pipeline.ocr_filtering.analyze_ocr.post_predict_jpeg",
            new=AsyncMock(side_effect=flaky),
        ):
            with patch("src.media_pipeline.ocr_filtering.analyze_ocr.asyncio.sleep", new=AsyncMock()):
                grouped = await analyzer.analyze(items)

        self.assertEqual(calls["n"], 3)
        self.assertEqual(grouped["00:01.000"][0]["text"], "OK文字")

    async def test_low_score_filtered_from_output(self) -> None:
        crop = np.full((40, 60, 3), 100, dtype=np.uint8)
        items = [
            {
                "timestamp": 0.0,
                "original_box_coords": [0, 0, 50, 30],
                "image_crop": crop,
            }
        ]
        analyzer = CloudOCRAnalyzer(endpoint_url="http://example.test/predict")

        async def low_score(_session, **_kwargs):  # noqa: ANN001
            return [{"text": "垃圾", "score": 0.2, "bbox": [[0, 0], [1, 0], [1, 1], [0, 1]]}]

        with patch(
            "src.media_pipeline.ocr_filtering.analyze_ocr.post_predict_jpeg",
            new=AsyncMock(side_effect=low_score),
        ):
            grouped = await analyzer.analyze(items)
        self.assertEqual(grouped, {})


if __name__ == "__main__":
    unittest.main()
