"""Adapter: media_pipeline OCR payload → Pilot A FrameOcrResult / HardSubEvent."""

from __future__ import annotations

import unittest

from src.ocr_pipeline.media_ocr_adapter import (
    frame_results_from_ocr_payload,
    hardsub_events_from_ocr_payload,
)


class MediaOcrAdapterTests(unittest.TestCase):
    def test_frame_results_maps_boxes_and_time_ms(self) -> None:
        payload = {
            "frames": [
                {
                    "frame_id": "frame_000001",
                    "time_ms": 1000,
                    "frame_width": 640,
                    "frame_height": 360,
                    "boxes": [
                        {"x": 0.1, "y": 0.8, "width": 0.7, "height": 0.1, "text": "你好", "confidence": 0.95},
                    ],
                }
            ]
        }
        frames = frame_results_from_ocr_payload(payload)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].frame_time_ms, 1000)
        self.assertEqual(frames[0].frame_width, 640)
        self.assertEqual(frames[0].boxes[0].text, "你好")
        self.assertAlmostEqual(frames[0].boxes[0].y, 0.8)

    def test_hardsub_events_from_filtered_payload(self) -> None:
        payload = {
            "frames": [
                {
                    "time_ms": 0,
                    "frame_width": 1000,
                    "frame_height": 1000,
                    "boxes": [
                        {"x": 0.1, "y": 0.8, "width": 0.7, "height": 0.1, "text": "甲", "confidence": 0.9},
                    ],
                },
                {
                    "time_ms": 500,
                    "frame_width": 1000,
                    "frame_height": 1000,
                    "boxes": [
                        {"x": 0.1, "y": 0.82, "width": 0.6, "height": 0.08, "text": "乙", "confidence": 0.9},
                    ],
                },
            ]
        }
        events = hardsub_events_from_ocr_payload(payload, band_ratio=0.28)
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0].start_ms, 0)


if __name__ == "__main__":
    unittest.main()
