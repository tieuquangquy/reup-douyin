"""Build a consolidated, suggestion-only Phase-4 remediation proposal.

The artifact turns visual-failure triage into explicit operator decisions.  It
does not relax QA thresholds, mutate a timeline, or rerun rendering.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "phase4_visual_remediation_proposal_v1"


class Phase4RemediationProposalError(RuntimeError):
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
        raise Phase4RemediationProposalError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise Phase4RemediationProposalError(f"{path.name} must contain an object")
    return payload


def _ref(root: Path, path: Path) -> dict[str, Any]:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise Phase4RemediationProposalError(
            f"Evidence path escapes run root: {path}"
        ) from exc
    if not path.is_file():
        raise Phase4RemediationProposalError(f"Missing evidence: {relative}")
    return {"path": relative, "sha256": _sha256_file(path)}


def _latest_residual_attempt(
    case_root: Path,
) -> tuple[Path, dict[str, Any]] | None:
    attempts = sorted(case_root.glob("phase2_residual_remediation_proposal*_attempt.json"))
    if not attempts:
        return None
    path = attempts[-1]
    return path, _load_object(path)


def _mask_action(row: Mapping[str, Any]) -> dict[str, Any]:
    recommendation = str(row.get("recommendation") or "")
    duplicate = dict(row.get("duplicate_output_residual_track") or {})
    duplicate_group = dict(
        row.get("duplicate_output_residual_track_group") or {}
    )
    if recommendation == "CANDIDATE_DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK_GROUP":
        action = "DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK_GROUP"
        guard = (
            "keep the geometry-aligned canonical track; drop every listed "
            "operator-approved track only when source, translation, active "
            "span, and at least 0.70 geometry overlap still match"
        )
    elif recommendation == "CANDIDATE_DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK":
        action = "DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK"
        guard = (
            "drop only the failed p4out track when another operator-approved "
            "track has the same source/translation, active span, and at least "
            "0.70 geometry overlap; do not alter damage thresholds"
        )
    elif str(dict(row.get("diagnostics") or {}).get("status") or "") == "PASS":
        context = dict(
            dict(dict(row.get("track") or {}).get("render_policy") or {}).get(
                "context"
            )
            or {}
        )
        if (
            str(row.get("text_id") or "").startswith("p4out_")
            and bool(context.get("output_residual_geometry_aligned"))
            and bool(context.get("output_residual_width_expanded"))
        ):
            action = "BOUNDED_EXACT_RESIDUAL_STYLIZED_COMPONENT_MASK"
            guard = (
                "use stylized component detection only after operator-approved "
                "geometry alignment and exact-signature width expansion; keep "
                "the ROI and damage thresholds unchanged"
            )
        elif str(row.get("text_id") or "").startswith("p4out_"):
            action = "TRIM_OUTPUT_RESIDUAL_TRACK_BEFORE_CONFIRMED_SOURCE_CHANGE"
            guard = (
                "the failed frame is operator-confirmed as a different source "
                "item; trim only the p4out track to the preceding frame and do "
                "not relax mask thresholds"
            )
        else:
            action = "SPLIT_TRACK_TO_SOURCE_VISIBLE_INTERVALS_AND_SCOPE_MASK_CACHE"
            guard = (
                "isolated frame diagnostic passes; verify text presence across the "
                "window, split blank intervals, and do not relax mask thresholds"
            )
    elif recommendation == "CANDIDATE_DYNAMIC_MASK_OR_CAPTION_PANEL_FALLBACK":
        action = "CAPTION_PANEL_FALLBACK_WITH_EXISTING_DAMAGE_BUDGET"
        guard = (
            "candidate_only; preserve mask density and frame-damage limits; "
            "rerender preview then require Output QA"
        )
    elif recommendation == "REVIEW_DROP_OR_EXPLICIT_COVER_ONLY_AUTHORITY":
        action = "DROP_EMPTY_CONTENT_TRACK"
        guard = (
            "drop only because text/content are empty and no explicit cover-only "
            "authority exists; never infer cover-only authority"
        )
    elif recommendation == "REVIEW_TRACK_TIMING_GEOMETRY_OR_REFERENCE_PLATE":
        action = "CONFIRM_TIMING_THEN_TIGHT_ROI_REFERENCE_PLATE_FALLBACK"
        guard = (
            "confirm source-visible frames first, keep the ROI bounded, and do "
            "not relax mask thresholds"
        )
    elif recommendation == "CANDIDATE_BOUNDED_MICRO_UI_SPATIAL_FALLBACK":
        action = "BOUNDED_MICRO_UI_SPATIAL_FALLBACK_WITH_EXISTING_DAMAGE_BUDGET"
        guard = (
            "disable the unalignable reference plate only for the approved "
            "micro-UI ROI; retain the existing frame-damage budget and require "
            "encoded Output QA"
        )
    else:
        action = "MASK_POLICY_REVIEW_REQUIRED"
        guard = "fail-closed until operator supplies a bounded policy"
    return {
        "action": action,
        "recommendation": recommendation,
        "guard": guard,
        "automatic_apply": False,
        "rerender_after_approval": True,
        **(
            {
                "duplicate_track_id": duplicate.get("text_id"),
                "duplicate_geometry_overlap_over_smaller": duplicate.get(
                    "geometry_overlap_over_smaller"
                ),
            }
            if action == "DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK"
            else {}
        ),
        **(
            {
                "canonical_track_id": duplicate_group.get(
                    "canonical_track_id"
                ),
                "drop_track_ids": list(
                    duplicate_group.get("drop_track_ids") or []
                ),
            }
            if action == "DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK_GROUP"
            else {}
        ),
    }


def _output_qa_action(row: Mapping[str, Any], case_root: Path) -> dict[str, Any]:
    attempt_result = _latest_residual_attempt(case_root)
    attempt_path, attempt = attempt_result or (None, None)
    reason = str(dict(attempt or {}).get("reason") or "")
    if "matches existing Phase-1 geometry" in reason:
        action = "UPSTREAM_PHASE1_TIMING_SPLIT_THEN_ADD_RESIDUAL_OCCURRENCE"
        guard = (
            "do not add an overlapping occurrence; first review the existing "
            "Phase-1 boundary and preserve master_timeline immutability"
        )
    else:
        action = "UPSTREAM_RESIDUAL_GEOMETRY_REMEDIATION_THEN_RERENDER"
        guard = "resolve OCR coverage/geometry first; rerun Output QA afterward"
    result = {
        "action": action,
        "recommendation": str(row.get("recommendation") or ""),
        "guard": guard,
        "automatic_apply": False,
        "rerender_after_approval": True,
        "residual_count": int(
            dict(row.get("output_qa") or {}).get("blocking_residual_cjk_count") or 0
        ),
        "residual_texts": sorted(
            {
                str(item.get("text") or "")
                for item in list(dict(row.get("output_qa") or {}).get("blocking_residual_cjk") or [])
                if isinstance(item, Mapping) and str(item.get("text") or "")
            }
        ),
    }
    if attempt is not None:
        result["residual_proposal_attempt"] = {
            "path": attempt_path.name if attempt_path else "",
            "status": attempt.get("status"),
            "reason": reason,
            "attempt_sha256": attempt.get("attempt_sha256"),
        }
    return result


def build_proposal(
    run_root: str | Path,
    *,
    triage_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    triage_file = (
        Path(triage_path).resolve()
        if triage_path is not None
        else root / "phase4_visual_failure_triage_v22_4.json"
    )
    state_path = root / "batch_regression_state.json"
    if not triage_file.is_file() or not state_path.is_file():
        raise Phase4RemediationProposalError(
            "Missing Phase-4 triage or batch state authority"
        )
    triage = _load_object(triage_file)
    state = _load_object(state_path)
    if str(triage.get("status") or "") != "REMEDIATION_PROPOSAL_REQUIRED":
        raise Phase4RemediationProposalError("Phase-4 triage is not proposal-ready")
    rows: list[dict[str, Any]] = []
    state_by_case = {
        str(item.get("case_id") or ""): dict(item)
        for item in list(state.get("cases") or [])
        if isinstance(item, Mapping)
    }
    for raw in list(triage.get("cases") or []):
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        case_id = str(row.get("case_id") or "")
        case_root = root / case_id
        if case_id not in state_by_case or not case_root.is_dir():
            raise Phase4RemediationProposalError(
                f"Triage case is missing from batch state: {case_id}"
            )
        failure_class = str(row.get("failure_class") or "")
        if failure_class in {
            "MASK_QUALITY_BLOCKED",
            "REFERENCE_PLATE_ALIGNMENT_BLOCKED",
        }:
            decision = _mask_action(row)
        elif failure_class == "ENCODED_OUTPUT_QA_FAILED":
            decision = _output_qa_action(row, case_root)
        else:
            raise Phase4RemediationProposalError(
                f"Unsupported Phase-4 failure class: {failure_class}"
            )
        evidence: dict[str, Any] = {}
        for key, value in dict(row.get("evidence") or {}).items():
            if not isinstance(value, Mapping):
                continue
            path = root / str(value.get("path") or "")
            evidence[key] = _ref(root, path)
        log_ref = dict(row.get("log_ref") or {})
        if log_ref:
            evidence["log"] = _ref(root, root / str(log_ref.get("path") or ""))
        rows.append(
            {
                "case_id": case_id,
                "failure_class": failure_class,
                "text_id": row.get("text_id"),
                "frame_index": row.get("frame_index"),
                "failed_checks": list(row.get("failed_checks") or []),
                "decision": decision,
                "evidence": evidence,
            }
        )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PROPOSAL_READY_FOR_OPERATOR_REVIEW",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_approval_written": False,
        "automatic_policy_changes_applied": False,
        "authority_refs": {
            "batch_state": _ref(root, state_path),
            "visual_failure_triage": _ref(root, triage_file),
        },
        "counts": {
            "cases": len(rows),
            "mask_quality_cases": sum(
                row["failure_class"]
                in {"MASK_QUALITY_BLOCKED", "REFERENCE_PLATE_ALIGNMENT_BLOCKED"}
                for row in rows
            ),
            "reference_plate_alignment_cases": sum(
                row["failure_class"] == "REFERENCE_PLATE_ALIGNMENT_BLOCKED"
                for row in rows
            ),
            "encoded_output_qa_cases": sum(
                row["failure_class"] == "ENCODED_OUTPUT_QA_FAILED" for row in rows
            ),
        },
        "decisions": rows,
        "non_goals": [
            "do_not_relax_mask_or_output_qa_thresholds",
            "do_not_overwrite_master_timeline",
            "do_not_apply_policy_without_operator_approval",
            "do_not_claim_visual_or_final_approval",
        ],
    }
    payload["proposal_sha256"] = _sha256_json(payload)
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    version = path.stem.removeprefix("phase4_remediation_proposal_")
    version_label = version.replace("_", ".").upper()
    lines = [
        f"# Phase 4 Visual Remediation Proposal {version_label}",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Proposal SHA-256: `{payload.get('proposal_sha256')}`",
        "- Automatic policy changes applied: `false`",
        "",
        "| Case | Failure | Track/Frame | Proposed decision | Guard | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for row in list(payload.get("decisions") or []):
        decision = dict(row.get("decision") or {})
        evidence = dict(row.get("evidence") or {})
        first = next(iter(evidence.values()), {})
        evidence_path = str(dict(first).get("path") or "-")
        lines.append(
            f"| `{row.get('case_id')}` | `{row.get('failure_class')}` | "
            f"`{row.get('text_id') or '-'}/{row.get('frame_index') or '-'}` | "
            f"`{decision.get('action')}` | {decision.get('guard')} | `{evidence_path}` |"
        )
    lines.extend(
        [
            "",
            "Proposal này chỉ là decision artifact; mọi thay đổi cần operator duyệt "
            "và rerun preview + Output QA.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase4_remediation_proposal"
    )
    parser.add_argument("run_root")
    parser.add_argument("--output-stem", default="phase4_remediation_proposal_v22_4")
    parser.add_argument("--triage-path")
    args = parser.parse_args()
    try:
        root = Path(args.run_root).resolve()
        stem = str(args.output_stem or "").strip()
        if not stem or Path(stem).name != stem:
            raise Phase4RemediationProposalError("Invalid output stem")
        payload = build_proposal(root, triage_path=args.triage_path)
        json_path = root / f"{stem}.json"
        markdown_path = root / f"{stem}.md"
        _write_json(json_path, payload)
        _write_markdown(markdown_path, payload)
    except (OSError, ValueError, Phase4RemediationProposalError) as exc:
        print(f"[PHASE4-REMEDIATION-PROPOSAL][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "counts": payload["counts"],
                "proposal_sha256": payload["proposal_sha256"],
                "json": str(json_path),
                "markdown": str(markdown_path),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
