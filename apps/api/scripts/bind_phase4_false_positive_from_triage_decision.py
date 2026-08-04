"""Bind an approved source-intrinsic triage decision to fresh Phase-4 OCR."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.media_pipeline.video_renderer.phase4_approvals import (
    Phase4ApprovalError,
    record_residual_cjk_false_positive_approval,
)


class ResidualFalsePositiveBridgeError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResidualFalsePositiveBridgeError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise ResidualFalsePositiveBridgeError(
            f"{path.name} must contain an object"
        )
    return payload


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_self(payload: Mapping[str, Any], field: str, *, label: str) -> None:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    if len(claimed) != 64 or claimed != _sha_json(unsigned):
        raise ResidualFalsePositiveBridgeError(f"{label} self-hash is invalid")


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _rect(raw: Mapping[str, Any]) -> tuple[float, float, float, float]:
    geometry = dict(raw.get("geometry") or {})
    x = float(geometry.get("x") or 0.0)
    y = float(geometry.get("y") or 0.0)
    width = float(geometry.get("width") or 0.0)
    height = float(geometry.get("height") or 0.0)
    if min(width, height) <= 0:
        raise ResidualFalsePositiveBridgeError("Residual geometry is invalid")
    return x, y, x + width, y + height


def _overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    a = _rect(left)
    b = _rect(right)
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1])
    )
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return intersection / smaller if smaller > 0 else 0.0


def bind_false_positive(
    *,
    run_root: str | Path,
    case_id: str,
    approval_token: str,
    operator_id: str,
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    root = (run / str(case_id)).resolve()
    if not root.is_relative_to(run) or not root.is_dir():
        raise ResidualFalsePositiveBridgeError("Case root is invalid")
    index_path = run / "phase4_residual_triage_materialization_index.json"
    index = _load(index_path)
    _verify_self(index, "materialization_sha256", label="Materialization index")
    parent_token = str(approval_token or "").strip()
    operator = str(operator_id or "").strip()
    if parent_token != str(index.get("approval_token") or "") or not operator:
        raise ResidualFalsePositiveBridgeError(
            "Parent triage approval token or operator is invalid"
        )
    case_row = next(
        (
            dict(row)
            for row in list(index.get("cases") or [])
            if str(dict(row).get("case_id") or "") == str(case_id)
        ),
        None,
    )
    if case_row is None:
        raise ResidualFalsePositiveBridgeError("Case is absent from materialization")
    projection_ref = dict(case_row.get("projection_ref") or {})
    projection_path = (run / str(projection_ref.get("path") or "")).resolve()
    if (
        not projection_path.is_relative_to(root)
        or not projection_path.is_file()
        or _sha_file(projection_path) != str(projection_ref.get("sha256") or "")
    ):
        raise ResidualFalsePositiveBridgeError("Decision projection is stale")
    projection = _load(projection_path)
    _verify_self(projection, "projection_sha256", label="Decision projection")
    decisions = [
        dict(row)
        for row in list(projection.get("false_positive_decisions") or [])
        if isinstance(row, Mapping)
    ]
    if len(decisions) != 1:
        raise ResidualFalsePositiveBridgeError(
            "Exactly one approved false-positive decision is required"
        )
    decision = decisions[0]
    frame_index = int(decision.get("frame_index") or 0)
    meta_path = root / "phase4_preflight_meta.json"
    meta = _load(meta_path)
    detections = [
        dict(row)
        for row in list(dict(meta.get("residual_cjk") or {}).get("detections") or [])
        if isinstance(row, Mapping)
        and int(dict(row).get("frame_index") or 0) == frame_index
    ]
    if len(detections) != 1:
        raise ResidualFalsePositiveBridgeError(
            "Fresh preflight does not have exactly one matching detection"
        )
    current = detections[0]
    visual_path = root / "phase4_residual_visual_triage.json"
    visual = _load(visual_path)
    _verify_self(visual, "triage_sha256", label="Visual triage")
    cluster = next(
        (
            dict(row)
            for row in list(visual.get("clusters") or [])
            if str(dict(row).get("cluster_id") or "")
            == str(decision.get("cluster_id") or "")
        ),
        None,
    )
    if cluster is None:
        raise ResidualFalsePositiveBridgeError("Approved visual cluster is missing")
    prior = max(
        list(cluster.get("detections") or []),
        key=lambda row: float(dict(row).get("confidence") or 0.0),
    )
    if (
        str(current.get("text") or "") != str(decision.get("source_text") or "")
        or str(current.get("text") or "") != str(dict(prior).get("text") or "")
        or _overlap(current, dict(prior)) < 0.80
    ):
        raise ResidualFalsePositiveBridgeError(
            "Fresh residual does not match the approved source-intrinsic cluster"
        )
    proposal_sha = str(
        dict(index.get("decision_proposal_ref") or {}).get("proposal_sha256") or ""
    )
    derived_token = f"OCR_FALSE_POSITIVE_CONFIRMED_V22_1_{proposal_sha[:12].upper()}"
    try:
        approval = record_residual_cjk_false_positive_approval(
            root_dir=root,
            frame_index=frame_index,
            approval_token=derived_token,
            operator_id=operator,
        )
    except Phase4ApprovalError as exc:
        raise ResidualFalsePositiveBridgeError(str(exc)) from exc
    approval_path = root / "phase4_residual_cjk_false_positive_approval.json"
    bridge: dict[str, Any] = {
        "schema_version": "phase4_residual_false_positive_decision_bridge_v1",
        "status": "SOURCE_INTRINSIC_FALSE_POSITIVE_APPROVAL_BOUND",
        "case_id": case_id,
        "parent_triage_approval_token": parent_token,
        "derived_phase4_approval_token": derived_token,
        "operator_id": operator,
        "materialization_ref": {
            "path": index_path.relative_to(run).as_posix(),
            "sha256": _sha_file(index_path),
            "materialization_sha256": index.get("materialization_sha256"),
        },
        "projection_ref": projection_ref,
        "fresh_preflight_ref": {
            "path": meta_path.name,
            "sha256": _sha_file(meta_path),
        },
        "phase4_approval_ref": {
            "path": approval_path.name,
            "sha256": _sha_file(approval_path),
            "approval_sha256": approval.get("approval_sha256"),
        },
    }
    bridge["bridge_sha256"] = _sha_json(bridge)
    _write(root / "phase4_residual_false_positive_decision_bridge.json", bridge)
    return bridge


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.bind_phase4_false_positive_from_triage_decision"
    )
    parser.add_argument("run_root")
    parser.add_argument("case_id")
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--operator", default="operator-user-approved-v22-1")
    args = parser.parse_args()
    try:
        bridge = bind_false_positive(
            run_root=args.run_root,
            case_id=args.case_id,
            approval_token=args.approval_token,
            operator_id=args.operator,
        )
        print(
            json.dumps(
                {
                    "status": bridge["status"],
                    "derived_phase4_approval_token": bridge[
                        "derived_phase4_approval_token"
                    ],
                    "bridge_sha256": bridge["bridge_sha256"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, ResidualFalsePositiveBridgeError) as exc:
        print(f"[PHASE4-FALSE-POSITIVE-BRIDGE][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
