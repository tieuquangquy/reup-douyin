"""Snap cover/VI to Chinese ink inside OCR AABB (ignore left empty/icon)."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import (
    build_cover_mask,
    draw_vi_overlays,
    process_frame_bgr,
    refine_segments_to_ink_inside_ocr,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


def _font() -> Path:
    segoe = Path(r"C:\Windows\Fonts\segoeui.ttf")
    return segoe if segoe.is_file() else Path(r"C:\Windows\Fonts\arial.ttf")


class InkInsideOcrSnapTests(unittest.TestCase):
    def _frame_with_left_empty_ocr(self) -> tuple[np.ndarray, OverlaySegment]:
        """OCR box includes empty left; Chinese ink only on the right half."""
        h, w = 120, 200
        frame = np.full((h, w, 3), 245, dtype=np.uint8)
        # Icon-like blob left of text (must not become cover/VI anchor).
        frame[40:70, 20:45] = (40, 180, 90)
        # Dark Chinese-like bar (true ink) on the right side of OCR.
        frame[45:65, 100:150] = (15, 15, 15)
        # OCR AABB: x=0.25..0.80 (50..160) — includes empty 50..100.
        seg = OverlaySegment(0, 1000, 0.25, 0.35, 0.55, 0.25, "Cơm", kind="ui")
        return frame, seg

    def test_refine_snaps_to_ink_not_ocr_left(self) -> None:
        frame, seg = self._frame_with_left_empty_ocr()
        h, w = frame.shape[:2]
        refined = refine_segments_to_ink_inside_ocr(frame, [seg])
        self.assertEqual(len(refined), 1)
        r = refined[0]
        # Ink starts ~x=100 → norm 0.50; must not stay at OCR left 0.25.
        self.assertGreater(float(r.x), 0.45)
        self.assertLess(float(r.x + r.width), 0.82)
        # Must not jump onto the green icon at x=20..45.
        self.assertGreater(float(r.x) * w, 90.0)

    def test_vi_left_matches_ink_not_ocr_padding(self) -> None:
        frame, seg = self._frame_with_left_empty_ocr()
        h, w = frame.shape[:2]
        out = process_frame_bgr(frame, [seg], fontfile=_font())
        # VI dark ink should appear near x=100, not near OCR left x=50.
        near_ink = out[45:65, 100:140, 0]
        near_ocr_left = out[45:65, 50:75, 0]
        self.assertGreater(float((near_ink < 80).mean()), 0.01)
        self.assertLess(float((near_ocr_left < 80).mean()), 0.01)

    def test_cover_does_not_swallow_left_icon(self) -> None:
        frame, seg = self._frame_with_left_empty_ocr()
        refined = refine_segments_to_ink_inside_ocr(frame, [seg])
        mask = build_cover_mask(frame, refined)
        # Green icon column must stay mostly uncovered.
        icon_col = mask[40:70, 20:45]
        self.assertLess(float((icon_col > 0).mean()), 0.15)


if __name__ == "__main__":
    unittest.main()
