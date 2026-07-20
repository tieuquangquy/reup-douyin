"""text_change_sampler: IoU gate keeps only frames with new text boxes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from src.media_pipeline.frame_sampling.local_text_detector import TextBox
from src.media_pipeline.frame_sampling.text_change_sampler import extract_text_change_keyframes


class _FakeCap:
    def __init__(self, frames: list[np.ndarray], fps: float = 30.0):
        self._frames = frames
        self._i = 0
        self._fps = fps
        self._opened = True

    def isOpened(self) -> bool:
        return self._opened

    def get(self, prop: int) -> float:
        import cv2

        if prop == cv2.CAP_PROP_FPS:
            return self._fps
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return float(len(self._frames))
        return 0.0

    def read(self):
        if self._i >= len(self._frames):
            return False, None
        frame = self._frames[self._i]
        self._i += 1
        return True, frame

    def release(self) -> None:
        self._opened = False


class _ScriptedDetector:
    """Returns predetermined boxes by absolute frame index (before stride)."""

    def __init__(self, boxes_by_frame: dict[int, list[TextBox]]):
        self.boxes_by_frame = boxes_by_frame
        self.calls = 0
        self._frame_i = 0

    def detect(self, _bgr: np.ndarray) -> list[TextBox]:
        # Caller only invokes detect on stride frames; we count detect calls.
        # Map call order → expected frame indices 0,5,10,...
        frame_idx = self.calls * 5
        self.calls += 1
        return list(self.boxes_by_frame.get(frame_idx, []))


class TextChangeSamplerTests(unittest.TestCase):
    def test_keeps_only_frames_with_new_text(self) -> None:
        # 20 frames @ 30fps; stride 5 → inspect 0,5,10,15
        solid = np.full((120, 160, 3), 40, dtype=np.uint8)
        frames = [solid.copy() for _ in range(20)]
        box_a = [TextBox(0.1, 0.8, 0.6, 0.08)]
        box_b = [TextBox(0.1, 0.2, 0.5, 0.06)]  # new location
        scripted = _ScriptedDetector(
            {
                0: box_a,
                5: box_a,  # same → skip
                10: box_b,  # new → keep
                15: box_b,  # same → skip
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "clip.mp4"
            video.write_bytes(b"fake")
            out = root / "frames"

            def fake_thumb(src, dest, **_kwargs):
                Path(dest).write_bytes(b"jpg")
                return Path(dest)

            from contextlib import contextmanager

            @contextmanager
            def fake_resolve(_src):
                yield video

            with patch(
                "src.media_pipeline.frame_sampling.text_change_sampler.resolve_video_source",
                side_effect=fake_resolve,
            ):
                with patch(
                    "src.media_pipeline.frame_sampling.text_change_sampler.extract_thumbnail_frame",
                    side_effect=fake_thumb,
                ):
                    with patch(
                        "src.media_pipeline.frame_sampling.text_change_sampler.cv2.VideoCapture",
                        return_value=_FakeCap(frames),
                    ):
                        with patch(
                            "src.media_pipeline.frame_sampling.text_change_sampler.probe_duration_ms",
                            return_value=400,
                        ):
                            with self.assertLogs(
                                "src.media_pipeline.frame_sampling.text_change_sampler",
                                level="INFO",
                            ) as log_cm:
                                got = extract_text_change_keyframes(
                                    video,
                                    out,
                                    frame_stride=5,
                                    min_keyframe_gap_ms=0,
                                    detector=scripted,  # type: ignore[arg-type]
                                )

            joined = "\n".join(log_cm.output)
            self.assertIn("[ONNX-Extract]", joined)
            self.assertIn("Phát hiện text mới", joined)
            # thumbnail + frame at t=0 (box_a) + frame at t=10 (box_b)
            self.assertGreaterEqual(len(got), 3)
            self.assertEqual(got[0].path.name, "thumbnail.jpg")
            key_times = [f.time_ms for f in got if f.path.name != "thumbnail.jpg"]
            self.assertIn(0, key_times)
            self.assertIn(333, key_times)  # frame 10 @ 30fps
            self.assertNotIn(166, key_times)  # frame 5 skipped
            self.assertTrue((out / "thumbnail.jpg").is_file())
            # Contract for Phase 2: path + time_ms
            for frame in got:
                self.assertTrue(hasattr(frame, "path") and hasattr(frame, "time_ms"))

    def test_min_keyframe_gap_skips_new_text_within_one_second(self) -> None:
        """Two IoU-new boxes 200ms apart → only first keyframe (+ thumbnail)."""
        from src.media_pipeline.frame_sampling.text_change_sampler import (
            DEFAULT_MIN_KEYFRAME_GAP_MS,
        )

        self.assertEqual(DEFAULT_MIN_KEYFRAME_GAP_MS, 1000)

        solid = np.full((120, 160, 3), 40, dtype=np.uint8)
        # Need frames through index 30 @ 30fps → t=1000ms for second keep
        frames = [solid.copy() for _ in range(40)]
        box_a = [TextBox(0.1, 0.8, 0.6, 0.08)]
        box_b = [TextBox(0.1, 0.2, 0.5, 0.06)]
        box_c = [TextBox(0.5, 0.5, 0.3, 0.05)]
        scripted = _ScriptedDetector(
            {
                0: box_a,
                5: box_b,  # new but t≈166ms < 1s → skip keep
                10: box_c,  # new but t≈333ms < 1s → skip keep
                30: box_b,  # t=1000ms → keep
                35: box_b,  # same → skip
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "clip.mp4"
            video.write_bytes(b"fake")
            out = root / "frames"

            def fake_thumb(src, dest, **_kwargs):
                Path(dest).write_bytes(b"jpg")
                return Path(dest)

            from contextlib import contextmanager

            @contextmanager
            def fake_resolve(_src):
                yield video

            with patch(
                "src.media_pipeline.frame_sampling.text_change_sampler.resolve_video_source",
                side_effect=fake_resolve,
            ):
                with patch(
                    "src.media_pipeline.frame_sampling.text_change_sampler.extract_thumbnail_frame",
                    side_effect=fake_thumb,
                ):
                    with patch(
                        "src.media_pipeline.frame_sampling.text_change_sampler.cv2.VideoCapture",
                        return_value=_FakeCap(frames),
                    ):
                        with patch(
                            "src.media_pipeline.frame_sampling.text_change_sampler.probe_duration_ms",
                            return_value=1200,
                        ):
                            got = extract_text_change_keyframes(
                                video,
                                out,
                                frame_stride=5,
                                detector=scripted,  # type: ignore[arg-type]
                            )

            key_times = [f.time_ms for f in got if f.path.name != "thumbnail.jpg"]
            self.assertIn(0, key_times)
            self.assertNotIn(166, key_times)
            self.assertNotIn(333, key_times)
            self.assertIn(1000, key_times)


class BackendResolveTests(unittest.TestCase):
    def test_default_is_text_onnx(self) -> None:
        from src.media_pipeline.frame_sampling.backend import resolve_frame_backend

        with patch.dict("os.environ", {}, clear=False):
            # Ensure unset
            import os

            os.environ.pop("OCR_FRAME_BACKEND", None)
            self.assertEqual(resolve_frame_backend(), "text_onnx")

    def test_ffmpeg_rollback(self) -> None:
        from src.media_pipeline.frame_sampling.backend import resolve_frame_backend

        self.assertEqual(resolve_frame_backend("ffmpeg_fps"), "ffmpeg_fps")


if __name__ == "__main__":
    unittest.main()
