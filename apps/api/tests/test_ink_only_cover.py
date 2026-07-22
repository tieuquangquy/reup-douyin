"""Cover must touch glyph ink only — never blur neighboring food/UI pixels."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import process_frame_bgr
from src.media_pipeline.video_renderer.overlays import OverlaySegment


def _font() -> Path:
    segoe = Path(r"C:\Windows\Fonts\segoeui.ttf")
    return segoe if segoe.is_file() else Path(r"C:\Windows\Fonts\arial.ttf")


class InkOnlyCoverTests(unittest.TestCase):
    def test_process_frame_does_not_blur_pixels_far_from_glyphs(self) -> None:
        h, w = 200, 200
        frame = np.full((h, w, 3), 220, dtype=np.uint8)
        # Target label ink (right).
        frame[90:110, 100:150] = (15, 15, 15)
        # Food marker well outside OCR box and ink search pad.
        frame[30:50, 30:50] = (0, 200, 0)
        seg = OverlaySegment(0, 1000, 0.50, 0.45, 0.25, 0.10, "Com", kind="ui")
        out = process_frame_bgr(frame, [seg], fontfile=_font())
        green_before = frame[30:50, 30:50, 1].astype(np.float32)
        green_after = out[30:50, 30:50, 1].astype(np.float32)
        self.assertTrue(
            np.allclose(green_before, green_after, atol=8.0),
            "pixels far from OCR ink must not be blurred",
        )

    def test_process_frame_does_not_blur_inside_ocr_box_but_outside_ink(self) -> None:
        """OCR AABB is wider than glyphs — padding must not blur the gap."""
        h, w = 200, 200
        frame = np.full((h, w, 3), 220, dtype=np.uint8)
        frame[90:110, 110:150] = (15, 15, 15)
        # Bright gap inside OCR box, left of ink — must stay bright.
        frame[90:110, 80:108] = (240, 240, 240)
        seg = OverlaySegment(0, 1000, 0.40, 0.45, 0.35, 0.10, "Com", kind="ui")
        out = process_frame_bgr(frame, [seg], fontfile=_font())
        gap_before = frame[90:110, 80:108, 0].astype(np.float32).mean()
        gap_after = out[90:110, 80:108, 0].astype(np.float32).mean()
        self.assertGreater(gap_after, 200.0)

    def test_process_frame_softens_glyph_ink(self) -> None:
        h, w = 200, 200
        frame = np.full((h, w, 3), 220, dtype=np.uint8)
        frame[90:110, 100:150] = (15, 15, 15)
        seg = OverlaySegment(0, 1000, 0.50, 0.45, 0.25, 0.10, "Com", kind="ui")
        out = process_frame_bgr(frame, [seg], fontfile=_font())
        self.assertLess(float((out[90:110, 100:150, 0] < 40).mean()), 0.55)

    def test_hybrid_fallback_covers_tight_ocr_when_ink_undetectable(self) -> None:
        """Ink scan miss must not leave the frame untouched — tight OCR fallback."""
        h, w = 200, 200
        frame = np.full((h, w, 3), 220, dtype=np.uint8)
        # Near-flat "text" — contrast ink finds nothing.
        frame[90:110, 100:140] = (218, 218, 218)
        seg = OverlaySegment(0, 1000, 0.50, 0.45, 0.20, 0.10, "Com", kind="hardsub")
        out = process_frame_bgr(frame, [seg], fontfile=_font())
        before = frame[90:110, 100:140].astype(np.float32)
        after = out[90:110, 100:140].astype(np.float32)
        self.assertFalse(np.allclose(before, after, atol=3.0))


if __name__ == "__main__":
    unittest.main()
