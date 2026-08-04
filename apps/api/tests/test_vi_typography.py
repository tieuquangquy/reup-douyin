"""VI burn: fixed global font size, center-bottom anchor, stroke, diacritics."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.media_pipeline.translator.translate_llm import USER_BATCH_INSTRUCTION
from src.media_pipeline.video_renderer.inpaint_render import (
    draw_vi_overlays,
    global_vi_font_size_px,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


def _segoe_or_arial() -> Path:
    segoe = Path(r"C:\Windows\Fonts\segoeui.ttf")
    if segoe.is_file():
        return segoe
    return Path(r"C:\Windows\Fonts\arial.ttf")


class ViTypographyTests(unittest.TestCase):
    def test_font_uses_global_size_not_box_fit(self) -> None:
        h, w = 500, 400
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        seg = OverlaySegment(0, 1000, 0.20, 0.70, 0.55, 0.04, "Cơm", kind="ui")
        font = _segoe_or_arial()
        out = draw_vi_overlays(frame, [seg], fontfile=font)
        expected = global_vi_font_size_px(h)
        pil_font = ImageFont.truetype(str(font), size=expected)
        bbox = ImageDraw.Draw(Image.new("RGB", (8, 8))).textbbox(
            (0, 0), "Cơm", font=pil_font, stroke_width=2
        )
        th = bbox[3] - bbox[1]
        ax = int((seg.x + seg.width / 2) * w)
        ay = int((seg.y + seg.height) * h)
        y0 = max(0, ay - th - 6)
        y1 = min(h, ay + 4)
        x0 = max(0, ax - 80)
        x1 = min(w, ax + 80)
        ink = out[y0:y1, x0:x1, 0] < 80
        self.assertTrue(np.any(ink))
        ys = np.where(np.any(ink, axis=1))[0]
        ink_h = int(ys.max() - ys.min() + 1)
        self.assertGreaterEqual(ink_h, int(expected * 0.50))

    def test_vi_centered_on_box_not_left_pad(self) -> None:
        h, w = 200, 300
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        seg = OverlaySegment(0, 1000, 0.30, 0.40, 0.40, 0.12, "Cơm", kind="ui")
        font = _segoe_or_arial()
        out = draw_vi_overlays(frame, [seg], fontfile=font)
        ax = int((seg.x + seg.width / 2) * w)
        ay = int((seg.y + seg.height) * h)
        # Ink should appear near center-bottom, not only at left OCR edge.
        band = out[max(0, ay - 40) : min(h, ay + 2), max(0, ax - 30) : min(w, ax + 30), 0]
        self.assertGreater(float((band < 80).mean()), 0.01)

    def test_diacritics_string_is_burned(self) -> None:
        h, w = 200, 320
        frame = np.full((h, w, 3), 250, dtype=np.uint8)
        text = "Bữa trưa"
        seg = OverlaySegment(0, 1000, 0.20, 0.50, 0.40, 0.12, text, kind="ui")
        font = _segoe_or_arial()
        out = draw_vi_overlays(frame, [seg], fontfile=font)
        ax = int((seg.x + seg.width / 2) * w)
        ay = int((seg.y + seg.height) * h)
        roi = out[max(0, ay - 50) : min(h, ay + 4), max(0, ax - 80) : min(w, ax + 80), 0]
        self.assertGreater(float((roi < 80).mean()), 0.005)
        pil_font = ImageFont.truetype(str(font), size=18)
        bbox = ImageDraw.Draw(Image.new("RGB", (8, 8))).textbbox((0, 0), text, font=pil_font)
        self.assertGreater(bbox[2] - bbox[0], 20)

    def test_user_instruction_requires_diacritics(self) -> None:
        lower = USER_BATCH_INSTRUCTION.lower()
        self.assertTrue(
            "có dấu" in USER_BATCH_INSTRUCTION
            or "co dau" in lower
            or "dấu" in USER_BATCH_INSTRUCTION,
            msg="USER_BATCH_INSTRUCTION must require Vietnamese with diacritics",
        )


if __name__ == "__main__":
    unittest.main()
