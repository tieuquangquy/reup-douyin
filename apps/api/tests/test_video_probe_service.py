"""VideoProbeService must parse real ffprobe JSON into technical fields."""

from __future__ import annotations

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

    def test_probe_uses_ffprobe_when_available(self) -> None:
        storage = MagicMock()
        storage.metadata.return_value = SimpleNamespace(
            exists=True,
            size_bytes=1200,
            absolute_path=r"C:\tmp\final.mp4",
        )
        storage.resolve.return_value = SimpleNamespace(absolute_path=r"C:\tmp\final.mp4")
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
        storage.metadata.return_value = SimpleNamespace(
            exists=True,
            size_bytes=99,
            absolute_path=r"C:\tmp\final.mp4",
        )
        storage.resolve.return_value = SimpleNamespace(absolute_path=r"C:\tmp\final.mp4")
        service = VideoProbeService(storage)
        with patch.object(service, "_run_ffprobe", side_effect=FileNotFoundError("ffprobe")):
            probe = service.probe("workspace/renders/final.mp4")
        self.assertIsNone(probe.width)
        self.assertEqual(probe.raw.get("probe_strategy"), "storage_metadata_fallback")
        self.assertEqual(probe.raw.get("size_bytes"), 99)


if __name__ == "__main__":
    unittest.main()
