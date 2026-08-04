"""Phase 4: ROI dilated inpaint + fixed-size centered VI burn."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import (
    GLOBAL_VI_FONT_FRAC,
    draw_vi_overlays,
    global_vi_font_size_px,
    inpaint_segments_roi,
    process_frame_bgr,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


def _font() -> Path:
    segoe = Path(r"C:\Windows\Fonts\segoeui.ttf")
    if segoe.is_file():
        return segoe
    return Path(r"C:\Windows\Fonts\arial.ttf")


class RoiInpaintTests(unittest.TestCase):
    def test_roi_inpaint_clears_box_without_touching_far_pixels(self) -> None:
        h, w = 200, 300
        frame = np.full((h, w, 3), 180, dtype=np.uint8)
        # Dark glyph block inside box.
        frame[80:120, 100:200] = (10, 10, 10)
        # Sentinel far from ROI — must stay unchanged.
        frame[10:20, 10:20] = (0, 0, 255)
        seg = OverlaySegment(0, 1000, 100 / w, 80 / h, 100 / w, 40 / h, "", kind="hardsub")
        out = inpaint_segments_roi(frame, [seg])
        self.assertTrue(np.array_equal(out[10:20, 10:20], frame[10:20, 10:20]))
        before = float(frame[80:120, 100:200].mean())
        after = float(out[80:120, 100:200].mean())
        self.assertGreater(after, before + 20)

    def test_empty_vi_skips_pillow_but_still_inpaints(self) -> None:
        h, w = 160, 240
        frame = np.full((h, w, 3), 200, dtype=np.uint8)
        frame[71:89, 75:165] = (5, 5, 5)
        seg = OverlaySegment(0, 1000, 75 / w, 71 / h, 90 / w, 18 / h, "", kind="hardsub")
        out = process_frame_bgr(frame, [seg], fontfile=_font())
        self.assertGreater(float(out[71:89, 75:165].mean()), float(frame[71:89, 75:165].mean()) + 15)


class FixedViFontTests(unittest.TestCase):
    def test_global_font_size_is_fraction_of_frame_height(self) -> None:
        self.assertEqual(global_vi_font_size_px(1000), int(round(1000 * GLOBAL_VI_FONT_FRAC)))
        self.assertGreaterEqual(global_vi_font_size_px(100), 12)

    def test_does_not_shrink_to_tiny_chinese_box(self) -> None:
        """Narrow ZH box must not force tiny VI — fixed GLOBAL size."""
        from PIL import Image, ImageDraw, ImageFont

        h, w = 500, 400
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        # Tiny OCR box (old path would shrink font into it).
        seg = OverlaySegment(0, 1000, 0.35, 0.80, 0.08, 0.03, "Thêm muối", kind="hardsub")
        out = draw_vi_overlays(frame, [seg], fontfile=_font())
        expected = global_vi_font_size_px(h)
        font = ImageFont.truetype(str(_font()), size=expected)
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        bbox = probe.textbbox((0, 0), "Thêm muối", font=font, stroke_width=2)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        # Ink footprint near bottom-center of box should be close to full glyph size,
        # not crushed into 0.03*H (~15px).
        ax = int((seg.x + seg.width / 2) * w)
        ay = int((seg.y + seg.height) * h)
        y0 = max(0, ay - th - 4)
        y1 = min(h, ay + 4)
        x0 = max(0, ax - tw // 2 - 4)
        x1 = min(w, ax + tw // 2 + 4)
        ink = out[y0:y1, x0:x1, 0] < 80
        self.assertTrue(np.any(ink))
        ys = np.where(np.any(ink, axis=1))[0]
        ink_h = int(ys.max() - ys.min() + 1)
        self.assertGreaterEqual(ink_h, int(expected * 0.55))

    def test_empty_text_vi_does_not_draw(self) -> None:
        h, w = 120, 200
        frame = np.full((h, w, 3), 250, dtype=np.uint8)
        seg = OverlaySegment(0, 1000, 0.2, 0.4, 0.4, 0.2, "", kind="hardsub")
        out = draw_vi_overlays(frame, [seg], fontfile=_font())
        self.assertTrue(np.array_equal(out, frame))


if __name__ == "__main__":
    unittest.main()
