"""Phase 1 OCR_FRAME_BACKEND=ske + hardsub crop-OCR wiring."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.backend import (
    BACKEND_SKE,
    extract_phase1_frames,
    resolve_frame_backend,
)
from src.media_pipeline.frame_sampling.smart_keyframe_extractor import BoundingBoxXYXY
from src.media_pipeline.hardsub_e2e import run_hardsub_phases_1_to_4
from src.media_pipeline.ocr_filtering.analyze_ocr import ske_grouped_to_ocr_payload


class ResolveSkeBackendTests(unittest.TestCase):
    def test_resolve_accepts_ske_aliases(self) -> None:
        self.assertEqual(resolve_frame_backend("ske"), BACKEND_SKE)
        self.assertEqual(resolve_frame_backend("smart_keyframe"), BACKEND_SKE)


class SkeGroupedPayloadTests(unittest.TestCase):
    def test_ske_grouped_to_ocr_payload_normalizes_boxes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            frame = np.full((100, 200, 3), 40, dtype=np.uint8)
            cv2.imwrite(str(root / "keyframe_000_f000030.jpg"), frame)
            summary = {
                "fps": 30.0,
                "keyframes": [
                    {
                        "frame_index": 30,
                        "approx_time_s": 1.0,
                        "frame_file": "keyframe_000_f000030.jpg",
                        "boxes": [{"x0": 20, "y0": 70, "x1": 180, "y1": 90}],
                    }
                ],
            }
            (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            grouped = {
                "00:01.000": [
                    {
                        "text": "减脂",
                        "box": [20.0, 70.0, 180.0, 70.0, 180.0, 90.0, 20.0, 90.0],
                    }
                ]
            }
            payload = ske_grouped_to_ocr_payload(grouped, ske_dir=root)
            self.assertEqual(payload["provider"], "ske_cloud_ocr")
            self.assertEqual(payload["frame_count"], 1)
            box = payload["frames"][0]["boxes"][0]
            self.assertEqual(box["text"], "减脂")
            self.assertAlmostEqual(box["x"], 0.10, places=2)
            self.assertAlmostEqual(box["y"], 0.70, places=2)
            self.assertAlmostEqual(box["width"], 0.80, places=2)
            self.assertAlmostEqual(box["height"], 0.20, places=2)
            self.assertEqual(payload["frames"][0]["time_ms"], 1000)


class ExtractSkePhase1Tests(unittest.TestCase):
    def test_ske_backend_writes_summary_and_returns_frames(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            video = root / "clip.mp4"
            video.write_bytes(b"fake")
            out = root / "frames"
            out.mkdir()
            frame = np.full((80, 120, 3), 90, dtype=np.uint8)
            kf = SimpleNamespace(
                frame_index=15,
                frame_bgr=frame,
                boxes=[BoundingBoxXYXY(10, 40, 100, 60)],
                enhanced_crops=[np.zeros((20, 40), dtype=np.uint8)],
            )

            with (
                patch(
                    "src.media_pipeline.frame_sampling.backend.resolve_frame_backend",
                    return_value=BACKEND_SKE,
                ),
                patch(
                    "src.media_pipeline.frame_sampling.ske_phase1.SmartKeyframeExtractor"
                ) as ext_cls,
                patch(
                    "src.media_pipeline.frame_sampling.ske_phase1.cv2.VideoCapture"
                ) as cap_cls,
            ):
                ext_cls.return_value.extract.return_value = [kf]
                cap = MagicMock()
                cap.isOpened.return_value = True
                cap.get.side_effect = lambda prop: {
                    5: 30.0,  # FPS
                    7: 900.0,  # FRAME_COUNT
                }.get(int(prop), 0.0)
                cap_cls.return_value = cap
                frames = extract_phase1_frames(video, out, backend=BACKEND_SKE)

            self.assertEqual(len(frames), 1)
            self.assertTrue(frames[0].path.is_file())
            self.assertEqual(frames[0].frame_index, 15)
            self.assertEqual(frames[0].time_ms, 500)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["keyframe_count"], 1)
            self.assertEqual(len(summary["keyframes"][0]["boxes"]), 1)

    def test_ske_empty_falls_back_to_text_onnx(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            video = root / "clip.mp4"
            video.write_bytes(b"fake")
            out = root / "frames"
            out.mkdir()
            fallback = [
                SimpleNamespace(path=out / "thumb.jpg", frame_index=0, time_ms=0)
            ]
            (out / "thumb.jpg").write_bytes(b"jpg")

            with (
                patch(
                    "src.media_pipeline.frame_sampling.backend.resolve_frame_backend",
                    return_value=BACKEND_SKE,
                ),
                patch(
                    "src.media_pipeline.frame_sampling.ske_phase1.extract_ske_phase1_frames",
                    return_value=[],
                ),
                patch(
                    "src.media_pipeline.frame_sampling.text_change_sampler.extract_text_change_keyframes",
                    return_value=fallback,
                ) as text_onnx,
            ):
                frames = extract_phase1_frames(video, out, backend=BACKEND_SKE)

            text_onnx.assert_called_once()
            self.assertEqual(frames, fallback)


class HardsubE2ESkeCropWiringTests(unittest.TestCase):
    def test_ske_summary_uses_crop_cloud_ocr_not_fullframe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            output = root / "cleaned.mp4"
            sample = root / "sample.jpg"
            frame = np.full((100, 200, 3), 40, dtype=np.uint8)
            cv2.imwrite(str(sample), frame)

            def fake_phase1(video, frames_dir, **_kwargs):
                frames_dir = Path(frames_dir)
                frame_path = frames_dir / "keyframe_000_f000030.jpg"
                cv2.imwrite(str(frame_path), frame)
                summary = {
                    "fps": 30.0,
                    "keyframes": [
                        {
                            "frame_index": 30,
                            "approx_time_s": 1.0,
                            "frame_file": frame_path.name,
                            "boxes": [{"x0": 20, "y0": 70, "x1": 180, "y1": 90}],
                        }
                    ],
                }
                (frames_dir / "summary.json").write_text(
                    json.dumps(summary), encoding="utf-8"
                )
                return [SimpleNamespace(path=frame_path, frame_index=30, time_ms=1000)]

            grouped = {
                "00:01.000": [
                    {
                        "text": "减脂餐",
                        "box": [20.0, 70.0, 180.0, 70.0, 180.0, 90.0, 20.0, 90.0],
                    }
                ]
            }

            with (
                patch(
                    "src.media_pipeline.hardsub_e2e.extract_phase1_frames",
                    side_effect=fake_phase1,
                ),
                patch(
                    "src.media_pipeline.ocr_filtering.ocr_quality_profile.is_best_ocr_profile",
                    return_value=False,
                ),
                patch(
                    "src.media_pipeline.ocr_filtering.analyze_ocr.CloudOCRAnalyzer"
                ) as analyzer_cls,
                patch(
                    "src.media_pipeline.hardsub_e2e.run_ocr_filtering"
                ) as legacy_ocr,
                patch(
                    "src.media_pipeline.hardsub_e2e.translate_subtitles",
                    return_value={"0#0": "Bua an giam beo"},
                ),
                patch(
                    "src.media_pipeline.translator.resolve.resolve_translator_settings",
                    return_value=SimpleNamespace(source="test"),
                ),
                patch(
                    "src.media_pipeline.hardsub_e2e.render_video_single_pass",
                    return_value=output,
                ),
            ):
                analyzer_cls.return_value.analyze_sync.return_value = grouped
                result = run_hardsub_phases_1_to_4(source, output)

            analyzer_cls.assert_called_once()
            analyzer_cls.return_value.analyze_sync.assert_called_once()
            legacy_ocr.assert_not_called()
            self.assertEqual(result.ocr_provider_name, "ske_cloud_ocr")
            self.assertEqual(result.ocr_payload["frames"][0]["boxes"][0]["text"], "减脂餐")


if __name__ == "__main__":
    unittest.main()
