"""Build a hash-bound batch index for Phase 4 preflight blockers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class Phase4BatchPreflightIndexError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4BatchPreflightIndexError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise Phase4BatchPreflightIndexError(
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


def _write_text_atomic(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def render_markdown(payload: Mapping[str, Any]) -> str:
    counts = dict(payload.get("counts") or {})
    lines = [
        "# Phase 4 V22.1 Batch Preflight",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Cases: `{counts.get('cases', 0)}`",
        f"- Preflight PASS: `{counts.get('ready', 0)}`",
        f"- Preflight blocked: `{counts.get('blocked', 0)}`",
        f"- Residual detections: `{counts.get('residual_detections', 0)}`",
        f"- Temporal OCR false positives excluded: `{counts.get('temporal_false_positives', 0)}`",
        f"- Collision events: `{counts.get('collision_events', 0)}`",
        f"- Remediation proposals ready: `{counts.get('proposal_ready', 0)}`",
        f"- Operator triage required: `{counts.get('triage_required', 0)}`",
        f"- Batch preflight SHA-256: `{payload.get('batch_preflight_sha256')}`",
        "",
        "| Case | State | Tracks | Overflow | Collisions | Residual | Result | Evidence |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in list(payload.get("cases") or []):
        typography = dict(row.get("typography") or {})
        residual = dict(row.get("residual_cjk") or {})
        result = str(row.get("review_result") or "")
        evidence = (
            f"[proposal]({row.get('proposal_markdown_path')})"
            if row.get("proposal_markdown_path")
            else f"[triage]({row.get('triage_path')})"
            if row.get("triage_path")
            else "-"
        )
        lines.append(
            f"| `{row.get('case_id')}` | `{row.get('state_status')}` | "
            f"{dict(row.get('render_counts') or {}).get('render_tracks', 0)} | "
            f"{typography.get('text_overflow', 0)} | "
            f"{typography.get('collision_events', 0)} | "
            f"{residual.get('detections', 0)} | `{result}` | {evidence} |"
        )
    lines.extend(
        [
            "",
            "No Phase 2 remediation, visual approval, audio approval, TTS, or render action has been written by this index.",
            "",
        ]
    )
    return "\n".join(lines)


def build_batch_preflight_index(*, run_root: str | Path) -> dict[str, Any]:
    run = Path(run_root).resolve()
    state_path = run / "batch_regression_state.json"
    state = _load_object(state_path)
    state_cases = [
        dict(row)
        for row in list(state.get("cases") or [])
        if isinstance(row, Mapping)
    ]
    if not state_cases:
        raise Phase4BatchPreflightIndexError("Batch state has no cases")
    allowed_states = {
        "WAITING_RESIDUAL_REMEDIATION_OPERATOR_REVIEW",
        "WAITING_RESIDUAL_CJK_OPERATOR_TRIAGE",
        "READY_FOR_PHASE4",
        "READY_FOR_VISUAL_PREVIEW",
    }
    totals = {
        "cases": 0,
        "ready": 0,
        "blocked": 0,
        "residual_detections": 0,
        "raw_residual_detections": 0,
        "temporal_false_positives": 0,
        "collision_events": 0,
        "proposal_ready": 0,
        "triage_required": 0,
    }
    case_rows: list[dict[str, Any]] = []
    for state_case in sorted(
        state_cases, key=lambda row: str(row.get("case_id") or "")
    ):
        case_id = str(state_case.get("case_id") or "").strip()
        state_status = str(state_case.get("status") or "")
        if not case_id or state_status not in allowed_states:
            raise Phase4BatchPreflightIndexError(
                f"Case is not at a Phase 4 preflight gate: {case_id or 'unknown'}"
            )
        root = (run / case_id).resolve()
        if not root.is_relative_to(run) or not root.is_dir():
            raise Phase4BatchPreflightIndexError(f"Invalid case root: {case_id}")
        meta_path = root / "phase4_preflight_meta.json"
        report_path = root / "qa" / "phase4_preflight_report.json"
        handoff_path = root / "phase3_render_handoff.json"
        meta = _load_object(meta_path)
        report = _load_object(report_path)
        if str(meta.get("phase3_render_handoff_sha256") or "") != _sha256_file(
            handoff_path
        ):
            raise Phase4BatchPreflightIndexError(
                f"Phase 4 preflight is stale for {case_id}"
            )
        residual = dict(meta.get("residual_cjk") or {})
        detections = list(residual.get("detections") or [])
        raw_detections = list(residual.get("raw_detections") or [])
        temporal_false_positives = list(
            residual.get("temporal_false_positives") or []
        )
        typography = dict(meta.get("typography") or {})
        blocked = str(meta.get("status") or "") != "READY_FOR_PHASE4"
        review_result = "READY"
        proposal_path = root / "phase2_residual_remediation_proposal.json"
        attempt_path = root / "phase2_residual_remediation_proposal_attempt.json"
        proposal_ref: dict[str, Any] | None = None
        triage_ref: dict[str, Any] | None = None
        if blocked and proposal_path.is_file():
            proposal = _load_object(proposal_path)
            if (
                not _verify_self_hash(proposal, "proposal_sha256")
                or str(proposal.get("status") or "")
                != "PROPOSAL_READY_FOR_OPERATOR_REVIEW"
                or bool(proposal.get("operator_approval_written"))
            ):
                raise Phase4BatchPreflightIndexError(
                    f"Residual proposal is invalid for {case_id}"
                )
            proposal_ref = {
                "path": f"{case_id}/{proposal_path.name}",
                "sha256": _sha256_file(proposal_path),
                "proposal_sha256": proposal.get("proposal_sha256"),
                "counts": proposal.get("counts"),
            }
            review_result = "REMEDIATION_PROPOSAL_READY"
            totals["proposal_ready"] += 1
        elif blocked and attempt_path.is_file():
            attempt = _load_object(attempt_path)
            if not _verify_self_hash(attempt, "attempt_sha256"):
                raise Phase4BatchPreflightIndexError(
                    f"Residual proposal attempt hash is invalid for {case_id}"
                )
            meta_ref = dict(attempt.get("phase4_preflight_meta_ref") or {})
            if str(meta_ref.get("sha256") or "") != _sha256_file(meta_path):
                raise Phase4BatchPreflightIndexError(
                    f"Residual proposal attempt is stale for {case_id}"
                )
            triage_ref = {
                "path": f"{case_id}/{attempt_path.name}",
                "sha256": _sha256_file(attempt_path),
                "attempt_sha256": attempt.get("attempt_sha256"),
                "reason": attempt.get("reason"),
            }
            review_result = "OPERATOR_TRIAGE_REQUIRED"
            totals["triage_required"] += 1
        elif blocked:
            raise Phase4BatchPreflightIndexError(
                f"Blocked case has no proposal or triage artifact: {case_id}"
            )

        row: dict[str, Any] = {
            "case_id": case_id,
            "state_status": state_status,
            "preflight_status": meta.get("status"),
            "final_render_gate": meta.get("final_render_gate"),
            "render_counts": meta.get("counts"),
            "typography": typography,
            "blocked_reasons": list(report.get("blocked_reasons") or []),
            "residual_cjk": {
                "complete": residual.get("complete"),
                "detections": len(detections),
                "raw_detections": len(raw_detections),
                "temporal_false_positives": len(temporal_false_positives),
            },
            "review_result": review_result,
            "preflight_meta_ref": {
                "path": f"{case_id}/{meta_path.name}",
                "sha256": _sha256_file(meta_path),
            },
            "preflight_report_ref": {
                "path": f"{case_id}/qa/{report_path.name}",
                "sha256": _sha256_file(report_path),
            },
        }
        if proposal_ref is not None:
            row["proposal_ref"] = proposal_ref
            row["proposal_markdown_path"] = (
                f"{case_id}/phase2_residual_remediation_proposal.md"
            )
        if triage_ref is not None:
            row["triage_ref"] = triage_ref
            row["triage_path"] = triage_ref["path"]
        case_rows.append(row)
        totals["cases"] += 1
        totals["blocked"] += int(blocked)
        totals["ready"] += int(not blocked)
        totals["residual_detections"] += len(detections)
        totals["raw_residual_detections"] += len(raw_detections)
        totals["temporal_false_positives"] += len(temporal_false_positives)
        totals["collision_events"] += int(
            typography.get("collision_events") or 0
        )

    payload: dict[str, Any] = {
        "schema_version": "phase4_batch_preflight_index_v1",
        "status": (
            "PHASE4_PREFLIGHT_OPERATOR_TRIAGE_REQUIRED"
            if totals["triage_required"]
            else "PHASE4_RESIDUAL_REMEDIATION_APPROVAL_REQUIRED"
            if totals["proposal_ready"]
            else "READY_FOR_PHASE4"
        ),
        "operator_approval_written": False,
        "batch_state_ref": {
            "path": state_path.name,
            "sha256": _sha256_file(state_path),
            "run_sha256": state.get("run_sha256"),
        },
        "counts": totals,
        "cases": case_rows,
    }
    payload["batch_preflight_sha256"] = _sha256_json(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase4_batch_preflight_index"
    )
    parser.add_argument("run_root")
    args = parser.parse_args()
    try:
        run = Path(args.run_root).resolve()
        payload = build_batch_preflight_index(run_root=run)
        output = run / "phase4_batch_preflight_index.json"
        markdown = run / "PHASE4_V22_1_PREFLIGHT_INDEX.md"
        _write_json_atomic(output, payload)
        _write_text_atomic(markdown, render_markdown(payload))
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "counts": payload["counts"],
                    "batch_preflight_sha256": payload[
                        "batch_preflight_sha256"
                    ],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, Phase4BatchPreflightIndexError) as exc:
        print(f"[PHASE4-BATCH-PREFLIGHT][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
