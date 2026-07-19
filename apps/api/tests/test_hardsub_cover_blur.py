"""Cover geometry helpers + filter contracts for hard-sub clean (pad/expand + blur)."""

from __future__ import annotations

import unittest
from pathlib import Path

from src.media_pipeline.video_renderer.filter_graph import build_single_render_filter
from src.media_pipeline.video_renderer.overlays import (
    DEFAULT_MIN_COVER_WIDTH,
    DEFAULT_PAD_X,
    DEFAULT_PAD_Y,
    OverlaySegment,
    expand_cover_rect,
)


class CoverGeometryTests(unittest.TestCase):
    def test_expand_cover_rect_pads_and_enforces_min_width(self) -> None:
        # Narrow OCR box → expand toward full subtitle strip so glyphs are not clipped.
        x0, y0, w, h = expand_cover_rect(
            0.35,
            0.82,
            0.25,
            0.08,
            pad_x=0.05,
            pad_y=0.03,
            min_width=0.88,
            side_margin=0.04,
        )
        self.assertGreaterEqual(w, 0.88 - 1e-6)
        self.assertGreaterEqual(x0, 0.04 - 1e-6)
        self.assertLessEqual(x0 + w, 1.0 - 0.04 + 1e-6)
        self.assertLess(y0, 0.82)
        self.assertGreater(h, 0.08)

    def test_defaults_are_wider_than_legacy_crumbs(self) -> None:
        self.assertGreaterEqual(DEFAULT_PAD_X, 0.04)
        self.assertGreaterEqual(DEFAULT_PAD_Y, 0.03)
        self.assertGreaterEqual(DEFAULT_MIN_COVER_WIDTH, 0.85)


class FilterGraphBlurMaskTests(unittest.TestCase):
    def test_single_render_uses_delogo_blur_not_black_drawbox(self) -> None:
        overlays = [
            OverlaySegment(
                start_ms=0,
                end_ms=1000,
                x=0.35,
                y=0.82,
                width=0.25,
                height=0.08,
                text_vi="Xin chao",
            )
        ]
        vf = build_single_render_filter(
            overlays,
            fontfile=Path("C:/Windows/Fonts/arial.ttf"),
            anti_seed=42,
            pad_x=0.05,
            pad_y=0.03,
            hold_ms=0,
            frame_width=1080,
            frame_height=1920,
        )
        self.assertIn("delogo=", vf)
        self.assertIn("show=0", vf)
        self.assertIn("drawtext=", vf)
        self.assertNotIn("drawbox=", vf)
        self.assertIn("enable=between(t\\,", vf)
        # delogo on common FFmpeg builds rejects iw*/ih* expressions.
        self.assertNotIn("iw*", vf.split("drawtext=")[0])
        self.assertNotIn("ih*", vf.split("drawtext=")[0])
        self.assertRegex(vf, r"delogo=x=\d+:y=\d+:w=\d+:h=\d+")
        self.assertLess(vf.index("delogo="), vf.index("drawtext="))

    def test_delogo_uses_integer_pixels_not_iw_expressions(self) -> None:
        """Regression: ANALYZE_OCR failed with Undefined constant in 'iw*0.0597'."""
        overlays = [
            OverlaySegment(0, 1000, 0.0597, 0.80, 0.88, 0.10, "VI", kind="hardsub")
        ]
        vf = build_single_render_filter(
            overlays,
            fontfile=Path("C:/Windows/Fonts/arial.ttf"),
            anti_seed=1,
            hold_ms=0,
            frame_width=1080,
            frame_height=1920,
        )
        delogo_part = vf.split("drawtext=")[0]
        self.assertIn("delogo=", delogo_part)
        self.assertNotIn("iw*", delogo_part)
        self.assertNotIn("ih*", delogo_part)
        self.assertRegex(delogo_part, r"delogo=x=\d+:y=\d+:w=\d+:h=\d+")



if __name__ == "__main__":
    unittest.main()
