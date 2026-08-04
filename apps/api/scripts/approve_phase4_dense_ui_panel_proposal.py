"""Record hash-bound operator approval for a dense UI panel proposal."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.run_phase4_adaptive import _source_path


class DenseUiPanelApprovalError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DenseUiPanelApprovalError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise DenseUiPanelApprovalError(f"{path.name} must contain an object")
    return payload


def _dependency_path(case: Path, name: str, ref: Mapping[str, Any]) -> Path:
    if name == "source_video":
        source = _source_path(case).resolve()
        if source.name != Path(str(ref.get("path") or "")).name:
            raise DenseUiPanelApprovalError("Panel source authority path changed")
        return source
    path = (case / str(ref.get("path") or "")).resolve()
    if not path.is_relative_to(case):
        raise DenseUiPanelApprovalError("Panel dependency escapes case root")
    return path


def approve(
    *,
    run_root: str | Path,
    case_root: str | Path,
    proposal_path: str | Path,
    approval_token: str,
    operator_id: str,
    approved_at: str,
    output_name: str,
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    case = Path(case_root).resolve()
    proposal_file = Path(proposal_path).resolve()
    if not case.is_relative_to(root) or not proposal_file.is_relative_to(root):
        raise DenseUiPanelApprovalError("Panel authority paths must stay in run root")
    proposal = _load(proposal_file)
    unsigned = dict(proposal)
    claimed = str(unsigned.pop("proposal_sha256", "") or "")
    if (
        claimed != _sha256_json(unsigned)
        or str(proposal.get("status") or "") != "PROPOSAL_READY_FOR_OPERATOR_REVIEW"
        or str(dict(proposal.get("decision") or {}).get("action") or "")
        != "DENSE_UI_PANEL_FALLBACK"
        or bool(proposal.get("operator_approval_written"))
        or str(approval_token or "").strip()
        != str(proposal.get("operator_approval_token") or "")
    ):
        raise DenseUiPanelApprovalError("Dense UI panel proposal is invalid")
    for name, raw in dict(proposal.get("authority_refs") or {}).items():
        if not isinstance(raw, Mapping):
            raise DenseUiPanelApprovalError("Panel proposal dependency is invalid")
        ref = dict(raw)
        path = _dependency_path(case, str(name), ref)
        if (
            not path.is_file()
            or _sha256_file(path) != str(ref.get("sha256") or "")
        ):
            raise DenseUiPanelApprovalError("Panel proposal dependency hash changed")
    operator = str(operator_id or "").strip()
    timestamp = str(approved_at or "").strip()
    if not operator or not timestamp:
        raise DenseUiPanelApprovalError("operator_id and approved_at are required")
    payload: dict[str, Any] = {
        "schema_version": "phase4_dense_ui_panel_proposal_approval_v1",
        "status": "PHASE4_DENSE_UI_PANEL_PROPOSAL_APPROVED",
        "operator_id": operator,
        "approved_at": timestamp,
        "approval_token": str(approval_token).strip(),
        "proposal_ref": {
            "path": proposal_file.name,
            "sha256": _sha256_file(proposal_file),
            "proposal_sha256": claimed,
        },
        "materialization_status": "PENDING",
        "operator_approval_written": True,
        "authority_mutation_written": False,
        "non_goals": [
            "do_not_overwrite_master_timeline",
            "do_not_relax_qa_thresholds",
            "do_not_write_visual_approval",
        ],
    }
    payload["approval_sha256"] = _sha256_json(payload)
    if Path(output_name).name != output_name or not output_name.endswith(".json"):
        raise DenseUiPanelApprovalError("Invalid approval output name")
    output = root / output_name
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.approve_phase4_dense_ui_panel_proposal"
    )
    parser.add_argument("run_root")
    parser.add_argument("case_root")
    parser.add_argument("proposal_path")
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--approved-at")
    parser.add_argument(
        "--output-name",
        default="phase4_dense_ui_panel_proposal_approval_v22_47.json",
    )
    args = parser.parse_args()
    try:
        payload = approve(
            run_root=args.run_root,
            case_root=args.case_root,
            proposal_path=args.proposal_path,
            approval_token=args.approval_token,
            operator_id=args.operator_id,
            approved_at=args.approved_at or datetime.now(timezone.utc).isoformat(),
            output_name=args.output_name,
        )
    except (OSError, ValueError, DenseUiPanelApprovalError) as exc:
        print(f"[PHASE4-DENSE-UI-PANEL-APPROVAL][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "approval_sha256": payload["approval_sha256"],
                "materialization_status": payload["materialization_status"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
