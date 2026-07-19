"""Duration parity: encode fps + mux must not stretch a 29s source to ~33s."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.media_pipeline.video_renderer.inpaint_render import (
    _parse_stream_fps,
    _probe_fps,
    mux_output_trim_args,
)


class ProbeFpsTests(unittest.TestCase):
    def test_prefers_r_frame_rate_over_lower_avg(self) -> None:
        # Douyin-like: avg ~26.something, nominal r=30 → must encode at 30.
        stream = {"avg_frame_rate": "26/1", "r_frame_rate": "30/1"}
        self.assertEqual(_parse_stream_fps(stream), 30.0)

    def test_falls_back_to_avg_when_r_missing(self) -> None:
        stream = {"avg_frame_rate": "25/1", "r_frame_rate": "0/0"}
        self.assertEqual(_parse_stream_fps(stream), 25.0)

    def test_probe_fps_uses_r_frame_rate_from_ffprobe_json(self) -> None:
        payload = {"streams": [{"avg_frame_rate": "26100/1000", "r_frame_rate": "30/1"}]}
        completed = MagicMock(returncode=0, stdout=json.dumps(payload))
        with (
            patch(
                "src.media_pipeline.video_renderer.renderer._resolve_ffprobe_binary",
                return_value="ffprobe",
            ),
            patch(
                "src.media_pipeline.video_renderer.inpaint_render.subprocess.run",
                return_value=completed,
            ),
        ):
            self.assertEqual(_probe_fps(Path("x.mp4"), ffmpeg_binary="ffmpeg"), 30.0)


class MuxTrimTests(unittest.TestCase):
    def test_trim_args_match_source_duration_seconds(self) -> None:
        # 29.0s source must cap mux so container cannot grow to ~33s via long audio.
        args = mux_output_trim_args(29_000)
        self.assertEqual(args, ["-t", "29.000"])

    def test_no_trim_when_duration_unknown(self) -> None:
        self.assertEqual(mux_output_trim_args(0), [])
        self.assertEqual(mux_output_trim_args(None), [])


if __name__ == "__main__":
    unittest.main()
