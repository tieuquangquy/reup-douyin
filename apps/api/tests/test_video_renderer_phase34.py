"""Phase 3+4 Single Render: one FFmpeg filtergraph (mask + VI + anti-hash)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.media_pipeline.video_renderer.filter_graph import (
    build_anti_detection_filters,
    build_single_render_filter,
    escape_drawtext,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment, overlays_from_ocr_payload
from src.media_pipeline.video_renderer.renderer import render_video_single_pass


class OverlayBuildTests(unittest.TestCase):
    def test_overlays_from_phase2_payload_one_segment_per_box(self) -> None:
        payload = {
            "frames": [
                {
                    "frame_id": "frame_000001",
                    "time_ms": 0,
                    "boxes": [
                        {"x": 0.10, "y": 0.80, "width": 0.30, "height": 0.08, "text": "甲"},
                        {"x": 0.40, "y": 0.82, "width": 0.40, "height": 0.08, "text": "乙"},
                    ],
                },
                {
                    "frame_id": "frame_000002",
                    "time_ms": 1000,
                    "boxes": [
                        {"x": 0.12, "y": 0.78, "width": 0.70, "height": 0.10, "text": "丙"},
                    ],
                },
            ]
        }
        vi = {"0#0": "Xin chao", "0#1": "The gioi", "1000#0": "Phu de dich"}
        overlays = overlays_from_ocr_payload(payload, vi, hold_ms=500, pad_x=0.0, pad_y=0.0)
        self.assertEqual(len(overlays), 3)
        self.assertEqual(overlays[0].text_vi, "Xin chao")
        self.assertAlmostEqual(overlays[0].x, 0.10, places=4)
        self.assertAlmostEqual(overlays[0].width, 0.30, places=4)
        self.assertEqual(overlays[1].text_vi, "The gioi")
        self.assertAlmostEqual(overlays[1].x, 0.40, places=4)
        self.assertEqual(overlays[0].start_ms, 0)
        self.assertEqual(overlays[0].end_ms, 1000)  # until next sample
        self.assertEqual(overlays[2].text_vi, "Phu de dich")
        self.assertEqual(overlays[2].end_ms, 1500)  # last sample + hold_ms


class FilterGraphTests(unittest.TestCase):
    def test_single_render_filter_has_three_layers(self) -> None:
        overlays = [
            OverlaySegment(
                start_ms=0,
                end_ms=1000,
                x=0.10,
                y=0.80,
                width=0.70,
                height=0.10,
                text_vi="Xin chao",
            )
        ]
        vf = build_single_render_filter(
            overlays,
            fontfile=Path("C:/Windows/Fonts/arial.ttf"),
            anti_seed=42,
            pad_x=0.0,
            pad_y=0.0,
            hold_ms=0,
            frame_width=1080,
            frame_height=1920,
        )
        self.assertIn("delogo=", vf)
        self.assertIn("drawtext=", vf)
        self.assertIn("enable=between(t\\,", vf)
        self.assertIn("eq=", vf)
        self.assertIn("noise=", vf)
        # delogo before drawtext before anti
        self.assertLess(vf.index("delogo="), vf.index("drawtext="))
        self.assertLess(vf.index("drawtext="), vf.index("eq="))
        self.assertLess(vf.index("eq="), vf.index("noise="))
        self.assertIn("text='Xin chao'", vf)
        self.assertNotIn("drawbox=", vf)

    def test_anti_detection_stays_in_one_to_two_percent(self) -> None:
        parts = build_anti_detection_filters(seed=7)
        self.assertEqual(len(parts), 2)
        eq = parts[0]
        # brightness absolute in [0.01, 0.02]
        self.assertRegex(eq, r"brightness=-?0\.0[12]\d*")
        self.assertRegex(eq, r"contrast=1\.0[12]\d*")
        self.assertRegex(eq, r"saturation=1\.0[12]\d*")

    def test_escape_drawtext_escapes_colon(self) -> None:
        self.assertIn(r"\:", escape_drawtext("a:b"))


class RenderInvokeTests(unittest.TestCase):
    def test_render_invokes_ffmpeg_once_with_filter_complex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "in.mp4"
            out = root / "out.mp4"
            src.write_bytes(b"fake")
            overlays = [
                OverlaySegment(0, 500, 0.1, 0.8, 0.7, 0.1, "Mock VI"),
            ]
            with patch.dict("os.environ", {"OCR_RENDER_BACKEND": "ffmpeg_delogo"}):
                with patch("src.media_pipeline.video_renderer.renderer.shutil.which", return_value="ffmpeg"):
                    with patch(
                        "src.media_pipeline.video_renderer.renderer.subprocess.Popen"
                    ) as popen:
                        proc = MagicMock()
                        proc.stderr = MagicMock()
                        proc.stderr.readline = MagicMock(side_effect=["frame=1\n", ""])
                        proc.wait.return_value = 0
                        proc.returncode = 0
                        popen.return_value = proc

                        def _wait() -> int:
                            out.write_bytes(b"mp4")
                            return 0

                        proc.wait.side_effect = _wait
                        with patch(
                            "src.media_pipeline.video_renderer.renderer.resolve_drawtext_font",
                            return_value=Path("C:/Windows/Fonts/arial.ttf"),
                        ):
                            result = render_video_single_pass(
                                src,
                                out,
                                overlays,
                                anti_seed=1,
                                frame_width=1080,
                                frame_height=1920,
                            )
            self.assertEqual(result, out)
            self.assertEqual(popen.call_count, 1)
            cmd = popen.call_args.args[0]
            self.assertIn("-filter_complex", cmd)
            self.assertEqual(cmd.count("-filter_complex"), 1)


if __name__ == "__main__":
    unittest.main()
