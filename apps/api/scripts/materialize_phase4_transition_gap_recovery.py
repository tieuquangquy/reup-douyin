"""Recover OCR-confirmed editor-text gaps between equivalent localized tracks."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.media_pipeline.video_renderer.adaptive_output_qa import (
    build_local_residual_ocr_provider,
    contains_cjk,
)
from src.media_pipeline.video_renderer.phase4_approvals import (
    Phase4ApprovalError,
    load_residual_cjk_false_positive_approval,
)
from src.media_pipeline.video_renderer.phase4_input_contract import (
    _resolve_phase1_source_path,
)
from src.media_pipeline.video_renderer.visual_remediation import (
    ACTIVE_POINTER_NAME,
    _sha256_json,
    _timing,
    apply_visual_remediation,
    load_active_visual_remediation,
)


POLICY_VERSION = "phase4_transition_gap_recovery_v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _write_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def archive_stale_residual_approval(
    root: Path, *, contract: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Move a stale optional OCR exception into immutable audit history."""

    path = root / "phase4_residual_cjk_false_positive_approval.json"
    if not path.is_file():
        return None
    try:
        load_residual_cjk_false_positive_approval(root_dir=root, contract=contract)
        return None
    except Phase4ApprovalError as exc:
        digest = _sha256_file(path)
        stale = (
            root
            / "qa"
            / "stale"
            / f"phase4_residual_cjk_false_positive_approval_{digest[:12]}.json"
        )
        stale.parent.mkdir(parents=True, exist_ok=True)
        if stale.is_file():
            if _sha256_file(stale) != digest:
                raise ValueError("Stale residual approval archive hash conflict")
            path.unlink()
        else:
            path.replace(stale)
        audit: dict[str, Any] = {
            "schema_version": "phase4_residual_approval_supersession_v1",
            "status": "STALE_RESIDUAL_APPROVAL_ARCHIVED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reason": str(exc),
            "stale_ref": {
                "path": stale.relative_to(root).as_posix(),
                "sha256": digest,
            },
            "required_next_state": "RERENDER_AND_RESCAN_RESIDUAL_CJK",
        }
        audit["audit_sha256"] = _sha256_json(audit)
        _write_atomic(
            root / "phase4_residual_cjk_false_positive_approval_supersession.json",
            audit,
        )
        return dict(audit["stale_ref"])


def _normalized_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]+", "", decomposed.encode("ascii", "ignore").decode().casefold())


def _rect(raw: Mapping[str, Any]) -> tuple[float, float, float, float]:
    geometry = dict(raw.get("geometry") or {})
    x = float(geometry.get("x") or 0.0)
    y = float(geometry.get("y") or 0.0)
    return (
        x,
        y,
        x + float(geometry.get("width") or 0.0),
        y + float(geometry.get("height") or 0.0),
    )


def _overlap_over_smaller(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    smaller = min(left_area, right_area)
    return intersection / smaller if smaller > 0.0 else 0.0


def find_transition_gap_candidates(
    tracks: Sequence[Mapping[str, Any]],
    *,
    max_gap_frames: int = 24,
    min_geometry_overlap: float = 0.50,
) -> list[dict[str, Any]]:
    """Return bounded gaps whose neighboring tracks carry the same translation."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in tracks:
        if not isinstance(raw, Mapping):
            continue
        track = dict(raw)
        signature = _normalized_text(str(track.get("text_vi") or ""))
        if not signature or not isinstance(track.get("render_policy"), Mapping):
            continue
        grouped.setdefault(signature, []).append(track)
    candidates: list[dict[str, Any]] = []
    for signature, rows in grouped.items():
        ordered = sorted(
            rows,
            key=lambda row: (
                int(row.get("start_frame") or 0),
                int(row.get("end_frame") or -1),
                str(row.get("text_id") or ""),
            ),
        )
        for previous, following in zip(ordered, ordered[1:]):
            gap_start = int(previous.get("end_frame") or -1) + 1
            gap_end = int(following.get("start_frame") or 0) - 1
            gap_frames = gap_end - gap_start + 1
            geometry_overlap = _overlap_over_smaller(
                _rect(previous), _rect(following)
            )
            if (
                not 1 <= gap_frames <= int(max_gap_frames)
                or geometry_overlap < float(min_geometry_overlap)
            ):
                continue
            candidates.append(
                {
                    "signature": signature,
                    "previous": previous,
                    "following": following,
                    "gap_start": gap_start,
                    "gap_end": gap_end,
                    "gap_frames": gap_frames,
                    "geometry_overlap": round(geometry_overlap, 6),
                }
            )
    return candidates


def gap_sample_indices(start_frame: int, end_frame: int) -> list[int]:
    middle = (int(start_frame) + int(end_frame)) // 2
    return sorted({int(start_frame), middle, int(end_frame)})


def recovered_transition_components(
    tracks: Sequence[Mapping[str, Any]],
    *,
    min_geometry_overlap: float = 0.50,
) -> list[list[dict[str, Any]]]:
    """Group touching equivalent tracks when at least one is an OCR gap track."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in tracks:
        if not isinstance(raw, Mapping):
            continue
        track = dict(raw)
        signature = _normalized_text(str(track.get("text_vi") or ""))
        if signature:
            grouped.setdefault(signature, []).append(track)
    components: list[list[dict[str, Any]]] = []
    for rows in grouped.values():
        ordered = sorted(
            rows,
            key=lambda row: (
                int(row.get("start_frame") or 0),
                int(row.get("end_frame") or -1),
            ),
        )
        current: list[dict[str, Any]] = []
        current_end = -2
        for track in ordered:
            start = int(track.get("start_frame") or 0)
            overlaps_component = any(
                _overlap_over_smaller(_rect(track), _rect(member))
                >= float(min_geometry_overlap)
                for member in current
            )
            if current and start <= current_end + 1 and overlaps_component:
                current.append(track)
                current_end = max(current_end, int(track.get("end_frame") or start))
            else:
                if current:
                    components.append(current)
                current = [track]
                current_end = int(track.get("end_frame") or start)
        if current:
            components.append(current)
    return [
        component
        for component in components
        if len(component) >= 2
        and any(
            str(
                dict(dict(track.get("render_policy") or {}).get("context") or {}).get(
                    "transition_gap_recovery"
                )
                or ""
            )
            == POLICY_VERSION
            for track in component
        )
        and not any(
            bool(
                dict(dict(track.get("render_policy") or {}).get("context") or {}).get(
                    "transition_gap_merge"
                )
            )
            for track in component
        )
    ]


def build_merged_transition_track(
    component: Sequence[Mapping[str, Any]], *, fps: float
) -> dict[str, Any]:
    rows = [dict(row) for row in component]
    originals = [
        row
        for row in rows
        if str(
            dict(dict(row.get("render_policy") or {}).get("context") or {}).get(
                "transition_gap_recovery"
            )
            or ""
        )
        != POLICY_VERSION
    ]
    anchors = originals or rows
    anchor = copy.deepcopy(
        max(
            anchors,
            key=lambda row: int(row.get("end_frame") or 0)
            - int(row.get("start_frame") or 0),
        )
    )
    start = min(int(row.get("start_frame") or 0) for row in rows)
    end = max(int(row.get("end_frame") or start) for row in rows)
    members = sorted(str(row.get("text_id") or "") for row in rows)
    identity = _sha256_json({"members": members, "window": [start, end]})[:12]
    start_ms, end_ms = _timing(start, end, float(fps))
    policy = copy.deepcopy(dict(anchor.get("render_policy") or {}))
    context = dict(policy.get("context") or {})
    context.pop("transition_gap_recovery", None)
    context.update(
        {
            "transition_gap_merge": POLICY_VERSION,
            "mask_cache_scope": f"p4gapmerge_{identity}",
        }
    )
    policy["policy_version"] = POLICY_VERSION
    policy["context"] = context
    anchor.update(
        {
            "text_id": f"p4gapmerge_{identity}",
            "content_id": f"p4gapmerge_content_{identity}",
            "start_frame": start,
            "end_frame": end,
            "best_frame_index": (start + end) // 2,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "render_policy": policy,
            "output_residual_coverage": {
                "status": "AUTO_OCR_CONFIRMED_TRANSITION_GROUP_MERGED",
                "policy_version": POLICY_VERSION,
                "member_text_ids": members,
            },
        }
    )
    return anchor


def build_gap_track(
    candidate: Mapping[str, Any],
    *,
    fps: float,
    detections: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    following = copy.deepcopy(dict(candidate.get("following") or {}))
    previous = dict(candidate.get("previous") or {})
    gap_start = int(candidate.get("gap_start") or 0)
    gap_end = int(candidate.get("gap_end") or gap_start)
    identity = _sha256_json(
        {
            "previous_text_id": previous.get("text_id"),
            "following_text_id": following.get("text_id"),
            "gap": [gap_start, gap_end],
            "detections": [dict(row) for row in detections],
        }
    )[:12]
    start_ms, end_ms = _timing(gap_start, gap_end, float(fps))
    policy = copy.deepcopy(dict(following.get("render_policy") or {}))
    context = dict(policy.get("context") or {})
    context.update(
        {
            "transition_gap_recovery": POLICY_VERSION,
            "mask_cache_scope": f"p4gap_{identity}",
        }
    )
    policy["policy_version"] = POLICY_VERSION
    policy["context"] = context
    following.update(
        {
            "text_id": f"p4gap_{identity}",
            "content_id": f"p4gap_content_{identity}",
            "start_frame": gap_start,
            "end_frame": gap_end,
            "best_frame_index": (gap_start + gap_end) // 2,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "render_policy": policy,
            "output_residual_coverage": {
                "status": "AUTO_OCR_CONFIRMED_TRANSITION_GAP",
                "policy_version": POLICY_VERSION,
                "neighbor_text_ids": [
                    previous.get("text_id"),
                    dict(candidate.get("following") or {}).get("text_id"),
                ],
                "source_text": str(detections[0].get("text") or "") if detections else "",
                "sample_detections": [dict(row) for row in detections],
            },
        }
    )
    return following


def _capture_frame(video: Path, frame_index: int, output: Path) -> None:
    import cv2

    capture = cv2.VideoCapture(str(video))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise ValueError(f"Cannot decode source frame {frame_index}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), frame):
        raise ValueError(f"Cannot persist source frame {frame_index}")


def _confirm_candidate(
    *,
    candidate: Mapping[str, Any],
    source_video: Path,
    evidence_dir: Path,
    provider: Any,
    fps: float,
    min_confidence: float,
) -> list[dict[str, Any]]:
    target_rects = [
        _rect(dict(candidate.get("previous") or {})),
        _rect(dict(candidate.get("following") or {})),
    ]
    confirmed: list[dict[str, Any]] = []
    sample_indices = gap_sample_indices(
        int(candidate.get("gap_start") or 0), int(candidate.get("gap_end") or 0)
    )
    for frame_index in sample_indices:
        image_path = evidence_dir / f"frame_{frame_index:06d}.jpg"
        _capture_frame(source_video, frame_index, image_path)
        result = provider.detect_frame(
            image_path,
            frame_time_ms=int(round(frame_index * 1000.0 / max(1.0, fps))),
        )
        matches: list[dict[str, Any]] = []
        for box in list(getattr(result, "boxes", []) or []):
            text = str(getattr(box, "text", "") or "").strip()
            confidence = float(getattr(box, "confidence", 0.0) or 0.0)
            raw = {
                "geometry": {
                    "x": float(getattr(box, "x", 0.0) or 0.0),
                    "y": float(getattr(box, "y", 0.0) or 0.0),
                    "width": float(getattr(box, "width", 0.0) or 0.0),
                    "height": float(getattr(box, "height", 0.0) or 0.0),
                }
            }
            if (
                confidence < float(min_confidence)
                or not contains_cjk(text)
                or max(_overlap_over_smaller(_rect(raw), target) for target in target_rects)
                < 0.50
            ):
                continue
            matches.append(
                {
                    "frame_index": frame_index,
                    "text": text,
                    "confidence": round(confidence, 6),
                    "geometry": raw["geometry"],
                    "evidence_path": image_path.relative_to(evidence_dir.parent.parent).as_posix(),
                    "evidence_sha256": _sha256_file(image_path),
                }
            )
        if not matches:
            return []
        confirmed.append(max(matches, key=lambda row: float(row["confidence"])))
    signatures = Counter(str(row.get("text") or "") for row in confirmed)
    if not signatures or signatures.most_common(1)[0][1] < len(sample_indices):
        return []
    return confirmed


def materialize(
    case_root: str | Path,
    *,
    artifact_version: str = "v22_67",
    operator_id: str = "operator-auto-transition-gap-recovery",
    max_gap_frames: int = 24,
    min_confidence: float = 0.80,
    provider: Any | None = None,
) -> dict[str, Any]:
    root = Path(case_root).resolve()
    contract_path = root / "phase4_render_input.json"
    contract = _load(contract_path)
    active = load_active_visual_remediation(root, contract_path=contract_path)
    if active is None:
        raise ValueError("Active visual remediation is required")
    parent, parent_ref = active
    effective, _ = apply_visual_remediation(root, contract, contract_path=contract_path)
    stale_residual_approval_ref = archive_stale_residual_approval(
        root, contract=effective
    )
    phase1 = _load(root / "phase1_meta.json")
    source_video = _resolve_phase1_source_path(root, str(phase1.get("video") or ""))
    fps = float(dict(effective.get("video") or {}).get("fps") or 30.0)
    candidates = find_transition_gap_candidates(
        list(effective.get("render_tracks") or []), max_gap_frames=max_gap_frames
    )
    resolved_provider = provider or build_local_residual_ocr_provider()
    evidence_root = root / "qa" / f"phase4_transition_gap_recovery_{artifact_version}"
    operations = [dict(row) for row in list(parent.get("operations") or [])]
    recovered: list[dict[str, Any]] = []
    existing_windows = {
        (
            int(dict(dict(op).get("track") or {}).get("start_frame") or -1),
            int(dict(dict(op).get("track") or {}).get("end_frame") or -1),
        )
        for op in operations
        if str(dict(op).get("operation") or "") == "ADD_TRACK"
        and str(
            dict(
                dict(dict(dict(op).get("track") or {}).get("render_policy") or {}).get(
                    "context"
                )
                or {}
            ).get("transition_gap_recovery")
            or ""
        )
        == POLICY_VERSION
    }
    for candidate in candidates:
        window = (int(candidate["gap_start"]), int(candidate["gap_end"]))
        if window in existing_windows:
            continue
        candidate_dir = evidence_root / f"gap_{window[0]:06d}_{window[1]:06d}"
        detections = _confirm_candidate(
            candidate=candidate,
            source_video=source_video,
            evidence_dir=candidate_dir,
            provider=resolved_provider,
            fps=fps,
            min_confidence=min_confidence,
        )
        if not detections:
            continue
        track = build_gap_track(candidate, fps=fps, detections=detections)
        operations.append(
            {
                "operation": "ADD_TRACK",
                "track": track,
                "expected_added_track_sha256": _sha256_json(track),
            }
        )
        recovered.append(
            {
                "text_id": track["text_id"],
                "window": list(window),
                "neighbor_text_ids": [
                    dict(candidate["previous"]).get("text_id"),
                    dict(candidate["following"]).get("text_id"),
                ],
                "sample_detections": detections,
            }
        )
    if not recovered:
        return {
            "status": (
                "STALE_RESIDUAL_APPROVAL_ARCHIVED"
                if stale_residual_approval_ref is not None
                else "NO_OCR_CONFIRMED_TRANSITION_GAPS"
            ),
            "candidate_count": len(candidates),
            "recovered_count": 0,
            "stale_residual_approval_ref": stale_residual_approval_ref,
        }
    payload: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_v1",
        "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_id": str(operator_id).strip(),
        "authority_refs": {
            **dict(parent.get("authority_refs") or {}),
            "parent_visual_remediation": dict(parent_ref),
            "transition_gap_recovery": {
                "policy_version": POLICY_VERSION,
                "source_video_sha256": _sha256_file(source_video),
                "recovered": recovered,
                "stale_residual_approval_ref": stale_residual_approval_ref,
            },
        },
        "operations": operations,
        "non_goals": [
            "do_not_modify_phase1_to_phase3_artifacts",
            "do_not_bridge_without_cjk_on_every_sample",
            "do_not_translate_source_scene_text",
        ],
    }
    payload["materialization_sha256"] = _sha256_json(payload)
    artifact_name = f"phase4_visual_remediation_transition_gap_{artifact_version}.json"
    artifact_path = root / artifact_name
    _write_atomic(artifact_path, payload)
    pointer: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_pointer_v1",
        "status": "ACTIVE",
        "active_ref": {
            "path": artifact_name,
            "sha256": _sha256_file(artifact_path),
            "materialization_sha256": payload["materialization_sha256"],
        },
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    pointer_path = root / ACTIVE_POINTER_NAME
    previous_pointer = pointer_path.read_bytes()
    _write_atomic(pointer_path, pointer)
    try:
        validated, _ = apply_visual_remediation(
            root, contract, contract_path=contract_path
        )
    except Exception:
        pointer_path.write_bytes(previous_pointer)
        raise
    return {
        "status": "PHASE4_TRANSITION_GAPS_RECOVERED",
        "artifact": pointer["active_ref"],
        "candidate_count": len(candidates),
        "recovered_count": len(recovered),
        "recovered": recovered,
        "stale_residual_approval_ref": stale_residual_approval_ref,
        "effective_track_count": len(list(validated.get("render_tracks") or [])),
    }


def consolidate(
    case_root: str | Path,
    *,
    artifact_version: str = "v22_67_2",
    operator_id: str = "operator-auto-transition-gap-consolidation",
) -> dict[str, Any]:
    root = Path(case_root).resolve()
    contract_path = root / "phase4_render_input.json"
    contract = _load(contract_path)
    active = load_active_visual_remediation(root, contract_path=contract_path)
    if active is None:
        raise ValueError("Active visual remediation is required")
    parent, parent_ref = active
    effective, _ = apply_visual_remediation(root, contract, contract_path=contract_path)
    fps = float(dict(effective.get("video") or {}).get("fps") or 30.0)
    components = recovered_transition_components(
        list(effective.get("render_tracks") or [])
    )
    if not components:
        return {"status": "NO_TRANSITION_GROUPS_TO_CONSOLIDATE", "merged_count": 0}
    operations = [dict(row) for row in list(parent.get("operations") or [])]
    merged_rows: list[dict[str, Any]] = []
    for component in components:
        merged = build_merged_transition_track(component, fps=fps)
        for member in component:
            operations.append(
                {
                    "operation": "DROP_TRACK",
                    "target_text_id": member.get("text_id"),
                    "expected_track_sha256": _sha256_json(member),
                    "reason": "ocr_confirmed_transition_group_consolidation",
                }
            )
        operations.append(
            {
                "operation": "ADD_TRACK",
                "track": merged,
                "expected_added_track_sha256": _sha256_json(merged),
            }
        )
        merged_rows.append(
            {
                "merged_text_id": merged["text_id"],
                "window": [merged["start_frame"], merged["end_frame"]],
                "member_text_ids": [str(row.get("text_id") or "") for row in component],
            }
        )
    payload: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_v1",
        "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_id": str(operator_id).strip(),
        "authority_refs": {
            **dict(parent.get("authority_refs") or {}),
            "parent_visual_remediation": dict(parent_ref),
            "transition_gap_consolidation": {
                "policy_version": POLICY_VERSION,
                "merged_groups": merged_rows,
            },
        },
        "operations": operations,
        "non_goals": [
            "do_not_modify_phase1_to_phase3_artifacts",
            "do_not_relax_temporal_flicker_threshold",
            "do_not_merge_without_ocr_confirmed_gap_members",
        ],
    }
    payload["materialization_sha256"] = _sha256_json(payload)
    artifact_name = f"phase4_visual_remediation_transition_merge_{artifact_version}.json"
    artifact_path = root / artifact_name
    _write_atomic(artifact_path, payload)
    pointer: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_pointer_v1",
        "status": "ACTIVE",
        "active_ref": {
            "path": artifact_name,
            "sha256": _sha256_file(artifact_path),
            "materialization_sha256": payload["materialization_sha256"],
        },
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    pointer_path = root / ACTIVE_POINTER_NAME
    previous_pointer = pointer_path.read_bytes()
    _write_atomic(pointer_path, pointer)
    try:
        validated, _ = apply_visual_remediation(
            root, contract, contract_path=contract_path
        )
    except Exception:
        pointer_path.write_bytes(previous_pointer)
        raise
    return {
        "status": "PHASE4_TRANSITION_GROUPS_CONSOLIDATED",
        "artifact": pointer["active_ref"],
        "merged_count": len(merged_rows),
        "merged_groups": merged_rows,
        "effective_track_count": len(list(validated.get("render_tracks") or [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.materialize_phase4_transition_gap_recovery"
    )
    parser.add_argument("case_root")
    parser.add_argument("--artifact-version", default="v22_67")
    parser.add_argument("--operator", default="operator-auto-transition-gap-recovery")
    parser.add_argument("--max-gap-frames", type=int, default=24)
    parser.add_argument("--consolidate-existing", action="store_true")
    args = parser.parse_args()
    try:
        result = (
            consolidate(
                args.case_root,
                artifact_version=str(args.artifact_version),
                operator_id=str(args.operator),
            )
            if args.consolidate_existing
            else materialize(
                args.case_root,
                artifact_version=str(args.artifact_version),
                operator_id=str(args.operator),
                max_gap_frames=int(args.max_gap_frames),
            )
        )
        # Windows PowerShell 5 can expose a legacy cp1252 stdout even though
        # the artifacts themselves are UTF-8. Keep the CLI summary portable.
        print(json.dumps(result, ensure_ascii=True), flush=True)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[P4-TRANSITION-GAP][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
