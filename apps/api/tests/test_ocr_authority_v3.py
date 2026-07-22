"""Regression fossils for OCR Authority V3 (f0, f3, f119, f758)."""

from __future__ import annotations

import unittest

from src.media_pipeline.ocr_filtering.box_timeline_tracker import TimedBox
from src.media_pipeline.ocr_filtering.ocr_authority_v3 import (
    EndcardSegment,
    FrameEvidence,
    authority_boxes_for_frame,
    classify_frame_state,
    detect_endcard_segments,
)


class OcrAuthorityV3RegressionTests(unittest.TestCase):
    def test_f0_keeps_two_title_boxes_and_rejects_rice_box(self) -> None:
        evidence = FrameEvidence(
            frame_index=0,
            time_ms=0,
            local_boxes=(
                TimedBox(0.0, 0.815, 1.0, 0.185),  # rice false-positive
                TimedBox(0.37, 0.46, 0.25, 0.07),
            ),
            ocr_boxes=(
                TimedBox(0.36, 0.45, 0.27, 0.08, "什锦炒虾仁", 0.99),
                TimedBox(0.43, 0.57, 0.15, 0.06, "525千卡", 0.96),
            ),
        )

        self.assertEqual(classify_frame_state(evidence), "title")
        boxes = authority_boxes_for_frame(evidence)
        self.assertEqual([box.text for box in boxes], ["什锦炒虾仁", "525千卡"])
        self.assertTrue(all(box.y < 0.7 for box in boxes))

    def test_f3_blank_food_frame_emits_no_boxes(self) -> None:
        evidence = FrameEvidence(
            frame_index=3,
            time_ms=116,
            local_boxes=(TimedBox(0.0, 0.815, 1.0, 0.185),),
            ocr_boxes=(),
        )

        self.assertEqual(classify_frame_state(evidence), "blank")
        self.assertEqual(authority_boxes_for_frame(evidence), [])

    def test_title_text_is_not_held_when_current_frame_has_no_local_title(self) -> None:
        evidence = FrameEvidence(
            frame_index=3,
            time_ms=116,
            local_boxes=(TimedBox(0.0, 0.815, 1.0, 0.185),),
            ocr_boxes=(
                TimedBox(0.36, 0.45, 0.27, 0.08, "什锦炒虾仁", 0.99),
                TimedBox(0.43, 0.57, 0.15, 0.06, "525千卡", 0.96),
            ),
        )

        self.assertEqual(authority_boxes_for_frame(evidence), [])

    def test_f119_hardsub_uses_text_evidence_not_giant_local_box(self) -> None:
        evidence = FrameEvidence(
            frame_index=119,
            time_ms=4594,
            local_boxes=(
                TimedBox(0.317, 0.815, 0.681, 0.185),  # rejected giant scan
                TimedBox(0.643, 0.95, 0.019, 0.011),  # DBNet glyph fragment
            ),
            ocr_boxes=(
                TimedBox(0.30, 0.925, 0.46, 0.055, "先把黄瓜去籽改刀成片状", 0.99),
            ),
        )

        self.assertEqual(classify_frame_state(evidence), "hardsub")
        boxes = authority_boxes_for_frame(evidence)
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0].text, "先把黄瓜去籽改刀成片状")
        self.assertLess(boxes[0].h, 0.10)
        self.assertLess(boxes[0].w * boxes[0].h, 0.08)

    def test_f758_dense_endcard_keeps_all_text_boxes(self) -> None:
        local = (
            TimedBox(0.03, 0.04, 0.05, 0.03),
            TimedBox(0.03, 0.11, 0.05, 0.02),
            TimedBox(0.05, 0.23, 0.25, 0.06),
            TimedBox(0.65, 0.24, 0.03, 0.02),
            TimedBox(0.09, 0.42, 0.03, 0.02),
            TimedBox(0.11, 0.46, 0.03, 0.02),
            TimedBox(0.08, 0.54, 0.04, 0.03),
        )
        texts = (
            "午餐",
            "2024-12-17",
            "蛋白质",
            "脂肪",
            "碳水化合物",
            "525千卡",
            "米饭",
            "花生油",
            "虾",
            "鸡蛋",
        )
        cloud = tuple(
            TimedBox(0.04, 0.04 + i * 0.08, 0.20, 0.04, text, 0.95)
            for i, text in enumerate(texts)
        )
        evidence = FrameEvidence(
            frame_index=758,
            time_ms=29261,
            local_boxes=local,
            ocr_boxes=cloud,
            timeline_ratio=1.0,
        )

        self.assertEqual(classify_frame_state(evidence), "endcard")
        boxes = authority_boxes_for_frame(evidence)
        self.assertEqual(len(boxes), len(texts))
        self.assertEqual({box.text for box in boxes}, set(texts))
        self.assertTrue(all(box.text for box in boxes))

    def test_dense_local_layout_creates_one_stable_endcard_segment(self) -> None:
        sparse = [{"x": 0.1, "y": 0.9, "w": 0.5, "h": 0.05}]
        dense = [
            {"x": 0.03, "y": 0.04, "w": 0.05, "h": 0.03},
            {"x": 0.03, "y": 0.11, "w": 0.05, "h": 0.02},
            {"x": 0.05, "y": 0.23, "w": 0.25, "h": 0.06},
            {"x": 0.65, "y": 0.24, "w": 0.03, "h": 0.02},
            {"x": 0.09, "y": 0.42, "w": 0.03, "h": 0.02},
            {"x": 0.11, "y": 0.54, "w": 0.03, "h": 0.02},
            {"x": 0.08, "y": 0.83, "w": 0.04, "h": 0.03},
        ]
        rows = [
            {"frame_index": 0, "time_ms": 0, "boxes": sparse},
            {"frame_index": 756, "time_ms": 29184, "boxes": dense},
            {"frame_index": 757, "time_ms": 29223, "boxes": dense},
            {"frame_index": 758, "time_ms": 29261, "boxes": dense},
        ]

        segments = detect_endcard_segments(rows, duration_ms=29261)

        self.assertEqual(
            segments,
            [
                EndcardSegment(
                    segment_id=0,
                    start_ms=29184,
                    end_ms=29262,
                    candidate_times_ms=(29223, 29261, 29184),
                )
            ],
        )

    def test_late_endcard_segment_extends_to_video_end_after_short_dense_run(
        self,
    ) -> None:
        """f1138 regression: high-res must cover the whole terminal endcard panel."""
        dense = [
            {"x": 0.03, "y": 0.04, "w": 0.05, "h": 0.03},
            {"x": 0.03, "y": 0.11, "w": 0.05, "h": 0.02},
            {"x": 0.05, "y": 0.23, "w": 0.25, "h": 0.06},
            {"x": 0.65, "y": 0.24, "w": 0.03, "h": 0.02},
            {"x": 0.09, "y": 0.42, "w": 0.03, "h": 0.02},
            {"x": 0.11, "y": 0.54, "w": 0.03, "h": 0.02},
            {"x": 0.08, "y": 0.83, "w": 0.04, "h": 0.03},
        ]
        sparse = [
            {"x": 0.03, "y": 0.44, "w": 0.12, "h": 0.02},
            {"x": 0.09, "y": 0.52, "w": 0.04, "h": 0.02},
            {"x": 0.14, "y": 0.26, "w": 0.04, "h": 0.02},
        ]
        rows = [
            {"frame_index": 1105, "time_ms": 36833, "boxes": dense},
            {"frame_index": 1106, "time_ms": 36867, "boxes": dense},
            {"frame_index": 1107, "time_ms": 36900, "boxes": dense},
            {"frame_index": 1108, "time_ms": 36933, "boxes": dense},
            {"frame_index": 1138, "time_ms": 37933, "boxes": sparse},
            {"frame_index": 1148, "time_ms": 38267, "boxes": sparse},
            {"frame_index": 1154, "time_ms": 38467, "boxes": sparse},
        ]
        segments = detect_endcard_segments(rows, duration_ms=38500)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].start_ms, 36833)
        self.assertEqual(segments[0].end_ms, 38501)


if __name__ == "__main__":
    unittest.main()
