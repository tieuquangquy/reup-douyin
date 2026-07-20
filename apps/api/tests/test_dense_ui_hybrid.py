"""Dense UI hybrid: near-full-frame panel wipe + VI at CJK label boxes."""

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
    def test_panel_covers_near_full_frame(self) -> None:
        """Dense Chinese UI spans the whole screen — panel must wipe nearly all of it."""
        x, y, w, h = dense_ui_content_panel()
        self.assertGreaterEqual(x, 0.02)
        self.assertLessEqual(x + w, 0.98)
        self.assertGreaterEqual(y + h, 0.90)
        self.assertGreaterEqual(h, 0.85)
        self.assertGreaterEqual(w, 0.85)


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
        self.assertGreaterEqual(panels[0].y + panels[0].height, 0.90)
        labels = [seg for seg in overlays if seg.kind != "dense_ui"]
        self.assertGreaterEqual(len(labels), 5)
        self.assertEqual(overlays[-1].end_ms, 29000)


class DenseUiRenderTests(unittest.TestCase):
    def test_dense_panel_wipes_chinese_outside_ocr_boxes(self) -> None:
        """Full-screen Chinese crumbs (no OCR box) must still be covered by the panel."""
        h, w = 400, 300
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        # Crumb left of the OCR box — previously left uncovered when slate was skipped.
        frame[100:130, 30:80] = (15, 15, 15)
        frame[48:72, 165:255] = (15, 15, 15)
        x, y, bw, bh = dense_ui_content_panel()
        segs = [
            OverlaySegment(0, 1000, x, y, bw, bh, "", kind="dense_ui"),
            OverlaySegment(0, 1000, 0.55, 0.12, 0.30, 0.06, "Bua trua", kind="ui"),
        ]
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = process_frame_bgr(frame, segs, fontfile=font)
        self.assertLess(float((out[100:130, 30:80, 0] < 40).mean()), 0.40)
        self.assertLess(float((out[48:72, 165:255, 0] < 25).mean()), 0.50)

    def test_dense_vi_stays_at_ocr_box_when_ink_is_elsewhere(self) -> None:
        """With dense_ui, VI authority is OCR box — do not snap to distant ink."""
        h, w = 400, 300
        frame = np.full((h, w, 3), 240, dtype=np.uint8)
        # Dark ink far left; OCR/VI box on the right.
        frame[48:72, 20:70] = (10, 10, 10)
        x, y, bw, bh = dense_ui_content_panel()
        segs = [
            OverlaySegment(0, 1000, x, y, bw, bh, "", kind="dense_ui"),
            OverlaySegment(0, 1000, 0.55, 0.12, 0.35, 0.06, "WWW", kind="ui"),
        ]
        font = Path(r"C:\Windows\Fonts\arial.ttf")
        if not font.is_file():
            font = Path(r"C:\Windows\Fonts\segoeui.ttf")
        out = process_frame_bgr(frame, segs, fontfile=font)
        # After panel fill (light), dark VI strokes land in the OCR box only.
        ocr_roi = out[48:72, 165:255]
        ink_roi = out[48:72, 20:70]
        self.assertGreater(float((ocr_roi[:, :, 0] < 80).mean()), 0.02)
        self.assertLess(float((ink_roi[:, :, 0] < 80).mean()), 0.02)

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


class LateClipNoForcePanelTests(unittest.TestCase):
    def test_late_clip_one_cjk_hardsub_does_not_force_dense_panel(self) -> None:
        """Sparse endcard OCR (1 hard-sub) must not paint the ugly slate wipe."""
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
        self.assertTrue(all(seg.kind != "dense_ui" for seg in overlays))
        self.assertEqual(len(overlays), 1)
        self.assertEqual(overlays[0].text_vi, "Dang giam mo thi follow nhe")
        self.assertEqual(overlays[0].end_ms, 29000)

    def test_late_clip_latin_only_skips_without_slate(self) -> None:
        """Latin/VI-only OCR must not invent a dense_ui slate."""
        from src.media_pipeline.video_renderer.errors import (
            VideoRendererError,
            VideoRendererErrorCode,
        )

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
        with self.assertRaises(VideoRendererError) as ctx:
            overlays_from_ocr_payload(
                payload,
                {},
                hold_ms=500,
                video_duration_ms=29000,
            )
        self.assertEqual(ctx.exception.code, VideoRendererErrorCode.EMPTY_OVERLAYS)

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
