"""Tests for ink snap + hardsub cover expand on TimedBox."""

from __future__ import annotations

import unittest

import numpy as np

from src.media_pipeline.ocr_filtering.box_geometry_refine import (
    expand_hardsub_cover_box,
    refine_timed_boxes_on_frame,
)
from src.media_pipeline.ocr_filtering.box_timeline_tracker import TimedBox


class BoxGeometryRefineTests(unittest.TestCase):
    def test_expand_hardsub_enforces_min_width(self) -> None:
        narrow = TimedBox(0.35, 0.91, 0.25, 0.05, text="开大火爆炒", confidence=0.95)
        got = expand_hardsub_cover_box(narrow)
        self.assertGreaterEqual(got.w, 0.85)
        self.assertLess(got.x, 0.1)

    def test_ink_refine_snaps_to_bright_hardsub(self) -> None:
        h, w = 180, 320
        frame = np.full((h, w, 3), 30, dtype=np.uint8)
        frame[150:170, 60:260] = 240
        box = TimedBox(0.15, 0.82, 0.20, 0.08, text="测试字幕行", confidence=0.9)
        got = refine_timed_boxes_on_frame(frame, [box], expand_hardsub=False)
        self.assertEqual(len(got), 1)
        self.assertGreater(got[0].w, box.w)
        self.assertGreater(got[0].x + got[0].w, box.x + box.w)

    def test_band_scan_finds_bottom_hardsub_line(self) -> None:
        from src.media_pipeline.ocr_filtering.per_frame_ink_scan import scan_hardsub_ink_box

        h, w = 200, 400
        frame = np.full((h, w, 3), 25, dtype=np.uint8)
        # Subtitle bar lower-right portion only — OCR hint is too narrow left.
        frame[170:188, 80:340] = 245
        hint = TimedBox(0.18, 0.84, 0.55, 0.06, text="字幕测试", confidence=0.9)
        got = scan_hardsub_ink_box(frame, hint=hint)
        self.assertIsNotNone(got)
        assert got is not None
        self.assertGreater(got.w, 0.35)
        self.assertGreater(got.y + got.h / 2.0, 0.85)


if __name__ == "__main__":
    unittest.main()
