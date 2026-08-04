"""Suggest Phase 3 edits from prior reviewed translations by exact Chinese text."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class Phase3ReferenceEditsError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase3ReferenceEditsError(f"Cannot read valid {path}") from exc
    if not isinstance(payload, dict):
        raise Phase3ReferenceEditsError(f"{path} must contain an object")
    return payload


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


def build_reference_edits(
    *, target_root: Path, reference_root: Path
) -> dict[str, Any]:
    queue_path = target_root / "phase3_review_queue.json"
    reference_timeline_path = reference_root / "phase3_translation_timeline.json"
    reference_approvals_path = reference_root / "phase3_approvals.json"
    queue = _load_object(queue_path)
    reference_timeline = _load_object(reference_timeline_path)
    reference_approvals = _load_object(reference_approvals_path)
    zh_by_id = {
        str(row.get("content_id") or ""): str(row.get("zh_approved") or "").strip()
        for row in list(reference_timeline.get("content_objects") or [])
        if isinstance(row, Mapping)
    }
    reviewed_by_zh: dict[str, str] = {}
    conflicted_zh: set[str] = set()
    for raw in list(reference_approvals.get("approvals") or []):
        if not isinstance(raw, Mapping):
            continue
        content_id = str(raw.get("content_id") or "")
        zh = zh_by_id.get(content_id, "")
        vi = str(raw.get("vi_text_approved") or "").strip()
        if (
            not zh
            or not vi
            or str(raw.get("decision") or "").upper() not in {"APPROVE", "EDIT"}
            or not str(raw.get("reviewer") or "").strip()
            or not str(raw.get("reviewed_at") or "").strip()
        ):
            continue
        previous = reviewed_by_zh.get(zh)
        if previous is not None and previous != vi:
            conflicted_zh.add(zh)
            continue
        reviewed_by_zh[zh] = vi
    for zh in conflicted_zh:
        reviewed_by_zh.pop(zh, None)

    edits: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    queue_rows = [
        dict(row)
        for row in list(queue.get("content_objects") or [])
        if isinstance(row, Mapping)
    ]
    for row in queue_rows:
        content_id = str(row.get("content_id") or "").strip()
        zh = str(row.get("zh_approved") or "").strip()
        if not content_id or not zh:
            raise Phase3ReferenceEditsError(
                "Phase 3 queue contains missing content_id/zh_approved"
            )
        reviewed_vi = reviewed_by_zh.get(zh)
        if reviewed_vi is None:
            unmatched.append(content_id)
            continue
        edits[content_id] = {
            "vi_text": reviewed_vi,
            "reasons": [
                "exact_chinese_authority_matches_operator_reviewed_translation"
            ],
        }
    return {
        "schema_version": "phase3_reference_edits_v1",
        "status": "UNAPPROVED_TRANSLATION_SUGGESTIONS",
        "phase3_review_queue_ref": {
            "path": queue_path.name,
            "sha256": _sha256_file(queue_path),
        },
        "reference": {
            "root": str(reference_root),
            "timeline_sha256": _sha256_file(reference_timeline_path),
            "approvals_sha256": _sha256_file(reference_approvals_path),
            "matching_policy": "exact_zh_approved_and_reviewed_decision_only",
        },
        "counts": {
            "queue_objects": len(queue_rows),
            "exact_reviewed_matches": len(edits),
            "operator_review_required": len(unmatched),
        },
        "unmatched_content_ids": unmatched,
        "edits": edits,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target_root")
    parser.add_argument("reference_root")
    parser.add_argument("--output")
    args = parser.parse_args()
    target = Path(args.target_root).resolve()
    reference = Path(args.reference_root).resolve()
    payload = build_reference_edits(
        target_root=target, reference_root=reference
    )
    output = (
        Path(args.output).resolve()
        if args.output
        else target / "phase3_reference_edits.json"
    )
    _write_json_atomic(output, payload)
    print(
        json.dumps(
            {"output": str(output), "status": payload["status"], "counts": payload["counts"]},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
