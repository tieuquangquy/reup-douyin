"""Materialize an explicitly approved Phase 2 proposal into decisions.

This script does not infer approval.  The caller must provide the exact
proposal SHA-256 shown to the operator, plus reviewer identity.
"""

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


class Phase2ProposalMaterializationError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase2ProposalMaterializationError(
            f"Cannot read valid {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise Phase2ProposalMaterializationError(f"{path} must contain an object")
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


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def materialize_approved_proposal(
    *,
    target_root: Path,
    proposal_path: Path,
    approved_proposal_sha256: str,
    reviewer: str,
    reviewed_at: str,
) -> dict[str, Any]:
    proposal = _load_object(proposal_path)
    try:
        validate_review_proposal(target_root=target_root, proposal=proposal)
    except Phase2ReviewProposalError as exc:
        raise Phase2ProposalMaterializationError(str(exc)) from exc
    claimed = str(proposal.get("proposal_sha256") or "")
    if approved_proposal_sha256 != claimed:
        raise Phase2ProposalMaterializationError(
            "Operator-approved proposal SHA-256 does not match"
        )
    reviewer = str(reviewer or "").strip()
    reviewed_at = str(reviewed_at or "").strip()
    if not reviewer or not reviewed_at:
        raise Phase2ProposalMaterializationError(
            "Reviewer and reviewed_at are required"
        )
    decisions: list[dict[str, Any]] = []
    for raw in list(proposal.get("proposals") or []):
        if not isinstance(raw, Mapping):
            continue
        content_id = str(raw.get("content_id") or "").strip()
        approved_text = str(raw.get("ocr_text_suggested") or "").strip()
        decision = str(raw.get("proposed_decision") or "").upper()
        if (
            not content_id
            or decision not in {"APPROVE", "EDIT", "REJECT_UI"}
            or (decision != "REJECT_UI" and not approved_text)
        ):
            raise Phase2ProposalMaterializationError(
                f"Proposal row is not materializable: {content_id or '(empty)'}"
            )
        decisions.append(
            {
                "content_id": content_id,
                "decision": decision,
                "ocr_text_approved": approved_text or None,
                "vi_text_approved": None,
            }
        )
    payload: dict[str, Any] = {
        "schema_version": "phase2_review_decisions_v1",
        "review_queue_sha256": str(
            dict(proposal.get("review_queue_ref") or {}).get("sha256") or ""
        ),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "approved_proposal_ref": {
            "path": proposal_path.name,
            "file_sha256": _sha256_file(proposal_path),
            "proposal_sha256": claimed,
        },
        "decisions": decisions,
    }
    payload["decisions_sha256"] = _sha256_json(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target_root")
    parser.add_argument("proposal_json")
    parser.add_argument("--approve-proposal-sha", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    target = Path(args.target_root).resolve()
    proposal_path = Path(args.proposal_json).resolve()
    payload = materialize_approved_proposal(
        target_root=target,
        proposal_path=proposal_path,
        approved_proposal_sha256=str(args.approve_proposal_sha),
        reviewer=str(args.reviewer),
        reviewed_at=datetime.now(timezone.utc).isoformat(),
    )
    output = (
        Path(args.output).resolve()
        if args.output
        else target / "phase2_review_decisions_from_approved_proposal.json"
    )
    _write_json_atomic(output, payload)
    print(
        json.dumps(
            {
                "output": str(output),
                "objects": len(payload["decisions"]),
                "edited": sum(
                    row["decision"] == "EDIT" for row in payload["decisions"]
                ),
                "rejected_ui": sum(
                    row["decision"] == "REJECT_UI" for row in payload["decisions"]
                ),
                "decisions_sha256": payload["decisions_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
