"""Dense UI hybrid: slate panel above subtitle band + VI at CJK label boxes."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from src.media_pipeline.video_renderer.inpaint_render import process_frame_bgr
from src.media_pipeline.video_renderer.overlays import (
    OverlaySegment,
    dense_ui_content_panel,
    overlays_from_ocr_payload,
)


def _nutrition_dense_frame(*, time_ms: int = 25000) -> dict:
    return {
        "frame_id": f"t{time_ms}",
        "time_ms": time_ms,
        "boxes": [
            {"x": 0.08, "y": 0.06, "width": 0.22, "height": 0.06, "text": "午餐"},
            {"x": 0.08, "y": 0.14, "width": 0.30, "height": 0.04, "text": "2024-12-17"},
            {"x": 0.15, "y": 0.28, "width": 0.35, "height": 0.05, "text": "蛋白质"},
            {"x": 0.15, "y": 0.35, "width": 0.30, "height": 0.05, "text": "脂肪"},
            {"x": 0.15, "y": 0.42, "width": 0.40, "height": 0.05, "text": "碳水化合物"},
            {"x": 0.70, "y": 0.26, "width": 0.18, "height": 0.10, "text": "525千卡"},
            {"x": 0.12, "y": 0.52, "width": 0.25, "height": 0.05, "text": "米饭"},
            {"x": 0.12, "y": 0.60, "width": 0.28, "height": 0.05, "text": "花生油"},
            {
                "x": 0.10,
                "y": 0.82,
                "width": 0.80,
                "height": 0.08,
                "text": "Đang giảm mỡ thì follow nhé",
            },
        ],
    }


class DenseUiPanelGeometryTests(unittest.TestCase):
    def test_panel_stops_above_subtitle_band(self) -> None:
        x, y, w, h = dense_ui_content_panel()
        self.assertGreaterEqual(x, 0.02)
        self.assertLessEqual(x + w, 0.98)
        self.assertLessEqual(y + h, 0.68)  # below ~2/3 reserved for hard-sub / VI
        self.assertGreaterEqual(h, 0.45)


class DenseUiOverlayTests(unittest.TestCase):
    def test_dense_frame_emits_panel_plus_cjk_labels_skips_vi(self) -> None:
        payload = {"frames": [_nutrition_dense_frame()]}
        vi = {f"25000#{i}": f"VI{i}" for i in range(7)}
        overlays = overlays_from_ocr_payload(
            payload,
            vi,
            hold_ms=500,
            video_duration_ms=29000,
        )
        kinds = [seg.kind for seg in overlays]
        self.assertIn("dense_ui", kinds)
        panels = [seg for seg in overlays if seg.kind == "dense_ui"]
        self.assertEqual(len(panels), 1)
        self.assertEqual(panels[0].text_vi, "")
        self.assertLessEqual(panels[0].y + panels[0].height, 0.68)
        labels = [seg for seg in overlays if seg.kind != "dense_ui"]
        self.assertGreaterEqual(len(labels), 5)
        self.assertTrue(all(seg.y + seg.height < 0.80 for seg in labels))
        self.assertEqual(overlays[-1].end_ms, 29000)


class DenseUiRenderTests(unittest.TestCase):
    def test_panel_wipes_ui_chinese_leaves_bottom_band(self) -> None:
        h, w = 400, 300
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        # Chinese-like bars in UI region (under panel; away from VI label boxes).
        frame[40:70, 30:120] = (15, 15, 15)
        frame[200:230, 40:150] = (15, 15, 15)
        # Dark bar in bottom subtitle band — must survive (no cover).
        frame[340:370, 40:260] = (10, 10, 10)
        x, y, bw, bh = dense_ui_content_panel()
        segs = [
            OverlaySegment(0, 1000, x, y, bw, bh, "", kind="dense_ui"),
            # VI labels placed away from the wipe probe ROIs above.
            OverlaySegment(0, 1000, 0.55, 0.12, 0.30, 0.06, "Bua trua", kind="ui"),
            OverlaySegment(0, 1000, 0.55, 0.45, 0.30, 0.06, "Com", kind="ui"),
        ]
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = process_frame_bgr(frame, segs, fontfile=font)
        # UI bars should be slate-wiped (not near-black Chinese strokes).
        self.assertGreater(float(out[40:70, 30:120, 0].mean()), 40.0)
        self.assertGreater(float(out[200:230, 40:150, 0].mean()), 40.0)
        self.assertLess(float((out[40:70, 30:120, 0] < 25).mean()), 0.05)
        # Bottom band largely unchanged (still dark).
        self.assertGreater(float((out[340:370, 40:260, 0] < 40).mean()), 0.80)

    def test_skips_filename_like_vi_burn(self) -> None:
        h, w = 200, 200
        frame = np.full((h, w, 3), 200, dtype=np.uint8)
        segs = [
            OverlaySegment(
                0,
                1000,
                0.1,
                0.7,
                0.8,
                0.08,
                "7449357262730136851__v19_OCR_PIPELINE_V1_cleaned.mp4",
                kind="hardsub",
            ),
        ]
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = process_frame_bgr(frame, segs, fontfile=font)
        # Cover may change pixels; must not re-burn the filename string as white text.
        # Filename burn would lighten a large fraction of the bottom band center.
        center = out[150:170, 40:160]
        whiteish = float((center[:, :, 0] > 220).mean())
        self.assertLess(whiteish, 0.35)


class LateClipForceDenseTests(unittest.TestCase):
    def test_late_clip_one_cjk_hardsub_still_gets_dense_panel(self) -> None:
        """Real job pattern: endcard OCR only returns 1 hard-sub line, misses UI labels."""
        payload = {
            "frames": [
                {
                    "frame_id": "late",
                    "time_ms": 27000,
                    "boxes": [
                        {
                            "x": 0.10,
                            "y": 0.82,
                            "width": 0.80,
                            "height": 0.08,
                            "text": "减脂就来关注吧",
                        },
                        {
                            "x": 0.10,
                            "y": 0.70,
                            "width": 0.80,
                            "height": 0.06,
                            "text": "Đang giảm mỡ thì follow nhé",
                        },
                    ],
                }
            ]
        }
        overlays = overlays_from_ocr_payload(
            payload,
            {"27000#0": "Dang giam mo thi follow nhe"},
            hold_ms=500,
            video_duration_ms=29000,
        )
        panels = [seg for seg in overlays if seg.kind == "dense_ui"]
        labels = [seg for seg in overlays if seg.kind != "dense_ui"]
        self.assertEqual(len(panels), 1)
        self.assertLessEqual(panels[0].y + panels[0].height, 0.68)
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0].text_vi, "Dang giam mo thi follow nhe")
        self.assertEqual(overlays[-1].end_ms, 29000)

    def test_late_clip_latin_only_still_gets_panel_no_vi_burn(self) -> None:
        """OCR only saw VI hard-sub; still wipe missed Chinese UI above the band."""
        payload = {
            "frames": [
                {
                    "frame_id": "late",
                    "time_ms": 28000,
                    "boxes": [
                        {
                            "x": 0.10,
                            "y": 0.82,
                            "width": 0.80,
                            "height": 0.08,
                            "text": "Đang giảm mỡ thì follow nhé",
                        },
                    ],
                }
            ]
        }
        overlays = overlays_from_ocr_payload(
            payload,
            {},
            hold_ms=500,
            video_duration_ms=29000,
        )
        self.assertEqual(len(overlays), 1)
        self.assertEqual(overlays[0].kind, "dense_ui")
        self.assertEqual(overlays[0].text_vi, "")
        self.assertLessEqual(overlays[0].y + overlays[0].height, 0.68)

    def test_mid_clip_single_hardsub_does_not_force_panel(self) -> None:
        payload = {
            "frames": [
                {
                    "frame_id": "mid",
                    "time_ms": 5000,
                    "boxes": [
                        {
                            "x": 0.10,
                            "y": 0.82,
                            "width": 0.80,
                            "height": 0.08,
                            "text": "焯一下木耳胡萝卜",
                        },
                    ],
                }
            ]
        }
        overlays = overlays_from_ocr_payload(
            payload,
            {"5000#0": "Chan moc nhi ca rot"},
            hold_ms=500,
            video_duration_ms=29000,
        )
        self.assertTrue(all(seg.kind != "dense_ui" for seg in overlays))
        self.assertEqual(len(overlays), 1)


if __name__ == "__main__":
    unittest.main()
