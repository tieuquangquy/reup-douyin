from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_phase4_remediation_proposal import (
    Phase4RemediationProposalError,
    _mask_action,
    build_proposal,
)


class Phase4RemediationProposalTests(unittest.TestCase):
    def test_builds_hash_bound_operator_only_decisions(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "batch_regression_state.json").write_text(
                json.dumps({"cases": [{"case_id": "local_case", "status": "FAILED"}]}),
                encoding="utf-8",
            )
            (root / "phase4_visual_failure_triage_v22_4.json").write_text(
                json.dumps(
                    {
                        "status": "REMEDIATION_PROPOSAL_REQUIRED",
                        "cases": [
                            {
                                "case_id": "local_case",
                                "failure_class": "MASK_QUALITY_BLOCKED",
                                "text_id": "sub_01",
                                "frame_index": 10,
                                "recommendation": "CANDIDATE_DYNAMIC_MASK_OR_CAPTION_PANEL_FALLBACK",
                                "evidence": {},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "local_case").mkdir()
            payload = build_proposal(root)

        self.assertEqual(payload["status"], "PROPOSAL_READY_FOR_OPERATOR_REVIEW")
        self.assertFalse(payload["operator_approval_written"])
        self.assertFalse(payload["automatic_policy_changes_applied"])
        self.assertEqual(
            payload["decisions"][0]["decision"]["action"],
            "CAPTION_PANEL_FALLBACK_WITH_EXISTING_DAMAGE_BUDGET",
        )
        self.assertEqual(len(payload["proposal_sha256"]), 64)

    def test_rejects_unknown_failure_class(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "batch_regression_state.json").write_text(
                json.dumps({"cases": [{"case_id": "local_case", "status": "FAILED"}]}),
                encoding="utf-8",
            )
            (root / "phase4_visual_failure_triage_v22_4.json").write_text(
                json.dumps(
                    {
                        "status": "REMEDIATION_PROPOSAL_REQUIRED",
                        "cases": [
                            {
                                "case_id": "local_case",
                                "failure_class": "UNKNOWN",
                                "evidence": {},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "local_case").mkdir()
            with self.assertRaises(Phase4RemediationProposalError):
                build_proposal(root)

    def test_reference_plate_block_routes_to_bounded_micro_ui_fallback(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "batch_regression_state.json").write_text(
                json.dumps({"cases": [{"case_id": "local_case", "status": "FAILED"}]}),
                encoding="utf-8",
            )
            (root / "phase4_visual_failure_triage_v22_4.json").write_text(
                json.dumps(
                    {
                        "status": "REMEDIATION_PROPOSAL_REQUIRED",
                        "cases": [
                            {
                                "case_id": "local_case",
                                "failure_class": "REFERENCE_PLATE_ALIGNMENT_BLOCKED",
                                "text_id": "p4out_01",
                                "frame_index": 615,
                                "recommendation": "CANDIDATE_BOUNDED_MICRO_UI_SPATIAL_FALLBACK",
                                "evidence": {},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "local_case").mkdir()
            payload = build_proposal(root)

        self.assertEqual(
            payload["decisions"][0]["decision"]["action"],
            "BOUNDED_MICRO_UI_SPATIAL_FALLBACK_WITH_EXISTING_DAMAGE_BUDGET",
        )

    def test_isolated_mask_pass_routes_to_timing_and_cache_review(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "batch_regression_state.json").write_text(
                json.dumps({"cases": [{"case_id": "local_case", "status": "FAILED"}]}),
                encoding="utf-8",
            )
            (root / "phase4_visual_failure_triage_v22_4.json").write_text(
                json.dumps(
                    {
                        "status": "REMEDIATION_PROPOSAL_REQUIRED",
                        "cases": [
                            {
                                "case_id": "local_case",
                                "failure_class": "MASK_QUALITY_BLOCKED",
                                "text_id": "sub_02",
                                "frame_index": 79,
                                "recommendation": "REVIEW_MASK_POLICY_WITHOUT_THRESHOLD_RELAXATION",
                                "diagnostics": {"status": "PASS"},
                                "evidence": {},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "local_case").mkdir()
            payload = build_proposal(root)

        self.assertEqual(
            payload["decisions"][0]["decision"]["action"],
            "SPLIT_TRACK_TO_SOURCE_VISIBLE_INTERVALS_AND_SCOPE_MASK_CACHE",
        )

    def test_isolated_p4out_mask_pass_routes_to_confirmed_source_trim(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "batch_regression_state.json").write_text(
                json.dumps({"cases": [{"case_id": "local_case", "status": "FAILED"}]}),
                encoding="utf-8",
            )
            (root / "phase4_visual_failure_triage_v22_4.json").write_text(
                json.dumps(
                    {
                        "status": "REMEDIATION_PROPOSAL_REQUIRED",
                        "cases": [
                            {
                                "case_id": "local_case",
                                "failure_class": "MASK_QUALITY_BLOCKED",
                                "text_id": "p4out_01",
                                "frame_index": 680,
                                "recommendation": "REVIEW_MASK_POLICY_WITHOUT_THRESHOLD_RELAXATION",
                                "diagnostics": {"status": "PASS"},
                                "evidence": {},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "local_case").mkdir()
            payload = build_proposal(root)

        self.assertEqual(
            payload["decisions"][0]["decision"]["action"],
            "TRIM_OUTPUT_RESIDUAL_TRACK_BEFORE_CONFIRMED_SOURCE_CHANGE",
        )

    def test_aligned_exact_residual_routes_to_stylized_component_mask(self) -> None:
        decision = _mask_action(
            {
                "text_id": "p4out_exact",
                "recommendation": "REVIEW_MASK_POLICY_WITHOUT_THRESHOLD_RELAXATION",
                "diagnostics": {"status": "PASS"},
                "track": {
                    "render_policy": {
                        "context": {
                            "output_residual_geometry_aligned": True,
                            "output_residual_width_expanded": True,
                        }
                    }
                },
            }
        )

        self.assertEqual(
            decision["action"],
            "BOUNDED_EXACT_RESIDUAL_STYLIZED_COMPONENT_MASK",
        )

    def test_duplicate_output_residual_track_routes_to_guarded_drop(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "batch_regression_state.json").write_text(
                json.dumps({"cases": [{"case_id": "local_case", "status": "FAILED"}]}),
                encoding="utf-8",
            )
            (root / "phase4_visual_failure_triage_v22_4.json").write_text(
                json.dumps(
                    {
                        "status": "REMEDIATION_PROPOSAL_REQUIRED",
                        "cases": [
                            {
                                "case_id": "local_case",
                                "failure_class": "MASK_QUALITY_BLOCKED",
                                "text_id": "p4out_target",
                                "frame_index": 615,
                                "recommendation": "CANDIDATE_DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK",
                                "duplicate_output_residual_track": {
                                    "text_id": "p4out_existing",
                                    "geometry_overlap_over_smaller": 0.98,
                                },
                                "diagnostics": {"status": "PASS"},
                                "evidence": {},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "local_case").mkdir()
            payload = build_proposal(root)

        decision = payload["decisions"][0]["decision"]
        self.assertEqual(
            decision["action"], "DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK"
        )
        self.assertEqual(decision["duplicate_track_id"], "p4out_existing")

    def test_duplicate_output_residual_group_routes_to_guarded_group_drop(self) -> None:
        decision = _mask_action(
            {
                "recommendation": (
                    "CANDIDATE_DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK_GROUP"
                ),
                "duplicate_output_residual_track_group": {
                    "canonical_track_id": "p4out_aligned",
                    "drop_track_ids": ["p4out_old_a", "p4out_old_b"],
                },
            }
        )

        self.assertEqual(
            decision["action"], "DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK_GROUP"
        )
        self.assertEqual(decision["canonical_track_id"], "p4out_aligned")
        self.assertEqual(
            decision["drop_track_ids"], ["p4out_old_a", "p4out_old_b"]
        )


if __name__ == "__main__":
    unittest.main()
