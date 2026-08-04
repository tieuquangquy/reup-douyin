"""Resolution-independent Phase 4 render planning by role and track context."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping

RENDER_POLICY_VERSION = "phase4_role_policy_v14"
SEMANTIC_RENDER_DEDUP_POLICY_VERSION = "semantic_render_dedup_v1"
UNIFIED_EDITOR_COVER_POLICY_VERSION = "editor_overlay_spatial_telea_full_roi_v1"
UNIFIED_EDITOR_COVER_STRATEGY = "spatial_telea_r9"
UNIFIED_EDITOR_COVER_MASK_MODE = "full_roi_plate"

_SAFE_X = 0.025
_SAFE_Y = 0.025

_GEOMETRY_LIMITS = {
    "hardsub": {"max_width": 0.96, "max_height": 0.20, "max_area": 0.16},
    "title": {"max_width": 0.96, "max_height": 0.28, "max_area": 0.22},
    "ui": {"max_width": 0.70, "max_height": 0.18, "max_area": 0.09},
}
_CAPTION_ROW_LIMITS = {
    "max_width": 0.92,
    "max_height": 0.10,
    # Keep area consistent with the independently allowed width/height. Wide
    # single-row captions near the lower third can legitimately occupy ~8%.
    "max_area": 0.09,
}


class RenderPolicyError(RuntimeError):
    """A track cannot safely receive an automatic render policy."""


def normalize_render_text(value: Any) -> str:
    """Return a stable semantic key for approved render text."""

    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def _geometry_overlap_over_smaller(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> float:
    left_x0 = float(left.get("x") or 0.0)
    left_y0 = float(left.get("y") or 0.0)
    left_x1 = left_x0 + float(left.get("width") or 0.0)
    left_y1 = left_y0 + float(left.get("height") or 0.0)
    right_x0 = float(right.get("x") or 0.0)
    right_y0 = float(right.get("y") or 0.0)
    right_x1 = right_x0 + float(right.get("width") or 0.0)
    right_y1 = right_y0 + float(right.get("height") or 0.0)
    intersection = max(0.0, min(left_x1, right_x1) - max(left_x0, right_x0)) * max(
        0.0, min(left_y1, right_y1) - max(left_y0, right_y0)
    )
    smaller = min(
        max(0.0, left_x1 - left_x0) * max(0.0, left_y1 - left_y0),
        max(0.0, right_x1 - right_x0) * max(0.0, right_y1 - right_y0),
    )
    return intersection / smaller if smaller > 0.0 else 0.0


def _axis_overlap_over_smaller(
    left_start: float,
    left_size: float,
    right_start: float,
    right_size: float,
) -> float:
    intersection = max(
        0.0,
        min(left_start + left_size, right_start + right_size)
        - max(left_start, right_start),
    )
    smaller = min(left_size, right_size)
    return intersection / smaller if smaller > 0.0 else 0.0


def _time_overlaps(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        int(left.get("start_ms") or 0) < int(right.get("end_ms") or 0)
        and int(right.get("start_ms") or 0) < int(left.get("end_ms") or 0)
    )


def select_text_render_tracks(
    active_tracks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Render one semantic label for overlapping source geometries.

    Every geometry remains in ``active_tracks`` for source-text removal. Only
    duplicate Vietnamese placement is suppressed, preferring the larger and
    therefore more stable geometry at the current frame.
    """
    text_candidates = [
        track for track in active_tracks if not bool(track.get("cover_only"))
    ]
    ranked = sorted(
        enumerate(text_candidates),
        key=lambda item: (
            -float(dict(item[1].get("geometry") or {}).get("width") or 0.0)
            * float(dict(item[1].get("geometry") or {}).get("height") or 0.0),
            item[0],
        ),
    )
    selected: list[tuple[int, dict[str, Any]]] = []
    for original_index, track in ranked:
        content_id = str(track.get("content_id") or "").strip()
        semantic_text = normalize_render_text(track.get("text_vi"))
        geometry = dict(track.get("geometry") or {})
        if any(
            (
                (
                    content_id
                    and content_id
                    == str(existing.get("content_id") or "").strip()
                )
                or (
                    semantic_text
                    and semantic_text
                    == normalize_render_text(existing.get("text_vi"))
                )
            )
            and (
                bool(track.get("duplicate_transition_canonical"))
                or bool(existing.get("duplicate_transition_canonical"))
                or _geometry_overlap_over_smaller(
                    geometry, dict(existing.get("geometry") or {})
                )
                >= 0.35
            )
            for _index, existing in selected
        ):
            continue
        selected.append((original_index, track))
    return [track for _index, track in sorted(selected, key=lambda item: item[0])]


def _rect(raw: Mapping[str, Any]) -> dict[str, float]:
    try:
        x = float(raw.get("x") or 0.0)
        y = float(raw.get("y") or 0.0)
        width = float(raw.get("width") or 0.0)
        height = float(raw.get("height") or 0.0)
    except (TypeError, ValueError) as exc:
        raise RenderPolicyError("Track geometry must be numeric") from exc
    if (
        x < 0.0
        or y < 0.0
        or width <= 0.0
        or height <= 0.0
        or x + width > 1.000001
        or y + height > 1.000001
    ):
        raise RenderPolicyError("Track geometry is outside normalized frame bounds")
    return {"x": x, "y": y, "width": width, "height": height}


def _expand(
    geometry: Mapping[str, float], *, pad_x: float, pad_y: float
) -> dict[str, float]:
    x0 = max(0.0, float(geometry["x"]) - pad_x)
    y0 = max(0.0, float(geometry["y"]) - pad_y)
    x1 = min(1.0, float(geometry["x"]) + float(geometry["width"]) + pad_x)
    y1 = min(1.0, float(geometry["y"]) + float(geometry["height"]) + pad_y)
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _clamped_area(
    *, x: float, y: float, width: float, height: float
) -> dict[str, float]:
    x0 = max(_SAFE_X, min(1.0 - _SAFE_X, x))
    y0 = max(_SAFE_Y, min(1.0 - _SAFE_Y, y))
    x1 = max(x0, min(1.0 - _SAFE_X, x + width))
    y1 = max(y0, min(1.0 - _SAFE_Y, y + height))
    return {
        "x": x0,
        "y": y0,
        "width": max(0.01, x1 - x0),
        "height": max(0.01, y1 - y0),
    }


def _safe_area(
    kind: str,
    geometry: Mapping[str, float],
    *,
    dense: bool,
    caption_row: bool = False,
    micro_ui: bool = False,
) -> dict[str, float]:
    if dense:
        return _clamped_area(x=0.04, y=0.05, width=0.92, height=0.90)
    if caption_row:
        pad_y = 0.012
        return _clamped_area(
            x=_SAFE_X,
            y=float(geometry["y"]) - pad_y,
            width=1.0 - 2 * _SAFE_X,
            height=max(
                0.045,
                min(0.075, float(geometry["height"]) + 2 * pad_y),
            ),
        )
    if kind == "hardsub":
        y = max(0.52, min(float(geometry["y"]) - 0.12, 0.86))
        return _clamped_area(x=_SAFE_X, y=y, width=1.0 - 2 * _SAFE_X, height=0.30)
    if kind == "title":
        y = max(_SAFE_Y, float(geometry["y"]) - 0.12)
        return _clamped_area(x=0.05, y=y, width=0.90, height=0.28)
    center_x = float(geometry["x"]) + float(geometry["width"]) * 0.5
    width = max(0.24, min(0.42, float(geometry["width"]) + 0.20))
    x = center_x - width * 0.5
    if micro_ui:
        pad_y = 0.010
        return _clamped_area(
            x=x,
            y=float(geometry["y"]) - pad_y,
            width=width,
            height=max(
                0.038,
                min(0.060, float(geometry["height"]) + 2 * pad_y),
            ),
        )
    # Expand around the source row symmetrically.  Shifting the entire extra
    # height above the row can make a long Vietnamese UI label collide with a
    # distinct label immediately above it even when source geometries only
    # touch at their boundaries.
    y = float(geometry["y"]) - 0.02
    height = max(0.055, min(0.14, float(geometry["height"]) + 0.04))
    return _clamped_area(x=x, y=y, width=width, height=height)


def plan_render_track(
    track: Mapping[str, Any],
    *,
    simultaneous_count: int,
    motion_score: float | None = None,
) -> dict[str, Any]:
    geometry = _rect(dict(track.get("geometry") or {}))
    kind = str(track.get("kind") or "ui").strip().lower()
    if kind not in {"hardsub", "title", "ui"}:
        kind = "ui"
    original_kind = kind
    roles = {str(value or "").strip().lower() for value in track.get("roles") or []}
    center_x = geometry["x"] + geometry["width"] * 0.5
    start_frame = max(0, int(track.get("start_frame") or 0))
    end_frame = max(start_frame, int(track.get("end_frame") or start_frame))
    span_frames = end_frame - start_frame + 1
    # Intro title glyphs are frequently split into separate, vertically-truncated
    # OCR boxes.  Width/position plus a very short opening lifespan is a stronger
    # signal than detector height here.  Treating these rows as normal captions
    # seeds the temporal cleaner exclusively with frames that still contain the
    # title, so it faithfully reconstructs the Chinese text instead of removing it.
    intro_visual_title = (
        kind == "ui"
        and "start_frame" in track
        and "end_frame" in track
        and start_frame <= 2
        and span_frames <= 6
        and geometry["width"] >= 0.20
        and 0.30 <= center_x <= 0.70
        and max(1, int(simultaneous_count)) <= 3
    )
    caption_row = (
        kind == "ui"
        and not intro_visual_title
        and geometry["height"] <= 0.10
        and (
            geometry["width"] >= 0.50
            or (geometry["width"] >= 0.35 and geometry["y"] >= 0.45)
        )
        and max(1, int(simultaneous_count)) <= 6
    )
    visual_title = (
        intro_visual_title
        or (
            kind == "ui"
            and not caption_row
            and geometry["width"] >= 0.20
            and geometry["height"] >= 0.06
            and 0.30 <= center_x <= 0.70
            and max(1, int(simultaneous_count)) <= 3
        )
    )
    if visual_title:
        kind = "title"
    micro_ui = (
        kind == "ui"
        and not caption_row
        and (
            "ui_chip" in roles
            or (
                geometry["height"] <= 0.05
                and geometry["width"] <= 0.45
            )
        )
    )
    effective_kind = kind
    typography_kind = (
        "caption_row"
        if caption_row
        else "micro_ui"
        if micro_ui
        else kind
    )
    limits = _CAPTION_ROW_LIMITS if caption_row else _GEOMETRY_LIMITS[kind]
    area = geometry["width"] * geometry["height"]
    if (
        geometry["width"] > limits["max_width"]
        or geometry["height"] > limits["max_height"]
        or area > limits["max_area"]
    ):
        raise RenderPolicyError(
            f"Sparse {kind} geometry exceeds automatic safety limits"
        )

    dense = max(1, int(simultaneous_count)) >= 8
    if caption_row:
        cover_roi = _expand(geometry, pad_x=0.015, pad_y=0.010)
    elif kind == "ui":
        cover_roi = _expand(
            geometry,
            pad_x=0.012 if dense else 0.006,
            pad_y=0.020 if dense else 0.008,
        )
    elif kind == "title":
        cover_roi = _expand(geometry, pad_x=0.020, pad_y=0.020)
    else:
        cover_roi = _expand(geometry, pad_x=0.015, pad_y=0.012)
    # Every localizable render track is an operator-approved editor overlay;
    # SOURCE_INTRINSIC tracks were partitioned into protected_source_tracks by
    # the Phase 4 input contract and never enter this planner.  Keep one cover
    # algorithm and one mask shape for the complete editor-overlay lane.  The
    # former role-specific mix (full-row spatial Telea for captions, temporal
    # ink plates for compact UI) produced visibly different texture and could
    # switch again between static/flow/spatial modes from frame to frame.
    strategy = UNIFIED_EDITOR_COVER_STRATEGY
    dense_panel_plate = kind == "ui" and int(simultaneous_count) >= 15
    # Cover and replacement text are one geometry authority for every editor
    # overlay.  Previously compact UI labels used a wider anchored_text safe
    # area while the source cover stayed at the OCR ROI, so QA correctly found
    # the blur and Vietnamese replacement in different regions.
    layout_mode = "cover_aligned"
    max_lines = 2 if kind in {"hardsub", "title"} else 1
    motion = None if motion_score is None else max(0.0, min(1.0, float(motion_score)))
    bounded_dense_ink_hardsub = (
        kind == "hardsub"
        and not dense
        and geometry["width"] >= 0.35
        and geometry["height"] <= 0.10
    )
    layout_safe_area = cover_roi
    # Chinese UI labels are often substantially shorter than their locked
    # Vietnamese replacements.  Keep the typography box centered on the same
    # source lane but let it expand horizontally within local bounds.  This
    # avoids both silent text omission and the old full-frame responsive grid
    # that made labels jump away from their removal geometry.
    if kind == "ui" and not caption_row:
        layout_safe_area = _safe_area(
            kind,
            geometry,
            dense=False,
            caption_row=caption_row,
            micro_ui=micro_ui,
        )

    damage_budget = {
        "max_frame_change_fraction": 0.55 if dense else min(0.12, max(0.015, area * 3.0)),
        "max_ink_roi_fill_fraction": (
            0.85
            if bounded_dense_ink_hardsub
            else 0.82
            if kind == "ui" and dense
            else 0.80
        ),
        "max_outside_mask_mean_abs_delta": 2.0,
        "min_outside_mask_ssim": 0.985,
        "max_temporal_flicker_delta": 4.0,
    }
    return {
        "policy_version": RENDER_POLICY_VERSION,
        "context": {
            "simultaneous_count": max(1, int(simultaneous_count)),
            "motion_score": motion,
            "dense_ui": dense,
            "caption_row": caption_row,
            "micro_ui": micro_ui,
            "output_residual_bounded_dense_mask": dense_panel_plate,
            "bounded_dense_ink_hardsub": bounded_dense_ink_hardsub,
            "source_kind": original_kind,
            "effective_kind": effective_kind,
            "typography_kind": typography_kind,
            "cover_consistency_policy": UNIFIED_EDITOR_COVER_POLICY_VERSION,
        },
        "cover": {
            "strategy": strategy,
            "roi": cover_roi,
            "mask_mode": UNIFIED_EDITOR_COVER_MASK_MODE,
            "consistency_policy": UNIFIED_EDITOR_COVER_POLICY_VERSION,
            "mask_dilate_radius_fraction": (
                0.10
                if kind == "hardsub"
                else 0.08
                if kind == "ui" and dense
                else 0.04
            ),
            "fallback": "operator_review",
        },
        "layout": {
            "mode": layout_mode,
            "safe_area": layout_safe_area,
            "anchor": "center_bottom" if kind != "ui" else "nearest_safe_center",
            "max_lines": max_lines,
            "safe_margin_x": _SAFE_X,
            "safe_margin_y": _SAFE_Y,
        },
        "damage_budget": damage_budget,
    }


def _max_simultaneous(track: Mapping[str, Any], tracks: list[dict[str, Any]]) -> int:
    start = int(track.get("start_ms") or 0)
    end = int(track.get("end_ms") or start)
    event_times = {start}
    for other in tracks:
        other_start = int(other.get("start_ms") or 0)
        if start <= other_start < end:
            event_times.add(other_start)
    return max(
        1,
        max(
            sum(
                int(other.get("start_ms") or 0) <= event < int(other.get("end_ms") or 0)
                for other in tracks
            )
            for event in event_times
        ),
    )


def enrich_phase4_render_policies(contract: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(contract)
    tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    enriched: list[dict[str, Any]] = []
    for row in tracks:
        row["render_policy"] = plan_render_track(
            row,
            simultaneous_count=_max_simultaneous(row, tracks),
        )
        enriched.append(row)
    title_rows = [
        row
        for row in enriched
        if str(
            dict(dict(row.get("render_policy") or {}).get("context") or {}).get(
                "effective_kind"
            )
            or ""
        )
        == "title"
    ]
    for row in enriched:
        policy = dict(row.get("render_policy") or {})
        context = dict(policy.get("context") or {})
        if context.get("effective_kind") == "title" or int(
            context.get("simultaneous_count") or 1
        ) > 3:
            continue
        geometry = dict(row.get("geometry") or {})
        center_x = float(geometry.get("x") or 0.0) + float(
            geometry.get("width") or 0.0
        ) * 0.5
        center_y = float(geometry.get("y") or 0.0) + float(
            geometry.get("height") or 0.0
        ) * 0.5
        for title in title_rows:
            if not (
                int(row.get("start_ms") or 0) < int(title.get("end_ms") or 0)
                and int(title.get("start_ms") or 0) < int(row.get("end_ms") or 0)
            ):
                continue
            title_geometry = dict(title.get("geometry") or {})
            title_x = float(title_geometry.get("x") or 0.0) + float(
                title_geometry.get("width") or 0.0
            ) * 0.5
            title_y = float(title_geometry.get("y") or 0.0) + float(
                title_geometry.get("height") or 0.0
            ) * 0.5
            if abs(center_x - title_x) > 0.25 or abs(center_y - title_y) > 0.25:
                continue
            context["reference_group"] = str(title.get("text_id") or "")
            cover = dict(policy.get("cover") or {})
            # A nearby title may still share semantic/reference metadata, but
            # must not escape the production-wide cover style.
            if str(cover.get("consistency_policy") or "") != (
                UNIFIED_EDITOR_COVER_POLICY_VERSION
            ):
                cover["mask_mode"] = "stylized_components"
            policy["context"] = context
            policy["cover"] = cover
            row["render_policy"] = policy
            break

    # Two distinct source labels can share one subtitle row. Centering both
    # Vietnamese strings in the full-width hardsub safe area makes them collide
    # even though their source geometries are side by side. Partition only such
    # temporally overlapping rows into source-aligned horizontal lanes. This is
    # content-agnostic and leaves normal single captions full-width.
    lane_candidates = [
        row
        for row in enriched
        if str(
            dict(dict(row.get("render_policy") or {}).get("context") or {}).get(
                "effective_kind"
            )
            or ""
        )
        == "hardsub"
        and not bool(
            dict(dict(row.get("render_policy") or {}).get("context") or {}).get(
                "dense_ui"
            )
        )
    ]
    neighbors: dict[str, set[str]] = {
        str(row.get("text_id") or ""): set() for row in lane_candidates
    }
    by_id = {
        str(row.get("text_id") or ""): row
        for row in lane_candidates
        if str(row.get("text_id") or "")
    }
    for index, left in enumerate(lane_candidates):
        left_id = str(left.get("text_id") or "")
        left_geometry = dict(left.get("geometry") or {})
        for right in lane_candidates[index + 1 :]:
            right_id = str(right.get("text_id") or "")
            right_geometry = dict(right.get("geometry") or {})
            vertical_overlap = _axis_overlap_over_smaller(
                float(left_geometry.get("y") or 0.0),
                float(left_geometry.get("height") or 0.0),
                float(right_geometry.get("y") or 0.0),
                float(right_geometry.get("height") or 0.0),
            )
            horizontal_overlap = _axis_overlap_over_smaller(
                float(left_geometry.get("x") or 0.0),
                float(left_geometry.get("width") or 0.0),
                float(right_geometry.get("x") or 0.0),
                float(right_geometry.get("width") or 0.0),
            )
            if (
                left_id
                and right_id
                and _time_overlaps(left, right)
                and vertical_overlap >= 0.55
                and horizontal_overlap <= 0.20
            ):
                neighbors[left_id].add(right_id)
                neighbors[right_id].add(left_id)

    visited: set[str] = set()
    for seed in sorted(by_id):
        if seed in visited or not neighbors.get(seed):
            continue
        pending = [seed]
        component_ids: set[str] = set()
        while pending:
            current = pending.pop()
            if current in component_ids:
                continue
            component_ids.add(current)
            pending.extend(sorted(neighbors.get(current) or set()))
        visited.update(component_ids)
        component = sorted(
            (by_id[text_id] for text_id in component_ids),
            key=lambda row: (
                float(dict(row.get("geometry") or {}).get("x") or 0.0)
                + float(dict(row.get("geometry") or {}).get("width") or 0.0)
                * 0.5,
                str(row.get("text_id") or ""),
            ),
        )
        if len(component) < 2:
            continue
        geometries = [dict(row.get("geometry") or {}) for row in component]
        outer_left = max(
            _SAFE_X,
            min(float(value.get("x") or 0.0) for value in geometries) - 0.012,
        )
        outer_right = min(
            1.0 - _SAFE_X,
            max(
                float(value.get("x") or 0.0)
                + float(value.get("width") or 0.0)
                for value in geometries
            )
            + 0.012,
        )
        boundaries = [outer_left]
        for left_geometry, right_geometry in zip(geometries, geometries[1:]):
            boundaries.append(
                (
                    float(left_geometry.get("x") or 0.0)
                    + float(left_geometry.get("width") or 0.0)
                    + float(right_geometry.get("x") or 0.0)
                )
                * 0.5
            )
        boundaries.append(outer_right)
        if any(
            boundaries[index + 1] - boundaries[index] < 0.10
            for index in range(len(component))
        ):
            continue
        member_ids = [str(row.get("text_id") or "") for row in component]
        for lane_index, row in enumerate(component):
            policy = dict(row.get("render_policy") or {})
            context = dict(policy.get("context") or {})
            layout = dict(policy.get("layout") or {})
            # Current editor-overlay contracts bind Vietnamese placement to
            # the exact cover ROI.  The legacy lane expansion below is kept
            # only for older non-cover-aligned policies; widening a v14 safe
            # area would reintroduce the cover/text mismatch this policy fixes.
            if str(layout.get("mode") or "") == "cover_aligned":
                continue
            safe_area = dict(layout.get("safe_area") or {})
            safe_area.update(
                {
                    "x": boundaries[lane_index],
                    "width": boundaries[lane_index + 1]
                    - boundaries[lane_index],
                }
            )
            context.update(
                {
                    "horizontal_lane_members": member_ids,
                    "horizontal_lane_index": lane_index,
                }
            )
            layout.update(
                {
                    "safe_area": safe_area,
                    "anchor": "source_horizontal_lane_bottom",
                }
            )
            policy["context"] = context
            policy["layout"] = layout
            row["render_policy"] = policy
    output["render_tracks"] = enriched
    output["render_policy_version"] = RENDER_POLICY_VERSION
    return output
