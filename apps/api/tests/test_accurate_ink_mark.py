"""OCR AABB often drifts; refine must recover true glyphs without latching icons."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import (
    process_frame_bgr,
    refine_segments_to_ink_inside_ocr,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


def _font() -> Path:
    segoe = Path(r"C:\Windows\Fonts\segoeui.ttf")
    return segoe if segoe.is_file() else Path(r"C:\Windows\Fonts\arial.ttf")


class AccurateInkMarkTests(unittest.TestCase):
    def test_refine_recovers_glyph_outside_shifted_ocr(self) -> None:
        """Paddle-style bad AABB (up-left of true text) must snap onto glyphs."""
        h, w = 120, 200
        frame = np.full((h, w, 3), 40, dtype=np.uint8)  # teal-ish dark
        frame[:, :] = (80, 140, 40)
        # True white title glyphs overlapping the bad OCR enough to recover.
        frame[18:48, 18:70] = (250, 250, 250)
        # Bad OCR at top-left corner (like 午餐 → 0,0).
        seg = OverlaySegment(0, 1000, 0.0, 0.0, 0.25, 0.28, "Bữa trưa", kind="ui")
        refined = refine_segments_to_ink_inside_ocr(frame, [seg])[0]
        cx = (float(refined.x) + float(refined.width) / 2.0) * w
        cy = (float(refined.y) + float(refined.height) / 2.0) * h
        self.assertGreaterEqual(cx, 25.0)
        self.assertLess(cx, 80.0)
        self.assertGreater(cy, 15.0)
        self.assertLess(cy, 55.0)

    def test_refine_skips_colorful_icon_left_of_text(self) -> None:
        h, w = 120, 200
        frame = np.full((h, w, 3), 245, dtype=np.uint8)
        frame[40:70, 15:45] = (30, 200, 80)  # green icon
        frame[45:65, 100:155] = (20, 20, 20)  # dark label
        # OCR covers icon margin + text (left-padded).
        seg = OverlaySegment(0, 1000, 0.05, 0.30, 0.75, 0.35, "Cơm", kind="ui")
        refined = refine_segments_to_ink_inside_ocr(frame, [seg])[0]
        self.assertGreater(float(refined.x) * w, 85.0)
        mask_x0 = float(refined.x) * w
        self.assertGreater(mask_x0, 50.0)  # not on icon

    def test_process_frame_inpaints_box_and_burns_vi_at_anchor(self) -> None:
        h, w = 200, 300
        frame = np.full((h, w, 3), 245, dtype=np.uint8)
        frame[80:100, 100:200] = (15, 15, 15)
        # Plausible UI label (~33%×10%) — taller slabs are refused as food FP.
        seg = OverlaySegment(0, 1000, 100 / w, 80 / h, 100 / w, 20 / h, "Cơm", kind="ui")
        out = process_frame_bgr(frame, [seg], fontfile=_font())
        # Chinese slab lifted by ROI inpaint.
        self.assertGreater(float(out[80:100, 100:200].mean()), 40.0)
        # VI stroke near center-bottom of the OCR box.
        ax = int((seg.x + seg.width / 2) * w)
        ay = int((seg.y + seg.height) * h)
        band = out[max(0, ay - 40) : ay, max(0, ax - 30) : ax + 30, 0]
        self.assertGreater(float((band < 80).mean()), 0.005)


if __name__ == "__main__":
    unittest.main()
