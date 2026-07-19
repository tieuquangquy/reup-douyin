"""Regression: OpenCV inpaint encode must not Broken-pipe without FFmpeg detail."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.media_pipeline.video_renderer.errors import VideoRendererError
from src.media_pipeline.video_renderer.inpaint_render import (
    _even_dimension,
    render_video_opencv_inpaint,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


class EvenDimensionTests(unittest.TestCase):
    def test_odd_dims_round_down_to_even(self) -> None:
        self.assertEqual(_even_dimension(1080), 1080)
        self.assertEqual(_even_dimension(1081), 1080)
        self.assertEqual(_even_dimension(1), 2)


class BrokenPipeSurfacesEncoderStderrTests(unittest.TestCase):
    def test_broken_pipe_includes_encoder_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.mp4"
            out = Path(tmp) / "out.mp4"
            src.write_bytes(b"fake")

            decoder = MagicMock()
            decoder.stdout = MagicMock()
            decoder.stdout.read = MagicMock(
                side_effect=[b"\x00" * (1080 * 1920 * 3), b""]
            )
            decoder.wait.return_value = 0
            decoder.stderr = MagicMock()
            decoder.stderr.read.return_value = b""

            encoder = MagicMock()
            encoder.stdin = MagicMock()
            encoder.stdin.write.side_effect = BrokenPipeError(32, "Broken pipe")
            encoder.stdin.close = MagicMock()
            encoder.wait.return_value = 1
            encoder.stderr = MagicMock()
            encoder.stderr.read = MagicMock(
                side_effect=[b"Error while opening encoder for output stream", b""]
            )
            decoder.stderr = MagicMock()
            decoder.stderr.read = MagicMock(return_value=b"")

            pops = [decoder, encoder]

            def _popen(*_a, **_k):
                return pops.pop(0)

            with (
                patch("src.media_pipeline.video_renderer.inpaint_render.shutil.which", return_value="ffmpeg"),
                patch(
                    "src.media_pipeline.video_renderer.renderer.probe_video_frame_size",
                    return_value=(1080, 1920),
                ),
                patch(
                    "src.media_pipeline.video_renderer.renderer.probe_video_duration_ms",
                    return_value=0,
                ),
                patch(
                    "src.media_pipeline.video_renderer.inpaint_render._probe_fps",
                    return_value=25.0,
                ),
                patch(
                    "src.media_pipeline.video_renderer.inpaint_render.resolve_drawtext_font",
                    return_value=Path(r"C:\Windows\Fonts\arial.ttf"),
                ),
                patch(
                    "src.media_pipeline.video_renderer.inpaint_render.process_frame_bgr",
                    side_effect=lambda frame, *_a, **_k: frame,
                ),
                patch("src.media_pipeline.video_renderer.inpaint_render.subprocess.Popen", side_effect=_popen),
            ):
                with self.assertRaises(VideoRendererError) as ctx:
                    render_video_opencv_inpaint(
                        src,
                        out,
                        [OverlaySegment(0, 500, 0.1, 0.8, 0.7, 0.1, "VI")],
                        progress=False,
                        frame_width=1080,
                        frame_height=1920,
                    )
            msg = str(ctx.exception.message)
            self.assertIn("Broken pipe", msg)
            self.assertIn("Error while opening encoder", msg)


if __name__ == "__main__":
    unittest.main()
