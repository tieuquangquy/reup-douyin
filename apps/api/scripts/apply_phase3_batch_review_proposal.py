"""Apply an explicitly authorized hash-bound Phase 3 proposal batch."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.apply_phase3_review_proposal import (
    Phase3ProposalApprovalError,
    apply_review_proposal,
)
from scripts.build_phase3_batch_review_index import approval_token


class Phase3BatchProposalApprovalError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase3BatchProposalApprovalError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise Phase3BatchProposalApprovalError(
            f"{path.name} must contain an object"
        )
    return payload


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


def _verify_self_hash(payload: Mapping[str, Any], field: str) -> bool:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    return len(claimed) == 64 and claimed == _sha256_json(unsigned)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _restore(path: Path, previous: bytes | None) -> None:
    if previous is None:
        if path.is_file():
            path.unlink()
        return
    temporary = path.with_suffix(path.suffix + ".rollback")
    temporary.write_bytes(previous)
    temporary.replace(path)


def apply_batch_review_proposal(
    *,
    run_root: str | Path,
    batch_index_path: str | Path,
    supplied_token: str,
    operator_id: str,
    approved_at: str,
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    batch_path = Path(batch_index_path).resolve()
    if not batch_path.is_relative_to(run):
        raise Phase3BatchProposalApprovalError(
            "Batch review index must be inside the run root"
        )
    batch = _load_object(batch_path)
    if not _verify_self_hash(batch, "batch_review_sha256"):
        raise Phase3BatchProposalApprovalError("Batch review self-hash is invalid")
    if (
        str(batch.get("status") or "")
        != "TRANSLATION_OPERATOR_REVIEW_REQUIRED"
        or bool(batch.get("operator_approval_written"))
    ):
        raise Phase3BatchProposalApprovalError("Batch review is not approvable")
    expected_token = approval_token(batch)
    if str(supplied_token or "").strip().upper() != expected_token:
        raise Phase3BatchProposalApprovalError(
            "Operator approval token does not match the current batch review"
        )
    operator = str(operator_id or "").strip()
    timestamp = str(approved_at or "").strip()
    if not operator or not timestamp:
        raise Phase3BatchProposalApprovalError(
            "operator_id and approved_at are required"
        )

    state_ref = dict(batch.get("batch_state_ref") or {})
    state_path = (run / str(state_ref.get("path") or "")).resolve()
    if (
        not state_path.is_relative_to(run)
        or not state_path.is_file()
        or str(state_ref.get("sha256") or "") != _sha256_file(state_path)
    ):
        raise Phase3BatchProposalApprovalError("Batch state reference is stale")

    prepared: list[dict[str, Any]] = []
    for raw in list(batch.get("cases") or []):
        if not isinstance(raw, Mapping):
            raise Phase3BatchProposalApprovalError("Batch contains an invalid case")
        case = dict(raw)
        case_id = str(case.get("case_id") or "").strip()
        case_root = (run / case_id).resolve()
        proposal_path = (run / str(case.get("proposal_path") or "")).resolve()
        queue_ref = dict(case.get("phase3_review_queue_ref") or {})
        queue_path = (run / str(queue_ref.get("path") or "")).resolve()
        approvals_path = case_root / "phase3_approvals.json"
        if (
            not case_id
            or not case_root.is_relative_to(run)
            or not case_root.is_dir()
            or not proposal_path.is_relative_to(case_root)
            or not proposal_path.is_file()
            or not queue_path.is_relative_to(case_root)
            or not queue_path.is_file()
            or not approvals_path.is_file()
        ):
            raise Phase3BatchProposalApprovalError(
                f"Missing case authority for {case_id or '(empty)'}"
            )
        if _sha256_file(proposal_path) != str(
            case.get("proposal_file_sha256") or ""
        ):
            raise Phase3BatchProposalApprovalError(
                f"Proposal file is stale for {case_id}"
            )
        if _sha256_file(queue_path) != str(queue_ref.get("sha256") or ""):
            raise Phase3BatchProposalApprovalError(
                f"Review queue is stale for {case_id}"
            )
        proposal = _load_object(proposal_path)
        if (
            not _verify_self_hash(proposal, "proposal_sha256")
            or str(proposal.get("proposal_sha256") or "")
            != str(case.get("proposal_sha256") or "")
        ):
            raise Phase3BatchProposalApprovalError(
                f"Proposal hash is invalid for {case_id}"
            )
        approvals = _load_object(approvals_path)
        if any(
            isinstance(row, Mapping)
            and (
                str(row.get("decision") or "").strip()
                or str(row.get("reviewer") or "").strip()
                or str(row.get("reviewed_at") or "").strip()
            )
            for row in list(approvals.get("approvals") or [])
        ):
            raise Phase3BatchProposalApprovalError(
                f"Operator decisions already exist for {case_id}"
            )
        prepared.append(
            {
                "case_id": case_id,
                "case_root": case_root,
                "proposal_path": proposal_path,
                "approvals_path": approvals_path,
                "audit_path": case_root / "phase3_operator_approval_audit.json",
            }
        )
    if len(prepared) != int(dict(batch.get("counts") or {}).get("cases") or 0):
        raise Phase3BatchProposalApprovalError("Batch case count mismatch")

    snapshots: dict[Path, bytes | None] = {}
    for item in prepared:
        for key in ("approvals_path", "audit_path"):
            path = Path(item[key])
            snapshots[path] = path.read_bytes() if path.is_file() else None
    applied: list[dict[str, Any]] = []
    try:
        for item in prepared:
            try:
                audit = apply_review_proposal(
                    root_dir=item["case_root"],
                    proposal_path=item["proposal_path"],
                    operator_id=operator,
                    approved_at=timestamp,
                )
            except (OSError, ValueError, Phase3ProposalApprovalError) as exc:
                raise Phase3BatchProposalApprovalError(
                    f"Cannot apply {item['case_id']}: {exc}"
                ) from exc
            audit_path = Path(item["audit_path"])
            applied.append(
                {
                    "case_id": item["case_id"],
                    "proposal_sha256": _load_object(
                        Path(item["proposal_path"])
                    ).get("proposal_sha256"),
                    "operator_review_audit_ref": {
                        "path": audit_path.relative_to(run).as_posix(),
                        "sha256": _sha256_file(audit_path),
                        "audit_sha256": audit.get("audit_sha256"),
                    },
                    "approvals_ref": {
                        "path": Path(item["approvals_path"])
                        .relative_to(run)
                        .as_posix(),
                        "sha256": _sha256_file(Path(item["approvals_path"])),
                    },
                    "counts": audit.get("counts"),
                }
            )
    except Exception:
        for path, previous in snapshots.items():
            _restore(path, previous)
        raise

    result: dict[str, Any] = {
        "schema_version": "phase3_batch_proposal_approval_v1",
        "status": "TRANSLATION_DECISIONS_RECORDED_PHASE3_RERUN_REQUIRED",
        "approval_token": expected_token,
        "operator_id": operator,
        "approved_at": timestamp,
        "batch_review_ref": {
            "path": batch_path.relative_to(run).as_posix(),
            "file_sha256": _sha256_file(batch_path),
            "batch_review_sha256": batch.get("batch_review_sha256"),
        },
        "counts": batch.get("counts"),
        "cases": applied,
    }
    result["approval_sha256"] = _sha256_json(result)
    _write_json_atomic(run / "phase3_batch_proposal_approval.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.apply_phase3_batch_review_proposal"
    )
    parser.add_argument("run_root")
    parser.add_argument("batch_review_json")
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--operator", default="operator-user-approved")
    args = parser.parse_args()
    try:
        result = apply_batch_review_proposal(
            run_root=args.run_root,
            batch_index_path=args.batch_review_json,
            supplied_token=args.approval_token,
            operator_id=args.operator,
            approved_at=datetime.now(timezone.utc).isoformat(),
        )
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "counts": result["counts"],
                    "approval_sha256": result["approval_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, Phase3BatchProposalApprovalError) as exc:
        print(f"[PHASE3-BATCH-APPROVAL][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
