"""Verify an approved Phase 3 rerun and publish a Phase 4-ready batch audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class Phase3BatchFinalizationError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase3BatchFinalizationError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise Phase3BatchFinalizationError(
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


def finalize_phase3_batch(
    *, run_root: str | Path, generated_at: str | None = None
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    approval_path = run / "phase3_batch_proposal_approval.json"
    approval = _load_object(approval_path)
    if not _verify_self_hash(approval, "approval_sha256"):
        raise Phase3BatchFinalizationError("Batch approval self-hash is invalid")
    if str(approval.get("status") or "") != (
        "TRANSLATION_DECISIONS_RECORDED_PHASE3_RERUN_REQUIRED"
    ):
        raise Phase3BatchFinalizationError("Batch approval is not awaiting rerun")
    batch_ref = dict(approval.get("batch_review_ref") or {})
    batch_path = (run / str(batch_ref.get("path") or "")).resolve()
    if (
        not batch_path.is_relative_to(run)
        or not batch_path.is_file()
        or str(batch_ref.get("file_sha256") or "") != _sha256_file(batch_path)
    ):
        raise Phase3BatchFinalizationError("Approved batch review is stale")

    totals = {
        "cases": 0,
        "approved_decisions": 0,
        "approved_unchanged": 0,
        "edited": 0,
        "content_objects": 0,
        "translated_approved": 0,
        "deterministic": 0,
        "geometry_refs": 0,
    }
    case_results: list[dict[str, Any]] = []
    for raw in list(approval.get("cases") or []):
        if not isinstance(raw, Mapping):
            raise Phase3BatchFinalizationError("Batch approval has an invalid case")
        approved_case = dict(raw)
        case_id = str(approved_case.get("case_id") or "").strip()
        case_root = (run / case_id).resolve()
        audit_ref = dict(approved_case.get("operator_review_audit_ref") or {})
        audit_path = (run / str(audit_ref.get("path") or "")).resolve()
        if (
            not case_id
            or not case_root.is_relative_to(run)
            or not case_root.is_dir()
            or not audit_path.is_relative_to(case_root)
            or not audit_path.is_file()
            or str(audit_ref.get("sha256") or "") != _sha256_file(audit_path)
        ):
            raise Phase3BatchFinalizationError(
                f"Operator review audit is stale for {case_id or '(empty)'}"
            )
        operator_audit = _load_object(audit_path)
        if (
            not _verify_self_hash(operator_audit, "audit_sha256")
            or str(operator_audit.get("audit_sha256") or "")
            != str(audit_ref.get("audit_sha256") or "")
        ):
            raise Phase3BatchFinalizationError(
                f"Operator review audit hash is invalid for {case_id}"
            )

        paths = {
            "approvals": case_root / "phase3_approvals.json",
            "timeline": case_root / "phase3_translation_timeline.json",
            "meta": case_root / "phase3_meta.json",
            "render_handoff": case_root / "phase3_render_handoff.json",
            "closeout": case_root / "phase3_closeout.json",
        }
        if any(not path.is_file() for path in paths.values()):
            raise Phase3BatchFinalizationError(
                f"Phase 3 rerun artifacts are incomplete for {case_id}"
            )
        approvals = _load_object(paths["approvals"])
        timeline = _load_object(paths["timeline"])
        meta = _load_object(paths["meta"])
        render_handoff = _load_object(paths["render_handoff"])
        closeout = _load_object(paths["closeout"])
        reviewed_rows = [
            dict(row)
            for row in list(approvals.get("approvals") or [])
            if isinstance(row, Mapping)
            and str(row.get("decision") or "").upper() in {"APPROVE", "EDIT"}
            and str(row.get("reviewer") or "").strip()
            and str(row.get("reviewed_at") or "").strip()
        ]
        expected = int(dict(approved_case.get("counts") or {}).get("objects") or 0)
        summary = dict(timeline.get("review_summary") or {})
        meta_summary = dict(meta.get("review_summary") or {})
        handoff_counts = dict(render_handoff.get("counts") or {})
        if len(reviewed_rows) != expected:
            raise Phase3BatchFinalizationError(
                f"Approved decision count drift for {case_id}"
            )
        if (
            str(summary.get("status") or "") != "TRANSLATION_APPROVED"
            or int(summary.get("unresolved") or 0) != 0
            or int(summary.get("failed") or 0) != 0
            or str(meta_summary.get("status") or "") != "TRANSLATION_APPROVED"
            or str(render_handoff.get("status") or "") != "READY_FOR_RENDER"
            or list(render_handoff.get("blocked_reasons") or [])
            or str(closeout.get("status") or "") != "PHASE3_CLOSED"
        ):
            raise Phase3BatchFinalizationError(
                f"Phase 3 rerun is not ready for Phase 4 for {case_id}"
            )
        if (
            str(dict(closeout.get("phase3_timeline_ref") or {}).get("sha256") or "")
            != _sha256_file(paths["timeline"])
            or str(
                dict(closeout.get("phase3_render_handoff_ref") or {}).get(
                    "sha256"
                )
                or ""
            )
            != _sha256_file(paths["render_handoff"])
        ):
            raise Phase3BatchFinalizationError(
                f"Phase 3 closeout is stale for {case_id}"
            )

        audit_counts = dict(operator_audit.get("counts") or {})
        case_result = {
            "case_id": case_id,
            "status": "READY_FOR_PHASE4_PREFLIGHT",
            "approved_decisions": len(reviewed_rows),
            "approved_unchanged": int(audit_counts.get("approved_unchanged") or 0),
            "edited": int(audit_counts.get("edited") or 0),
            "review_summary": summary,
            "render_handoff_counts": handoff_counts,
            "phase3_timeline_ref": {
                "path": paths["timeline"].relative_to(run).as_posix(),
                "sha256": _sha256_file(paths["timeline"]),
            },
            "phase3_render_handoff_ref": {
                "path": paths["render_handoff"].relative_to(run).as_posix(),
                "sha256": _sha256_file(paths["render_handoff"]),
            },
            "phase3_closeout_ref": {
                "path": paths["closeout"].relative_to(run).as_posix(),
                "sha256": _sha256_file(paths["closeout"]),
            },
        }
        case_results.append(case_result)
        totals["cases"] += 1
        totals["approved_decisions"] += case_result["approved_decisions"]
        totals["approved_unchanged"] += case_result["approved_unchanged"]
        totals["edited"] += case_result["edited"]
        totals["content_objects"] += int(summary.get("content_objects") or 0)
        totals["translated_approved"] += int(summary.get("approved") or 0)
        totals["deterministic"] += int(summary.get("deterministic") or 0)
        totals["geometry_refs"] += int(handoff_counts.get("geometry_refs") or 0)

    expected_cases = int(dict(approval.get("counts") or {}).get("cases") or 0)
    expected_objects = int(
        dict(approval.get("counts") or {}).get("review_objects") or 0
    )
    if (
        totals["cases"] != expected_cases
        or totals["approved_decisions"] != expected_objects
    ):
        raise Phase3BatchFinalizationError("Batch finalization count mismatch")

    result: dict[str, Any] = {
        "schema_version": "phase3_batch_handoff_ready_v1",
        "status": "READY_FOR_PHASE4_PREFLIGHT",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "batch_approval_ref": {
            "path": approval_path.name,
            "sha256": _sha256_file(approval_path),
            "approval_sha256": approval.get("approval_sha256"),
        },
        "counts": totals,
        "cases": case_results,
    }
    result["handoff_ready_sha256"] = _sha256_json(result)
    _write_json_atomic(run / "phase3_batch_handoff_ready.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.finalize_phase3_batch_approval"
    )
    parser.add_argument("run_root")
    args = parser.parse_args()
    try:
        result = finalize_phase3_batch(run_root=args.run_root)
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "counts": result["counts"],
                    "handoff_ready_sha256": result["handoff_ready_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, Phase3BatchFinalizationError) as exc:
        print(f"[PHASE3-BATCH-FINALIZE][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
