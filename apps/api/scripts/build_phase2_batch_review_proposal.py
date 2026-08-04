"""Build a queue-bound multi-case Phase 2 OCR review proposal.

This is a proposal-only operation.  It never writes Phase 2 approvals or a
Phase 3 handoff, and it refuses to use existing reviewed rows as authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.build_phase2_ocr_visual_review import build_visual_review
from scripts.build_phase2_review_proposal import (
    Phase2ReviewProposalError,
    build_review_proposal,
    validate_review_proposal,
)


class Phase2BatchReviewProposalError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase2BatchReviewProposalError(f"Cannot read valid {path}") from exc
    if not isinstance(payload, dict):
        raise Phase2BatchReviewProposalError(f"{path} must contain an object")
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


def _reviewed_approval_count(case_root: Path) -> int:
    path = case_root / "phase2_approvals.json"
    if not path.is_file():
        return 0
    payload = _load_object(path)
    return sum(
        1
        for raw in list(payload.get("approvals") or [])
        if isinstance(raw, Mapping)
        and str(raw.get("decision") or "").upper()
        in {"APPROVE", "EDIT", "REJECT_UI"}
        and str(raw.get("reviewer") or "").strip()
        and str(raw.get("reviewed_at") or "").strip()
    )


def render_batch_markdown(payload: Mapping[str, Any]) -> str:
    counts = dict(payload.get("counts") or {})
    lines = [
        "# Phase 2 OCR batch review proposal",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Cases: `{counts.get('cases', 0)}`",
        f"- OCR objects: `{counts.get('objects', 0)}`",
        f"- Exact candidate confirmations: `{counts.get('proposed_approve', 0)}`",
        f"- Proposed edits: `{counts.get('proposed_edit', 0)}`",
        f"- Proposed `REJECT_UI`: `{counts.get('proposed_reject_ui', 0)}`",
        f"- Operator input required: `{counts.get('operator_input_required', 0)}`",
        f"- Batch proposal SHA-256: `{payload.get('batch_proposal_sha256')}`",
        "",
        "No decision below is approved yet. Contact sheets are navigation aids; the operator must confirm the exact crop/keyframe.",
        "",
        "## Case summary",
        "",
        "| Case | Objects | Confirm | Edit | Reject UI | Input | Proposal SHA | Review |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in list(payload.get("cases") or []):
        case_counts = dict(row.get("counts") or {})
        lines.append(
            f"| `{row.get('case_id')}` | {case_counts.get('objects', 0)} | "
            f"{case_counts.get('proposed_approve', 0)} | "
            f"{case_counts.get('proposed_edit', 0)} | "
            f"{case_counts.get('proposed_reject_ui', 0)} | "
            f"{case_counts.get('operator_input_required', 0)} | "
            f"`{row.get('proposal_sha256')}` | "
            f"[visual review]({row.get('visual_review_markdown')}) |"
        )
    lines.extend(
        [
            "",
            "## Explicit remediation recommendations",
            "",
            "Rows not listed here still require exact confirmation of the current OCR candidate.",
            "",
            "| Case | Object | Decision | Proposed text | Confidence | Reason |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in list(payload.get("explicit_recommendations") or []):
        proposed = json.dumps(
            str(row.get("ocr_text_suggested") or ""), ensure_ascii=False
        ).replace("|", "\\|")
        reason = str(row.get("reason") or "").replace("|", "\\|")
        lines.append(
            f"| `{row.get('case_id')}` | `{row.get('content_id')}` | "
            f"`{row.get('decision') or ''}` | `{proposed}` | "
            f"`{row.get('confidence') or ''}` | {reason} |"
        )
    return "\n".join(lines) + "\n"


def render_review_index(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Phase 2 OCR review index",
        "",
        "Current canonical review pack: [PHASE2_BATCH_REVIEW_PROPOSAL.md](PHASE2_BATCH_REVIEW_PROPOSAL.md).",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Batch proposal SHA-256: `{payload.get('batch_proposal_sha256')}`",
        "",
        "| Case | Proposal SHA-256 | Visual review |",
        "|---|---|---|",
    ]
    for row in list(payload.get("cases") or []):
        lines.append(
            f"| `{row.get('case_id')}` | `{row.get('proposal_sha256')}` | "
            f"[open]({row.get('visual_review_markdown')}) |"
        )
    return "\n".join(lines) + "\n"


def build_batch_review_proposal(
    *,
    run_root: Path,
    recommendations_path: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    manifest = _load_object(recommendations_path)
    if str(manifest.get("schema_version") or "") != (
        "phase2_batch_review_recommendations_v1"
    ):
        raise Phase2BatchReviewProposalError("Unsupported recommendation schema")
    state_ref = dict(manifest.get("batch_state_ref") or {})
    state_path = run_root / str(state_ref.get("path") or "batch_regression_state.json")
    if not state_path.is_file() or str(state_ref.get("sha256") or "") != _sha256_file(
        state_path
    ):
        raise Phase2BatchReviewProposalError("Batch state reference is stale")
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, Mapping) or not raw_cases:
        raise Phase2BatchReviewProposalError("Recommendation manifest has no cases")

    case_rows: list[dict[str, Any]] = []
    explicit_rows: list[dict[str, Any]] = []
    total_counts = {
        "cases": 0,
        "objects": 0,
        "proposed_approve": 0,
        "proposed_edit": 0,
        "proposed_reject_ui": 0,
        "operator_input_required": 0,
        "transition_merge_groups": 0,
    }
    for case_id in sorted(str(value) for value in raw_cases):
        case_config = raw_cases.get(case_id)
        if not isinstance(case_config, Mapping):
            raise Phase2BatchReviewProposalError(
                f"Invalid recommendation case: {case_id}"
            )
        case_root = (run_root / case_id).resolve()
        if not case_root.is_relative_to(run_root) or not case_root.is_dir():
            raise Phase2BatchReviewProposalError(f"Unknown case root: {case_id}")
        if _reviewed_approval_count(case_root):
            raise Phase2BatchReviewProposalError(
                f"Reviewed Phase 2 authority already exists for {case_id}"
            )
        queue_path = case_root / "phase2_review_queue.json"
        expected_queue_sha = str(case_config.get("review_queue_sha256") or "")
        if not queue_path.is_file() or expected_queue_sha != _sha256_file(queue_path):
            raise Phase2BatchReviewProposalError(
                f"Review queue reference is stale for {case_id}"
            )
        recommendations = case_config.get("recommendations") or {}
        if not isinstance(recommendations, Mapping):
            raise Phase2BatchReviewProposalError(
                f"Recommendations must be an object for {case_id}"
            )
        try:
            proposal = build_review_proposal(
                target_root=case_root,
                reference_root=case_root,
                suggestions=recommendations,
                generated_at=generated_at,
            )
            validate_review_proposal(target_root=case_root, proposal=proposal)
        except Phase2ReviewProposalError as exc:
            raise Phase2BatchReviewProposalError(
                f"Cannot build proposal for {case_id}: {exc}"
            ) from exc
        proposal_path = case_root / "phase2_review_proposal.json"
        _write_json_atomic(proposal_path, proposal)
        visual = build_visual_review(case_root)
        counts = dict(proposal.get("counts") or {})
        case_rows.append(
            {
                "case_id": case_id,
                "review_queue_sha256": expected_queue_sha,
                "proposal_path": f"{case_id}/phase2_review_proposal.json",
                "proposal_file_sha256": _sha256_file(proposal_path),
                "proposal_sha256": proposal.get("proposal_sha256"),
                "visual_review_path": f"{case_id}/phase2_ocr_visual_review.json",
                "visual_review_sha256": visual.get("visual_review_sha256"),
                "visual_review_markdown": f"{case_id}/PHASE2_OCR_VISUAL_REVIEW.md",
                "counts": counts,
            }
        )
        total_counts["cases"] += 1
        for key in total_counts:
            if key == "cases":
                continue
            total_counts[key] += int(counts.get(key) or 0)
        proposal_by_id = {
            str(row.get("content_id") or ""): dict(row)
            for row in list(proposal.get("proposals") or [])
            if isinstance(row, Mapping)
        }
        for content_id in recommendations:
            row = proposal_by_id[str(content_id)]
            explicit_rows.append(
                {
                    "case_id": case_id,
                    "content_id": content_id,
                    "decision": row.get("proposed_decision"),
                    "ocr_text_suggested": row.get("ocr_text_suggested"),
                    "confidence": row.get("recommendation_confidence"),
                    "reason": row.get("recommendation_reason"),
                    "evidence": list(row.get("recommendation_evidence") or []),
                    "review_input_sha256": row.get("review_input_sha256"),
                }
            )

    payload: dict[str, Any] = {
        "schema_version": "phase2_batch_review_proposal_v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "status": (
            "OPERATOR_INPUT_REQUIRED"
            if total_counts["operator_input_required"]
            else "OPERATOR_APPROVAL_REQUIRED"
        ),
        "non_authoritative": True,
        "batch_state_ref": {
            "path": state_path.name,
            "sha256": _sha256_file(state_path),
        },
        "recommendations_ref": {
            "path": recommendations_path.name,
            "sha256": _sha256_file(recommendations_path),
        },
        "counts": total_counts,
        "cases": case_rows,
        "explicit_recommendations": explicit_rows,
        "operator_decision": None,
    }
    payload["batch_proposal_sha256"] = _sha256_json(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    parser.add_argument("recommendations_json")
    parser.add_argument("--output")
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    output = (
        Path(args.output).resolve()
        if args.output
        else run_root / "phase2_batch_review_proposal.json"
    )
    result = build_batch_review_proposal(
        run_root=run_root,
        recommendations_path=Path(args.recommendations_json).resolve(),
    )
    _write_json_atomic(output, result)
    _write_text_atomic(
        run_root / "PHASE2_BATCH_REVIEW_PROPOSAL.md",
        render_batch_markdown(result),
    )
    _write_text_atomic(
        run_root / "PHASE2_OCR_REVIEW_INDEX.md",
        render_review_index(result),
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "counts": result["counts"],
                "batch_proposal_sha256": result["batch_proposal_sha256"],
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
