"""Build a hash-bound, proposal-only Phase 3 review index for a batch run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class Phase3BatchReviewIndexError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase3BatchReviewIndexError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise Phase3BatchReviewIndexError(f"{path.name} must contain an object")
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


def _write_text_atomic(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def approval_token(payload: Mapping[str, Any], release_label: str | None = None) -> str:
    digest = str(payload.get("batch_review_sha256") or "")
    if len(digest) != 64:
        raise Phase3BatchReviewIndexError("Batch review SHA-256 is missing")
    normalized = str(
        release_label or payload.get("release_label") or "V22_1"
    ).replace(".", "_").replace("-", "_")
    return f"TRANSLATION_PROPOSALS_APPROVED_{normalized}_{digest[:12].upper()}"


def render_batch_markdown(
    payload: Mapping[str, Any], release_label: str = "V22_1"
) -> str:
    counts = dict(payload.get("counts") or {})
    lines = [
        f"# Phase 3 {release_label} Translation Review",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Cases: `{counts.get('cases', 0)}`",
        f"- Review objects: `{counts.get('review_objects', 0)}`",
        f"- Recommended unchanged approvals: `{counts.get('recommended_approvals', 0)}`",
        f"- Recommended edits: `{counts.get('recommended_edits', 0)}`",
        f"- Translation failures: `{counts.get('translation_failures', 0)}`",
        f"- Candidate quality flags: `{counts.get('candidate_quality_flags', 0)}`",
        f"- Operator approval written: `{str(bool(payload.get('operator_approval_written'))).lower()}`",
        f"- Batch review SHA-256: `{payload.get('batch_review_sha256')}`",
        "",
        "## Case proposals",
        "",
        "| Case | Objects | Approve | Edit | Flags | Proposal SHA-256 | Review |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for row in list(payload.get("cases") or []):
        summary = dict(row.get("summary") or {})
        lines.append(
            f"| `{row.get('case_id')}` | {summary.get('review_objects', 0)} | "
            f"{summary.get('recommended_approvals', 0)} | "
            f"{summary.get('recommended_edits', 0)} | "
            f"{summary.get('candidate_quality_flags', 0)} | "
            f"`{row.get('proposal_sha256')}` | "
            f"[open]({row.get('proposal_markdown_path')}) |"
        )
    lines.extend(
        [
            "",
            "## Approval token",
            "",
            f"`{approval_token(payload, release_label)}`",
            "",
            "This token approves the complete hash-bound proposal set only. No translation decision, Phase 3 closeout, TTS, render, export, or publish action has been written.",
            "",
        ]
    )
    return "\n".join(lines)


def build_batch_review_index(
    *, run_root: str | Path, generated_at: str | None = None,
    release_label: str = "V22_1"
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    state_path = run / "batch_regression_state.json"
    state = _load_object(state_path)
    state_cases = [
        dict(row)
        for row in list(state.get("cases") or [])
        if isinstance(row, Mapping)
    ]
    if not state_cases:
        raise Phase3BatchReviewIndexError("Batch state has no cases")

    case_rows: list[dict[str, Any]] = []
    proposal_times: list[str] = []
    totals = {
        "cases": 0,
        "review_objects": 0,
        "recommended_edits": 0,
        "recommended_approvals": 0,
        "translation_failures": 0,
        "candidate_quality_flags": 0,
    }
    for state_case in sorted(
        state_cases, key=lambda row: str(row.get("case_id") or "")
    ):
        case_id = str(state_case.get("case_id") or "").strip()
        state_status = str(state_case.get("status") or "")
        if state_status == "NO_TEXT_OPERATOR_APPROVED":
            continue
        if (
            not case_id
            or state_status != "WAITING_TRANSLATION_OPERATOR_REVIEW"
        ):
            raise Phase3BatchReviewIndexError(
                "Case is not waiting at the translation operator gate: "
                f"{case_id or 'unknown'}"
            )
        case_root = (run / case_id).resolve()
        if not case_root.is_relative_to(run) or not case_root.is_dir():
            raise Phase3BatchReviewIndexError(f"Invalid case root: {case_id}")

        queue_path = case_root / "phase3_review_queue.json"
        proposal_path = case_root / "phase3_review_proposal.json"
        approvals_path = case_root / "phase3_approvals.json"
        queue = _load_object(queue_path)
        proposal = _load_object(proposal_path)
        approvals = _load_object(approvals_path)
        if not _verify_self_hash(proposal, "proposal_sha256"):
            raise Phase3BatchReviewIndexError(
                f"Invalid proposal self-hash for {case_id}"
            )
        if (
            str(proposal.get("status") or "")
            != "PROPOSAL_READY_FOR_OPERATOR_REVIEW"
            or bool(proposal.get("operator_approval_written"))
        ):
            raise Phase3BatchReviewIndexError(
                f"Proposal is not an unapproved review artifact for {case_id}"
            )
        queue_ref = dict(proposal.get("phase3_review_queue_ref") or {})
        if str(queue_ref.get("sha256") or "") != _sha256_file(queue_path):
            raise Phase3BatchReviewIndexError(f"Stale proposal for {case_id}")
        if dict(proposal.get("phase2_handoff_ref") or {}) != dict(
            queue.get("phase2_handoff_ref") or {}
        ):
            raise Phase3BatchReviewIndexError(
                f"Phase 2 authority mismatch for {case_id}"
            )

        queue_ids = {
            str(row.get("content_id") or "")
            for row in list(queue.get("content_objects") or [])
            if isinstance(row, Mapping)
        }
        proposal_ids = {
            str(row.get("content_id") or "")
            for row in list(proposal.get("proposals") or [])
            if isinstance(row, Mapping)
        }
        if not queue_ids or "" in queue_ids or queue_ids != proposal_ids:
            raise Phase3BatchReviewIndexError(
                f"Proposal does not cover the queue exactly for {case_id}"
            )
        decided = [
            row
            for row in list(approvals.get("approvals") or [])
            if isinstance(row, Mapping)
            and (
                str(row.get("decision") or "").strip()
                or str(row.get("reviewer") or "").strip()
                or str(row.get("reviewed_at") or "").strip()
            )
        ]
        if decided:
            raise Phase3BatchReviewIndexError(
                f"Operator translation decisions already exist for {case_id}"
            )

        summary = dict(proposal.get("summary") or {})
        failed = int(dict(queue.get("review_summary") or {}).get("failed") or 0)
        case_summary = {
            "review_objects": int(summary.get("review_objects") or 0),
            "recommended_edits": int(summary.get("recommended_edits") or 0),
            "recommended_approvals": int(
                summary.get("recommended_approvals") or 0
            ),
            "translation_failures": failed,
            "candidate_quality_flags": int(
                summary.get("candidate_quality_flags") or 0
            ),
        }
        if case_summary["review_objects"] != len(queue_ids):
            raise Phase3BatchReviewIndexError(
                f"Review object count mismatch for {case_id}"
            )
        for key in case_summary:
            totals[key] += case_summary[key]
        totals["cases"] += 1
        proposal_times.append(str(proposal.get("created_at") or ""))
        case_rows.append(
            {
                "case_id": case_id,
                "status": state_case.get("status"),
                "phase3_review_queue_ref": {
                    "path": f"{case_id}/{queue_path.name}",
                    "sha256": _sha256_file(queue_path),
                },
                "proposal_path": f"{case_id}/{proposal_path.name}",
                "proposal_markdown_path": f"{case_id}/phase3_review_proposal.md",
                "proposal_file_sha256": _sha256_file(proposal_path),
                "proposal_sha256": proposal.get("proposal_sha256"),
                "summary": case_summary,
            }
        )

    payload: dict[str, Any] = {
        "schema_version": "phase3_batch_review_index_v1",
        "status": (
            "TRANSLATION_PROPOSAL_BLOCKED"
            if totals["translation_failures"]
            else "TRANSLATION_OPERATOR_REVIEW_REQUIRED"
        ),
        "operator_approval_written": False,
        "release_label": release_label,
        "generated_at": generated_at or max(proposal_times),
        "batch_state_ref": {
            "path": state_path.name,
            "sha256": _sha256_file(state_path),
            "run_sha256": state.get("run_sha256"),
        },
        "counts": totals,
        "cases": case_rows,
    }
    payload["batch_review_sha256"] = _sha256_json(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase3_batch_review_index"
    )
    parser.add_argument("run_root")
    parser.add_argument("--release-label", default="V22_1")
    args = parser.parse_args()
    try:
        run = Path(args.run_root).resolve()
        payload = build_batch_review_index(
            run_root=run, release_label=args.release_label
        )
        output = run / "phase3_batch_review_index.json"
        markdown = run / f"PHASE3_{args.release_label}_OPERATOR_REVIEW_INDEX.md"
        _write_json_atomic(output, payload)
        _write_text_atomic(markdown, render_batch_markdown(payload, args.release_label))
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "counts": payload["counts"],
                    "batch_review_sha256": payload["batch_review_sha256"],
                    "approval_token": approval_token(payload, args.release_label),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, Phase3BatchReviewIndexError) as exc:
        print(f"[PHASE3-BATCH-REVIEW][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
