from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.build_phase3_reference_edits import build_reference_edits


class BuildPhase3ReferenceEditsTests(unittest.TestCase):
    def test_uses_only_exact_chinese_with_real_review_metadata(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            reference = root / "reference"
            target.mkdir()
            reference.mkdir()
            (target / "phase3_review_queue.json").write_text(
                json.dumps(
                    {
                        "content_objects": [
                            {"content_id": "new_1", "zh_approved": "鸡腿"},
                            {"content_id": "new_2", "zh_approved": "新标题"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (reference / "phase3_translation_timeline.json").write_text(
                json.dumps(
                    {
                        "content_objects": [
                            {"content_id": "old_1", "zh_approved": "鸡腿"},
                            {"content_id": "old_2", "zh_approved": "新标题"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (reference / "phase3_approvals.json").write_text(
                json.dumps(
                    {
                        "approvals": [
                            {
                                "content_id": "old_1",
                                "decision": "APPROVE",
                                "vi_text_approved": "Đùi gà",
                                "reviewer": "operator",
                                "reviewed_at": "2026-07-27T00:00:00+00:00",
                            },
                            {
                                "content_id": "old_2",
                                "decision": "",
                                "vi_text_approved": "Tiêu đề mới",
                                "reviewer": None,
                                "reviewed_at": None,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            payload = build_reference_edits(
                target_root=target, reference_root=reference
            )

            self.assertEqual(payload["counts"]["exact_reviewed_matches"], 1)
            self.assertEqual(payload["unmatched_content_ids"], ["new_2"])
            self.assertEqual(payload["edits"]["new_1"]["vi_text"], "Đùi gà")


if __name__ == "__main__":
    unittest.main()
