"""Build a hash-bound Phase 3 language-review proposal without approving it."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.media_pipeline.ocr_filtering.script_filter import contains_cjk
from src.media_pipeline.translator.phase3_contract import (
    _approval_preserves_protected_tokens,
)


class Phase3ReviewProposalError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase3ReviewProposalError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise Phase3ReviewProposalError(f"{path.name} must contain an object")
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


def _write_text_atomic(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def render_review_proposal_markdown(proposal: Mapping[str, Any]) -> str:
    summary = dict(proposal.get("summary") or {})
    lines = [
        "# Phase 3 Translation Review Proposal",
        "",
        f"- Status: `{proposal.get('status')}`",
        f"- Review objects: `{summary.get('review_objects', 0)}`",
        f"- Recommended edits: `{summary.get('recommended_edits', 0)}`",
        f"- Recommended unchanged approvals: `{summary.get('recommended_approvals', 0)}`",
        f"- Operator approval written: `{str(bool(proposal.get('operator_approval_written'))).lower()}`",
        f"- Proposal SHA-256: `{proposal.get('proposal_sha256')}`",
        "",
        "| content_id | Chinese authority | Current candidate | Proposed Vietnamese | Reasons |",
        "|---|---|---|---|---|",
    ]

    def cell(value: Any) -> str:
        return str(value or "").replace("|", "\\|").replace("\n", " ")

    for row in list(proposal.get("proposals") or []):
        if not isinstance(row, Mapping) or row.get("recommendation") != "EDIT":
            continue
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    row.get("content_id"),
                    row.get("zh_approved"),
                    row.get("vi_text_candidate"),
                    row.get("vi_text_proposed"),
                    ", ".join(str(reason) for reason in row.get("reasons") or []),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "This file is a language-review proposal only. It does not authorize Phase 3 or Phase 4.",
            "",
        ]
    )
    return "\n".join(lines)


def _normalize_edits(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw_edits = payload.get("edits", payload)
    if not isinstance(raw_edits, Mapping):
        raise Phase3ReviewProposalError("edits must be an object")
    edits: dict[str, dict[str, Any]] = {}
    for raw_id, raw_value in raw_edits.items():
        content_id = str(raw_id or "").strip()
        if not content_id or not isinstance(raw_value, Mapping):
            raise Phase3ReviewProposalError("Each edit must be an object")
        proposed = str(raw_value.get("vi_text") or "").strip()
        if not proposed:
            raise Phase3ReviewProposalError(f"Missing vi_text for {content_id}")
        reasons = [
            str(value).strip()
            for value in list(raw_value.get("reasons") or [])
            if str(value).strip()
        ]
        edits[content_id] = {"vi_text": proposed, "reasons": reasons}
    return edits


def build_review_proposal(
    *,
    root_dir: str | Path,
    edits: Mapping[str, Mapping[str, Any]],
    proposal_author: str,
    created_at: str,
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    queue_path = root / "phase3_review_queue.json"
    queue = _load_object(queue_path)
    rows = [
        dict(row)
        for row in list(queue.get("content_objects") or [])
        if isinstance(row, Mapping)
    ]
    if not rows:
        raise Phase3ReviewProposalError("Phase 3 review queue is empty")
    by_id = {str(row.get("content_id") or ""): row for row in rows}
    if len(by_id) != len(rows) or "" in by_id:
        raise Phase3ReviewProposalError("Review queue content_id set is invalid")
    unknown = sorted(set(edits) - set(by_id))
    if unknown:
        raise Phase3ReviewProposalError(f"Unknown edit content_id values: {unknown}")

    proposal_rows: list[dict[str, Any]] = []
    edit_count = 0
    for row in rows:
        content_id = str(row["content_id"])
        candidate = str(row.get("vi_text_candidate") or "").strip()
        review_hash = str(row.get("review_input_sha256") or "").strip()
        if not candidate or len(review_hash) != 64:
            raise Phase3ReviewProposalError(
                f"Candidate/hash missing for {content_id}"
            )
        edit = dict(edits.get(content_id) or {})
        proposed = str(edit.get("vi_text") or candidate).strip()
        if not proposed or contains_cjk(proposed):
            raise Phase3ReviewProposalError(
                f"Proposed Vietnamese text is invalid for {content_id}"
            )
        if not _approval_preserves_protected_tokens(
            row, candidate=candidate, approved=proposed
        ):
            raise Phase3ReviewProposalError(
                f"Protected number/unit mismatch for {content_id}"
            )
        recommendation = "EDIT" if proposed != candidate else "APPROVE"
        edit_count += int(recommendation == "EDIT")
        proposal_rows.append(
            {
                "content_id": content_id,
                "recommendation": recommendation,
                "review_input_sha256": review_hash,
                "zh_approved": row.get("zh_approved"),
                "roles": list(row.get("roles") or []),
                "vi_text_candidate": candidate,
                "vi_text_proposed": proposed,
                "reasons": list(edit.get("reasons") or []),
                "candidate_quality_flags": list(row.get("quality_flags") or []),
            }
        )

    proposal: dict[str, Any] = {
        "schema_version": "phase3_translation_review_proposal_v1",
        "status": "PROPOSAL_READY_FOR_OPERATOR_REVIEW",
        "operator_approval_written": False,
        "proposal_author": str(proposal_author or "").strip(),
        "created_at": created_at,
        "phase2_handoff_ref": queue.get("phase2_handoff_ref"),
        "phase3_review_queue_ref": {
            "path": queue_path.name,
            "sha256": _sha256_file(queue_path),
        },
        "summary": {
            "review_objects": len(proposal_rows),
            "recommended_edits": edit_count,
            "recommended_approvals": len(proposal_rows) - edit_count,
            "candidate_quality_flags": sum(
                len(row["candidate_quality_flags"]) for row in proposal_rows
            ),
        },
        "proposals": proposal_rows,
    }
    if not proposal["proposal_author"]:
        raise Phase3ReviewProposalError("proposal_author is required")
    proposal["proposal_sha256"] = _sha256_json(proposal)
    return proposal


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase3_review_proposal"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("edits_json")
    parser.add_argument("--author", default="codex-assisted-language-review")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        root = Path(args.artifact_root).resolve()
        edits = _normalize_edits(_load_object(Path(args.edits_json).resolve()))
        proposal = build_review_proposal(
            root_dir=root,
            edits=edits,
            proposal_author=args.author,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        output = (
            Path(args.output).resolve()
            if args.output
            else root / "phase3_review_proposal.json"
        )
        _write_json_atomic(output, proposal)
        markdown_output = output.with_suffix(".md")
        _write_text_atomic(
            markdown_output, render_review_proposal_markdown(proposal)
        )
        print(
            json.dumps(
                {
                    "output": str(output),
                    "markdown": str(markdown_output),
                    "status": proposal["status"],
                    "summary": proposal["summary"],
                    "proposal_sha256": proposal["proposal_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, Phase3ReviewProposalError) as exc:
        print(f"[PHASE3-REVIEW-PROPOSAL][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
