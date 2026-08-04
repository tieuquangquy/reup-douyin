"""Materialize an operator-approved Phase-4 residual triage batch proposal.

This adapter projects the approved batch decisions into per-case Phase-2
remediation authority.  It preserves ``master_timeline.json`` and leaves the
separate source-intrinsic false-positive decision for Phase-4 binding after
the remediated preflight is regenerated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from scripts.materialize_phase2_residual_remediation import (
    _capture_translation_authority,
    verify_remediation,
)
from src.media_pipeline.frame_sampling.phase2_ocr_contract import (
    parse_localization_policy,
)
from src.services.residual_remediation_authority import (
    ACTIVE_POINTER_NAME,
    ResidualRemediationAuthorityError,
    build_active_remediation_pointer,
    resolve_active_residual_remediation,
)


SCHEMA_VERSION = "phase4_residual_triage_materialization_index_v1"
_SIGNATURE_RE = re.compile(r"[0-9\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


class ResidualTriageMaterializationError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResidualTriageMaterializationError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise ResidualTriageMaterializationError(
            f"{path.name} must contain an object"
        )
    return payload


def _load_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResidualTriageMaterializationError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, list):
        raise ResidualTriageMaterializationError(
            f"{path.name} must contain a list"
        )
    return [dict(row) for row in payload if isinstance(row, Mapping)]


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


def _verify_self_hash(
    payload: Mapping[str, Any], field: str, *, label: str
) -> None:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    if len(claimed) != 64 or claimed != _sha256_json(unsigned):
        raise ResidualTriageMaterializationError(f"{label} self-hash is invalid")


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _merge_cumulative_remediation(
    *,
    root: Path,
    parent_path: Path | None,
    delta: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(delta)
    if parent_path is None:
        merged["generation"] = 1
        return merged
    parent = _load_object(parent_path)
    if not verify_remediation(parent):
        raise ResidualTriageMaterializationError(
            "Parent residual remediation self-hash is invalid"
        )
    parent_master = dict(
        dict(parent.get("authority_refs") or {}).get("master_timeline") or {}
    )
    delta_master = dict(
        dict(delta.get("authority_refs") or {}).get("master_timeline") or {}
    )
    if str(parent_master.get("sha256") or "") != str(
        delta_master.get("sha256") or ""
    ):
        raise ResidualTriageMaterializationError(
            "Cumulative remediation targets another Phase 1 authority"
        )

    parent_occurrences = [
        dict(row)
        for row in list(parent.get("approved_occurrences") or [])
        if isinstance(row, Mapping)
    ]
    delta_occurrences = [
        dict(row)
        for row in list(delta.get("approved_occurrences") or [])
        if isinstance(row, Mapping)
    ]
    occurrence_ids = [
        str(dict(row.get("occurrence") or {}).get("text_id") or "")
        for row in [*parent_occurrences, *delta_occurrences]
    ]
    if any(not value for value in occurrence_ids) or len(set(occurrence_ids)) != len(
        occurrence_ids
    ):
        raise ResidualTriageMaterializationError(
            "Cumulative remediation contains duplicate occurrence ids"
        )

    parent_overrides = [
        dict(row)
        for row in list(parent.get("approved_geometry_overrides") or [])
        if isinstance(row, Mapping)
    ]
    delta_overrides = [
        dict(row)
        for row in list(delta.get("approved_geometry_overrides") or [])
        if isinstance(row, Mapping)
    ]
    override_ids = [
        str(
            dict(row.get("geometry_override") or {}).get("target_text_id") or ""
        )
        for row in [*parent_overrides, *delta_overrides]
    ]
    if any(not value for value in override_ids) or len(set(override_ids)) != len(
        override_ids
    ):
        raise ResidualTriageMaterializationError(
            "Cumulative remediation contains duplicate geometry overrides"
        )

    parent_false = [
        dict(row)
        for row in list(parent.get("false_positive_decisions_deferred_to_phase4") or [])
        if isinstance(row, Mapping)
    ]
    delta_false = [
        dict(row)
        for row in list(delta.get("false_positive_decisions_deferred_to_phase4") or [])
        if isinstance(row, Mapping)
    ]
    false_keys = [
        (str(row.get("cluster_id") or ""), str(row.get("source_text") or ""))
        for row in [*parent_false, *delta_false]
    ]
    if len(set(false_keys)) != len(false_keys):
        raise ResidualTriageMaterializationError(
            "Cumulative remediation contains duplicate false-positive decisions"
        )

    authority = dict(delta.get("authority_refs") or {})
    authority["parent_remediation"] = {
        "path": parent_path.relative_to(root).as_posix(),
        "sha256": _sha256_file(parent_path),
        "remediation_sha256": parent.get("remediation_sha256"),
    }
    merged.update(
        {
            "authority_refs": authority,
            "approved_occurrences": [*parent_occurrences, *delta_occurrences],
            "approved_geometry_overrides": [*parent_overrides, *delta_overrides],
            "false_positive_decisions_deferred_to_phase4": [
                *parent_false,
                *delta_false,
            ],
            "generation": int(parent.get("generation") or 1) + 1,
            "delta_counts": {
                "occurrences": len(delta_occurrences),
                "geometry_overrides": len(delta_overrides),
                "false_positive_deferred": len(delta_false),
            },
        }
    )
    return merged


def _write_jpeg_atomic(path: Path, image: np.ndarray) -> None:
    import cv2

    ok, encoded = cv2.imencode(
        ".jpg", np.asarray(image), [int(cv2.IMWRITE_JPEG_QUALITY), 94]
    )
    if not ok:
        raise ResidualTriageMaterializationError(
            f"Cannot encode remediation crop: {path.name}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encoded.tobytes())
    temporary.replace(path)


def _safe_ref(root: Path, raw_path: str, *, label: str) -> Path:
    path = (root / raw_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ResidualTriageMaterializationError(f"Invalid {label} path")
    return path


def _verify_ref(
    root: Path, ref: Mapping[str, Any], *, label: str
) -> Path:
    path = _safe_ref(root, str(ref.get("path") or ""), label=label)
    if str(ref.get("sha256") or "") != _sha256_file(path):
        raise ResidualTriageMaterializationError(f"Stale {label} artifact")
    return path


def _signature(value: str) -> str:
    return "".join(_SIGNATURE_RE.findall(str(value or "")))


def _rect(raw: Mapping[str, Any]) -> tuple[float, float, float, float]:
    try:
        x = float(raw.get("x") or 0.0)
        y = float(raw.get("y") or 0.0)
        width = float(raw.get("width") or 0.0)
        height = float(raw.get("height") or 0.0)
    except (TypeError, ValueError) as exc:
        raise ResidualTriageMaterializationError("Geometry is invalid") from exc
    if (
        width <= 0
        or height <= 0
        or min(x, y) < 0
        or x + width > 1.001
        or y + height > 1.001
    ):
        raise ResidualTriageMaterializationError("Geometry is out of bounds")
    return x, y, x + width, y + height


def _normalized_master_geometry(
    row: Mapping[str, Any], *, width: int, height: int
) -> dict[str, float] | None:
    coords = list(row.get("box_coords") or [])
    if len(coords) != 4:
        return None
    try:
        x0, y0, x1, y1 = [float(value) for value in coords]
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return {
        "x": x0 / width,
        "y": y0 / height,
        "width": (x1 - x0) / width,
        "height": (y1 - y0) / height,
    }


def _center_distance(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> float:
    lx0, ly0, lx1, ly1 = _rect(left)
    rx0, ry0, rx1, ry1 = _rect(right)
    return math.hypot((lx0 + lx1 - rx0 - rx1) / 2.0, (ly0 + ly1 - ry0 - ry1) / 2.0)


def _resolve_temporal_window(
    *,
    proposed_occurrence: Mapping[str, Any],
    master: Sequence[Mapping[str, Any]],
    frame_count: int,
    frame_width: int,
    frame_height: int,
) -> tuple[int, int, dict[str, Any]]:
    anchor = int(proposed_occurrence.get("representative_frame_index") or 0)
    geometry = dict(proposed_occurrence.get("geometry") or {})
    temporal = dict(proposed_occurrence.get("temporal") or {})
    strategy = str(temporal.get("strategy") or "")
    if not 0 <= anchor < frame_count:
        raise ResidualTriageMaterializationError(
            "Representative frame is outside video authority"
        )
    if strategy == "SOURCE_BOUNDARY_RESCAN_REQUIRED":
        previous_ends = [
            int(row.get("end_frame") or 0)
            for row in master
            if int(row.get("end_frame") or 0) < anchor
        ]
        next_starts = [
            int(row.get("start_frame") or 0)
            for row in master
            if int(row.get("start_frame") or 0) > anchor
        ]
        start = max(previous_ends) + 1 if previous_ends else 0
        end = min(next_starts) - 1 if next_starts else frame_count - 1
        if not start <= anchor <= end or end - start + 1 > 120:
            raise ResidualTriageMaterializationError(
                "Source-only temporal gap is ambiguous"
            )
        return start, end, {
            "method": "phase1_gap_bounded_source_rescan",
            "anchor_frame": anchor,
            "phase1_gap": [start, end],
        }
    if strategy != "ALIGN_AND_RESCAN_FROM_PHASE1_WINDOW":
        raise ResidualTriageMaterializationError(
            "Unsupported approved temporal strategy"
        )
    reference_window = list(temporal.get("reference_window") or [])
    if len(reference_window) != 2:
        raise ResidualTriageMaterializationError(
            "Approved temporal reference is missing"
        )
    envelope_start, envelope_end = [int(value) for value in reference_window]
    candidates: list[tuple[float, tuple[int, int], str]] = []
    for raw in master:
        row = dict(raw)
        start = int(row.get("start_frame") or 0)
        end = int(row.get("end_frame") or start)
        if not start <= anchor <= end:
            continue
        normalized = _normalized_master_geometry(
            row, width=frame_width, height=frame_height
        )
        if normalized is None:
            continue
        candidates.append(
            (
                _center_distance(geometry, normalized),
                (max(start, envelope_start), min(end, envelope_end)),
                str(row.get("text_id") or ""),
            )
        )
    nearest = sorted(candidates, key=lambda item: item[0])[:5]
    valid_windows = [window for _distance, window, _text_id in nearest if window[0] <= anchor <= window[1]]
    counts = Counter(valid_windows)
    if counts and counts.most_common(1)[0][1] >= 2:
        (start, end), support = counts.most_common(1)[0]
        method = "nearest_phase1_window_consensus"
    else:
        start, end = envelope_start, envelope_end
        support = 1
        method = "approved_phase1_reference_window"
    if not 0 <= start <= anchor <= end < frame_count or end - start + 1 > 180:
        raise ResidualTriageMaterializationError(
            "Resolved temporal window is unsafe"
        )
    return start, end, {
        "method": method,
        "anchor_frame": anchor,
        "approved_reference_text_id": temporal.get("reference_text_id"),
        "approved_reference_window": [envelope_start, envelope_end],
        "nearest_phase1_windows": [
            {"text_id": text_id, "window": list(window), "distance": round(distance, 6)}
            for distance, window, text_id in nearest
        ],
        "selected_support": support,
    }


def _timecode(frame_index: int, fps: float) -> str:
    milliseconds = int(round(frame_index * 1000.0 / max(fps, 0.001)))
    seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f"{hours:02d}:{minute:02d}:{sec:02d}.{ms:03d}"


def _localization(source_text: str, vi_text: str, *, decision_ref: str) -> dict[str, Any]:
    policy = parse_localization_policy(source_text)
    if str(policy.get("mode") or "") == "deterministic":
        suggested = str(policy.get("render_text_suggested") or "").strip()
        if suggested != vi_text:
            raise ResidualTriageMaterializationError(
                f"Deterministic localization drift: {source_text} -> {suggested}"
            )
        return policy
    return {
        **policy,
        "mode": "translation_review_required",
        "render_text_suggested": vi_text,
        "suggestion_source": decision_ref,
        "operator_approval_written": True,
    }


def _evidence_row(
    cluster: Mapping[str, Any], *, frame_index: int
) -> dict[str, Any]:
    rows = [dict(row) for row in list(cluster.get("evidence_frames") or [])]
    exact = [row for row in rows if int(row.get("frame_index") or 0) == frame_index]
    if exact:
        return exact[0]
    if not rows:
        raise ResidualTriageMaterializationError("Cluster evidence is missing")
    return min(
        rows,
        key=lambda row: abs(int(row.get("frame_index") or 0) - frame_index),
    )


def _write_decision_crop(
    *,
    root: Path,
    cluster: Mapping[str, Any],
    geometry: Mapping[str, Any],
    frame_index: int,
    remediation_id: str,
) -> tuple[Path, Path]:
    import cv2

    evidence = _evidence_row(cluster, frame_index=frame_index)
    source_ref = dict(evidence.get("source_frame_ref") or {})
    source_path = _verify_ref(root, source_ref, label="decision source frame")
    frame = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
    if frame is None:
        raise ResidualTriageMaterializationError(
            "Decision source frame is unreadable"
        )
    height, width = frame.shape[:2]
    x0, y0, x1, y1 = _rect(geometry)
    # Keep multi-line title/value cards separated. The detector geometry is
    # already operator-approved, so a small anti-aliasing margin is enough.
    margin = max(8, int(round(max((x1 - x0) * width, (y1 - y0) * height) * 0.04)))
    px0 = max(0, int(math.floor(x0 * width)) - margin)
    py0 = max(0, int(math.floor(y0 * height)) - margin)
    px1 = min(width, int(math.ceil(x1 * width)) + margin)
    py1 = min(height, int(math.ceil(y1 * height)) + margin)
    crop = frame[py0:py1, px0:px1]
    if crop.size == 0:
        raise ResidualTriageMaterializationError("Decision crop is empty")
    crop_path = (
        root
        / "qa"
        / "phase2_residual_decision_materialization"
        / remediation_id
        / "source_crop.jpg"
    )
    _write_jpeg_atomic(crop_path, crop)
    return source_path, crop_path


def _accepted_signatures(
    cluster: Mapping[str, Any], source_text: str
) -> list[str]:
    values = {_signature(source_text), str(cluster.get("signature") or "")}
    values.update(
        _signature(str(dict(row).get("text") or ""))
        for row in list(cluster.get("detections") or [])
    )
    return sorted(value for value in values if value)


def _visual_override_ref(
    *,
    root: Path,
    cluster: Mapping[str, Any],
    source_text: str,
    source_path: Path,
    crop_path: Path,
    proposal_sha256: str,
) -> dict[str, Any]:
    return {
        "policy_version": "phase2_operator_visual_override_v1",
        "batch_decision_proposal_sha256": proposal_sha256,
        "cluster_id": cluster.get("cluster_id"),
        "cluster_evidence_sha256": _sha256_json(cluster),
        "approved_source_text_sha256": hashlib.sha256(
            source_text.encode("utf-8")
        ).hexdigest(),
        "source_frame_ref": {
            "path": source_path.relative_to(root).as_posix(),
            "sha256": _sha256_file(source_path),
        },
        "crop_ref": {
            "path": crop_path.relative_to(root).as_posix(),
            "sha256": _sha256_file(crop_path),
        },
    }


def _build_case_projection(
    *,
    run: Path,
    proposal_path: Path,
    case_proposal: Mapping[str, Any],
    batch_proposal: Mapping[str, Any],
    approval_token: str,
    operator_id: str,
    approved_at: str,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    case_id = str(case_proposal.get("case_id") or "")
    root = (run / case_id).resolve()
    if not root.is_relative_to(run) or not root.is_dir():
        raise ResidualTriageMaterializationError(
            f"Invalid case root: {case_id or 'unknown'}"
        )
    for label, ref in dict(case_proposal.get("authority_refs") or {}).items():
        _verify_ref(root, dict(ref), label=f"{case_id} {label}")
    visual_ref = dict(case_proposal.get("visual_triage_ref") or {})
    visual_path = _verify_ref(run, visual_ref, label=f"{case_id} visual triage")
    visual = _load_object(visual_path)
    _verify_self_hash(visual, "triage_sha256", label=f"{case_id} visual triage")
    clusters = {
        str(row.get("cluster_id") or ""): dict(row)
        for row in list(visual.get("clusters") or [])
        if isinstance(row, Mapping)
    }
    master_path = root / "master_timeline.json"
    phase2_path = root / "phase2_ocr_timeline.json"
    master = _load_list(master_path)
    phase2_before = _load_object(phase2_path)
    master_by_id = {
        str(row.get("text_id") or ""): row
        for row in master
        if str(row.get("text_id") or "")
    }
    phase2_content_by_geometry = {
        str(text_id): dict(row)
        for row in list(phase2_before.get("content_objects") or [])
        if isinstance(row, Mapping)
        for text_id in list(dict(row).get("geometry_refs") or [])
        if str(text_id)
    }
    video = dict(visual.get("video") or {})
    frame_width = int(video.get("frame_width") or 0)
    frame_height = int(video.get("frame_height") or 0)
    frame_count = int(video.get("frame_count") or 0)
    fps = float(video.get("fps") or 0.0)
    if min(frame_width, frame_height, frame_count) < 1 or fps <= 0:
        raise ResidualTriageMaterializationError(
            f"{case_id} video authority is invalid"
        )
    approved_occurrences: list[dict[str, Any]] = []
    approved_overrides: list[dict[str, Any]] = []
    false_positive_decisions: list[dict[str, Any]] = []
    linked_coverage_decisions: list[dict[str, Any]] = []
    projection_changes: list[dict[str, Any]] = []
    proposal_sha = str(batch_proposal.get("proposal_sha256") or "")
    proposal_decisions = {
        str(dict(row).get("cluster_id") or ""): dict(row)
        for row in list(case_proposal.get("decisions") or [])
        if isinstance(row, Mapping)
    }
    for raw in list(case_proposal.get("decisions") or []):
        decision = dict(raw)
        cluster_id = str(decision.get("cluster_id") or "")
        cluster = clusters.get(cluster_id)
        if cluster is None or str(decision.get("proposal_status") or "") != "OPERATOR_REVIEW_REQUIRED":
            raise ResidualTriageMaterializationError(
                f"Approved decision cluster drifted: {case_id}/{cluster_id}"
            )
        if str(decision.get("cluster_evidence_sha256") or "") != _sha256_json(cluster):
            raise ResidualTriageMaterializationError(
                f"Approved decision evidence drifted: {case_id}/{cluster_id}"
            )
        action = str(decision.get("proposed_action") or "")
        if action == "COVERED_BY_PROPOSED_OCCURRENCE":
            linked_cluster_id = str(decision.get("linked_cluster_id") or "")
            linked = dict(proposal_decisions.get(linked_cluster_id) or {})
            if (
                str(linked.get("proposed_action") or "")
                != "ADD_PHASE2_OCCURRENCE"
                or str(linked.get("source_text_suggested") or "")
                != str(decision.get("source_text_suggested") or "")
                or str(linked.get("vi_text_suggested") or "")
                != str(decision.get("vi_text_suggested") or "")
            ):
                raise ResidualTriageMaterializationError(
                    f"Linked residual decision drifted: {case_id}/{cluster_id}"
                )
            linked_row = {
                "cluster_id": cluster_id,
                "linked_cluster_id": linked_cluster_id,
                "source_text": decision.get("source_text_suggested"),
                "vi_text": decision.get("vi_text_suggested"),
                "visual_evidence_ref": decision.get("visual_evidence_ref"),
            }
            linked_coverage_decisions.append(linked_row)
            projection_changes.append(
                {**decision, "materialized_linked_coverage": linked_row}
            )
            continue
        if action == "APPROVE_SOURCE_INTRINSIC_FALSE_POSITIVE":
            false_positive_decisions.append(
                {
                    "cluster_id": cluster_id,
                    "source_text": decision.get("source_text_suggested"),
                    "frame_index": int(cluster.get("representative_frame_index") or 0),
                    "scope": decision.get("false_positive_scope"),
                    "visual_evidence_ref": decision.get("visual_evidence_ref"),
                }
            )
            projection_changes.append(decision)
            continue
        source_text = str(decision.get("source_text_suggested") or "")
        vi_text = str(decision.get("vi_text_suggested") or "")
        accepted = _accepted_signatures(cluster, source_text)
        identity = hashlib.sha256(
            json.dumps(
                {
                    "case_id": case_id,
                    "cluster_id": cluster_id,
                    "action": action,
                    "source_text": source_text,
                    "vi_text": vi_text,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:12]
        remediation_id = f"p2r_dec_{identity}"
        operator_review = {
            "decision": (
                "APPROVE"
                if _signature(source_text) == str(cluster.get("signature") or "")
                else "EDIT"
            ),
            "reviewer": operator_id,
            "reviewed_at": approved_at,
            "proposal_sha256": proposal_sha,
            "approval_token": approval_token,
        }
        if action == "ADD_PHASE2_OCCURRENCE":
            proposed = dict(decision.get("proposed_occurrence") or {})
            geometry = dict(proposed.get("geometry") or {})
            start, end, boundary = _resolve_temporal_window(
                proposed_occurrence=proposed,
                master=master,
                frame_count=frame_count,
                frame_width=frame_width,
                frame_height=frame_height,
            )
            representative = int(proposed.get("representative_frame_index") or 0)
            source_path, crop_path = _write_decision_crop(
                root=root,
                cluster=cluster,
                geometry=geometry,
                frame_index=representative,
                remediation_id=remediation_id,
            )
            x0, y0, x1, y1 = _rect(geometry)
            detection_frames = sorted(
                {
                    int(row.get("frame_index") or 0)
                    for row in list(cluster.get("detections") or [])
                    if start <= int(dict(row).get("frame_index") or 0) <= end
                }
            )
            occurrence = {
                "text_id": remediation_id,
                "start_frame": start,
                "end_frame": end,
                "start_time": _timecode(start, fps),
                "end_time": _timecode(end + 1, fps),
                "box_coords": [
                    round(x0 * frame_width, 4),
                    round(y0 * frame_height, 4),
                    round(x1 * frame_width, 4),
                    round(y1 * frame_height, 4),
                ],
                "best_keyframe_path": source_path.relative_to(root).as_posix(),
                "crop_path": crop_path.relative_to(root).as_posix(),
                "best_frame_index": representative,
                "hit_frames": detection_frames or [representative],
                "boundary_evidence": {
                    "status": "operator_approved_visual_window_rescan",
                    **boundary,
                    "observed_detection_frames": detection_frames,
                    "approved_decision_proposal_sha256": proposal_sha,
                },
            }
            approved_occurrences.append(
                {
                    "remediation_id": remediation_id,
                    "occurrence": occurrence,
                    "ocr_text_approved": source_text,
                    "vi_text_approved": vi_text,
                    "accepted_candidate_signatures": accepted,
                    "visual_override": _visual_override_ref(
                        root=root,
                        cluster=cluster,
                        source_text=source_text,
                        source_path=source_path,
                        crop_path=crop_path,
                        proposal_sha256=proposal_sha,
                    ),
                    "localization": _localization(
                        source_text,
                        vi_text,
                        decision_ref=proposal_path.name,
                    ),
                    "operator_review": operator_review,
                }
            )
            projection_changes.append(
                {**decision, "materialized_occurrence": occurrence}
            )
            continue
        if action != "EXPAND_EXISTING_PHASE2_GEOMETRY":
            raise ResidualTriageMaterializationError(
                f"Unsupported approved action: {action}"
            )
        target_text_id = str(decision.get("target_text_id") or "")
        target = dict(master_by_id.get(target_text_id) or {})
        target_content = dict(phase2_content_by_geometry.get(target_text_id) or {})
        accepted = sorted(
            {
                *accepted,
                *(
                    _signature(str(value))
                    for value in list(
                        target_content.get("ocr_text_raw_candidates") or []
                    )
                ),
                _signature(str(target_content.get("ocr_text_candidate") or "")),
                _signature(str(target_content.get("ocr_text_llm_suggested") or "")),
            }
            - {""}
        )
        original = list(target.get("box_coords") or [])
        if len(original) != 4:
            raise ResidualTriageMaterializationError(
                f"Geometry target is invalid: {target_text_id}"
            )
        detector = max(
            list(cluster.get("detections") or []),
            key=lambda row: float(dict(row).get("confidence") or 0.0),
        )
        residual_rect = _rect(dict(dict(detector).get("geometry") or {}))
        original_rect = (
            float(original[0]) / frame_width,
            float(original[1]) / frame_height,
            float(original[2]) / frame_width,
            float(original[3]) / frame_height,
        )
        expanded = (
            min(original_rect[0], residual_rect[0]),
            min(original_rect[1], residual_rect[1]),
            max(original_rect[2], residual_rect[2]),
            max(original_rect[3], residual_rect[3]),
        )
        geometry = {
            "x": expanded[0],
            "y": expanded[1],
            "width": expanded[2] - expanded[0],
            "height": expanded[3] - expanded[1],
        }
        representative = int(dict(detector).get("frame_index") or 0)
        source_path, crop_path = _write_decision_crop(
            root=root,
            cluster=cluster,
            geometry=geometry,
            frame_index=representative,
            remediation_id=remediation_id,
        )
        override = {
            "target_text_id": target_text_id,
            "start_frame": int(target.get("start_frame") or 0),
            "end_frame": int(target.get("end_frame") or 0),
            "start_time": target.get("start_time"),
            "end_time": target.get("end_time"),
            "original_box_coords": original,
            "box_coords": [
                round(expanded[0] * frame_width, 4),
                round(expanded[1] * frame_height, 4),
                round(expanded[2] * frame_width, 4),
                round(expanded[3] * frame_height, 4),
            ],
            "best_keyframe_path": source_path.relative_to(root).as_posix(),
            "crop_path": crop_path.relative_to(root).as_posix(),
            "best_frame_index": representative,
            "hit_frames": [representative],
            "boundary_evidence": {
                "status": "operator_approved_visual_geometry_union",
                "target_text_id": target_text_id,
                "approved_decision_proposal_sha256": proposal_sha,
            },
        }
        approved_overrides.append(
            {
                "remediation_id": remediation_id,
                "geometry_override": override,
                "ocr_text_approved": source_text,
                "vi_text_approved": vi_text,
                "accepted_candidate_signatures": accepted,
                "visual_override": _visual_override_ref(
                    root=root,
                    cluster=cluster,
                    source_text=source_text,
                    source_path=source_path,
                    crop_path=crop_path,
                    proposal_sha256=proposal_sha,
                ),
                "localization": {
                    "mode": "translation_carry_forward_exact",
                    "content_id": decision.get("target_content_id"),
                },
                "operator_review": {**operator_review, "decision": "EDIT"},
            }
        )
        projection_changes.append(
            {**decision, "materialized_geometry_override": override}
        )

    projection: dict[str, Any] = {
        "schema_version": "phase2_residual_decision_projection_v1",
        "status": "OPERATOR_APPROVED_DECISION_PROJECTION",
        "case_id": case_id,
        "approved_at": approved_at,
        "operator_id": operator_id,
        "approval_token": approval_token,
        "batch_proposal_ref": {
            "path": (Path("..") / proposal_path.relative_to(run)).as_posix(),
            "sha256": _sha256_file(proposal_path),
            "proposal_sha256": proposal_sha,
        },
        "changes": projection_changes,
        "false_positive_decisions": false_positive_decisions,
        "linked_coverage_decisions": linked_coverage_decisions,
    }
    projection["projection_sha256"] = _sha256_json(projection)
    proposal_seed = proposal_sha[:12]
    projection_name = (
        "phase2_residual_remediation_decision_projection.json"
        if proposal_path.name == "phase4_residual_triage_decision_proposal.json"
        else f"phase2_residual_remediation_decision_projection_{proposal_seed}.json"
    )
    projection_path = root / projection_name
    authority_refs = {
        "master_timeline": {
            "path": master_path.name,
            "sha256": _sha256_file(master_path),
        },
        "phase2_timeline_before_remediation": case_proposal.get(
            "authority_refs", {}
        ).get("phase2_ocr_timeline"),
        "phase3_handoff_before_remediation": case_proposal.get(
            "authority_refs", {}
        ).get("phase3_render_handoff"),
        "visual_triage": visual_ref,
        "batch_decision_proposal": projection["batch_proposal_ref"],
    }
    remediation: dict[str, Any] = {
        "schema_version": "phase2_residual_remediation_v2",
        "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
        "approved_at": approved_at,
        "operator_id": operator_id,
        "proposal_ref": {
            "path": projection_path.name,
            "file_sha256": "PENDING_PROJECTION_WRITE",
            "proposal_sha256": proposal_sha,
        },
        "authority_refs": authority_refs,
        "approved_occurrences": approved_occurrences,
        "approved_geometry_overrides": approved_overrides,
        "translation_carry_forward": _capture_translation_authority(root),
        "false_positive_decisions_deferred_to_phase4": false_positive_decisions,
    }
    return projection_path, projection, remediation


def materialize_batch(
    *,
    run_root: str | Path,
    proposal_path: str | Path,
    approval_token: str,
    operator_id: str,
    approved_at: str,
    case_ids: Sequence[str] = (),
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    proposal_file = Path(proposal_path).resolve()
    if not proposal_file.is_relative_to(run) or not proposal_file.is_file():
        raise ResidualTriageMaterializationError(
            "Approved decision proposal is outside the batch run"
        )
    proposal = _load_object(proposal_file)
    _verify_self_hash(proposal, "proposal_sha256", label="Decision proposal")
    token = str(approval_token or "").strip()
    operator = str(operator_id or "").strip()
    timestamp = str(approved_at or "").strip()
    if (
        str(proposal.get("status") or "")
        != "RESIDUAL_TRIAGE_DECISION_PROPOSAL_READY_FOR_OPERATOR_REVIEW"
        or token != str(proposal.get("operator_approval_token") or "")
        or not operator
        or not timestamp
    ):
        raise ResidualTriageMaterializationError(
            "Operator approval token or identity is invalid"
        )
    _verify_ref(
        run,
        dict(proposal.get("batch_visual_triage_ref") or {}),
        label="batch visual triage",
    )
    _verify_ref(
        run,
        dict(proposal.get("curated_input_ref") or {}),
        label="curated decision input",
    )
    all_cases = [
        dict(row)
        for row in list(proposal.get("cases") or [])
        if isinstance(row, Mapping)
    ]
    available_ids = {str(row.get("case_id") or "") for row in all_cases}
    selected_ids = {str(value) for value in case_ids if str(value)}
    if selected_ids and not selected_ids.issubset(available_ids):
        raise ResidualTriageMaterializationError(
            f"Unknown case selection: {sorted(selected_ids - available_ids)}"
        )
    staged: list[tuple[str, Path, dict[str, Any], dict[str, Any]]] = []
    for case in all_cases:
        if selected_ids and str(case.get("case_id") or "") not in selected_ids:
            continue
        projection_path, projection, remediation = _build_case_projection(
            run=run,
            proposal_path=proposal_file,
            case_proposal=case,
            batch_proposal=proposal,
            approval_token=token,
            operator_id=operator,
            approved_at=timestamp,
        )
        staged.append((str(case.get("case_id") or ""), projection_path, projection, remediation))
    if not staged:
        raise ResidualTriageMaterializationError("Decision proposal has no cases")

    proposal_sha = str(proposal.get("proposal_sha256") or "")
    versioned_generation = (
        proposal_file.name != "phase4_residual_triage_decision_proposal.json"
    )
    index_path = run / (
        f"phase4_residual_triage_materialization_index_{proposal_sha[:12]}.json"
        if versioned_generation
        else "phase4_residual_triage_materialization_index.json"
    )
    case_rows_by_id: dict[str, dict[str, Any]] = {}
    if index_path.is_file():
        previous = _load_object(index_path)
        _verify_self_hash(
            previous,
            "materialization_sha256",
            label="Previous materialization index",
        )
        previous_ref = dict(previous.get("decision_proposal_ref") or {})
        if (
            str(previous.get("approval_token") or "") != token
            or str(previous_ref.get("proposal_sha256") or "")
            != str(proposal.get("proposal_sha256") or "")
        ):
            raise ResidualTriageMaterializationError(
                "Previous materialization index belongs to another approval"
            )
        for raw in list(previous.get("cases") or []):
            row = dict(raw)
            _verify_ref(
                run,
                dict(row.get("projection_ref") or {}),
                label="previous materialization projection",
            )
            _verify_ref(
                run,
                dict(row.get("remediation_ref") or {}),
                label="previous materialization remediation",
            )
        return previous
    for case_id, projection_path, projection, remediation in staged:
        _write_json_atomic(projection_path, projection)
        remediation["proposal_ref"]["file_sha256"] = _sha256_file(projection_path)
        try:
            parent_path = resolve_active_residual_remediation(
                projection_path.parent
            )
        except ResidualRemediationAuthorityError as exc:
            raise ResidualTriageMaterializationError(str(exc)) from exc
        merged_remediation = _merge_cumulative_remediation(
            root=projection_path.parent,
            parent_path=parent_path,
            delta=remediation,
        )
        merged_remediation["remediation_sha256"] = _sha256_json(
            merged_remediation
        )
        if not verify_remediation(merged_remediation):
            raise ResidualTriageMaterializationError(
                f"Materialized remediation self-hash is invalid: {case_id}"
            )
        remediation_path = projection_path.parent / (
            f"phase2_residual_remediation_{proposal_sha[:12]}.json"
            if versioned_generation
            else "phase2_residual_remediation.json"
        )
        _write_json_atomic(remediation_path, merged_remediation)
        pointer_path: Path | None = None
        if versioned_generation:
            pointer = build_active_remediation_pointer(
                root=projection_path.parent,
                remediation_path=remediation_path,
                remediation_sha256=str(
                    merged_remediation.get("remediation_sha256") or ""
                ),
            )
            pointer_path = projection_path.parent / ACTIVE_POINTER_NAME
            _write_json_atomic(pointer_path, pointer)
        case_rows_by_id[case_id] = {
                "case_id": case_id,
                "projection_ref": {
                    "path": projection_path.relative_to(run).as_posix(),
                    "sha256": _sha256_file(projection_path),
                    "projection_sha256": projection.get("projection_sha256"),
                },
                "remediation_ref": {
                    "path": remediation_path.relative_to(run).as_posix(),
                    "sha256": _sha256_file(remediation_path),
                    "remediation_sha256": merged_remediation.get(
                        "remediation_sha256"
                    ),
                },
                **(
                    {
                        "active_pointer_ref": {
                            "path": pointer_path.relative_to(run).as_posix(),
                            "sha256": _sha256_file(pointer_path),
                        }
                    }
                    if pointer_path is not None
                    else {}
                ),
                "counts": {
                    "occurrences": len(
                        merged_remediation["approved_occurrences"]
                    ),
                    "geometry_overrides": len(
                        merged_remediation["approved_geometry_overrides"]
                    ),
                    "false_positive_deferred": len(
                        merged_remediation[
                            "false_positive_decisions_deferred_to_phase4"
                        ]
                    ),
                },
                "delta_counts": merged_remediation.get("delta_counts") or {
                    "occurrences": len(remediation["approved_occurrences"]),
                    "geometry_overrides": len(
                        remediation["approved_geometry_overrides"]
                    ),
                    "false_positive_deferred": len(
                        remediation["false_positive_decisions_deferred_to_phase4"]
                    ),
                },
            }
    case_rows = [case_rows_by_id[key] for key in sorted(case_rows_by_id)]
    index: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PHASE2_RESIDUAL_TRIAGE_DECISIONS_MATERIALIZED",
        "approved_at": timestamp,
        "operator_id": operator,
        "approval_token": token,
        "decision_proposal_ref": {
            "path": proposal_file.relative_to(run).as_posix(),
            "sha256": _sha256_file(proposal_file),
            "proposal_sha256": proposal.get("proposal_sha256"),
        },
        "counts": {
            "cases": len(case_rows),
            "occurrences": sum(row["counts"]["occurrences"] for row in case_rows),
            "geometry_overrides": sum(
                row["counts"]["geometry_overrides"] for row in case_rows
            ),
            "false_positive_deferred": sum(
                row["counts"]["false_positive_deferred"] for row in case_rows
            ),
        },
        "cases": case_rows,
    }
    index["materialization_sha256"] = _sha256_json(index)
    _write_json_atomic(index_path, index)
    return index


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.materialize_phase4_residual_triage_decisions"
    )
    parser.add_argument("run_root")
    parser.add_argument("proposal_json")
    parser.add_argument("--approval-token", required=True)
    parser.add_argument("--operator", default="operator-user-approved-v22-1")
    parser.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args()
    try:
        payload = materialize_batch(
            run_root=args.run_root,
            proposal_path=args.proposal_json,
            approval_token=args.approval_token,
            operator_id=args.operator,
            approved_at=datetime.now(timezone.utc).isoformat(),
            case_ids=args.case_id,
        )
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "counts": payload["counts"],
                    "materialization_sha256": payload[
                        "materialization_sha256"
                    ],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, ResidualTriageMaterializationError) as exc:
        print(f"[RESIDUAL-TRIAGE-MATERIALIZE][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
