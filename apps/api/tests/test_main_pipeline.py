"""End-to-end media pipeline orchestrator: order of phases + temp cleanup."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.main_pipeline import PipelineResult, run_pipeline
from src.media_pipeline.ocr_filtering.types import DetectedTextBox, FrameOcrFilterResult, OcrFilteringResult


class MainPipelineOrchestratorTests(unittest.TestCase):
    def test_run_pipeline_calls_phases_in_order_and_cleans_temp(self) -> None:
        call_order: list[str] = []
        temp_holder: dict[str, Path] = {}

        def fake_extract(video, output_dir, *, sample_fps=1, ffmpeg_binary="ffmpeg"):
            call_order.append("phase1")
            out = Path(output_dir)
            temp_holder["dir"] = out
            frame = out / "frame_000001.jpg"
            frame.write_bytes(b"jpg")
            frame_obj = MagicMock()
            frame_obj.path = frame
            frame_obj.time_ms = 0
            return [frame_obj]

        def fake_ocr(paths, *, ocr_provider=None, frame_time_ms=None, band_ratio=None, **_kwargs):
            call_order.append("phase2")
            self.assertEqual(len(paths), 1)
            self.assertEqual(frame_time_ms, [0])
            return OcrFilteringResult(
                frame_count=1,
                frames=[
                    FrameOcrFilterResult(
                        frame_id="frame_000001",
                        path=str(paths[0]),
                        time_ms=0,
                        frame_width=640,
                        frame_height=360,
                        boxes=[DetectedTextBox(0.1, 0.8, 0.7, 0.1, "你好", 0.9)],
                    )
                ],
                provider="mock",
            )

        def fake_translate(payload, **kwargs):
            call_order.append("phase25")
            self.assertIn("frames", payload)
            return {"0": "Xin chao"}

        def fake_render(source, output, overlays=None, **kwargs):
            call_order.append("phase34")
            self.assertEqual(len(overlays or []), 1)
            self.assertEqual((overlays or [])[0].text_vi, "Xin chao")
            self.assertNotIn("ocr_payload", kwargs)
            self.assertNotIn("vi_texts", kwargs)
            out = Path(output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"mp4")
            return out

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "in.mp4"
            video.write_bytes(b"fake-video")
            output = root / "out" / "final.mp4"
            with (
                patch(
                    "src.media_pipeline.hardsub_e2e.extract_phase1_frames",
                    side_effect=fake_extract,
                ),
                patch(
                    "src.media_pipeline.hardsub_e2e.run_ocr_filtering",
                    side_effect=fake_ocr,
                ),
                patch(
                    "src.media_pipeline.hardsub_e2e.translate_subtitles",
                    side_effect=fake_translate,
                ),
                patch(
                    "src.media_pipeline.hardsub_e2e.render_video_single_pass",
                    side_effect=fake_render,
                ),
                patch(
                    "src.media_pipeline.hardsub_e2e.build_default_ocr_provider",
                    return_value=MagicMock(provider_name="mock"),
                ),
                patch(
                    "src.media_pipeline.translator.resolve.resolve_translator_settings",
                    return_value=MagicMock(source="env"),
                ),
            ):
                result = run_pipeline(str(video), str(output), sample_fps=1, prefer_mock_ocr=True)

            self.assertEqual(call_order, ["phase1", "phase2", "phase25", "phase34"])
            self.assertTrue(Path(result.output_path).is_file())
            self.assertIsInstance(result, PipelineResult)
            self.assertIn("dir", temp_holder)
            self.assertFalse(temp_holder["dir"].exists())

    def test_run_pipeline_cleans_temp_even_on_failure(self) -> None:
        temp_holder: dict[str, Path] = {}

        def fake_extract(video, output_dir, *, sample_fps=1, ffmpeg_binary="ffmpeg"):
            out = Path(output_dir)
            temp_holder["dir"] = out
            out.mkdir(parents=True, exist_ok=True)
            (out / "frame_000001.jpg").write_bytes(b"x")
            frame_obj = MagicMock()
            frame_obj.path = out / "frame_000001.jpg"
            frame_obj.time_ms = 0
            return [frame_obj]

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "in.mp4"
            video.write_bytes(b"v")
            with (
                patch(
                    "src.media_pipeline.hardsub_e2e.extract_phase1_frames",
                    side_effect=fake_extract,
                ),
                patch(
                    "src.media_pipeline.hardsub_e2e.run_ocr_filtering",
                    side_effect=RuntimeError("ocr boom"),
                ),
                patch(
                    "src.media_pipeline.hardsub_e2e.build_default_ocr_provider",
                    return_value=MagicMock(),
                ),
            ):
                with self.assertRaises(RuntimeError):
                    run_pipeline(str(video), str(Path(tmp) / "out.mp4"), prefer_mock_ocr=True)

            self.assertFalse(temp_holder["dir"].exists())


if __name__ == "__main__":
    unittest.main()
