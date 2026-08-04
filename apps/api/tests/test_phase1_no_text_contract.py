from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.media_pipeline.frame_sampling.phase1_no_text_contract import (
    Phase1NoTextContractError,
    evaluate_no_text_review,
    evaluate_no_text_operator_gate,
    prepare_no_text_review,
    record_no_text_decision,
)


class Phase1NoTextContractTests(unittest.TestCase):
    def _root(self, tmp: str, *, uncovered: list[list[int]] | None = None) -> Path:
        root = Path(tmp)
        (root / "qa").mkdir()
        (root / "master_timeline.json").write_text("[]", encoding="utf-8")
        (root / "phase1_score.json").write_text(
            json.dumps(
                {
                    "PASS": False,
                    "tracks": 0,
                    "uncovered_dense_hardsub_spans": uncovered or [],
                    "high_confidence_local_text_rejects": [],
                }
            ),
            encoding="utf-8",
        )
        (root / "text_frame_coverage.json").write_text(
            json.dumps({"n_frames_with_text": 12, "n_hits": 30}),
            encoding="utf-8",
        )
        (root / "qa" / "quality_report.json").write_text(
            json.dumps({"uncertain_tracks": 0}), encoding="utf-8"
        )
        (root / "phase1_meta.json").write_text(
            json.dumps(
                {"video": "source.webm", "n_scanned_frames": 120}
            ),
            encoding="utf-8",
        )
        (root / "source.webm").write_bytes(b"source-v1")
        return root

    def test_candidate_waits_for_operator_and_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._root(tmp)
            first = prepare_no_text_review(root)
            second = prepare_no_text_review(root)
            gate = evaluate_no_text_review(root)
            self.assertEqual(first, second)
            self.assertEqual(first["schema_version"], "phase1_no_text_review_v2")
            self.assertEqual(first["source_video"]["size_bytes"], 9)
            self.assertEqual(gate["status"], "WAITING_NO_TEXT_OPERATOR_REVIEW")
            self.assertTrue(gate["operator_touch_required"])

    def test_hash_bound_operator_approval_and_stale_rejection(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._root(tmp)
            approval = record_no_text_decision(
                root,
                operator_id="operator-1",
                decision="NO_TEXT_CONFIRMED",
            )
            self.assertEqual(
                evaluate_no_text_review(root)["status"],
                "NO_TEXT_OPERATOR_APPROVED",
            )
            approval["operator_id"] = "tampered"
            (root / "phase1_no_text_approval.json").write_text(
                json.dumps(approval), encoding="utf-8"
            )
            with self.assertRaises(Phase1NoTextContractError):
                evaluate_no_text_review(root)

    def test_source_byte_change_makes_existing_approval_stale(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._root(tmp)
            record_no_text_decision(
                root,
                operator_id="operator-1",
                decision="NO_TEXT_CONFIRMED",
            )

            (root / "source.webm").write_bytes(b"source-v2")

            with self.assertRaisesRegex(Phase1NoTextContractError, "stale"):
                evaluate_no_text_review(root)

            gate = evaluate_no_text_operator_gate(root)
            self.assertEqual(gate["status"], "WAITING_NO_TEXT_OPERATOR_REVIEW")
            self.assertEqual(gate["approval_state"], "STALE_APPROVAL")
            self.assertTrue(gate["operator_touch_required"])

    def test_uncovered_text_is_never_no_text_eligible(self) -> None:
        with TemporaryDirectory() as tmp:
            root = self._root(tmp, uncovered=[[10, 20, 11]])
            with self.assertRaises(Phase1NoTextContractError):
                prepare_no_text_review(root)


if __name__ == "__main__":
    unittest.main()
