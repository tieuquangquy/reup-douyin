from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.media_pipeline.video_renderer.phase4_input_contract import (
    Phase4InputError,
    _apply_geometry_overrides,
    _kind_for_roles,
    _normalize_shared_caption_boundaries,
    _rects_overlap,
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
            {"text_id": "sub_01", "content_id": "ocr_content_001"},
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
        self.assertEqual(first["kind"], "hardsub")
        self.assertIn("render_policy", first)
        self.assertEqual(
            first["render_policy"]["cover"]["roi"],
            first["render_policy"]["layout"]["safe_area"],
        )
        self.assertEqual(first["render_policy"]["layout"]["mode"], "cover_aligned")

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
