"""Apply operator-approved Phase-4 visual remediations at the render boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


ACTIVE_POINTER_NAME = "phase4_visual_remediation_active.json"


class VisualRemediationError(RuntimeError):
    pass


def _int_or_default(value: Any, default: int) -> int:
    """Default only missing authority fields; zero is a valid frame/time."""

    return int(default if value is None else value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualRemediationError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise VisualRemediationError(f"{path.name} must contain an object")
    return payload


def _verify_self_hash(payload: Mapping[str, Any], key: str) -> bool:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(key, "") or "")
    return len(claimed) == 64 and claimed == _sha256_json(unsigned)


def _track_hash(track: Mapping[str, Any]) -> str:
    return _sha256_json(dict(track))


def _geometry_overlap_over_smaller(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> float:
    def rect(value: Mapping[str, Any]) -> tuple[float, float, float, float]:
        geometry = dict(value.get("geometry") or value)
        x = float(geometry.get("x") or 0.0)
        y = float(geometry.get("y") or 0.0)
        width = float(geometry.get("width") or 0.0)
        height = float(geometry.get("height") or 0.0)
        return x, y, x + width, y + height

    a = rect(left)
    b = rect(right)
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1])
    )
    smaller = min(
        max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1]),
        max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]),
    )
    return intersection / smaller if smaller > 0 else 0.0


def _timing(frame_start: int, frame_end: int, fps: float) -> tuple[int, int]:
    return (
        int(round(frame_start * 1000.0 / max(0.001, fps))),
        int(round((frame_end + 1) * 1000.0 / max(0.001, fps))),
    )


def load_active_visual_remediation(
    root_dir: str | Path,
    *,
    contract_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    root = Path(root_dir).resolve()
    pointer_path = root / ACTIVE_POINTER_NAME
    if not pointer_path.is_file():
        return None
    pointer = _load_object(pointer_path)
    if not _verify_self_hash(pointer, "pointer_sha256"):
        raise VisualRemediationError("Visual remediation pointer self-hash is invalid")
    ref = dict(pointer.get("active_ref") or {})
    path = (root / str(ref.get("path") or "")).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise VisualRemediationError("Active visual remediation path is invalid")
    if _sha256_file(path) != str(ref.get("sha256") or ""):
        raise VisualRemediationError("Active visual remediation file hash drifted")
    payload = _load_object(path)
    if (
        not _verify_self_hash(payload, "materialization_sha256")
        or str(payload.get("status") or "")
        != "PHASE4_VISUAL_REMEDIATION_APPROVED"
    ):
        raise VisualRemediationError("Visual remediation authority is invalid")
    source_path = (
        Path(contract_path).resolve()
        if contract_path is not None
        else root / "phase4_render_input.json"
    )
    input_ref = dict(dict(payload.get("authority_refs") or {}).get("phase4_input") or {})
    if (
        not source_path.is_file()
        or source_path.name != str(input_ref.get("path") or "")
        or _sha256_file(source_path) != str(input_ref.get("sha256") or "")
    ):
        raise VisualRemediationError("Visual remediation Phase-4 input authority drifted")
    return payload, {
        "path": path.name,
        "sha256": _sha256_file(path),
        "materialization_sha256": payload["materialization_sha256"],
    }


def apply_visual_remediation(
    root_dir: str | Path,
    contract: Mapping[str, Any],
    *,
    contract_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return an effective render contract without mutating Phase 1-3 artifacts."""

    active = load_active_visual_remediation(
        root_dir,
        contract_path=contract_path,
    )
    if active is None:
        return dict(contract), None
    payload, remediation_ref = active
    tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    by_id = {
        str(row.get("text_id") or ""): row
        for row in tracks
        if str(row.get("text_id") or "")
    }
    fps = float(dict(contract.get("video") or {}).get("fps") or 30.0)
    frame_count = int(dict(contract.get("video") or {}).get("frame_count") or 0)
    dense_ui_panels = [
        dict(row)
        for row in list(contract.get("dense_ui_panels") or [])
        if isinstance(row, Mapping)
    ]
    source_scene_text_regions = [
        dict(row)
        for row in list(contract.get("source_scene_text_regions") or [])
        if isinstance(row, Mapping)
    ]
    source_scene_text_tracks = [
        dict(row)
        for row in list(contract.get("source_scene_text_tracks") or [])
        if isinstance(row, Mapping)
    ]
    for raw in list(payload.get("operations") or []):
        if not isinstance(raw, Mapping):
            raise VisualRemediationError("Visual remediation operation is invalid")
        operation = dict(raw)
        kind = str(operation.get("operation") or "")
        if kind == "CLASSIFY_SOURCE_SCENE_TEXT_REGION":
            region = dict(operation.get("region") or {})
            region_id = str(region.get("region_id") or "")
            roi = dict(region.get("region_roi") or {})
            start_frame = int(region.get("start_frame") or 0)
            end_frame = _int_or_default(region.get("end_frame"), -1)
            targets = [
                dict(row)
                for row in list(operation.get("targets") or [])
                if isinstance(row, Mapping)
            ]
            target_ids = [str(row.get("target_text_id") or "") for row in targets]
            evidence = dict(region.get("evidence") or {})
            roi_area = float(roi.get("width") or 0.0) * float(roi.get("height") or 0.0)
            targetless_qa_region = (
                not targets
                and str(evidence.get("reason") or "")
                == "RESIDUAL_RIGHT_EDGE_PHONE_UI_BOUNDING"
                and float(roi.get("x") or 0.0) >= 0.75
                and 0.0 < roi_area <= 0.15
                and end_frame - start_frame <= 200
                and bool(list(evidence.get("qa_frames") or []))
            )
            disabled_panels = [
                str(value) for value in list(operation.get("disabled_panel_ids") or [])
            ]
            panel_ids = {str(row.get("panel_id") or "") for row in dense_ui_panels}
            if (
                not region_id
                or str(region.get("classification") or "") != "SOURCE_SCENE_TEXT"
                or _sha256_json(region) != str(operation.get("expected_region_sha256") or "")
                or start_frame < 0
                or end_frame < start_frame
                or (frame_count > 0 and end_frame >= frame_count)
                or (not targets and not targetless_qa_region)
                or len(target_ids) != len(set(target_ids))
                or any(not value or value not in by_id for value in target_ids)
                or any(
                    _track_hash(by_id[target_id])
                    != str(target.get("expected_track_sha256") or "")
                    for target_id, target in zip(target_ids, targets)
                )
                or set(target_ids) != set(str(value) for value in list(region.get("track_ids") or []))
                or any(str(by_id[target_id].get("kind") or "") == "hardsub" for target_id in target_ids)
                or any(value not in panel_ids for value in disabled_panels)
                or float(roi.get("x") or 0.0) < 0.0
                or float(roi.get("y") or 0.0) < 0.0
                or float(roi.get("width") or 0.0) <= 0.0
                or float(roi.get("height") or 0.0) <= 0.0
                or float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0) > 1.000001
                or float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0) > 1.000001
            ):
                raise VisualRemediationError(
                    f"Unsafe source-scene text classification: {region_id or 'missing'}"
                )
            classified = [by_id[target_id] for target_id in target_ids]
            source_scene_text_tracks.extend(
                {
                    "text_id": row.get("text_id"),
                    "content_id": row.get("content_id"),
                    "start_frame": row.get("start_frame"),
                    "end_frame": row.get("end_frame"),
                    "geometry": row.get("geometry"),
                    "classification": "SOURCE_SCENE_TEXT",
                    "region_id": region_id,
                }
                for row in classified
            )
            tracks = [row for row in tracks if str(row.get("text_id") or "") not in set(target_ids)]
            by_id = {
                str(row.get("text_id") or ""): row
                for row in tracks
                if str(row.get("text_id") or "")
            }
            dense_ui_panels = [
                row
                for row in dense_ui_panels
                if str(row.get("panel_id") or "") not in set(disabled_panels)
            ]
            source_scene_text_regions.append(region)
            continue
        if kind == "EXTEND_SOURCE_SCENE_TEXT_REGION":
            region_id = str(operation.get("region_id") or "")
            region_index = next(
                (
                    index
                    for index, row in enumerate(source_scene_text_regions)
                    if str(row.get("region_id") or "") == region_id
                ),
                None,
            )
            current = (
                dict(source_scene_text_regions[region_index])
                if region_index is not None
                else None
            )
            replacement = dict(operation.get("replacement_region") or {})
            roi = dict(replacement.get("region_roi") or {})
            if (
                current is None
                or _sha256_json(current)
                != str(operation.get("expected_region_sha256") or "")
                or _sha256_json(replacement)
                != str(operation.get("expected_replacement_sha256") or "")
                or str(replacement.get("region_id") or "") != region_id
                or str(replacement.get("classification") or "")
                != "SOURCE_SCENE_TEXT"
                or int(replacement.get("start_frame") or 0)
                > int(current.get("start_frame") or 0)
                or _int_or_default(replacement.get("end_frame"), -1)
                < _int_or_default(current.get("end_frame"), -1)
                or int(replacement.get("start_frame") or 0) < 0
                or _int_or_default(replacement.get("end_frame"), -1)
                >= frame_count
                or float(roi.get("x") or 0.0) < 0.0
                or float(roi.get("y") or 0.0) < 0.0
                or float(roi.get("width") or 0.0) <= 0.0
                or float(roi.get("height") or 0.0) <= 0.0
                or float(roi.get("x") or 0.0)
                + float(roi.get("width") or 0.0)
                > 1.000001
                or float(roi.get("y") or 0.0)
                + float(roi.get("height") or 0.0)
                > 1.000001
            ):
                raise VisualRemediationError(
                    f"Unsafe source-scene region extension: {region_id or 'missing'}"
                )
            source_scene_text_regions[region_index] = replacement
            continue
        if kind == "ADD_DENSE_UI_PANEL":
            panel = dict(operation.get("panel") or {})
            panel_id = str(panel.get("panel_id") or "")
            canonical_id = str(panel.get("canonical_text_id") or "")
            canonical = by_id.get(canonical_id)
            roi = dict(panel.get("panel_roi") or {})
            start_frame = int(panel.get("start_frame") or 0)
            end_frame = _int_or_default(panel.get("end_frame"), -1)
            area = float(roi.get("width") or 0.0) * float(
                roi.get("height") or 0.0
            )
            budget = float(
                dict(
                    dict(dict(canonical or {}).get("render_policy") or {}).get(
                        "damage_budget"
                    )
                    or {}
                ).get("max_frame_change_fraction")
                or 0.0
            )
            if (
                not panel_id
                or any(
                    str(row.get("panel_id") or "") == panel_id
                    for row in dense_ui_panels
                )
                or canonical is None
                or _track_hash(canonical)
                != str(operation.get("expected_canonical_track_sha256") or "")
                or _sha256_json(panel)
                != str(operation.get("expected_panel_sha256") or "")
                or start_frame < 0
                or end_frame < start_frame
                or (frame_count > 0 and end_frame >= frame_count)
                or area <= 0.0
                or area > budget
                or abs(
                    float(panel.get("max_frame_change_fraction") or 0.0) - budget
                )
                > 1e-9
                or float(roi.get("x") or 0.0) < 0.0
                or float(roi.get("y") or 0.0) < 0.0
                or float(roi.get("x") or 0.0)
                + float(roi.get("width") or 0.0)
                > 1.000001
                or float(roi.get("y") or 0.0)
                + float(roi.get("height") or 0.0)
                > 1.000001
                or str(panel.get("cover_strategy") or "")
                != "OPAQUE_SOURCE_AWARE_PHONE_UI_PLATE"
                or str(panel.get("layout_strategy") or "")
                != "DEDUPLICATED_PRIORITY_GRID"
                or int(panel.get("max_rendered_lines") or 0) not in range(1, 13)
            ):
                raise VisualRemediationError(
                    f"Unsafe dense UI panel: {panel_id or 'missing'}"
                )
            dense_ui_panels.append(panel)
            continue
        if kind == "ADD_TRACK":
            track = dict(operation.get("track") or {})
            track_id = str(track.get("text_id") or "")
            geometry = dict(track.get("geometry") or {})
            start_frame = int(track.get("start_frame") or 0)
            end_value = track.get("end_frame")
            end_frame = _int_or_default(end_value, -1)
            start_ms_value = track.get("start_ms")
            end_ms_value = track.get("end_ms")
            if (
                not track_id
                or track_id in by_id
                or _track_hash(track)
                != str(operation.get("expected_added_track_sha256") or "")
                or start_frame < 0
                or end_frame < start_frame
                or (frame_count > 0 and end_frame >= frame_count)
                or _int_or_default(start_ms_value, -1)
                != _timing(start_frame, start_frame, fps)[0]
                or _int_or_default(end_ms_value, -1)
                != _timing(end_frame, end_frame, fps)[1]
                or not str(track.get("text_vi") or "").strip()
                or str(track.get("translation_status") or "")
                not in {"TRANSLATION_APPROVED", "TRANSLATION_DETERMINISTIC"}
                or any(
                    float(geometry.get(key) or 0.0) <= 0.0
                    for key in ("width", "height")
                )
                or float(geometry.get("x") or 0.0) < 0.0
                or float(geometry.get("y") or 0.0) < 0.0
                or float(geometry.get("x") or 0.0)
                + float(geometry.get("width") or 0.0)
                > 1.000001
                or float(geometry.get("y") or 0.0)
                + float(geometry.get("height") or 0.0)
                > 1.000001
                or not isinstance(track.get("render_policy"), Mapping)
            ):
                raise VisualRemediationError(
                    f"Unsafe added visual-remediation track: {track_id or 'missing'}"
                )
            tracks.append(track)
            by_id[track_id] = track
            continue
        if kind == "DROP_TRACK_GROUP":
            canonical_id = str(operation.get("canonical_track_id") or "")
            canonical = by_id.get(canonical_id)
            targets = [
                dict(row)
                for row in list(operation.get("targets") or [])
                if isinstance(row, Mapping)
            ]
            if (
                canonical is None
                or _track_hash(canonical)
                != str(operation.get("expected_canonical_track_sha256") or "")
                or not targets
            ):
                raise VisualRemediationError(
                    "Visual remediation drop-group canonical drifted"
                )
            canonical_coverage = dict(
                canonical.get("output_residual_coverage") or {}
            )
            canonical_source = str(
                canonical_coverage.get("source_text") or ""
            ).strip()
            canonical_vi = str(canonical.get("text_vi") or "").strip()
            canonical_start = int(canonical.get("start_frame") or 0)
            canonical_end = _int_or_default(canonical.get("end_frame"), -1)
            drop_ids: set[str] = set()
            for entry in targets:
                drop_id = str(entry.get("target_text_id") or "")
                target = by_id.get(drop_id)
                coverage = dict(
                    dict(target or {}).get("output_residual_coverage") or {}
                )
                if (
                    target is None
                    or drop_id == canonical_id
                    or _track_hash(target)
                    != str(entry.get("expected_track_sha256") or "")
                    or str(coverage.get("source_text") or "").strip()
                    != canonical_source
                    or str(target.get("text_vi") or "").strip() != canonical_vi
                    or _geometry_overlap_over_smaller(canonical, target) < 0.70
                    or min(
                        canonical_end,
                        _int_or_default(target.get("end_frame"), -1),
                    )
                    < max(canonical_start, int(target.get("start_frame") or 0))
                ):
                    raise VisualRemediationError(
                        f"Unsafe visual-remediation drop-group target: {drop_id}"
                    )
                drop_ids.add(drop_id)
            tracks = [
                row
                for row in tracks
                if str(row.get("text_id") or "") not in drop_ids
            ]
            for drop_id in drop_ids:
                by_id.pop(drop_id, None)
            continue
        target_id = str(operation.get("target_text_id") or "")
        target = by_id.get(target_id)
        if target is None:
            raise VisualRemediationError(f"Visual remediation target is missing: {target_id}")
        if _track_hash(target) != str(operation.get("expected_track_sha256") or ""):
            raise VisualRemediationError(f"Visual remediation target drifted: {target_id}")
        if kind == "DROP_TRACK":
            tracks = [row for row in tracks if str(row.get("text_id") or "") != target_id]
            by_id.pop(target_id, None)
            continue
        if kind == "POLICY_OVERRIDE":
            policy = dict(target.get("render_policy") or {})
            context = dict(policy.get("context") or {})
            cover = dict(policy.get("cover") or {})
            layout = dict(policy.get("layout") or {})
            context.update(dict(operation.get("context_updates") or {}))
            cover.update(dict(operation.get("cover_updates") or {}))
            damage_budget = dict(policy.get("damage_budget") or {})
            damage_budget_updates = dict(operation.get("damage_budget_updates") or {})
            if damage_budget_updates:
                for key, value in damage_budget_updates.items():
                    if key not in {"max_frame_change_fraction", "max_ink_roi_fill_fraction"}:
                        raise VisualRemediationError(
                            f"Unsupported remediation damage budget field: {key}"
                        )
                    numeric = float(value)
                    if numeric <= 0.0 or numeric > 0.80:
                        raise VisualRemediationError(
                            f"Unsafe remediation damage budget: {target_id}"
                        )
                    damage_budget[key] = numeric
            layout_updates = dict(operation.get("layout_updates") or {})
            if layout_updates:
                mode = str(layout_updates.get("mode") or layout.get("mode") or "")
                if mode not in {"anchored_text", "cover_aligned"}:
                    raise VisualRemediationError(
                        f"Unsupported remediation layout mode: {mode or 'missing'}"
                    )
                safe_area = dict(
                    layout_updates.get("safe_area") or layout.get("safe_area") or {}
                )
                if (
                    float(safe_area.get("x") or 0.0) < 0.0
                    or float(safe_area.get("y") or 0.0) < 0.0
                    or float(safe_area.get("width") or 0.0) <= 0.0
                    or float(safe_area.get("height") or 0.0) <= 0.0
                    or float(safe_area.get("x") or 0.0)
                    + float(safe_area.get("width") or 0.0)
                    > 1.000001
                    or float(safe_area.get("y") or 0.0)
                    + float(safe_area.get("height") or 0.0)
                    > 1.000001
                ):
                    raise VisualRemediationError(
                        f"Unsafe remediation layout safe area: {target_id}"
                    )
                max_lines = int(layout_updates.get("max_lines") or layout.get("max_lines") or 1)
                if max_lines not in range(1, 4):
                    raise VisualRemediationError(
                        f"Unsafe remediation layout max_lines: {target_id}"
                    )
                layout.update(layout_updates)
            policy.update(
                {
                    "policy_version": "phase4_visual_remediation_v1",
                    "context": context,
                    "cover": cover,
                    "damage_budget": damage_budget,
                    **({"layout": layout} if layout_updates else {}),
                }
            )
            target["render_policy"] = policy
            continue
        if kind == "TIMING_OVERRIDE":
            original = list(operation.get("original_window") or [])
            replacement = list(operation.get("replacement_window") or [])
            if (
                original != [target.get("start_frame"), target.get("end_frame")]
                or len(replacement) != 2
                or int(replacement[0]) < int(original[0])
                or int(replacement[1]) > int(original[1])
                or int(replacement[0]) > int(replacement[1])
            ):
                raise VisualRemediationError(f"Unsafe timing override: {target_id}")
            start_frame, end_frame = map(int, replacement)
            start_ms, end_ms = _timing(start_frame, end_frame, fps)
            target.update(
                {
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "visual_timing_remediation": {
                        "status": "OPERATOR_APPROVED_OVERRIDE",
                        "original_window": original,
                    },
                }
            )
            continue
        if kind == "SPLIT_TRACK":
            intervals = [
                [int(value[0]), int(value[1])]
                for value in list(operation.get("intervals") or [])
                if isinstance(value, Sequence)
                and not isinstance(value, (str, bytes))
                and len(value) == 2
            ]
            if (
                len(intervals) < 2
                or intervals != sorted(intervals)
                or intervals[0][0] != int(target.get("start_frame") or 0)
                or intervals[-1][1] != int(target.get("end_frame") or 0)
                or any(start > end for start, end in intervals)
                or any(left[1] >= right[0] for left, right in zip(intervals, intervals[1:]))
            ):
                raise VisualRemediationError(f"Unsafe track split: {target_id}")
            index = next(
                position
                for position, row in enumerate(tracks)
                if str(row.get("text_id") or "") == target_id
            )
            replacements: list[dict[str, Any]] = []
            for part, (start_frame, end_frame) in enumerate(intervals, start=1):
                clone = dict(target)
                clone_id = f"{target_id}__p4r_{part:02d}"
                start_ms, end_ms = _timing(start_frame, end_frame, fps)
                policy = dict(clone.get("render_policy") or {})
                context = dict(policy.get("context") or {})
                context.update(
                    {
                        "visual_remediation_parent_text_id": target_id,
                        "mask_cache_scope": clone_id,
                    }
                )
                policy.update(
                    {
                        "policy_version": "phase4_visual_remediation_v1",
                        "context": context,
                    }
                )
                clone.update(
                    {
                        "text_id": clone_id,
                        "start_frame": start_frame,
                        "end_frame": end_frame,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "best_frame_index": (start_frame + end_frame) // 2,
                        "render_policy": policy,
                        "visual_track_split": {
                            "status": "OPERATOR_APPROVED_SPLIT",
                            "parent_text_id": target_id,
                        },
                    }
                )
                replacements.append(clone)
            tracks[index : index + 1] = replacements
            by_id.pop(target_id, None)
            by_id.update({str(row["text_id"]): row for row in replacements})
            continue
        raise VisualRemediationError(f"Unsupported visual remediation operation: {kind}")
    ids = [str(row.get("text_id") or "") for row in tracks]
    if not tracks or len(ids) != len(set(ids)) or any(not value for value in ids):
        raise VisualRemediationError("Visual remediation produced invalid render tracks")
    output = dict(contract)
    output["render_tracks"] = tracks
    output["dense_ui_panels"] = dense_ui_panels
    output["source_scene_text_regions"] = source_scene_text_regions
    output["source_scene_text_tracks"] = source_scene_text_tracks
    counts = dict(output.get("counts") or {})
    counts.update(
        {
            "render_tracks": len(tracks),
            "translated_tracks": sum(
                bool(str(row.get("text_vi") or "").strip()) for row in tracks
            ),
            "cover_only_tracks": sum(bool(row.get("cover_only")) for row in tracks),
        }
    )
    output["counts"] = counts
    refs = dict(output.get("refs") or {})
    refs["visual_remediation_ref"] = remediation_ref
    output["refs"] = refs
    output["visual_remediation_policy_version"] = "phase4_visual_remediation_v1"
    return output, remediation_ref
