"""Tests for MagicVideoCleaner (Step 4: ROI inpaint + ASS)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.media_pipeline.video_renderer.video_cleaner_and_sub import (
    MagicVideoCleaner,
    inpaint_frame_rois,
    parse_step3_events,
    write_ass,
)


def _write_dummy_video(path: Path, *, frames: int = 15, fps: float = 10.0, size=(160, 120)) -> None:
    w, h = size
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (w, h),
    )
    assert writer.isOpened(), "VideoWriter failed to open"
    for i in range(frames):
        frame = np.full((h, w, 3), 40, dtype=np.uint8)
        # White hardsub-like bar near bottom for first half of clip
        if i < frames // 2:
            frame[90:110, 20:140] = 240
        writer.write(frame)
    writer.release()


class ParseStep3Tests(unittest.TestCase):
    def test_parse_hold_duration_and_pixel_quad(self) -> None:
        step3 = {
            "00:01.000": [
                {
                    "original_box_coords": [10.0, 20.0, 50.0, 20.0, 50.0, 40.0, 10.0, 40.0],
                    "original_text": "加盐",
                    "vietnamese_text": "Thêm muối",
                }
            ]
        }
        events = parse_step3_events(step3, default_hold_s=2.0, video_duration_s=10.0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].start_ms, 1000)
        self.assertEqual(events[0].end_ms, 3000)
        self.assertEqual(events[0].xyxy, (10, 20, 50, 40))
        self.assertEqual(events[0].vietnamese_text, "Thêm muối")

    def test_hold_capped_not_stretched_to_next_timestamp(self) -> None:
        """Regression: 02.5s event must not stick until 10.3s (wrong VI on broccoli)."""
        step3 = {
            "00:02.500": [
                {
                    "original_box_coords": [10.0, 20.0, 50.0, 20.0, 50.0, 40.0, 10.0, 40.0],
                    "original_text": "加盐",
                    "vietnamese_text": "Thêm muối",
                }
            ],
            "00:10.333": [
                {
                    "original_box_coords": [10.0, 20.0, 50.0, 20.0, 50.0, 40.0, 10.0, 40.0],
                    "original_text": "花",
                    "vietnamese_text": "Bông cải",
                }
            ],
        }
        events = parse_step3_events(step3, default_hold_s=2.0, video_duration_s=30.0)
        first = next(e for e in events if e.vietnamese_text == "Thêm muối")
        self.assertEqual(first.start_ms, 2500)
        self.assertEqual(first.end_ms, 4500)  # min(10333, 2500+2000)
        self.assertLess(first.end_ms, 10000)


class WriteAssTests(unittest.TestCase):
    def test_ass_has_style_outline_shadow_and_timing(self) -> None:
        step3 = {
            "00:00.500": [
                {
                    "original_box_coords": [10.0, 80.0, 100.0, 80.0, 100.0, 100.0, 10.0, 100.0],
                    "original_text": "减脂",
                    "vietnamese_text": "Giảm béo",
                }
            ]
        }
        events = parse_step3_events(step3, default_hold_s=2.0, video_duration_s=5.0)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "vietnamese_sub.ass"
            write_ass(events, video_w=200, video_h=120, path=path)
            text = path.read_text(encoding="utf-8")
        self.assertIn("Style:", text)
        # V4+ Style positional: BorderStyle, Outline, Shadow, Alignment → 1,2,1,2
        self.assertRegex(text, r"Style:\s*ReupVI,.*,1,2,1,2,")
        self.assertIn("&H00FFFFFF", text)
        self.assertIn("Dialogue:", text)
        self.assertIn("0:00:00.50", text)
        self.assertIn("0:00:02.50", text)
        self.assertIn("Giảm béo", text)
        self.assertIn("\\pos(", text)

    def test_missing_vi_uses_ellipsis_not_crash(self) -> None:
        step3 = {
            "00:01.000": [
                {
                    "original_box_coords": [1.0, 2.0, 3.0, 2.0, 3.0, 4.0, 1.0, 4.0],
                    "original_text": "加盐",
                    "vietnamese_text": "",
                }
            ]
        }
        events = parse_step3_events(step3, default_hold_s=1.0, video_duration_s=3.0)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "out.ass"
            write_ass(events, video_w=100, video_h=100, path=path)
            text = path.read_text(encoding="utf-8")
        # Empty / placeholder VI must not appear as Dialogue
        self.assertNotIn("Dialogue:", text)

    def test_skips_dry_vi_prefix_in_ass(self) -> None:
        step3 = {
            "00:01.000": [
                {
                    "original_box_coords": [10.0, 80.0, 100.0, 80.0, 100.0, 100.0, 10.0, 100.0],
                    "original_text": "花",
                    "vietnamese_text": "[vi]花",
                },
                {
                    "original_box_coords": [10.0, 40.0, 80.0, 40.0, 80.0, 60.0, 10.0, 60.0],
                    "original_text": "加盐",
                    "vietnamese_text": "Thêm muối",
                },
            ]
        }
        events = parse_step3_events(step3, default_hold_s=1.0, video_duration_s=5.0)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "out.ass"
            write_ass(events, video_w=200, video_h=120, path=path)
            text = path.read_text(encoding="utf-8")
        self.assertIn("Thêm muối", text)
        self.assertNotIn("[vi]", text)
        self.assertEqual(text.count("Dialogue:"), 1)


class RoiInpaintTests(unittest.TestCase):
    def test_inpaint_removes_bright_bar_toward_background(self) -> None:
        h, w = 120, 160
        frame = np.full((h, w, 3), 40, dtype=np.uint8)
        frame[90:110, 20:140] = 240
        before = float(frame[90:110, 20:140].mean())
        cleaned = inpaint_frame_rois(frame, [(20, 90, 140, 110)])
        after = float(cleaned[90:110, 20:140].mean())
        self.assertLess(after, before - 50)
        self.assertLess(after, 120)


class ProcessOutputsTests(unittest.TestCase):
    def test_process_writes_cleaned_mp4_and_ass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            video = root / "src.mp4"
            _write_dummy_video(video)
            step3 = {
                "00:00.000": [
                    {
                        "original_box_coords": [
                            20.0,
                            90.0,
                            140.0,
                            90.0,
                            140.0,
                            110.0,
                            20.0,
                            110.0,
                        ],
                        "original_text": "加盐",
                        "vietnamese_text": "Thêm muối",
                    }
                ]
            }
            cleaner = MagicVideoCleaner(default_hold_s=0.5)
            cleaned, ass = cleaner.process(video, step3, root / "out")
            self.assertTrue(cleaned.is_file())
            self.assertTrue(ass.is_file())
            self.assertEqual(cleaned.name, "cleaned_video.mp4")
            self.assertEqual(ass.name, "vietnamese_sub.ass")
            self.assertGreater(cleaned.stat().st_size, 0)
            self.assertIn("Thêm muối", ass.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
