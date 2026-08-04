"""Apply an explicitly approved, hash-bound Phase 1 geometry proposal."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.media_pipeline.frame_sampling.phase1_geometry_review import (
    Phase1GeometryReviewError,
    prepare_phase1_geometry_review,
    record_phase1_geometry_decisions,
)


class Phase1GeometryProposalError(RuntimeError):
    pass


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase1GeometryProposalError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise Phase1GeometryProposalError(f"{path.name} must contain an object")
    return payload


def _verify_self_hash(payload: Mapping[str, Any], field: str) -> bool:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    return len(claimed) == 64 and claimed == _sha256_json(unsigned)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def apply_proposal(
    *,
    run_root: str | Path,
    approval_token: str,
    operator_id: str,
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    proposal_path = run / "phase1_geometry_review_proposal.json"
    proposal = _load_object(proposal_path)
    if not _verify_self_hash(proposal, "proposal_sha256"):
        raise Phase1GeometryProposalError("Geometry proposal self-hash is invalid")
    expected_token = str(proposal.get("approval_token_required") or "")
    provided_token = str(approval_token or "").strip()
    operator = str(operator_id or "").strip()
    if not expected_token or provided_token != expected_token:
        raise Phase1GeometryProposalError("Explicit geometry approval token is invalid")
    if not operator:
        raise Phase1GeometryProposalError("Geometry approval requires operator_id")
    if bool(proposal.get("ocr_approval_granted")) or bool(
        proposal.get("recipe_lock_granted")
    ):
        raise Phase1GeometryProposalError("Geometry proposal exceeds its authority")

    target = run / "phase1_geometry_proposal_approval.json"
    if target.is_file():
        existing = _load_object(target)
        proposal_ref = dict(existing.get("proposal_ref") or {})
        if (
            _verify_self_hash(existing, "approval_sha256")
            and str(existing.get("approval_token") or "") == provided_token
            and str(proposal_ref.get("proposal_sha256") or "")
            == str(proposal.get("proposal_sha256") or "")
        ):
            return existing

    case_refs: list[dict[str, Any]] = []
    raw_cases = list(proposal.get("cases") or [])
    if not raw_cases:
        raise Phase1GeometryProposalError("Geometry proposal has no cases")
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            raise Phase1GeometryProposalError("Geometry proposal case is invalid")
        case = dict(raw_case)
        case_id = str(case.get("case_id") or "").strip()
        case_root = (run / case_id).resolve()
        if not case_id or not case_root.is_relative_to(run) or not case_root.is_dir():
            raise Phase1GeometryProposalError("Geometry proposal case root is invalid")
        current_review = prepare_phase1_geometry_review(case_root)
        expected_review = str(dict(case.get("review_ref") or {}).get("review_sha256") or "")
        if expected_review != str(current_review.get("review_sha256") or ""):
            raise Phase1GeometryProposalError(
                f"Geometry proposal is stale for {case_id}"
            )
        decisions = [
            dict(row)
            for row in list(case.get("decisions") or [])
            if isinstance(row, Mapping)
        ]
        approval = record_phase1_geometry_decisions(
            case_root,
            operator_id=operator,
            decisions=decisions,
            notes=f"Approved by token {provided_token}",
        )
        approval_path = case_root / "phase1_geometry_approval.json"
        materialization_path = case_root / "phase1_geometry_overrides.json"
        materialization = _load_object(materialization_path)
        case_refs.append(
            {
                "case_id": case_id,
                "review_sha256": current_review.get("review_sha256"),
                "approval_ref": {
                    "path": approval_path.relative_to(run).as_posix(),
                    "file_sha256": _sha256_file(approval_path),
                    "approval_sha256": approval.get("approval_sha256"),
                },
                "materialization_ref": {
                    "path": materialization_path.relative_to(run).as_posix(),
                    "file_sha256": _sha256_file(materialization_path),
                    "materialization_sha256": materialization.get(
                        "materialization_sha256"
                    ),
                },
            }
        )

    authority: dict[str, Any] = {
        "schema_version": "phase1_geometry_proposal_approval_v1",
        "status": "PHASE1_GEOMETRY_PROPOSALS_APPROVED",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "operator_id": operator,
        "approval_token": provided_token,
        "proposal_ref": {
            "path": proposal_path.name,
            "file_sha256": _sha256_file(proposal_path),
            "proposal_sha256": proposal.get("proposal_sha256"),
        },
        "case_approvals": case_refs,
        "authority": {
            "geometry_only": True,
            "ocr_approval_granted": False,
            "recipe_lock_granted": False,
            "external_publish_granted": False,
        },
    }
    authority["approval_sha256"] = _sha256_json(authority)
    _write_json_atomic(target, authority)
    return authority


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--operator-id", default="local_operator")
    args = parser.parse_args(argv)
    try:
        result = apply_proposal(
            run_root=args.run_root,
            approval_token=args.approval_token,
            operator_id=args.operator_id,
        )
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "case_count": len(list(result.get("case_approvals") or [])),
                    "approval_sha256": result["approval_sha256"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, Phase1GeometryReviewError, Phase1GeometryProposalError) as exc:
        print(f"[PHASE1-GEOMETRY-PROPOSAL][FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

