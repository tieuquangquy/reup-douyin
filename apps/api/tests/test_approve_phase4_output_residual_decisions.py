from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.approve_phase4_output_residual_decisions import (
    OutputResidualDecisionApprovalError,
    _sha256_json,
    approve,
)


def _proposal(root: Path) -> Path:
    dependency = root / "review.json"
    dependency.write_text("{}", encoding="utf-8")
    payload = {
        "status": "OUTPUT_RESIDUAL_DECISIONS_READY_FOR_OPERATOR_REVIEW",
        "operator_approval_written": False,
        "authority_mutation_written": False,
        "operator_approval_token": "APPROVED_TOKEN",
        "authority_refs": {
            "review": {
                "path": dependency.name,
                "sha256": hashlib.sha256(dependency.read_bytes()).hexdigest(),
            }
        },
        "counts": {"decisions": 2},
    }
    payload["proposal_sha256"] = _sha256_json(payload)
    path = root / "proposal.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_records_hash_bound_decision_approval_without_materializing() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = _proposal(root)
        approval = approve(
            run_root=root,
            proposal_path=path,
            approval_token="APPROVED_TOKEN",
            operator_id="operator",
            approved_at="2026-07-30T00:00:00+00:00",
        )

    assert approval["status"] == "PHASE4_OUTPUT_RESIDUAL_DECISIONS_APPROVED"
    assert approval["materialization_status"] == "PENDING_SOURCE_BOUNDARY_VALIDATION"
    assert approval["authority_mutation_written"] is False


def test_rejects_dependency_hash_drift() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = _proposal(root)
        (root / "review.json").write_text("changed", encoding="utf-8")
        with pytest.raises(OutputResidualDecisionApprovalError):
            approve(
                run_root=root,
                proposal_path=path,
                approval_token="APPROVED_TOKEN",
                operator_id="operator",
                approved_at="now",
            )
