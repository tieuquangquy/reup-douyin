"""Cover authority must include all on-screen text zones, not caption-only."""

from __future__ import annotations

import unittest

from src.media_pipeline.ocr_filtering.box_timeline_tracker import TimedBox
from src.media_pipeline.ocr_filtering.ocr_authority_v3 import (
    FrameEvidence,
    authority_boxes_for_frame,
    merge_local_cover_only,
)
from src.media_pipeline.ocr_filtering.overlay_zones import (
    is_compact_overlay_label,
    is_mid_title_box,
)
from src.media_pipeline.ocr_filtering.per_frame_position_authority import (
    append_raw_compact_label_geometry_keeps,
    keep_rejected_compact_label_geometry,
)
from src.media_pipeline.video_renderer.overlays import overlays_from_ocr_payload


class MultiZoneCaptionTests(unittest.TestCase):
    def test_hardsub_frame_keeps_mid_label_and_hardsub(self) -> None:
        """Regression: 加盐 (mid) must not be dropped when bottom hardsub is active."""
        evidence = FrameEvidence(
            frame_index=75,
            time_ms=2500,
            local_boxes=(
                TimedBox(0.15, 0.48, 0.12, 0.045),  # 加盐 geometry
                TimedBox(0.0, 0.87, 0.64, 0.043),  # hardsub geometry
            ),
            ocr_boxes=(
                TimedBox(0.16, 0.49, 0.10, 0.04, "加盐", 0.99),
                TimedBox(0.0, 0.87, 0.64, 0.043, "虾仁豆腐蒸蛋614千卡", 0.99),
            ),
        )
        boxes = authority_boxes_for_frame(evidence)
        texts = {b.text for b in boxes}
        self.assertIn("加盐", texts)
        self.assertIn("虾仁豆腐蒸蛋614千卡", texts)


class LocalCoverOnlyMergeTests(unittest.TestCase):
    def test_unmatched_local_hardsub_becomes_cover_only(self) -> None:
        """Chrome 中式减脂餐 is in local_hardsub_boxes but missing from OCR → cover_only."""
        approved = [
            TimedBox(0.0, 0.869, 0.645, 0.043, "虾仁豆腐蒸蛋614千卡", 0.99),
        ]
        local = [
            TimedBox(0.0, 0.869, 0.645, 0.043),
            TimedBox(0.008, 0.864, 0.201, 0.055),  # orange chrome
        ]
        merged = merge_local_cover_only(approved, local)
        self.assertEqual(len(merged), 2)
        cover = [b for b in merged if b.cover_only]
        self.assertEqual(len(cover), 1)
        self.assertAlmostEqual(cover[0].x, 0.008, places=3)
        self.assertFalse(bool(merged[0].cover_only))


class CompactLabelZoneTests(unittest.TestCase):
    def test_compact_action_label_accepted(self) -> None:
        self.assertTrue(
            is_compact_overlay_label(
                {"x": 0.15, "y": 0.48, "width": 0.12, "height": 0.04}
            )
        )
        # Giant rice FP bottom band — not a compact mid label
        self.assertFalse(
            is_compact_overlay_label(
                {"x": 0.0, "y": 0.815, "width": 1.0, "height": 0.185}
            )
        )

    def test_jia_yan_geometry_is_compact_not_mid_title(self) -> None:
        """DBNet 加盐 at t≈2.5s: narrow+tall must not use mid-title width bypass."""
        box = {"x": 0.157, "y": 0.462, "width": 0.067, "height": 0.064}
        self.assertFalse(is_mid_title_box(box))
        self.assertTrue(is_compact_overlay_label(box))

    def test_unmatched_compact_local_becomes_cover_only(self) -> None:
        approved = [
            TimedBox(0.0, 0.869, 0.645, 0.043, "虾仁豆腐蒸蛋614千卡", 0.99),
        ]
        local = [
            TimedBox(0.0, 0.869, 0.645, 0.043),
            TimedBox(0.157, 0.462, 0.067, 0.064),  # 加盐 local, no OCR
        ]
        merged = merge_local_cover_only(approved, local)
        cover = [b for b in merged if b.cover_only]
        self.assertEqual(len(cover), 1)
        self.assertAlmostEqual(cover[0].y, 0.462, places=3)

    def test_keep_rejected_compact_label_geometry(self) -> None:
        box = TimedBox(0.157, 0.462, 0.067, 0.064)
        self.assertTrue(keep_rejected_compact_label_geometry(box))
        uncertain: list[TimedBox] = []
        append_raw_compact_label_geometry_keeps(
            raw_boxes=[box],
            accepted=[],
            uncertain=uncertain,
        )
        self.assertEqual(len(uncertain), 1)
        self.assertAlmostEqual(uncertain[0].w, 0.067, places=3)


class OverlayCoverOnlyAlwaysTests(unittest.TestCase):
    def test_cover_only_emitted_outside_endcard(self) -> None:
        payload = {
            "endcard_mode": "text_only",
            "frames": [
                {
                    "time_ms": 2500,
                    "frame_state": "hardsub",
                    "boxes": [
                        {
                            "x": 0.0,
                            "y": 0.87,
                            "w": 0.64,
                            "h": 0.04,
                            "text": "虾仁豆腐蒸蛋614千卡",
                            "confidence": 0.99,
                        },
                        {
                            "x": 0.01,
                            "y": 0.86,
                            "w": 0.20,
                            "h": 0.05,
                            "cover_only": True,
                        },
                    ],
                }
            ],
        }
        overlays = overlays_from_ocr_payload(
            payload, {"2500#0": "Tôm đậu hũ trứng hấp 614 kcal"}, hold_ms=500
        )
        self.assertGreaterEqual(len(overlays), 2)
        self.assertTrue(any(o.text_vi == "" and o.kind == "ui" for o in overlays))
        self.assertTrue(any("Tôm" in (o.text_vi or "") for o in overlays))

    def test_endcard_state_covers_all_boxes_without_forced_brown_panel(self) -> None:
        """text_only endcards must cover each box; avoid full-frame blur slate."""
        payload = {
            "endcard_mode": "text_only",
            "frames": [
                {
                    "time_ms": 27500,
                    "frame_state": "endcard",
                    "boxes": [
                        {
                            "x": 0.1,
                            "y": 0.2,
                            "w": 0.3,
                            "h": 0.04,
                            "text": "即热米饭",
                            "confidence": 0.9,
                        },
                        {
                            "x": 0.1,
                            "y": 0.4,
                            "w": 0.3,
                            "h": 0.04,
                            "text": "鸡蛋",
                            "confidence": 0.9,
                        },
                        {
                            "x": 0.1,
                            "y": 0.6,
                            "w": 0.3,
                            "h": 0.04,
                            "text": "豆腐",
                            "confidence": 0.9,
                        },
                        {
                            "x": 0.1,
                            "y": 0.75,
                            "w": 0.3,
                            "h": 0.04,
                            "text": "虾仁",
                            "confidence": 0.9,
                        },
                    ],
                }
            ],
        }
        overlays = overlays_from_ocr_payload(payload, {}, hold_ms=500)
        self.assertFalse(any(o.kind == "dense_ui" for o in overlays))
        self.assertGreaterEqual(len(overlays), 4)


if __name__ == "__main__":
    unittest.main()
