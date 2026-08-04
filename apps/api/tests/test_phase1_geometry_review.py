from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.media_pipeline.frame_sampling.phase1_geometry_review import (
    Phase1GeometryReviewError,
    apply_phase1_geometry_materialization,
    evaluate_phase1_geometry_operator_gate,
    evaluate_phase1_geometry_operator_gate_safe,
    load_phase1_geometry_materialization,
    prepare_phase1_geometry_review,
    record_phase1_geometry_decisions,
)


class Phase1GeometryReviewTests(unittest.TestCase):
    def _root(self, tmp: str, *, unsupported_failure: bool = False) -> Path:
        root = Path(tmp)
        (root / "qa" / "overlays").mkdir(parents=True)
        (root / "qa" / "boundaries").mkdir(parents=True)
        (root / "qa" / "boundary_crops").mkdir(parents=True)
        (root / "crops").mkdir()
        (root / "frames").mkdir()
        (root / "source.mp4").write_bytes(b"source-v1")
        (root / "crops" / "sub_01.jpg").write_bytes(b"crop")
        (root / "frames" / "sub_01.jpg").write_bytes(b"frame")
        (root / "qa" / "overlays" / "sub_01.jpg").write_bytes(b"overlay")
        (root / "qa" / "boundaries" / "sub_01.jpg").write_bytes(b"boundary")
        track = {
            "text_id": "sub_01",
            "start_frame": 10,
            "end_frame": 19,
            "box_coords": [1.0, 90.0, 220.0, 116.0],
            "best_frame_index": 14,
            "hit_count": 2,
            "crop_path": "crops/sub_01.jpg",
            "best_keyframe_path": "frames/sub_01.jpg",
        }
        (root / "master_timeline.json").write_text(
            json.dumps([track]), encoding="utf-8"
        )
        checks = {
            "has_tracks": True,
            "has_quality_report": True,
            "has_text_frame_coverage": True,
            "no_uncertain_tracks": False,
            "crops_complete": not unsupported_failure,
            "keyframes_complete": True,
        }
        (root / "phase1_score.json").write_text(
            json.dumps(
                {
                    "PASS": False,
                    "tracks": 1,
                    "frame_size": [240, 120],
                    "empty_left_wide_hardsubs": ["sub_01"],
                    "checks": checks,
                }
            ),
            encoding="utf-8",
        )
        (root / "text_frame_coverage.json").write_text(
            json.dumps({"frame_width": 240, "frame_height": 120, "by_frame": {}}),
            encoding="utf-8",
        )
        (root / "qa" / "quality_report.json").write_text(
            json.dumps(
                {
                    "uncertain_tracks": 1,
                    "review_queue": [
                        {
                            "text_id": "sub_01",
                            "boundary_evidence": {
                                "status": "uncertain",
                                "reasons": ["frame_edge_box_review"],
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (root / "phase1_meta.json").write_text(
            json.dumps({"video": "source.mp4", "frame_count": 30}),
            encoding="utf-8",
        )
        return root

    def test_candidate_is_hash_bound_idempotent_and_waits(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._root(tmp)
            first = prepare_phase1_geometry_review(root)
            second = prepare_phase1_geometry_review(root)
            gate = evaluate_phase1_geometry_operator_gate(root)

            self.assertEqual(first, second)
            self.assertEqual(len(first["issues"]), 1)
            self.assertEqual(first["issues"][0]["issue_type"], "TRACK_GEOMETRY")
            self.assertIn("uncertain_track", first["issues"][0]["reasons"])
            self.assertIn("edge_geometry", first["issues"][0]["reasons"])
            self.assertEqual(gate["status"], "WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW")
            self.assertTrue(gate["operator_touch_required"])

    def test_approval_materializes_edit_without_approving_ocr(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._root(tmp)
            review = prepare_phase1_geometry_review(root)
            issue_id = review["issues"][0]["issue_id"]
            approval = record_phase1_geometry_decisions(
                root,
                operator_id="operator-1",
                decisions=[
                    {
                        "issue_id": issue_id,
                        "decision": "EDIT_GEOMETRY",
                        "geometry": {
                            "box_coords": [8.0, 91.0, 218.0, 116.0],
                            "start_frame": 11,
                            "end_frame": 19,
                        },
                    }
                ],
            )
            gate = evaluate_phase1_geometry_operator_gate(root)
            material = load_phase1_geometry_materialization(root)

            self.assertEqual(gate["status"], "PHASE1_GEOMETRY_OPERATOR_APPROVED")
            self.assertEqual(gate["next_stage"], "phase2")
            self.assertEqual(
                material["geometry_overrides"][0]["box_coords"],
                [8.0, 91.0, 218.0, 116.0],
            )
            self.assertIsNone(material["geometry_overrides"][0]["crop_path"])
            self.assertEqual(material["ocr_authority"], "NOT_APPROVED_BY_THIS_ARTIFACT")
            self.assertEqual(len(approval["approval_sha256"]), 64)
            timeline, ref = apply_phase1_geometry_materialization(
                root,
                json.loads((root / "master_timeline.json").read_text(encoding="utf-8")),
            )
            self.assertEqual(timeline[0]["box_coords"], [8.0, 91.0, 218.0, 116.0])
            self.assertIsNone(timeline[0]["crop_path"])
            self.assertEqual(ref["materialization_sha256"], material["materialization_sha256"])

    def test_source_drift_invalidates_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._root(tmp)
            review = prepare_phase1_geometry_review(root)
            record_phase1_geometry_decisions(
                root,
                operator_id="operator-1",
                decisions=[
                    {
                        "issue_id": review["issues"][0]["issue_id"],
                        "decision": "APPROVE_GEOMETRY",
                    }
                ],
            )
            (root / "source.mp4").write_bytes(b"source-v2")

            gate = evaluate_phase1_geometry_operator_gate_safe(root)

            self.assertEqual(gate["status"], "WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW")
            self.assertEqual(gate["approval_state"], "STALE_APPROVAL")

    def test_missing_crop_is_not_converted_into_geometry_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._root(tmp, unsupported_failure=True)
            with self.assertRaisesRegex(
                Phase1GeometryReviewError, "not geometry-review eligible"
            ):
                prepare_phase1_geometry_review(root)

    def test_decisions_must_cover_every_issue_once(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._root(tmp)
            prepare_phase1_geometry_review(root)
            with self.assertRaisesRegex(Phase1GeometryReviewError, "exactly once"):
                record_phase1_geometry_decisions(
                    root,
                    operator_id="operator-1",
                    decisions=[],
                )


if __name__ == "__main__":
    unittest.main()
