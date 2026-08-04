from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_phase2_review_proposal import (
    Phase2ReviewProposalError,
    build_review_proposal,
    validate_review_proposal,
)


class BuildPhase2ReviewProposalTests(unittest.TestCase):
    def _fixture(self, root: Path, *, reviewed: bool = True) -> tuple[Path, Path]:
        target = root / "target"
        reference = root / "reference"
        (target / "crops").mkdir(parents=True)
        (reference / "crops").mkdir(parents=True)
        (target / "crops" / "sub_01.jpg").write_bytes(b"same")
        (target / "crops" / "sub_02.jpg").write_bytes(b"changed")
        (reference / "crops" / "old_01.jpg").write_bytes(b"same")
        queue = {
            "phase1_ref": {"path": "master_timeline.json", "sha256": "a" * 64},
            "content_objects": [
                {
                    "content_id": "ocr_content_001",
                    "geometry_refs": ["sub_01"],
                    "ocr_text_candidate": "exact",
                    "review_input_sha256": "b" * 64,
                    "review_assets": [],
                },
                {
                    "content_id": "ocr_content_002",
                    "geometry_refs": ["sub_02"],
                    "ocr_text_candidate": "wr0ng",
                    "review_input_sha256": "c" * 64,
                    "review_assets": [],
                },
            ],
        }
        (target / "phase2_review_queue.json").write_text(
            json.dumps(queue), encoding="utf-8"
        )
        (reference / "phase2_ocr_timeline.json").write_text(
            json.dumps(
                {
                    "content_objects": [
                        {
                            "content_id": "old_content",
                            "geometry_refs": ["old_01"],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (reference / "phase2_approvals.json").write_text(
            json.dumps(
                {
                    "approvals": [
                        {
                            "content_id": "old_content",
                            "decision": "APPROVE" if reviewed else "",
                            "ocr_text_approved": "exact",
                            "reviewer": "operator" if reviewed else None,
                            "reviewed_at": (
                                "2026-07-27T00:00:00+00:00" if reviewed else None
                            ),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return target, reference

    def test_separates_exact_review_authority_from_unapproved_suggestion(self) -> None:
        with TemporaryDirectory() as tmp:
            target, reference = self._fixture(Path(tmp))

            proposal = build_review_proposal(
                target_root=target,
                reference_root=reference,
                suggestions={"ocr_content_002": "wrong"},
                generated_at="2026-07-28T00:00:00+00:00",
            )
            validate_review_proposal(target_root=target, proposal=proposal)

            self.assertEqual(proposal["counts"]["carry_forward_eligible"], 1)
            self.assertEqual(proposal["counts"]["operator_review_required"], 1)
            self.assertEqual(
                proposal["proposals"][0]["proposal_status"],
                "CARRY_FORWARD_ELIGIBLE",
            )
            self.assertEqual(
                proposal["proposals"][1]["suggestion_source"],
                "explicit_unapproved_suggestion",
            )
            self.assertEqual(proposal["proposals"][1]["proposed_decision"], "EDIT")

    def test_unreviewed_placeholder_never_becomes_carry_authority(self) -> None:
        with TemporaryDirectory() as tmp:
            target, reference = self._fixture(Path(tmp), reviewed=False)

            proposal = build_review_proposal(
                target_root=target,
                reference_root=reference,
                generated_at="2026-07-28T00:00:00+00:00",
            )

            self.assertEqual(proposal["counts"]["carry_forward_eligible"], 0)
            self.assertEqual(proposal["counts"]["operator_review_required"], 2)

    def test_proposes_one_translation_for_touching_operator_corrections(self) -> None:
        with TemporaryDirectory() as tmp:
            target, reference = self._fixture(Path(tmp), reviewed=False)
            queue_path = target / "phase2_review_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["content_objects"][0].update(
                {
                    "ocr_text_candidate": "下入西",
                    "review_assets": [{"start_frame": 10, "end_frame": 20}],
                }
            )
            queue["content_objects"][1].update(
                {
                    "ocr_text_candidate": "下西",
                    "review_assets": [{"start_frame": 21, "end_frame": 30}],
                }
            )
            queue_path.write_text(json.dumps(queue), encoding="utf-8")

            proposal = build_review_proposal(
                target_root=target,
                reference_root=reference,
                suggestions={
                    "ocr_content_001": "下入西红柿",
                    "ocr_content_002": "下入西红柿",
                },
                generated_at="2026-07-28T00:00:00+00:00",
            )

            self.assertEqual(proposal["counts"]["transition_merge_groups"], 1)
            merge = proposal["transition_merge_groups"][0]
            self.assertEqual(
                merge["source_content_ids"],
                ["ocr_content_001", "ocr_content_002"],
            )
            self.assertEqual(
                merge["status"], "MERGE_AFTER_EXACT_OPERATOR_APPROVAL"
            )

    def test_validation_rejects_stale_queue(self) -> None:
        with TemporaryDirectory() as tmp:
            target, reference = self._fixture(Path(tmp))
            proposal = build_review_proposal(
                target_root=target,
                reference_root=reference,
                generated_at="2026-07-28T00:00:00+00:00",
            )
            queue_path = target / "phase2_review_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["changed"] = True
            queue_path.write_text(json.dumps(queue), encoding="utf-8")

            with self.assertRaises(Phase2ReviewProposalError):
                validate_review_proposal(target_root=target, proposal=proposal)

    def test_structured_recommendations_keep_rejects_and_input_fail_closed(self) -> None:
        with TemporaryDirectory() as tmp:
            target, reference = self._fixture(Path(tmp), reviewed=False)

            proposal = build_review_proposal(
                target_root=target,
                reference_root=reference,
                suggestions={
                    "ocr_content_001": {
                        "decision": "REJECT_UI",
                        "reason": "source UI icon",
                    },
                    "ocr_content_002": {
                        "decision": "OPERATOR_INPUT_REQUIRED",
                        "reason": "blurred crop",
                    },
                },
                generated_at="2026-07-28T00:00:00+00:00",
            )
            validate_review_proposal(target_root=target, proposal=proposal)

            self.assertEqual(proposal["counts"]["proposed_reject_ui"], 1)
            self.assertEqual(proposal["counts"]["operator_input_required"], 1)
            self.assertEqual(
                proposal["proposals"][0]["proposed_decision"], "REJECT_UI"
            )
            self.assertIsNone(proposal["proposals"][1]["proposed_decision"])


if __name__ == "__main__":
    unittest.main()
