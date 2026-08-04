from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from scripts.score_phase1_pass import score_phase1_out, write_phase1_score


class Phase1ScoreArtifactTests(unittest.TestCase):
    def test_writes_durable_score_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            score = {"PASS": True, "tracks": 3}

            target = write_phase1_score(root, score)

            self.assertEqual(target, root / "phase1_score.json")
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), score)
            self.assertEqual(list(root.glob(".phase1_score.json.*.tmp")), [])


class Phase1ScoreTemporalDuplicateTests(unittest.TestCase):
    def test_left_aligned_caption_with_matching_detector_geometry_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "sub_01.jpg").touch()
            (root / "frames" / "sub_01.jpg").touch()
            box = [2.0, 990.0, 900.0, 1050.0]
            (root / "master_timeline.json").write_text(
                json.dumps(
                    [
                        {
                            "text_id": "sub_01",
                            "start_frame": 10,
                            "end_frame": 19,
                            "box_coords": box,
                            "crop_path": "crops/sub_01.jpg",
                            "best_keyframe_path": "frames/sub_01.jpg",
                            "hit_count": 10,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 1,
                        "confirmed_tracks": 1,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps(
                    {
                        "frame_width": 1920,
                        "frame_height": 1080,
                        "by_frame": {
                            str(frame): [{"boxes": box, "role": "hardsub"}]
                            for frame in range(10, 20)
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = score_phase1_out(root)

            self.assertEqual(result["empty_left_wide_hardsubs"], [])
            self.assertTrue(result["checks"]["no_empty_left_wide_hardsub"])
            self.assertTrue(result["PASS"])

    def test_overmerged_ui_grid_columns_block_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "sub_01.jpg").touch()
            frame = np.full((1080, 1920, 3), 255, dtype=np.uint8)
            frame[220:250, 100:155] = 0
            frame[220:250, 265:345] = 0
            cv2.imwrite(str(root / "frames" / "sub_01.jpg"), frame)
            peer_boxes = [
                [80.0, 80.0, 150.0, 110.0],
                [900.0, 90.0, 970.0, 120.0],
                [1700.0, 100.0, 1770.0, 130.0],
                [100.0, 500.0, 170.0, 530.0],
                [920.0, 520.0, 990.0, 550.0],
                [1680.0, 700.0, 1750.0, 730.0],
            ]
            timeline = [
                {
                    "text_id": "sub_01",
                    "start_frame": 100,
                    "end_frame": 123,
                    "box_coords": [80.0, 200.0, 360.0, 270.0],
                    "crop_path": "crops/sub_01.jpg",
                    "best_keyframe_path": "frames/sub_01.jpg",
                    "best_frame_index": 110,
                    "hit_count": 24,
                }
            ]
            timeline.extend(
                {
                    "text_id": f"sub_{index:02d}",
                    "start_frame": 100,
                    "end_frame": 123,
                    "box_coords": box,
                    "crop_path": "crops/sub_01.jpg",
                    "best_keyframe_path": "frames/sub_01.jpg",
                    "best_frame_index": 110,
                    "hit_count": 24,
                }
                for index, box in enumerate(peer_boxes, start=2)
            )
            (root / "master_timeline.json").write_text(
                json.dumps(timeline),
                encoding="utf-8",
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": len(timeline),
                        "confirmed_tracks": len(timeline),
                        "uncertain_tracks": 0,
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps(
                    {"frame_width": 1920, "frame_height": 1080, "by_frame": {}}
                ),
                encoding="utf-8",
            )

            result = score_phase1_out(root)

            self.assertEqual(
                [row["text_id"] for row in result["overmerged_ui_grid_tracks"]],
                ["sub_01"],
            )
            self.assertFalse(result["checks"]["no_overmerged_ui_grid_tracks"])
            self.assertFalse(result["PASS"])

    def test_uses_coverage_frame_size_for_720p_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "sub_01.jpg").touch()
            (root / "frames" / "sub_01.jpg").touch()
            (root / "master_timeline.json").write_text(
                json.dumps(
                    [
                        {
                            "text_id": "sub_01",
                            "start_frame": 13,
                            "end_frame": 66,
                            "box_coords": [465.0, 646.0, 812.0, 700.0],
                            "crop_path": "crops/sub_01.jpg",
                            "best_keyframe_path": "frames/sub_01.jpg",
                            "hit_count": 54,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 1,
                        "confirmed_tracks": 1,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps(
                    {"frame_width": 1280, "frame_height": 720, "by_frame": {}}
                ),
                encoding="utf-8",
            )

            result = score_phase1_out(root)

            self.assertEqual(result["frame_size"], [1280, 720])
            self.assertEqual(result["roles"]["hardsub"], 1)
            self.assertTrue(result["PASS"])

    def test_high_confidence_cjk_local_reject_blocks_automatic_pass(self) -> None:
        """A confidently read label cannot disappear behind a semantic gate."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "sub_01.jpg").touch()
            (root / "frames" / "sub_01.jpg").touch()
            (root / "master_timeline.json").write_text(
                json.dumps(
                    [
                        {
                            "text_id": "sub_01",
                            "start_frame": 1,
                            "end_frame": 10,
                            "box_coords": [600.0, 1000.0, 1300.0, 1050.0],
                            "crop_path": "crops/sub_01.jpg",
                            "best_keyframe_path": "frames/sub_01.jpg",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 1,
                        "confirmed_tracks": 1,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "qa" / "before_after.json").write_text(
                json.dumps(
                    {
                        "local_text_gate": {
                            "rows": [
                                {
                                    "reason": "local_text_reject",
                                    "role": "ui_chip",
                                    "text": "150g里脊肉",
                                    "confidence": 0.996,
                                    "box": [886.0, 660.0, 1113.0, 715.0],
                                }
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps({"by_frame": {}}), encoding="utf-8"
            )

            result = score_phase1_out(root)

            self.assertEqual(len(result["high_confidence_local_text_rejects"]), 1)
            self.assertFalse(
                result["checks"]["no_high_confidence_local_text_rejects"]
            )
            self.assertFalse(result["PASS"])

    def test_isolated_micro_source_track_blocks_automatic_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "sub_01.jpg").touch()
            (root / "frames" / "sub_01.jpg").touch()
            (root / "master_timeline.json").write_text(
                json.dumps(
                    [
                        {
                            "text_id": "sub_01",
                            "start_frame": 10,
                            "end_frame": 40,
                            "box_coords": [1636.0, 934.0, 1673.0, 948.0],
                            "crop_path": "crops/sub_01.jpg",
                            "best_keyframe_path": "frames/sub_01.jpg",
                            "best_frame_index": 20,
                            "hit_count": 31,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 1,
                        "confirmed_tracks": 1,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps({"by_frame": {}}), encoding="utf-8"
            )

            result = score_phase1_out(root)

            self.assertEqual(result["isolated_micro_source_tracks"], ["sub_01"])
            self.assertFalse(result["checks"]["no_isolated_micro_source_tracks"])
            self.assertFalse(result["PASS"])

    def test_sequential_same_locus_captions_are_not_near_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            timeline = []
            for text_id, start, end in (
                ("sub_01", 1, 4),
                ("sub_02", 6, 10),
            ):
                crop_path = f"crops/{text_id}.jpg"
                frame_path = f"frames/{text_id}.jpg"
                (root / crop_path).touch()
                (root / frame_path).touch()
                timeline.append(
                    {
                        "text_id": text_id,
                        "start_frame": start,
                        "end_frame": end,
                        "box_coords": [600.0, 1000.0, 1300.0, 1050.0],
                        "crop_path": crop_path,
                        "best_keyframe_path": frame_path,
                    }
                )
            (root / "master_timeline.json").write_text(
                json.dumps(timeline), encoding="utf-8"
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 2,
                        "confirmed_tracks": 2,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps({"by_frame": {}}), encoding="utf-8"
            )

            result = score_phase1_out(root)

            self.assertEqual(result["near_dupe_pairs"], [])
            self.assertTrue(result["PASS"])

    def test_temporally_nested_ui_fragment_blocks_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            timeline = [
                {
                    "text_id": "sub_15",
                    "start_frame": 650,
                    "end_frame": 815,
                    "box_coords": [118.5, 465.6, 348.6, 530.25],
                    "crop_path": "crops/sub_15.jpg",
                    "best_keyframe_path": "frames/sub_15.jpg",
                    "hit_count": 166,
                },
                {
                    "text_id": "sub_19",
                    "start_frame": 753,
                    "end_frame": 772,
                    "box_coords": [177.75, 474.06, 293.25, 511.05],
                    "crop_path": "crops/sub_19.jpg",
                    "best_keyframe_path": "frames/sub_19.jpg",
                    "hit_count": 20,
                },
            ]
            for item in timeline:
                (root / str(item["crop_path"])).touch()
                (root / str(item["best_keyframe_path"])).touch()
            (root / "master_timeline.json").write_text(
                json.dumps(timeline), encoding="utf-8"
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 2,
                        "confirmed_tracks": 2,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps(
                    {
                        "frame_width": 1920,
                        "frame_height": 1080,
                        "by_frame": {},
                    }
                ),
                encoding="utf-8",
            )

            result = score_phase1_out(root)

            self.assertEqual(
                result["nested_temporal_ui_fragments"][0][
                    "candidate_text_id"
                ],
                "sub_19",
            )
            self.assertEqual(
                result["nested_temporal_ui_fragments"][0][
                    "authority_text_id"
                ],
                "sub_15",
            )
            self.assertFalse(
                result["checks"]["no_nested_temporal_ui_fragments"]
            )
            self.assertFalse(result["PASS"])

    def test_uncertain_track_blocks_automatic_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "sub_01.jpg").touch()
            (root / "frames" / "sub_01.jpg").touch()
            (root / "master_timeline.json").write_text(
                json.dumps(
                    [
                        {
                            "text_id": "sub_01",
                            "start_frame": 1,
                            "end_frame": 10,
                            "box_coords": [1229.0, 985.0, 1920.0, 1035.0],
                            "crop_path": "crops/sub_01.jpg",
                            "best_keyframe_path": "frames/sub_01.jpg",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 1,
                        "confirmed_tracks": 0,
                        "uncertain_tracks": 1,
                        "review_queue": [{"text_id": "sub_01"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps({"by_frame": {}}), encoding="utf-8"
            )

            result = score_phase1_out(root)

            self.assertFalse(result["checks"]["no_uncertain_tracks"])
            self.assertFalse(result["PASS"])

    def test_strongly_rejected_shadow_is_explained_only_beside_active_caption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "sub_01.jpg").touch()
            (root / "frames" / "sub_01.jpg").touch()
            (root / "master_timeline.json").write_text(
                json.dumps(
                    [
                        {
                            "text_id": "sub_01",
                            "start_frame": 10,
                            "end_frame": 19,
                            "box_coords": [600.0, 1000.0, 1300.0, 1055.0],
                            "crop_path": "crops/sub_01.jpg",
                            "best_keyframe_path": "frames/sub_01.jpg",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 1,
                        "confirmed_tracks": 1,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            shadow = [1635.0, 1030.0, 1885.0, 1072.0]
            (root / "qa" / "before_after.json").write_text(
                json.dumps(
                    {
                        "local_text_gate": {
                            "rows": [
                                {
                                    "reason": "local_text_reject",
                                    "role": "hardsub",
                                    "box": shadow,
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps(
                    {
                        "by_frame": {
                            str(frame): [
                                {"boxes": shadow, "role": "hardsub"}
                            ]
                            for frame in range(10, 20)
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = score_phase1_out(root)

            self.assertEqual(result["uncovered_dense_hardsub_spans"], [])
            self.assertEqual(
                result["locally_rejected_shadow_frames"], list(range(10, 20))
            )
            self.assertTrue(result["PASS"])

    def test_uncovered_dense_hardsub_span_blocks_automatic_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "sub_01.jpg").touch()
            (root / "frames" / "sub_01.jpg").touch()
            (root / "master_timeline.json").write_text(
                json.dumps(
                    [
                        {
                            "text_id": "sub_01",
                            "start_frame": 1,
                            "end_frame": 5,
                            "box_coords": [600.0, 1000.0, 1300.0, 1050.0],
                            "crop_path": "crops/sub_01.jpg",
                            "best_keyframe_path": "frames/sub_01.jpg",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 1,
                        "confirmed_tracks": 1,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            missing_box = [650.0, 1000.0, 1150.0, 1050.0]
            (root / "qa" / "before_after.json").write_text(
                json.dumps(
                    {
                        "local_text_gate": {
                            "rows": [
                                {
                                    "reason": "local_text_reject",
                                    "role": "hardsub",
                                    "box": missing_box,
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps(
                    {
                        "by_frame": {
                            str(frame): [
                                {"boxes": missing_box, "role": "hardsub"}
                            ]
                            for frame in range(10, 14)
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = score_phase1_out(root)

            self.assertEqual(result["uncovered_dense_hardsub_spans"], [[10, 13, 4]])
            self.assertFalse(
                result["checks"]["no_uncovered_dense_hardsub_spans"]
            )
            self.assertFalse(result["PASS"])

    def test_standalone_geometry_reject_explains_food_texture_hardsub(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "label_01.jpg").touch()
            (root / "frames" / "label_01.jpg").touch()
            (root / "master_timeline.json").write_text(
                json.dumps(
                    [
                        {
                            "text_id": "label_01",
                            "start_frame": 1,
                            "end_frame": 4,
                            "box_coords": [700.0, 500.0, 900.0, 560.0],
                            "crop_path": "crops/label_01.jpg",
                            "best_keyframe_path": "frames/label_01.jpg",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 1,
                        "confirmed_tracks": 1,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            food_edge = [760.0, 905.0, 1240.0, 1014.0]
            (root / "qa" / "before_after.json").write_text(
                json.dumps(
                    {
                        "local_text_gate": {
                            "rows": [
                                {
                                    "reason": "not_overlay_geometry",
                                    "role": "hardsub",
                                    "box": food_edge,
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps(
                    {
                        "by_frame": {
                            str(frame): [
                                {
                                    "boxes": [765.0, 910.0, 1235.0, 1012.0],
                                    "role": "hardsub",
                                }
                            ]
                            for frame in range(10, 16)
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = score_phase1_out(root)

            self.assertEqual(result["uncovered_dense_hardsub_spans"], [])
            self.assertEqual(
                result["locally_rejected_shadow_frames"], list(range(10, 16))
            )
            self.assertTrue(result["PASS"])

    def test_latin_source_text_reject_explains_detector_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "label_01.jpg").touch()
            (root / "frames" / "label_01.jpg").touch()
            (root / "master_timeline.json").write_text(
                json.dumps(
                    [
                        {
                            "text_id": "label_01",
                            "start_frame": 1,
                            "end_frame": 4,
                            "box_coords": [700.0, 500.0, 900.0, 560.0],
                            "crop_path": "crops/label_01.jpg",
                            "best_keyframe_path": "frames/label_01.jpg",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {"confirmed_tracks": 1, "uncertain_tracks": 0}
                ),
                encoding="utf-8",
            )
            source_box = [760.0, 905.0, 1240.0, 1014.0]
            (root / "qa" / "before_after.json").write_text(
                json.dumps(
                    {
                        "local_text_gate": {
                            "rows": [
                                {
                                    "reason": "latin_text_without_editor_card_evidence",
                                    "role": "hardsub",
                                    "text": "Rubidium",
                                    "confidence": 0.99,
                                    "box": source_box,
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps(
                    {
                        "by_frame": {
                            str(frame): [
                                {"boxes": [765.0, 910.0, 1235.0, 1012.0]}
                            ]
                            for frame in range(10, 16)
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = score_phase1_out(root)

            self.assertEqual(result["uncovered_dense_hardsub_spans"], [])
            self.assertEqual(
                result["locally_rejected_shadow_frames"], list(range(10, 16))
            )
            self.assertTrue(result["PASS"])

    def test_dense_detector_core_blocks_overexpanded_final_box(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "sub_01.jpg").touch()
            (root / "frames" / "sub_01.jpg").touch()
            (root / "master_timeline.json").write_text(
                json.dumps(
                    [
                        {
                            "text_id": "sub_01",
                            "start_frame": 10,
                            "end_frame": 19,
                            "box_coords": [500.0, 990.0, 1500.0, 1055.0],
                            "crop_path": "crops/sub_01.jpg",
                            "best_keyframe_path": "frames/sub_01.jpg",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 1,
                        "confirmed_tracks": 1,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            core = [650.0, 995.0, 1150.0, 1050.0]
            (root / "text_frame_coverage.json").write_text(
                json.dumps(
                    {
                        "by_frame": {
                            str(frame): [{"boxes": core, "role": "hardsub"}]
                            for frame in range(10, 20)
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = score_phase1_out(root)

            self.assertEqual(
                result["overexpanded_dense_hardsubs"],
                [["sub_01", 1000.0, 500.0, 2.0]],
            )
            self.assertFalse(
                result["checks"]["no_overexpanded_dense_hardsubs"]
            )
            self.assertFalse(result["PASS"])

    def test_adjacent_thin_detector_shadow_is_explained_by_active_hardsub(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "sub_01.jpg").touch()
            (root / "frames" / "sub_01.jpg").touch()
            timeline = [
                {
                    "text_id": "sub_01",
                    "start_frame": 10,
                    "end_frame": 19,
                    "box_coords": [600.0, 1000.0, 1300.0, 1055.0],
                    "crop_path": "crops/sub_01.jpg",
                    "best_keyframe_path": "frames/sub_01.jpg",
                }
            ]
            (root / "master_timeline.json").write_text(
                json.dumps(timeline), encoding="utf-8"
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 1,
                        "confirmed_tracks": 1,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            main = [650.0, 1005.0, 1250.0, 1050.0]
            upper_shadow = [680.0, 950.0, 1120.0, 990.0]
            (root / "text_frame_coverage.json").write_text(
                json.dumps(
                    {
                        "by_frame": {
                            str(frame): [
                                {"boxes": main, "role": "hardsub"},
                                {"boxes": upper_shadow, "role": "hardsub"},
                            ]
                            for frame in range(10, 20)
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = score_phase1_out(root)

            self.assertEqual(result["uncovered_dense_hardsub_spans"], [])
            self.assertTrue(result["PASS"])

    def test_semantic_scene_role_requires_matching_audit_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crops").mkdir()
            (root / "frames").mkdir()
            (root / "qa").mkdir()
            (root / "crops" / "sub_01.jpg").touch()
            (root / "frames" / "sub_01.jpg").touch()
            box = [450.0, 300.0, 700.0, 340.0]
            timeline = [
                {
                    "text_id": "sub_01",
                    "start_frame": 0,
                    "end_frame": 19,
                    "box_coords": box,
                    "crop_path": "crops/sub_01.jpg",
                    "best_keyframe_path": "frames/sub_01.jpg",
                    "semantic_role": "semantic_scene_label",
                    "hit_count": 20,
                }
            ]
            (root / "master_timeline.json").write_text(
                json.dumps(timeline), encoding="utf-8"
            )
            (root / "qa" / "quality_report.json").write_text(
                json.dumps(
                    {
                        "tracks": 1,
                        "confirmed_tracks": 1,
                        "uncertain_tracks": 0,
                        "review_queue": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "text_frame_coverage.json").write_text(
                json.dumps(
                    {"frame_width": 1920, "frame_height": 1080, "by_frame": {}}
                ),
                encoding="utf-8",
            )
            before_after = {
                "local_text_gate": {
                    "rows": [],
                    "semantic_scene_label": {
                        "rows": [
                            {
                                "semantic_role": "semantic_scene_label",
                                "start_frame": 0,
                                "end_frame": 19,
                                "box": box,
                                "text": "Earth",
                                "confidence": 0.99,
                            }
                        ]
                    },
                }
            }
            (root / "qa" / "before_after.json").write_text(
                json.dumps(before_after), encoding="utf-8"
            )

            verified = score_phase1_out(root)
            self.assertEqual(verified["roles"]["semantic_scene_label"], 1)
            self.assertTrue(verified["PASS"])

            before_after["local_text_gate"]["semantic_scene_label"]["rows"] = []
            (root / "qa" / "before_after.json").write_text(
                json.dumps(before_after), encoding="utf-8"
            )
            unverified = score_phase1_out(root)
            self.assertEqual(unverified["unverified_semantic_scene_tracks"], ["sub_01"])
            self.assertFalse(unverified["PASS"])


if __name__ == "__main__":
    unittest.main()
