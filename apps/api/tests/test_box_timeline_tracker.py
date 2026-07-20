"""Tests for sparse OCR → dense hold-forward box timeline."""

from __future__ import annotations

import unittest

from src.media_pipeline.ocr_filtering.box_timeline_tracker import (
    TimedBox,
    OcrObservation,
    densify_hold_forward,
    match_boxes_by_iou,
    observations_from_ocr_payload,
)


class BoxTimelineTrackerTests(unittest.TestCase):
    def test_densify_hold_forward_uses_latest_ocr(self) -> None:
        obs = [
            OcrObservation(
                0,
                (TimedBox(0.1, 0.9, 0.5, 0.05, text="A", confidence=0.9),),
            ),
            OcrObservation(
                1000,
                (TimedBox(0.2, 0.9, 0.4, 0.05, text="B", confidence=0.8),),
            ),
        ]
        dense = densify_hold_forward(obs, [0, 400, 999, 1000, 1500])
        self.assertEqual(dense[0]["boxes"][0]["text"], "A")
        self.assertEqual(dense[0]["ocr_source_ms"], 0)
        self.assertEqual(dense[1]["boxes"][0]["text"], "A")
        self.assertEqual(dense[2]["boxes"][0]["text"], "A")
        self.assertEqual(dense[3]["boxes"][0]["text"], "B")
        self.assertEqual(dense[3]["ocr_source_ms"], 1000)
        self.assertEqual(dense[4]["boxes"][0]["text"], "B")

    def test_densify_before_first_observation_is_empty(self) -> None:
        obs = [
            OcrObservation(500, (TimedBox(0.1, 0.1, 0.2, 0.2, text="X", confidence=1.0),)),
        ]
        dense = densify_hold_forward(obs, [0, 100, 500])
        self.assertEqual(dense[0]["boxes"], [])
        self.assertIsNone(dense[0]["ocr_source_ms"])
        self.assertEqual(dense[1]["boxes"], [])
        self.assertEqual(len(dense[2]["boxes"]), 1)

    def test_densify_skips_empty_ocr_miss_ticks(self) -> None:
        """OCR empty at a tick must not wipe hold-forward (f436 n=0 bug)."""
        obs = [
            OcrObservation(
                0,
                (TimedBox(0.2, 0.92, 0.5, 0.04, text="A", confidence=0.9),),
            ),
            OcrObservation(1000, ()),  # miss
            OcrObservation(
                2000,
                (TimedBox(0.2, 0.92, 0.5, 0.04, text="B", confidence=0.9),),
            ),
        ]
        dense = densify_hold_forward(obs, [500, 1000, 1500, 2000], skip_empty=True)
        self.assertEqual(dense[0]["boxes"][0]["text"], "A")
        self.assertEqual(dense[1]["boxes"][0]["text"], "A")
        self.assertEqual(dense[1]["ocr_source_ms"], 0)
        self.assertEqual(dense[2]["boxes"][0]["text"], "A")
        self.assertEqual(dense[3]["boxes"][0]["text"], "B")

    def test_match_boxes_by_iou_one_to_one(self) -> None:
        prev = [
            TimedBox(0.1, 0.1, 0.2, 0.2, text="a"),
            TimedBox(0.6, 0.6, 0.2, 0.2, text="b"),
        ]
        curr = [
            TimedBox(0.11, 0.11, 0.2, 0.2, text="a2"),
            TimedBox(0.0, 0.8, 0.1, 0.1, text="new"),
        ]
        matches = match_boxes_by_iou(prev, curr, iou_thresh=0.3)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], 0)
        self.assertEqual(matches[0][1], 0)

    def test_observations_from_ocr_payload_filters_low_conf(self) -> None:
        frames = [
            {
                "time_ms": 0,
                "boxes": [
                    {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1, "text": "ok", "confidence": 0.9},
                    {"x": 0.1, "y": 0.5, "w": 0.2, "h": 0.1, "text": "no", "confidence": 0.1},
                    {"x": 0.1, "y": 0.7, "w": 0.2, "h": 0.1, "text": "", "confidence": 0.99},
                ],
            }
        ]
        obs = observations_from_ocr_payload(frames, min_confidence=0.3)
        self.assertEqual(len(obs), 1)
        self.assertEqual(len(obs[0].boxes), 1)
        self.assertEqual(obs[0].boxes[0].text, "ok")


if __name__ == "__main__":
    unittest.main()
