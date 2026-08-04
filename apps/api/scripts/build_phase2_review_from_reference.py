"""Build hash-bound OCR decisions from byte-identical reviewed crops plus overrides."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ReviewReferenceError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewReferenceError(f"Cannot read valid {path}") from exc
    if not isinstance(payload, dict):
        raise ReviewReferenceError(f"{path} must contain an object")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def build_decisions(
    *,
    target_root: Path,
    reference_root: Path,
    overrides: dict[str, str],
    reviewer: str,
    reviewed_at: str,
) -> dict[str, Any]:
    queue_path = target_root / "phase2_review_queue.json"
    queue = _load_object(queue_path)
    reference_timeline = _load_object(reference_root / "phase2_ocr_timeline.json")
    reference_approvals = _load_object(reference_root / "phase2_approvals.json")
    approved_by_id = {
        str(row.get("content_id") or ""): str(row.get("ocr_text_approved") or "")
        for row in list(reference_approvals.get("approvals") or [])
        if isinstance(row, dict)
        and str(row.get("decision") or "").upper() in {"APPROVE", "EDIT"}
        and str(row.get("reviewer") or "").strip()
        and str(row.get("reviewed_at") or "").strip()
    }
    text_by_crop_hash: dict[str, str] = {}
    for content in list(reference_timeline.get("content_objects") or []):
        if not isinstance(content, dict):
            continue
        content_id = str(content.get("content_id") or "")
        approved = approved_by_id.get(content_id, "").strip()
        if not approved:
            continue
        for text_id in list(content.get("geometry_refs") or []):
            crop = reference_root / "crops" / f"{text_id}.jpg"
            if crop.is_file():
                text_by_crop_hash[_sha256_file(crop)] = approved

    decisions: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for content in list(queue.get("content_objects") or []):
        if not isinstance(content, dict):
            continue
        content_id = str(content.get("content_id") or "")
        approved = str(overrides.get(content_id) or "").strip()
        if not approved:
            inherited = {
                text_by_crop_hash.get(_sha256_file(crop), "")
                for text_id in list(content.get("geometry_refs") or [])
                if (crop := target_root / "crops" / f"{text_id}.jpg").is_file()
            }
            inherited.discard("")
            if len(inherited) == 1:
                approved = inherited.pop().strip()
        if not approved:
            unresolved.append(content_id)
            continue
        candidate = str(content.get("ocr_text_candidate") or "").strip()
        decisions.append(
            {
                "content_id": content_id,
                "decision": "APPROVE" if approved == candidate else "EDIT",
                "ocr_text_approved": approved,
                "vi_text_approved": None,
            }
        )
    queue_ids = {
        str(row.get("content_id") or "")
        for row in list(queue.get("content_objects") or [])
        if isinstance(row, dict)
    }
    unknown_overrides = sorted(set(overrides) - queue_ids)
    if unresolved or unknown_overrides or len(decisions) != len(queue_ids):
        raise ReviewReferenceError(
            f"Review manifest incomplete: unresolved={unresolved} "
            f"unknown_overrides={unknown_overrides}"
        )
    payload: dict[str, Any] = {
        "schema_version": "phase2_review_decisions_v1",
        "review_queue_sha256": _sha256_file(queue_path),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "reference": {
            "root": str(reference_root),
            "approvals_sha256": _sha256_file(
                reference_root / "phase2_approvals.json"
            ),
            "matching_policy": "exact_crop_sha256_only",
        },
        "decisions": decisions,
    }
    payload["decisions_sha256"] = _sha256_json(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target_root")
    parser.add_argument("reference_root")
    parser.add_argument("--overrides")
    parser.add_argument("--output")
    parser.add_argument("--reviewer", default="codex-assisted-user-authorized")
    args = parser.parse_args()
    target = Path(args.target_root).resolve()
    reference = Path(args.reference_root).resolve()
    overrides: dict[str, str] = {}
    if args.overrides:
        raw = _load_object(Path(args.overrides).resolve())
        values = raw.get("overrides", raw)
        if not isinstance(values, dict):
            raise ReviewReferenceError("Overrides must be an object")
        overrides = {str(key): str(value) for key, value in values.items()}
    payload = build_decisions(
        target_root=target,
        reference_root=reference,
        overrides=overrides,
        reviewer=str(args.reviewer),
        reviewed_at=datetime.now(timezone.utc).isoformat(),
    )
    output = (
        Path(args.output).resolve()
        if args.output
        else target / "phase2_review_decisions_from_reference.json"
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
                "decisions_sha256": payload["decisions_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
