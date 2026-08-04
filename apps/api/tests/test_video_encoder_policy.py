from __future__ import annotations

import unittest

from src.media_pipeline.video_renderer.video_encoder import (
    EncoderProbeResult,
    ffmpeg_video_encode_args,
    preferred_hardware_encoders,
    select_video_encoder,
)


def _probe(available: set[str]):
    def run(encoder: str) -> EncoderProbeResult:
        return EncoderProbeResult(
            encoder=encoder,
            available=encoder in available,
            probe_kind="test",
            elapsed_ms=1,
            diagnostic=None if encoder in available else "unavailable",
        )

    return run


class EncoderSelectionTests(unittest.TestCase):
    def test_windows_auto_prefers_verified_nvenc(self) -> None:
        selection = select_video_encoder(
            "auto",
            platform_name="Windows",
            probe=_probe({"h264_nvenc", "h264_qsv", "libx264"}),
        )
        self.assertEqual(selection.selected_encoder, "h264_nvenc")
        self.assertTrue(selection.hardware)
        self.assertFalse(selection.fallback_used)

    def test_auto_uses_qsv_when_nvenc_probe_fails(self) -> None:
        selection = select_video_encoder(
            "auto",
            platform_name="Windows",
            probe=_probe({"h264_qsv", "libx264"}),
        )
        self.assertEqual(selection.selected_encoder, "h264_qsv")
        self.assertEqual(
            [probe.encoder for probe in selection.probes],
            ["h264_nvenc", "h264_qsv"],
        )

    def test_explicit_hardware_failure_falls_back_to_cpu(self) -> None:
        selection = select_video_encoder(
            "h264_nvenc",
            platform_name="Windows",
            probe=_probe({"libx264"}),
        )
        self.assertEqual(selection.selected_encoder, "libx264")
        self.assertTrue(selection.fallback_used)
        self.assertEqual(
            selection.fallback_reason,
            "requested_encoder_unavailable:h264_nvenc",
        )

    def test_mac_prefers_videotoolbox(self) -> None:
        self.assertEqual(
            preferred_hardware_encoders("Darwin"),
            ("h264_videotoolbox",),
        )


class EncoderArgumentsTests(unittest.TestCase):
    def test_nvenc_uses_quality_mode_and_yuv420p(self) -> None:
        args = ffmpeg_video_encode_args("h264_nvenc", width=1080, height=1920)
        self.assertIn("h264_nvenc", args)
        self.assertIn("-cq", args)
        self.assertIn("yuv420p", args)

    def test_cpu_fallback_is_reproducible(self) -> None:
        args = ffmpeg_video_encode_args("libx264", width=1080, height=1920)
        self.assertEqual(args[:2], ["-c:v", "libx264"])
        self.assertIn("-crf", args)
        self.assertIn("20", args)


if __name__ == "__main__":
    unittest.main()
