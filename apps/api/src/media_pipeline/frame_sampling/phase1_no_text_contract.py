"""Hash-bound operator review for Phase 1 sources with no confirmed text."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class Phase1NoTextContractError(RuntimeError):
    pass


class Phase1NoTextApprovalError(Phase1NoTextContractError):
    """An approval exists but cannot authorize the current review candidate."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase1NoTextContractError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise Phase1NoTextContractError(f"{path.name} must contain an object")
    return payload


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_source_video(root: Path, raw_value: Any) -> Path:
    raw = Path(str(raw_value or "").strip())
    if not str(raw):
        raise Phase1NoTextContractError("Phase 1 source video path is missing")
    candidates = [raw] if raw.is_absolute() else [base / raw for base in (root, *root.parents)]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    raise Phase1NoTextContractError("Phase 1 source video is missing")


def _verify_self_hash(payload: Mapping[str, Any], key: str) -> bool:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(key, "") or "")
    return len(claimed) == 64 and claimed == _sha256_json(unsigned)


def prepare_no_text_review(root_dir: str | Path) -> dict[str, Any]:
    """Create an immutable review candidate; never self-approve it."""
    root = Path(root_dir).resolve()
    timeline_path = root / "master_timeline.json"
    score_path = root / "phase1_score.json"
    coverage_path = root / "text_frame_coverage.json"
    quality_path = root / "qa" / "quality_report.json"
    meta_path = root / "phase1_meta.json"
    for path in (timeline_path, score_path, coverage_path, quality_path, meta_path):
        if not path.is_file():
            raise Phase1NoTextContractError(f"Missing Phase 1 evidence: {path.name}")
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    score = _load_object(score_path)
    coverage = _load_object(coverage_path)
    quality = _load_object(quality_path)
    meta = _load_object(meta_path)
    source_video_path = _resolve_source_video(root, meta.get("video"))
    if not isinstance(timeline, list):
        raise Phase1NoTextContractError("master_timeline.json must contain a list")
    if bool(score.get("PASS")):
        raise Phase1NoTextContractError("A Phase 1 PASS case is not a no-text candidate")
    if timeline or int(score.get("tracks") or 0) != 0:
        raise Phase1NoTextContractError("No-text review requires zero final tracks")
    if list(score.get("uncovered_dense_hardsub_spans") or []):
        raise Phase1NoTextContractError("Uncovered hardsub evidence blocks no-text review")
    if list(score.get("high_confidence_local_text_rejects") or []):
        raise Phase1NoTextContractError("High-confidence rejected text blocks no-text review")
    if int(quality.get("uncertain_tracks") or 0) != 0:
        raise Phase1NoTextContractError("Uncertain tracks block no-text review")

    payload: dict[str, Any] = {
        "schema_version": "phase1_no_text_review_v2",
        "status": "NO_TEXT_OPERATOR_REVIEW_REQUIRED",
        "created_at": _now(),
        "review_instruction": (
            "Review the complete source video, not detector counts alone. Confirm "
            "NO_TEXT only when no translatable/editor text appears in any frame."
        ),
        "phase1_refs": {
            "master_timeline": {
                "path": timeline_path.name,
                "sha256": _sha256_file(timeline_path),
            },
            "phase1_score": {
                "path": score_path.name,
                "sha256": _sha256_file(score_path),
            },
            "text_frame_coverage": {
                "path": coverage_path.name,
                "sha256": _sha256_file(coverage_path),
            },
            "quality_report": {
                "path": "qa/quality_report.json",
                "sha256": _sha256_file(quality_path),
            },
        },
        "source_video": {
            "path": str(meta.get("video") or ""),
            "sha256": _sha256_file(source_video_path),
            "size_bytes": source_video_path.stat().st_size,
        },
        "automated_evidence": {
            "final_tracks": 0,
            "uncertain_tracks": 0,
            "uncovered_dense_hardsub_spans": [],
            "decoded_frames": int(
                meta.get("n_scanned_frames") or meta.get("frame_count") or 0
            ),
            "frames_with_detector_candidates": int(
                coverage.get("n_frames_with_text") or 0
            ),
            "detector_hits": int(coverage.get("n_hits") or 0),
        },
        "operator_decision": None,
    }
    # Preserve idempotency across resumptions when the evidence is unchanged.
    target = root / "phase1_no_text_review.json"
    if target.is_file():
        existing = _load_object(target)
        if _verify_self_hash(existing, "review_sha256"):
            old_refs = dict(existing.get("phase1_refs") or {})
            old_source = existing.get("source_video")
            if (
                old_refs == payload["phase1_refs"]
                and isinstance(old_source, Mapping)
                and dict(old_source) == payload["source_video"]
            ):
                return existing
    payload["review_sha256"] = _sha256_json(payload)
    _write_json_atomic(target, payload)
    return payload


def record_no_text_decision(
    root_dir: str | Path,
    *,
    operator_id: str,
    decision: str,
    notes: str | None = None,
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    operator = str(operator_id or "").strip()
    normalized = str(decision or "").strip().upper()
    if not operator:
        raise Phase1NoTextContractError("No-text approval requires an operator id")
    if normalized not in {"NO_TEXT_CONFIRMED", "TEXT_PRESENT_REJECTED"}:
        raise Phase1NoTextContractError("Unsupported no-text operator decision")
    candidate = prepare_no_text_review(root)
    candidate_sha = str(candidate.get("review_sha256") or "")
    target = root / "phase1_no_text_approval.json"
    if target.is_file():
        existing = _load_object(target)
        if (
            _verify_self_hash(existing, "approval_sha256")
            and str(dict(existing.get("review_ref") or {}).get("sha256") or "")
            == candidate_sha
            and str(existing.get("operator_id") or "") == operator
            and str(existing.get("decision") or "") == normalized
            and str(existing.get("notes") or "") == str(notes or "")
        ):
            return existing
    approval: dict[str, Any] = {
        "schema_version": "phase1_no_text_approval_v2",
        "status": (
            "NO_TEXT_OPERATOR_APPROVED"
            if normalized == "NO_TEXT_CONFIRMED"
            else "TEXT_PRESENT_PHASE1_REJECTED"
        ),
        "decision": normalized,
        "operator_id": operator,
        "reviewed_at": _now(),
        "notes": str(notes or ""),
        "review_ref": {
            "path": "phase1_no_text_review.json",
            "sha256": candidate_sha,
        },
    }
    approval["approval_sha256"] = _sha256_json(approval)
    _write_json_atomic(target, approval)
    return approval


def evaluate_no_text_review(root_dir: str | Path) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    candidate = prepare_no_text_review(root)
    approval_path = root / "phase1_no_text_approval.json"
    if not approval_path.is_file():
        return {
            "status": "WAITING_NO_TEXT_OPERATOR_REVIEW",
            "next_stage": "phase1_no_text_review",
            "operator_touch_required": True,
            "review_required": 1,
            "review_sha256": candidate["review_sha256"],
        }
    approval = _load_object(approval_path)
    if not _verify_self_hash(approval, "approval_sha256"):
        raise Phase1NoTextApprovalError(
            "No-text approval self-hash is invalid",
            reason="INVALID_APPROVAL_SELF_HASH",
        )
    if str(dict(approval.get("review_ref") or {}).get("sha256") or "") != str(
        candidate.get("review_sha256") or ""
    ):
        raise Phase1NoTextApprovalError(
            "No-text approval is stale",
            reason="STALE_APPROVAL",
        )
    decision = str(approval.get("decision") or "")
    if decision == "NO_TEXT_CONFIRMED":
        return {
            "status": "NO_TEXT_OPERATOR_APPROVED",
            "next_stage": None,
            "operator_touch_required": False,
            "review_required": 0,
            "approval_sha256": approval["approval_sha256"],
        }
    return {
        "status": "TEXT_PRESENT_PHASE1_REJECTED",
        "next_stage": None,
        "operator_touch_required": False,
        "review_required": 0,
        "approval_sha256": approval["approval_sha256"],
    }


def evaluate_no_text_operator_gate(root_dir: str | Path) -> dict[str, Any]:
    """Queue stale/invalid approvals for review without weakening strict validation."""
    try:
        return evaluate_no_text_review(root_dir)
    except Phase1NoTextApprovalError as exc:
        candidate = prepare_no_text_review(root_dir)
        return {
            "status": "WAITING_NO_TEXT_OPERATOR_REVIEW",
            "next_stage": "phase1_no_text_review",
            "operator_touch_required": True,
            "review_required": 1,
            "review_sha256": candidate["review_sha256"],
            "approval_state": exc.reason,
        }
