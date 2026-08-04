"""Verify an approved Phase 2 batch rerun and publish a Phase 3-ready audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class Phase2BatchFinalizationError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase2BatchFinalizationError(f"Cannot read valid {path}") from exc
    if not isinstance(payload, dict):
        raise Phase2BatchFinalizationError(f"{path} must contain an object")
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


def finalize_phase2_batch(
    *, run_root: Path, generated_at: str | None = None
) -> dict[str, Any]:
    run_root = run_root.resolve()
    approval_path = run_root / "phase2_batch_proposal_approval.json"
    approval = _load_object(approval_path)
    if not _verify_self_hash(approval, "approval_sha256"):
        raise Phase2BatchFinalizationError("Batch approval self-hash is invalid")
    if str(approval.get("status") or "") != (
        "OCR_DECISIONS_RECORDED_PHASE2_RERUN_REQUIRED"
    ):
        raise Phase2BatchFinalizationError("Batch approval is not awaiting rerun")
    batch_ref = dict(approval.get("batch_proposal_ref") or {})
    batch_path = (run_root / str(batch_ref.get("path") or "")).resolve()
    if (
        not batch_path.is_relative_to(run_root)
        or not batch_path.is_file()
        or _sha256_file(batch_path) != str(batch_ref.get("file_sha256") or "")
    ):
        raise Phase2BatchFinalizationError("Approved batch proposal is stale")

    case_results: list[dict[str, Any]] = []
    totals = {
        "cases": 0,
        "approved_decisions": 0,
        "contract_content_objects": 0,
        "transition_duplicates_merged": 0,
        "translate_items": 0,
        "deterministic_items": 0,
        "cover_only_items": 0,
        "geometry_refs": 0,
    }
    for raw in list(approval.get("cases") or []):
        if not isinstance(raw, Mapping):
            raise Phase2BatchFinalizationError("Batch approval has an invalid case")
        approved_case = dict(raw)
        case_id = str(approved_case.get("case_id") or "").strip()
        case_root = (run_root / case_id).resolve()
        audit_ref = dict(approved_case.get("operator_review_audit_ref") or {})
        audit_path = (run_root / str(audit_ref.get("path") or "")).resolve()
        if (
            not case_id
            or not case_root.is_relative_to(run_root)
            or not case_root.is_dir()
            or not audit_path.is_relative_to(case_root)
            or not audit_path.is_file()
            or _sha256_file(audit_path) != str(audit_ref.get("sha256") or "")
        ):
            raise Phase2BatchFinalizationError(
                f"Operator review audit is stale for {case_id or '(empty)'}"
            )
        operator_audit = _load_object(audit_path)
        if (
            not _verify_self_hash(operator_audit, "audit_sha256")
            or str(operator_audit.get("audit_sha256") or "")
            != str(audit_ref.get("audit_sha256") or "")
        ):
            raise Phase2BatchFinalizationError(
                f"Operator review audit hash is invalid for {case_id}"
            )
        paths = {
            "approvals": case_root / "phase2_approvals.json",
            "timeline": case_root / "phase2_ocr_timeline.json",
            "meta": case_root / "phase2_meta.json",
            "handoff": case_root / "phase2_handoff.json",
        }
        if any(not path.is_file() for path in paths.values()):
            raise Phase2BatchFinalizationError(
                f"Phase 2 rerun artifacts are incomplete for {case_id}"
            )
        approvals = _load_object(paths["approvals"])
        timeline = _load_object(paths["timeline"])
        meta = _load_object(paths["meta"])
        handoff = _load_object(paths["handoff"])
        reviewed_rows = [
            dict(row)
            for row in list(approvals.get("approvals") or [])
            if isinstance(row, Mapping)
            and str(row.get("decision") or "").upper()
            in {"APPROVE", "EDIT", "REJECT_UI"}
            and str(row.get("reviewer") or "").strip()
            and str(row.get("reviewed_at") or "").strip()
        ]
        expected_decisions = int(
            dict(approved_case.get("counts") or {}).get("objects") or 0
        )
        review_summary = dict(timeline.get("review_summary") or {})
        handoff_counts = dict(handoff.get("counts") or {})
        if len(reviewed_rows) != expected_decisions:
            raise Phase2BatchFinalizationError(
                f"Approved decision count drift for {case_id}"
            )
        if (
            str(review_summary.get("status") or "") != "OCR_APPROVED"
            or int(review_summary.get("unresolved") or 0) != 0
            or int(meta.get("review_required") or 0) != 0
            or not bool(meta.get("ready_for_phase3"))
            or str(meta.get("handoff_status") or "") != "READY_FOR_PHASE3"
            or str(handoff.get("status") or "") != "READY_FOR_PHASE3"
            or list(handoff.get("blocked_reasons") or [])
        ):
            raise Phase2BatchFinalizationError(
                f"Phase 2 rerun is not ready for Phase 3 for {case_id}"
            )
        phase2_ref = dict(handoff.get("phase2_ref") or {})
        if str(phase2_ref.get("sha256") or "") != _sha256_file(paths["timeline"]):
            raise Phase2BatchFinalizationError(
                f"Phase 2 handoff is stale for {case_id}"
            )
        duplicate_summary = dict(timeline.get("duplicate_transition_summary") or {})
        case_result = {
            "case_id": case_id,
            "status": "READY_FOR_PHASE3",
            "approved_decisions": len(reviewed_rows),
            "contract_content_objects": len(list(timeline.get("content_objects") or [])),
            "transition_duplicates_merged": int(
                duplicate_summary.get("merged_content_objects") or 0
            ),
            "handoff_counts": handoff_counts,
            "phase2_timeline_ref": {
                "path": paths["timeline"].relative_to(run_root).as_posix(),
                "sha256": _sha256_file(paths["timeline"]),
            },
            "phase2_handoff_ref": {
                "path": paths["handoff"].relative_to(run_root).as_posix(),
                "sha256": _sha256_file(paths["handoff"]),
            },
        }
        case_results.append(case_result)
        totals["cases"] += 1
        totals["approved_decisions"] += case_result["approved_decisions"]
        totals["contract_content_objects"] += case_result[
            "contract_content_objects"
        ]
        totals["transition_duplicates_merged"] += case_result[
            "transition_duplicates_merged"
        ]
        for key in (
            "translate_items",
            "deterministic_items",
            "cover_only_items",
            "geometry_refs",
        ):
            totals[key] += int(handoff_counts.get(key) or 0)

    result: dict[str, Any] = {
        "schema_version": "phase2_batch_handoff_ready_v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "status": "READY_FOR_PHASE3",
        "batch_approval_ref": {
            "path": approval_path.name,
            "sha256": _sha256_file(approval_path),
            "approval_sha256": approval.get("approval_sha256"),
        },
        "counts": totals,
        "cases": case_results,
    }
    result["handoff_ready_sha256"] = _sha256_json(result)
    _write_json_atomic(run_root / "phase2_batch_handoff_ready.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root")
    args = parser.parse_args()
    result = finalize_phase2_batch(run_root=Path(args.run_root))
    print(
        json.dumps(
            {
                "status": result["status"],
                "counts": result["counts"],
                "handoff_ready_sha256": result["handoff_ready_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
