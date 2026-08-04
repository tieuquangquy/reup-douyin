"""Record hash-bound operator approval for V22.8.1 residual decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class OutputResidualDecisionApprovalError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OutputResidualDecisionApprovalError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise OutputResidualDecisionApprovalError(
            f"{path.name} must contain an object"
        )
    return payload


def _verify_ref(root: Path, raw: Mapping[str, Any]) -> None:
    ref = dict(raw)
    path = (root / str(ref.get("path") or "")).resolve()
    if (
        not path.is_relative_to(root)
        or not path.is_file()
        or _sha256_file(path) != str(ref.get("sha256") or "")
    ):
        raise OutputResidualDecisionApprovalError(
            "Decision proposal dependency hash changed"
        )


def approve(
    *,
    run_root: str | Path,
    proposal_path: str | Path,
    approval_token: str,
    operator_id: str,
    approved_at: str,
    output_name: str = "phase4_output_residual_decision_approval_v22_8_1.json",
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    proposal_file = Path(proposal_path).resolve()
    if not proposal_file.is_relative_to(root):
        raise OutputResidualDecisionApprovalError(
            "Decision proposal must be inside run root"
        )
    proposal = _load_object(proposal_file)
    unsigned = dict(proposal)
    claimed_hash = str(unsigned.pop("proposal_sha256", "") or "")
    token = str(approval_token or "").strip()
    if (
        len(claimed_hash) != 64
        or claimed_hash != _sha256_json(unsigned)
        or str(proposal.get("status") or "")
        != "OUTPUT_RESIDUAL_DECISIONS_READY_FOR_OPERATOR_REVIEW"
        or bool(proposal.get("operator_approval_written"))
        or bool(proposal.get("authority_mutation_written"))
        or token != str(proposal.get("operator_approval_token") or "")
    ):
        raise OutputResidualDecisionApprovalError(
            "Residual decision proposal authority is invalid"
        )
    for raw in dict(proposal.get("authority_refs") or {}).values():
        if not isinstance(raw, Mapping):
            raise OutputResidualDecisionApprovalError(
                "Decision proposal dependency is invalid"
            )
        _verify_ref(root, raw)
    operator = str(operator_id or "").strip()
    timestamp = str(approved_at or "").strip()
    if not operator or not timestamp:
        raise OutputResidualDecisionApprovalError(
            "operator_id and approved_at are required"
        )
    counts = dict(proposal.get("counts") or {})
    if int(counts.get("decisions") or 0) < 1:
        raise OutputResidualDecisionApprovalError("Proposal has no decisions")
    payload: dict[str, Any] = {
        "schema_version": "phase4_output_residual_decision_approval_v1",
        "status": "PHASE4_OUTPUT_RESIDUAL_DECISIONS_APPROVED",
        "operator_id": operator,
        "approved_at": timestamp,
        "approval_token": token,
        "proposal_ref": {
            "path": proposal_file.name,
            "sha256": _sha256_file(proposal_file),
            "proposal_sha256": claimed_hash,
        },
        "approved_counts": counts,
        "materialization_status": "PENDING_SOURCE_BOUNDARY_VALIDATION",
        "operator_approval_written": True,
        "authority_mutation_written": False,
        "non_goals": [
            "do_not_overwrite_master_timeline",
            "do_not_relax_qa_thresholds",
            "do_not_materialize_unverified_source_boundaries",
        ],
    }
    payload["approval_sha256"] = _sha256_json(payload)
    filename = str(output_name or "").strip()
    if (
        not filename
        or Path(filename).name != filename
        or not filename.endswith(".json")
    ):
        raise OutputResidualDecisionApprovalError("Invalid approval output name")
    output = root / filename
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(output)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.approve_phase4_output_residual_decisions"
    )
    parser.add_argument("run_root")
    parser.add_argument("proposal_path")
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--approved-at")
    parser.add_argument(
        "--output-name",
        default="phase4_output_residual_decision_approval_v22_8_1.json",
    )
    args = parser.parse_args()
    try:
        payload = approve(
            run_root=args.run_root,
            proposal_path=args.proposal_path,
            approval_token=args.approval_token,
            operator_id=args.operator_id,
            approved_at=args.approved_at or datetime.now(timezone.utc).isoformat(),
            output_name=args.output_name,
        )
    except (OSError, ValueError, OutputResidualDecisionApprovalError) as exc:
        print(f"[PHASE4-OUTPUT-RESIDUAL-DECISION-APPROVAL][FAIL] {exc}", flush=True)
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
