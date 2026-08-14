from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from src.media_pipeline.video_renderer.adaptive_output_qa import (
    OUTPUT_QA_CONTACT_SHEET_MAX_HEIGHT,
    _write_contact_sheet,
    allowed_edit_mask_for_frame,
    build_local_residual_ocr_provider,
    build_output_qa_verdict,
    collect_adaptive_output_qa,
    collect_reused_visual_output_qa,
    classify_source_scene_protected_cjk,
    classify_editor_caption_ocr_false_positives,
    classify_source_intrinsic_edge_cjk,
    classify_temporally_unconfirmed_cjk,
    compute_temporal_flicker,
    evaluate_audio_quality,
    evaluate_cover_layout_alignment,
    evaluate_output_damage,
    final_audio_target_lufs,
    include_dense_ui_interval_frames,
    include_phase1_completeness_frames,
    include_operator_approved_qa_frame,
    propagate_source_intrinsic_cjk_exclusions,
    select_qa_frame_indices,
    summarize_temporal_flicker_for_verdict,
)


class CompletenessFrameSelectionTests(unittest.TestCase):
    def test_untracked_phase1_candidates_are_carried_into_output_ocr_qa(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_dir = root / "qa" / "phase4_output"
            artifact_dir.mkdir(parents=True)
            (root / "phase1_candidate_windows_v1.json").write_text(
                json.dumps(
                    {
                        "policy_version": "audio_visual_temporal_policy_v9_completeness_first",
                        "fps": 30.0,
                        "hard_textness_frames": [7],
                        "completeness_candidate_frames": [10, 15, 20, 25],
                        "coverage_unassigned_candidate_frames": [41],
                        "coverage_residual_dbnet_frames": [41],
                        "policy": {"completeness_sample_fps": 6.0},
                    }
                ),
                encoding="utf-8",
            )
            selected = include_phase1_completeness_frames(
                [0, 59],
                artifact_dir=artifact_dir,
                decoded_frame_count=60,
            )
        self.assertIn(7, selected)
        self.assertIn(41, selected)
        self.assertEqual(selected[0], 0)
        self.assertEqual(selected[-1], 59)

    def test_hard_textness_frames_obey_heavy_ocr_budget(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_dir = root / "qa" / "phase4_output"
            artifact_dir.mkdir(parents=True)
            (root / "phase1_candidate_windows_v1.json").write_text(
                json.dumps(
                    {
                        "policy_version": (
                            "audio_visual_temporal_policy_v11_audio_authority_proxy_budget"
                        ),
                        "fps": 30.0,
                        "hard_textness_frames": list(range(1, 1_001, 2)),
                        "completeness_candidate_frames": [],
                        "coverage_unassigned_candidate_frames": [],
                        "coverage_residual_dbnet_frames": [],
                        "policy": {"completeness_sample_fps": 6.0},
                    }
                ),
                encoding="utf-8",
            )

            selected = include_phase1_completeness_frames(
                [0, 1_199],
                artifact_dir=artifact_dir,
                decoded_frame_count=1_200,
                max_added_frames=24,
            )

        self.assertLessEqual(len(set(selected) - {0, 1_199}), 24)
        self.assertIn(1, selected)
        self.assertIn(999, selected)


class ReusedVisualQaTests(unittest.TestCase):
    def test_exact_preview_packets_reuse_visual_qa_and_probe_only_final_audio(self) -> None:
        with TemporaryDirectory() as tmp:
            preview = Path(tmp) / "preview.mp4"
            final = Path(tmp) / "final.mp4"
            preview.write_bytes(b"preview")
            final.write_bytes(b"final")
            preview_qa = {
                "status": "PASS",
                "failed_checks": [],
                "checks": {
                    "duration": True,
                    "frame_count": True,
                    "color_authority": True,
                    "temporal_flicker": True,
                    "residual_ocr_complete": True,
                    "residual_cjk": True,
                    "outside_cover_damage": True,
                    "cover_layout_alignment": True,
                    "timeline_edit_coverage": True,
                    "protected_source_integrity": True,
                    "final_audio": True,
                },
                "media": {
                    "source_duration_seconds": 1.0,
                    "duration_tolerance_seconds": 0.08,
                    "expected_frame_count": 30,
                },
                "residual_cjk": {"complete": True, "detections": []},
            }
            authority = {
                "duration_seconds": 1.0,
                "frame_timestamps_seconds": [index / 30 for index in range(30)],
                "video": {
                    "color_range": "tv",
                    "color_space": "bt709",
                    "color_transfer": "bt709",
                    "color_primaries": "bt709",
                },
            }

            result = collect_reused_visual_output_qa(
                preview,
                final,
                preview_qa=preview_qa,
                contract={"video": {"frame_count": 30}, "authorities": {"audio": {}}},
                media_probe=lambda _path: authority,
                video_packet_probe=lambda _path: "a" * 64,
                audio_quality_probe=lambda _path: {
                    "present": True,
                    "audio_duration_seconds": 1.0,
                    "integrated_lufs": -14.0,
                    "true_peak_db": -1.5,
                    "measurement_complete": True,
                },
            )

            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["checks"]["visual_packet_authority"])
            self.assertEqual(result["audio"]["status"], "PASS")
            self.assertTrue(result["visual_authority_reuse"]["exact_packet_match"])


class OutputQaContactSheetTests(unittest.TestCase):
    def test_portrait_sheet_is_bounded_below_jpeg_height_limit(self) -> None:
        frame = np.zeros((16, 9, 3), dtype=np.uint8)
        indices = list(range(121))
        frames = {index: frame for index in indices}

        with patch("cv2.imwrite", return_value=True) as imwrite:
            _write_contact_sheet(Path("contact.jpg"), indices, frames, frames)

        sheet = imwrite.call_args.args[1]
        self.assertLessEqual(sheet.shape[0], OUTPUT_QA_CONTACT_SHEET_MAX_HEIGHT)
        self.assertEqual(sheet.shape[1], 1080)


class SourceSceneProtectedCjkTests(unittest.TestCase):
    @staticmethod
    def _detection(frame_index: int, *, y: float = 0.2) -> dict:
        return {
            "frame_index": frame_index,
            "text": "用餐时间",
            "confidence": 0.96,
            "geometry": {"x": 0.1, "y": y, "width": 0.12, "height": 0.04},
        }

    @staticmethod
    def _contract(*, with_editor: bool = False) -> dict:
        tracks = []
        if with_editor:
            tracks.append(
                {
                    "text_id": "sub_editor",
                    "kind": "hardsub",
                    "start_frame": 10,
                    "end_frame": 20,
                    "text_vi": "Bữa trưa",
                    "geometry": {"x": 0.08, "y": 0.18, "width": 0.3, "height": 0.08},
                    "render_policy": {
                        "cover": {
                            "roi": {"x": 0.08, "y": 0.18, "width": 0.3, "height": 0.08}
                        },
                        "layout": {
                            "safe_area": {"x": 0.08, "y": 0.18, "width": 0.3, "height": 0.08}
                        },
                    },
                }
            )
        return {
            "render_tracks": tracks,
            "source_scene_text_regions": [
                {
                    "region_id": "source_scene_dense_01",
                    "classification": "SOURCE_SCENE_TEXT",
                    "start_frame": 10,
                    "end_frame": 20,
                    "region_roi": {"x": 0.05, "y": 0.05, "width": 0.5, "height": 0.7},
                }
            ],
        }

    def test_source_scene_cjk_is_excluded_inside_active_protected_region(self) -> None:
        blocking, excluded = classify_source_scene_protected_cjk(
            [self._detection(15)], contract=self._contract()
        )
        self.assertEqual(blocking, [])
        self.assertEqual(excluded[0]["classification"], "SOURCE_SCENE_TEXT_PROTECTED")

    def test_editor_hardsub_overlap_remains_blocking(self) -> None:
        blocking, excluded = classify_source_scene_protected_cjk(
            [self._detection(15)], contract=self._contract(with_editor=True)
        )
        self.assertEqual(excluded, [])
        self.assertEqual(
            blocking[0]["source_scene_protection"]["status"],
            "BLOCKED_BY_ACTIVE_EDITOR_AUTHORITY",
        )

    def test_verified_source_ui_can_overlap_broad_editor_lane(self) -> None:
        detection = self._detection(15)
        detection["geometry"].update({"x": 0.30, "width": 0.05, "height": 0.04})
        contract = self._contract(with_editor=True)
        editor = contract["render_tracks"][0]
        editor["geometry"] = {
            "x": 0.08,
            "y": 0.18,
            "width": 0.10,
            "height": 0.08,
        }
        editor["render_policy"]["cover"]["roi"] = {
            "x": 0.08,
            "y": 0.18,
            "width": 0.30,
            "height": 0.08,
        }
        source_frame = np.full((100, 100, 3), 80, dtype=np.uint8)
        rendered_frame = source_frame.copy()
        blocking, excluded = classify_source_scene_protected_cjk(
            [detection],
            contract=contract,
            source_detections=[detection],
            source_frames={15: source_frame},
            rendered_frames={15: rendered_frame},
        )

        self.assertEqual(blocking, [])
        self.assertEqual(
            excluded[0]["classification"],
            "SOURCE_SCENE_TEXT_PROTECTED_OVERLAPPING_EDITOR_VERIFIED",
        )

    def test_supplemental_cover_residual_stays_blocking(self) -> None:
        contract = self._contract(with_editor=True)
        contract["render_tracks"][0]["render_policy"]["context"] = {
            "supplemental_cover_only": True
        }
        detection = self._detection(15)
        detection["geometry"].update({"width": 0.05, "height": 0.04})
        frame = np.full((100, 100, 3), 80, dtype=np.uint8)
        blocking, excluded = classify_source_scene_protected_cjk(
            [detection],
            contract=contract,
            source_detections=[detection],
            source_frames={15: frame},
            rendered_frames={15: frame.copy()},
        )

        self.assertEqual(excluded, [])
        self.assertEqual(
            blocking[0]["source_scene_protection"]["status"],
            "BLOCKED_BY_ACTIVE_EDITOR_AUTHORITY",
        )

    def test_source_scene_region_is_inactive_outside_frame_span(self) -> None:
        blocking, excluded = classify_source_scene_protected_cjk(
            [self._detection(21)], contract=self._contract()
        )
        self.assertEqual(len(blocking), 1)
        self.assertEqual(excluded, [])

    def test_large_layout_safe_area_does_not_claim_unrelated_source_ui(self) -> None:
        contract = self._contract(with_editor=True)
        editor = contract["render_tracks"][0]
        editor["geometry"] = {"x": 0.2, "y": 0.9, "width": 0.4, "height": 0.06}
        editor["render_policy"]["cover"]["roi"] = dict(editor["geometry"])
        editor["render_policy"]["layout"]["safe_area"] = {
            "x": 0.04,
            "y": 0.05,
            "width": 0.92,
            "height": 0.9,
        }
        blocking, excluded = classify_source_scene_protected_cjk(
            [self._detection(15)], contract=contract
        )
        self.assertEqual(blocking, [])
        self.assertEqual(excluded[0]["classification"], "SOURCE_SCENE_TEXT_PROTECTED")

    def test_wide_cjk_in_gap_between_editor_captions_remains_blocking(self) -> None:
        contract = self._contract()
        contract["source_scene_text_regions"][0]["region_roi"] = {
            "x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0
        }
        contract["render_tracks"] = [
            {
                "text_id": "before",
                "kind": "hardsub",
                "start_frame": 10,
                "end_frame": 12,
                "render_policy": {"cover": {"roi": {"x": 0.25, "y": 0.9, "width": 0.5, "height": 0.08}}},
            },
            {
                "text_id": "after",
                "kind": "hardsub",
                "start_frame": 18,
                "end_frame": 20,
                "render_policy": {"cover": {"roi": {"x": 0.25, "y": 0.9, "width": 0.5, "height": 0.08}}},
            },
        ]
        detection = self._detection(15, y=0.91)
        detection["geometry"].update({"x": 0.3, "width": 0.4, "height": 0.05})
        blocking, excluded = classify_source_scene_protected_cjk(
            [detection], contract=contract
        )
        self.assertEqual(excluded, [])
        self.assertEqual(
            blocking[0]["source_scene_protection"]["status"],
            "BLOCKED_BY_PERSISTENT_EDITOR_CAPTION_LANE",
        )


class QaSamplingTests(unittest.TestCase):
    def test_samples_start_mid_end_and_motion_peak(self) -> None:
        contract = {
            "video": {"frame_count": 100},
            "render_tracks": [
                {"text_id": "a", "start_frame": 10, "end_frame": 20},
                {"text_id": "b", "start_frame": 50, "end_frame": 60},
            ],
        }
        indices = select_qa_frame_indices(
            contract,
            motion_scores={17: 50.0, 56: 80.0},
            limit=20,
        )
        for expected in (10, 15, 17, 20, 21, 50, 55, 56, 60, 61):
            self.assertIn(expected, indices)

    def test_dense_track_boundaries_are_not_thinned_out(self) -> None:
        contract = {
            "video": {"frame_count": 2000},
            "render_tracks": [
                {"text_id": f"sub_{i}", "start_frame": i * 40, "end_frame": i * 40 + 38}
                for i in range(40)
            ],
        }
        indices = select_qa_frame_indices(contract, limit=20)
        self.assertTrue(all(i * 40 + 39 in indices for i in range(40)))
        self.assertLessEqual(len(indices), 66)

    def test_operator_approved_evidence_frame_is_always_sampled(self) -> None:
        indices = include_operator_approved_qa_frame(
            [0, 50, 99],
            decoded_frame_count=100,
            approval={"detection": {"frame_index": 42}},
        )

        self.assertEqual(indices, [0, 42, 50, 99])

    def test_dense_ui_short_interval_is_sampled_exhaustively(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "start_frame": 10,
                    "end_frame": 14,
                    "output_residual_coverage": {"status": "VERIFIED"},
                    "render_policy": {
                        "context": {"dense_ui": True, "simultaneous_count": 20}
                    },
                }
            ]
        }
        indices = include_dense_ui_interval_frames(
            [0, 50], contract, decoded_frame_count=60
        )
        self.assertEqual(indices, [0, 10, 11, 12, 13, 14, 50])

    def test_dense_ui_interval_cost_cap_preserves_bounded_sampler(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "start_frame": 0,
                    "end_frame": 120,
                    "output_residual_coverage": {"status": "VERIFIED"},
                    "render_policy": {
                        "context": {"dense_ui": True, "simultaneous_count": 20}
                    },
                },
                {
                    "start_frame": 200,
                    "end_frame": 320,
                    "output_residual_coverage": {"status": "VERIFIED"},
                    "render_policy": {
                        "context": {"dense_ui": True, "simultaneous_count": 20}
                    },
                },
            ]
        }
        indices = include_dense_ui_interval_frames(
            [0, 50], contract, decoded_frame_count=400, max_added_frames=180
        )
        self.assertEqual(indices, [0, 50])

    def test_editor_caption_epoch_is_scanned_at_ten_fps(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "kind": "hardsub",
                    "start_frame": 7,
                    "end_frame": 17,
                    "render_policy": {"context": {"dense_ui": True}},
                }
            ]
        }
        indices = include_dense_ui_interval_frames(
            [0], contract, decoded_frame_count=30
        )
        self.assertEqual(indices, [0, 7, 10, 13, 16, 17])


class CoverLayoutAlignmentTests(unittest.TestCase):
    @staticmethod
    def _contract(mode: str, safe_area: dict) -> dict:
        return {
            "render_tracks": [
                {
                    "text_id": "sub_02",
                    "kind": "hardsub",
                    "roles": ["hardsub"],
                    "render_policy": {
                        "context": {"source_kind": "hardsub"},
                        "cover": {
                            "roi": {"x": 0.25, "y": 0.90, "width": 0.5, "height": 0.08}
                        },
                        "layout": {"mode": mode, "safe_area": safe_area},
                    },
                }
            ]
        }

    def test_responsive_grid_caption_is_blocked(self) -> None:
        verdict = evaluate_cover_layout_alignment(
            self._contract(
                "responsive_grid",
                {"x": 0.04, "y": 0.05, "width": 0.92, "height": 0.9},
            )
        )
        self.assertEqual(verdict["status"], "BLOCKED")

    def test_cover_aligned_caption_passes(self) -> None:
        roi = {"x": 0.25, "y": 0.90, "width": 0.5, "height": 0.08}
        verdict = evaluate_cover_layout_alignment(
            self._contract("cover_aligned", roi)
        )
        self.assertEqual(verdict["status"], "PASS")


class EditorCaptionOcrFalsePositiveTests(unittest.TestCase):
    def test_low_confidence_unchanged_texture_inside_caption_is_excluded(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "text_id": "sub_01",
                    "start_frame": 10,
                    "end_frame": 30,
                    "text_vi": "Bữa này chuẩn bị 170 g cơm",
                    "geometry": {"x": 0.30, "y": 0.88, "width": 0.45, "height": 0.08},
                    "render_policy": {
                        "cover": {"roi": {"x": 0.28, "y": 0.86, "width": 0.49, "height": 0.12}},
                        "layout": {"safe_area": {"x": 0.28, "y": 0.86, "width": 0.49, "height": 0.12}},
                    },
                }
            ]
        }
        row = {
            "frame_index": 20,
            "text": "福",
            "confidence": 0.25,
            "geometry": {"x": 0.46, "y": 0.89, "width": 0.03, "height": 0.03},
        }
        frame = np.full((100, 200, 3), 90, dtype=np.uint8)

        kept, excluded = classify_editor_caption_ocr_false_positives(
            [row],
            contract=contract,
            source_frames={20: frame},
            rendered_frames={20: frame.copy()},
        )

        self.assertEqual(kept, [])
        self.assertEqual(
            excluded[0]["classification"],
            "EDITOR_CAPTION_TEXTURE_OCR_FALSE_POSITIVE",
        )

    def test_mostly_latin_vietnamese_with_one_cjk_misread_is_excluded(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "text_id": "sub_117",
                    "start_frame": 995,
                    "end_frame": 1044,
                    "text_vi": "Chỉ vài chục tệ là mua được",
                    "geometry": {"x": 0.33, "y": 0.91, "width": 0.35, "height": 0.07},
                    "render_policy": {
                        "cover": {"roi": {"x": 0.32, "y": 0.90, "width": 0.37, "height": 0.09}},
                        "layout": {"safe_area": {"x": 0.32, "y": 0.90, "width": 0.37, "height": 0.09}},
                    },
                }
            ]
        }
        kept, excluded = classify_editor_caption_ocr_false_positives(
            [
                {
                    "frame_index": 995,
                    "text": "Chi vai chuc t 間 mua duoc",
                    "geometry": {"x": 0.34, "y": 0.935, "width": 0.325, "height": 0.03},
                }
            ],
            contract=contract,
        )
        self.assertEqual(kept, [])
        self.assertEqual(excluded[0]["matched_text_id"], "sub_117")

    def test_cjk_prefix_in_editor_caption_is_blocking_residual(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "text_id": "sub_28",
                    "start_frame": 188,
                    "end_frame": 439,
                    "text_vi": "Có thể chuyển đổi theo nhu cầu",
                    "geometry": {"x": 0.30, "y": 0.92, "width": 0.52, "height": 0.06},
                    "render_policy": {
                        "cover": {"roi": {"x": 0.16, "y": 0.89, "width": 0.64, "height": 0.11}},
                        "layout": {"safe_area": {"x": 0.02, "y": 0.80, "width": 0.95, "height": 0.17}},
                    },
                }
            ]
        }
        kept, excluded = classify_editor_caption_ocr_false_positives(
            [
                {
                    "frame_index": 188,
                    "text": "连热 Cothe chuyendoi theo nhu cau",
                    "geometry": {"x": 0.20, "y": 0.92, "width": 0.47, "height": 0.05},
                }
            ],
            contract=contract,
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(excluded, [])


class TemporalFlickerVerdictTests(unittest.TestCase):
    def test_cover_aligned_caption_uses_motion_tolerant_limit(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "kind": "hardsub",
                    "start_frame": 10,
                    "end_frame": 20,
                    "render_policy": {"layout": {"mode": "cover_aligned"}},
                }
            ]
        }

        summary = summarize_temporal_flicker_for_verdict(
            [{"frame_index": 15, "extra_flicker_max": 10.5}],
            contract=contract,
        )

        self.assertEqual(summary["max_extra_flicker"], 10.5)
        self.assertEqual(summary["limit"], 12.0)

    def test_caption_boundaries_are_not_blocking_flicker(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "kind": "hardsub",
                    "start_frame": 10,
                    "end_frame": 20,
                    "render_policy": {
                        "cover": {"strategy": "editor_caption_full_lane_plate"}
                    },
                }
            ]
        }
        summary = summarize_temporal_flicker_for_verdict(
            [
                {"frame_index": 10, "extra_flicker_max": 50.0},
                {"frame_index": 15, "extra_flicker_max": 12.0},
            ],
            contract=contract,
        )
        self.assertEqual(summary["max_extra_flicker"], 12.0)
        self.assertEqual(summary["limit"], 16.0)

    def test_overlap_transition_boundary_remains_blocking(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "kind": "hardsub",
                    "start_frame": 10,
                    "end_frame": 20,
                    "cover_start_frame": 10,
                    "cover_end_frame": 20,
                    "render_policy": {
                        "cover": {
                            "strategy": "soft_reconstruction_plate_v1",
                            "transition_hold_frames": 3,
                        }
                    },
                },
                {
                    "kind": "hardsub",
                    "start_frame": 21,
                    "end_frame": 30,
                    "cover_start_frame": 21,
                    "cover_end_frame": 30,
                    "render_policy": {
                        "cover": {
                            "strategy": "soft_reconstruction_plate_v1",
                            "transition_hold_frames": 3,
                        }
                    },
                },
            ]
        }

        summary = summarize_temporal_flicker_for_verdict(
            [{"frame_index": 20, "extra_flicker_max": 50.0}],
            contract=contract,
        )

        self.assertEqual(summary["max_extra_flicker"], 50.0)
        self.assertEqual(
            summary["frames"][0]["blocking_boundary"],
            "ACTIVE_COVER_TRANSITION",
        )


class TemporalFlickerTests(unittest.TestCase):
    def test_identical_temporal_change_has_zero_extra_flicker(self) -> None:
        source = [
            np.full((20, 20, 3), value, dtype=np.uint8) for value in (50, 55, 60)
        ]
        mask = np.ones((20, 20), dtype=np.uint8) * 255
        result = compute_temporal_flicker(source, source, mask)
        self.assertEqual(result["extra_flicker_mean"], 0.0)

    def test_flashing_render_is_detected(self) -> None:
        source = [np.full((20, 20, 3), 50, dtype=np.uint8) for _ in range(3)]
        rendered = [
            np.full((20, 20, 3), value, dtype=np.uint8) for value in (50, 180, 50)
        ]
        mask = np.ones((20, 20), dtype=np.uint8) * 255
        result = compute_temporal_flicker(source, rendered, mask)
        self.assertGreater(result["extra_flicker_mean"], 100.0)

    def test_motion_revealed_under_source_glyph_is_not_flicker(self) -> None:
        source = [
            np.full((40, 40, 3), 50, dtype=np.uint8),
            np.full((40, 40, 3), 50, dtype=np.uint8),
        ]
        rendered = [frame.copy() for frame in source]
        # The source glyph occludes a moving patch. The cleaned output reveals
        # the same local motion at the glyph position.
        source[1][17:24, 17:24] = 120
        rendered[1][12:29, 12:29] = 120
        mask = np.ones((40, 40), dtype=np.uint8) * 255
        result = compute_temporal_flicker(source, rendered, mask)
        naive_extra = float(
            np.abs(rendered[1].astype(np.float32) - rendered[0].astype(np.float32))
            .mean(axis=2)
            .mean()
        )
        self.assertLess(result["extra_flicker_mean"], naive_extra * 0.75)


class OutputDamageTests(unittest.TestCase):
    def test_damage_outside_cover_is_blocking(self) -> None:
        source = np.full((60, 80, 3), 100, dtype=np.uint8)
        rendered = source.copy()
        allowed = np.zeros((60, 80), dtype=np.uint8)
        allowed[20:40, 30:50] = 255
        rendered[0:15, 0:20] = 240
        result = evaluate_output_damage(source, rendered, allowed)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("outside_cover_damage", result["blocked_reasons"])


class OutputQaVerdictTests(unittest.TestCase):
    def test_residual_cjk_or_flicker_blocks_output(self) -> None:
        verdict = build_output_qa_verdict(
            duration_match=True,
            frame_count_match=True,
            color_authority_match=True,
            max_extra_flicker=12.0,
            residual_cjk=[{"frame_index": 10, "text": "午餐"}],
            outside_damage_blocked=False,
        )
        self.assertEqual(verdict["status"], "FAIL")
        self.assertIn("residual_cjk", verdict["failed_checks"])
        self.assertIn("temporal_flicker", verdict["failed_checks"])

    def test_missing_residual_ocr_is_fail_closed(self) -> None:
        verdict = build_output_qa_verdict(
            duration_match=True,
            frame_count_match=True,
            color_authority_match=True,
            max_extra_flicker=0.0,
            residual_cjk=[],
            outside_damage_blocked=False,
            residual_ocr_complete=False,
        )
        self.assertEqual(verdict["status"], "FAIL")
        self.assertIn("residual_ocr_complete", verdict["failed_checks"])

    def test_final_audio_duration_or_loudness_failure_blocks_output(self) -> None:
        verdict = build_output_qa_verdict(
            duration_match=True,
            frame_count_match=True,
            color_authority_match=True,
            max_extra_flicker=0.0,
            residual_cjk=[],
            outside_damage_blocked=False,
            final_audio_passed=False,
        )
        self.assertEqual(verdict["status"], "FAIL")
        self.assertIn("final_audio", verdict["failed_checks"])

    def test_unchanged_source_strokes_block_output_even_without_ocr_hit(self) -> None:
        verdict = build_output_qa_verdict(
            duration_match=True,
            frame_count_match=True,
            color_authority_match=True,
            max_extra_flicker=0.0,
            residual_cjk=[],
            outside_damage_blocked=False,
            residual_stroke_removal=False,
        )

        self.assertEqual(verdict["status"], "FAIL")
        self.assertIn("residual_stroke_removal", verdict["failed_checks"])


class SourceIntrinsicCjkClassificationTests(unittest.TestCase):
    @staticmethod
    def _row(x: float, text: str = "图所示") -> dict:
        return {
            "frame_index": 20,
            "text": text,
            "confidence": 0.9,
            "geometry": {"x": x, "y": 0.5, "width": 0.03, "height": 0.03},
        }

    def test_small_source_matched_edge_print_is_non_blocking(self) -> None:
        rendered = self._row(0.94)
        source = self._row(0.941)
        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [rendered], [source], contract={"render_tracks": []}
        )
        self.assertEqual(blocking, [])
        self.assertEqual(excluded[0]["classification"], "SOURCE_INTRINSIC_EDGE_PRINT")

    def test_central_or_authorized_text_remains_blocking(self) -> None:
        central = self._row(0.10, "170克")
        blocking, _ = classify_source_intrinsic_edge_cjk(
            [central], [central], contract={"render_tracks": []}
        )
        self.assertEqual(blocking, [central])

        edge = self._row(0.94)
        contract = {
            "render_tracks": [
                {
                    "start_frame": 10,
                    "end_frame": 30,
                    "render_policy": {
                        "cover": {
                            "roi": {
                                "x": 0.92,
                                "y": 0.48,
                                "width": 0.07,
                                "height": 0.08,
                            }
                        }
                    },
                }
            ]
        }
        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [edge], [edge], contract=contract
        )
        self.assertEqual(blocking, [edge])
        self.assertEqual(excluded, [])

    @staticmethod
    def _tiny_tall_row() -> dict:
        return {
            "frame_index": 20,
            "text": "\u798f",
            "confidence": 0.85,
            "geometry": {"x": 0.63, "y": 0.06, "width": 0.01, "height": 0.05},
        }

    def test_tiny_source_stable_texture_false_positive_is_non_blocking(self) -> None:
        row = self._tiny_tall_row()
        source_frame = np.full((100, 200, 3), 90, dtype=np.uint8)
        rendered_frame = np.full((100, 200, 3), 92, dtype=np.uint8)
        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [],
            contract={"render_tracks": []},
            source_frames={20: source_frame},
            rendered_frames={20: rendered_frame},
        )
        self.assertEqual(blocking, [])
        self.assertEqual(
            excluded[0]["classification"],
            "SOURCE_INTRINSIC_TEXTURE_FALSE_POSITIVE",
        )

    def test_real_rendered_cjk_change_remains_blocking(self) -> None:
        row = self._tiny_tall_row()
        source_frame = np.full((100, 200, 3), 240, dtype=np.uint8)
        rendered_frame = source_frame.copy()
        rendered_frame[6:11, 126:128] = 20
        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [],
            contract={"render_tracks": []},
            source_frames={20: source_frame},
            rendered_frames={20: rendered_frame},
        )
        self.assertEqual(blocking, [row])
        self.assertEqual(excluded, [])

    def test_low_confidence_small_source_texture_is_non_blocking(self) -> None:
        row = {
            "frame_index": 20,
            "text": "\u798f",
            "confidence": 0.4112,
            "geometry": {"x": 0.63, "y": 0.06, "width": 0.016, "height": 0.045},
        }
        source_row = {
            **row,
            "confidence": 0.2921,
            "geometry": {"x": 0.63, "y": 0.058, "width": 0.016, "height": 0.052},
        }
        source_frame = np.full((500, 1000, 3), 90, dtype=np.uint8)
        rendered_frame = np.full((500, 1000, 3), 92, dtype=np.uint8)

        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [source_row],
            contract={"render_tracks": []},
            source_frames={20: source_frame},
            rendered_frames={20: rendered_frame},
        )

        self.assertEqual(blocking, [])
        self.assertEqual(excluded[0]["policy_branch"], "low_confidence_texture")

    def test_low_confidence_bounded_scene_texture_is_non_blocking(self) -> None:
        row = {
            "frame_index": 20,
            "text": "\u798f",
            "confidence": 0.49,
            "geometry": {"x": 0.56, "y": 0.0, "width": 0.21, "height": 0.61},
        }
        source_frame = np.full((100, 200, 3), 90, dtype=np.uint8)
        rendered_frame = np.full((100, 200, 3), 92, dtype=np.uint8)
        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [],
            contract={"render_tracks": []},
            source_frames={20: source_frame},
            rendered_frames={20: rendered_frame},
        )
        self.assertEqual(blocking, [])
        self.assertEqual(excluded[0]["policy_branch"], "bounded_source_texture")

    def test_low_confidence_multi_glyph_object_print_is_non_blocking(self) -> None:
        row = {
            "frame_index": 20,
            "text": "美虾",
            "confidence": 0.6023,
            "geometry": {"x": 0.24, "y": 0.84, "width": 0.46, "height": 0.11},
        }
        source_frame = np.full((500, 1000, 3), 90, dtype=np.uint8)
        rendered_frame = np.full((500, 1000, 3), 92, dtype=np.uint8)

        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [],
            contract={"render_tracks": []},
            source_frames={20: source_frame},
            rendered_frames={20: rendered_frame},
        )

        self.assertEqual(blocking, [])
        self.assertEqual(excluded[0]["policy_branch"], "object_print_unchanged")

    def test_medium_confidence_tall_reflection_texture_is_non_blocking(self) -> None:
        row = {
            "frame_index": 20,
            "text": "福",
            "confidence": 0.79,
            "geometry": {"x": 0.70, "y": 0.37, "width": 0.10, "height": 0.31},
        }
        frame = np.full((500, 1000, 3), 90, dtype=np.uint8)

        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [row],
            contract={"render_tracks": []},
            source_frames={20: frame},
            rendered_frames={20: frame.copy()},
        )

        self.assertEqual(blocking, [])
        self.assertEqual(excluded[0]["policy_branch"], "bounded_source_texture")

    def test_source_matched_medium_scene_texture_is_non_blocking(self) -> None:
        row = {
            "frame_index": 20,
            "text": "福",
            "confidence": 0.65,
            "geometry": {"x": 0.58, "y": 0.80, "width": 0.06, "height": 0.08},
        }
        frame = np.full((500, 1000, 3), 90, dtype=np.uint8)

        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [row],
            contract={"render_tracks": []},
            source_frames={20: frame},
            rendered_frames={20: frame.copy()},
        )

        self.assertEqual(blocking, [])
        self.assertEqual(excluded[0]["policy_branch"], "bounded_source_texture")

    def test_high_confidence_same_size_source_glyph_remains_blocking(self) -> None:
        row = {
            "frame_index": 20,
            "text": "\u798f",
            "confidence": 0.85,
            "geometry": {"x": 0.63, "y": 0.06, "width": 0.016, "height": 0.045},
        }
        frame = np.full((500, 1000, 3), 90, dtype=np.uint8)

        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [row],
            contract={"render_tracks": []},
            source_frames={20: frame},
            rendered_frames={20: frame.copy()},
        )

        self.assertEqual(blocking, [row])
        self.assertEqual(excluded, [])

    def test_small_low_confidence_source_matched_print_is_non_blocking(self) -> None:
        rendered = {
            "frame_index": 20,
            "text": "\u798f",
            "confidence": 0.85,
            "geometry": {"x": 0.304, "y": 0.445, "width": 0.044, "height": 0.026},
        }
        source = {
            **rendered,
            "confidence": 0.31,
            "geometry": {"x": 0.319, "y": 0.448, "width": 0.023, "height": 0.018},
        }
        source_frame = np.full((500, 1000, 3), 90, dtype=np.uint8)
        rendered_frame = np.full((500, 1000, 3), 92, dtype=np.uint8)

        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [rendered],
            [source],
            contract={"render_tracks": []},
            source_frames={20: source_frame},
            rendered_frames={20: rendered_frame},
        )

        self.assertEqual(blocking, [])
        self.assertEqual(
            excluded[0]["policy_branch"],
            "small_matched_unchanged_source_print",
        )

    def test_small_source_matched_glyph_inside_editor_cover_remains_blocking(self) -> None:
        row = {
            "frame_index": 20,
            "text": "\u798f",
            "confidence": 0.35,
            "geometry": {"x": 0.304, "y": 0.445, "width": 0.044, "height": 0.026},
        }
        frame = np.full((500, 1000, 3), 90, dtype=np.uint8)
        contract = {
            "render_tracks": [
                {
                    "start_frame": 10,
                    "end_frame": 30,
                    "render_policy": {
                        "cover": {
                            "roi": {"x": 0.28, "y": 0.42, "width": 0.10, "height": 0.08}
                        }
                    },
                }
            ]
        }

        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [row],
            contract=contract,
            source_frames={20: frame},
            rendered_frames={20: frame.copy()},
        )

        self.assertEqual(blocking, [row])
        self.assertEqual(excluded, [])

    def test_adjacent_pixel_proven_texture_inherits_source_intrinsic_exclusion(
        self,
    ) -> None:
        proven = {
            "frame_index": 328,
            "text": "\u7535",
            "confidence": 0.81,
            "geometry": {
                "x": 0.177,
                "y": 0.813,
                "width": 0.049,
                "height": 0.026,
            },
            "classification": "SOURCE_INTRINSIC_TEXTURE_FALSE_POSITIVE",
            "policy_branch": "bounded_source_texture",
            "source_render_patch": {
                "mean_abs_delta": 1.2,
                "p95_abs_delta": 4.0,
                "pixel_aspect": 1.1,
            },
        }
        adjacent = {
            **proven,
            "frame_index": 329,
            "confidence": 0.8666,
            "geometry": {
                "x": 0.1774,
                "y": 0.8135,
                "width": 0.0489,
                "height": 0.0258,
            },
        }
        adjacent.pop("classification")
        adjacent.pop("policy_branch")
        adjacent.pop("source_render_patch")

        blocking, excluded = propagate_source_intrinsic_cjk_exclusions(
            [adjacent],
            [proven],
            contract={"render_tracks": []},
        )

        self.assertEqual(blocking, [])
        self.assertEqual(
            excluded[0]["classification"],
            "SOURCE_INTRINSIC_TEMPORAL_PROPAGATION_FALSE_POSITIVE",
        )
        self.assertEqual(
            excluded[0]["matched_source_intrinsic_provenance"]["frame_index"],
            328,
        )

    def test_real_editor_caption_is_not_excluded_by_adjacent_texture_provenance(
        self,
    ) -> None:
        proven = {
            "frame_index": 328,
            "text": "\u7535",
            "confidence": 0.81,
            "geometry": {"x": 0.177, "y": 0.813, "width": 0.049, "height": 0.026},
            "classification": "SOURCE_INTRINSIC_TEXTURE_FALSE_POSITIVE",
            "policy_branch": "bounded_source_texture",
            "source_render_patch": {
                "mean_abs_delta": 1.2,
                "p95_abs_delta": 4.0,
                "pixel_aspect": 1.1,
            },
        }
        editor_caption = {
            "frame_index": 329,
            "text": "\u7535",
            "confidence": 0.92,
            "geometry": {"x": 0.178, "y": 0.814, "width": 0.049, "height": 0.026},
        }
        contract = {
            "render_tracks": [
                {
                    "start_frame": 329,
                    "end_frame": 340,
                    "render_policy": {
                        "cover": {
                            "roi": {
                                "x": 0.17,
                                "y": 0.80,
                                "width": 0.07,
                                "height": 0.06,
                            }
                        }
                    },
                }
            ]
        }

        blocking, excluded = propagate_source_intrinsic_cjk_exclusions(
            [editor_caption],
            [proven],
            contract=contract,
        )

        self.assertEqual(blocking, [editor_caption])
        self.assertEqual(excluded, [])

    def test_exclusion_without_pixel_provenance_does_not_propagate(self) -> None:
        proven = {
            "frame_index": 328,
            "text": "\u7535",
            "confidence": 0.81,
            "geometry": {"x": 0.177, "y": 0.813, "width": 0.049, "height": 0.026},
            "classification": "SOURCE_INTRINSIC_EDGE_PRINT",
        }
        adjacent = {**proven, "frame_index": 329}
        adjacent.pop("classification")

        blocking, excluded = propagate_source_intrinsic_cjk_exclusions(
            [adjacent],
            [proven],
            contract={"render_tracks": []},
        )

        self.assertEqual(blocking, [adjacent])
        self.assertEqual(excluded, [])

    def test_large_unchanged_scene_texture_hallucination_is_non_blocking(self) -> None:
        row = {
            "frame_index": 20,
            "text": "福",
            "confidence": 0.88,
            "geometry": {"x": 0.28, "y": 0.38, "width": 0.30, "height": 0.53},
        }
        frame = np.full((500, 1000, 3), 90, dtype=np.uint8)

        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [],
            contract={"render_tracks": []},
            source_frames={20: frame},
            rendered_frames={20: frame.copy()},
        )

        self.assertEqual(blocking, [])
        self.assertEqual(
            excluded[0]["policy_branch"], "large_unchanged_scene_texture"
        )

    def test_unchanged_edge_source_print_without_matching_ocr_is_non_blocking(self) -> None:
        row = {
            "frame_index": 20,
            "text": "安全说明",
            "confidence": 0.9,
            "geometry": {"x": 0.92, "y": 0.42, "width": 0.06, "height": 0.05},
        }
        frame = np.full((100, 200, 3), 90, dtype=np.uint8)

        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [],
            contract={"render_tracks": []},
            source_frames={20: frame},
            rendered_frames={20: frame.copy()},
        )

        self.assertEqual(blocking, [])
        self.assertEqual(
            excluded[0]["policy_branch"], "edge_unchanged_source_print"
        )

    def test_wide_low_confidence_food_texture_is_non_blocking(self) -> None:
        row = {
            "frame_index": 20,
            "text": "福",
            "confidence": 0.25,
            "geometry": {
                "x": 0.46,
                "y": 0.88,
                "width": 0.0325,
                "height": 0.0275,
            },
        }
        frame = np.full((108, 192, 3), 90, dtype=np.uint8)

        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [],
            contract={"render_tracks": []},
            source_frames={20: frame},
            rendered_frames={20: frame.copy()},
        )

        self.assertEqual(blocking, [])
        self.assertEqual(
            excluded[0]["policy_branch"], "wide_low_confidence_texture"
        )

    def test_wide_low_confidence_food_texture_detector_expansion_is_non_blocking(self) -> None:
        row = {
            "frame_index": 20,
            "text": "福",
            "confidence": 0.37,
            "geometry": {
                "x": 0.58,
                "y": 0.81,
                "width": 0.059,
                "height": 0.061,
            },
        }
        source = np.full((720, 1280, 3), 90, dtype=np.uint8)
        rendered = source.copy()
        rendered[583:628, 742:820] = 92

        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [],
            contract={"render_tracks": []},
            source_frames={20: source},
            rendered_frames={20: rendered},
        )

        self.assertEqual(blocking, [])
        self.assertEqual(
            excluded[0]["policy_branch"], "wide_low_confidence_texture"
        )

    def test_tiny_source_stable_candidate_in_active_cover_remains_blocking(self) -> None:
        row = self._tiny_tall_row()
        frame = np.full((100, 200, 3), 90, dtype=np.uint8)
        contract = {
            "render_tracks": [
                {
                    "start_frame": 10,
                    "end_frame": 30,
                    "render_policy": {
                        "cover": {
                            "roi": {
                                "x": 0.62,
                                "y": 0.04,
                                "width": 0.04,
                                "height": 0.10,
                            }
                        }
                    },
                }
            ]
        }
        blocking, excluded = classify_source_intrinsic_edge_cjk(
            [row],
            [],
            contract=contract,
            source_frames={20: frame},
            rendered_frames={20: frame.copy()},
        )
        self.assertEqual(blocking, [row])
        self.assertEqual(excluded, [])

    def test_single_frame_cjk_is_fail_closed_without_neighbor(self) -> None:
        row = self._row(0.63, "福")
        blocking, excluded = classify_temporally_unconfirmed_cjk(
            [row],
            [],
            contract={"render_tracks": []},
            frame_count=30,
        )

        self.assertEqual(excluded, [])
        self.assertEqual(
            blocking[0]["temporal_confirmation"]["status"],
            "SINGLE_FRAME_CJK_FAIL_CLOSED",
        )

    def test_low_confidence_glyph_on_caption_plate_edge_is_excluded(self) -> None:
        row = {
            "frame_index": 20,
            "text": "\u56cd",
            "confidence": 0.3254,
            "geometry": {
                "x": 0.32,
                "y": 0.819,
                "width": 0.031,
                "height": 0.022,
            },
        }
        contract = {
            "render_tracks": [
                {
                    "text_id": "caption",
                    "start_frame": 20,
                    "end_frame": 30,
                    "kind": "ui",
                    "text_vi": "Đã đỡ hơn nhiều rồi.",
                    "render_policy": {
                        "context": {"caption_row": True},
                        "cover": {
                            "roi": {
                                "x": 0.0,
                                "y": 0.712,
                                "width": 1.0,
                                "height": 0.100,
                            }
                        },
                    },
                }
            ]
        }
        blocking, excluded = classify_temporally_unconfirmed_cjk(
            [row],
            [],
            contract=contract,
            frame_count=40,
        )

        self.assertEqual(blocking, [])
        self.assertEqual(
            excluded[0]["classification"],
            "EDITOR_CAPTION_EDGE_TEXTURE_FALSE_POSITIVE",
        )

    def test_low_confidence_plate_texture_in_cover_tail_is_excluded(self) -> None:
        row = {
            "frame_index": 31,
            "text": "老线",
            "confidence": 0.2671,
            "geometry": {
                "x": 0.34,
                "y": 0.782,
                "width": 0.102,
                "height": 0.017,
            },
        }
        contract = {
            "render_tracks": [
                {
                    "text_id": "caption_tail",
                    "start_frame": 20,
                    "end_frame": 30,
                    "cover_start_frame": 20,
                    "cover_end_frame": 32,
                    "kind": "ui",
                    "roles": ["generic"],
                    "cover_only": True,
                    "text_vi": "",
                    "geometry": {
                        "x": 0.02,
                        "y": 0.74,
                        "width": 0.96,
                        "height": 0.05,
                    },
                    "render_policy": {
                        "context": {
                            "caption_row": True,
                            "micro_ui": False,
                            "source_kind": "ui",
                        },
                        "cover": {
                            "roi": {
                                "x": 0.01,
                                "y": 0.735,
                                "width": 0.98,
                                "height": 0.055,
                            }
                        },
                    },
                }
            ]
        }

        blocking, excluded = classify_editor_caption_ocr_false_positives(
            [row], contract=contract
        )

        self.assertEqual(blocking, [])
        self.assertEqual(
            excluded[0]["classification"],
            "BLUR_ONLY_PLATE_EDGE_OCR_FALSE_POSITIVE",
        )

    def test_adjacent_same_geometry_residual_remains_blocking(self) -> None:
        row = self._row(0.63, "福")
        confirmation = dict(row)
        confirmation["frame_index"] = 19
        blocking, excluded = classify_temporally_unconfirmed_cjk(
            [row],
            [confirmation],
            contract={"render_tracks": []},
            frame_count=30,
        )

        self.assertEqual(len(blocking), 1)
        self.assertEqual(
            blocking[0]["temporal_confirmation"]["status"],
            "CONFIRMED_ON_ADJACENT_FRAME",
        )
        self.assertEqual(excluded, [])

    def test_adjacent_nested_texture_box_does_not_confirm_residual(self) -> None:
        row = self._row(0.63, "福")
        confirmation = dict(row)
        confirmation["frame_index"] = 19
        confirmation["geometry"] = {
            "x": 0.635,
            "y": 0.505,
            "width": 0.006,
            "height": 0.012,
        }
        blocking, excluded = classify_temporally_unconfirmed_cjk(
            [row],
            [confirmation],
            contract={"render_tracks": []},
            frame_count=30,
        )

        self.assertEqual(excluded, [])
        self.assertEqual(
            blocking[0]["temporal_confirmation"]["status"],
            "SINGLE_FRAME_CJK_FAIL_CLOSED",
        )

    def test_single_frame_authority_residual_stays_blocking_without_neighbor(self) -> None:
        row = self._row(0.63, "福")
        contract = {
            "render_tracks": [
                {
                    "start_frame": 20,
                    "end_frame": 20,
                    "render_policy": {
                        "cover": {
                            "roi": {
                                "x": 0.62,
                                "y": 0.48,
                                "width": 0.04,
                                "height": 0.10,
                            }
                        }
                    },
                }
            ]
        }
        blocking, excluded = classify_temporally_unconfirmed_cjk(
            [row],
            [],
            contract=contract,
            frame_count=30,
        )

        self.assertEqual(len(blocking), 1)
        self.assertEqual(
            blocking[0]["temporal_confirmation"]["status"],
            "NOT_APPLICABLE_SINGLE_FRAME_AUTHORITY",
        )
        self.assertEqual(excluded, [])

    def test_source_confirmed_post_end_residual_stays_blocking(self) -> None:
        row = self._row(0.63, "\u798f")
        row["frame_index"] = 21
        source = dict(row)
        contract = {
            "render_tracks": [
                {
                    "text_id": "sub_boundary",
                    "start_frame": 10,
                    "end_frame": 20,
                    "render_policy": {
                        "cover": {
                            "roi": {
                                "x": 0.62,
                                "y": 0.48,
                                "width": 0.04,
                                "height": 0.10,
                            }
                        }
                    },
                }
            ]
        }

        blocking, excluded = classify_temporally_unconfirmed_cjk(
            [row],
            [],
            contract=contract,
            frame_count=30,
            source_detections=[source],
        )

        self.assertEqual(len(blocking), 1)
        self.assertEqual(
            blocking[0]["temporal_confirmation"]["status"],
            "SOURCE_CONFIRMED_POST_END_BOUNDARY_RESIDUAL",
        )
        self.assertEqual(
            blocking[0]["temporal_confirmation"][
                "trailing_authority_text_ids"
            ],
            ["sub_boundary"],
        )
        self.assertEqual(excluded, [])


class AudioQualityTests(unittest.TestCase):
    def test_full_duration_normalized_audio_passes(self) -> None:
        result = evaluate_audio_quality(
            present=True,
            audio_duration_seconds=27.13,
            expected_duration_seconds=27.133,
            integrated_lufs=-14.2,
            true_peak_db=-1.6,
            measurement_complete=True,
        )
        self.assertEqual(result["status"], "PASS")

    def test_truncated_or_clipping_audio_fails(self) -> None:
        result = evaluate_audio_quality(
            present=True,
            audio_duration_seconds=18.0,
            expected_duration_seconds=27.0,
            integrated_lufs=-9.0,
            true_peak_db=0.2,
            measurement_complete=True,
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("audio_duration_mismatch", result["failed_checks"])
        self.assertIn("audio_true_peak", result["failed_checks"])

    def test_verified_no_dialogue_source_audio_uses_music_safe_reference(self) -> None:
        contract = {
            "authorities": {
                "audio": {
                    "strategy": "preserve_verified_no_dialogue_source_audio"
                }
            }
        }

        self.assertEqual(final_audio_target_lufs(contract), -16.0)
        result = evaluate_audio_quality(
            present=True,
            audio_duration_seconds=32.766,
            expected_duration_seconds=32.766667,
            integrated_lufs=-17.6,
            true_peak_db=-2.38,
            measurement_complete=True,
            target_lufs=final_audio_target_lufs(contract),
        )
        self.assertEqual(result["status"], "PASS")

    def test_dialogue_audio_keeps_short_form_speech_reference(self) -> None:
        contract = {
            "authorities": {
                "audio": {"strategy": "replace_with_vietnamese_narration"}
            }
        }

        self.assertEqual(final_audio_target_lufs(contract), -14.0)


class EditAuthorityMaskTests(unittest.TestCase):
    def test_mask_contains_active_dense_ui_panel_only_inside_epoch(self) -> None:
        contract = {
            "render_tracks": [],
            "dense_ui_panels": [
                {
                    "start_frame": 10,
                    "end_frame": 12,
                    "panel_roi": {"x": 0.2, "y": 0.1, "width": 0.3, "height": 0.4},
                }
            ],
        }
        active = allowed_edit_mask_for_frame(contract, 11, (100, 100))
        inactive = allowed_edit_mask_for_frame(contract, 13, (100, 100))
        self.assertEqual(int(active[20, 30]), 255)
        self.assertEqual(int(active[70, 30]), 0)
        self.assertEqual(int(inactive.max()), 0)

    def test_mask_contains_cover_and_layout_but_only_while_active(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "start_frame": 2,
                    "end_frame": 4,
                    "text_vi": "Bữa trưa",
                    "geometry": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
                    "render_policy": {
                        "cover": {"roi": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1}},
                        "layout": {"safe_area": {"x": 0.6, "y": 0.6, "width": 0.2, "height": 0.2}},
                    },
                }
            ]
        }
        active = allowed_edit_mask_for_frame(contract, 3, (100, 100))
        inactive = allowed_edit_mask_for_frame(contract, 5, (100, 100))
        self.assertEqual(int(active[15, 15]), 255)
        self.assertEqual(int(active[70, 70]), 255)
        self.assertEqual(int(active[40, 40]), 0)
        self.assertEqual(int(inactive.max()), 0)

    def test_transition_hold_allows_cover_but_not_early_text_layout(self) -> None:
        contract = {
            "render_tracks": [
                {
                    "start_frame": 10,
                    "end_frame": 20,
                    "text_vi": "Nhãn Việt",
                    "render_policy": {
                        "cover": {
                            "roi": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1},
                            "transition_hold_frames": 2,
                        },
                        "layout": {
                            "safe_area": {"x": 0.6, "y": 0.6, "width": 0.2, "height": 0.2}
                        },
                    },
                }
            ]
        }

        held = allowed_edit_mask_for_frame(contract, 8, (100, 100))

        self.assertEqual(int(held[15, 15]), 255)
        self.assertEqual(int(held[70, 70]), 0)


class OutputQaCollectorContractTests(unittest.TestCase):
    def test_collector_is_exposed_for_encoded_media_qa(self) -> None:
        self.assertTrue(callable(collect_adaptive_output_qa))
        self.assertTrue(callable(build_local_residual_ocr_provider))


if __name__ == "__main__":
    unittest.main()
