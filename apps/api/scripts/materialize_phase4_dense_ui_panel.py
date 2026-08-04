"""Materialize an approved dense UI panel into active visual remediation."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.run_phase4_adaptive import _source_path

from src.media_pipeline.video_renderer.visual_remediation import (
    ACTIVE_POINTER_NAME,
    apply_visual_remediation,
    load_active_visual_remediation,
)


class DenseUiPanelMaterializationError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DenseUiPanelMaterializationError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise DenseUiPanelMaterializationError(f"{path.name} must contain an object")
    return payload


def _verify_self_hash(payload: Mapping[str, Any], key: str) -> bool:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(key, "") or "")
    return len(claimed) == 64 and claimed == _sha256_json(unsigned)


def _dependency_path(case: Path, name: str, ref: Mapping[str, Any]) -> Path:
    if name == "source_video":
        source = _source_path(case).resolve()
        if source.name != Path(str(ref.get("path") or "")).name:
            raise DenseUiPanelMaterializationError("Panel source authority path changed")
        return source
    path = (case / str(ref.get("path") or "")).resolve()
    if not path.is_relative_to(case):
        raise DenseUiPanelMaterializationError("Panel dependency escapes case root")
    return path


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def materialize(
    *,
    run_root: str | Path,
    case_root: str | Path,
    proposal_name: str,
    approval_name: str,
    artifact_version: str,
    operator_id: str,
    output_name: str,
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    case = Path(case_root).resolve()
    if not case.is_relative_to(root):
        raise DenseUiPanelMaterializationError("Case root must stay in run root")
    proposal_path = root / proposal_name
    approval_path = root / approval_name
    proposal = _load(proposal_path)
    approval = _load(approval_path)
    if (
        not _verify_self_hash(proposal, "proposal_sha256")
        or not _verify_self_hash(approval, "approval_sha256")
        or str(approval.get("status") or "")
        != "PHASE4_DENSE_UI_PANEL_PROPOSAL_APPROVED"
        or str(dict(approval.get("proposal_ref") or {}).get("sha256") or "")
        != _sha256_file(proposal_path)
        or str(dict(approval.get("proposal_ref") or {}).get("proposal_sha256") or "")
        != str(proposal.get("proposal_sha256") or "")
    ):
        raise DenseUiPanelMaterializationError("Panel approval is stale")
    for name, raw in dict(proposal.get("authority_refs") or {}).items():
        if not isinstance(raw, Mapping):
            raise DenseUiPanelMaterializationError("Panel dependency is invalid")
        ref = dict(raw)
        path = _dependency_path(case, str(name), ref)
        if (
            not path.is_file()
            or _sha256_file(path) != str(ref.get("sha256") or "")
        ):
            raise DenseUiPanelMaterializationError("Panel dependency hash changed")
    contract_path = case / "phase4_render_input.json"
    raw_contract = _load(contract_path)
    effective, active_ref = apply_visual_remediation(
        case, raw_contract, contract_path=contract_path
    )
    if active_ref != dict(
        dict(proposal.get("authority_refs") or {}).get("visual_remediation") or {}
    ):
        raise DenseUiPanelMaterializationError("Active remediation changed after proposal")
    active = load_active_visual_remediation(case, contract_path=contract_path)
    if active is None:
        raise DenseUiPanelMaterializationError("Dense panel requires parent remediation")
    parent, parent_ref = active
    decision = dict(proposal.get("decision") or {})
    canonical_id = str(decision.get("canonical_text_id") or "")
    canonical = next(
        (
            dict(row)
            for row in list(effective.get("render_tracks") or [])
            if str(dict(row).get("text_id") or "") == canonical_id
        ),
        None,
    )
    if canonical is None:
        raise DenseUiPanelMaterializationError("Canonical panel track is missing")
    span = [int(value) for value in list(decision.get("frame_span") or [])]
    if len(span) != 2:
        raise DenseUiPanelMaterializationError("Panel frame span is invalid")
    approval_hash = str(approval.get("approval_sha256") or "")
    panel = {
        "panel_id": f"p4panel_{approval_hash[:12]}",
        "canonical_text_id": canonical_id,
        "start_frame": span[0],
        "end_frame": span[1],
        "panel_roi": dict(decision.get("panel_roi") or {}),
        "cover_strategy": decision.get("cover_strategy"),
        "layout_strategy": decision.get("layout_strategy"),
        "deduplication_key": decision.get("deduplication_key"),
        "max_rendered_lines": int(decision.get("max_rendered_lines") or 0),
        "max_frame_change_fraction": float(
            decision.get("existing_max_frame_change_fraction") or 0.0
        ),
        "operator_approval_ref": {
            "path": f"../{approval_path.name}",
            "sha256": _sha256_file(approval_path),
            "approval_sha256": approval_hash,
        },
    }
    operation = {
        "operation": "ADD_DENSE_UI_PANEL",
        "panel": panel,
        "expected_panel_sha256": _sha256_json(panel),
        "expected_canonical_track_sha256": _sha256_json(canonical),
    }
    operations = [
        dict(row)
        for row in list(parent.get("operations") or [])
        if isinstance(row, Mapping)
    ]
    if any(str(dict(row.get("panel") or {}).get("panel_id") or "") == panel["panel_id"] for row in operations):
        raise DenseUiPanelMaterializationError("Dense panel is already materialized")
    operations.append(operation)
    resolved_operator = str(operator_id or "").strip()
    if resolved_operator != str(approval.get("operator_id") or "").strip():
        raise DenseUiPanelMaterializationError("Materializer operator does not match approval")
    if Path(output_name).name != output_name or not output_name.endswith(".json"):
        raise DenseUiPanelMaterializationError("Invalid materialization output name")
    payload: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_v1",
        "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_id": resolved_operator,
        "authority_refs": {
            "phase4_input": dict(
                dict(parent.get("authority_refs") or {}).get("phase4_input") or {}
            ),
            "dense_ui_panel_proposal": {
                "path": f"../{proposal_path.name}",
                "sha256": _sha256_file(proposal_path),
                "proposal_sha256": proposal.get("proposal_sha256"),
            },
            "dense_ui_panel_approval": panel["operator_approval_ref"],
            "parent_visual_remediation": parent_ref,
        },
        "operations": operations,
        "non_goals": [
            "do_not_overwrite_master_timeline",
            "do_not_relax_mask_or_output_qa_thresholds",
            "do_not_write_visual_approval",
        ],
    }
    if not payload["operator_id"]:
        raise DenseUiPanelMaterializationError("operator_id is required")
    payload["materialization_sha256"] = _sha256_json(payload)
    artifact_name = (
        f"phase4_visual_remediation_{approval_hash[:12]}_dense_ui_panel.json"
    )
    artifact_path = case / artifact_name
    _write_json_atomic(artifact_path, payload)
    pointer: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_pointer_v1",
        "status": "ACTIVE",
        "active_ref": {
            "path": artifact_name,
            "sha256": _sha256_file(artifact_path),
            "materialization_sha256": payload["materialization_sha256"],
        },
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    _write_json_atomic(case / ACTIVE_POINTER_NAME, pointer)
    summary: dict[str, Any] = {
        "schema_version": "phase4_dense_ui_panel_materialization_v1",
        "status": "PHASE4_DENSE_UI_PANEL_MATERIALIZED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_id": case.name,
        "proposal_ref": payload["authority_refs"]["dense_ui_panel_proposal"],
        "approval_ref": payload["authority_refs"]["dense_ui_panel_approval"],
        "visual_remediation_ref": pointer["active_ref"],
        "panel": panel,
        "artifact_version": str(artifact_version),
    }
    summary["materialization_sha256"] = _sha256_json(summary)
    _write_json_atomic(root / output_name, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.materialize_phase4_dense_ui_panel"
    )
    parser.add_argument("run_root")
    parser.add_argument("case_root")
    parser.add_argument("--proposal-name", required=True)
    parser.add_argument("--approval-name", required=True)
    parser.add_argument("--artifact-version", default="v22_47")
    parser.add_argument("--operator-id", required=True)
    parser.add_argument(
        "--output-name", default="phase4_dense_ui_panel_materialization_v22_47.json"
    )
    args = parser.parse_args()
    try:
        payload = materialize(
            run_root=args.run_root,
            case_root=args.case_root,
            proposal_name=args.proposal_name,
            approval_name=args.approval_name,
            artifact_version=args.artifact_version,
            operator_id=args.operator_id,
            output_name=args.output_name,
        )
    except (OSError, ValueError, DenseUiPanelMaterializationError) as exc:
        print(f"[PHASE4-DENSE-UI-PANEL-MATERIALIZATION][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "case_id": payload["case_id"],
                "panel_id": payload["panel"]["panel_id"],
                "visual_remediation_ref": payload["visual_remediation_ref"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
