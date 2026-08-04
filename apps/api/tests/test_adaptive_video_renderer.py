from __future__ import annotations

import unittest
import hashlib
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from src.media_pipeline.video_renderer.adaptive_video import (
    AdaptiveVideoRenderError,
    active_tracks_for_frame,
    build_audio_mux_command,
    execute_mux_with_fallback,
    resolve_background_gain,
    resolve_narration_atempo,
    should_seed_reference_plate,
    validate_narration_file_authority,
    validate_adaptive_render_contract,
)


class AdaptiveVideoContractTests(unittest.TestCase):
    def test_background_gain_prefers_audio_authority_over_global_default(self) -> None:
        contract = {
            "authorities": {"audio": {"background_gain": 1.0}}
        }

        self.assertEqual(resolve_background_gain(contract), 1.0)

    def test_narration_atempo_fits_sub_percent_overrun(self) -> None:
        ratio = resolve_narration_atempo(73.0, 72.866667)
        self.assertGreater(ratio, 1.0)
        self.assertLess(ratio, 1.01)

    def test_narration_atempo_keeps_small_probe_rounding_at_unity(self) -> None:
        self.assertEqual(resolve_narration_atempo(73.000001, 73.0), 1.0)

    def test_short_opening_overlay_uses_bounded_spatial_fallback(self) -> None:
        policy = {
            "render_policy": {
                "cover": {"mask_mode": "stylized_components"}
            }
        }
        self.assertFalse(
            should_seed_reference_plate(
                {**policy, "start_frame": 0, "end_frame": 3}
            )
        )
        self.assertTrue(
            should_seed_reference_plate(
                {**policy, "start_frame": 10, "end_frame": 30}
            )
        )
        approved = {
            "render_policy": {
                "cover": {"mask_mode": "stylized_components"},
                "context": {"short_intro_reference_plate_approved": True},
            },
            "start_frame": 0,
            "end_frame": 3,
        }
        self.assertTrue(should_seed_reference_plate(approved))

    def test_activation_uses_frame_authority_not_nominal_timestamp(self) -> None:
        contract = {
            "render_tracks": [
                {"text_id": "a", "start_frame": 2, "end_frame": 4},
                {"text_id": "b", "start_frame": 5, "end_frame": 7},
            ]
        }
        self.assertEqual(
            [row["text_id"] for row in active_tracks_for_frame(contract, 4)], ["a"]
        )
        self.assertEqual(
            [row["text_id"] for row in active_tracks_for_frame(contract, 5)], ["b"]
        )

    def test_vfr_contract_requires_pts_map(self) -> None:
        contract = {
            "status": "READY_FOR_PHASE4",
            "authorities": {"timebase": {"mode": "VFR", "status": "PTS_RENDER_REQUIRED"}},
            "render_tracks": [],
        }
        with self.assertRaises(AdaptiveVideoRenderError):
            validate_adaptive_render_contract(contract, visual_preview=True)

    def test_visual_preview_allows_source_audio_but_final_requires_tts(self) -> None:
        contract = {
            "status": "READY_FOR_PHASE4",
            "authorities": {
                "timebase": {"mode": "VFR", "status": "READY_WITH_PTS_MAP"},
                "audio": {"status": "VISUAL_PREVIEW_ONLY", "strategy": "source_passthrough"},
            },
            "render_tracks": [],
        }
        validate_adaptive_render_contract(contract, visual_preview=True)
        with self.assertRaises(AdaptiveVideoRenderError):
            validate_adaptive_render_contract(contract, visual_preview=False)

    def test_mux_command_uses_explicit_audio_authority(self) -> None:
        command = build_audio_mux_command(
            video_only=Path("video_only.mp4"),
            audio_source=Path("joined.wav"),
            output=Path("final.mp4"),
            duration_seconds=12.5,
            ffmpeg_binary="ffmpeg",
            audio_filter_args=["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"],
        )
        self.assertIn("joined.wav", [str(value) for value in command])
        self.assertIn("-t", command)
        self.assertNotIn("-shortest", command)
        self.assertIn("-af", command)
        self.assertTrue(any("loudnorm" in str(value) for value in command))

    def test_mux_command_can_encode_lossless_intermediate_with_vfr_passthrough(self) -> None:
        command = build_audio_mux_command(
            video_only=Path("video_only.mkv"),
            audio_source=Path("joined.wav"),
            output=Path("final.mp4"),
            duration_seconds=12.5,
            ffmpeg_binary="ffmpeg",
            video_codec_args=["-c:v", "h264_nvenc", "-preset", "p5"],
        )
        self.assertIn("h264_nvenc", command)
        self.assertIn("-fps_mode:v", command)
        self.assertIn("passthrough", command)
        self.assertNotIn("copy", command)

    def test_mux_command_preserves_explicit_color_authority(self) -> None:
        command = build_audio_mux_command(
            video_only=Path("video_only.mkv"),
            audio_source=Path("joined.wav"),
            output=Path("preview.mp4"),
            duration_seconds=1.0,
            ffmpeg_binary="ffmpeg",
            color_metadata={"color_range": "tv", "color_space": "bt709"},
        )
        self.assertEqual(command[command.index("-color_range") + 1], "tv")
        self.assertEqual(command[command.index("-colorspace") + 1], "bt709")
        self.assertEqual(
            command[command.index("-bsf:v") + 1],
            "h264_metadata=video_full_range_flag=0",
        )

    def test_hardware_runtime_failure_retries_same_intermediate_with_cpu(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "video.mkv"
            audio = root / "audio.wav"
            output = root / "final.mp4"
            video.write_bytes(b"lossless")
            audio.write_bytes(b"audio")
            commands: list[list[str]] = []

            def run(command, **_kwargs):
                commands.append([str(value) for value in command])
                if len(commands) == 1:
                    output.write_bytes(b"partial")
                    return subprocess.CompletedProcess(command, 1, "", "nvenc failed")
                output.write_bytes(b"cpu success")
                return subprocess.CompletedProcess(command, 0, "", "")

            completed, metadata = execute_mux_with_fallback(
                video_only=video,
                audio_source=audio,
                background_audio_source=None,
                output=output,
                duration_seconds=1.0,
                ffmpeg_binary="ffmpeg",
                audio_filter_args=(),
                background_gain=0.22,
                selected_encoder="h264_nvenc",
                selected_video_args=["-c:v", "h264_nvenc"],
                selected_encoder_is_hardware=True,
                hardware_fallback_enabled=True,
                width=64,
                height=64,
                run=run,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertTrue(metadata["success"])
            self.assertTrue(metadata["runtime_fallback_used"])
            self.assertEqual(metadata["selected_encoder"], "libx264")
            self.assertIn("h264_nvenc", commands[0])
            self.assertIn("libx264", commands[1])

    def test_final_narration_file_must_match_approved_manifest_hash(self) -> None:
        with TemporaryDirectory() as tmp:
            narration = Path(tmp) / "joined.wav"
            narration.write_bytes(b"approved narration")
            digest = hashlib.sha256(narration.read_bytes()).hexdigest()
            contract = {
                "authorities": {
                    "audio": {
                        "status": "READY",
                        "narration_ref": {"sha256": digest},
                    }
                }
            }
            validate_narration_file_authority(narration, contract)
            narration.write_bytes(b"stale narration")
            with self.assertRaises(AdaptiveVideoRenderError):
                validate_narration_file_authority(narration, contract)

    def test_mux_can_mix_verified_background_with_narration(self) -> None:
        command = build_audio_mux_command(
            video_only=Path("video_only.mp4"),
            audio_source=Path("joined.wav"),
            background_audio_source=Path("background.wav"),
            output=Path("final.mp4"),
            duration_seconds=10.0,
            ffmpeg_binary="ffmpeg",
            audio_filter_args=["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"],
        )
        self.assertIn("background.wav", [str(value) for value in command])
        self.assertIn("-filter_complex", command)
        self.assertTrue(any("amix" in str(value) for value in command))
        self.assertTrue(any("loudnorm" in str(value) for value in command))
        self.assertTrue(any("channel_layouts=stereo" in str(value) for value in command))
        self.assertEqual(command[command.index("-ac") + 1], "2")

    def test_mux_fits_long_narration_before_background_mix(self) -> None:
        command = build_audio_mux_command(
            video_only=Path("video_only.mp4"),
            audio_source=Path("joined.wav"),
            background_audio_source=Path("background.wav"),
            output=Path("final.mp4"),
            duration_seconds=38.5,
            ffmpeg_binary="ffmpeg",
            narration_atempo=1.111169,
        )

        filter_complex = command[command.index("-filter_complex") + 1]
        self.assertIn("atempo=1.111169", filter_complex)
        self.assertIn("amix=inputs=2:duration=longest", filter_complex)


if __name__ == "__main__":
    unittest.main()
