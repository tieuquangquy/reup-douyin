from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.build_phase3_batch_review_index import (
    Phase3BatchReviewIndexError,
    approval_token,
    build_batch_review_index,
    render_batch_markdown,
)
from scripts.build_phase3_review_proposal import build_review_proposal


def _write_case(run: Path, *, decided: bool = False) -> Path:
    case = run / "local_case"
    case.mkdir()
    queue = {
        "phase2_handoff_ref": {
            "path": "phase2_handoff.json",
            "sha256": "a" * 64,
        },
        "review_summary": {"failed": 0},
        "content_objects": [
            {
                "content_id": "ocr_content_001",
                "zh_approved": "蛋白质",
                "roles": ["mid_label"],
                "vi_text_candidate": "Protein",
                "review_input_sha256": "b" * 64,
                "quality_flags": [],
                "unit_tokens": [],
            }
        ],
    }
    (case / "phase3_review_queue.json").write_text(
        json.dumps(queue), encoding="utf-8"
    )
    proposal = build_review_proposal(
        root_dir=case,
        edits={
            "ocr_content_001": {
                "vi_text": "Đạm",
                "reasons": ["vietnamese_ui_label"],
            }
        },
        proposal_author="test",
        created_at="2026-07-29T00:00:00+00:00",
    )
    (case / "phase3_review_proposal.json").write_text(
        json.dumps(proposal), encoding="utf-8"
    )
    (case / "phase3_approvals.json").write_text(
        json.dumps(
            {
                "phase2_handoff_ref": queue["phase2_handoff_ref"],
                "approvals": [
                    {
                        "content_id": "ocr_content_001",
                        "decision": "APPROVE" if decided else "",
                        "reviewer": "operator" if decided else None,
                        "reviewed_at": "2026-07-29T00:00:00+00:00"
                        if decided
                        else None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return case


def test_builds_hash_bound_batch_index_without_writing_approval() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        case = _write_case(run)
        (run / "batch_regression_state.json").write_text(
            json.dumps(
                {
                    "run_sha256": "c" * 64,
                    "cases": [
                        {
                            "case_id": "local_case",
                            "status": "WAITING_TRANSLATION_OPERATOR_REVIEW",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        payload = build_batch_review_index(run_root=run)

        assert payload["status"] == "TRANSLATION_OPERATOR_REVIEW_REQUIRED"
        assert payload["counts"] == {
            "cases": 1,
            "review_objects": 1,
            "recommended_edits": 1,
            "recommended_approvals": 0,
            "translation_failures": 0,
            "candidate_quality_flags": 0,
        }
        assert payload["operator_approval_written"] is False
        assert approval_token(payload).startswith(
            "TRANSLATION_PROPOSALS_APPROVED_V22_1_"
        )
        assert approval_token(payload) in render_batch_markdown(payload)
        approvals = json.loads(
            (case / "phase3_approvals.json").read_text(encoding="utf-8")
        )
        assert approvals["approvals"][0]["decision"] == ""


def test_rejects_case_with_existing_operator_decision() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        _write_case(run, decided=True)
        (run / "batch_regression_state.json").write_text(
            json.dumps(
                {
                    "cases": [
                        {
                            "case_id": "local_case",
                            "status": "WAITING_TRANSLATION_OPERATOR_REVIEW",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(Phase3BatchReviewIndexError):
            build_batch_review_index(run_root=run)
