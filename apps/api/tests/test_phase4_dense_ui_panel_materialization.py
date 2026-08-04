from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.approve_phase4_dense_ui_panel_proposal import (
    DenseUiPanelApprovalError,
    approve,
)
from scripts.materialize_phase4_dense_ui_panel import materialize
from src.media_pipeline.video_renderer.visual_remediation import _sha256_json


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    run = tmp_path / "run"
    case = run / "case"
    case.mkdir(parents=True)
    contract = {
        "status": "READY_FOR_PHASE4",
        "video": {"fps": 30.0, "frame_count": 100},
        "render_tracks": [
            {
                "text_id": "canonical",
                "content_id": "content",
                "start_frame": 10,
                "end_frame": 20,
                "text_vi": "100 kcal",
                "geometry": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1},
                "render_policy": {
                    "damage_budget": {"max_frame_change_fraction": 0.55}
                },
            }
        ],
    }
    contract_path = case / "phase4_render_input.json"
    _write(contract_path, contract)
    parent = {
        "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
        "operator_id": "previous",
        "authority_refs": {
            "phase4_input": {"path": contract_path.name, "sha256": _sha(contract_path)}
        },
        "operations": [],
    }
    parent["materialization_sha256"] = _sha256_json(parent)
    parent_path = case / "phase4_visual_remediation_parent.json"
    _write(parent_path, parent)
    pointer = {
        "status": "ACTIVE",
        "active_ref": {
            "path": parent_path.name,
            "sha256": _sha(parent_path),
            "materialization_sha256": parent["materialization_sha256"],
        },
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    _write(case / "phase4_visual_remediation_active.json", pointer)
    token = "PHASE4_DENSE_UI_PANEL_PROPOSAL_APPROVED_TEST"
    proposal = {
        "status": "PROPOSAL_READY_FOR_OPERATOR_REVIEW",
        "operator_approval_written": False,
        "operator_approval_token": token,
        "authority_refs": {
            "phase4_input": {"path": contract_path.name, "sha256": _sha(contract_path)},
            "visual_remediation": pointer["active_ref"],
        },
        "decision": {
            "action": "DENSE_UI_PANEL_FALLBACK",
            "canonical_text_id": "canonical",
            "frame_span": [10, 20],
            "panel_roi": {"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.4},
            "cover_strategy": "OPAQUE_SOURCE_AWARE_PHONE_UI_PLATE",
            "layout_strategy": "DEDUPLICATED_PRIORITY_GRID",
            "deduplication_key": "content_id_then_normalized_vi_text",
            "max_rendered_lines": 12,
            "existing_max_frame_change_fraction": 0.55,
        },
    }
    proposal["proposal_sha256"] = _sha256_json(proposal)
    proposal_path = run / "proposal.json"
    _write(proposal_path, proposal)
    return run, case, proposal_path, token


def test_approval_rejects_wrong_token(tmp_path: Path) -> None:
    run, case, proposal, _ = _fixture(tmp_path)
    with pytest.raises(DenseUiPanelApprovalError):
        approve(
            run_root=run,
            case_root=case,
            proposal_path=proposal,
            approval_token="wrong",
            operator_id="operator",
            approved_at="2026-07-31T00:00:00+00:00",
            output_name="approval.json",
        )


def test_materialization_updates_pointer_and_rejects_duplicate(tmp_path: Path) -> None:
    run, case, proposal, token = _fixture(tmp_path)
    approve(
        run_root=run,
        case_root=case,
        proposal_path=proposal,
        approval_token=token,
        operator_id="operator",
        approved_at="2026-07-31T00:00:00+00:00",
        output_name="approval.json",
    )
    summary = materialize(
        run_root=run,
        case_root=case,
        proposal_name="proposal.json",
        approval_name="approval.json",
        artifact_version="v_test",
        operator_id="operator",
        output_name="summary.json",
    )
    assert summary["status"] == "PHASE4_DENSE_UI_PANEL_MATERIALIZED"
    pointer = json.loads((case / "phase4_visual_remediation_active.json").read_text())
    active = json.loads((case / pointer["active_ref"]["path"]).read_text())
    assert active["operations"][-1]["operation"] == "ADD_DENSE_UI_PANEL"
    with pytest.raises(Exception, match="already materialized|Active remediation changed"):
        materialize(
            run_root=run,
            case_root=case,
            proposal_name="proposal.json",
            approval_name="approval.json",
            artifact_version="v_test",
            operator_id="operator",
            output_name="summary.json",
        )
