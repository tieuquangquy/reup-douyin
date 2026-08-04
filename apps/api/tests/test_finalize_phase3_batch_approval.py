from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.finalize_phase3_batch_approval import (
    Phase3BatchFinalizationError,
    finalize_phase3_batch,
)


def _hash_json(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _fixture(run: Path, *, omit_handoff: bool = False) -> None:
    case = run / "local_case"
    case.mkdir()
    batch_path = run / "phase3_batch_review_index.json"
    batch_path.write_text("{}", encoding="utf-8")
    audit = {
        "status": "TRANSLATION_DECISIONS_RECORDED_RERUN_REQUIRED",
        "counts": {"objects": 1, "edited": 1, "approved_unchanged": 0},
    }
    audit["audit_sha256"] = _hash_json(audit)
    audit_path = case / "phase3_operator_approval_audit.json"
    _write_json(audit_path, audit)
    _write_json(
        case / "phase3_approvals.json",
        {
            "approvals": [
                {
                    "content_id": "ocr_content_001",
                    "decision": "EDIT",
                    "reviewer": "operator",
                    "reviewed_at": "2026-07-29T00:00:00+00:00",
                }
            ]
        },
    )
    summary = {
        "status": "TRANSLATION_APPROVED",
        "content_objects": 2,
        "approved": 1,
        "deterministic": 1,
        "failed": 0,
        "unresolved": 0,
    }
    timeline_path = case / "phase3_translation_timeline.json"
    _write_json(timeline_path, {"review_summary": summary})
    _write_json(case / "phase3_meta.json", {"review_summary": summary})
    render_path = case / "phase3_render_handoff.json"
    if not omit_handoff:
        _write_json(
            render_path,
            {
                "status": "READY_FOR_RENDER",
                "blocked_reasons": [],
                "counts": {"content_objects": 2, "geometry_refs": 2},
            },
        )
    closeout = {
        "status": "PHASE3_CLOSED",
        "phase3_timeline_ref": {
            "sha256": hashlib.sha256(timeline_path.read_bytes()).hexdigest()
        },
        "phase3_render_handoff_ref": {
            "sha256": hashlib.sha256(render_path.read_bytes()).hexdigest()
            if render_path.is_file()
            else "x" * 64
        },
    }
    _write_json(case / "phase3_closeout.json", closeout)
    approval = {
        "status": "TRANSLATION_DECISIONS_RECORDED_PHASE3_RERUN_REQUIRED",
        "batch_review_ref": {
            "path": batch_path.name,
            "file_sha256": hashlib.sha256(batch_path.read_bytes()).hexdigest(),
        },
        "counts": {"cases": 1, "review_objects": 1},
        "cases": [
            {
                "case_id": "local_case",
                "operator_review_audit_ref": {
                    "path": "local_case/phase3_operator_approval_audit.json",
                    "sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
                    "audit_sha256": audit["audit_sha256"],
                },
                "counts": {"objects": 1},
            }
        ],
    }
    approval["approval_sha256"] = _hash_json(approval)
    _write_json(run / "phase3_batch_proposal_approval.json", approval)


def test_finalizes_only_complete_phase3_rerun() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        _fixture(run)

        result = finalize_phase3_batch(
            run_root=run, generated_at="2026-07-29T00:00:00+00:00"
        )

        assert result["status"] == "READY_FOR_PHASE4_PREFLIGHT"
        assert result["counts"]["approved_decisions"] == 1
        assert result["counts"]["deterministic"] == 1
        assert (run / "phase3_batch_handoff_ready.json").is_file()


def test_rejects_incomplete_phase3_rerun() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        _fixture(run, omit_handoff=True)

        with pytest.raises(Phase3BatchFinalizationError):
            finalize_phase3_batch(run_root=run)
