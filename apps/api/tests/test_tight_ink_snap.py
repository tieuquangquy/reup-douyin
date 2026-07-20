"""Snap bbox must hug true glyphs — not sit left of them in empty OCR pad."""

from __future__ import annotations

import unittest

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import refine_segments_to_ink_inside_ocr
from src.media_pipeline.video_renderer.overlays import OverlaySegment


class TightInkSnapTests(unittest.TestCase):
    def test_snap_ignores_soft_gray_fringe_left_of_glyphs(self) -> None:
        """Soft AA fringe darker than card but lighter than glyphs must not expand snap left."""
        h, w = 160, 240
        frame = np.full((h, w, 3), 254, dtype=np.uint8)
        # Separate lighter fringe CC (mean~190) left of dark glyphs (mean~40).
        frame[72:92, 100:120] = (190, 190, 190)
        frame[70:95, 130:185] = (40, 40, 40)
        seg = OverlaySegment(0, 1000, 0.35, 0.40, 0.45, 0.20, "Protein", kind="ui")
        refined = refine_segments_to_ink_inside_ocr(frame, [seg])[0]
        snap_x0 = float(refined.x) * w
        self.assertGreaterEqual(snap_x0, 125.0)
        self.assertLess(snap_x0, 138.0)


if __name__ == "__main__":
    unittest.main()
