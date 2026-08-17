from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from scripts import run_phase4_preflight
from src.media_pipeline.video_renderer.phase4_input_contract import Phase4InputError


class RunPhase4PreflightTests(unittest.TestCase):
    def test_recorded_run_persists_actionable_input_failure(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase3_render_handoff.json").write_text(
                '{"status":"READY_FOR_RENDER"}', encoding="utf-8"
            )
            with patch.object(
                run_phase4_preflight,
                "run",
                side_effect=Phase4InputError("Invalid timing/geometry for sub_71"),
            ):
                with self.assertRaisesRegex(Phase4InputError, "sub_71"):
                    run_phase4_preflight.run_recorded(root)

            failure = json.loads(
                (root / "phase4_preflight_failure.json").read_text(encoding="utf-8")
            )

        self.assertEqual(failure["error_code"], "PHASE4_INPUT_INVALID")
        self.assertEqual(failure["error_type"], "Phase4InputError")
        self.assertFalse(failure["retryable"])
        self.assertIn("sub_71", failure["message"])
        self.assertEqual(len(failure["phase3_render_handoff_sha256"]), 64)

    def test_operator_false_positive_exclusion_keeps_raw_detection_auditable(
        self,
    ) -> None:
        detection = {
            "frame_index": 685,
            "text": "22.2å…ƒ",
            "confidence": 0.9589,
            "geometry": {"x": 0.26, "y": 0.33, "width": 0.04, "height": 0.02},
        }
        approval = {
            "detection": detection,
            "detection_sha256": run_phase4_preflight.residual_detection_sha256(
                detection
            ),
            "approval_sha256": "a" * 64,
            "approval_token": "OCR_FALSE_POSITIVE_CONFIRMED_CASE_V1",
        }

        blocking, excluded = (
            run_phase4_preflight._apply_residual_false_positive_approval(
                [detection], approval
            )
        )

        self.assertEqual(blocking, [])
        self.assertEqual(
            excluded[0]["classification"],
            "OPERATOR_CONFIRMED_OCR_FALSE_POSITIVE",
        )

    def test_operator_false_positive_exclusion_covers_only_tight_temporal_cluster(
        self,
    ) -> None:
        detection = {
            "frame_index": 685,
            "text": "22.2Ã¥â€¦Æ’",
            "confidence": 0.9589,
            "geometry": {"x": 0.26, "y": 0.33, "width": 0.04, "height": 0.02},
        }
        peer = {**detection, "frame_index": 693, "confidence": 0.95}
        distant = {**detection, "frame_index": 745}
        approval = {
            "detection": detection,
            "detection_sha256": run_phase4_preflight.residual_detection_sha256(
                detection
            ),
            "approval_sha256": "a" * 64,
            "approval_token": "OCR_FALSE_POSITIVE_CONFIRMED_CASE_V1",
        }

        blocking, excluded = (
            run_phase4_preflight._apply_residual_false_positive_approval(
                [detection, peer, distant], approval, fps=30.0
            )
        )

        self.assertEqual(blocking, [distant])
        self.assertEqual([row["frame_index"] for row in excluded], [685, 693])
        self.assertEqual(
            excluded[1]["approval_match"]["type"],
            "TEMPORAL_GEOMETRY_CLUSTER",
        )

    def test_exact_frame_loader_decodes_sequentially_for_vfr_safety(self) -> None:
        class FakeCapture:
            def __init__(self) -> None:
                self.read_count = 0

            def read(self) -> tuple[bool, int]:
                value = self.read_count
                self.read_count += 1
                return True, value

        capture = FakeCapture()

        decoded = run_phase4_preflight._decode_frames_sequential(
            capture, [5, 2, 5]
        )

        self.assertEqual(decoded, {2: 2, 5: 5})
        self.assertEqual(capture.read_count, 6)

    def test_reference_selection_rejects_plate_with_unchanged_text_roi(self) -> None:
        current = np.zeros((20, 20, 3), dtype=np.uint8)
        track = {
            "start_frame": 5,
            "end_frame": 6,
            "render_policy": {
                "cover": {
                    "roi": {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}
                }
            },
        }

        reference = run_phase4_preflight._reference_frame_for_track(
            {4: current.copy()},
            track,
            current_frame=current,
            frame_count=20,
            fps=10.0,
        )

        self.assertIsNone(reference)

    def test_reference_selection_accepts_clean_plate_with_changed_text_roi(self) -> None:
        current = np.zeros((20, 20, 3), dtype=np.uint8)
        clean = current.copy()
        clean[5:15, 5:15] = 20
        track = {
            "start_frame": 5,
            "end_frame": 6,
            "render_policy": {
                "cover": {
                    "roi": {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}
                }
            },
        }

        reference = run_phase4_preflight._reference_frame_for_track(
            {4: clean},
            track,
            current_frame=current,
            frame_count=20,
            fps=10.0,
        )

        self.assertIsNotNone(reference)
        assert reference is not None
        self.assertEqual(reference[0], 4)

    def test_quarantines_the_entire_previous_sample_set(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample_dir = root / "qa" / "phase4_preflight_samples"
            sample_dir.mkdir(parents=True)
            (sample_dir / "frame_000001.jpg").write_bytes(b"old-frame")
            (sample_dir / "sample_manifest.json").write_text(
                "{}", encoding="utf-8"
            )

            moved = run_phase4_preflight._quarantine_previous_preflight_samples(
                sample_dir, root=root
            )

            self.assertEqual(moved, 2)
            self.assertEqual(list(sample_dir.iterdir()), [])
            stale = root / "qa" / "stale" / "phase4_preflight_samples"
            runs = list(stale.iterdir())
            self.assertEqual(len(runs), 1)
            self.assertTrue((runs[0] / "frame_000001.jpg").is_file())
            self.assertTrue((runs[0] / "sample_manifest.json").is_file())

    def test_representative_frames_prefer_stable_best_frame(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "text_id": "sub_01",
                    "content_id": "content_01",
                    "start_frame": 10,
                    "end_frame": 30,
                    "best_frame_index": 22,
                    "text_vi": "Bản dịch",
                }
            ]
        }

        frames = run_phase4_preflight._representative_frames(contract, {})

        self.assertEqual(frames, [22])

    def test_representative_frames_always_include_video_boundaries(self) -> None:
        contract = {
            "video": {"frame_count": 100},
            "render_tracks": [
                {
                    "text_id": "sub_01",
                    "content_id": "content_01",
                    "start_frame": 10,
                    "end_frame": 30,
                    "best_frame_index": 22,
                    "text_vi": "Báº£n dá»‹ch",
                }
            ],
        }

        frames = run_phase4_preflight._representative_frames(contract, {})

        self.assertEqual(frames, [0, 22, 99])

    def test_run_writes_ready_meta_without_rendering_video(self) -> None:
        contract = {
            "status": "READY_FOR_PHASE4",
            "counts": {
                "render_tracks": 36,
                "localized_tracks": 36,
                "cover_only_tracks": 0,
            },
            "refs": {"phase3_render_handoff_ref": {"sha256": "f" * 64}},
            "render_tracks": [],
        }
        report = {
            "status": "READY_FOR_PHASE4",
            "counts": {
                "text_overflow": 0,
                "clamp_required": 0,
                "collision_events": 0,
            },
        }
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            with (
                patch.object(
                    run_phase4_preflight,
                    "prepare_phase4_from_root",
                    return_value=(contract, report, source),
                ),
                patch.object(
                    run_phase4_preflight,
                    "write_phase4_preflight_artifacts",
                    return_value={},
                ),
                patch.object(
                    run_phase4_preflight,
                    "write_preflight_samples",
                    return_value=[root / "qa" / "contact_sheet.jpg"],
                ),
                patch.object(
                    run_phase4_preflight,
                    "probe_media_authority",
                    return_value={
                        "video": {"color_space": "bt709"},
                        "audio": {"present": True},
                        "timebase": {"status": "READY", "mode": "CFR"},
                    },
                ),
                patch.object(
                    run_phase4_preflight,
                    "resolve_audio_authority",
                    return_value={
                        "status": "VISUAL_PREVIEW_ONLY",
                        "strategy": "source_passthrough",
                        "warnings": ["tts_joined_narration_missing"],
                    },
                ),
                patch.object(
                    run_phase4_preflight,
                    "build_reproducible_render_recipe",
                    return_value={"recipe_sha256": "r" * 64},
                ),
                patch.object(
                    run_phase4_preflight,
                    "_sha256_file",
                    return_value="s" * 64,
                ),
            ):
                result = run_phase4_preflight.run(root)

            self.assertEqual(result, 0)
            meta = json.loads(
                (root / "phase4_preflight_meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(meta["status"], "READY_FOR_PHASE4")
            self.assertEqual(meta["final_render_gate"], "BLOCKED_AUDIO_AUTHORITY")
            self.assertNotIn("source_path", meta)
            self.assertFalse((root / "output.mp4").exists())

    def test_preflight_reconciles_small_media_frame_count_delta(self) -> None:
        contract = {
            "status": "READY_FOR_PHASE4",
            "counts": {"render_tracks": 0, "localized_tracks": 0},
            "refs": {"phase3_render_handoff_ref": {"sha256": "f" * 64}},
            "video": {"frame_count": 11, "fps": 30.0},
            "render_tracks": [],
        }
        report = {
            "status": "READY_FOR_PHASE4",
            "counts": {"text_overflow": 0, "clamp_required": 0, "collision_events": 0},
        }
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            with (
                patch.object(
                    run_phase4_preflight,
                    "prepare_phase4_from_root",
                    return_value=(contract, report, source),
                ),
                patch.object(run_phase4_preflight, "write_phase4_preflight_artifacts"),
                patch.object(run_phase4_preflight, "write_preflight_samples", return_value=[]),
                patch.object(
                    run_phase4_preflight,
                    "probe_media_authority",
                    return_value={
                        "video": {},
                        "audio": {},
                        "timebase": {"status": "READY"},
                        "frame_timestamps_seconds": [float(index) for index in range(10)],
                    },
                ),
                patch.object(run_phase4_preflight, "resolve_audio_authority", return_value={"status": "READY"}),
                patch.object(run_phase4_preflight, "build_reproducible_render_recipe", return_value={}),
                patch.object(run_phase4_preflight, "_sha256_file", return_value="s" * 64),
            ):
                result = run_phase4_preflight.run(root)

            meta = json.loads(
                (root / "phase4_preflight_meta.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result, 0)
        self.assertEqual(meta["status"], "READY_FOR_PHASE4")
        self.assertEqual(
            meta["frame_count_reconciliation"]["decoded_frame_count"], 10
        )

    def test_residual_cjk_in_preflight_sample_blocks_phase4(self) -> None:
        contract = {
            "status": "READY_FOR_PHASE4",
            "counts": {"render_tracks": 1, "localized_tracks": 1},
            "refs": {"phase3_render_handoff_ref": {"sha256": "f" * 64}},
            "video": {"fps": 30.0},
            "render_tracks": [],
        }
        report = {
            "status": "READY_FOR_PHASE4",
            "counts": {"text_overflow": 0, "clamp_required": 0, "collision_events": 0},
        }
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            sample = root / "qa" / "phase4_preflight_samples" / "frame_000010.jpg"
            source.write_bytes(b"video")
            sample.parent.mkdir(parents=True)
            sample.write_bytes(b"image")
            with (
                patch.object(
                    run_phase4_preflight,
                    "prepare_phase4_from_root",
                    return_value=(contract, report, source),
                ),
                patch.object(run_phase4_preflight, "write_phase4_preflight_artifacts"),
                patch.object(
                    run_phase4_preflight,
                    "write_preflight_samples",
                    return_value=[sample],
                ),
                patch.object(run_phase4_preflight, "probe_media_authority", return_value={
                    "video": {}, "audio": {}, "timebase": {"status": "READY"}
                }),
                patch.object(run_phase4_preflight, "resolve_audio_authority", return_value={"status": "READY"}),
                patch.object(run_phase4_preflight, "build_reproducible_render_recipe", return_value={}),
                patch.object(run_phase4_preflight, "build_local_residual_ocr_provider", return_value=object()),
                patch.object(
                    run_phase4_preflight,
                    "_detect_residual_cjk",
                    return_value=(
                        True,
                        [{"frame_index": 10, "text": "午餐", "confidence": 0.99}],
                        None,
                    ),
                ),
                patch.object(run_phase4_preflight, "_sha256_file", return_value="s" * 64),
            ):
                result = run_phase4_preflight.run(root)

            meta = json.loads(
                (root / "phase4_preflight_meta.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result, 1)
        self.assertEqual(meta["status"], "PHASE4_PREFLIGHT_BLOCKED")
        self.assertEqual(meta["final_render_gate"], "BLOCKED_VISUAL_RESIDUAL_CJK")

    def test_unconfirmed_single_frame_residual_fails_closed(self) -> None:
        detection = {
            "frame_index": 10,
            "text": "22.2å…ƒ",
            "confidence": 0.99,
            "geometry": {"x": 0.25, "y": 0.30, "width": 0.05, "height": 0.03},
        }
        contract = {
            "status": "READY_FOR_PHASE4",
            "counts": {"render_tracks": 1, "localized_tracks": 1},
            "refs": {"phase3_render_handoff_ref": {"sha256": "f" * 64}},
            "video": {"fps": 30.0, "frame_count": 30},
            "render_tracks": [
                {
                    "start_frame": 5,
                    "end_frame": 20,
                    "render_policy": {
                        "cover": {
                            "roi": {
                                "x": 0.24,
                                "y": 0.29,
                                "width": 0.07,
                                "height": 0.06,
                            }
                        }
                    },
                }
            ],
        }
        report = {
            "status": "READY_FOR_PHASE4",
            "counts": {"text_overflow": 0, "clamp_required": 0, "collision_events": 0},
        }
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            sample = root / "qa" / "phase4_preflight_samples" / "frame_000010.jpg"
            source_sample = root / "qa" / "phase4_preflight_samples" / "residual_source_confirmation" / "frame_000010.jpg"
            neighbor = root / "qa" / "phase4_preflight_samples" / "residual_temporal_confirmation" / "frame_000009.jpg"
            source.write_bytes(b"video")
            sample.parent.mkdir(parents=True)
            sample.write_bytes(b"image")
            source_sample.parent.mkdir(parents=True)
            source_sample.write_bytes(b"image")
            neighbor.parent.mkdir(parents=True)
            neighbor.write_bytes(b"image")
            with (
                patch.object(
                    run_phase4_preflight,
                    "prepare_phase4_from_root",
                    return_value=(contract, report, source),
                ),
                patch.object(run_phase4_preflight, "write_phase4_preflight_artifacts"),
                patch.object(
                    run_phase4_preflight,
                    "write_preflight_samples",
                    return_value=[sample],
                ),
                patch.object(
                    run_phase4_preflight,
                    "write_source_residual_samples",
                    return_value={10: source_sample},
                ),
                patch.object(
                    run_phase4_preflight,
                    "write_residual_temporal_confirmation_samples",
                    return_value={9: neighbor},
                ),
                patch.object(run_phase4_preflight, "probe_media_authority", return_value={
                    "video": {}, "audio": {}, "timebase": {"status": "READY"}
                }),
                patch.object(run_phase4_preflight, "resolve_audio_authority", return_value={"status": "READY"}),
                patch.object(run_phase4_preflight, "build_reproducible_render_recipe", return_value={}),
                patch.object(run_phase4_preflight, "build_local_residual_ocr_provider", return_value=object()),
                patch.object(
                    run_phase4_preflight,
                    "_detect_residual_cjk",
                    side_effect=[
                        (True, [detection], None),
                        (True, [], None),
                        (True, [], None),
                    ],
                ),
                patch.object(run_phase4_preflight, "_sha256_file", return_value="s" * 64),
            ):
                result = run_phase4_preflight.run(root)

            meta = json.loads(
                (root / "phase4_preflight_meta.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result, 1)
        self.assertEqual(meta["status"], "PHASE4_PREFLIGHT_BLOCKED")
        self.assertEqual(len(meta["residual_cjk"]["detections"]), 1)
        self.assertEqual(meta["residual_cjk"]["temporal_false_positives"], [])


if __name__ == "__main__":
    unittest.main()
