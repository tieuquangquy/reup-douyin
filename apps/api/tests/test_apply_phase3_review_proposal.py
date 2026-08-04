from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.apply_phase3_review_proposal import (
    Phase3ProposalApprovalError,
    apply_review_proposal,
)


def _json_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class ApplyPhase3ReviewProposalTests(unittest.TestCase):
    @staticmethod
    def _fixture(tmp: str) -> tuple[Path, Path]:
        root = Path(tmp)
        authority = {"path": "phase2_handoff.json", "sha256": "a" * 64}
        queue = {
            "phase2_handoff_ref": authority,
            "content_objects": [
                {
                    "content_id": "ocr_content_001",
                    "vi_text_candidate": "Protein",
                    "review_input_sha256": "b" * 64,
                },
                {
                    "content_id": "ocr_content_002",
                    "vi_text_candidate": "Muối",
                    "review_input_sha256": "c" * 64,
                },
            ],
        }
        queue_path = root / "phase3_review_queue.json"
        queue_path.write_text(json.dumps(queue), encoding="utf-8")
        (root / "phase3_approvals.json").write_text(
            json.dumps({"phase2_handoff_ref": authority, "approvals": []}),
            encoding="utf-8",
        )
        proposal = {
            "schema_version": "phase3_translation_review_proposal_v1",
            "status": "PROPOSAL_READY_FOR_OPERATOR_REVIEW",
            "operator_approval_written": False,
            "phase2_handoff_ref": authority,
            "phase3_review_queue_ref": {
                "path": queue_path.name,
                "sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
            },
            "proposals": [
                {
                    "content_id": "ocr_content_001",
                    "recommendation": "EDIT",
                    "review_input_sha256": "b" * 64,
                    "vi_text_candidate": "Protein",
                    "vi_text_proposed": "Đạm",
                },
                {
                    "content_id": "ocr_content_002",
                    "recommendation": "APPROVE",
                    "review_input_sha256": "c" * 64,
                    "vi_text_candidate": "Muối",
                    "vi_text_proposed": "Muối",
                },
            ],
        }
        proposal["proposal_sha256"] = _json_hash(proposal)
        proposal_path = root / "phase3_review_proposal.json"
        proposal_path.write_text(
            json.dumps(proposal, ensure_ascii=False), encoding="utf-8"
        )
        return root, proposal_path

    def test_applies_complete_authorized_proposal_and_writes_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            root, proposal = self._fixture(tmp)
            audit = apply_review_proposal(
                root_dir=root,
                proposal_path=proposal,
                operator_id="operator",
                approved_at="2026-07-28T00:00:00+00:00",
            )
            approvals = json.loads(
                (root / "phase3_approvals.json").read_text(encoding="utf-8")
            )

        self.assertEqual(audit["counts"]["edited"], 1)
        self.assertEqual(
            [row["decision"] for row in approvals["approvals"]],
            ["EDIT", "APPROVE"],
        )
        self.assertEqual(approvals["approvals"][0]["vi_text_approved"], "Đạm")

    def test_rejects_stale_queue(self) -> None:
        with TemporaryDirectory() as tmp:
            root, proposal = self._fixture(tmp)
            (root / "phase3_review_queue.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(Phase3ProposalApprovalError):
                apply_review_proposal(
                    root_dir=root,
                    proposal_path=proposal,
                    operator_id="operator",
                    approved_at="2026-07-28T00:00:00+00:00",
                )


if __name__ == "__main__":
    unittest.main()
