"""Per-box cover + VI: layout-preserving Chinese replacement anywhere in the clip."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.translator.normalize import flatten_ocr_chinese
from src.media_pipeline.video_renderer.inpaint_render import process_frame_bgr
from src.media_pipeline.video_renderer.overlays import OverlaySegment, overlays_from_ocr_payload


def _nutrition_ui_frame(*, time_ms: int = 5000) -> dict:
    return {
        "frame_id": f"t{time_ms}",
        "time_ms": time_ms,
        "boxes": [
            {"x": 0.08, "y": 0.06, "width": 0.22, "height": 0.06, "text": "午餐"},
            {"x": 0.08, "y": 0.14, "width": 0.30, "height": 0.04, "text": "2024-12-17"},
            {"x": 0.15, "y": 0.28, "width": 0.22, "height": 0.04, "text": "蛋白质"},
            {"x": 0.70, "y": 0.26, "width": 0.18, "height": 0.08, "text": "525千卡"},
            {"x": 0.12, "y": 0.50, "width": 0.25, "height": 0.05, "text": "米饭"},
            {"x": 0.12, "y": 0.60, "width": 0.28, "height": 0.05, "text": "花生油"},
            {"x": 0.12, "y": 0.70, "width": 0.18, "height": 0.05, "text": "虾"},
        ],
    }


class PerBoxFlattenTests(unittest.TestCase):
    def test_flatten_emits_one_key_per_cjk_box(self) -> None:
        payload = {"frames": [_nutrition_ui_frame()]}
        flat = flatten_ocr_chinese(payload)
        # Date "2024-12-17" has no CJK → skipped; indices among Chinese only.
        self.assertEqual(flat["5000#0"], "午餐")
        self.assertEqual(flat["5000#1"], "蛋白质")
        self.assertEqual(flat["5000#3"], "米饭")
        self.assertIn("花生油", flat.values())
        self.assertNotIn("2024-12-17", flat.values())
        self.assertNotEqual(len(flat), 1)


class PerBoxOverlayTests(unittest.TestCase):
    def test_nutrition_ui_mid_clip_emits_dense_panel_plus_cjk_labels(self) -> None:
        payload = {"frames": [_nutrition_ui_frame(time_ms=5000)]}
        # 6 CJK boxes (date skipped): 午餐 蛋白质 525千卡 米饭 花生油 虾
        vi = {
            "5000#0": "Bua trua",
            "5000#1": "Protein",
            "5000#2": "525 kcal",
            "5000#3": "Com",
            "5000#4": "Dau phong",
            "5000#5": "Tom",
        }
        overlays = overlays_from_ocr_payload(
            payload,
            vi,
            hold_ms=500,
            video_duration_ms=29000,
        )
        panels = [seg for seg in overlays if seg.kind == "dense_ui"]
        labels = [seg for seg in overlays if seg.kind != "dense_ui"]
        self.assertEqual(len(panels), 1)
        self.assertEqual(len(labels), 6)
        self.assertEqual(panels[0].text_vi, "")
        self.assertLessEqual(panels[0].y + panels[0].height, 0.68)
        self.assertEqual(labels[0].text_vi, "Bua trua")
        self.assertEqual(labels[3].text_vi, "Com")
        self.assertLess(labels[0].width, 0.50)

    def test_late_clip_also_gets_dense_panel_to_eof(self) -> None:
        payload = {"frames": [_nutrition_ui_frame(time_ms=25000)]}
        vi = {f"25000#{i}": f"VI{i}" for i in range(6)}
        overlays = overlays_from_ocr_payload(
            payload,
            vi,
            hold_ms=500,
            video_duration_ms=29000,
        )
        self.assertTrue(any(seg.kind == "dense_ui" for seg in overlays))
        self.assertEqual(overlays[-1].end_ms, 29000)


class PerBoxRenderTests(unittest.TestCase):
    def test_process_frame_covers_each_label_and_burns_vi(self) -> None:
        h, w = 400, 300
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        # Dark Chinese-like bars in known ROIs.
        frame[24:48, 24:90] = (20, 20, 20)
        frame[200:220, 36:110] = (20, 20, 20)
        segs = [
            OverlaySegment(0, 1000, 0.08, 0.06, 0.22, 0.06, "Bua trua", kind="ui"),
            OverlaySegment(0, 1000, 0.12, 0.50, 0.25, 0.05, "Com", kind="ui"),
        ]
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = process_frame_bgr(frame, segs, fontfile=font)
        # Original dark bars should be largely gone.
        self.assertLess(float((out[24:48, 24:90, 0] < 40).mean()), 0.35)
        self.assertLess(float((out[200:220, 36:110, 0] < 40).mean()), 0.35)
        # Frame must change (VI burn and/or fill).
        self.assertFalse(np.array_equal(out, frame))


if __name__ == "__main__":
    unittest.main()
