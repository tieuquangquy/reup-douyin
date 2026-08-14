from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from scripts import run_phase3_only


def _write_handoff(root: Path) -> Path:
    path = root / "phase2_handoff.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "phase2_handoff_v1",
                "status": "READY_FOR_PHASE3",
                "translate_items": [],
                "deterministic_items": [],
            }
        ),
        encoding="utf-8",
    )
    return path


class RunPhase3OnlyTests(unittest.TestCase):
    def test_loads_locked_candidates_from_residual_remediation(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff = {
                "status": "READY_FOR_PHASE3",
                "translate_items": [
                    {
                        "content_id": "ocr_content_001",
                        "geometry_refs": ["sub_01"],
                        "roles": ["title"],
                        "zh_approved": "午餐",
                        "translation_input": "午餐",
                        "protected_values": [],
                        "unit_tokens": [],
                    },
                    {
                        "content_id": "ocr_content_002",
                        "geometry_refs": ["p2r_01"],
                        "roles": ["ui"],
                        "zh_approved": "鸡蛋",
                        "translation_input": "鸡蛋",
                        "protected_values": [],
                        "unit_tokens": [],
                    },
                ],
            }
            remediation = {
                "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
                "translation_carry_forward": {
                    "rows": [
                        {
                            "content_id": "ocr_content_001",
                            "zh_approved": "午餐",
                            "vi_text_candidate": "Bữa trưa",
                            "vi_text_approved": "Bữa trưa",
                        }
                    ]
                },
                "approved_occurrences": [
                    {
                        "ocr_text_approved": "午餐",
                        "vi_text_approved": "Bữa trưa",
                        "localization": {"mode": "translation_review_required"},
                    },
                    {
                        "ocr_text_approved": "鸡蛋",
                        "vi_text_approved": "Trứng gà",
                        "localization": {"mode": "translation_review_required"},
                    }
                ],
            }
            remediation["remediation_sha256"] = run_phase3_only._sha256_json(
                remediation
            )
            (root / "phase2_residual_remediation.json").write_text(
                json.dumps(remediation), encoding="utf-8"
            )

            fossils = run_phase3_only._load_remediation_review_fossils(
                root,
                handoff=handoff,
                phase2_handoff_sha256="a" * 64,
            )

            self.assertEqual(
                fossils["ocr_content_001"]["vi_text_candidate"], "Bữa trưa"
            )
            self.assertEqual(
                fossils["ocr_content_002"]["vi_text_candidate"], "Trứng gà"
            )
            self.assertEqual(
                len(fossils["ocr_content_002"]["review_input_sha256"]), 64
            )

    def test_reuses_operator_approved_geometry_override_translation_fossil(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff = {
                "status": "READY_FOR_PHASE3",
                "translate_items": [
                    {
                        "content_id": "ocr_content_split",
                        "geometry_refs": ["sub_09"],
                        "roles": ["hardsub"],
                        "zh_approved": "下入西红柿",
                        "translation_input": "下入西红柿",
                        "protected_values": [],
                        "unit_tokens": [],
                    }
                ],
            }
            remediation = {
                "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
                "translation_carry_forward": {
                    "rows": [
                        {
                            "content_id": "ocr_content_original",
                            "zh_approved": "下入西红柿",
                            "vi_text_candidate": "Cho cà chua vào",
                            "vi_text_approved": "Cho cà chua vào",
                        }
                    ]
                },
                "approved_occurrences": [],
                "approved_geometry_overrides": [
                    {
                        "ocr_text_approved": "下入西红柿",
                        "vi_text_approved": "Cho cà chua vào",
                        "localization": {
                            "mode": "translation_carry_forward_exact"
                        },
                        "operator_review": {"decision": "EDIT"},
                    }
                ],
            }
            remediation["remediation_sha256"] = run_phase3_only._sha256_json(
                remediation
            )
            (root / "phase2_residual_remediation.json").write_text(
                json.dumps(remediation), encoding="utf-8"
            )

            fossils = run_phase3_only._load_remediation_review_fossils(
                root,
                handoff=handoff,
                phase2_handoff_sha256="a" * 64,
            )

            self.assertEqual(
                fossils["ocr_content_split"]["vi_text_candidate"],
                "Cho cà chua vào",
            )

    def test_rebinds_shifted_content_id_through_exact_translation_fossil(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff = {
                "status": "READY_FOR_PHASE3",
                "translate_items": [
                    {
                        "content_id": "ocr_content_018",
                        "geometry_refs": ["sub_shifted"],
                        "roles": ["hardsub"],
                        "zh_approved": "target approved text",
                        "translation_input": "target approved text",
                        "protected_values": [],
                        "unit_tokens": [],
                    }
                ],
            }
            remediation = {
                "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
                "translation_carry_forward": {
                    "rows": [
                        {
                            "content_id": "ocr_content_018",
                            "zh_approved": "previous content at this projection id",
                            "vi_text_candidate": "Previous translation",
                            "vi_text_approved": "Previous translation",
                        },
                        {
                            "content_id": "ocr_content_011",
                            "zh_approved": "target approved text",
                            "vi_text_candidate": "Stable translation",
                            "vi_text_approved": "Stable translation",
                        },
                    ]
                },
                "approved_occurrences": [],
                "approved_geometry_overrides": [],
            }
            remediation["remediation_sha256"] = run_phase3_only._sha256_json(
                remediation
            )
            (root / "phase2_residual_remediation.json").write_text(
                json.dumps(remediation), encoding="utf-8"
            )

            fossils = run_phase3_only._load_remediation_review_fossils(
                root,
                handoff=handoff,
                phase2_handoff_sha256="a" * 64,
            )

            self.assertEqual(
                fossils["ocr_content_018"]["vi_text_candidate"],
                "Stable translation",
            )

    def test_uses_additive_fossil_when_new_object_reuses_old_projection_id(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff = {
                "status": "READY_FOR_PHASE3",
                "translate_items": [
                    {
                        "content_id": "ocr_content_084",
                        "geometry_refs": ["residual_01"],
                        "roles": ["ui"],
                        "zh_approved": "new residual text",
                        "translation_input": "new residual text",
                        "protected_values": [],
                        "unit_tokens": [],
                    }
                ],
            }
            remediation = {
                "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
                "translation_carry_forward": {
                    "rows": [
                        {
                            "content_id": "ocr_content_084",
                            "zh_approved": "old text at projection id",
                            "vi_text_candidate": "Old translation",
                            "vi_text_approved": "Old translation",
                        }
                    ]
                },
                "approved_occurrences": [
                    {
                        "ocr_text_approved": "new residual text",
                        "vi_text_approved": "New translation",
                        "localization": {"mode": "translation_review_required"},
                    }
                ],
                "approved_geometry_overrides": [],
            }
            remediation["remediation_sha256"] = run_phase3_only._sha256_json(
                remediation
            )
            (root / "phase2_residual_remediation.json").write_text(
                json.dumps(remediation), encoding="utf-8"
            )

            fossils = run_phase3_only._load_remediation_review_fossils(
                root,
                handoff=handoff,
                phase2_handoff_sha256="a" * 64,
            )

            self.assertEqual(
                fossils["ocr_content_084"]["vi_text_candidate"],
                "New translation",
            )

    def test_semantic_dialogue_authority_consumes_matching_additive_geometry(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff = {
                "status": "READY_FOR_PHASE3",
                "translate_items": [],
                "deterministic_items": [
                    {
                        "content_id": "ocr_content_dialogue",
                        "geometry_refs": ["p2r_dialogue"],
                        "zh_approved": "partial asr text",
                        "render_text": "Bản dịch lời thoại đã duyệt",
                        "semantic_hardsub": {
                            "classification": "DIALOGUE_HARDSUB",
                            "translation_ready": True,
                            "vi_text_authority": "Bản dịch lời thoại đã duyệt",
                            "translation_authority": {
                                "translation_status": "APPROVED"
                            },
                        },
                    }
                ],
            }
            remediation = {
                "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
                "translation_carry_forward": {"rows": []},
                "approved_occurrences": [
                    {
                        "occurrence": {"text_id": "p2r_dialogue"},
                        "ocr_text_approved": "full OCR sentence",
                        "vi_text_approved": "Visual suggestion",
                        "localization": {
                            "mode": "translation_review_required"
                        },
                    }
                ],
            }
            remediation["remediation_sha256"] = run_phase3_only._sha256_json(
                remediation
            )
            (root / "phase2_residual_remediation.json").write_text(
                json.dumps(remediation), encoding="utf-8"
            )

            fossils = run_phase3_only._load_remediation_review_fossils(
                root,
                handoff=handoff,
                phase2_handoff_sha256="a" * 64,
            )

            self.assertEqual(fossils, {})

    def test_lock_current_candidates_records_explicit_operator_approval(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = _write_handoff(root)
            handoff_hash = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
            (root / "phase3_translation_timeline.json").write_text(
                json.dumps(
                    {
                        "phase2_handoff_ref": {"sha256": handoff_hash},
                        "content_objects": [
                            {
                                "content_id": "ocr_content_001",
                                "vi_text_candidate": "Bản dịch đã khóa",
                                "review_input_sha256": "a" * 64,
                                "review_required": True,
                            },
                            {
                                "content_id": "ocr_content_002",
                                "vi_text_candidate": "510 kcal",
                                "review_input_sha256": None,
                                "review_required": False,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "phase3_approvals.json").write_text(
                json.dumps(
                    {
                        "phase2_handoff_ref": {"sha256": handoff_hash},
                        "approvals": [
                            {
                                "content_id": "ocr_content_001",
                                "decision": "",
                                "review_input_sha256": "a" * 64,
                                "vi_text_approved": "Bản dịch đã khóa",
                                "reviewer": None,
                                "reviewed_at": None,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            count = run_phase3_only.lock_current_candidates(
                root,
                reviewer="operator",
                reviewed_at="2026-07-27T02:00:00+07:00",
            )

            self.assertEqual(count, 1)
            payload = json.loads(
                (root / "phase3_approvals.json").read_text(encoding="utf-8")
            )
            row = payload["approvals"][0]
            self.assertEqual(row["decision"], "APPROVE")
            self.assertEqual(row["reviewer"], "operator")
            self.assertEqual(row["reviewed_at"], "2026-07-27T02:00:00+07:00")

    def test_lock_current_candidates_rejects_candidate_drift(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = _write_handoff(root)
            handoff_hash = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
            (root / "phase3_translation_timeline.json").write_text(
                json.dumps(
                    {
                        "phase2_handoff_ref": {"sha256": handoff_hash},
                        "content_objects": [
                            {
                                "content_id": "ocr_content_001",
                                "vi_text_candidate": "Bản mới",
                                "review_input_sha256": "a" * 64,
                                "review_required": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "phase3_approvals.json").write_text(
                json.dumps(
                    {
                        "phase2_handoff_ref": {"sha256": handoff_hash},
                        "approvals": [
                            {
                                "content_id": "ocr_content_001",
                                "decision": "",
                                "review_input_sha256": "a" * 64,
                                "vi_text_approved": "Bản cũ",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(run_phase3_only.Phase3RunnerError):
                run_phase3_only.lock_current_candidates(root, reviewer="operator")

    def test_main_requires_phase2_handoff_authority(self) -> None:
        with TemporaryDirectory() as tmp:
            result = run_phase3_only.main([tmp])
        self.assertEqual(result, 1)

    def test_run_uses_workspace_caption_ai_and_contract(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = _write_handoff(root)
            handoff_hash = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
            settings = MagicMock(model_name="caption-test", source="workspace_db")
            contract = {
                "phase2_handoff_ref": {
                    "path": "phase2_handoff.json",
                    "sha256": handoff_hash,
                },
                "stats": {"translate_items": 0, "deterministic_items": 0},
                "review_summary": {
                    "content_objects": 0,
                    "unresolved": 0,
                    "failed": 0,
                    "status": "TRANSLATION_APPROVED",
                },
                "content_objects": [],
            }
            session = MagicMock()
            session_factory = MagicMock(return_value=session)
            with (
                patch.object(run_phase3_only, "get_session_factory", return_value=session_factory),
                patch.object(
                    run_phase3_only,
                    "resolve_translator_settings",
                    return_value=settings,
                ) as resolve,
                patch.object(
                    run_phase3_only,
                    "translate_phase3_handoff",
                    return_value=contract,
                ) as translate,
                patch.object(
                    run_phase3_only,
                    "write_phase3_artifacts",
                    return_value={},
                ) as write,
            ):
                result = run_phase3_only.run(root)

            self.assertEqual(result, 0)
            resolve.assert_called_once_with(db=session, workspace_id=None)
            translate.assert_called_once()
            kwargs = translate.call_args.kwargs
            self.assertEqual(kwargs["settings"], settings)
            self.assertEqual(kwargs["phase2_handoff_path"], handoff_path)
            self.assertEqual(kwargs["review_fossils"], {})
            self.assertEqual(
                kwargs["memory_path"], root / "qa" / "phase3_translation_memory.json"
            )
            write.assert_called_once_with(root_dir=root, contract=contract)
            session.close.assert_called_once()
            meta = json.loads((root / "phase3_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["phase2_handoff_sha256"], handoff_hash)
            self.assertNotIn("base_url", meta)
            self.assertNotIn("api_key", meta)

    def test_stale_approval_authority_fails_closed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_handoff(root)
            (root / "phase3_approvals.json").write_text(
                json.dumps(
                    {
                        "phase2_handoff_ref": {"sha256": "0" * 64},
                        "approvals": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(run_phase3_only.Phase3RunnerError):
                run_phase3_only.run(root)

    def test_loads_hash_bound_candidate_fossil_for_approved_decision(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff_path = _write_handoff(root)
            handoff_hash = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
            proposal = {
                "phase2_handoff_ref": {"sha256": handoff_hash},
                "proposals": [
                    {
                        "content_id": "ocr_content_001",
                        "vi_text_candidate": "Yêu thích",
                        "candidate_quality_flags": [],
                        "review_input_sha256": "b" * 64,
                    }
                ],
            }
            proposal["proposal_sha256"] = run_phase3_only._sha256_json(proposal)
            proposal_path = root / "phase3_review_proposal.json"
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
            audit = {
                "proposal_ref": {
                    "path": proposal_path.name,
                    "sha256": hashlib.sha256(proposal_path.read_bytes()).hexdigest(),
                    "proposal_sha256": proposal["proposal_sha256"],
                }
            }
            audit["audit_sha256"] = run_phase3_only._sha256_json(audit)
            (root / "phase3_operator_approval_audit.json").write_text(
                json.dumps(audit), encoding="utf-8"
            )
            approvals = {
                "ocr_content_001": {
                    "decision": "EDIT",
                    "review_input_sha256": "b" * 64,
                    "vi_text_approved": "Đã lưu",
                }
            }

            fossils = run_phase3_only._load_approved_review_fossils(
                root,
                phase2_handoff_sha256=handoff_hash,
                approvals=approvals,
            )

        self.assertEqual(
            fossils["ocr_content_001"]["vi_text_candidate"], "Yêu thích"
        )
        self.assertEqual(
            fossils["ocr_content_001"]["review_input_sha256"], "b" * 64
        )


if __name__ == "__main__":
    unittest.main()
