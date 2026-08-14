"""OCR preprocess: max edge 1920 + contrast/sharpen before JPEG upload."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.media_pipeline.ocr_filtering.async_batch import (
    ASYNC_OCR_CONCURRENCY,
    ASYNC_OCR_JPEG_QUALITY,
    ASYNC_OCR_MAX_EDGE_PX,
    ASYNC_OCR_TIMEOUT_SECONDS,
    enhance_ocr_frame_bgr,
    prepare_ocr_jpeg_bytes,
    resolve_ocr_preprocess_max_edge,
)
from src.media_pipeline.ocr_filtering.errors import OcrFilteringError


def _write_solid_jpeg(path: Path, *, width: int, height: int) -> None:
    from PIL import Image

    Image.new("RGB", (width, height), color=(30, 60, 90)).save(path, format="JPEG", quality=95)


def _write_soft_textish_jpeg(path: Path, *, width: int, height: int) -> None:
    """Soft gray glyphs on white — contrast/sharpen should change pixels."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 40, 200, 70), fill=(180, 180, 180))
    draw.rectangle((40, 100, 280, 125), fill=(160, 160, 160))
    img.save(path, format="JPEG", quality=95)


class AsyncOcrPreprocessUpgradeTests(unittest.TestCase):
    def test_defaults_max_edge_1920_semaphore_timeout(self) -> None:
        self.assertEqual(ASYNC_OCR_CONCURRENCY, 2)
        self.assertEqual(ASYNC_OCR_TIMEOUT_SECONDS, 300)
        self.assertEqual(ASYNC_OCR_MAX_EDGE_PX, 1920)
        self.assertEqual(ASYNC_OCR_JPEG_QUALITY, 85)

    def test_ocr_preprocess_max_edge_env_override(self) -> None:
        with patch.dict("os.environ", {"OCR_PREPROCESS_MAX_EDGE": "720"}):
            self.assertEqual(resolve_ocr_preprocess_max_edge(), 720)

    def test_prepare_keeps_1080p_and_resizes_only_above_1920(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "full_hd.jpg"
            _write_solid_jpeg(path, width=1080, height=1920)
            raw, up_w, up_h, orig_w, orig_h = prepare_ocr_jpeg_bytes(path)
            self.assertEqual((orig_w, orig_h), (1080, 1920))
            self.assertEqual((up_w, up_h), (1080, 1920))
            self.assertTrue(raw.startswith(b"\xff\xd8"))

            big = Path(tmp) / "4k.jpg"
            _write_solid_jpeg(big, width=2160, height=3840)
            _raw, up_w2, up_h2, orig_w2, orig_h2 = prepare_ocr_jpeg_bytes(big)
            self.assertEqual((orig_w2, orig_h2), (2160, 3840))
            self.assertEqual(max(up_w2, up_h2), 1920)
            self.assertAlmostEqual(up_w2 / up_h2, 2160 / 3840, places=2)

    def test_enhance_increases_local_contrast_on_soft_glyphs(self) -> None:
        frame = np.full((120, 200, 3), 240, dtype=np.uint8)
        frame[40:70, 30:150] = 170
        out = enhance_ocr_frame_bgr(frame)
        self.assertEqual(out.shape, frame.shape)
        # Soft bar should move away from mid-gray after contrast+sharpen.
        self.assertNotEqual(int(out[50, 80, 0]), int(frame[50, 80, 0]))

    def test_enhance_returns_copy_on_bad_input_without_crash(self) -> None:
        empty = np.zeros((0, 0, 3), dtype=np.uint8)
        out = enhance_ocr_frame_bgr(empty)
        self.assertEqual(out.shape, empty.shape)

    def test_prepare_applies_enhance_pipeline_and_survives_soft_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "soft_ui.jpg"
            _write_soft_textish_jpeg(path, width=720, height=1280)
            raw, up_w, up_h, orig_w, orig_h = prepare_ocr_jpeg_bytes(path)
            self.assertEqual((orig_w, orig_h), (720, 1280))
            self.assertEqual((up_w, up_h), (720, 1280))
            self.assertTrue(raw.startswith(b"\xff\xd8"))
            self.assertGreater(len(raw), 500)

    def test_prepare_raises_on_unreadable_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jpg"
            path.write_bytes(b"not-an-image")
            with self.assertRaises(OcrFilteringError) as ctx:
                prepare_ocr_jpeg_bytes(path)
            self.assertIn("bad.jpg", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
