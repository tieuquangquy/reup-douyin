from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.finalize_phase2_batch_approval import finalize_phase2_batch


def _sha_json(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_finalizes_only_fully_reviewed_phase3_ready_case() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        case = root / "local_case"
        case.mkdir()
        batch_path = root / "phase2_batch_review_proposal.json"
        _write(batch_path, {"batch": True})
        operator_audit = {
            "status": "DECISIONS_RECORDED_PHASE2_RERUN_REQUIRED",
            "counts": {"objects": 1},
        }
        operator_audit["audit_sha256"] = _sha_json(operator_audit)
        operator_audit_path = case / "phase2_operator_review_audit.json"
        _write(operator_audit_path, operator_audit)
        approvals = {
            "approvals": [
                {
                    "content_id": "ocr_content_001",
                    "decision": "EDIT",
                    "reviewer": "operator",
                    "reviewed_at": "2026-07-29T00:00:00+00:00",
                }
            ]
        }
        _write(case / "phase2_approvals.json", approvals)
        timeline = {
            "review_summary": {"status": "OCR_APPROVED", "unresolved": 0},
            "duplicate_transition_summary": {"merged_content_objects": 0},
            "content_objects": [{"content_id": "ocr_content_001"}],
        }
        timeline_path = case / "phase2_ocr_timeline.json"
        _write(timeline_path, timeline)
        _write(
            case / "phase2_meta.json",
            {
                "review_required": 0,
                "ready_for_phase3": True,
                "handoff_status": "READY_FOR_PHASE3",
            },
        )
        _write(
            case / "phase2_handoff.json",
            {
                "status": "READY_FOR_PHASE3",
                "blocked_reasons": [],
                "phase2_ref": {
                    "sha256": hashlib.sha256(timeline_path.read_bytes()).hexdigest()
                },
                "counts": {
                    "translate_items": 1,
                    "deterministic_items": 0,
                    "cover_only_items": 0,
                    "geometry_refs": 1,
                },
            },
        )
        approval = {
            "status": "OCR_DECISIONS_RECORDED_PHASE2_RERUN_REQUIRED",
            "batch_proposal_ref": {
                "path": batch_path.name,
                "file_sha256": hashlib.sha256(batch_path.read_bytes()).hexdigest(),
            },
            "cases": [
                {
                    "case_id": "local_case",
                    "counts": {"objects": 1},
                    "operator_review_audit_ref": {
                        "path": "local_case/phase2_operator_review_audit.json",
                        "sha256": hashlib.sha256(
                            operator_audit_path.read_bytes()
                        ).hexdigest(),
                        "audit_sha256": operator_audit["audit_sha256"],
                    },
                }
            ],
        }
        approval["approval_sha256"] = _sha_json(approval)
        _write(root / "phase2_batch_proposal_approval.json", approval)

        result = finalize_phase2_batch(
            run_root=root, generated_at="2026-07-29T01:00:00+00:00"
        )

        assert result["status"] == "READY_FOR_PHASE3"
        assert result["counts"]["approved_decisions"] == 1
        assert result["counts"]["translate_items"] == 1
        assert (root / "phase2_batch_handoff_ready.json").is_file()
