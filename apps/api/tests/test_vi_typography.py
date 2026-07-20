"""VI burn: size near OCR box height, left at OCR x (not cover pad), keep diacritics."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.media_pipeline.translator.service import USER_INSTRUCTION
from src.media_pipeline.video_renderer.inpaint_render import (
    _TIGHT_PAD_X,
    draw_vi_overlays,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


def _segoe_or_arial() -> Path:
    segoe = Path(r"C:\Windows\Fonts\segoeui.ttf")
    if segoe.is_file():
        return segoe
    return Path(r"C:\Windows\Fonts\arial.ttf")


class ViTypographyTests(unittest.TestCase):
    def test_font_height_matches_ocr_box_scale(self) -> None:
        """VI ink height must track the scanned label box (not half-size)."""
        h, w = 200, 300
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        # Short VI so width shrink does not dominate; height 40px.
        seg = OverlaySegment(0, 1000, 0.20, 0.40, 0.55, 0.20, "Cơm", kind="ui")
        font = _segoe_or_arial()
        ocr_h = int(seg.height * h)
        out = draw_vi_overlays(frame, [seg], fontfile=font, align="left")
        x0 = int(seg.x * w)
        y0 = int(seg.y * h)
        x1 = int((seg.x + seg.width) * w)
        y1 = int((seg.y + seg.height) * h)
        roi = out[y0:y1, x0:x1, 0]
        ink = roi < 80
        self.assertTrue(np.any(ink))
        ys = np.where(np.any(ink, axis=1))[0]
        ink_h = int(ys.max() - ys.min() + 1)
        ratio = ink_h / float(ocr_h)
        self.assertGreaterEqual(ratio, 0.70)
        self.assertLessEqual(ratio, 1.05)

    def test_vi_left_edge_at_ocr_x_not_cover_pad(self) -> None:
        h, w = 200, 300
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        seg = OverlaySegment(0, 1000, 0.30, 0.40, 0.40, 0.12, "Cơm", kind="ui")
        font = _segoe_or_arial()
        out = draw_vi_overlays(frame, [seg], fontfile=font, align="left")
        x0 = int(seg.x * w)
        y0 = int(seg.y * h)
        y1 = int((seg.y + seg.height) * h)
        # Pad would start ~_TIGHT_PAD_X*w left of OCR; ink must not live there.
        pad_px = int(_TIGHT_PAD_X * w) + 2
        left_of_ocr = out[y0:y1, max(0, x0 - pad_px) : x0, 0]
        in_ocr_left = out[y0:y1, x0 : x0 + 20, 0]
        self.assertLess(float((left_of_ocr < 80).mean()), 0.01)
        self.assertGreater(float((in_ocr_left < 80).mean()), 0.01)

    def test_diacritics_string_is_burned(self) -> None:
        h, w = 120, 240
        frame = np.full((h, w, 3), 250, dtype=np.uint8)
        text = "Bữa trưa"
        seg = OverlaySegment(0, 1000, 0.10, 0.30, 0.55, 0.25, text, kind="ui")
        font = _segoe_or_arial()
        out = draw_vi_overlays(frame, [seg], fontfile=font, align="left")
        x0 = int(seg.x * w)
        y0 = int(seg.y * h)
        x1 = int((seg.x + seg.width) * w)
        y1 = int((seg.y + seg.height) * h)
        self.assertGreater(float((out[y0:y1, x0:x1, 0] < 80).mean()), 0.005)
        # Font must be able to measure the diacritic string (not tofu-only).
        pil_font = ImageFont.truetype(str(font), size=18)
        bbox = ImageDraw.Draw(Image.new("RGB", (8, 8))).textbbox((0, 0), text, font=pil_font)
        self.assertGreater(bbox[2] - bbox[0], 20)

    def test_user_instruction_requires_diacritics(self) -> None:
        lower = USER_INSTRUCTION.lower()
        self.assertTrue(
            "có dấu" in USER_INSTRUCTION or "co dau" in lower or "dấu" in USER_INSTRUCTION,
            msg="USER_INSTRUCTION must require Vietnamese with diacritics",
        )


if __name__ == "__main__":
    unittest.main()
