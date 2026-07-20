"""OCR quality profile resolution."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from src.media_pipeline.ocr_filtering.ocr_quality_profile import (
    BEST_JPEG_QUALITY,
    BEST_PREPROCESS_MAX_EDGE,
    effective_ocr_crop_band,
    effective_ocr_jpeg_quality,
    effective_ocr_preprocess_max_edge,
    is_best_ocr_profile,
    resolve_ocr_quality_profile,
)


class OcrQualityProfileTests(unittest.TestCase):
    def test_best_profile_enables_max_upload(self) -> None:
        with mock.patch.dict(os.environ, {"OCR_QUALITY_PROFILE": "best"}, clear=False):
            self.assertTrue(is_best_ocr_profile())
            self.assertEqual(
                effective_ocr_preprocess_max_edge(1280),
                BEST_PREPROCESS_MAX_EDGE,
            )
            self.assertEqual(effective_ocr_jpeg_quality(85), BEST_JPEG_QUALITY)
            self.assertTrue(effective_ocr_crop_band(False))

    def test_default_profile_unchanged(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "OCR_QUALITY_PROFILE"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_ocr_quality_profile(), "default")
            self.assertFalse(is_best_ocr_profile())


if __name__ == "__main__":
    unittest.main()
