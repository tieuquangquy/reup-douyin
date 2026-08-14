from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.media_pipeline.video_renderer.phase4_input_contract import (
    Phase4InputError,
    _apply_geometry_overrides,
    _collapse_residual_caption_cover_groups,
    _kind_for_roles,
    _normalize_shared_caption_boundaries,
    _rects_overlap,
    _resolve_protected_caption_shadow_ids,
    _resolve_phase1_source_path,
    _suppress_weak_caption_fragments,
    analyze_phase4_typography,
    build_phase4_render_input,
    write_phase4_preflight_artifacts,
)
from src.media_pipeline.video_renderer.render_policy import (
    enrich_phase4_render_policies,
)


class Phase4SourceResolutionTests(unittest.TestCase):
    def test_demotes_dense_source_shadow_inside_approved_editor_caption_lane(self) -> None:
        master = {
            "editor": {
                "text_id": "editor",
                "start_frame": 100,
                "end_frame": 125,
                "box_coords": [230, 530, 585, 565],
            },
            "shadow_top": {
                "text_id": "shadow_top",
                "start_frame": 104,
                "end_frame": 122,
                "box_coords": [215, 528, 582, 569],
                "visual_provenance": {
                    "classification": "SOURCE_INTRINSIC",
                    "confidence": 0.96,
                },
            },
            "shadow_second_line": {
                "text_id": "shadow_second_line",
                "start_frame": 98,
                "end_frame": 160,
                "box_coords": [333, 571, 488, 596],
                "visual_provenance": {
                    "classification": "SOURCE_INTRINSIC",
                    "confidence": 0.98,
                },
            },
            "phone_label": {
                "text_id": "phone_label",
                "start_frame": 104,
                "end_frame": 122,
                "box_coords": [30, 300, 95, 330],
                "visual_provenance": {
                    "classification": "SOURCE_INTRINSIC",
                    "confidence": 0.96,
                },
            },
            "nested_editor_fragment": {
                "text_id": "nested_editor_fragment",
                "start_frame": 104,
                "end_frame": 122,
                "box_coords": [500, 535, 555, 557],
                "visual_provenance": {
                    "classification": "SOURCE_INTRINSIC_PANEL",
                    "confidence": 0.94,
                },
            },
            "tall_source_object": {
                "text_id": "tall_source_object",
                "start_frame": 104,
                "end_frame": 122,
                "box_coords": [215, 570, 582, 660],
                "visual_provenance": {
                    "classification": "SOURCE_INTRINSIC",
                    "confidence": 0.98,
                },
            },
        }
        enrichments = {
            "editor": {
                "visual_provenance": {
                    "classification": "EDITOR_LABEL",
                    "confidence": 0.97,
                }
            }
        }

        demoted = _resolve_protected_caption_shadow_ids(
            master,
            enrichments,
            ["editor"],
            {
                "shadow_top",
                "shadow_second_line",
                "phone_label",
                "tall_source_object",
                "nested_editor_fragment",
            },
            frame_width=720,
            frame_height=1280,
        )

        self.assertEqual(
            demoted,
            {"shadow_top", "shadow_second_line", "nested_editor_fragment"},
        )

    def test_unions_same_lane_residual_caption_fragments(self) -> None:
        tracks = [
            {
                "text_id": "p2r_left",
                "start_frame": 100,
                "end_frame": 140,
                "best_frame_index": 110,
                "hit_frames": [110, 120],
                "geometry": {"x": 0.10, "y": 0.75, "width": 0.12, "height": 0.04},
                "cover_only": True,
                "residual_caption_fragment_cover_only": True,
            },
            {
                "text_id": "p2r_right",
                "start_frame": 100,
                "end_frame": 105,
                "best_frame_index": 102,
                "hit_frames": [101, 102],
                "geometry": {"x": 0.78, "y": 0.755, "width": 0.10, "height": 0.035},
                "cover_only": True,
                "residual_caption_fragment_cover_only": True,
            },
        ]

        collapsed, count = _collapse_residual_caption_cover_groups(tracks)

        self.assertEqual(count, 1)
        self.assertEqual(len(collapsed), 1)
        geometry = collapsed[0]["geometry"]
        self.assertAlmostEqual(geometry["x"], 0.10)
        self.assertAlmostEqual(geometry["width"], 0.78)
        self.assertEqual(
            collapsed[0]["residual_caption_cover_group"]["members"],
            ["p2r_left", "p2r_right"],
        )

    def test_suppresses_short_ocr_empty_fragment_beside_active_caption(self) -> None:
        tracks = [
            {
                "text_id": "caption",
                "kind": "hardsub",
                "start_frame": 355,
                "end_frame": 367,
                "geometry": {
                    "x": 0.38,
                    "y": 0.89,
                    "width": 0.13,
                    "height": 0.08,
                },
                "text_vi": "Cho cà chua vào",
                "cover_only": False,
                "weak_ocr_fragment_candidate": False,
            },
            {
                "text_id": "fragment",
                "kind": "hardsub",
                "start_frame": 359,
                "end_frame": 363,
                "geometry": {
                    "x": 0.54,
                    "y": 0.86,
                    "width": 0.056,
                    "height": 0.038,
                },
                "text_vi": "Câu bị gán nhầm",
                "cover_only": False,
                "weak_ocr_fragment_candidate": True,
            },
        ]

        count = _suppress_weak_caption_fragments(tracks)

        self.assertEqual(count, 1)
        self.assertTrue(tracks[1]["cover_only"])
        self.assertEqual(tracks[1]["text_vi"], "")
        self.assertEqual(
            tracks[1]["weak_fragment_suppression"]["parent_text_id"], "caption"
        )

    def test_does_not_suppress_standalone_ocr_empty_fragment(self) -> None:
        track = {
            "text_id": "fragment",
            "kind": "hardsub",
            "start_frame": 10,
            "end_frame": 14,
            "geometry": {"x": 0.5, "y": 0.8, "width": 0.05, "height": 0.03},
            "text_vi": "Giữ nguyên để review",
            "cover_only": False,
            "weak_ocr_fragment_candidate": True,
        }

        self.assertEqual(_suppress_weak_caption_fragments([track]), 0)
        self.assertFalse(track["cover_only"])

    def test_explicit_ui_chip_role_overrides_spurious_hardsub_role(self) -> None:
        self.assertEqual(_kind_for_roles(["ui_chip", "hardsub"]), "ui")

    def test_tiny_layout_edge_contact_is_not_a_readability_collision(self) -> None:
        self.assertFalse(_rects_overlap((547, 956, 692, 986), (685, 933, 1235, 983)))
        self.assertTrue(_rects_overlap((244, 122, 358, 155), (255, 137, 333, 160)))

    def test_short_overlapping_ui_transition_is_assigned_to_incoming_track(self) -> None:
        tracks = [
            {
                "text_id": "outgoing",
                "content_id": "content_a",
                "kind": "ui",
                "start_frame": 115,
                "end_frame": 126,
                "geometry": {"x": 0.0, "y": 0.09, "width": 0.19, "height": 0.07},
            },
            {
                "text_id": "incoming",
                "content_id": "content_b",
                "kind": "ui",
                "start_frame": 122,
                "end_frame": 132,
                "geometry": {"x": 0.14, "y": 0.12, "width": 0.02, "height": 0.03},
            },
        ]

        adjusted = _normalize_shared_caption_boundaries(tracks, fps=30.0)

        self.assertEqual(adjusted, 1)
        self.assertEqual(tracks[0]["end_frame"], 121)
        self.assertEqual(tracks[0]["timing_adjustment"]["frames_trimmed"], 5)

    def test_equal_start_caption_tracks_are_partitioned_by_hit_evidence(self) -> None:
        tracks = [
            {
                "text_id": "sub_27",
                "content_id": "content_early",
                "kind": "ui",
                "start_frame": 1831,
                "end_frame": 1854,
                "best_frame_index": 1845,
                "hit_frames": [1845, 1848, 1849],
                "geometry": {"x": 0.238, "y": 0.756, "width": 0.512, "height": 0.029},
            },
            {
                "text_id": "sub_28",
                "content_id": "content_late",
                "kind": "ui",
                "start_frame": 1831,
                "end_frame": 1907,
                "best_frame_index": 1892,
                "hit_frames": [1890, 1892, 1905],
                "geometry": {"x": 0.280, "y": 0.757, "width": 0.467, "height": 0.027},
            },
        ]

        adjusted = _normalize_shared_caption_boundaries(tracks, fps=43.97)

        self.assertEqual(adjusted, 1)
        self.assertLess(tracks[0]["end_frame"], tracks[1]["start_frame"])
        self.assertGreaterEqual(tracks[0]["end_frame"], max(tracks[0]["hit_frames"]))
        self.assertLessEqual(tracks[1]["start_frame"], min(tracks[1]["hit_frames"]))
        self.assertEqual(tracks[0]["cover_start_frame"], 1831)
        self.assertEqual(tracks[1]["cover_start_frame"], 1831)
        self.assertEqual(
            tracks[1]["timing_adjustment"]["reason"],
            "temporal_evidence_partitioned_shared_caption_lane",
        )

    def test_resolves_phase1_path_relative_to_api_runtime_root(self) -> None:
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            api_root = workspace / "apps" / "api"
            artifact_root = api_root / "regression_runs" / "run" / "case"
            source = workspace / ".douyin_profiles" / "download_staging" / "video.mp4"
            artifact_root.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            source.write_bytes(b"video")

            resolved = _resolve_phase1_source_path(
                artifact_root,
                r"..\..\.douyin_profiles\download_staging\video.mp4",
                api_root=api_root,
            )

        self.assertEqual(resolved, source.resolve())


def _master() -> list[dict]:
    return [
        {
            "text_id": "sub_01",
            "start_frame": 0,
            "end_frame": 9,
            "box_coords": [100, 100, 500, 180],
        },
        {
            "text_id": "sub_02",
            "start_frame": 10,
            "end_frame": 19,
            "box_coords": [120, 110, 520, 190],
        },
    ]


def _phase2() -> dict:
    return {
        "track_enrichments": [
            {
                "text_id": "sub_01",
                "content_id": "ocr_content_001",
                "coverage_authority": {
                    "presence_ranges": [[0, 9]],
                    "geometry_keyframes": [
                        {
                            "frame_index": 0,
                            "geometry": {
                                "x": 100 / 1920,
                                "y": 100 / 1080,
                                "width": 400 / 1920,
                                "height": 80 / 1080,
                            },
                        }
                    ],
                },
            },
            {"text_id": "sub_02", "content_id": "ocr_content_001"},
        ],
        "content_objects": [
            {
                "content_id": "ocr_content_001",
                "geometry_refs": ["sub_01", "sub_02"],
                "roles": ["hardsub"],
            }
        ],
    }


def _phase3() -> dict:
    return {
        "status": "READY_FOR_RENDER",
        "geometry_map": {
            "sub_01": {
                "content_id": "ocr_content_001",
                "text_vi": "Bản dịch đã khóa",
                "translation_status": "TRANSLATION_APPROVED",
            },
            "sub_02": {
                "content_id": "ocr_content_001",
                "text_vi": "Bản dịch đã khóa",
                "translation_status": "TRANSLATION_APPROVED",
            },
        },
    }


class Phase4InputContractTests(unittest.TestCase):
    def test_recovered_duplicate_shadow_is_suppressed_without_content_id_shift(self) -> None:
        master = [
            {
                "text_id": "sub_host",
                "start_frame": 10,
                "end_frame": 40,
                "box_coords": [100, 700, 620, 760],
            },
            {
                "text_id": "sub_shadow",
                "start_frame": 20,
                "end_frame": 23,
                "box_coords": [440, 1250, 500, 1270],
            },
        ]
        phase2 = {
            "track_enrichments": [
                {
                    "text_id": "sub_host",
                    "content_id": "ocr_content_001",
                    "ocr_text_raw": "第一行",
                },
                {
                    "text_id": "sub_shadow",
                    "content_id": "ocr_content_002",
                    "ocr_text_raw": "第一行",
                    "geometry_recovery": {
                        "status": "LOCAL_DERIVED_TEMPORAL_CONSENSUS",
                        "derived_box_coords": [100, 700, 620, 760],
                        "frame_support": 2,
                        "geometry_observation_count": 2,
                    },
                },
            ],
            "content_objects": [
                {
                    "content_id": "ocr_content_001",
                    "geometry_refs": ["sub_host"],
                    "roles": ["hardsub"],
                },
                {
                    "content_id": "ocr_content_002",
                    "geometry_refs": ["sub_shadow"],
                    "roles": ["hardsub"],
                },
            ],
        }
        phase3 = {
            "status": "READY_FOR_RENDER",
            "geometry_map": {
                "sub_host": {
                    "content_id": "ocr_content_001",
                    "text_vi": "Dòng đầu",
                    "translation_status": "TRANSLATION_APPROVED",
                },
                "sub_shadow": {
                    "content_id": "ocr_content_002",
                    "text_vi": "Dòng đầu",
                    "translation_status": "TRANSLATION_APPROVED",
                },
            },
        }

        contract = build_phase4_render_input(
            master,
            phase2,
            phase3,
            video_metadata={
                "frame_width": 720,
                "frame_height": 1280,
                "frame_count": 60,
                "fps": 30.0,
            },
            refs={},
        )

        assert [row["text_id"] for row in contract["render_tracks"]] == [
            "sub_host"
        ]
        assert contract["counts"]["suppressed_shadow_tracks"] == 1

    def test_applies_hash_authorized_geometry_without_mutating_master(self) -> None:
        master = _master()
        original = json.loads(json.dumps(master))
        output = _apply_geometry_overrides(
            master,
            [
                {
                    "target_text_id": "sub_01",
                    "start_frame": 0,
                    "end_frame": 9,
                    "original_box_coords": [100, 100, 500, 180],
                    "box_coords": [100, 100, 650, 180],
                    "best_keyframe_path": "qa/source.jpg",
                    "crop_path": "qa/crop.jpg",
                    "best_frame_index": 4,
                }
            ],
        )

        self.assertEqual(master, original)
        self.assertEqual(output[0]["box_coords"], [100, 100, 650, 180])
        self.assertEqual(
            output[0]["geometry_remediation"]["status"],
            "OPERATOR_APPROVED_OVERRIDE",
        )

    def test_geometry_override_fails_when_original_authority_drifted(self) -> None:
        with self.assertRaises(Phase4InputError):
            _apply_geometry_overrides(
                _master(),
                [
                    {
                        "target_text_id": "sub_01",
                        "start_frame": 0,
                        "end_frame": 9,
                        "original_box_coords": [101, 100, 500, 180],
                        "box_coords": [100, 100, 650, 180],
                    }
                ],
            )

    def test_adjacent_ui_rows_keep_source_order_without_collision(self) -> None:
        tracks = [
            {
                "text_id": "micro_a",
                "content_id": "content_a",
                "start_ms": 0,
                "end_ms": 1000,
                "geometry": {
                    "x": 0.40,
                    "y": 0.193,
                    "width": 0.20,
                    "height": 0.018,
                },
                "kind": "ui",
                "text_vi": "Quang phổ",
            },
            {
                "text_id": "micro_b",
                "content_id": "content_b",
                "start_ms": 0,
                "end_ms": 1000,
                "geometry": {
                    "x": 0.39,
                    "y": 0.168,
                    "width": 0.23,
                    "height": 0.017,
                },
                "kind": "ui",
                "text_vi": "Hấp thụ",
            },
            {
                "text_id": "caption_a",
                "content_id": "content_c",
                "start_ms": 1000,
                "end_ms": 2000,
                "geometry": {
                    "x": 0.18,
                    "y": 0.663,
                    "width": 0.63,
                    "height": 0.024,
                },
                "kind": "ui",
                "text_vi": "Lớp khí lấy đi",
            },
            {
                "text_id": "micro_c",
                "content_id": "content_d",
                "start_ms": 1000,
                "end_ms": 2000,
                "geometry": {
                    "x": 0.36,
                    "y": 0.704,
                    "width": 0.29,
                    "height": 0.020,
                },
                "kind": "ui",
                "text_vi": "hay hấp thụ nó.",
            },
        ]
        contract = enrich_phase4_render_policies(
            {
                "video": {"frame_width": 1080, "frame_height": 1920},
                "render_tracks": tracks,
            }
        )

        report = analyze_phase4_typography(
            contract,
            fontfile=Path(r"C:\Windows\Fonts\segoeui.ttf"),
        )

        self.assertEqual(report["counts"]["text_overflow"], 0)
        self.assertEqual(report["counts"]["collision_events"], 0)

    def test_writes_final_input_only_when_preflight_is_ready(self) -> None:
        contract = build_phase4_render_input(
            _master(),
            _phase2(),
            _phase3(),
            video_metadata={
                "frame_width": 1920,
                "frame_height": 1080,
                "frame_count": 100,
                "fps": 25.0,
            },
            refs={},
        )
        report = analyze_phase4_typography(
            contract,
            fontfile=Path(r"C:\Windows\Fonts\segoeui.ttf"),
        )
        contract["status"] = "READY_FOR_PHASE4"
        with TemporaryDirectory() as tmp:
            paths = write_phase4_preflight_artifacts(
                root_dir=tmp,
                contract=contract,
                report=report,
            )
            self.assertTrue(paths["preview"].is_file())
            self.assertTrue(paths["final"].is_file())
            self.assertTrue(paths["report_json"].is_file())
            self.assertTrue(paths["report_md"].is_file())
            written = json.loads(paths["final"].read_text(encoding="utf-8"))
            self.assertEqual(written["status"], "READY_FOR_PHASE4")
            self.assertIn("layout_rect_px", report["track_metrics"][0])

    def test_builds_one_render_track_per_exact_geometry_ref(self) -> None:
        contract = build_phase4_render_input(
            _master(),
            _phase2(),
            _phase3(),
            video_metadata={
                "frame_width": 1920,
                "frame_height": 1080,
                "frame_count": 100,
                "fps": 25.0,
            },
            refs={"phase3_render_handoff_ref": {"sha256": "f" * 64}},
        )
        self.assertEqual(contract["status"], "READY_FOR_PHASE4_PREFLIGHT")
        self.assertEqual(contract["counts"]["render_tracks"], 2)
        first = contract["render_tracks"][0]
        self.assertEqual(first["text_id"], "sub_01")
        self.assertEqual(first["content_id"], "ocr_content_001")
        self.assertEqual(first["text_vi"], "Bản dịch đã khóa")
        self.assertEqual(first["start_ms"], 0)
        self.assertEqual(first["end_ms"], 400)
        self.assertAlmostEqual(first["geometry"]["x"], 100 / 1920)
        self.assertEqual(
            first["coverage_authority"]["presence_ranges"], [[0, 9]]
        )
        self.assertEqual(first["kind"], "hardsub")
        self.assertIn("render_policy", first)
        self.assertEqual(
            first["render_policy"]["cover"]["roi"],
            first["render_policy"]["layout"]["safe_area"],
        )
        self.assertEqual(first["render_policy"]["layout"]["mode"], "cover_aligned")

    def test_suppresses_phase2_temporal_shadow_without_mutating_master(self) -> None:
        master = _master() + [
            {
                "text_id": "shadow_short",
                "start_frame": 5,
                "end_frame": 8,
                "box_coords": [120, 50, 220, 70],
            }
        ]
        contract = build_phase4_render_input(
            master,
            _phase2(),
            _phase3(),
            video_metadata={
                "frame_width": 1920,
                "frame_height": 1080,
                "frame_count": 100,
                "fps": 25.0,
            },
            refs={},
            suppressed_shadow_refs=["shadow_short"],
        )

        self.assertEqual(contract["counts"]["render_tracks"], 2)
        self.assertEqual(contract["counts"]["suppressed_shadow_tracks"], 1)
        self.assertNotIn(
            "shadow_short",
            {row["text_id"] for row in contract["render_tracks"]},
        )
        self.assertEqual(len(master), 3)

    def test_evidence_suppression_retires_stale_geometry_projection(self) -> None:
        contract = build_phase4_render_input(
            _master(),
            _phase2(),
            _phase3(),
            video_metadata={
                "frame_width": 1920,
                "frame_height": 1080,
                "frame_count": 100,
                "fps": 25.0,
            },
            refs={},
            suppressed_shadow_refs=["sub_02"],
        )

        self.assertEqual(contract["counts"]["render_tracks"], 1)
        self.assertEqual(contract["suppressed_shadow_refs"], ["sub_02"])

    def test_output_residual_caption_fragment_is_cover_only(self) -> None:
        master = _master()
        master[0]["text_id"] = "p2r_fragment"
        master[0]["boundary_evidence"] = {
            "method": "phase4_residual_source_ocr"
        }
        phase2 = _phase2()
        phase2["track_enrichments"][0]["text_id"] = "p2r_fragment"
        phase2["content_objects"][0]["geometry_refs"] = [
            "p2r_fragment",
            "sub_02",
        ]
        phase3 = _phase3()
        phase3["geometry_map"]["p2r_fragment"] = phase3["geometry_map"].pop(
            "sub_01"
        )

        contract = build_phase4_render_input(
            master,
            phase2,
            phase3,
            video_metadata={
                "frame_width": 1920,
                "frame_height": 1080,
                "frame_count": 100,
                "fps": 25.0,
            },
            refs={},
        )

        fragment = next(
            row for row in contract["render_tracks"] if row["text_id"] == "p2r_fragment"
        )
        self.assertTrue(fragment["cover_only"])
        self.assertTrue(fragment["residual_caption_fragment_cover_only"])
        self.assertEqual(fragment["text_vi"], "")

    def test_semantic_dialogue_residual_uses_hardsub_render_policy(self) -> None:
        master = [
            {
                "text_id": "p2r_dialogue",
                "start_frame": 10,
                "end_frame": 12,
                "box_coords": [8, 1008, 712, 1040],
            }
        ]
        phase2 = {
            "track_enrichments": [
                {
                    "text_id": "p2r_dialogue",
                    "content_id": "ocr_content_dialogue",
                }
            ],
            "content_objects": [
                {
                    "content_id": "ocr_content_dialogue",
                    "geometry_refs": ["p2r_dialogue"],
                    "roles": ["generic"],
                    "ocr_text_raw_candidates": ["中文对白"],
                    "semantic_hardsub": {
                        "classification": "DIALOGUE_HARDSUB",
                        "translation_ready": True,
                        "alignment": {
                            "transcript_start_ms": 1_000,
                            "transcript_end_ms": 5_000,
                            "translation_status": "APPROVED",
                        },
                        "translation_authority": {
                            "translation_status": "APPROVED"
                        },
                    },
                }
            ],
        }
        phase3 = {
            "status": "READY_FOR_RENDER",
            "geometry_map": {
                "p2r_dialogue": {
                    "content_id": "ocr_content_dialogue",
                    "text_vi": "Bản dịch lời thoại đã duyệt",
                    "translation_status": "TRANSLATION_DETERMINISTIC",
                }
            },
        }

        contract = build_phase4_render_input(
            master,
            phase2,
            phase3,
            video_metadata={
                "frame_width": 720,
                "frame_height": 1280,
                "frame_count": 180,
                "fps": 30.0,
            },
            refs={},
        )

        track = contract["render_tracks"][0]
        self.assertEqual(track["kind"], "hardsub")
        self.assertFalse(track["cover_only"])
        self.assertTrue(track["semantic_dialogue_residual_expanded"])
        self.assertEqual(track["start_frame"], 10)
        self.assertEqual(track["end_frame"], 149)
        self.assertEqual(track["text_vi"], "Bản dịch lời thoại đã duyệt")

    def test_semantic_dialogue_residual_keeps_visual_tail_after_speech(self) -> None:
        master = [
            {
                "text_id": "p2r_dialogue_tail",
                "start_frame": 140,
                "end_frame": 160,
                "box_coords": [8, 1008, 712, 1040],
            }
        ]
        phase2 = {
            "track_enrichments": [
                {
                    "text_id": "p2r_dialogue_tail",
                    "content_id": "ocr_content_dialogue_tail",
                    "semantic_hardsub": {
                        "classification": "DIALOGUE_HARDSUB",
                        "alignment": {
                            "transcript_start_ms": 4_000,
                            "transcript_end_ms": 5_000,
                            "translation_status": "APPROVED",
                        },
                        "translation_authority": {
                            "translation_status": "APPROVED"
                        },
                    },
                }
            ],
            "content_objects": [
                {
                    "content_id": "ocr_content_dialogue_tail",
                    "geometry_refs": ["p2r_dialogue_tail"],
                    "roles": ["generic"],
                    "ocr_text_raw_candidates": ["dialogue"],
                    "semantic_hardsub": {
                        "classification": "DIALOGUE_HARDSUB"
                    },
                }
            ],
        }
        phase3 = {
            "status": "READY_FOR_RENDER",
            "geometry_map": {
                "p2r_dialogue_tail": {
                    "content_id": "ocr_content_dialogue_tail",
                    "text_vi": "Tam biet.",
                    "translation_status": "TRANSLATION_DETERMINISTIC",
                }
            },
        }

        contract = build_phase4_render_input(
            master,
            phase2,
            phase3,
            video_metadata={
                "frame_width": 720,
                "frame_height": 1280,
                "frame_count": 180,
                "fps": 30.0,
            },
            refs={},
        )

        track = contract["render_tracks"][0]
        self.assertEqual(track["start_frame"], 120)
        self.assertEqual(track["end_frame"], 160)

    def test_shared_caption_boundary_is_assigned_to_incoming_caption(self) -> None:
        master = _master()
        master[0]["end_frame"] = 10
        phase2 = _phase2()
        phase2["track_enrichments"][1]["content_id"] = "ocr_content_002"
        phase2["content_objects"] = [
            {
                "content_id": "ocr_content_001",
                "geometry_refs": ["sub_01"],
                "roles": ["hardsub"],
            },
            {
                "content_id": "ocr_content_002",
                "geometry_refs": ["sub_02"],
                "roles": ["hardsub"],
            },
        ]
        phase3 = _phase3()
        phase3["geometry_map"]["sub_02"]["content_id"] = "ocr_content_002"

        contract = build_phase4_render_input(
            master,
            phase2,
            phase3,
            video_metadata={
                "frame_width": 1920,
                "frame_height": 1080,
                "frame_count": 100,
                "fps": 25.0,
            },
            refs={},
        )

        first, second = contract["render_tracks"]
        self.assertEqual(first["end_frame"], 9)
        self.assertEqual(second["start_frame"], 10)
        self.assertEqual(first["timing_adjustment"]["frames_trimmed"], 1)
        self.assertEqual(
            contract["timing_normalization"][
                "adjusted_shared_caption_boundaries"
            ],
            1,
        )

    def test_builds_approved_supplemental_occurrence_by_exact_text_id(self) -> None:
        master = _master() + [
            {
                "text_id": "p2r_test",
                "start_frame": 10,
                "end_frame": 19,
                "box_coords": [150, 900, 240, 930],
            }
        ]
        phase2 = _phase2()
        phase2["track_enrichments"].append(
            {"text_id": "p2r_test", "content_id": "ocr_content_002"}
        )
        phase2["content_objects"].append(
            {
                "content_id": "ocr_content_002",
                "geometry_refs": ["p2r_test"],
                "roles": ["ui_chip"],
            }
        )
        phase3 = _phase3()
        phase3["geometry_map"]["p2r_test"] = {
            "content_id": "ocr_content_002",
            "text_vi": "170 g",
            "translation_status": "TRANSLATION_DETERMINISTIC",
        }
        contract = build_phase4_render_input(
            master,
            phase2,
            phase3,
            video_metadata={
                "frame_width": 1920,
                "frame_height": 1080,
                "frame_count": 100,
                "fps": 25.0,
            },
            refs={},
        )
        supplemental = next(
            row for row in contract["render_tracks"] if row["text_id"] == "p2r_test"
        )
        self.assertEqual(contract["counts"]["render_tracks"], 3)
        self.assertEqual(supplemental["text_vi"], "170 g")
        self.assertEqual(
            supplemental["translation_status"], "TRANSLATION_DETERMINISTIC"
        )

    def test_rejects_missing_geometry_translation(self) -> None:
        handoff = _phase3()
        del handoff["geometry_map"]["sub_02"]
        with self.assertRaises(Phase4InputError):
            build_phase4_render_input(
                _master(),
                _phase2(),
                handoff,
                video_metadata={
                    "frame_width": 1920,
                    "frame_height": 1080,
                    "frame_count": 100,
                    "fps": 25.0,
                },
                refs={},
            )

    def test_rejects_unapproved_translation(self) -> None:
        handoff = _phase3()
        handoff["geometry_map"]["sub_01"][
            "translation_status"
        ] = "TRANSLATION_CANDIDATE"
        with self.assertRaises(Phase4InputError):
            build_phase4_render_input(
                _master(),
                _phase2(),
                handoff,
                video_metadata={
                    "frame_width": 1920,
                    "frame_height": 1080,
                    "frame_count": 100,
                    "fps": 25.0,
                },
                refs={},
            )

    def test_typography_fails_closed_when_single_line_is_wider_than_frame(self) -> None:
        tiny_master = [
            {
                "text_id": "sub_01",
                "start_frame": 0,
                "end_frame": 9,
                "box_coords": [10, 40, 110, 55],
            }
        ]
        contract = build_phase4_render_input(
            tiny_master,
            {
                "track_enrichments": _phase2()["track_enrichments"][:1],
                "content_objects": _phase2()["content_objects"],
            },
            {
                "status": "READY_FOR_RENDER",
                "geometry_map": {
                    "sub_01": {
                        "content_id": "ocr_content_001",
                        "text_vi": "Một câu tiếng Việt cố ý dài hơn rất nhiều so với khung hình",
                        "translation_status": "TRANSLATION_APPROVED",
                    }
                },
            },
            video_metadata={
                "frame_width": 120,
                "frame_height": 100,
                "frame_count": 20,
                "fps": 25.0,
            },
            refs={},
        )
        report = analyze_phase4_typography(
            contract,
            fontfile=Path(r"C:\Windows\Fonts\segoeui.ttf"),
        )
        self.assertEqual(report["status"], "PHASE4_PREFLIGHT_BLOCKED")
        self.assertGreater(report["counts"]["text_overflow"], 0)

    def test_dense_typography_measures_only_temporally_active_sets(self) -> None:
        tracks = []
        for scene in range(6):
            start_ms = scene * 1000
            for index in range(10):
                tracks.append(
                    {
                        "text_id": f"s{scene}_{index}",
                        "content_id": f"c{scene}_{index}",
                        "start_ms": start_ms,
                        "end_ms": start_ms + 900,
                        "geometry": {
                            "x": 0.08 if index < 5 else 0.72,
                            "y": 0.08 + (index % 5) * 0.16,
                            "width": 0.18,
                            "height": 0.04,
                        },
                        "kind": "ui",
                        "text_vi": f"Nhãn {scene}-{index}",
                    }
                )
        contract = enrich_phase4_render_policies(
            {
                "video": {"frame_width": 1280, "frame_height": 720},
                "render_tracks": tracks,
            }
        )

        report = analyze_phase4_typography(
            contract,
            fontfile=Path(r"C:\Windows\Fonts\segoeui.ttf"),
        )

        self.assertEqual(report["counts"]["text_overflow"], 0)
        self.assertEqual(report["counts"]["measured_tracks"], 60)

    def test_typography_ignores_duplicate_text_placement_for_same_content(self) -> None:
        tracks = [
            {
                "text_id": "large",
                "content_id": "same_content",
                "start_ms": 0,
                "end_ms": 1000,
                "geometry": {"x": 0.1, "y": 0.7, "width": 0.5, "height": 0.05},
                "kind": "ui",
                "text_vi": "Cùng một nhãn",
            },
            {
                "text_id": "small",
                "content_id": "same_content",
                "start_ms": 100,
                "end_ms": 900,
                "geometry": {"x": 0.2, "y": 0.71, "width": 0.2, "height": 0.04},
                "kind": "ui",
                "text_vi": "Cùng một nhãn",
            },
        ]
        contract = enrich_phase4_render_policies(
            {
                "video": {"frame_width": 1280, "frame_height": 720},
                "render_tracks": tracks,
            }
        )

        report = analyze_phase4_typography(
            contract,
            fontfile=Path(r"C:\Windows\Fonts\segoeui.ttf"),
        )

        self.assertEqual(report["counts"]["collision_events"], 0)


if __name__ == "__main__":
    unittest.main()
