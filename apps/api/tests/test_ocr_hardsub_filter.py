"""Hard-sub filter + event grouping unit tests."""

from __future__ import annotations

import unittest

from src.ocr_pipeline.hardsub_filter import (
    filter_hard_sub_boxes,
    group_hard_sub_events,
    is_in_hard_sub_band,
    stable_hard_sub_band,
)
from src.ocr_pipeline.types import FrameOcrResult, OcrBox


class HardSubFilterTests(unittest.TestCase):
    def test_bottom_band_accepted_top_rejected(self) -> None:
        bottom = OcrBox(x=0.1, y=0.8, width=0.8, height=0.1, text="sub", confidence=0.9)
        top = OcrBox(x=0.1, y=0.1, width=0.3, height=0.05, text="logo", confidence=0.9)
        self.assertTrue(is_in_hard_sub_band(bottom))
        self.assertFalse(is_in_hard_sub_band(top))
        filtered = filter_hard_sub_boxes([bottom, top])
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].text, "sub")

    def test_group_events_merges_nearby_samples(self) -> None:
        frames = [
            FrameOcrResult(
                frame_time_ms=0,
                frame_width=1080,
                frame_height=1920,
                boxes=[OcrBox(0.1, 0.8, 0.8, 0.1, "一", 0.9)],
            ),
            FrameOcrResult(
                frame_time_ms=500,
                frame_width=1080,
                frame_height=1920,
                boxes=[OcrBox(0.1, 0.81, 0.8, 0.1, "二", 0.9)],
            ),
            FrameOcrResult(
                frame_time_ms=2000,
                frame_width=1080,
                frame_height=1920,
                boxes=[OcrBox(0.1, 0.8, 0.8, 0.1, "三", 0.9)],
            ),
        ]
        events = group_hard_sub_events(frames, min_stable_samples=2, gap_ms=800)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].start_ms, 0)
        self.assertEqual(events[0].end_ms, 500)
        self.assertFalse(events[0].unstable)
        self.assertTrue(events[1].unstable)

    def test_stable_band_covers_union(self) -> None:
        frames = [
            FrameOcrResult(0, 1080, 1920, [OcrBox(0.1, 0.75, 0.8, 0.1, "a", 0.9)]),
            FrameOcrResult(500, 1080, 1920, [OcrBox(0.1, 0.78, 0.8, 0.12, "b", 0.9)]),
        ]
        events = group_hard_sub_events(frames, min_stable_samples=1)
        x, y, w, h = stable_hard_sub_band(events)
        self.assertEqual(x, 0.0)
        self.assertEqual(w, 1.0)
        self.assertGreaterEqual(y, 0.7)
        self.assertGreater(h, 0.1)


if __name__ == "__main__":
    unittest.main()
