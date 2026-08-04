from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.materialize_phase2_residual_remediation import (
    _sha256_json as remediation_hash,
    activate_cumulative_remediation,
    materialize_remediation,
    merge_cumulative_remediation,
    verify_remediation,
)
from scripts.rebind_phase3_approvals_after_residual_remediation import (
    Phase3ApprovalRebindError,
    rebind_approvals,
    stage_unapproved_placeholders,
)
from scripts.run_phase2_only import _remediation_approvals


def _carry() -> dict:
    return {
        "source_refs": {},
        "rows": [
            {
                "content_id": "ocr_content_001",
                "decision": "EDIT",
                "zh_approved": "花生油",
                "vi_text_candidate": "Dầu lạc",
                "vi_text_approved": "Dầu đậu phộng",
                "reviewer": "operator",
                "reviewed_at": "2026-07-28T00:00:00+00:00",
                "previous_review_input_sha256": "a" * 64,
            }
        ],
    }


class ResidualRemediationMaterializationTests(unittest.TestCase):
    def test_cumulative_generation_preserves_immutable_parent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = {
                "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
                "proposal_ref": {"proposal_sha256": "a" * 64},
                "authority_refs": {
                    "master_timeline": {"sha256": "m" * 64}
                },
                "approved_occurrences": [
                    {"occurrence": {"text_id": "p2r_old"}}
                ],
                "approved_geometry_overrides": [],
                "translation_carry_forward": _carry(),
            }
            parent["remediation_sha256"] = remediation_hash(parent)
            legacy = root / "phase2_residual_remediation.json"
            legacy.write_text(json.dumps(parent), encoding="utf-8")
            delta = {
                "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
                "proposal_ref": {"proposal_sha256": "b" * 64},
                "authority_refs": {
                    "master_timeline": {"sha256": "m" * 64}
                },
                "approved_occurrences": [
                    {"occurrence": {"text_id": "p2r_new"}}
                ],
                "approved_geometry_overrides": [],
                "translation_carry_forward": _carry(),
            }
            delta["remediation_sha256"] = remediation_hash(delta)

            merged = merge_cumulative_remediation(
                root_dir=root,
                delta=delta,
                parent_path=legacy,
            )

            self.assertTrue(verify_remediation(merged))
            self.assertEqual(merged["generation"], 2)
            self.assertEqual(
                [
                    row["occurrence"]["text_id"]
                    for row in merged["approved_occurrences"]
                ],
                ["p2r_old", "p2r_new"],
            )
            parent_ref = merged["authority_refs"]["parent_remediation"]
            self.assertNotEqual(parent_ref["path"], legacy.name)
            self.assertTrue((root / parent_ref["path"]).is_file())

    def test_activation_is_idempotent_for_the_same_proposal(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            delta = {
                "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
                "proposal_ref": {"proposal_sha256": "b" * 64},
                "authority_refs": {
                    "master_timeline": {"sha256": "m" * 64}
                },
                "approved_occurrences": [
                    {"occurrence": {"text_id": "p2r_new"}}
                ],
                "approved_geometry_overrides": [],
                "translation_carry_forward": _carry(),
            }
            delta["remediation_sha256"] = remediation_hash(delta)

            first_path, first = activate_cumulative_remediation(
                root_dir=root,
                delta=delta,
            )
            second_path, second = activate_cumulative_remediation(
                root_dir=root,
                delta=delta,
            )

            self.assertEqual(second_path, first_path)
            self.assertEqual(second, first)
            self.assertEqual(first["generation"], 1)
            self.assertTrue(
                (root / "phase2_residual_remediation_active.json").is_file()
            )

    def test_materializes_only_the_hash_approved_proposal(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "phase2_residual_remediation_proposal.json"
            proposal = {
                "proposal_sha256": "b" * 64,
                "authority_refs": {},
                "proposals": [
                    {
                        "remediation_id": "p2r_test",
                        "proposed_action": "ADD_PHASE2_OCCURRENCE",
                        "ocr_text_suggested": "170克",
                        "render_text_suggested": "170 g",
                        "localization": {"mode": "deterministic"},
                        "proposed_occurrence": {
                            "text_id": "p2r_test",
                            "start_frame": 10,
                            "end_frame": 20,
                        },
                    }
                ],
            }
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
            with (
                patch(
                    "scripts.materialize_phase2_residual_remediation.validate_proposal"
                ),
                patch(
                    "scripts.materialize_phase2_residual_remediation."
                    "_capture_translation_authority",
                    return_value=_carry(),
                ),
            ):
                payload = materialize_remediation(
                    root_dir=root,
                    proposal_path=proposal_path,
                    approved_proposal_sha256="b" * 64,
                    operator_id="operator",
                    approved_at="2026-07-28T01:00:00+00:00",
                )
            self.assertTrue(verify_remediation(payload))
            self.assertEqual(
                payload["approved_occurrences"][0]["ocr_text_approved"],
                "170克",
            )

    def test_builds_phase2_approval_from_exact_remediation_candidate(self) -> None:
        contract = {
            "track_enrichments": [
                {"text_id": "p2r_test", "content_id": "ocr_content_056"}
            ],
            "content_objects": [
                {
                    "content_id": "ocr_content_056",
                    "ocr_text_candidate": "170克",
                    "review_input_sha256": "c" * 64,
                }
            ],
        }
        approvals = _remediation_approvals(
            contract,
            {
                "p2r_test": {
                    "ocr_text_approved": "170克",
                    "vi_text_approved": "170 g",
                    "operator_review": {
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-28T01:00:00+00:00",
                    },
                }
            },
        )
        self.assertEqual(approvals["ocr_content_056"]["decision"], "APPROVE")
        self.assertEqual(approvals["ocr_content_056"]["vi_text_approved"], "170 g")

    def test_materializes_operator_approved_geometry_override(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposal_path = root / "phase2_residual_remediation_proposal.json"
            proposal = {
                "proposal_sha256": "b" * 64,
                "authority_refs": {},
                "proposals": [
                    {
                        "remediation_id": "p2r_expand",
                        "proposed_action": "EXPAND_EXISTING_PHASE2_GEOMETRY",
                        "ocr_text_suggested": "下入西红柿",
                        "render_text_suggested": "Cho cà chua vào",
                        "accepted_candidate_signatures": ["下入西红柿", "下人西红柿"],
                        "localization": {"mode": "translation_carry_forward_exact"},
                        "proposed_geometry_override": {
                            "target_text_id": "sub_08",
                            "start_frame": 341,
                            "end_frame": 354,
                            "original_box_coords": [488, 645, 677, 701],
                            "box_coords": [488, 645, 781, 701],
                        },
                    }
                ],
            }
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
            with (
                patch(
                    "scripts.materialize_phase2_residual_remediation.validate_proposal"
                ),
                patch(
                    "scripts.materialize_phase2_residual_remediation."
                    "_capture_translation_authority",
                    return_value=_carry(),
                ),
            ):
                payload = materialize_remediation(
                    root_dir=root,
                    proposal_path=proposal_path,
                    approved_proposal_sha256="b" * 64,
                    operator_id="operator",
                    approved_at="2026-07-28T01:00:00+00:00",
                )

        self.assertTrue(verify_remediation(payload))
        self.assertEqual(len(payload["approved_occurrences"]), 0)
        self.assertEqual(
            payload["approved_geometry_overrides"][0]["geometry_override"][
                "target_text_id"
            ],
            "sub_08",
        )

    def test_geometry_override_allows_only_hash_reviewed_candidate_edit(self) -> None:
        contract = {
            "track_enrichments": [
                {"text_id": "sub_08", "content_id": "ocr_content_008"}
            ],
            "content_objects": [
                {
                    "content_id": "ocr_content_008",
                    "ocr_text_candidate": "下人西红柿",
                    "review_input_sha256": "c" * 64,
                }
            ],
        }
        approvals = _remediation_approvals(
            contract,
            {
                "sub_08": {
                    "ocr_text_approved": "下入西红柿",
                    "vi_text_approved": "Cho cà chua vào",
                    "accepted_candidate_signatures": ["下人西红柿"],
                    "operator_review": {
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-28T01:00:00+00:00",
                    },
                }
            },
        )

        self.assertEqual(approvals["ocr_content_008"]["decision"], "EDIT")

    def test_geometry_override_allows_one_missing_glyph_but_no_substitution(self) -> None:
        contract = {
            "track_enrichments": [
                {"text_id": "sub_09", "content_id": "ocr_content_009"}
            ],
            "content_objects": [
                {
                    "content_id": "ocr_content_009",
                    "ocr_text_candidate": "下西红柿",
                    "review_input_sha256": "d" * 64,
                }
            ],
        }
        authority = {
            "sub_09": {
                "ocr_text_approved": "下入西红柿",
                "vi_text_approved": "Cho cà chua vào",
                "accepted_candidate_signatures": ["下入西红柿"],
                "operator_review": {
                    "reviewer": "operator",
                    "reviewed_at": "2026-07-28T01:00:00+00:00",
                },
            }
        }

        approvals = _remediation_approvals(contract, authority)
        self.assertEqual(approvals["ocr_content_009"]["decision"], "EDIT")

        contract["content_objects"][0]["ocr_text_candidate"] = "下人西红柿"
        with self.assertRaises(RuntimeError):
            _remediation_approvals(contract, authority)

    def test_hash_bound_visual_override_accepts_non_numeric_ocr_confusion(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jpg"
            crop = root / "crop.jpg"
            source.write_bytes(b"source")
            crop.write_bytes(b"crop")
            approved = "千卡千焦"
            contract = {
                "track_enrichments": [
                    {"text_id": "p2r_01", "content_id": "ocr_content_001"}
                ],
                "content_objects": [
                    {
                        "content_id": "ocr_content_001",
                        "ocr_text_candidate": "干卡干焦",
                        "review_input_sha256": "d" * 64,
                    }
                ],
            }
            authority = {
                "p2r_01": {
                    "ocr_text_approved": approved,
                    "vi_text_approved": "kcal/kJ",
                    "accepted_candidate_signatures": [],
                    "operator_review": {
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-28T01:00:00+00:00",
                    },
                    "visual_override": {
                        "policy_version": "phase2_operator_visual_override_v1",
                        "batch_decision_proposal_sha256": "a" * 64,
                        "cluster_evidence_sha256": "b" * 64,
                        "approved_source_text_sha256": hashlib.sha256(
                            approved.encode("utf-8")
                        ).hexdigest(),
                        "source_frame_ref": {
                            "path": source.name,
                            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        },
                        "crop_ref": {
                            "path": crop.name,
                            "sha256": hashlib.sha256(crop.read_bytes()).hexdigest(),
                        },
                    },
                }
            }

            approvals = _remediation_approvals(contract, authority, root=root)

            self.assertEqual(approvals["ocr_content_001"]["decision"], "EDIT")
            self.assertEqual(
                approvals["ocr_content_001"]["visual_override"]["cluster_id"],
                None,
            )

    def test_visual_override_rejects_candidate_with_different_numeric_shape(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jpg"
            crop = root / "crop.jpg"
            source.write_bytes(b"source")
            crop.write_bytes(b"crop")
            approved = "葱烧鸡腿饭"
            contract = {
                "track_enrichments": [
                    {"text_id": "p2r_01", "content_id": "ocr_content_001"}
                ],
                "content_objects": [
                    {
                        "content_id": "ocr_content_001",
                        "ocr_text_candidate": "1329千卡",
                        "review_input_sha256": "d" * 64,
                    }
                ],
            }
            authority = {
                "p2r_01": {
                    "ocr_text_approved": approved,
                    "vi_text_approved": "Cơm gà",
                    "accepted_candidate_signatures": [],
                    "operator_review": {
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-28T01:00:00+00:00",
                    },
                    "visual_override": {
                        "policy_version": "phase2_operator_visual_override_v1",
                        "batch_decision_proposal_sha256": "a" * 64,
                        "cluster_evidence_sha256": "b" * 64,
                        "approved_source_text_sha256": hashlib.sha256(
                            approved.encode("utf-8")
                        ).hexdigest(),
                        "source_frame_ref": {
                            "path": source.name,
                            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        },
                        "crop_ref": {
                            "path": crop.name,
                            "sha256": hashlib.sha256(crop.read_bytes()).hexdigest(),
                        },
                    },
                }
            }

            with self.assertRaises(RuntimeError):
                _remediation_approvals(contract, authority, root=root)

    def test_hash_bound_visual_override_accepts_adjacent_ui_date_prefix(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jpg"
            crop = root / "crop.jpg"
            source.write_bytes(b"source")
            crop.write_bytes(b"crop")
            approved = "早餐加餐"
            contract = {
                "track_enrichments": [
                    {"text_id": "p2r_01", "content_id": "ocr_content_001"}
                ],
                "content_objects": [
                    {
                        "content_id": "ocr_content_001",
                        "ocr_text_candidate": "4日早加餐",
                        "review_input_sha256": "d" * 64,
                    }
                ],
            }
            authority = {
                "p2r_01": {
                    "ocr_text_approved": approved,
                    "vi_text_approved": "Bữa phụ sáng",
                    "accepted_candidate_signatures": ["加", approved],
                    "operator_review": {
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-29T13:33:21+00:00",
                    },
                    "visual_override": {
                        "policy_version": "phase2_operator_visual_override_v1",
                        "batch_decision_proposal_sha256": "a" * 64,
                        "cluster_evidence_sha256": "b" * 64,
                        "approved_source_text_sha256": hashlib.sha256(
                            approved.encode("utf-8")
                        ).hexdigest(),
                        "source_frame_ref": {
                            "path": source.name,
                            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        },
                        "crop_ref": {
                            "path": crop.name,
                            "sha256": hashlib.sha256(crop.read_bytes()).hexdigest(),
                        },
                    },
                }
            }

            approvals = _remediation_approvals(contract, authority, root=root)

            self.assertEqual(approvals["ocr_content_001"]["decision"], "EDIT")

            contract["content_objects"][0]["ocr_text_candidate"] = "4日完全不同"
            with self.assertRaises(RuntimeError):
                _remediation_approvals(contract, authority, root=root)


class Phase3AdditiveApprovalRebindTests(unittest.TestCase):
    def _fixture(self, root: Path, *, candidate: str = "Dầu lạc") -> None:
        remediation = {
            "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
            "translation_carry_forward": _carry(),
        }
        remediation["remediation_sha256"] = remediation_hash(remediation)
        (root / "phase2_residual_remediation.json").write_text(
            json.dumps(remediation), encoding="utf-8"
        )
        queue = {
            "phase2_handoff_ref": {
                "path": "phase2_handoff.json",
                "sha256": "d" * 64,
            },
            "content_objects": [
                {
                    "content_id": "ocr_content_001",
                    "zh_approved": "花生油",
                    "vi_text_candidate": candidate,
                    "review_input_sha256": "e" * 64,
                }
            ],
        }
        (root / "phase3_review_queue.json").write_text(
            json.dumps(queue), encoding="utf-8"
        )

    def test_stages_empty_decisions_against_the_new_phase2_handoff(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            remediation = {
                "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
                "translation_carry_forward": _carry(),
            }
            remediation["remediation_sha256"] = remediation_hash(remediation)
            (root / "phase2_residual_remediation.json").write_text(
                json.dumps(remediation), encoding="utf-8"
            )
            (root / "phase2_handoff.json").write_text(
                json.dumps({"status": "READY_FOR_PHASE3"}), encoding="utf-8"
            )

            audit = stage_unapproved_placeholders(root)
            approvals = json.loads(
                (root / "phase3_approvals.json").read_text(encoding="utf-8")
            )

            self.assertEqual(audit["counts"]["placeholders"], 1)
            self.assertEqual(approvals["approvals"][0]["decision"], "")
            self.assertIsNone(approvals["approvals"][0]["reviewer"])

    def test_rebinds_only_exact_unchanged_translation_content(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            audit = rebind_approvals(root)
            approvals = json.loads(
                (root / "phase3_approvals.json").read_text(encoding="utf-8")
            )
            self.assertEqual(audit["counts"]["rebound"], 1)
            self.assertEqual(
                approvals["approvals"][0]["vi_text_approved"],
                "Dầu đậu phộng",
            )
            self.assertEqual(
                approvals["approvals"][0]["review_input_sha256"],
                "e" * 64,
            )

    def test_rebinds_exact_operator_approved_additive_translation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            remediation_path = root / "phase2_residual_remediation.json"
            remediation = json.loads(remediation_path.read_text(encoding="utf-8"))
            remediation.pop("remediation_sha256")
            remediation["approved_occurrences"] = [
                {
                    "remediation_id": "p2r_new",
                    "ocr_text_approved": "new zh",
                    "vi_text_approved": "new vi",
                    "localization": {"mode": "translation_review_required"},
                    "operator_review": {
                        "decision": "APPROVE",
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-29T00:00:00+00:00",
                    },
                },
                {
                    "remediation_id": "p2r_unit",
                    "ocr_text_approved": "441 kcal source",
                    "vi_text_approved": "441 kcal",
                    "localization": {"mode": "deterministic"},
                    "operator_review": {
                        "decision": "APPROVE",
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-29T00:00:00+00:00",
                    },
                },
            ]
            remediation["remediation_sha256"] = remediation_hash(remediation)
            remediation_path.write_text(json.dumps(remediation), encoding="utf-8")
            queue_path = root / "phase3_review_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["content_objects"].append(
                {
                    "content_id": "ocr_content_002",
                    "zh_approved": "new zh",
                    "vi_text_candidate": "new vi",
                    "review_input_sha256": "f" * 64,
                }
            )
            queue_path.write_text(json.dumps(queue), encoding="utf-8")

            audit = rebind_approvals(root)
            approvals = json.loads(
                (root / "phase3_approvals.json").read_text(encoding="utf-8")
            )

            self.assertEqual(audit["counts"]["carry_forward"], 1)
            self.assertEqual(audit["counts"]["remediation_approved"], 1)
            additive = next(
                row
                for row in approvals["approvals"]
                if row["content_id"] == "ocr_content_002"
            )
            self.assertEqual(additive["decision"], "APPROVE")
            self.assertEqual(additive["vi_text_approved"], "new vi")
            self.assertEqual(additive["review_input_sha256"], "f" * 64)

    def test_rebinds_additive_candidate_drift_as_operator_approved_edit(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            remediation_path = root / "phase2_residual_remediation.json"
            remediation = json.loads(remediation_path.read_text(encoding="utf-8"))
            remediation.pop("remediation_sha256")
            remediation["approved_occurrences"] = [
                {
                    "remediation_id": "p2r_new",
                    "ocr_text_approved": "new zh",
                    "vi_text_approved": "operator approved vi",
                    "localization": {"mode": "translation_review_required"},
                    "operator_review": {
                        "decision": "APPROVE",
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-29T00:00:00+00:00",
                    },
                }
            ]
            remediation["remediation_sha256"] = remediation_hash(remediation)
            remediation_path.write_text(json.dumps(remediation), encoding="utf-8")
            queue_path = root / "phase3_review_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["content_objects"].append(
                {
                    "content_id": "ocr_content_002",
                    "zh_approved": "new zh",
                    "vi_text_candidate": "different model candidate",
                    "review_input_sha256": "f" * 64,
                }
            )
            queue_path.write_text(json.dumps(queue), encoding="utf-8")

            rebind_approvals(root)
            approvals = json.loads(
                (root / "phase3_approvals.json").read_text(encoding="utf-8")
            )

            additive = next(
                row
                for row in approvals["approvals"]
                if row["content_id"] == "ocr_content_002"
            )
            self.assertEqual(additive["decision"], "EDIT")
            self.assertEqual(additive["vi_text_approved"], "operator approved vi")
            self.assertEqual(additive["review_input_sha256"], "f" * 64)

    def test_rebind_groups_duplicate_additive_occurrences_by_content(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            remediation_path = root / "phase2_residual_remediation.json"
            remediation = json.loads(remediation_path.read_text(encoding="utf-8"))
            remediation.pop("remediation_sha256")
            remediation["approved_occurrences"] = [
                {
                    "remediation_id": f"p2r_new_{index}",
                    "ocr_text_approved": "same zh",
                    "vi_text_approved": "same vi",
                    "localization": {"mode": "translation_review_required"},
                    "operator_review": {
                        "decision": "APPROVE",
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-29T00:00:00+00:00",
                    },
                }
                for index in range(2)
            ]
            remediation["remediation_sha256"] = remediation_hash(remediation)
            remediation_path.write_text(json.dumps(remediation), encoding="utf-8")
            queue_path = root / "phase3_review_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["content_objects"].append(
                {
                    "content_id": "ocr_content_002",
                    "zh_approved": "same zh",
                    "vi_text_candidate": "same vi",
                    "review_input_sha256": "f" * 64,
                }
            )
            queue_path.write_text(json.dumps(queue), encoding="utf-8")

            audit = rebind_approvals(root)

            self.assertEqual(audit["counts"]["remediation_approved"], 2)
            self.assertEqual(audit["counts"]["remediation_content_groups"], 1)
            self.assertEqual(audit["counts"]["reused_existing_content_groups"], 0)

    def test_rebind_reuses_existing_approved_content_for_new_geometry(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            remediation_path = root / "phase2_residual_remediation.json"
            remediation = json.loads(remediation_path.read_text(encoding="utf-8"))
            remediation.pop("remediation_sha256")
            carry_row = remediation["translation_carry_forward"]["rows"][0]
            remediation["approved_occurrences"] = [
                {
                    "remediation_id": "p2r_reuse",
                    "ocr_text_approved": carry_row["zh_approved"],
                    "vi_text_approved": carry_row["vi_text_approved"],
                    "localization": {"mode": "translation_review_required"},
                    "operator_review": {
                        "decision": "APPROVE",
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-29T00:00:00+00:00",
                    },
                }
            ]
            remediation["remediation_sha256"] = remediation_hash(remediation)
            remediation_path.write_text(json.dumps(remediation), encoding="utf-8")

            audit = rebind_approvals(root)

            self.assertEqual(audit["counts"]["remediation_approved"], 1)
            self.assertEqual(audit["counts"]["remediation_content_groups"], 1)
            self.assertEqual(audit["counts"]["reused_existing_content_groups"], 1)

    def test_rebind_disambiguates_duplicate_existing_text_by_geometry(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            remediation_path = root / "phase2_residual_remediation.json"
            remediation = json.loads(remediation_path.read_text(encoding="utf-8"))
            remediation.pop("remediation_sha256")
            duplicate_carry = dict(
                remediation["translation_carry_forward"]["rows"][0]
            )
            duplicate_carry["content_id"] = "ocr_content_002"
            remediation["translation_carry_forward"]["rows"].append(duplicate_carry)
            carry_row = remediation["translation_carry_forward"]["rows"][0]
            remediation["approved_occurrences"] = [
                {
                    "remediation_id": "p2r_reuse",
                    "occurrence": {"text_id": "p2r_reuse"},
                    "ocr_text_approved": carry_row["zh_approved"],
                    "vi_text_approved": carry_row["vi_text_approved"],
                    "localization": {"mode": "translation_review_required"},
                    "operator_review": {
                        "decision": "APPROVE",
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-29T00:00:00+00:00",
                    },
                }
            ]
            remediation["remediation_sha256"] = remediation_hash(remediation)
            remediation_path.write_text(json.dumps(remediation), encoding="utf-8")
            queue_path = root / "phase3_review_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["content_objects"][0]["geometry_refs"] = ["p2r_reuse"]
            duplicate_queue = dict(queue["content_objects"][0])
            duplicate_queue["content_id"] = "ocr_content_002"
            duplicate_queue["geometry_refs"] = ["sub_02"]
            queue["content_objects"].append(duplicate_queue)
            queue_path.write_text(json.dumps(queue), encoding="utf-8")

            audit = rebind_approvals(root)

            self.assertEqual(audit["counts"]["reused_existing_content_groups"], 1)
            self.assertEqual(audit["counts"]["rebound"], 2)

    def test_rebind_reuses_one_translation_across_two_existing_geometry_groups(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            remediation_path = root / "phase2_residual_remediation.json"
            remediation = json.loads(remediation_path.read_text(encoding="utf-8"))
            remediation.pop("remediation_sha256")
            duplicate_carry = dict(
                remediation["translation_carry_forward"]["rows"][0]
            )
            duplicate_carry["content_id"] = "ocr_content_002"
            remediation["translation_carry_forward"]["rows"].append(duplicate_carry)
            carry_row = remediation["translation_carry_forward"]["rows"][0]
            remediation["approved_occurrences"] = [
                {
                    "remediation_id": f"p2r_reuse_{index}",
                    "occurrence": {"text_id": f"p2r_reuse_{index}"},
                    "ocr_text_approved": carry_row["zh_approved"],
                    "vi_text_approved": carry_row["vi_text_approved"],
                    "localization": {"mode": "translation_review_required"},
                    "operator_review": {
                        "decision": "APPROVE",
                        "reviewer": "operator",
                        "reviewed_at": "2026-07-29T00:00:00+00:00",
                    },
                }
                for index in range(2)
            ]
            remediation["remediation_sha256"] = remediation_hash(remediation)
            remediation_path.write_text(json.dumps(remediation), encoding="utf-8")
            queue_path = root / "phase3_review_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["content_objects"][0]["geometry_refs"] = ["p2r_reuse_0"]
            duplicate_queue = dict(queue["content_objects"][0])
            duplicate_queue["content_id"] = "ocr_content_002"
            duplicate_queue["geometry_refs"] = ["p2r_reuse_1"]
            queue["content_objects"].append(duplicate_queue)
            queue_path.write_text(json.dumps(queue), encoding="utf-8")

            audit = rebind_approvals(root)

            self.assertEqual(audit["counts"]["reused_existing_content_groups"], 1)
            self.assertEqual(audit["counts"]["rebound"], 2)

    def test_rebind_fails_closed_on_unapproved_additive_translation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            queue_path = root / "phase3_review_queue.json"
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            queue["content_objects"].append(
                {
                    "content_id": "ocr_content_002",
                    "zh_approved": "unexpected zh",
                    "vi_text_candidate": "unexpected vi",
                    "review_input_sha256": "f" * 64,
                }
            )
            queue_path.write_text(json.dumps(queue), encoding="utf-8")

            with self.assertRaises(Phase3ApprovalRebindError):
                rebind_approvals(root)

    def test_rebind_fails_closed_on_candidate_drift(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root, candidate="Dầu ăn")
            with self.assertRaises(Phase3ApprovalRebindError):
                rebind_approvals(root)


if __name__ == "__main__":
    unittest.main()
