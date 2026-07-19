"""0-frame / partial-pipe reads must not produce silent 0s cleaned videos."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.media_pipeline.video_renderer.errors import VideoRendererError
from src.media_pipeline.video_renderer.inpaint_render import (
    read_exact_bytes,
    render_video_opencv_inpaint,
)
from src.media_pipeline.video_renderer.overlays import OverlaySegment


class ReadExactBytesTests(unittest.TestCase):
    def test_assembles_partial_reads_into_full_frame(self) -> None:
        # Simulate Windows pipe returning smaller chunks than requested.
        stream = io.BytesIO(b"ABCDEFGHIJKLMNOP")
        raw_read = stream.read

        def _chunked(n: int = -1) -> bytes:
            if n is None or n < 0:
                return raw_read()
            return raw_read(min(3, n))

        stream.read = _chunked  # type: ignore[method-assign]
        got = read_exact_bytes(stream, 10)
        self.assertEqual(got, b"ABCDEFGHIJ")
        self.assertEqual(len(got), 10)

    def test_short_eof_returns_partial(self) -> None:
        stream = io.BytesIO(b"AB")
        got = read_exact_bytes(stream, 8)
        self.assertEqual(got, b"AB")


class ZeroFrameEncodeRejectedTests(unittest.TestCase):
    def test_zero_frames_raises_instead_of_silent_0s_mp4(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.mp4"
            out = Path(tmp) / "out.mp4"
            src.write_bytes(b"fake")

            decoder = MagicMock()
            decoder.stdout = MagicMock()
            decoder.stdout.read = MagicMock(return_value=b"")
            decoder.wait.return_value = 0
            decoder.stderr = MagicMock()
            decoder.stderr.read = MagicMock(return_value=b"")

            encoder = MagicMock()
            encoder.stdin = MagicMock()
            encoder.wait.return_value = 0
            encoder.stderr = MagicMock()
            encoder.stderr.read = MagicMock(return_value=b"")

            pops = [decoder, encoder]

            def _popen(*_a, **_k):
                return pops.pop(0)

            with (
                patch(
                    "src.media_pipeline.video_renderer.inpaint_render.shutil.which",
                    return_value="ffmpeg",
                ),
                patch(
                    "src.media_pipeline.video_renderer.renderer.probe_video_frame_size",
                    return_value=(1080, 1920),
                ),
                patch(
                    "src.media_pipeline.video_renderer.renderer.probe_video_duration_ms",
                    return_value=5000,
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
                    "src.media_pipeline.video_renderer.inpaint_render.subprocess.Popen",
                    side_effect=_popen,
                ),
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
            self.assertIn("0 frames", str(ctx.exception.message))


if __name__ == "__main__":
    unittest.main()
