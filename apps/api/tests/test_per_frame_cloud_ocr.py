"""Tests for full per-frame Cloud OCR timeline (no hold-forward)."""

from __future__ import annotations

import unittest

from src.media_pipeline.ocr_filtering.box_timeline_tracker import TimedBox
from src.media_pipeline.ocr_filtering.clean_box_authority import filter_authority_boxes
from src.media_pipeline.ocr_filtering.per_frame_cloud_ocr import (
    build_frames_from_crop_results,
    merge_boxes_by_frame,
)
from src.media_pipeline.ocr_filtering.types import DetectedTextBox, FrameOcrDetection


class PerFrameCloudOcrTests(unittest.TestCase):
    def test_merge_boxes_by_frame_groups_hard_and_mid(self) -> None:
        jobs = [
            (0, 0, "hard", 0.667, 1.0),
            (0, 0, "mid", 0.22, 0.65),
            (1, 40, "hard", 0.667, 1.0),
        ]
        detections = [
            FrameOcrDetection(
                1080,
                1920,
                [
                    DetectedTextBox(
                        x=0.1,
                        y=0.5,
                        width=0.8,
                        height=0.2,
                        text="底部字幕",
                        confidence=0.95,
                    )
                ],
            ),
            FrameOcrDetection(
                1080,
                1920,
                [
                    DetectedTextBox(
                        x=0.2,
                        y=0.4,
                        width=0.6,
                        height=0.15,
                        text="标题",
                        confidence=0.9,
                    )
                ],
            ),
            FrameOcrDetection(1080, 1920, []),
        ]
        merged = merge_boxes_by_frame(list(zip(jobs, detections, strict=True)))
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["frame_index"], 0)
        self.assertEqual(len(merged[0]["raw_boxes"]), 2)
        self.assertEqual(merged[1]["frame_index"], 1)
        self.assertEqual(merged[1]["raw_boxes"], [])

    def test_build_frames_uses_ocr_on_same_frame_not_hold_forward(self) -> None:
        merged = [
            {
                "frame_index": 0,
                "time_ms": 0,
                "raw_boxes": [
                    TimedBox(0.1, 0.9, 0.8, 0.05, text="第一", confidence=0.95),
                ],
            },
            {
                "frame_index": 1,
                "time_ms": 40,
                "raw_boxes": [],
            },
        ]
        frames = build_frames_from_crop_results(merged, min_confidence=0.75)
        self.assertEqual(len(frames[0]["boxes"]), 1)
        self.assertEqual(frames[0]["boxes"][0]["text"], "第一")
        self.assertEqual(frames[0]["ocr_source_frame"], 0)
        self.assertEqual(frames[1]["boxes"], [])
        self.assertEqual(frames[1]["ocr_source_frame"], 1)

    def test_filter_authority_repairs_band_top_stuck_box(self) -> None:
        stuck = TimedBox(0.1, 0.68, 0.8, 0.08, text="吃到爽的同时还没有啥负担", confidence=0.99)
        kept = filter_authority_boxes([stuck])
        self.assertEqual(len(kept), 1)
        cy = float(kept[0].y) + float(kept[0].h) / 2.0
        self.assertGreaterEqual(cy, 0.85)


if __name__ == "__main__":
    unittest.main()
