"""Hash-bound Phase 1 geometry review and materialization.

This gate authorizes geometry/provenance corrections only.  It deliberately
does not approve OCR text, translation, or any downstream phase.  The review
candidate binds the source video and every Phase 1 evidence artifact; an
approval or materialization becomes stale as soon as one of those inputs
changes.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


class Phase1GeometryReviewError(RuntimeError):
    pass


class Phase1GeometryApprovalError(Phase1GeometryReviewError):
    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


SCHEMA_VERSION = "phase1_geometry_review_v1"
APPROVAL_SCHEMA_VERSION = "phase1_geometry_approval_v1"
MATERIALIZATION_SCHEMA_VERSION = "phase1_geometry_materialization_v1"

# Only quality gates whose correction is a geometry/provenance decision may be
# operator-resolved here. Missing artifacts and OCR/semantic evidence remain
# hard failures and are intentionally not converted into a geometry approval.
GEOMETRY_CHECKS = frozenset(
    {
        "no_uncertain_tracks",
        "no_uncovered_dense_hardsub_spans",
        "no_unresolved_residual_hardsub_spans",
        "no_overexpanded_dense_hardsubs",
        "no_overmerged_ui_grid_tracks",
        "no_empty_left_wide_hardsub",
        "no_isolated_micro_source_tracks",
        "no_nested_temporal_ui_fragments",
        "near_dupe_pairs_le_2",
    }
)
ALLOWED_DECISIONS = (
    "APPROVE_GEOMETRY",
    "EDIT_GEOMETRY",
    "REJECT_TRACK",
    "EXPLAIN_SHADOW",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase1GeometryReviewError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise Phase1GeometryReviewError(f"{path.name} must contain an object")
    return payload


def _load_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase1GeometryReviewError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, list):
        raise Phase1GeometryReviewError(f"{path.name} must contain a list")
    return [dict(row) for row in payload if isinstance(row, Mapping)]


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _verify_self_hash(payload: Mapping[str, Any], key: str) -> bool:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(key, "") or "")
    return len(claimed) == 64 and claimed == sha256_json(unsigned)


def _source_video(root: Path, meta: Mapping[str, Any]) -> Path:
    raw = Path(str(meta.get("video") or "").strip())
    if not str(raw):
        raise Phase1GeometryReviewError("Phase 1 source video path is missing")
    candidates = [raw] if raw.is_absolute() else [root / raw, *[p / raw for p in root.parents]]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    raise Phase1GeometryReviewError("Phase 1 source video is missing")


def _ref(root: Path, path: Path, *, label: str) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise Phase1GeometryReviewError(f"Missing {label}: {path.name}")
    return {
        "path": resolved.relative_to(root).as_posix(),
        "sha256": sha256_file(resolved),
    }


def _failed_geometry_checks(score: Mapping[str, Any]) -> list[str]:
    checks = dict(score.get("checks") or {})
    failed = [str(key) for key, value in checks.items() if value is False]
    unsupported = [key for key in failed if key not in GEOMETRY_CHECKS]
    if unsupported:
        raise Phase1GeometryReviewError(
            "Phase 1 failure is not geometry-review eligible: "
            + ", ".join(sorted(unsupported))
        )
    return sorted(failed)


def _issue_id(issue: Mapping[str, Any]) -> str:
    return "geo_" + sha256_json(issue)[:16]


def _track_assets(root: Path, row: Mapping[str, Any]) -> list[dict[str, Any]]:
    text_id = str(row.get("text_id") or "")
    paths = {
        "crop_path": str(row.get("crop_path") or ""),
        "best_keyframe_path": str(row.get("best_keyframe_path") or ""),
        "overlay_path": f"qa/overlays/{text_id}.jpg",
        "boundary_path": f"qa/boundaries/{text_id}.jpg",
        "boundary_crop_path": f"qa/boundary_crops/{text_id}.jpg",
    }
    assets: dict[str, dict[str, Any]] = {}
    for key, raw in paths.items():
        if not raw:
            continue
        candidate = (root / raw).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            assets[key] = _ref(root, candidate, label=f"{key} evidence")
    return [{"text_id": text_id, "assets": assets}]


def prepare_phase1_geometry_review(root_dir: str | Path) -> dict[str, Any]:
    """Create (or return) the immutable Phase 1 geometry review candidate."""
    root = Path(root_dir).resolve()
    required = (
        root / "master_timeline.json",
        root / "phase1_score.json",
        root / "text_frame_coverage.json",
        root / "qa" / "quality_report.json",
        root / "phase1_meta.json",
    )
    for path in required:
        if not path.is_file():
            raise Phase1GeometryReviewError(f"Missing Phase 1 evidence: {path.name}")
    timeline = _load_list(required[0])
    score = _load_object(required[1])
    coverage = _load_object(required[2])
    quality = _load_object(required[3])
    meta = _load_object(required[4])
    if bool(score.get("PASS")):
        raise Phase1GeometryReviewError("A Phase 1 PASS case needs no geometry review")
    if not timeline or int(score.get("tracks") or 0) <= 0:
        raise Phase1GeometryReviewError("Zero-track cases must use the NO_TEXT gate")
    failed_checks = _failed_geometry_checks(score)
    by_id = {str(row.get("text_id") or ""): row for row in timeline}
    issues_by_track: dict[str, dict[str, Any]] = {}

    def add_track_issue(text_id: str, reason: str, evidence: Mapping[str, Any] | None = None) -> None:
        if text_id not in by_id:
            return
        row = issues_by_track.setdefault(
            text_id,
            {
                "issue_type": "TRACK_GEOMETRY",
                "text_id": text_id,
                "reasons": [],
                "track": {
                    key: by_id[text_id].get(key)
                    for key in ("start_frame", "end_frame", "box_coords", "hit_count", "best_frame_index")
                },
                "review_assets": _track_assets(root, by_id[text_id]),
            },
        )
        if reason not in row["reasons"]:
            row["reasons"].append(reason)
        if evidence:
            row.setdefault("evidence", {}).update(dict(evidence))

    for raw in list(quality.get("review_queue") or []):
        add_track_issue(
            str(raw.get("text_id") or ""),
            "uncertain_track",
            {"boundary_evidence": raw.get("boundary_evidence")},
        )
    for text_id in list(score.get("empty_left_wide_hardsubs") or []):
        add_track_issue(str(text_id), "edge_geometry")
    for text_id in list(score.get("isolated_micro_source_tracks") or []):
        add_track_issue(str(text_id), "isolated_micro_track")
    for text_id in list(score.get("overexpanded_dense_hardsubs") or []):
        if isinstance(text_id, list) and text_id:
            add_track_issue(str(text_id[0]), "overexpanded_geometry")
    for text_id in list(score.get("overmerged_ui_grid_tracks") or []):
        if isinstance(text_id, Mapping):
            add_track_issue(str(text_id.get("text_id") or ""), "overmerged_ui_grid")
    for text_id in list(score.get("nested_temporal_ui_fragments") or []):
        if isinstance(text_id, Mapping):
            add_track_issue(str(text_id.get("candidate_text_id") or ""), "nested_ui_fragment")

    issues: list[dict[str, Any]] = []
    for issue in issues_by_track.values():
        issue["reasons"] = sorted(issue["reasons"])
        issue["issue_id"] = _issue_id(issue)
        issues.append(issue)

    spans = [
        list(span)
        for key in ("uncovered_dense_hardsub_spans", "unresolved_residual_hardsub_spans")
        for span in list(score.get(key) or [])
        if isinstance(span, list) and len(span) >= 2
    ]
    seen_spans: set[tuple[int, int]] = set()
    for span in spans:
        key = (int(span[0]), int(span[1]))
        if key in seen_spans:
            continue
        seen_spans.add(key)
        issue = {
            "issue_type": "RESIDUAL_SPAN",
            "span": [int(span[0]), int(span[1]), int(span[2]) if len(span) > 2 else int(span[1]) - int(span[0]) + 1],
            "reasons": ["unresolved_residual_span"],
        }
        issue["issue_id"] = _issue_id(issue)
        issues.append(issue)

    # A failed eligible check without a row is still explicit operator work;
    # never silently turn it into an automatic pass.
    represented = set()
    for issue in issues:
        represented.update(
            {
                "no_uncertain_tracks" if "uncertain_track" in issue.get("reasons", []) else "",
                "no_empty_left_wide_hardsub" if "edge_geometry" in issue.get("reasons", []) else "",
                "no_isolated_micro_source_tracks" if "isolated_micro_track" in issue.get("reasons", []) else "",
                "no_overexpanded_dense_hardsubs" if "overexpanded_geometry" in issue.get("reasons", []) else "",
                "no_overmerged_ui_grid_tracks" if "overmerged_ui_grid" in issue.get("reasons", []) else "",
                "no_nested_temporal_ui_fragments" if "nested_ui_fragment" in issue.get("reasons", []) else "",
                "no_uncovered_dense_hardsub_spans" if issue.get("issue_type") == "RESIDUAL_SPAN" else "",
                "no_unresolved_residual_hardsub_spans" if issue.get("issue_type") == "RESIDUAL_SPAN" else "",
            }
        )
    for check in failed_checks:
        if check not in represented:
            issue = {
                "issue_type": "QUALITY_CHECK",
                "check": check,
                "reasons": ["quality_check_failure"],
            }
            issue["issue_id"] = _issue_id(issue)
            issues.append(issue)
    if not issues:
        raise Phase1GeometryReviewError("No actionable geometry issue was produced")

    source = _source_video(root, meta)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PHASE1_GEOMETRY_OPERATOR_REVIEW_REQUIRED",
        "created_at": _now(),
        "review_instruction": (
            "Review the complete source and each linked geometry evidence item. "
            "This gate authorizes geometry/provenance only; it never approves OCR text."
        ),
        "allowed_decisions": list(ALLOWED_DECISIONS),
        "phase1_refs": {
            "master_timeline": _ref(root, required[0], label="master timeline"),
            "phase1_score": _ref(root, required[1], label="phase1 score"),
            "text_frame_coverage": _ref(root, required[2], label="text coverage"),
            "quality_report": _ref(root, required[3], label="quality report"),
        },
        "source_video": {
            "path": str(meta.get("video") or ""),
            "sha256": sha256_file(source),
            "size_bytes": source.stat().st_size,
        },
        "frame_size": [
            int(coverage.get("frame_width") or score.get("frame_size", [1920, 1080])[0] or 1920),
            int(coverage.get("frame_height") or score.get("frame_size", [1920, 1080])[1] or 1080),
        ],
        "failed_geometry_checks": failed_checks,
        "issues": issues,
        "operator_decision": None,
    }
    existing_path = root / "phase1_geometry_review.json"
    if existing_path.is_file():
        existing = _load_object(existing_path)
        if _verify_self_hash(existing, "review_sha256"):
            if (
                existing.get("phase1_refs") == payload["phase1_refs"]
                and existing.get("source_video") == payload["source_video"]
            ):
                return existing
    payload["review_sha256"] = sha256_json(payload)
    _write_json_atomic(existing_path, payload)
    return payload


def _numeric_box(raw: Any, *, frame_w: int, frame_h: int) -> list[float]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 4:
        raise Phase1GeometryReviewError("EDIT_GEOMETRY requires box_coords[4]")
    values = [float(raw[index]) for index in range(4)]
    if not all(math.isfinite(value) for value in values):
        raise Phase1GeometryReviewError("Geometry coordinates must be finite")
    x0, y0, x1, y1 = values
    if not (0 <= x0 < x1 <= frame_w and 0 <= y0 < y1 <= frame_h):
        raise Phase1GeometryReviewError("Edited geometry is outside the frame")
    return [round(value, 3) for value in values]


def _materialize(
    root: Path,
    *,
    review: Mapping[str, Any],
    approval_sha256: str,
    decisions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    timeline = _load_list(root / "master_timeline.json")
    by_id = {str(row.get("text_id") or ""): row for row in timeline}
    approved: list[str] = []
    rejected: list[str] = []
    overrides: list[dict[str, Any]] = []
    explained: list[list[int]] = []
    for row in decisions:
        decision = str(row.get("decision") or "").upper()
        issue = next(item for item in list(review.get("issues") or []) if str(item.get("issue_id") or "") == str(row.get("issue_id") or ""))
        if issue.get("issue_type") == "TRACK_GEOMETRY":
            text_id = str(issue.get("text_id") or "")
            if decision == "APPROVE_GEOMETRY":
                approved.append(text_id)
            elif decision == "REJECT_TRACK":
                rejected.append(text_id)
            elif decision == "EDIT_GEOMETRY":
                current = by_id.get(text_id)
                if current is None:
                    raise Phase1GeometryReviewError(f"Unknown geometry track {text_id}")
                geometry = dict(row.get("geometry") or {})
                coords = _numeric_box(
                    geometry.get("box_coords"),
                    frame_w=int(review["frame_size"][0]),
                    frame_h=int(review["frame_size"][1]),
                )
                start = int(geometry.get("start_frame", current.get("start_frame") or 0))
                end = int(geometry.get("end_frame", current.get("end_frame") or start))
                if start < 0 or end < start:
                    raise Phase1GeometryReviewError("Edited frame span is invalid")
                overrides.append(
                    {
                        "target_text_id": text_id,
                        "original_box_coords": list(current.get("box_coords") or []),
                        "box_coords": coords,
                        "start_frame": start,
                        "end_frame": end,
                        "best_frame_index": int(geometry.get("best_frame_index", current.get("best_frame_index") or start)),
                        "crop_path": None,
                        "best_keyframe_path": current.get("best_keyframe_path"),
                    }
                )
            else:
                raise Phase1GeometryReviewError("EXPLAIN_SHADOW is valid only for residual spans")
        elif issue.get("issue_type") == "RESIDUAL_SPAN":
            if decision == "EXPLAIN_SHADOW":
                explained.append(list(issue.get("span") or []))
            elif decision == "EDIT_GEOMETRY":
                target = str(row.get("target_text_id") or "")
                if target not in by_id:
                    raise Phase1GeometryReviewError("Residual EDIT_GEOMETRY requires target_text_id")
                geometry = dict(row.get("geometry") or {})
                current = by_id[target]
                coords = _numeric_box(
                    geometry.get("box_coords", current.get("box_coords")),
                    frame_w=int(review["frame_size"][0]),
                    frame_h=int(review["frame_size"][1]),
                )
                overrides.append(
                    {
                        "target_text_id": target,
                        "original_box_coords": list(current.get("box_coords") or []),
                        "box_coords": coords,
                        "start_frame": int(geometry.get("start_frame", current.get("start_frame") or 0)),
                        "end_frame": int(geometry.get("end_frame", current.get("end_frame") or 0)),
                        "best_frame_index": int(geometry.get("best_frame_index", current.get("best_frame_index") or 0)),
                        "crop_path": None,
                        "best_keyframe_path": current.get("best_keyframe_path"),
                    }
                )
            else:
                raise Phase1GeometryReviewError("Residual span needs EXPLAIN_SHADOW or EDIT_GEOMETRY")
        elif decision != "APPROVE_GEOMETRY":
            raise Phase1GeometryReviewError("Quality-check issue can only be approved as geometry")

    materialized: dict[str, Any] = {
        "schema_version": MATERIALIZATION_SCHEMA_VERSION,
        "status": "PHASE1_GEOMETRY_OVERRIDES_MATERIALIZED",
        "created_at": _now(),
        "review_ref": {"path": "phase1_geometry_review.json", "sha256": review.get("review_sha256")},
        "approval_ref": {"path": "phase1_geometry_approval.json", "sha256": approval_sha256},
        "master_timeline_ref": {"path": "master_timeline.json", "sha256": sha256_file(root / "master_timeline.json")},
        "approved_track_ids": sorted(set(approved)),
        "rejected_track_ids": sorted(set(rejected)),
        "geometry_overrides": overrides,
        "explained_shadow_spans": explained,
        "ocr_authority": "NOT_APPROVED_BY_THIS_ARTIFACT",
    }
    materialized["materialization_sha256"] = sha256_json(materialized)
    _write_json_atomic(root / "phase1_geometry_overrides.json", materialized)
    return materialized


def record_phase1_geometry_decisions(
    root_dir: str | Path,
    *,
    operator_id: str,
    decisions: Sequence[Mapping[str, Any]],
    notes: str | None = None,
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    operator = str(operator_id or "").strip()
    if not operator:
        raise Phase1GeometryReviewError("Geometry approval requires operator_id")
    review = prepare_phase1_geometry_review(root)
    expected = {str(item.get("issue_id") or "") for item in list(review.get("issues") or [])}
    rows = [dict(row) for row in decisions if isinstance(row, Mapping)]
    actual = [str(row.get("issue_id") or "") for row in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise Phase1GeometryReviewError("Decisions must cover every geometry issue exactly once")
    for row in rows:
        if str(row.get("decision") or "").upper() not in ALLOWED_DECISIONS:
            raise Phase1GeometryReviewError("Unsupported Phase 1 geometry decision")
    approval: dict[str, Any] = {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "status": "PHASE1_GEOMETRY_OPERATOR_APPROVED",
        "operator_id": operator,
        "reviewed_at": _now(),
        "notes": str(notes or ""),
        "review_ref": {"path": "phase1_geometry_review.json", "sha256": review.get("review_sha256")},
        "decisions": rows,
    }
    approval["approval_sha256"] = sha256_json(approval)
    _write_json_atomic(root / "phase1_geometry_approval.json", approval)
    materialized = _materialize(
        root,
        review=review,
        approval_sha256=approval["approval_sha256"],
        decisions=rows,
    )
    return {
        **approval,
        "materialization_ref": {
            "path": "phase1_geometry_overrides.json",
            "sha256": sha256_file(root / "phase1_geometry_overrides.json"),
            "materialization_sha256": materialized["materialization_sha256"],
        },
    }


def evaluate_phase1_geometry_operator_gate(root_dir: str | Path) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    review = prepare_phase1_geometry_review(root)
    approval_path = root / "phase1_geometry_approval.json"
    if not approval_path.is_file():
        return {
            "status": "WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW",
            "next_stage": "phase1_geometry_review",
            "operator_touch_required": True,
            "review_required": 1,
            "review_sha256": review["review_sha256"],
        }
    approval = _load_object(approval_path)
    if not _verify_self_hash(approval, "approval_sha256"):
        raise Phase1GeometryApprovalError("Geometry approval self-hash is invalid", reason="INVALID_APPROVAL_SELF_HASH")
    if dict(approval.get("review_ref") or {}).get("sha256") != review.get("review_sha256"):
        raise Phase1GeometryApprovalError("Geometry approval is stale", reason="STALE_APPROVAL")
    material_path = root / "phase1_geometry_overrides.json"
    if not material_path.is_file():
        raise Phase1GeometryApprovalError("Geometry materialization is missing", reason="MISSING_MATERIALIZATION")
    material = _load_object(material_path)
    if not _verify_self_hash(material, "materialization_sha256"):
        raise Phase1GeometryApprovalError("Geometry materialization self-hash is invalid", reason="INVALID_MATERIALIZATION_SELF_HASH")
    if dict(material.get("approval_ref") or {}).get("sha256") != approval.get("approval_sha256"):
        raise Phase1GeometryApprovalError("Geometry materialization is stale", reason="STALE_MATERIALIZATION")
    master_ref = dict(material.get("master_timeline_ref") or {})
    if master_ref.get("sha256") != sha256_file(root / "master_timeline.json"):
        raise Phase1GeometryApprovalError("Geometry materialization master hash drifted", reason="MASTER_HASH_DRIFT")
    return {
        "status": "PHASE1_GEOMETRY_OPERATOR_APPROVED",
        "next_stage": "phase2",
        "operator_touch_required": False,
        "review_required": 0,
        "review_sha256": review["review_sha256"],
        "approval_sha256": approval["approval_sha256"],
        "materialization_sha256": material["materialization_sha256"],
    }


def evaluate_phase1_geometry_operator_gate_safe(root_dir: str | Path) -> dict[str, Any]:
    try:
        return evaluate_phase1_geometry_operator_gate(root_dir)
    except Phase1GeometryApprovalError as exc:
        review = prepare_phase1_geometry_review(root_dir)
        return {
            "status": "WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW",
            "next_stage": "phase1_geometry_review",
            "operator_touch_required": True,
            "review_required": 1,
            "review_sha256": review["review_sha256"],
            "approval_state": exc.reason,
        }


def load_phase1_geometry_materialization(root_dir: str | Path) -> dict[str, Any] | None:
    root = Path(root_dir).resolve()
    path = root / "phase1_geometry_overrides.json"
    if not path.is_file():
        return None
    gate = evaluate_phase1_geometry_operator_gate(root)
    if gate.get("status") != "PHASE1_GEOMETRY_OPERATOR_APPROVED":
        raise Phase1GeometryReviewError("Phase 1 geometry approval is not active")
    payload = _load_object(path)
    if not _verify_self_hash(payload, "materialization_sha256"):
        raise Phase1GeometryReviewError("Invalid Phase 1 geometry materialization")
    if dict(payload.get("master_timeline_ref") or {}).get("sha256") != sha256_file(root / "master_timeline.json"):
        raise Phase1GeometryReviewError("Stale Phase 1 geometry materialization")
    return payload


def apply_phase1_geometry_materialization(
    root_dir: str | Path,
    timeline: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Return the effective Phase 1 geometry without mutating the master file."""
    root = Path(root_dir).resolve()
    path = root / "phase1_geometry_overrides.json"
    material = load_phase1_geometry_materialization(root)
    if material is None:
        return [dict(row) for row in timeline], None
    rejected = {str(value) for value in list(material.get("rejected_track_ids") or [])}
    overrides: dict[str, dict[str, Any]] = {}
    for raw in list(material.get("geometry_overrides") or []):
        if not isinstance(raw, Mapping):
            raise Phase1GeometryReviewError("Invalid geometry override row")
        row = dict(raw)
        text_id = str(row.get("target_text_id") or "")
        if not text_id or text_id in overrides:
            raise Phase1GeometryReviewError("Duplicate or missing geometry override target")
        overrides[text_id] = row
    known = {
        str(row.get("text_id") or "")
        for row in timeline
        if isinstance(row, Mapping)
    }
    if not rejected.issubset(known) or not set(overrides).issubset(known):
        raise Phase1GeometryReviewError("Geometry materialization targets unknown tracks")
    effective: list[dict[str, Any]] = []
    for raw in timeline:
        row = dict(raw)
        text_id = str(row.get("text_id") or "")
        if text_id in rejected:
            continue
        override = overrides.get(text_id)
        if override is not None:
            if list(override.get("original_box_coords") or []) != list(
                row.get("box_coords") or []
            ):
                raise Phase1GeometryReviewError(
                    f"Original geometry drifted for {text_id}"
                )
            row.update(
                {
                    "box_coords": list(override.get("box_coords") or []),
                    "start_frame": int(override.get("start_frame") or 0),
                    "end_frame": int(override.get("end_frame") or 0),
                    "best_frame_index": int(
                        override.get("best_frame_index") or 0
                    ),
                    # The old crop represents the old box. Force Phase 2 to
                    # recrop the source video at the operator-approved box.
                    "crop_path": None,
                    "phase1_geometry_review": {
                        "status": "OPERATOR_APPROVED_OVERRIDE",
                        "materialization_sha256": material.get(
                            "materialization_sha256"
                        ),
                        "original_box_coords": list(
                            override.get("original_box_coords") or []
                        ),
                    },
                }
            )
        effective.append(row)
    if not effective:
        raise Phase1GeometryReviewError(
            "Geometry decisions rejected every track; use the full-video NO_TEXT gate"
        )
    ref = {
        "path": path.name,
        "sha256": sha256_file(path),
        "materialization_sha256": material.get("materialization_sha256"),
    }
    return effective, ref
