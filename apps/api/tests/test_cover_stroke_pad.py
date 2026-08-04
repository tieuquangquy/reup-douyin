"""Cover must include glyph stroke outside a tight OCR AABB (all videos)."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import (
    inpaint_segments_roi,
    process_frame_bgr,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


def _font() -> Path:
    segoe = Path(r"C:\Windows\Fonts\segoeui.ttf")
    return segoe if segoe.is_file() else Path(r"C:\Windows\Fonts\arial.ttf")


class CoverStrokePadTests(unittest.TestCase):
    def test_inpaint_clears_stroke_outside_tight_ocr_aabb(self) -> None:
        """
        Stylized hard-sub often has outline pixels above/below Paddle AABB.

        Mask must grow vertically — ROI crop pad alone is not enough.
        """
        h, w = 240, 400
        frame = np.full((h, w, 3), 90, dtype=np.uint8)  # textured-ish mid gray
        # True glyph band (tall); OCR reports a shorter middle strip.
        glyph_y0, glyph_y1 = 150, 190
        ocr_y0, ocr_y1 = 160, 180
        x0, x1 = 40, 280
        frame[glyph_y0:glyph_y1, x0:x1] = (250, 250, 250)
        # Dark outline rings just outside OCR but inside glyph band.
        frame[glyph_y0 : ocr_y0, x0:x1] = (5, 5, 5)
        frame[ocr_y1:glyph_y1, x0:x1] = (5, 5, 5)
        seg = OverlaySegment(
            0,
            1000,
            x0 / w,
            ocr_y0 / h,
            (x1 - x0) / w,
            (ocr_y1 - ocr_y0) / h,
            "",
            kind="hardsub",
        )
        out = inpaint_segments_roi(frame, [seg])
        top = out[glyph_y0:ocr_y0, x0:x1, 0]
        bot = out[ocr_y1:glyph_y1, x0:x1, 0]
        # Outline leftovers must be lifted — not left as dark strokes.
        self.assertLess(float((top < 40).mean()), 0.25)
        self.assertLess(float((bot < 40).mean()), 0.25)
        # Far sentinel untouched.
        self.assertTrue(np.array_equal(out[10:20, 10:20], frame[10:20, 10:20]))

    def test_process_frame_hardsub_hides_stroke_overhang(self) -> None:
        h, w = 240, 400
        frame = np.full((h, w, 3), 70, dtype=np.uint8)
        glyph_y0, glyph_y1 = 150, 192
        ocr_y0, ocr_y1 = 162, 180
        x0, x1 = 50, 300
        frame[glyph_y0:glyph_y1, x0:x1] = (245, 245, 245)
        frame[glyph_y0:ocr_y0, x0:x1] = (8, 8, 8)
        frame[ocr_y1:glyph_y1, x0:x1] = (8, 8, 8)
        seg = OverlaySegment(
            0,
            1000,
            x0 / w,
            ocr_y0 / h,
            (x1 - x0) / w,
            (ocr_y1 - ocr_y0) / h,
            "Hấp",
            kind="hardsub",
        )
        out = process_frame_bgr(frame, [seg], fontfile=_font())
        overhang = np.concatenate(
            [
                out[glyph_y0:ocr_y0, x0:x1, 0].ravel(),
                out[ocr_y1:glyph_y1, x0:x1, 0].ravel(),
            ]
        )
        self.assertLess(float((overhang < 40).mean()), 0.30)

    def test_ui_flat_card_cover_lifts_dark_label_without_far_damage(self) -> None:
        """UI labels on near-solid cards should local-fill, not smear neighbors."""
        h, w = 200, 240
        frame = np.full((h, w, 3), 245, dtype=np.uint8)
        frame[90:108, 60:160] = (12, 12, 12)
        # Neighbor icon column must stay.
        frame[90:108, 20:45] = (40, 180, 60)
        seg = OverlaySegment(0, 1000, 60 / w, 90 / h, 100 / w, 18 / h, "Cơm", kind="ui")
        out = process_frame_bgr(frame, [seg], fontfile=_font())
        self.assertGreater(float(out[90:108, 60:160, 0].mean()), 160.0)
        self.assertTrue(
            np.allclose(
                out[90:108, 20:45].astype(np.float32),
                frame[90:108, 20:45].astype(np.float32),
                atol=12.0,
            )
        )


class Phase1RoiCoverageTests(unittest.TestCase):
    def test_roi_includes_upper_mid_content_not_only_lower_third(self) -> None:
        """Nutrition / mid-card copy often sits above y=0.35 — ROI must see it."""
        from src.media_pipeline.frame_sampling.master_phase1_extractor import ROI_Y0

        self.assertLessEqual(ROI_Y0, 0.15)
        self.assertGreaterEqual(ROI_Y0, 0.05)


if __name__ == "__main__":
    unittest.main()
