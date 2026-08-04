from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_phase2_review_from_reference import (
    ReviewReferenceError,
    build_decisions,
)


class BuildPhase2ReviewFromReferenceTests(unittest.TestCase):
    def test_inherits_only_identical_crop_and_hashes_complete_decisions(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            reference = root / "reference"
            (target / "crops").mkdir(parents=True)
            (reference / "crops").mkdir(parents=True)
            (target / "crops" / "sub_01.jpg").write_bytes(b"same-crop")
            (target / "crops" / "sub_02.jpg").write_bytes(b"new-crop")
            (reference / "crops" / "old_01.jpg").write_bytes(b"same-crop")
            queue = {
                "content_objects": [
                    {
                        "content_id": "ocr_content_001",
                        "geometry_refs": ["sub_01"],
                        "ocr_text_candidate": "approved",
                    },
                    {
                        "content_id": "ocr_content_002",
                        "geometry_refs": ["sub_02"],
                        "ocr_text_candidate": "bad",
                    },
                ]
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
                                "decision": "APPROVE",
                                "ocr_text_approved": "approved",
                                "reviewer": "operator",
                                "reviewed_at": "2026-07-26T00:00:00+00:00",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            payload = build_decisions(
                target_root=target,
                reference_root=reference,
                overrides={"ocr_content_002": "corrected"},
                reviewer="operator",
                reviewed_at="2026-07-27T00:00:00+00:00",
            )

            self.assertEqual(
                [row["decision"] for row in payload["decisions"]],
                ["APPROVE", "EDIT"],
            )
            unsigned = dict(payload)
            claimed = unsigned.pop("decisions_sha256")
            encoded = json.dumps(
                unsigned,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self.assertEqual(claimed, hashlib.sha256(encoded).hexdigest())

    def test_fails_closed_when_a_crop_has_no_review_authority(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            reference = root / "reference"
            (target / "crops").mkdir(parents=True)
            (reference / "crops").mkdir(parents=True)
            (target / "crops" / "sub_01.jpg").write_bytes(b"unreviewed")
            (target / "phase2_review_queue.json").write_text(
                json.dumps(
                    {
                        "content_objects": [
                            {
                                "content_id": "ocr_content_001",
                                "geometry_refs": ["sub_01"],
                                "ocr_text_candidate": "candidate",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (reference / "phase2_ocr_timeline.json").write_text(
                json.dumps({"content_objects": []}), encoding="utf-8"
            )
            (reference / "phase2_approvals.json").write_text(
                json.dumps({"approvals": []}), encoding="utf-8"
            )

            with self.assertRaises(ReviewReferenceError):
                build_decisions(
                    target_root=target,
                    reference_root=reference,
                    overrides={},
                    reviewer="operator",
                    reviewed_at="2026-07-27T00:00:00+00:00",
                )

    def test_unreviewed_placeholder_is_not_reference_authority(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            reference = root / "reference"
            (target / "crops").mkdir(parents=True)
            (reference / "crops").mkdir(parents=True)
            (target / "crops" / "sub_01.jpg").write_bytes(b"same-crop")
            (reference / "crops" / "old_01.jpg").write_bytes(b"same-crop")
            (target / "phase2_review_queue.json").write_text(
                json.dumps(
                    {
                        "content_objects": [
                            {
                                "content_id": "ocr_content_001",
                                "geometry_refs": ["sub_01"],
                                "ocr_text_candidate": "candidate",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
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
                                "decision": "",
                                "ocr_text_approved": "candidate",
                                "reviewer": None,
                                "reviewed_at": None,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ReviewReferenceError):
                build_decisions(
                    target_root=target,
                    reference_root=reference,
                    overrides={},
                    reviewer="operator",
                    reviewed_at="2026-07-27T00:00:00+00:00",
                )


if __name__ == "__main__":
    unittest.main()
