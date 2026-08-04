"""Che nhầm: cover must stay near OCR AABB (general — all videos)."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import process_frame_bgr
from src.media_pipeline.video_renderer.overlays import OverlaySegment


def _font() -> Path:
    segoe = Path(r"C:\Windows\Fonts\segoeui.ttf")
    return segoe if segoe.is_file() else Path(r"C:\Windows\Fonts\arial.ttf")


class CoverNoFalsePositiveTests(unittest.TestCase):
    def test_oversized_midframe_box_does_not_wipe_food_texture(self) -> None:
        """
        Detector false-positives are often huge mid-frame boxes over food.

        Cover must refuse those boxes (all videos) — not paint solid/blur fills.
        """
        h, w = 240, 360
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                frame[y, x] = (
                    (40, 90, 220) if ((x // 10) + (y // 10)) % 2 == 0 else (80, 140, 255)
                )
        # Real fossil shape class: ~53%×13% mid-frame "ui" with empty VI.
        seg = OverlaySegment(0, 1000, 0.234, 0.42, 0.531, 0.128, "", kind="ui")
        out = process_frame_bgr(frame, [seg], fontfile=_font())
        y0, y1 = int(0.42 * h), int((0.42 + 0.128) * h)
        x0, x1 = int(0.234 * w), int((0.234 + 0.531) * w)
        delta = float(
            np.abs(out[y0:y1, x0:x1].astype(np.float32) - frame[y0:y1, x0:x1].astype(np.float32)).mean()
        )
        self.assertLess(delta, 5.0, "oversized non-text box must not be covered")

    def test_plausible_hardsub_line_still_covers_ink(self) -> None:
        h, w = 200, 360
        frame = np.full((h, w, 3), 80, dtype=np.uint8)
        # Realistic hardsub band (~60%×6%), not a mid-frame slab.
        y0, y1, x0, x1 = 160, 172, 40, 260
        frame[y0:y1, x0:x1] = (20, 20, 20)
        seg = OverlaySegment(
            0,
            1000,
            x0 / w,
            y0 / h,
            (x1 - x0) / w,
            (y1 - y0) / h,
            "Hấp",
            kind="hardsub",
        )
        out = process_frame_bgr(frame, [seg], fontfile=_font())
        self.assertGreater(
            float(out[y0:y1, x0:x1].mean()),
            float(frame[y0:y1, x0:x1].mean()) + 15.0,
        )
        # Distant patch untouched.
        frame_far = np.full_like(frame, 80)
        frame_far[30:70, 20:80] = (230, 230, 230)
        frame_far[y0:y1, x0:x1] = (20, 20, 20)
        out_far = process_frame_bgr(frame_far, [seg], fontfile=_font())
        self.assertTrue(
            np.allclose(
                out_far[30:70, 20:80].astype(np.float32),
                frame_far[30:70, 20:80].astype(np.float32),
                atol=12.0,
            )
        )

    def test_oversized_tall_blob_rejected_by_height(self) -> None:
        """Tall mid-frame slabs (>12% height) are food FP size-class, not labels."""
        from src.media_pipeline.video_renderer.overlays import is_plausible_text_cover_segment

        seg = OverlaySegment(0, 1000, 0.40, 0.35, 0.19, 0.20, "", kind="ui")
        self.assertFalse(is_plausible_text_cover_segment(seg))

    def test_compact_vertical_label_still_allowed(self) -> None:
        """Narrow tall crumbs (加盐-class) must remain coverable."""
        from src.media_pipeline.video_renderer.overlays import is_plausible_text_cover_segment

        seg = OverlaySegment(0, 1000, 0.55, 0.40, 0.05, 0.09, "", kind="ui")
        self.assertTrue(is_plausible_text_cover_segment(seg))


if __name__ == "__main__":
    unittest.main()
