from __future__ import annotations

import unittest

from src.media_pipeline.video_renderer.render_authority import (
    analyze_frame_timestamps,
    apply_pts_map_to_contract,
    build_reproducible_render_recipe,
    resolve_audio_authority,
)


class FrameTimestampAuthorityTests(unittest.TestCase):
    def test_detects_cfr_timestamps(self) -> None:
        result = analyze_frame_timestamps([0.0, 0.04, 0.08, 0.12, 0.16])
        self.assertEqual(result["mode"], "CFR")
        self.assertEqual(result["status"], "READY")

    def test_vfr_requires_explicit_pts_render_path(self) -> None:
        result = analyze_frame_timestamps([0.0, 0.033, 0.081, 0.114, 0.180])
        self.assertEqual(result["mode"], "VFR")
        self.assertEqual(result["status"], "PTS_RENDER_REQUIRED")

    def test_pts_map_replaces_nominal_track_times_without_changing_frames(self) -> None:
        contract = {
            "video": {"frame_count": 4, "fps": 30.0},
            "render_tracks": [
                {
                    "text_id": "a",
                    "start_frame": 1,
                    "end_frame": 2,
                    "start_ms": 33,
                    "end_ms": 100,
                }
            ],
        }
        mapped = apply_pts_map_to_contract(contract, [0.0, 0.033, 0.081, 0.114])
        track = mapped["render_tracks"][0]
        self.assertEqual(track["start_frame"], 1)
        self.assertEqual(track["end_frame"], 2)
        self.assertEqual(track["start_ms"], 33)
        self.assertEqual(track["end_ms"], 114)
        self.assertEqual(mapped["timebase_mode"], "PTS")


class AudioAuthorityTests(unittest.TestCase):
    def test_prefers_joined_tts_narration(self) -> None:
        manifest = {
            "manifest_version": "RENDER_PREP_MANIFEST_V2",
            "audio_review": {"status": "AUDIO_APPROVED"},
            "current_outputs": {
                "joined_narration": [
                    {"storage_key": "workspace/video/audio/joined.wav", "sha256": "a" * 64}
                ]
            }
        }
        result = resolve_audio_authority(
            manifest,
            allow_source_passthrough=False,
        )
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["strategy"], "replace_with_vietnamese_narration")

    def test_background_mix_gain_is_part_of_audio_authority(self) -> None:
        manifest = {
            "manifest_version": "RENDER_PREP_MANIFEST_V2",
            "audio_review": {"status": "AUDIO_APPROVED"},
            "render_contract": {
                "audio_strategy": "mix_vietnamese_narration_with_background_stem",
                "background_gain": 1.0,
            },
            "current_outputs": {
                "joined_narration": [
                    {"storage_key": "joined.wav", "sha256": "a" * 64}
                ],
                "background_audio": [
                    {"storage_key": "background.wav", "sha256": "b" * 64}
                ],
            },
        }

        result = resolve_audio_authority(manifest, allow_source_passthrough=False)

        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["background_gain"], 1.0)

    def test_invalid_background_mix_gain_blocks_audio_authority(self) -> None:
        manifest = {
            "manifest_version": "RENDER_PREP_MANIFEST_V2",
            "audio_review": {"status": "AUDIO_APPROVED"},
            "render_contract": {"background_gain": 1.5},
            "current_outputs": {
                "joined_narration": [
                    {"storage_key": "joined.wav", "sha256": "a" * 64}
                ],
                "background_audio": [
                    {"storage_key": "background.wav", "sha256": "b" * 64}
                ],
            },
        }

        result = resolve_audio_authority(manifest, allow_source_passthrough=False)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("background_mix_gain_invalid", result["warnings"])

    def test_unapproved_or_unhashed_narration_is_blocked(self) -> None:
        pending = {
            "manifest_version": "RENDER_PREP_MANIFEST_V2",
            "audio_review": {"status": "PENDING_AUDIO_REVIEW"},
            "current_outputs": {
                "joined_narration": [
                    {"storage_key": "audio.wav", "sha256": "a" * 64}
                ]
            },
        }
        unhashed = {
            "manifest_version": "RENDER_PREP_MANIFEST_V2",
            "audio_review": {"status": "AUDIO_APPROVED"},
            "current_outputs": {
                "joined_narration": [{"storage_key": "audio.wav"}]
            },
        }
        self.assertEqual(
            resolve_audio_authority(pending, allow_source_passthrough=False)["status"],
            "BLOCKED",
        )
        self.assertEqual(
            resolve_audio_authority(unhashed, allow_source_passthrough=False)["status"],
            "BLOCKED",
        )

    def test_approved_measured_no_dialogue_audio_uses_passthrough_strategy(self) -> None:
        manifest = {
            "manifest_version": "RENDER_PREP_MANIFEST_V2",
            "audio_review": {"status": "AUDIO_APPROVED"},
            "current_outputs": {
                "joined_narration": [
                    {
                        "storage_key": "phase4_joined_narration.wav",
                        "sha256": "a" * 64,
                        "mime_type": "audio/wav",
                        "role": "verified_no_dialogue_source_audio",
                    }
                ]
            },
        }
        result = resolve_audio_authority(manifest, allow_source_passthrough=False)
        self.assertEqual(result["status"], "READY")
        self.assertEqual(
            result["strategy"], "preserve_verified_no_dialogue_source_audio"
        )

    def test_missing_tts_blocks_final_but_allows_explicit_visual_preview(self) -> None:
        blocked = resolve_audio_authority(None, allow_source_passthrough=False)
        preview = resolve_audio_authority(None, allow_source_passthrough=True)
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertEqual(preview["status"], "VISUAL_PREVIEW_ONLY")
        self.assertEqual(preview["strategy"], "source_passthrough")


class ReproducibleRecipeTests(unittest.TestCase):
    def test_recipe_hash_is_stable_and_anti_transform_is_opt_in(self) -> None:
        kwargs = {
            "phase4_input_sha256": "1" * 64,
            "source_video_sha256": "2" * 64,
            "font_sha256": "3" * 64,
            "policy_version": "phase4_role_policy_v1",
            "runtime_versions": {"opencv": "4.10", "ffmpeg": "7.0"},
            "audio_authority": {"strategy": "source_passthrough"},
            "color_authority": {"color_space": "bt709"},
            "timebase_authority": {"mode": "CFR"},
            "anti_transform_enabled": False,
            "anti_seed": None,
        }
        first = build_reproducible_render_recipe(**kwargs)
        second = build_reproducible_render_recipe(**kwargs)
        self.assertEqual(first["recipe_sha256"], second["recipe_sha256"])
        self.assertFalse(first["localization"]["anti_transform_enabled"])

    def test_recipe_records_safe_encoder_policy_without_visual_transform(self) -> None:
        recipe = build_reproducible_render_recipe(
            phase4_input_sha256="1" * 64,
            source_video_sha256="2" * 64,
            font_sha256="3" * 64,
            policy_version="phase4_role_policy_v2",
            runtime_versions={"ffmpeg": "7.0"},
            audio_authority={"status": "READY"},
            color_authority={"color_space": "bt709"},
            timebase_authority={"mode": "VFR"},
            anti_transform_enabled=False,
            anti_seed=None,
            encoding_policy={
                "requested_encoder": "auto",
                "geometry_transform": "none",
                "invisible_perturbation": False,
            },
        )
        self.assertEqual(recipe["encoding_policy"]["requested_encoder"], "auto")
        self.assertEqual(recipe["encoding_policy"]["geometry_transform"], "none")
        self.assertFalse(recipe["encoding_policy"]["invisible_perturbation"])


if __name__ == "__main__":
    unittest.main()
