from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_phase3_review_proposal import (
    Phase3ReviewProposalError,
    build_review_proposal,
    render_review_proposal_markdown,
)
from src.media_pipeline.translator.phase3_contract import (
    _approval_preserves_protected_tokens,
)


class BuildPhase3ReviewProposalTests(unittest.TestCase):
    @staticmethod
    def _root(tmp: str) -> Path:
        root = Path(tmp)
        queue = {
            "phase2_handoff_ref": {"path": "phase2_handoff.json", "sha256": "a" * 64},
            "content_objects": [
                {
                    "content_id": "ocr_content_001",
                    "zh_approved": "清水130g",
                    "roles": ["mid_label"],
                    "vi_text_candidate": "Nước lọc 130 g",
                    "review_input_sha256": "b" * 64,
                    "quality_flags": [],
                    "unit_tokens": [{"raw": "g", "canonical": "g"}],
                },
                {
                    "content_id": "ocr_content_002",
                    "zh_approved": "蛋白质",
                    "roles": ["mid_label"],
                    "vi_text_candidate": "Protein",
                    "review_input_sha256": "c" * 64,
                    "quality_flags": [],
                    "unit_tokens": [],
                },
            ],
        }
        (root / "phase3_review_queue.json").write_text(
            json.dumps(queue), encoding="utf-8"
        )
        return root

    def test_builds_complete_self_hashed_non_approval_proposal(self) -> None:
        with TemporaryDirectory() as tmp:
            proposal = build_review_proposal(
                root_dir=self._root(tmp),
                edits={
                    "ocr_content_002": {
                        "vi_text": "Đạm",
                        "reasons": ["ui_consistency"],
                    }
                },
                proposal_author="reviewer-assist",
                created_at="2026-07-28T00:00:00+00:00",
            )

        self.assertFalse(proposal["operator_approval_written"])
        self.assertEqual(proposal["summary"]["recommended_edits"], 1)
        self.assertEqual(
            [row["recommendation"] for row in proposal["proposals"]],
            ["APPROVE", "EDIT"],
        )
        unsigned = dict(proposal)
        claimed = unsigned.pop("proposal_sha256")
        encoded = json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(claimed, hashlib.sha256(encoded).hexdigest())
        markdown = render_review_proposal_markdown(proposal)
        self.assertIn("ocr_content_002", markdown)
        self.assertNotIn("ocr_content_001 |", markdown)

    def test_rejects_edit_that_changes_protected_number(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(Phase3ReviewProposalError):
                build_review_proposal(
                    root_dir=self._root(tmp),
                    edits={
                        "ocr_content_001": {
                            "vi_text": "Nước lọc 120 g",
                            "reasons": [],
                        }
                    },
                    proposal_author="reviewer-assist",
                    created_at="2026-07-28T00:00:00+00:00",
                )

    def test_allows_contextual_counter_and_unit_spacing_localization(self) -> None:
        self.assertTrue(
            _approval_preserves_protected_tokens(
                {"unit_tokens": [{"raw": "个", "canonical": "cái"}]},
                candidate="3 cái trứng",
                approved="3 quả trứng",
            )
        )
        self.assertTrue(
            _approval_preserves_protected_tokens(
                {"unit_tokens": [{"raw": "g", "canonical": "g"}]},
                candidate="Thêm 2g dầu",
                approved="Thêm 2 g dầu",
            )
        )


if __name__ == "__main__":
    unittest.main()
