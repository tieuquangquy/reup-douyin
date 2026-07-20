"""Snap must cover full label glyphs and must not latch food thumbnails."""

from __future__ import annotations

import unittest

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import refine_segments_to_ink_inside_ocr
from src.media_pipeline.video_renderer.overlays import OverlaySegment


class FullLabelSnapTests(unittest.TestCase):
    def test_snap_covers_both_chinese_characters(self) -> None:
        h, w = 120, 220
        frame = np.full((h, w, 3), 252, dtype=np.uint8)
        # Two glyphs; second much lighter (darkest+55 filter used to drop it).
        frame[50:75, 90:115] = (20, 20, 20)
        frame[50:75, 120:150] = (95, 95, 95)
        seg = OverlaySegment(0, 1000, 0.30, 0.35, 0.45, 0.30, "Cơm", kind="ui")
        r = refine_segments_to_ink_inside_ocr(frame, [seg])[0]
        x0 = float(r.x) * w
        x1 = (float(r.x) + float(r.width)) * w
        self.assertLess(x0, 95.0)
        self.assertGreater(x1, 145.0)

    def test_snap_recovers_when_ocr_parked_left_of_glyph(self) -> None:
        """Paddle box in the gap left of the character must snap onto the glyph."""
        h, w = 120, 220
        frame = np.full((h, w, 3), 252, dtype=np.uint8)
        frame[40:85, 15:55] = (30, 160, 70)  # icon
        # OCR covers gap (mostly white on the right half of the box).
        # Glyph sits to the right of OCR.
        frame[50:78, 110:145] = (25, 25, 25)
        seg = OverlaySegment(0, 1000, 0.25, 0.35, 0.18, 0.35, "Tôm", kind="ui")
        # OCR ~55..95; glyph at 110..145
        r = refine_segments_to_ink_inside_ocr(frame, [seg])[0]
        x0 = float(r.x) * w
        self.assertGreater(x0, 100.0)

    def test_snap_grows_right_when_ocr_clips_second_glyph(self) -> None:
        """Left-padded OCR that only covers the first char must still include the next."""
        h, w = 120, 240
        frame = np.full((h, w, 3), 252, dtype=np.uint8)
        # First glyph inside OCR; second glyph just outside OCR right edge.
        frame[50:75, 88:112] = (25, 25, 25)
        frame[50:75, 116:140] = (40, 40, 40)
        # OCR ~70..115 (covers first glyph only; left pad empty).
        seg = OverlaySegment(0, 1000, 70 / w, 48 / h, 45 / w, 30 / h, "Cơm", kind="ui")
        r = refine_segments_to_ink_inside_ocr(frame, [seg])[0]
        x0 = float(r.x) * w
        x1 = (float(r.x) + float(r.width)) * w
        self.assertLess(x0, 95.0)
        self.assertGreater(x1, 135.0)

    def test_reject_hairline_snap_on_header_title(self) -> None:
        """Bad (0,0) OCR must not latch a 1px top fringe — recover real white title."""
        h, w = 200, 320
        frame = np.full((h, w, 3), (80, 140, 40), dtype=np.uint8)
        # Top fringe noise (anti-aliased edge) that a naive pass-1 would grab.
        frame[0:2, 20:280] = (240, 240, 240)
        # True title below the bogus OCR box.
        frame[55:85, 30:110] = (250, 250, 250)
        # OCR at origin, height stops above the real glyphs (Paddle 午餐 style).
        seg = OverlaySegment(0, 1000, 0.0, 0.0, 0.20, 0.20, "Bữa trưa", kind="ui")
        r = refine_segments_to_ink_inside_ocr(frame, [seg])[0]
        cy = (float(r.y) + float(r.height) / 2.0) * h
        ch = float(r.height) * h
        self.assertGreater(cy, 50.0)
        self.assertGreater(ch, 15.0)

    def test_snap_does_not_bridge_wide_gap_to_next_word(self) -> None:
        """Do not merge a distant word on the same row."""
        h, w = 120, 280
        frame = np.full((h, w, 3), 252, dtype=np.uint8)
        frame[50:75, 80:110] = (25, 25, 25)
        frame[50:75, 200:240] = (25, 25, 25)  # far word
        seg = OverlaySegment(0, 1000, 70 / w, 48 / h, 50 / w, 30 / h, "Cơm", kind="ui")
        r = refine_segments_to_ink_inside_ocr(frame, [seg])[0]
        x1 = (float(r.x) + float(r.width)) * w
        self.assertLess(x1, 130.0)


if __name__ == "__main__":
    unittest.main()
