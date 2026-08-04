from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.apply_phase3_batch_review_proposal import (
    Phase3BatchProposalApprovalError,
    apply_batch_review_proposal,
)
from scripts.build_phase3_batch_review_index import approval_token


def _hash_json(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_fixture(run: Path) -> tuple[Path, str]:
    case = run / "local_case"
    case.mkdir()
    queue = {
        "phase2_handoff_ref": {"path": "phase2_handoff.json", "sha256": "a" * 64},
        "content_objects": [
            {
                "content_id": "ocr_content_001",
                "vi_text_candidate": "Protein",
                "review_input_sha256": "b" * 64,
            }
        ],
    }
    queue_path = case / "phase3_review_queue.json"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    proposal = {
        "schema_version": "phase3_translation_review_proposal_v1",
        "status": "PROPOSAL_READY_FOR_OPERATOR_REVIEW",
        "operator_approval_written": False,
        "phase2_handoff_ref": queue["phase2_handoff_ref"],
        "phase3_review_queue_ref": {
            "path": queue_path.name,
            "sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
        },
        "proposals": [
            {
                "content_id": "ocr_content_001",
                "recommendation": "EDIT",
                "review_input_sha256": "b" * 64,
                "vi_text_candidate": "Protein",
                "vi_text_proposed": "Đạm",
            }
        ],
    }
    proposal["proposal_sha256"] = _hash_json(proposal)
    proposal_path = case / "phase3_review_proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    approvals_path = case / "phase3_approvals.json"
    approvals_path.write_text(
        json.dumps(
            {
                "phase2_handoff_ref": queue["phase2_handoff_ref"],
                "approvals": [
                    {
                        "content_id": "ocr_content_001",
                        "decision": "",
                        "review_input_sha256": "b" * 64,
                        "vi_text_approved": "Protein",
                        "reviewer": None,
                        "reviewed_at": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    state_path = run / "batch_regression_state.json"
    state_path.write_text(json.dumps({"cases": []}), encoding="utf-8")
    batch = {
        "schema_version": "phase3_batch_review_index_v1",
        "status": "TRANSLATION_OPERATOR_REVIEW_REQUIRED",
        "operator_approval_written": False,
        "batch_state_ref": {
            "path": state_path.name,
            "sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
        },
        "counts": {
            "cases": 1,
            "review_objects": 1,
            "recommended_edits": 1,
            "recommended_approvals": 0,
        },
        "cases": [
            {
                "case_id": "local_case",
                "phase3_review_queue_ref": {
                    "path": "local_case/phase3_review_queue.json",
                    "sha256": hashlib.sha256(queue_path.read_bytes()).hexdigest(),
                },
                "proposal_path": "local_case/phase3_review_proposal.json",
                "proposal_file_sha256": hashlib.sha256(
                    proposal_path.read_bytes()
                ).hexdigest(),
                "proposal_sha256": proposal["proposal_sha256"],
            }
        ],
    }
    batch["batch_review_sha256"] = _hash_json(batch)
    batch_path = run / "phase3_batch_review_index.json"
    batch_path.write_text(json.dumps(batch), encoding="utf-8")
    return batch_path, approval_token(batch)


def test_applies_exact_batch_and_writes_hash_bound_audit() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        batch_path, token = _write_fixture(run)

        result = apply_batch_review_proposal(
            run_root=run,
            batch_index_path=batch_path,
            supplied_token=token,
            operator_id="operator",
            approved_at="2026-07-29T00:00:00+00:00",
        )

        assert result["status"] == (
            "TRANSLATION_DECISIONS_RECORDED_PHASE3_RERUN_REQUIRED"
        )
        approvals = json.loads(
            (run / "local_case" / "phase3_approvals.json").read_text(
                encoding="utf-8"
            )
        )
        assert approvals["approvals"][0]["decision"] == "EDIT"
        assert approvals["approvals"][0]["vi_text_approved"] == "Đạm"
        assert (run / "phase3_batch_proposal_approval.json").is_file()


def test_rejects_wrong_token_without_changing_approvals() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        batch_path, _ = _write_fixture(run)
        approvals_path = run / "local_case" / "phase3_approvals.json"
        before = approvals_path.read_bytes()

        with pytest.raises(Phase3BatchProposalApprovalError):
            apply_batch_review_proposal(
                run_root=run,
                batch_index_path=batch_path,
                supplied_token="TRANSLATION_PROPOSALS_APPROVED_V22_1_WRONG",
                operator_id="operator",
                approved_at="2026-07-29T00:00:00+00:00",
            )

        assert approvals_path.read_bytes() == before
