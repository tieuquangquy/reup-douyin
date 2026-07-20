"""Per-frame local text-box scan (detect-only; no Cloud OCR / blur)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.media_pipeline.frame_sampling.local_text_detector import TextBox
from src.media_pipeline.frame_sampling.per_frame_text_detect import (
    detect_text_boxes_every_frame,
    write_per_frame_boxes_json,
)


class _FakeCap:
    def __init__(self, frames: list[np.ndarray], fps: float = 10.0) -> None:
        self._frames = frames
        self._i = 0
        self._fps = fps

    def isOpened(self) -> bool:
        return True

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
        return None


class _ScriptedDetector:
    def __init__(self, by_index: dict[int, list[TextBox]]) -> None:
        self._by_index = by_index
        self.calls: list[int] = []

    def detect(self, frame_bgr: np.ndarray) -> list[TextBox]:
        idx = len(self.calls)
        self.calls.append(idx)
        return list(self._by_index.get(idx, []))


class PerFrameTextDetectTests(unittest.TestCase):
    def test_emits_boxes_for_every_frame_including_empty(self) -> None:
        solid = np.full((40, 60, 3), 30, dtype=np.uint8)
        frames = [solid.copy() for _ in range(5)]
        det = _ScriptedDetector(
            {
                0: [TextBox(0.1, 0.8, 0.5, 0.1)],
                2: [TextBox(0.2, 0.2, 0.3, 0.05), TextBox(0.6, 0.7, 0.2, 0.04)],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"fake")

            from contextlib import contextmanager

            @contextmanager
            def fake_resolve(_src):
                yield video

            with patch(
                "src.media_pipeline.frame_sampling.per_frame_text_detect.resolve_video_source",
                side_effect=fake_resolve,
            ):
                with patch(
                    "src.media_pipeline.frame_sampling.per_frame_text_detect.cv2.VideoCapture",
                    return_value=_FakeCap(frames, fps=10.0),
                ):
                    result = detect_text_boxes_every_frame(
                        video,
                        frame_stride=1,
                        detector=det,  # type: ignore[arg-type]
                    )

        self.assertEqual(result["detector"], "dbnet_onnx")
        self.assertEqual(result["stride"], 1)
        self.assertEqual(result["frame_count"], 5)
        self.assertEqual(len(result["frames"]), 5)
        self.assertEqual(det.calls, [0, 1, 2, 3, 4])

        f0 = result["frames"][0]
        self.assertEqual(f0["frame_index"], 0)
        self.assertEqual(f0["time_ms"], 0)
        self.assertEqual(f0["boxes"], [{"x": 0.1, "y": 0.8, "w": 0.5, "h": 0.1}])

        f1 = result["frames"][1]
        self.assertEqual(f1["time_ms"], 100)
        self.assertEqual(f1["boxes"], [])

        f2 = result["frames"][2]
        self.assertEqual(f2["time_ms"], 200)
        self.assertEqual(len(f2["boxes"]), 2)
        self.assertEqual(f2["boxes"][1], {"x": 0.6, "y": 0.7, "w": 0.2, "h": 0.04})

    def test_stride_skips_unevaluated_frames(self) -> None:
        solid = np.full((40, 60, 3), 30, dtype=np.uint8)
        frames = [solid.copy() for _ in range(6)]
        det = _ScriptedDetector({0: [TextBox(0.1, 0.1, 0.2, 0.2)]})

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"fake")

            from contextlib import contextmanager

            @contextmanager
            def fake_resolve(_src):
                yield video

            with patch(
                "src.media_pipeline.frame_sampling.per_frame_text_detect.resolve_video_source",
                side_effect=fake_resolve,
            ):
                with patch(
                    "src.media_pipeline.frame_sampling.per_frame_text_detect.cv2.VideoCapture",
                    return_value=_FakeCap(frames, fps=30.0),
                ):
                    result = detect_text_boxes_every_frame(
                        video,
                        frame_stride=2,
                        detector=det,  # type: ignore[arg-type]
                    )

        # Evaluated indices 0,2,4 → 3 detect calls; output only evaluated frames
        self.assertEqual(result["stride"], 2)
        self.assertEqual(len(result["frames"]), 3)
        self.assertEqual([f["frame_index"] for f in result["frames"]], [0, 2, 4])
        self.assertEqual(len(det.calls), 3)

    def test_write_json_roundtrip(self) -> None:
        payload = {
            "video": "x.mp4",
            "detector": "dbnet_onnx",
            "stride": 1,
            "frame_count": 1,
            "frames": [
                {
                    "frame_index": 0,
                    "time_ms": 0,
                    "boxes": [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "boxes.json"
            write_per_frame_boxes_json(payload, out)
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(loaded["frames"][0]["boxes"][0]["w"], 0.3)


if __name__ == "__main__":
    unittest.main()
