"""Tight OCR-box mask + blur cover (not solid slate / wide pad)."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import (
    apply_blur_cover,
    build_cover_mask,
    process_frame_bgr,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


class TightCoverMaskTests(unittest.TestCase):
    def test_ui_mask_stays_near_ocr_box_not_wide_pad(self) -> None:
        h, w = 200, 200
        frame = np.full((h, w, 3), 200, dtype=np.uint8)
        # OCR box: x=0.40..0.55 (30px), y=0.40..0.48 (16px) on 200px frame.
        seg = OverlaySegment(0, 1000, 0.40, 0.40, 0.15, 0.08, "VI", kind="ui")
        mask = build_cover_mask(frame, [seg])
        ys, xs = np.where(mask > 0)
        self.assertGreater(len(xs), 0)
        # Must not spill far outside the OCR rect (allow ~4px / 0.02 norm slack).
        self.assertGreaterEqual(xs.min(), int(0.40 * w) - 4)
        self.assertLessEqual(xs.max(), int(0.55 * w) + 4)
        self.assertGreaterEqual(ys.min(), int(0.40 * h) - 4)
        self.assertLessEqual(ys.max(), int(0.48 * h) + 4)
        self.assertLess(float(np.count_nonzero(mask)) / float(mask.size), 0.05)


class BlurCoverTests(unittest.TestCase):
    def test_blur_cover_only_changes_mask_pixels(self) -> None:
        h, w = 120, 160
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = (30, 40, 50)
        frame[40:70, 50:110] = (255, 255, 255)
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[40:70, 50:110] = 255
        out = apply_blur_cover(frame, mask)
        outside = mask == 0
        self.assertTrue(np.array_equal(out[outside], frame[outside]))
        # White bar must pick up darker neighbors via blur kernel.
        self.assertLess(float((out[40:70, 50:110, 0] > 240).mean()), 0.50)

    def test_process_frame_blurs_ui_box_and_keeps_outside(self) -> None:
        h, w = 200, 200
        frame = np.full((h, w, 3), 220, dtype=np.uint8)
        frame[80:100, 80:140] = (10, 10, 10)  # dark "glyph" bar
        frame[20:40, 20:60] = (0, 180, 0)  # green marker outside text
        seg = OverlaySegment(0, 1000, 0.40, 0.40, 0.30, 0.10, "Com", kind="ui")
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = process_frame_bgr(frame, [seg], fontfile=font)
        # Outside marker mostly intact (cover must not slate-wipe the frame).
        self.assertGreater(float(out[20:40, 20:60, 1].mean()), 150.0)
        # Dark glyph region should be softened (not near-black slab).
        self.assertLess(float((out[80:100, 80:140, 0] < 25).mean()), 0.50)


if __name__ == "__main__":
    unittest.main()
