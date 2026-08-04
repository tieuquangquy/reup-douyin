from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.approve_phase4_output_residual_review import (
    OutputResidualReviewApprovalError,
    approve,
    _sha256_json,
)


def test_approval_is_review_only_and_hash_bound() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        review = {
            "status": "OUTPUT_RESIDUAL_REVIEW_REQUIRED",
            "operator_approval_written": False,
            "operator_review_token": "TOKEN",
            "counts": {"clusters": 1},
        }
        review["review_sha256"] = _sha256_json(review)
        review_path = root / "review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")
        payload = approve(
            run_root=root,
            review_path=review_path,
            review_token="TOKEN",
            operator_id="operator",
            approved_at="2026-07-30T00:00:00+00:00",
        )

    assert payload["status"] == "PHASE4_OUTPUT_RESIDUAL_REVIEW_APPROVED"
    assert payload["translation_approval_written"] is False
    assert payload["remediation_authority_written"] is False
    assert len(payload["approval_sha256"]) == 64


def test_rejects_wrong_review_token() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        review = {
            "status": "OUTPUT_RESIDUAL_REVIEW_REQUIRED",
            "operator_approval_written": False,
            "operator_review_token": "TOKEN",
        }
        review["review_sha256"] = _sha256_json(review)
        path = root / "review.json"
        path.write_text(json.dumps(review), encoding="utf-8")
        with pytest.raises(OutputResidualReviewApprovalError):
            approve(
                run_root=root,
                review_path=path,
                review_token="WRONG",
                operator_id="operator",
                approved_at="now",
            )

