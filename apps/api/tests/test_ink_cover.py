"""Ink helpers remain available; process_frame uses unified OCR AABB alignment."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import (
    build_ink_cover_mask,
    process_frame_bgr,
    refine_segments_to_ink,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


class InkAwareCoverTests(unittest.TestCase):
    def test_ink_mask_covers_glyph_beyond_left_biased_ocr_box(self) -> None:
        h, w = 200, 200
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        frame[90:112, 80:140] = (20, 20, 20)
        seg = OverlaySegment(0, 1000, 0.40, 0.45, 0.12, 0.11, "Protein", kind="ui")
        mask = build_ink_cover_mask(frame, [seg])
        self.assertGreater(int(mask[100, 125]), 0)
        self.assertGreater(int(mask[100, 100]), 0)
        self.assertEqual(int(mask[20, 20]), 0)

    def test_refine_expands_segment_to_ink_bbox(self) -> None:
        h, w = 200, 200
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        frame[90:112, 80:140] = (20, 20, 20)
        seg = OverlaySegment(0, 1000, 0.40, 0.45, 0.12, 0.11, "Protein", kind="ui")
        refined = refine_segments_to_ink(frame, [seg])
        self.assertEqual(len(refined), 1)
        r = refined[0]
        self.assertGreater(r.x + r.width, seg.x + seg.width + 0.05)
        self.assertLess(r.x, 0.45)

    def test_refine_does_not_swallow_neighbor_label(self) -> None:
        h, w = 200, 200
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        frame[90:110, 40:80] = (20, 20, 20)
        frame[90:110, 120:170] = (20, 20, 20)
        left = OverlaySegment(0, 1000, 0.20, 0.45, 0.15, 0.10, "A", kind="ui")
        right = OverlaySegment(0, 1000, 0.60, 0.45, 0.20, 0.10, "B", kind="ui")
        refined = refine_segments_to_ink(frame, [left, right])
        self.assertEqual(len(refined), 2)
        self.assertLess(refined[0].x + refined[0].width, 0.55)
        self.assertGreater(refined[1].x, 0.50)

    def test_process_frame_blurs_ocr_box_keeps_far_pixels(self) -> None:
        h, w = 200, 200
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        frame[90:112, 80:140] = (20, 20, 20)
        frame[20:40, 20:50] = (0, 180, 0)
        seg = OverlaySegment(0, 1000, 0.40, 0.45, 0.30, 0.11, "Com", kind="ui")
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = process_frame_bgr(frame, [seg], fontfile=font)
        self.assertGreater(float(out[20:40, 20:50, 1].mean()), 150.0)
        self.assertLess(float((out[90:112, 90:130, 0] < 40).mean()), 0.55)


if __name__ == "__main__":
    unittest.main()
