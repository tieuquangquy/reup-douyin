"""Apply an explicitly approved hash-bound Phase 2 OCR batch proposal."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.build_phase2_review_proposal import (
    Phase2ReviewProposalError,
    validate_review_proposal,
)
from scripts.materialize_phase2_review_proposal import (
    Phase2ProposalMaterializationError,
    materialize_approved_proposal,
)
from src.services.phase2_operator_review import (
    Phase2OperatorReviewError,
    apply_phase2_operator_review,
)


class Phase2BatchProposalApprovalError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase2BatchProposalApprovalError(f"Cannot read valid {path}") from exc
    if not isinstance(payload, dict):
        raise Phase2BatchProposalApprovalError(f"{path} must contain an object")
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
    path.parent.mkdir(parents=True, exist_ok=True)
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


def expected_approval_token(
    batch_proposal_sha256: str, *, approval_label: str
) -> str:
    label = str(approval_label or "").strip().upper()
    digest = str(batch_proposal_sha256 or "").strip().upper()
    if not label or len(digest) != 64:
        raise Phase2BatchProposalApprovalError(
            "Approval label and full batch proposal SHA-256 are required"
        )
    return f"OCR_PROPOSALS_APPROVED_{label}_{digest[:12]}"


def apply_batch_proposal(
    *,
    run_root: Path,
    batch_proposal_path: Path,
    approval_token: str,
    approval_label: str,
    reviewer: str,
    reviewed_at: str,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    batch_proposal_path = batch_proposal_path.resolve()
    if not batch_proposal_path.is_relative_to(run_root):
        raise Phase2BatchProposalApprovalError(
            "Batch proposal must be inside the run root"
        )
    batch = _load_object(batch_proposal_path)
    if not _verify_self_hash(batch, "batch_proposal_sha256"):
        raise Phase2BatchProposalApprovalError("Batch proposal self-hash is invalid")
    if str(batch.get("status") or "") != "OPERATOR_APPROVAL_REQUIRED":
        raise Phase2BatchProposalApprovalError("Batch proposal is not approvable")
    batch_sha = str(batch.get("batch_proposal_sha256") or "")
    expected_token = expected_approval_token(
        batch_sha, approval_label=approval_label
    )
    if str(approval_token or "").strip().upper() != expected_token:
        raise Phase2BatchProposalApprovalError(
            "Operator approval token does not match the current batch proposal"
        )
    reviewer = str(reviewer or "").strip()
    reviewed_at = str(reviewed_at or "").strip()
    if not reviewer or not reviewed_at:
        raise Phase2BatchProposalApprovalError("Reviewer and reviewed_at are required")

    for ref_name in ("batch_state_ref", "recommendations_ref"):
        ref = dict(batch.get(ref_name) or {})
        ref_path = (run_root / str(ref.get("path") or "")).resolve()
        if (
            not ref_path.is_relative_to(run_root)
            or not ref_path.is_file()
            or str(ref.get("sha256") or "") != _sha256_file(ref_path)
        ):
            raise Phase2BatchProposalApprovalError(
                f"Batch proposal {ref_name} is stale"
            )

    prepared: list[dict[str, Any]] = []
    for raw in list(batch.get("cases") or []):
        if not isinstance(raw, Mapping):
            raise Phase2BatchProposalApprovalError("Batch contains an invalid case")
        case = dict(raw)
        case_id = str(case.get("case_id") or "").strip()
        case_root = (run_root / case_id).resolve()
        proposal_path = (run_root / str(case.get("proposal_path") or "")).resolve()
        queue_path = case_root / "phase2_review_queue.json"
        if (
            not case_id
            or not case_root.is_relative_to(run_root)
            or not case_root.is_dir()
            or not proposal_path.is_relative_to(case_root)
            or not proposal_path.is_file()
            or not queue_path.is_file()
        ):
            raise Phase2BatchProposalApprovalError(
                f"Missing case authority for {case_id or '(empty)'}"
            )
        if _sha256_file(proposal_path) != str(case.get("proposal_file_sha256") or ""):
            raise Phase2BatchProposalApprovalError(
                f"Proposal file is stale for {case_id}"
            )
        if _sha256_file(queue_path) != str(case.get("review_queue_sha256") or ""):
            raise Phase2BatchProposalApprovalError(
                f"Review queue is stale for {case_id}"
            )
        proposal = _load_object(proposal_path)
        if str(proposal.get("proposal_sha256") or "") != str(
            case.get("proposal_sha256") or ""
        ):
            raise Phase2BatchProposalApprovalError(
                f"Proposal hash drift for {case_id}"
            )
        try:
            validate_review_proposal(target_root=case_root, proposal=proposal)
            decisions = materialize_approved_proposal(
                target_root=case_root,
                proposal_path=proposal_path,
                approved_proposal_sha256=str(case.get("proposal_sha256") or ""),
                reviewer=reviewer,
                reviewed_at=reviewed_at,
            )
        except (Phase2ReviewProposalError, Phase2ProposalMaterializationError) as exc:
            raise Phase2BatchProposalApprovalError(
                f"Cannot materialize {case_id}: {exc}"
            ) from exc
        prepared.append(
            {
                "case_id": case_id,
                "case_root": case_root,
                "proposal_path": proposal_path,
                "decisions": decisions,
                "decisions_path": case_root
                / "phase2_review_decisions_from_approved_batch.json",
            }
        )

    snapshots: dict[Path, bytes | None] = {}
    touched: list[Path] = []
    applied_rows: list[dict[str, Any]] = []
    try:
        for item in prepared:
            case_root = Path(item["case_root"])
            for path in (
                Path(item["decisions_path"]),
                case_root / "phase2_approvals.json",
                case_root / "phase2_operator_review_audit.json",
            ):
                snapshots[path] = path.read_bytes() if path.is_file() else None
                touched.append(path)
            _write_json_atomic(Path(item["decisions_path"]), item["decisions"])
        for item in prepared:
            try:
                audit = apply_phase2_operator_review(
                    root_dir=item["case_root"],
                    decisions_path=item["decisions_path"],
                )
            except (OSError, ValueError, Phase2OperatorReviewError) as exc:
                raise Phase2BatchProposalApprovalError(
                    f"Cannot apply {item['case_id']}: {exc}"
                ) from exc
            applied_rows.append(
                {
                    "case_id": item["case_id"],
                    "proposal_sha256": _load_object(
                        Path(item["proposal_path"])
                    ).get("proposal_sha256"),
                    "decisions_ref": {
                        "path": Path(item["decisions_path"])
                        .relative_to(run_root)
                        .as_posix(),
                        "sha256": _sha256_file(Path(item["decisions_path"])),
                        "decisions_sha256": item["decisions"].get(
                            "decisions_sha256"
                        ),
                    },
                    "operator_review_audit_ref": {
                        "path": (
                            Path(item["case_root"])
                            / "phase2_operator_review_audit.json"
                        )
                        .relative_to(run_root)
                        .as_posix(),
                        "sha256": _sha256_file(
                            Path(item["case_root"])
                            / "phase2_operator_review_audit.json"
                        ),
                        "audit_sha256": audit.get("audit_sha256"),
                    },
                    "counts": audit.get("counts"),
                }
            )
    except Exception:
        for path in reversed(touched):
            _restore(path, snapshots[path])
        raise

    result: dict[str, Any] = {
        "schema_version": "phase2_batch_proposal_approval_v1",
        "status": "OCR_DECISIONS_RECORDED_PHASE2_RERUN_REQUIRED",
        "approval_token": expected_token,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "batch_proposal_ref": {
            "path": batch_proposal_path.relative_to(run_root).as_posix(),
            "file_sha256": _sha256_file(batch_proposal_path),
            "batch_proposal_sha256": batch_sha,
        },
        "counts": batch.get("counts"),
        "cases": applied_rows,
    }
    result["approval_sha256"] = _sha256_json(result)
    _write_json_atomic(run_root / "phase2_batch_proposal_approval.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("batch_proposal_json")
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--approval-label", default="V22_1")
    parser.add_argument("--reviewer", default="operator-user-approved")
    args = parser.parse_args()
    result = apply_batch_proposal(
        run_root=Path(args.run_root),
        batch_proposal_path=Path(args.batch_proposal_json),
        approval_token=str(args.approval_token),
        approval_label=str(args.approval_label),
        reviewer=str(args.reviewer),
        reviewed_at=datetime.now(timezone.utc).isoformat(),
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "counts": result["counts"],
                "approval_sha256": result["approval_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
