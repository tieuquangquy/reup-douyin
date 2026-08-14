"""Apply a complete hash-bound Phase 2 OCR review decision set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class Phase2OperatorReviewError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase2OperatorReviewError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise Phase2OperatorReviewError(f"{path.name} must contain an object")
    return payload


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _verify_self_hash(payload: Mapping[str, Any], field: str) -> bool:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    return len(claimed) == 64 and claimed == _sha256_json(unsigned)


def _stable_semantic_identity(content: Mapping[str, Any]) -> dict[str, Any]:
    """Return only per-object semantic evidence suitable for approval carry.

    ``semantic_authority_sha256`` summarizes the complete clip and therefore
    changes when an unrelated residual is added.  It must not be the identity
    used to decide whether one already-reviewed source object is unchanged.
    """

    semantic = dict(content.get("semantic_hardsub") or {})
    return {
        key: semantic.get(key)
        for key in (
            "schema_version",
            "recipe_version",
            "cue_id",
            "classification",
            "action",
            "canonical_text_authority",
        )
    }


def _review_evidence(content: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "geometry_refs": [str(value) for value in content.get("geometry_refs") or []],
        "ocr_text_candidate": str(content.get("ocr_text_candidate") or ""),
        "provenance_classifications": [
            str(value) for value in content.get("provenance_classifications") or []
        ],
        "semantic_identity": _stable_semantic_identity(content),
    }


def apply_phase2_operator_review(
    *, root_dir: str | Path, decisions_path: str | Path
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    decisions_file = Path(decisions_path).resolve()
    queue_path = root / "phase2_review_queue.json"
    approvals_path = root / "phase2_approvals.json"
    decisions = _load_object(decisions_file)
    if not _verify_self_hash(decisions, "decisions_sha256"):
        raise Phase2OperatorReviewError("Decision-set self-hash is invalid")
    queue = _load_object(queue_path)
    expected_queue_sha = str(decisions.get("review_queue_sha256") or "")
    if expected_queue_sha != _sha256_file(queue_path):
        raise Phase2OperatorReviewError("Decision set is stale for the OCR review queue")
    reviewer = str(decisions.get("reviewer") or "").strip()
    reviewed_at = str(decisions.get("reviewed_at") or "").strip()
    if not reviewer or not reviewed_at:
        raise Phase2OperatorReviewError("Reviewer and reviewed_at are required")
    queue_objects = {
        str(item.get("content_id") or ""): dict(item)
        for item in list(queue.get("content_objects") or [])
        if isinstance(item, Mapping)
    }
    decision_rows = {
        str(item.get("content_id") or ""): dict(item)
        for item in list(decisions.get("decisions") or [])
        if isinstance(item, Mapping)
    }
    if not queue_objects or set(queue_objects) != set(decision_rows):
        raise Phase2OperatorReviewError(
            "Decision set must cover every unresolved OCR object exactly once"
        )
    current_objects: dict[str, dict[str, Any]] = {}
    timeline_path = root / "phase2_ocr_timeline.json"
    if timeline_path.is_file():
        timeline = _load_object(timeline_path)
        current_objects = {
            str(item.get("content_id") or ""): dict(item)
            for item in list(timeline.get("content_objects") or [])
            if isinstance(item, Mapping)
        }

    preserved_rows: dict[str, dict[str, Any]] = {}
    if approvals_path.is_file() and current_objects:
        existing = _load_object(approvals_path)
        if dict(existing.get("phase1_ref") or {}) == dict(queue.get("phase1_ref") or {}):
            for raw in list(existing.get("approvals") or []):
                if not isinstance(raw, Mapping):
                    continue
                row = dict(raw)
                content_id = str(row.get("content_id") or "")
                current = current_objects.get(content_id)
                if content_id in queue_objects or current is None:
                    continue
                if str(row.get("decision") or "").upper() not in {
                    "APPROVE",
                    "EDIT",
                    "REJECT_UI",
                    "PRESERVE_SOURCE",
                }:
                    continue
                if not str(row.get("reviewer") or "").strip() or not str(
                    row.get("reviewed_at") or ""
                ).strip():
                    continue
                if str(row.get("review_input_sha256") or "") != str(
                    current.get("review_input_sha256") or ""
                ):
                    continue
                preserved_rows[content_id] = row

    decided_rows: dict[str, dict[str, Any]] = {}
    edited_count = 0
    for content_id, content in queue_objects.items():
        row = decision_rows[content_id]
        decision = str(row.get("decision") or "").upper()
        if decision not in {"APPROVE", "EDIT", "REJECT_UI", "PRESERVE_SOURCE"}:
            raise Phase2OperatorReviewError(f"Unsupported decision for {content_id}")
        approved_text = str(row.get("ocr_text_approved") or "").strip()
        if decision not in {"REJECT_UI", "PRESERVE_SOURCE"} and not approved_text:
            raise Phase2OperatorReviewError(f"Approved OCR text missing for {content_id}")
        candidate = str(content.get("ocr_text_candidate") or "").strip()
        if decision == "APPROVE" and approved_text != candidate:
            raise Phase2OperatorReviewError(
                f"APPROVE must preserve the OCR candidate for {content_id}"
            )
        edited_count += int(decision == "EDIT")
        decided_rows[content_id] = {
                "content_id": content_id,
                "decision": decision,
                "review_input_sha256": content.get("review_input_sha256"),
                "review_evidence": _review_evidence(content),
                "ocr_text_approved": approved_text or None,
                "vi_text_approved": row.get("vi_text_approved"),
                "reviewer": reviewer,
                "reviewed_at": reviewed_at,
            }
    combined_rows = {**preserved_rows, **decided_rows}
    ordered_ids = list(current_objects) if current_objects else list(queue_objects)
    approval_rows = [
        combined_rows[content_id]
        for content_id in ordered_ids
        if content_id in combined_rows
    ]
    approvals = {
        "schema_version": "phase2_approvals_v2",
        "phase1_ref": queue.get("phase1_ref"),
        "approvals": approval_rows,
    }
    _write_json_atomic(approvals_path, approvals)
    audit: dict[str, Any] = {
        "schema_version": "phase2_operator_review_audit_v1",
        "status": "DECISIONS_RECORDED_PHASE2_RERUN_REQUIRED",
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "review_queue_ref": {
            "path": queue_path.name,
            "sha256": expected_queue_sha,
        },
        "decision_set_ref": {
            "path": decisions_file.name,
            "sha256": _sha256_file(decisions_file),
            "decisions_sha256": decisions.get("decisions_sha256"),
        },
        "approvals_ref": {
            "path": approvals_path.name,
            "sha256": _sha256_file(approvals_path),
        },
        "counts": {
            "objects": len(approval_rows),
            "edited": edited_count,
            "approved_unchanged": len(decided_rows) - edited_count,
            "preserved_fresh_approvals": len(preserved_rows),
        },
    }
    audit["audit_sha256"] = _sha256_json(audit)
    _write_json_atomic(root / "phase2_operator_review_audit.json", audit)
    return audit
