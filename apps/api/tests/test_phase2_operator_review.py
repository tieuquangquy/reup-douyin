from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.services.phase2_operator_review import apply_phase2_operator_review


def _self_hashed(payload: dict) -> dict:
    result = dict(payload)
    encoded = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    result["decisions_sha256"] = hashlib.sha256(encoded).hexdigest()
    return result


class Phase2OperatorReviewTests(unittest.TestCase):
    def test_applies_complete_fresh_decision_set_and_writes_audit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = {
                "phase1_ref": {"path": "master_timeline.json", "sha256": "a" * 64},
                "review_summary": {"unresolved": 2},
                "content_objects": [
                    {
                        "content_id": "ocr_content_001",
                        "ocr_text_candidate": "exact",
                        "review_input_sha256": "b" * 64,
                    },
                    {
                        "content_id": "ocr_content_002",
                        "ocr_text_candidate": "wr0ng",
                        "review_input_sha256": "c" * 64,
                    },
                ],
            }
            queue_path = root / "phase2_review_queue.json"
            queue_path.write_text(json.dumps(queue), encoding="utf-8")
            queue_sha = hashlib.sha256(queue_path.read_bytes()).hexdigest()
            decisions = _self_hashed(
                {
                    "reviewer": "operator-1",
                    "reviewed_at": "2026-07-27T00:00:00+00:00",
                    "review_queue_sha256": queue_sha,
                    "decisions": [
                        {
                            "content_id": "ocr_content_001",
                            "decision": "APPROVE",
                            "ocr_text_approved": "exact",
                        },
                        {
                            "content_id": "ocr_content_002",
                            "decision": "EDIT",
                            "ocr_text_approved": "wrong",
                        },
                    ],
                }
            )
            decisions_path = root / "decisions.json"
            decisions_path.write_text(json.dumps(decisions), encoding="utf-8")

            audit = apply_phase2_operator_review(
                root_dir=root, decisions_path=decisions_path
            )

            self.assertEqual(audit["counts"]["objects"], 2)
            self.assertEqual(audit["counts"]["edited"], 1)
            approvals = json.loads(
                (root / "phase2_approvals.json").read_text(encoding="utf-8")
            )
            self.assertEqual(approvals["approvals"][1]["ocr_text_approved"], "wrong")
            self.assertEqual(
                approvals["approvals"][0]["review_evidence"]["ocr_text_candidate"],
                "exact",
            )
            self.assertTrue((root / "phase2_operator_review_audit.json").is_file())

    def test_partial_review_preserves_only_fresh_existing_approvals(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            phase1_ref = {"path": "master_timeline.json", "sha256": "a" * 64}
            timeline = {
                "phase1_ref": phase1_ref,
                "content_objects": [
                    {
                        "content_id": "ocr_content_001",
                        "review_input_sha256": "b" * 64,
                    },
                    {
                        "content_id": "ocr_content_002",
                        "review_input_sha256": "c" * 64,
                    },
                    {
                        "content_id": "ocr_content_003",
                        "review_input_sha256": "d" * 64,
                    },
                ],
            }
            (root / "phase2_ocr_timeline.json").write_text(
                json.dumps(timeline), encoding="utf-8"
            )
            existing = {
                "schema_version": "phase2_approvals_v2",
                "phase1_ref": phase1_ref,
                "approvals": [
                    {
                        "content_id": "ocr_content_001",
                        "decision": "APPROVE",
                        "review_input_sha256": "b" * 64,
                        "ocr_text_approved": "first",
                        "reviewer": "operator-1",
                        "reviewed_at": "2026-07-27T00:00:00+00:00",
                    },
                    {
                        "content_id": "ocr_content_003",
                        "decision": "APPROVE",
                        "review_input_sha256": "x" * 64,
                        "ocr_text_approved": "stale",
                        "reviewer": "operator-1",
                        "reviewed_at": "2026-07-27T00:00:00+00:00",
                    },
                ],
            }
            (root / "phase2_approvals.json").write_text(
                json.dumps(existing), encoding="utf-8"
            )
            queue = {
                "phase1_ref": phase1_ref,
                "content_objects": [
                    {
                        "content_id": "ocr_content_002",
                        "ocr_text_candidate": "second",
                        "review_input_sha256": "c" * 64,
                    }
                ],
            }
            queue_path = root / "phase2_review_queue.json"
            queue_path.write_text(json.dumps(queue), encoding="utf-8")
            decisions = _self_hashed(
                {
                    "reviewer": "operator-2",
                    "reviewed_at": "2026-07-27T01:00:00+00:00",
                    "review_queue_sha256": hashlib.sha256(
                        queue_path.read_bytes()
                    ).hexdigest(),
                    "decisions": [
                        {
                            "content_id": "ocr_content_002",
                            "decision": "APPROVE",
                            "ocr_text_approved": "second",
                        }
                    ],
                }
            )
            decisions_path = root / "decisions.json"
            decisions_path.write_text(json.dumps(decisions), encoding="utf-8")

            audit = apply_phase2_operator_review(
                root_dir=root, decisions_path=decisions_path
            )

            approvals = json.loads(
                (root / "phase2_approvals.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [row["content_id"] for row in approvals["approvals"]],
                ["ocr_content_001", "ocr_content_002"],
            )
            self.assertEqual(audit["counts"]["preserved_fresh_approvals"], 1)


if __name__ == "__main__":
    unittest.main()
