"""Band-crop remap keeps OCR boxes aligned to the full frame."""

from __future__ import annotations

import unittest

from src.ocr_pipeline.band_crop import band_crop_top_ratio, remap_box_from_band_crop
from src.ocr_pipeline.types import OcrBox


class BandCropRemapTests(unittest.TestCase):
    def test_remap_box_from_band_crop_scales_into_bottom_band(self) -> None:
        band_ratio = 0.28
        # Box at top of the crop (y≈0) must land near band top in full frame.
        box = OcrBox(x=0.1, y=0.0, width=0.8, height=0.5, text="硬字幕", confidence=0.9)
        remapped = remap_box_from_band_crop(box, band_ratio=band_ratio)
        self.assertAlmostEqual(remapped.y, band_crop_top_ratio(band_ratio), places=4)
        self.assertAlmostEqual(remapped.height, 0.5 * band_ratio, places=4)
        self.assertEqual(remapped.text, "硬字幕")
        self.assertAlmostEqual(remapped.x, 0.1, places=4)


if __name__ == "__main__":
    unittest.main()
