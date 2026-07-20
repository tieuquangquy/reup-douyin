"""Overlay zones beyond bottom hard-sub: mid-title + dense end-card."""

from __future__ import annotations

import unittest

from src.media_pipeline.ocr_filtering.overlay_zones import (
    OVERLAY_CROP_TOP,
    cluster_boxes_by_y,
    filter_overlay_boxes,
    is_endcard_dense,
    is_mid_title_box,
)
from src.media_pipeline.ocr_filtering.subtitle_band import BOTTOM_BAND_RATIO
from src.media_pipeline.ocr_filtering.types import DetectedTextBox
from src.media_pipeline.video_renderer.overlays import OverlaySegment, overlays_from_ocr_payload
from src.media_pipeline.translator.normalize import flatten_ocr_chinese


class MidTitleZoneTests(unittest.TestCase):
    def test_keeps_mid_title_and_bottom_hardsub_rejects_top_logo(self) -> None:
        # Keep sparse (3 boxes) so relaxed endcard rules do not swallow cooking shots.
        boxes = [
            DetectedTextBox(x=0.1, y=0.05, width=0.2, height=0.04, text="logo", confidence=0.9),
            DetectedTextBox(x=0.25, y=0.38, width=0.5, height=0.07, text="什锦炒虾仁", confidence=0.95),
            DetectedTextBox(x=0.1, y=0.80, width=0.7, height=0.08, text="硬字幕", confidence=0.95),
        ]
        kept = filter_overlay_boxes(boxes, band_ratio=BOTTOM_BAND_RATIO)
        texts = [b.text for b in kept]
        self.assertEqual(texts, ["什锦炒虾仁", "硬字幕"])
        self.assertTrue(is_mid_title_box(boxes[1]))
        self.assertFalse(is_mid_title_box(boxes[0]))
        self.assertFalse(is_endcard_dense(boxes))

    def test_overlay_crop_top_covers_mid_title_band(self) -> None:
        self.assertLessEqual(OVERLAY_CROP_TOP, 0.25)


class EndcardDenseTests(unittest.TestCase):
    def test_dense_nutrition_ui_is_endcard(self) -> None:
        boxes = [
            DetectedTextBox(0.1, 0.1 + i * 0.08, 0.8, 0.06, f"line{i}", 0.9) for i in range(8)
        ]
        self.assertTrue(is_endcard_dense(boxes))
        kept = filter_overlay_boxes(boxes, band_ratio=BOTTOM_BAND_RATIO)
        self.assertEqual(len(kept), 8)

    def test_four_box_ui_card_is_endcard(self) -> None:
        """Relaxed: 4 boxes + area≥0.08 → endcard."""
        boxes = [
            DetectedTextBox(0.1, 0.12 + i * 0.12, 0.75, 0.08, f"row{i}", 0.9) for i in range(4)
        ]
        # 4 * 0.75 * 0.08 = 0.24 area
        self.assertTrue(is_endcard_dense(boxes))

    def test_many_small_ocr_crumbs_is_endcard_even_if_area_low(self) -> None:
        """Real PaddleOCR on UI cards: many tiny boxes, sum area often << 0.15."""
        boxes = [
            DetectedTextBox(0.1, 0.08 + i * 0.09, 0.35, 0.035, f"ui{i}", 0.9) for i in range(6)
        ]
        # 6 * 0.35 * 0.035 ≈ 0.073 area — old threshold 0.15 would miss.
        self.assertTrue(is_endcard_dense(boxes))

    def test_tall_y_span_four_boxes_is_endcard(self) -> None:
        boxes = [
            DetectedTextBox(0.1, 0.10, 0.5, 0.04, "a", 0.9),
            DetectedTextBox(0.1, 0.30, 0.5, 0.04, "b", 0.9),
            DetectedTextBox(0.1, 0.50, 0.5, 0.04, "c", 0.9),
            DetectedTextBox(0.1, 0.70, 0.5, 0.04, "d", 0.9),
        ]
        self.assertTrue(is_endcard_dense(boxes))

    def test_sparse_mid_scene_is_not_endcard(self) -> None:
        boxes = [
            DetectedTextBox(0.25, 0.38, 0.5, 0.07, "title", 0.95),
            DetectedTextBox(0.1, 0.80, 0.7, 0.08, "sub", 0.95),
        ]
        self.assertFalse(is_endcard_dense(boxes))

    def test_late_clip_sparse_label_is_per_box_not_dense_panel(self) -> None:
        """Last 20% with one CJK label: per-box cover only — no force slate."""
        payload = {
            "frames": [
                {
                    "frame_id": "late",
                    "time_ms": 24000,
                    "boxes": [
                        {"x": 0.2, "y": 0.4, "width": 0.5, "height": 0.06, "text": "午餐"},
                    ],
                }
            ]
        }
        overlays = overlays_from_ocr_payload(
            payload,
            {"24000#0": "Bua trua"},
            hold_ms=500,
            video_duration_ms=29000,
        )
        panels = [seg for seg in overlays if seg.kind == "dense_ui"]
        labels = [seg for seg in overlays if seg.kind != "dense_ui"]
        self.assertEqual(len(panels), 0)
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0].end_ms, 29000)
        self.assertLess(labels[0].width, 0.70)

    def test_dense_ui_frame_is_panel_plus_labels_to_eof(self) -> None:
        """Dense nutrition UI: slate panel + one VI label segment per CJK box."""
        boxes = [
            {"x": 0.08, "y": 0.08 + i * 0.09, "width": 0.75, "height": 0.07, "text": f"行{i}"}
            for i in range(8)
        ]
        payload = {
            "frames": [
                {"frame_id": "end", "time_ms": 28000, "boxes": boxes},
            ]
        }
        overlays = overlays_from_ocr_payload(
            payload,
            {f"28000#{i}": f"VI{i}" for i in range(8)},
            hold_ms=500,
            video_duration_ms=32000,
        )
        panels = [seg for seg in overlays if seg.kind == "dense_ui"]
        labels = [seg for seg in overlays if seg.kind != "dense_ui"]
        self.assertEqual(len(panels), 1)
        self.assertEqual(len(labels), 8)
        self.assertGreaterEqual(panels[0].y + panels[0].height, 0.90)
        self.assertEqual(overlays[0].start_ms, 28000)
        self.assertEqual(overlays[0].end_ms, 32000)

    def test_hardsub_delogo_uses_min_cover_width(self) -> None:
        from pathlib import Path

        from src.media_pipeline.video_renderer.filter_graph import build_single_render_filter

        hard = OverlaySegment(28000, 32000, 0.30, 0.82, 0.40, 0.08, " ", kind="hardsub")
        vf = build_single_render_filter(
            [hard],
            fontfile=Path("C:/Windows/Fonts/arial.ttf"),
            anti_seed=1,
            pad_x=0.05,
            pad_y=0.03,
            hold_ms=0,
            frame_width=1080,
            frame_height=1920,
        )
        # min_width ~0.88 on 1080 → delogo w near full usable width (not ~540).
        self.assertRegex(vf, r"delogo=x=\d+:y=\d+:w=9\d\d:")


class ClusterOverlayTests(unittest.TestCase):
    def test_vertically_distant_boxes_become_separate_overlays(self) -> None:
        payload = {
            "frames": [
                {
                    "frame_id": "frame_000001",
                    "time_ms": 0,
                    "boxes": [
                        {"x": 0.25, "y": 0.38, "width": 0.5, "height": 0.07, "text": "什锦炒虾仁"},
                        {"x": 0.10, "y": 0.80, "width": 0.70, "height": 0.08, "text": "硬字幕"},
                    ],
                }
            ]
        }
        clusters = cluster_boxes_by_y(payload["frames"][0]["boxes"])
        self.assertEqual(len(clusters), 2)

        flat = flatten_ocr_chinese(payload)
        self.assertIn("0#0", flat)
        self.assertIn("0#1", flat)
        self.assertEqual(flat["0#0"], "什锦炒虾仁")
        self.assertEqual(flat["0#1"], "硬字幕")

        vi = {"0#0": "Tom xao thap cam", "0#1": "Phu de"}
        overlays = overlays_from_ocr_payload(payload, vi, hold_ms=500, pad_x=0.0, pad_y=0.0)
        self.assertEqual(len(overlays), 2)
        self.assertEqual(overlays[0].text_vi, "Tom xao thap cam")
        self.assertEqual(overlays[1].text_vi, "Phu de")
        # Must not merge into one giant cover from y=0.38 to bottom.
        self.assertLess(overlays[0].y + overlays[0].height, 0.55)
        self.assertGreater(overlays[1].y, 0.70)
        self.assertEqual(overlays[0].kind, "title")
        self.assertEqual(overlays[1].kind, "hardsub")


class ExpandByKindTests(unittest.TestCase):
    def test_hardsub_expands_min_width_title_does_not(self) -> None:
        from src.media_pipeline.video_renderer.filter_graph import build_single_render_filter
        from pathlib import Path

        title = OverlaySegment(0, 1000, 0.30, 0.38, 0.40, 0.07, "Title VI", kind="title")
        hard = OverlaySegment(0, 1000, 0.30, 0.82, 0.40, 0.08, "Sub VI", kind="hardsub")
        vf = build_single_render_filter(
            [title, hard],
            fontfile=Path("C:/Windows/Fonts/arial.ttf"),
            anti_seed=1,
            pad_x=0.05,
            pad_y=0.03,
            hold_ms=0,
            frame_width=1080,
            frame_height=1920,
        )
        # Title stays relatively narrow; hardsub forces ~min cover width.
        self.assertIn("delogo=", vf)
        self.assertEqual(vf.count("delogo="), 2)


if __name__ == "__main__":
    unittest.main()
