"""Tests for bottom-band pixel change → OCR tick times."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.media_pipeline.ocr_filtering.bottom_band_change_ticks import (
    sample_bottom_band_change_times_ms,
)


def _write_synthetic_mp4(path: Path, frames: list[np.ndarray], fps: float = 10.0) -> None:
    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    assert writer.isOpened(), "VideoWriter failed"
    for fr in frames:
        writer.write(fr)
    writer.release()


class BottomBandChangeTicksTests(unittest.TestCase):
    def test_emits_tick_when_bottom_band_changes(self) -> None:
        # 1080p-ish short clip: stable top, caption strip changes at frame 5.
        w, h = 320, 180
        frames: list[np.ndarray] = []
        for i in range(12):
            fr = np.full((h, w, 3), 30, dtype=np.uint8)
            # mid content noise (ignored)
            fr[40:90, 80:240] = 90
            if i < 5:
                fr[150:170, 40:280] = 40  # dark band
            else:
                # bright "caption" bar appears
                fr[150:170, 40:280] = 220
            frames.append(fr)

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            _write_synthetic_mp4(video, frames, fps=10.0)
            times = sample_bottom_band_change_times_ms(
                video,
                y0_norm=0.75,
                frame_stride=1,
                min_gap_ms=0,
                change_mae_thresh=8.0,
                always_include_ends=True,
            )
        # t=0 always; change near frame 5 → 500ms
        self.assertIn(0, times)
        self.assertTrue(any(400 <= t <= 700 for t in times), times)

    def test_stable_band_does_not_spam_ticks(self) -> None:
        w, h = 160, 90
        frames = [np.full((h, w, 3), 50, dtype=np.uint8) for _ in range(10)]
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "stable.mp4"
            _write_synthetic_mp4(video, frames, fps=10.0)
            times = sample_bottom_band_change_times_ms(
                video,
                y0_norm=0.7,
                frame_stride=1,
                min_gap_ms=200,
                change_mae_thresh=8.0,
                always_include_ends=True,
            )
        # Only ends (0 + last), no mid spam
        self.assertEqual(times[0], 0)
        self.assertLessEqual(len(times), 3)
