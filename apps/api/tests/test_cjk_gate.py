"""CJK gate: keep Chinese UI/hard-sub; leave Latin/VI-only text untouched."""

from __future__ import annotations

import unittest

from src.media_pipeline.ocr_filtering.script_filter import contains_cjk
from src.media_pipeline.translator.normalize import flatten_ocr_chinese
from src.media_pipeline.video_renderer.overlays import overlays_from_ocr_payload


def _frame_with_vi_hardsub(*, time_ms: int = 5000) -> dict:
    return {
        "frame_id": f"t{time_ms}",
        "time_ms": time_ms,
        "boxes": [
            {"x": 0.08, "y": 0.06, "width": 0.22, "height": 0.06, "text": "午餐"},
            {"x": 0.08, "y": 0.14, "width": 0.30, "height": 0.04, "text": "2024-12-17"},
            {"x": 0.15, "y": 0.28, "width": 0.22, "height": 0.04, "text": "蛋白质"},
            {"x": 0.70, "y": 0.26, "width": 0.18, "height": 0.08, "text": "525千卡"},
            {"x": 0.12, "y": 0.50, "width": 0.25, "height": 0.05, "text": "米饭"},
            {
                "x": 0.10,
                "y": 0.82,
                "width": 0.80,
                "height": 0.08,
                "text": "Đang siết cân thì follow nha",
            },
        ],
    }


class ContainsCjkTests(unittest.TestCase):
    def test_chinese_and_mixed_have_cjk(self) -> None:
        self.assertTrue(contains_cjk("午餐"))
        self.assertTrue(contains_cjk("525千卡"))
        self.assertTrue(contains_cjk("200.00克"))

    def test_latin_vi_date_no_cjk(self) -> None:
        self.assertFalse(contains_cjk("Đang siết cân thì follow nha"))
        self.assertFalse(contains_cjk("2024-12-17"))
        self.assertFalse(contains_cjk("27%"))
        self.assertFalse(contains_cjk(""))


class CjkFlattenTests(unittest.TestCase):
    def test_flatten_skips_vi_hardsub_and_date(self) -> None:
        flat = flatten_ocr_chinese({"frames": [_frame_with_vi_hardsub()]})
        self.assertEqual(flat["5000#0"], "午餐")
        self.assertEqual(flat["5000#1"], "蛋白质")
        self.assertEqual(flat["5000#2"], "525千卡")
        self.assertEqual(flat["5000#3"], "米饭")
        self.assertNotIn("Đang siết cân thì follow nha", flat.values())
        self.assertNotIn("2024-12-17", flat.values())
        # Contiguous indices among CJK-only boxes.
        self.assertEqual(len([k for k in flat if "#" in k]), 4)


class CjkOverlayTests(unittest.TestCase):
    def test_overlays_skip_vi_hardsub_keep_chinese_boxes(self) -> None:
        payload = {"frames": [_frame_with_vi_hardsub(time_ms=5000)]}
        vi = {
            "5000#0": "Bua trua",
            "5000#1": "Protein",
            "5000#2": "525 kcal",
            "5000#3": "Com",
        }
        overlays = overlays_from_ocr_payload(
            payload,
            vi,
            hold_ms=500,
            video_duration_ms=29000,
        )
        labels = [seg for seg in overlays if seg.kind != "dense_ui"]
        self.assertEqual(len(labels), 4)
        texts = [seg.text_vi for seg in labels]
        self.assertEqual(texts, ["Bua trua", "Protein", "525 kcal", "Com"])
        # Dense panel wipes near-full frame; labels stay on CJK boxes only.
        for seg in overlays:
            if seg.kind == "dense_ui":
                self.assertGreaterEqual(seg.y + seg.height, 0.90)
            else:
                self.assertLess(seg.y + seg.height, 0.80)


if __name__ == "__main__":
    unittest.main()
