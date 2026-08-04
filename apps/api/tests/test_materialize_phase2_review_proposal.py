from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_phase2_review_proposal import build_review_proposal
from scripts.materialize_phase2_review_proposal import (
    Phase2ProposalMaterializationError,
    materialize_approved_proposal,
)


class MaterializePhase2ReviewProposalTests(unittest.TestCase):
    def _proposal(self, root: Path) -> tuple[Path, Path, dict]:
        target = root / "target"
        reference = root / "reference"
        (target / "crops").mkdir(parents=True)
        (reference / "crops").mkdir(parents=True)
        (target / "crops" / "sub_01.jpg").write_bytes(b"new")
        queue = {
            "phase1_ref": {"path": "master_timeline.json", "sha256": "a" * 64},
            "content_objects": [
                {
                    "content_id": "ocr_content_001",
                    "geometry_refs": ["sub_01"],
                    "ocr_text_candidate": "wr0ng",
                    "review_input_sha256": "b" * 64,
                    "review_assets": [],
                }
            ],
        }
        (target / "phase2_review_queue.json").write_text(
            json.dumps(queue), encoding="utf-8"
        )
        (reference / "phase2_ocr_timeline.json").write_text(
            json.dumps({"content_objects": []}), encoding="utf-8"
        )
        (reference / "phase2_approvals.json").write_text(
            json.dumps({"approvals": []}), encoding="utf-8"
        )
        proposal = build_review_proposal(
            target_root=target,
            reference_root=reference,
            suggestions={"ocr_content_001": "wrong"},
            generated_at="2026-07-28T00:00:00+00:00",
        )
        proposal_path = target / "phase2_review_proposal.json"
        proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
        return target, proposal_path, proposal

    def test_requires_exact_operator_approved_proposal_hash(self) -> None:
        with TemporaryDirectory() as tmp:
            target, proposal_path, proposal = self._proposal(Path(tmp))

            with self.assertRaises(Phase2ProposalMaterializationError):
                materialize_approved_proposal(
                    target_root=target,
                    proposal_path=proposal_path,
                    approved_proposal_sha256="0" * 64,
                    reviewer="operator",
                    reviewed_at="2026-07-28T01:00:00+00:00",
                )

            decisions = materialize_approved_proposal(
                target_root=target,
                proposal_path=proposal_path,
                approved_proposal_sha256=proposal["proposal_sha256"],
                reviewer="operator",
                reviewed_at="2026-07-28T01:00:00+00:00",
            )

            self.assertEqual(decisions["decisions"][0]["decision"], "EDIT")
            self.assertEqual(
                decisions["approved_proposal_ref"]["proposal_sha256"],
                proposal["proposal_sha256"],
            )

    def test_materializes_explicit_reject_ui_without_ocr_text(self) -> None:
        with TemporaryDirectory() as tmp:
            target, proposal_path, _proposal = self._proposal(Path(tmp))
            proposal = build_review_proposal(
                target_root=target,
                reference_root=Path(tmp) / "reference",
                suggestions={
                    "ocr_content_001": {
                        "decision": "REJECT_UI",
                        "reason": "status icon",
                    }
                },
                generated_at="2026-07-28T00:00:00+00:00",
            )
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

            decisions = materialize_approved_proposal(
                target_root=target,
                proposal_path=proposal_path,
                approved_proposal_sha256=proposal["proposal_sha256"],
                reviewer="operator",
                reviewed_at="2026-07-28T01:00:00+00:00",
            )

            self.assertEqual(decisions["decisions"][0]["decision"], "REJECT_UI")
            self.assertIsNone(decisions["decisions"][0]["ocr_text_approved"])


if __name__ == "__main__":
    unittest.main()
