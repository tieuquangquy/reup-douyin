"""Polish: local background fill + soft blur; dark VI on light UI."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import (
    apply_blur_cover,
    draw_vi_overlays,
    process_frame_bgr,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


class CoverPolishTests(unittest.TestCase):
    def test_local_fill_removes_dark_ink_on_white_card(self) -> None:
        h, w = 120, 160
        frame = np.full((h, w, 3), 245, dtype=np.uint8)
        frame[40:70, 40:120] = (15, 15, 15)
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[40:70, 40:120] = 255
        out = apply_blur_cover(frame, mask)
        # Near-white card fill — dark Chinese slab must be gone.
        self.assertGreater(float(out[40:70, 40:120, 0].mean()), 180.0)
        self.assertLess(float((out[40:70, 40:120, 0] < 40).mean()), 0.05)
        # Outside unchanged.
        self.assertTrue(np.array_equal(out[mask == 0], frame[mask == 0]))

    def test_per_region_fill_matches_local_background(self) -> None:
        """Teal bar + white card must not share one global fill color."""
        h, w = 120, 160
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:50, :] = (80, 140, 40)  # teal-ish BGR
        frame[50:, :] = (240, 240, 240)
        frame[15:35, 20:60] = (10, 10, 10)  # dark text on teal
        frame[70:95, 30:100] = (10, 10, 10)  # dark text on white
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[15:35, 20:60] = 255
        mask[70:95, 30:100] = 255
        out = apply_blur_cover(frame, mask)
        teal_mean = out[15:35, 20:60].reshape(-1, 3).mean(axis=0)
        white_mean = out[70:95, 30:100].reshape(-1, 3).mean(axis=0)
        self.assertLess(float(teal_mean[0]), 120.0)
        self.assertGreater(float(white_mean[0]), 180.0)

    def test_median_ring_ignores_dark_glyph_outliers(self) -> None:
        """Ring must not average leftover Chinese ink into a muddy gray fill."""
        h, w = 100, 120
        frame = np.full((h, w, 3), 245, dtype=np.uint8)
        frame[40:60, 30:90] = (10, 10, 10)
        # Dark strokes just outside the mask (OCR AABB shortfall).
        frame[38:40, 30:90] = (5, 5, 5)
        frame[60:62, 30:90] = (5, 5, 5)
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[40:60, 30:90] = 255
        out = apply_blur_cover(frame, mask)
        self.assertGreater(float(out[40:60, 30:90, 0].mean()), 200.0)

    def test_header_box_does_not_sample_white_card_below(self) -> None:
        """Title on teal must fill teal, not the white card under the OCR box."""
        h, w = 120, 160
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:45, :] = (80, 140, 40)
        frame[45:, :] = (245, 245, 245)
        frame[8:28, 10:50] = (15, 15, 15)
        mask = np.zeros((h, w), dtype=np.uint8)
        # OCR box slightly overlaps into the white card (common Paddle AABB).
        mask[8:50, 10:50] = 255
        out = apply_blur_cover(frame, mask)
        self.assertLess(float(out[8:28, 10:50, 0].mean()), 120.0)

    def test_dark_vi_on_light_background(self) -> None:
        h, w = 100, 200
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        seg = OverlaySegment(0, 1000, 0.10, 0.30, 0.50, 0.30, "Com", kind="ui")
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = draw_vi_overlays(frame, [seg], fontfile=font, align="left")
        # Dark ink (not white-on-white) should appear in the label band.
        band = out[35:65, 25:120, 0]
        self.assertGreater(float((band < 80).mean()), 0.01)

    def test_process_frame_hides_chinese_better_than_ghost_blur(self) -> None:
        h, w = 160, 200
        frame = np.full((h, w, 3), 250, dtype=np.uint8)
        frame[70:95, 40:140] = (10, 10, 10)
        seg = OverlaySegment(0, 1000, 0.20, 0.42, 0.50, 0.16, "Tom", kind="ui")
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = process_frame_bgr(frame, [seg], fontfile=font)
        # Cover must lift the near-black Chinese slab (VI ink may still be dark).
        self.assertGreater(float(out[70:95, 40:140, 0].mean()), 100.0)


if __name__ == "__main__":
    unittest.main()
