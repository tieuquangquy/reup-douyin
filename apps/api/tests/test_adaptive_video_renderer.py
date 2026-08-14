from __future__ import annotations

import unittest
import hashlib
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.media_pipeline.video_renderer.adaptive_video import (
    AdaptiveVideoRenderError,
    active_tracks_for_frame,
    build_audio_mux_command,
    execute_mux_with_fallback,
    remux_adaptive_preview_as_final,
    resolve_background_gain,
    resolve_narration_atempo,
    should_seed_reference_plate,
    validate_narration_file_authority,
    validate_adaptive_render_contract,
)


class AdaptiveVideoContractTests(unittest.TestCase):
    def test_final_can_reuse_exact_approved_preview_video_stream(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            preview = root / "preview.mp4"
            narration = root / "joined.wav"
            output = root / "final.mp4"
            qa = root / "final.qa.json"
            preview.write_bytes(b"approved visual packets")
            narration.write_bytes(b"approved narration")
            preview_hash = hashlib.sha256(preview.read_bytes()).hexdigest()
            narration_hash = hashlib.sha256(narration.read_bytes()).hexdigest()
            contract = {
                "status": "READY_FOR_PHASE4",
                "video": {
                    "frame_count": 30,
                    "frame_width": 1080,
                    "frame_height": 1920,
                    "fps": 30.0,
                },
                "authorities": {
                    "timebase": {
                        "mode": "CFR",
                        "status": "READY",
                        "nominal_fps": 30.0,
                    },
                    "audio": {
                        "status": "READY",
                        "narration_ref": {"sha256": narration_hash},
                    },
                },
                "render_tracks": [],
            }

            def fake_mux(**kwargs):
                self.assertEqual(kwargs["selected_video_args"], ["-c:v", "copy"])
                kwargs["output"].write_bytes(b"final container")
                return subprocess.CompletedProcess([], 0, "", ""), {
                    "success": True,
                    "selected_encoder": "stream_copy",
                    "runtime_fallback_used": False,
                    "runtime_fallback_reason": None,
                    "encode_attempts": [],
                }

            with patch(
                "src.media_pipeline.video_renderer.adaptive_video.probe_video_duration_ms",
                return_value=1000,
            ), patch(
                "src.media_pipeline.video_renderer.adaptive_video.two_pass_loudness_filter_args",
                return_value=[],
            ), patch(
                "src.media_pipeline.video_renderer.adaptive_video.execute_mux_with_fallback",
                side_effect=fake_mux,
            ):
                result = remux_adaptive_preview_as_final(
                    preview,
                    output,
                    contract=contract,
                    narration_path=narration,
                    expected_preview_sha256=preview_hash,
                    qa_path=qa,
                )

            self.assertTrue(output.is_file())
            self.assertEqual(result.frame_count, 30)
            self.assertTrue(result.encoder_metadata["visual_authority_reused"])
            self.assertEqual(result.encoder_metadata["selected_encoder"], "stream_copy")
            self.assertEqual(
                json.loads(qa.read_text(encoding="utf-8"))["video_codec"], "copy"
            )

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

    def test_blur_transition_hold_covers_without_rendering_text(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "text_id": "held",
                    "start_frame": 10,
                    "end_frame": 20,
                    "cover_only": False,
                    "render_policy": {
                        "cover": {"transition_hold_frames": 2}
                    },
                }
            ]
        }

        before = active_tracks_for_frame(contract, 8)
        active = active_tracks_for_frame(contract, 10)
        outside = active_tracks_for_frame(contract, 7)

        self.assertTrue(before[0]["cover_only"])
        self.assertTrue(before[0]["transition_hold_cover_only"])
        self.assertFalse(active[0]["cover_only"])
        self.assertEqual(outside, [])

    def test_transition_hold_is_not_truncated_to_three_frames(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "text_id": "held_60fps",
                    "start_frame": 20,
                    "end_frame": 30,
                    "render_policy": {
                        "cover": {"transition_hold_frames": 7}
                    },
                }
            ]
        }

        self.assertEqual(
            [row["text_id"] for row in active_tracks_for_frame(contract, 13)],
            ["held_60fps"],
        )
        self.assertEqual(active_tracks_for_frame(contract, 12), [])

    def test_coverage_authority_controls_presence_and_frame_geometry(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "text_id": "moving",
                    "start_frame": 2,
                    "end_frame": 8,
                    "geometry": {"x": 0.20, "y": 0.60, "width": 0.30, "height": 0.05},
                    "coverage_authority": {
                        "presence_ranges": [[4, 5]],
                        "geometry_keyframes": [
                            {
                                "frame_index": 4,
                                "geometry": {"x": 0.10, "y": 0.60, "width": 0.35, "height": 0.05},
                            },
                            {
                                "frame_index": 5,
                                "geometry": {"x": 0.12, "y": 0.60, "width": 0.35, "height": 0.05},
                            },
                        ],
                    },
                    "render_policy": {
                        "cover": {
                            "transition_hold_frames": 0,
                            "roi": {"x": 0.18, "y": 0.59, "width": 0.34, "height": 0.07},
                        },
                        "layout": {
                            "mode": "cover_aligned",
                            "safe_area": {"x": 0.18, "y": 0.59, "width": 0.34, "height": 0.07},
                        },
                    },
                }
            ]
        }

        self.assertEqual(active_tracks_for_frame(contract, 3), [])
        active = active_tracks_for_frame(contract, 4)
        self.assertEqual(len(active), 1)
        self.assertAlmostEqual(active[0]["geometry"]["x"], 0.10)
        self.assertAlmostEqual(
            active[0]["render_policy"]["cover"]["roi"]["x"], 0.08
        )
        self.assertEqual(
            active[0]["render_policy"]["layout"]["safe_area"],
            active[0]["render_policy"]["cover"]["roi"],
        )

    def test_explicit_cover_interval_closes_ocr_presence_gaps(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "text_id": "gap_caption",
                    "start_frame": 10,
                    "end_frame": 20,
                    "cover_start_frame": 10,
                    "cover_end_frame": 20,
                    "coverage_authority": {
                        "presence_ranges": [[14, 16]],
                    },
                    "render_policy": {
                        "cover": {"transition_hold_frames": 0}
                    },
                }
            ]
        }

        before_presence = active_tracks_for_frame(contract, 12)
        during_presence = active_tracks_for_frame(contract, 15)

        self.assertEqual(len(before_presence), 1)
        self.assertFalse(before_presence[0].get("cover_only", False))
        self.assertFalse(during_presence[0].get("cover_only", False))

    def test_stable_caption_cover_ignores_sparse_geometry_jitter(self) -> None:
        stable_roi = {"x": 0.12, "y": 0.70, "width": 0.76, "height": 0.06}
        contract = {
            "render_tracks": [
                {
                    "text_id": "stable_caption",
                    "start_frame": 1,
                    "end_frame": 5,
                    "geometry": {"x": 0.18, "y": 0.72, "width": 0.64, "height": 0.03},
                    "coverage_authority": {
                        "presence_ranges": [[1, 5]],
                        "geometry_keyframes": [
                            {
                                "frame_index": 3,
                                "geometry": {"x": 0.05, "y": 0.68, "width": 0.90, "height": 0.08},
                            }
                        ],
                    },
                    "render_policy": {
                        "cover": {
                            "transition_hold_frames": 0,
                            "geometry_mode": "stable_caption_group",
                            "roi": stable_roi,
                        },
                        "layout": {"mode": "cover_aligned", "safe_area": stable_roi},
                    },
                }
            ]
        }

        active = active_tracks_for_frame(contract, 3)[0]

        self.assertEqual(active["render_policy"]["cover"]["roi"], stable_roi)
        self.assertEqual(active["render_policy"]["layout"]["safe_area"], stable_roi)
        self.assertEqual(active["geometry"]["x"], 0.05)

    def test_intro_stylized_title_keeps_bounded_cover_static(self) -> None:
        base_roi = {"x": 0.18, "y": 0.645, "width": 0.704, "height": 0.161}
        contract = {
            "render_tracks": [
                {
                    "text_id": "intro_title",
                    "start_frame": 0,
                    "end_frame": 4,
                    "geometry": {"x": 0.20, "y": 0.665, "width": 0.663, "height": 0.121},
                    "coverage_authority": {
                        "presence_ranges": [[0, 15]],
                        "geometry_keyframes": [
                            {"frame_index": 0, "geometry": {"x": 0.20, "y": 0.596, "width": 0.663, "height": 0.190}},
                            {"frame_index": 3, "geometry": {"x": 0.088, "y": 0.596, "width": 0.777, "height": 0.258}},
                        ],
                    },
                    "render_policy": {
                        "context": {"intro_stylized_title": True},
                        "cover": {"roi": base_roi, "geometry_mode": "track_relative"},
                        "layout": {"mode": "cover_aligned", "safe_area": base_roi},
                    },
                }
            ]
        }
        active = active_tracks_for_frame(contract, 3)[0]
        self.assertEqual(active["render_policy"]["cover"]["roi"], base_roi)
        self.assertEqual(active["render_policy"]["layout"]["safe_area"], base_roi)

    def test_dynamic_geometry_preserves_expanded_vietnamese_safe_area(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "text_id": "long_ui_chip",
                    "start_frame": 1,
                    "end_frame": 10,
                    "geometry": {
                        "x": 0.165,
                        "y": 0.557,
                        "width": 0.173,
                        "height": 0.047,
                    },
                    "coverage_authority": {
                        "presence_ranges": [[1, 10]],
                        "geometry_keyframes": [
                            {
                                "frame_index": 1,
                                "geometry": {
                                    "x": 0.155,
                                    "y": 0.545,
                                    "width": 0.193,
                                    "height": 0.071,
                                },
                            }
                        ],
                    },
                    "render_policy": {
                        "cover": {
                            "transition_hold_frames": 0,
                            "roi": {
                                "x": 0.155,
                                "y": 0.545,
                                "width": 0.193,
                                "height": 0.071,
                            },
                        },
                        "layout": {
                            "mode": "cover_aligned",
                            "safe_area": {
                                "x": 0.065,
                                "y": 0.537,
                                "width": 0.373,
                                "height": 0.087,
                            },
                            "max_lines": 2,
                        },
                    },
                }
            ]
        }

        active = active_tracks_for_frame(contract, 1)
        cover = active[0]["render_policy"]["cover"]["roi"]
        safe = active[0]["render_policy"]["layout"]["safe_area"]

        self.assertGreater(safe["width"], cover["width"])
        self.assertGreater(safe["height"], cover["height"])
        self.assertAlmostEqual(safe["width"] - cover["width"], 0.18)
        self.assertAlmostEqual(safe["height"] - cover["height"], 0.016)

    def test_dynamic_caption_lane_updates_its_bounded_damage_budget(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "text_id": "dynamic_caption",
                    "start_frame": 0,
                    "end_frame": 2,
                    "geometry": {
                        "x": 0.1,
                        "y": 0.70,
                        "width": 0.8,
                        "height": 0.05,
                    },
                    "coverage_authority": {
                        "presence_ranges": [[0, 2]],
                        "geometry_keyframes": [
                            {
                                "frame_index": 1,
                                "geometry": {
                                    "x": 0.0,
                                    "y": 0.67,
                                    "width": 1.0,
                                    "height": 0.09,
                                },
                            }
                        ],
                    },
                    "render_policy": {
                        "cover": {
                            "transition_hold_frames": 0,
                            "geometry_mode": "full_width_caption_lane",
                            "roi": {
                                "x": 0.0,
                                "y": 0.67,
                                "width": 1.0,
                                "height": 0.10,
                            },
                        },
                        "layout": {
                            "mode": "cover_aligned",
                            "safe_area": {
                                "x": 0.0,
                                "y": 0.67,
                                "width": 1.0,
                                "height": 0.10,
                            },
                        },
                        "damage_budget": {
                            "max_frame_change_fraction": 0.11,
                        },
                    },
                }
            ]
        }

        active = active_tracks_for_frame(contract, 1)
        cover = active[0]["render_policy"]["cover"]["roi"]
        budget = active[0]["render_policy"]["damage_budget"]

        self.assertEqual(cover["x"], 0.0)
        self.assertEqual(cover["width"], 1.0)
        self.assertGreaterEqual(
            budget["max_frame_change_fraction"],
            cover["height"] * 1.02,
        )
        self.assertLessEqual(budget["max_frame_change_fraction"], 0.16)

    def test_cover_interval_survives_text_authority_partition(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "text_id": "late_caption",
                    "start_frame": 15,
                    "end_frame": 20,
                    "cover_start_frame": 10,
                    "cover_end_frame": 20,
                    "cover_only": False,
                    "render_policy": {"cover": {"transition_hold_frames": 0}},
                }
            ]
        }

        cover_only = active_tracks_for_frame(contract, 12)
        text_active = active_tracks_for_frame(contract, 16)

        self.assertEqual([row["text_id"] for row in cover_only], ["late_caption"])
        self.assertTrue(cover_only[0]["cover_only"])
        self.assertFalse(text_active[0]["cover_only"])

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
