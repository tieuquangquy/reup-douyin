from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np
import pytest

from scripts.apply_phase2_batch_review_proposal import (
    Phase2BatchProposalApprovalError,
    apply_batch_proposal,
    expected_approval_token,
)
from scripts.build_phase2_batch_review_proposal import build_batch_review_proposal


def _fixture(root: Path) -> tuple[Path, Path, dict]:
    state_path = root / "batch_regression_state.json"
    state_path.write_text(json.dumps({"status": "RUNNING"}), encoding="utf-8")
    case_root = root / "local_case"
    (case_root / "crops").mkdir(parents=True)
    cv2.imwrite(
        str(case_root / "crops" / "sub_01.jpg"),
        np.full((40, 120, 3), 180, dtype=np.uint8),
    )
    phase1_ref = {"path": "master_timeline.json", "sha256": "a" * 64}
    timeline = {
        "phase1_ref": phase1_ref,
        "content_objects": [
            {"content_id": "ocr_content_001", "review_input_sha256": "b" * 64}
        ],
    }
    (case_root / "phase2_ocr_timeline.json").write_text(
        json.dumps(timeline), encoding="utf-8"
    )
    (case_root / "phase2_approvals.json").write_text(
        json.dumps({"phase1_ref": phase1_ref, "approvals": []}), encoding="utf-8"
    )
    queue = {
        "phase1_ref": phase1_ref,
        "content_objects": [
            {
                "content_id": "ocr_content_001",
                "geometry_refs": ["sub_01"],
                "ocr_text_candidate": "wr0ng",
                "review_input_sha256": "b" * 64,
                "review_assets": [
                    {"text_id": "sub_01", "crop_path": "crops/sub_01.jpg"}
                ],
            }
        ],
    }
    queue_path = case_root / "phase2_review_queue.json"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    manifest = {
        "schema_version": "phase2_batch_review_recommendations_v1",
        "batch_state_ref": {
            "path": state_path.name,
            "sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
        },
        "cases": {
            "local_case": {
                "review_queue_sha256": hashlib.sha256(
                    queue_path.read_bytes()
                ).hexdigest(),
                "recommendations": {
                    "ocr_content_001": {"decision": "EDIT", "text": "wrong"}
                },
            }
        },
    }
    manifest_path = root / "recommendations.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    batch = build_batch_review_proposal(
        run_root=root,
        recommendations_path=manifest_path,
        generated_at="2026-07-29T00:00:00+00:00",
    )
    batch_path = root / "phase2_batch_review_proposal.json"
    batch_path.write_text(json.dumps(batch), encoding="utf-8")
    return case_root, batch_path, batch


def test_applies_exact_batch_token_and_records_root_audit() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        case_root, batch_path, batch = _fixture(root)
        token = expected_approval_token(
            batch["batch_proposal_sha256"], approval_label="V22_1"
        )

        result = apply_batch_proposal(
            run_root=root,
            batch_proposal_path=batch_path,
            approval_token=token,
            approval_label="V22_1",
            reviewer="operator",
            reviewed_at="2026-07-29T00:01:00+00:00",
        )

        assert result["status"] == "OCR_DECISIONS_RECORDED_PHASE2_RERUN_REQUIRED"
        approvals = json.loads(
            (case_root / "phase2_approvals.json").read_text(encoding="utf-8")
        )
        assert approvals["approvals"][0]["ocr_text_approved"] == "wrong"
        assert (root / "phase2_batch_proposal_approval.json").is_file()


def test_wrong_batch_token_is_fail_closed_before_writes() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        case_root, batch_path, _batch = _fixture(root)
        before = (case_root / "phase2_approvals.json").read_bytes()

        with pytest.raises(Phase2BatchProposalApprovalError):
            apply_batch_proposal(
                run_root=root,
                batch_proposal_path=batch_path,
                approval_token="OCR_PROPOSALS_APPROVED_V22_1_BAD",
                approval_label="V22_1",
                reviewer="operator",
                reviewed_at="2026-07-29T00:01:00+00:00",
            )

        assert (case_root / "phase2_approvals.json").read_bytes() == before
        assert not (root / "phase2_batch_proposal_approval.json").exists()
