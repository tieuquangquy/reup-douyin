"""Apply an explicitly authorized Phase 3 review proposal to approvals."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class Phase3ProposalApprovalError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase3ProposalApprovalError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise Phase3ProposalApprovalError(f"{path.name} must contain an object")
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


def apply_review_proposal(
    *,
    root_dir: str | Path,
    proposal_path: str | Path,
    operator_id: str,
    approved_at: str,
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    proposal_file = Path(proposal_path).resolve()
    operator = str(operator_id or "").strip()
    if not operator:
        raise Phase3ProposalApprovalError("operator_id is required")
    proposal = _load_object(proposal_file)
    if not _verify_self_hash(proposal, "proposal_sha256"):
        raise Phase3ProposalApprovalError("Proposal self-hash is invalid")
    if str(proposal.get("status") or "") != "PROPOSAL_READY_FOR_OPERATOR_REVIEW":
        raise Phase3ProposalApprovalError("Proposal status is not reviewable")
    if bool(proposal.get("operator_approval_written")):
        raise Phase3ProposalApprovalError("Proposal already claims operator approval")

    queue_path = root / "phase3_review_queue.json"
    approvals_path = root / "phase3_approvals.json"
    queue = _load_object(queue_path)
    approvals = _load_object(approvals_path)
    queue_ref = dict(proposal.get("phase3_review_queue_ref") or {})
    if str(queue_ref.get("sha256") or "") != _sha256_file(queue_path):
        raise Phase3ProposalApprovalError("Proposal is stale for the review queue")
    if dict(proposal.get("phase2_handoff_ref") or {}) != dict(
        queue.get("phase2_handoff_ref") or {}
    ):
        raise Phase3ProposalApprovalError("Proposal Phase 2 authority mismatch")
    if dict(approvals.get("phase2_handoff_ref") or {}) != dict(
        queue.get("phase2_handoff_ref") or {}
    ):
        raise Phase3ProposalApprovalError("Approval Phase 2 authority mismatch")

    queue_rows = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(queue.get("content_objects") or [])
        if isinstance(row, Mapping)
    }
    proposal_rows = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(proposal.get("proposals") or [])
        if isinstance(row, Mapping)
    }
    if not queue_rows or set(queue_rows) != set(proposal_rows) or "" in queue_rows:
        raise Phase3ProposalApprovalError(
            "Proposal must cover every Phase 3 review object exactly once"
        )

    approval_rows: list[dict[str, Any]] = []
    edited = 0
    for content_id, queue_row in queue_rows.items():
        row = proposal_rows[content_id]
        recommendation = str(row.get("recommendation") or "").upper()
        if recommendation not in {"APPROVE", "EDIT"}:
            raise Phase3ProposalApprovalError(
                f"Invalid recommendation for {content_id}"
            )
        candidate = str(queue_row.get("vi_text_candidate") or "").strip()
        proposed = str(row.get("vi_text_proposed") or "").strip()
        if (
            str(row.get("review_input_sha256") or "")
            != str(queue_row.get("review_input_sha256") or "")
            or str(row.get("vi_text_candidate") or "").strip() != candidate
            or not proposed
        ):
            raise Phase3ProposalApprovalError(
                f"Proposal content drift detected for {content_id}"
            )
        if recommendation == "APPROVE" and proposed != candidate:
            raise Phase3ProposalApprovalError(
                f"APPROVE changed the candidate for {content_id}"
            )
        if recommendation == "EDIT" and proposed == candidate:
            raise Phase3ProposalApprovalError(
                f"EDIT did not change the candidate for {content_id}"
            )
        edited += int(recommendation == "EDIT")
        approval_rows.append(
            {
                "content_id": content_id,
                "decision": recommendation,
                "review_input_sha256": queue_row.get("review_input_sha256"),
                "vi_text_approved": proposed,
                "reviewer": operator,
                "reviewed_at": approved_at,
            }
        )

    approved_payload = {
        "schema_version": "phase3_translation_approvals_v1",
        "phase2_handoff_ref": queue.get("phase2_handoff_ref"),
        "approvals": approval_rows,
    }
    _write_json_atomic(approvals_path, approved_payload)
    audit: dict[str, Any] = {
        "schema_version": "phase3_operator_approval_audit_v1",
        "status": "TRANSLATION_DECISIONS_RECORDED_RERUN_REQUIRED",
        "operator_id": operator,
        "approved_at": approved_at,
        "proposal_ref": {
            "path": proposal_file.name,
            "sha256": _sha256_file(proposal_file),
            "proposal_sha256": proposal.get("proposal_sha256"),
        },
        "review_queue_ref": {
            "path": queue_path.name,
            "sha256": _sha256_file(queue_path),
        },
        "approvals_ref": {
            "path": approvals_path.name,
            "sha256": _sha256_file(approvals_path),
        },
        "counts": {
            "objects": len(approval_rows),
            "edited": edited,
            "approved_unchanged": len(approval_rows) - edited,
        },
    }
    audit["audit_sha256"] = _sha256_json(audit)
    _write_json_atomic(root / "phase3_operator_approval_audit.json", audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.apply_phase3_review_proposal"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("proposal_json")
    parser.add_argument("--operator", default="user-authorized-via-codex")
    args = parser.parse_args()
    try:
        audit = apply_review_proposal(
            root_dir=args.artifact_root,
            proposal_path=args.proposal_json,
            operator_id=args.operator,
            approved_at=datetime.now(timezone.utc).isoformat(),
        )
        print(
            json.dumps(
                {
                    "status": audit["status"],
                    "counts": audit["counts"],
                    "audit_sha256": audit["audit_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, Phase3ProposalApprovalError) as exc:
        print(f"[PHASE3-PROPOSAL-APPROVAL][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
