"""Cover and VI must share the same OCR box (left-aligned, no ink-refine drift)."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import (
    build_cover_mask,
    draw_vi_overlays,
    process_frame_bgr,
    _norm_box_to_pixels,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


class UnifiedOcrBoxAlignTests(unittest.TestCase):
    def test_cover_mask_matches_ocr_box_not_ink_drift(self) -> None:
        h, w = 200, 200
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        # Dark icon left of label — must not pull cover leftward.
        frame[90:110, 10:35] = (10, 10, 10)
        frame[90:110, 80:140] = (20, 20, 20)
        seg = OverlaySegment(0, 1000, 0.40, 0.45, 0.30, 0.10, "Com", kind="ui")
        mask = build_cover_mask(frame, [seg])
        ys, xs = np.where(mask > 0)
        self.assertGreater(len(xs), 0)
        # Cover stays near OCR box (x≈80..140), not the icon at x=10.
        self.assertGreaterEqual(int(xs.min()), 70)
        self.assertLessEqual(int(xs.max()), 155)

    def test_vi_centered_on_segment_box(self) -> None:
        h, w = 200, 300
        frame = np.full((h, w, 3), 200, dtype=np.uint8)
        seg = OverlaySegment(0, 1000, 0.20, 0.40, 0.35, 0.12, "ABCDEF", kind="ui")
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = draw_vi_overlays(frame, [seg], fontfile=font)
        x0, y0, x1, y1 = _norm_box_to_pixels(
            seg.x, seg.y, seg.width, seg.height, frame_w=w, frame_h=h
        )
        ax = (x0 + x1) // 2
        ay = y1
        # Center-bottom band has ink; far-left of box should be quieter than center.
        center_band = out[max(0, ay - 35) : ay, max(0, ax - 20) : ax + 20, 0]
        left_band = out[max(0, ay - 35) : ay, x0 : x0 + 15, 0]
        self.assertGreater(float((center_band < 80).mean()), 0.01)
        self.assertGreaterEqual(
            float((center_band < 80).mean()),
            float((left_band < 80).mean()) - 0.01,
        )

    def test_process_frame_does_not_use_ink_refine_drift(self) -> None:
        h, w = 200, 200
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        frame[90:110, 10:35] = (10, 10, 10)
        frame[90:110, 80:140] = (20, 20, 20)
        seg = OverlaySegment(0, 1000, 0.40, 0.45, 0.30, 0.10, "Com", kind="ui")
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = process_frame_bgr(frame, [seg], fontfile=font)
        # Icon region should remain mostly dark (cover must not jump onto it).
        self.assertLess(float(out[90:110, 10:35, 0].mean()), 80.0)


if __name__ == "__main__":
    unittest.main()
