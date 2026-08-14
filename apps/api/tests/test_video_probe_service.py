"""VideoProbeService must parse real ffprobe JSON into technical fields."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.render_pipeline.services.video_probe_service import VideoProbeService, parse_ffprobe_payload


class VideoProbeServiceTests(unittest.TestCase):
    def test_parse_ffprobe_payload_reads_video_audio_and_duration(self) -> None:
        payload = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1080,
                    "height": 1920,
                    "avg_frame_rate": "30/1",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                },
            ],
            "format": {"duration": "72.4"},
        }
        probe = parse_ffprobe_payload(payload)
        self.assertEqual(probe.width, 1080)
        self.assertEqual(probe.height, 1920)
        self.assertEqual(probe.fps, 30.0)
        self.assertEqual(probe.duration_seconds, 72.4)
        self.assertEqual(probe.video_codec, "h264")
        self.assertEqual(probe.audio_codec, "aac")
        self.assertEqual(probe.raw.get("probe_strategy"), "ffprobe")
        self.assertEqual(probe.raw.get("video_stream_count"), 1)
        self.assertEqual(probe.raw.get("audio_stream_count"), 1)

    def test_probe_uses_ffprobe_when_available(self) -> None:
        storage = MagicMock()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        media_path = Path(temp_dir.name) / "final.mp4"
        media_path.write_bytes(b"probe-fixture")
        storage.metadata.return_value = SimpleNamespace(
            exists=True,
            size_bytes=1200,
            absolute_path=str(media_path),
        )
        storage.resolve.return_value = SimpleNamespace(absolute_path=str(media_path))
        service = VideoProbeService(storage)
        payload = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 720,
                    "height": 1280,
                    "avg_frame_rate": "25/1",
                }
            ],
            "format": {"duration": "10"},
        }
        with patch.object(service, "_run_ffprobe", return_value=payload) as run:
            probe = service.probe("workspace/renders/final.mp4")
        run.assert_called_once()
        self.assertEqual(probe.width, 720)
        self.assertEqual(probe.height, 1280)
        self.assertEqual(probe.fps, 25.0)
        self.assertEqual(probe.duration_seconds, 10.0)

    def test_probe_falls_back_when_ffprobe_unavailable(self) -> None:
        storage = MagicMock()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        media_path = Path(temp_dir.name) / "final.mp4"
        media_path.write_bytes(b"probe-fixture")
        storage.metadata.return_value = SimpleNamespace(
            exists=True,
            size_bytes=99,
            absolute_path=str(media_path),
        )
        storage.resolve.return_value = SimpleNamespace(absolute_path=str(media_path))
        service = VideoProbeService(storage)
        with patch.object(service, "_run_ffprobe", side_effect=FileNotFoundError("ffprobe")):
            probe = service.probe("workspace/renders/final.mp4")
        self.assertIsNone(probe.width)
        self.assertEqual(probe.raw.get("probe_strategy"), "storage_metadata_fallback")
        self.assertEqual(probe.raw.get("size_bytes"), 99)

    def test_run_ffprobe_uses_argument_list_for_windows_paths_and_timeout(self) -> None:
        storage = MagicMock()
        binary = r"C:\Program Files\ffmpeg\bin\ffprobe.exe"
        media_path = Path(r"C:\Video Files\source clip.mp4")
        service = VideoProbeService(
            storage,
            ffprobe_binary=binary,
            timeout_seconds=7.5,
        )
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "video",
                            "codec_name": "h264",
                            "width": 1080,
                            "height": 1920,
                        }
                    ],
                    "format": {"duration": "1.0"},
                }
            ),
            stderr="",
        )

        with (
            patch(
                "src.render_pipeline.services.video_probe_service.shutil.which",
                return_value=None,
            ),
            patch(
                "src.render_pipeline.services.video_probe_service.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            payload = service._run_ffprobe(media_path)

        self.assertEqual(payload["format"]["duration"], "1.0")
        command = run.call_args.args[0]
        self.assertIsInstance(command, list)
        self.assertEqual(command[0], binary)
        self.assertEqual(command[-1], str(media_path))
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertEqual(run.call_args.kwargs["timeout"], 7.5)


if __name__ == "__main__":
    unittest.main()
