"""Resolution-independent Phase 4 render planning by role and track context."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping

RENDER_POLICY_VERSION = "phase4_role_policy_v20_soft_reconstruction_epochs"
SEMANTIC_RENDER_DEDUP_POLICY_VERSION = "semantic_render_dedup_v1"
UNIFIED_EDITOR_COVER_POLICY_VERSION = "editor_overlay_soft_reconstruction_v6"
UNIFIED_EDITOR_COVER_STRATEGY = "soft_reconstruction_plate_v1"
UNIFIED_EDITOR_COVER_MASK_MODE = "full_roi_plate"
SOFT_COVER_EPOCH_POLICY_VERSION = "soft_cover_epoch_v1"
UNIFIED_EDITOR_BLUR_PROFILE = {
    "sigma_text_height_fraction": 0.72,
    "sigma_frame_min_fraction": 0.006,
    "sigma_frame_max_fraction": 0.050,
    "feather_text_height_fraction": 0.10,
    "background_tint_alpha": 0.24,
    "max_residual_stroke_ratio": 0.30,
    # Ratio-only checks become unstable when an earlier overlapping track has
    # already flattened the ROI and source stroke energy is near zero.  An
    # absolute low-energy pass prevents false blocks without allowing visible
    # glyphs through the gate.
    "max_output_stroke_energy": 2.2,
    "max_source_stroke_energy_for_absolute_pass": 5.0,
    # A moving/textured background can retain a few isolated Laplacian peaks
    # after the glyph itself is no longer readable.  Mean energy alone then
    # produces false blocks.  Accept only when strong residual strokes occupy
    # a very small portion of the fully concealed core; real glyphs remain a
    # connected, much denser edge field and continue to fail closed.
    "strong_stroke_threshold": 12.0,
    "max_output_strong_stroke_fraction": 0.04,
    "max_structural_residual_ratio": 0.45,
    "overlap_residual_min_prior_fraction": 0.70,
    "overlap_residual_max_source_energy": 8.0,
    "overlap_residual_max_output_energy": 3.0,
    "retry_sigma_multiplier": 1.40,
    "retry_sigma_frame_max_fraction": 0.07,
    "retry_tint_increment": 0.14,
    "rounded_corner_text_height_fraction": 0.16,
    "soft_edge_text_height_fraction": 0.14,
    "spatial_surface_max_ring_mad": 18.0,
    "max_boundary_seam_score": 0.10,
    "max_temporal_flicker_score": 0.16,
    "max_background_color_drift": 0.08,
}
UNIFIED_EDITOR_TRANSITION_HOLD_FRAMES = 3
UNIFIED_EDITOR_TRANSITION_HOLD_SECONDS = 0.12

# Caption OCR is content-oriented: the detected box changes when a sentence
# changes even though the editor-owned visual lane stays fixed.  The renderer
# therefore stabilizes nearby caption rows into one spatial cover authority and
# closes only short temporal gaps.  The limit is converted from seconds using
# the source FPS so 24/30/60-fps media receive the same physical treatment.
CAPTION_COVER_MAX_BRIDGE_SECONDS = 0.80
# A presence envelope is used for physical concealment activation.  A short
# detector hole is bridged so the plate cannot pulse, while a real clean gap
# remains inactive and does not blur the subject for an entire semantic epoch.
CAPTION_PRESENCE_BRIDGE_SECONDS = 0.12

_SAFE_X = 0.025
_SAFE_Y = 0.025

_GEOMETRY_LIMITS = {
    "hardsub": {"max_width": 0.96, "max_height": 0.20, "max_area": 0.16},
    "title": {"max_width": 0.96, "max_height": 0.28, "max_area": 0.22},
    "ui": {"max_width": 0.70, "max_height": 0.18, "max_area": 0.09},
}
_CAPTION_ROW_LIMITS = {
    # Portrait Douyin captions can legitimately span almost the full raster.
    # The physical cover remains bounded by `_caption_lane_cover`; rejecting
    # a 96–98% glyph envelope here caused valid rows to fail before render.
    "max_width": 0.985,
    "max_height": 0.10,
    # Keep area consistent with the independently allowed width/height. Wide
    # single-row captions near the lower third can legitimately occupy ~8%.
    "max_area": 0.09,
}

# ``ui_chip`` describes the source visual role, not the amount of Vietnamese
# text that the approved translation will occupy.  A compact Chinese chip can
# legitimately expand into a short Vietnamese phrase.  Keeping such a phrase
# in the micro-ui one-line contract is what caused otherwise valid locked text
# to fail at adaptive render time.  This threshold is deliberately conservative
# and is measured after removing whitespace, so numeric/unit chips remain in
# the compact path while conversational labels get a two-line UI layout.
_MICRO_UI_MAX_VISIBLE_CHARS = 18


class RenderPolicyError(RuntimeError):
    """A track cannot safely receive an automatic render policy."""


def enforce_unified_editor_cover(cover: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the production-wide editor-overlay concealment contract.

    Geometry and damage-budget decisions may still come from an approved
    remediation, but the renderer must never switch concealment algorithms by
    role, motion, or frame.
    """

    output = dict(cover)
    output.update(
        {
            "strategy": UNIFIED_EDITOR_COVER_STRATEGY,
            "mask_mode": UNIFIED_EDITOR_COVER_MASK_MODE,
            "consistency_policy": UNIFIED_EDITOR_COVER_POLICY_VERSION,
            "blur": dict(UNIFIED_EDITOR_BLUR_PROFILE),
            "transition_hold_frames": UNIFIED_EDITOR_TRANSITION_HOLD_FRAMES,
            "fallback": "operator_review",
        }
    )
    return output


def enforce_unified_editor_cover_contract(
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Reassert the unified cover at the final renderer boundary."""

    output = dict(contract)
    fps = max(1.0, float(dict(contract.get("video") or {}).get("fps") or 30.0))
    transition_hold_frames = max(
        UNIFIED_EDITOR_TRANSITION_HOLD_FRAMES,
        min(12, int(round(fps * UNIFIED_EDITOR_TRANSITION_HOLD_SECONDS))),
    )
    tracks: list[dict[str, Any]] = []
    for raw in list(contract.get("render_tracks") or []):
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        policy = dict(row.get("render_policy") or {})
        cover = policy.get("cover")
        if isinstance(cover, Mapping):
            context = dict(policy.get("context") or {})
            context["cover_consistency_policy"] = (
                UNIFIED_EDITOR_COVER_POLICY_VERSION
            )
            policy["context"] = context
            unified = enforce_unified_editor_cover(cover)
            unified["transition_hold_frames"] = transition_hold_frames
            unified["transition_hold_seconds"] = (
                UNIFIED_EDITOR_TRANSITION_HOLD_SECONDS
            )
            # A large opening title is still concealed with the same soft
            # reconstruction profile, but a full rectangular plate over a
            # face/chest is visibly destructive.  Keep only the source-bound
            # stylized glyph mask for this narrowly identified role.
            if bool(context.get("intro_stylized_title")):
                unified["mask_mode"] = "stylized_components"
            policy["cover"] = unified
            row["render_policy"] = policy
        tracks.append(row)
    output["render_tracks"] = tracks
    output["render_policy_version"] = RENDER_POLICY_VERSION
    # Older persisted Phase-4 contracts may predate soft-cover epochs. Build
    # the runtime style authority deterministically at the final boundary so
    # frontend retries receive the same v20 renderer without mutating source
    # Phase-1/2 artifacts.
    if not list(output.get("soft_cover_epochs") or []) and tracks:
        tracks, epochs = _assign_soft_cover_epochs(tracks, fps=fps)
        output["render_tracks"] = tracks
        output["soft_cover_epochs"] = epochs
        counts = dict(output.get("counts") or {})
        counts["soft_cover_epochs"] = len(epochs)
        output["counts"] = counts
    return output


def normalize_render_text(value: Any) -> str:
    """Return a stable semantic key for approved render text."""

    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def _visible_text_length(value: Any) -> int:
    """Count visible code points for the typography-capacity guard."""

    return len(re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))))


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


def _caption_lane_cover(
    geometry: Mapping[str, float],
) -> dict[str, float]:
    """Return a padded but spatially bounded cover for one caption row.

    The old policy expanded every caption to the complete frame width and a
    fixed 10% frame height.  That hid detector uncertainty by creating an
    obvious horizontal blur bar.  Coverage keyframes and lane stabilization
    now handle uncertainty, so the per-row cover can stay close to the proven
    glyph envelope while retaining enough padding for outlines and shadows.
    """

    x = float(geometry["x"])
    y = float(geometry["y"])
    width = float(geometry["width"])
    height = float(geometry["height"])
    pad_x = max(0.018, min(0.045, width * 0.06))
    pad_y = max(0.008, min(0.016, height * 0.35))
    x0 = max(0.0, x - pad_x)
    x1 = min(1.0, x + width + pad_x)
    center_y = y + height * 0.5
    target_height = height + 2.0 * pad_y
    if height <= 0.055:
        target_height = max(0.050, min(0.072, target_height))
    else:
        target_height = min(0.125, target_height)
    y0 = max(0.0, center_y - target_height * 0.5)
    y1 = min(1.0, y0 + target_height)
    y0 = max(0.0, y1 - target_height)
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _caption_layout_safe_area(
    cover: Mapping[str, float],
) -> dict[str, float]:
    """Give Vietnamese text room without enlarging the source blur plate."""

    cover_x = float(cover["x"])
    cover_y = float(cover["y"])
    cover_width = float(cover["width"])
    cover_height = float(cover["height"])
    center_x = cover_x + cover_width * 0.5
    center_y = cover_y + cover_height * 0.5
    width = min(0.92, cover_width + 0.14)
    height = min(0.12, max(0.075, cover_height + 0.025))
    # This is a typography area, not a camera-safe crop.  Preserve the exact
    # cover center even when a long Vietnamese phrase legitimately needs more
    # than the left/right safe margin.
    x0 = max(0.0, min(1.0 - width, center_x - width * 0.5))
    y0 = max(0.0, min(1.0 - height, center_y - height * 0.5))
    return {"x": x0, "y": y0, "width": width, "height": height}


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
    coverage_geometries = [
        dict(raw.get("geometry") or {})
        for raw in list(
            dict(track.get("coverage_authority") or {}).get(
                "geometry_keyframes"
            )
            or []
        )
        if isinstance(raw, Mapping)
        and isinstance(raw.get("geometry"), Mapping)
    ]
    coverage_caption_votes = sum(
        float(value.get("width") or 0.0) >= 0.50
        and 0.0 < float(value.get("height") or 0.0) <= 0.10
        for value in coverage_geometries
    )
    coverage_caption_row = bool(
        coverage_geometries
        and coverage_caption_votes >= max(2, len(coverage_geometries) // 5)
    )
    caption_row = (
        kind == "ui"
        and not intro_visual_title
        and geometry["height"] <= 0.10
        and (
            bool(track.get("editor_caption_shadow_cover_only"))
            or
            geometry["width"] >= 0.50
            or (geometry["width"] >= 0.35 and geometry["y"] >= 0.45)
            or coverage_caption_row
        )
        # A blur-only scan may retain several adjacent geometry epochs for
        # one caption lane. Their overlap count can exceed six even though
        # each row is a valid full-width caption.  The provenance/cover-only
        # gate is deliberately required here; ordinary dense UI remains under
        # the stricter simultaneous-count safety limit.
        and (
            max(1, int(simultaneous_count)) <= 6
            or (
                bool(track.get("cover_only"))
                and geometry["width"] >= 0.50
                and str(
                    dict(track.get("visual_provenance") or {}).get(
                        "classification"
                    )
                    or ""
                )
                == "EDITOR_OVERLAY"
            )
        )
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
    micro_ui_source = (
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
    # A source chip can carry a longer approved Vietnamese phrase.  Preserve
    # its source geometry/cover role, but promote typography to the normal UI
    # scale so it may wrap instead of failing late in the renderer.
    # Only an explicit ``ui_chip`` is eligible for this promotion.  A compact
    # geometry inferred from a legacy semantic role is intentionally kept in
    # its historical micro-ui contract because its safe band is an authority
    # for source-preservation work, not a free-flowing translated label.
    micro_ui_overflow_promoted = (
        micro_ui_source
        and "ui_chip" in roles
        and _visible_text_length(track.get("text_vi"))
        > _MICRO_UI_MAX_VISIBLE_CHARS
    )
    micro_ui = micro_ui_source and not micro_ui_overflow_promoted
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
    bounded_residual_hardsub = bool(
        kind == "hardsub"
        and str(track.get("text_id") or "").startswith("p2r_")
        and (
            span_frames <= 12
            or bool(track.get("semantic_dialogue_residual_expanded"))
        )
        and geometry["width"] <= 1.0
        and geometry["height"] <= 0.10
        and area <= 0.10
    )
    if (
        geometry["width"] > limits["max_width"]
        or geometry["height"] > limits["max_height"]
        or area > limits["max_area"]
    ) and not bounded_residual_hardsub:
        raise RenderPolicyError(
            f"Sparse {kind} geometry exceeds automatic safety limits"
        )

    dense = max(1, int(simultaneous_count)) >= 8
    if caption_row:
        cover_roi = _caption_lane_cover(geometry)
    elif kind == "ui":
        cover_roi = _expand(
            geometry,
            pad_x=0.016 if dense else 0.010,
            pad_y=0.022 if dense else 0.012,
        )
    elif kind == "title":
        cover_roi = _expand(geometry, pad_x=0.020, pad_y=0.020)
    else:
        cover_roi = _expand(geometry, pad_x=0.020, pad_y=0.015)
    # Coverage authority can legitimately grow a detector box on frames where
    # a second subtitle line is present. The damage budget must cover that
    # frame-exact ROI too; otherwise a valid full-plate mask is rejected even
    # though the base Phase-1 geometry passed preflight.
    coverage_max_roi_area = 0.0
    for coverage_geometry in coverage_geometries:
        try:
            coverage_rect = _rect(coverage_geometry)
        except RenderPolicyError:
            continue
        if caption_row:
            coverage_roi = _caption_lane_cover(coverage_rect)
        elif kind == "ui":
            coverage_roi = _expand(
                coverage_rect,
                pad_x=0.016 if dense else 0.010,
                pad_y=0.022 if dense else 0.012,
            )
        elif kind == "title":
            coverage_roi = _expand(coverage_rect, pad_x=0.020, pad_y=0.020)
        else:
            coverage_roi = _expand(coverage_rect, pad_x=0.020, pad_y=0.015)
        coverage_max_roi_area = max(
            coverage_max_roi_area,
            float(coverage_roi["width"]) * float(coverage_roi["height"]),
        )
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
    max_lines = (
        3
        if kind == "hardsub"
        and str(track.get("text_id") or "").startswith("p2r_")
        and span_frames <= 12
        else 2
        if kind in {"hardsub", "title"} or caption_row
        else 2
        if kind == "ui" and micro_ui_overflow_promoted
        else 1
    )
    motion = None if motion_score is None else max(0.0, min(1.0, float(motion_score)))
    bounded_dense_ink_hardsub = (
        kind == "hardsub"
        and not dense
        and geometry["width"] >= 0.35
        and geometry["height"] <= 0.10
    )
    layout_safe_area = (
        _caption_layout_safe_area(cover_roi)
        if (
            caption_row
            or bool(track.get("semantic_dialogue_residual_expanded"))
            or (
                bounded_dense_ink_hardsub
                and geometry["width"] >= 0.45
            )
        )
        else cover_roi
    )
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

    # A short opening title can legitimately occupy more than 12% of a
    # portrait frame. Its mask is component-bound rather than a rectangular
    # plate, so the normal sparse-UI ceiling would block the safest removal
    # mode before structural QA runs. Keep a bounded title-only allowance;
    # this never applies to ordinary captions/UI or full-frame masks.
    non_dense_damage_limit = (
        0.20 if intro_visual_title else 0.16 if caption_row else 0.12
    )
    base_damage_budget = (
        0.55
        if dense
        else min(
            non_dense_damage_limit,
            max(
                0.015,
                area * 3.0,
                (
                    float(cover_roi["width"])
                    * float(cover_roi["height"])
                    * 1.02
                    if caption_row
                    else 0.0
                ),
            ),
        )
    )
    title_damage_budget = (
        max(
            base_damage_budget,
            float(cover_roi["width"])
            * float(cover_roi["height"])
            * 1.02,
        )
        if intro_visual_title
        else base_damage_budget
    )
    damage_budget = {
        "max_frame_change_fraction": (
            title_damage_budget
            if coverage_max_roi_area <= 0.0
            else min(
                non_dense_damage_limit if not dense else 0.55,
                max(title_damage_budget, coverage_max_roi_area * 1.02),
            )
        ),
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
            "micro_ui_source": micro_ui_source,
            "micro_ui_overflow_promoted": micro_ui_overflow_promoted,
            "output_residual_bounded_dense_mask": dense_panel_plate,
            "bounded_dense_ink_hardsub": bounded_dense_ink_hardsub,
            "source_kind": original_kind,
            "effective_kind": effective_kind,
            "typography_kind": typography_kind,
            "cover_consistency_policy": UNIFIED_EDITOR_COVER_POLICY_VERSION,
            "intro_stylized_title": bool(intro_visual_title),
        },
        "cover": {
            **enforce_unified_editor_cover({
            "strategy": strategy,
            "roi": cover_roi,
            "geometry_mode": (
                "stable_caption_envelope" if caption_row else "track_relative"
            ),
            "mask_dilate_radius_fraction": (
                0.10
                if kind == "hardsub"
                else 0.08
                if kind == "ui" and dense
                else 0.04
            ),
            }),
            "mask_mode": (
                "stylized_components"
                if intro_visual_title
                else UNIFIED_EDITOR_COVER_MASK_MODE
            ),
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


def _linear_quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, float(fraction))) * (len(ordered) - 1)
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _seed_cover_intervals_from_evidence(
    rows: list[dict[str, Any]],
    *,
    fps: float = 30.0,
) -> int:
    """Build a fail-closed physical concealment envelope.

    OCR presence is evidence, not a complete timing authority.  A detector can
    miss the first/last frames of a caption (or one frame during a transition),
    which used to make the renderer remove the blur while the Chinese glyphs
    were still visible.  Editor-caption rows therefore use the union of their
    semantic interval and observed evidence.  Non-caption UI keeps the stricter
    observed boundary so texture in phones/hair cannot create a long blur.

    A semantic dialogue residual is a separate authority case: Phase 4 has
    already expanded its short OCR observation to the approved transcript
    segment.  Never collapse that interval back to the sparse detector hits,
    otherwise the original hard-sub leaks before and after the sampled frame.
    """

    adjusted = 0
    for row in rows:
        boundary = dict(row.get("boundary_evidence") or {})
        hits = sorted(
            int(value)
            for value in list(row.get("hit_frames") or [])
            if isinstance(value, (int, float))
        )
        raw_first = boundary.get("observed_first_frame")
        raw_last = boundary.get("observed_last_frame")
        observed_first = (
            int(raw_first)
            if isinstance(raw_first, (int, float))
            else hits[0]
            if hits
            else None
        )
        observed_last = (
            int(raw_last)
            if isinstance(raw_last, (int, float))
            else hits[-1]
            if hits
            else None
        )
        semantic_dialogue_expanded = bool(
            row.get("semantic_dialogue_residual_expanded")
        )
        if semantic_dialogue_expanded:
            raw_semantic_start = row.get("start_frame")
            raw_semantic_end = row.get("end_frame")
            semantic_start = (
                int(raw_semantic_start)
                if isinstance(raw_semantic_start, (int, float))
                else int(observed_first or 0)
            )
            semantic_end = (
                int(raw_semantic_end)
                if isinstance(raw_semantic_end, (int, float))
                else int(observed_last or semantic_start)
            )
            semantic_start = max(0, semantic_start)
            semantic_end = max(semantic_start, semantic_end)
            prior_start = int(
                row.get("cover_start_frame")
                if isinstance(row.get("cover_start_frame"), (int, float))
                else semantic_start
            )
            prior_end = int(
                row.get("cover_end_frame")
                if isinstance(row.get("cover_end_frame"), (int, float))
                else semantic_end
            )
            # The approved transcript closes detector gaps, while a genuine
            # observed subtitle can start a little before or finish a little
            # after the ASR segment boundary.  Keep the physical union: the
            # transcript must never be shortened to OCR hits, and OCR evidence
            # must never be clipped merely because speech timing ended first.
            cover_start = min(
                semantic_start,
                observed_first
                if observed_first is not None
                else semantic_start,
            )
            cover_end = max(
                semantic_end,
                observed_last
                if observed_last is not None
                else semantic_end,
            )
            if (cover_start, cover_end) != (prior_start, prior_end):
                adjusted += 1
            row["cover_start_frame"] = cover_start
            row["cover_end_frame"] = cover_end
            policy = dict(row.get("render_policy") or {})
            context = dict(policy.get("context") or {})
            context["cover_timing_authority"] = {
                "mode": "approved_transcript_segment_union",
                "observed_range": (
                    [observed_first, observed_last]
                    if observed_first is not None and observed_last is not None
                    else None
                ),
                "semantic_range": [semantic_start, semantic_end],
                "effective_range": [cover_start, cover_end],
            }
            policy["context"] = context
            row["render_policy"] = policy
            continue
        if observed_first is None or observed_last is None:
            continue
        coverage_ranges = [
            (int(raw[0]), int(raw[1]))
            for raw in list(
                dict(row.get("coverage_authority") or {}).get("presence_ranges")
                or []
            )
            if isinstance(raw, (list, tuple))
            and len(raw) == 2
            and int(raw[1]) >= int(raw[0])
        ]
        coverage_first = (
            min(start for start, _end in coverage_ranges)
            if coverage_ranges
            else observed_first
        )
        coverage_last = (
            max(end for _start, end in coverage_ranges)
            if coverage_ranges
            else observed_last
        )
        context = dict(
            dict(row.get("render_policy") or {}).get("context") or {}
        )
        provenance = dict(row.get("visual_provenance") or {})
        provenance_reasons = set(provenance.get("reasons") or [])
        geometry = dict(row.get("geometry") or {})
        geometry_center_y = float(geometry.get("y") or 0.0) + float(
            geometry.get("height") or 0.0
        ) * 0.5
        geometry_width = float(geometry.get("width") or 0.0)
        # Caption-lane inference is persisted by Phase 1.  Older contracts
        # may not carry ``caption_row`` on every sibling, so retain the
        # geometry/provenance fallback for a wide lower-third editor lane.
        is_editor_caption = bool(
            context.get("caption_row")
            or "caption_lane_provenance_overrides_dense_source_context"
            in provenance_reasons
            or "sequential_screen_locked_caption_lane" in provenance_reasons
            or (
                str(context.get("source_kind") or str(row.get("kind") or ""))
                in {"ui", "title", "generic"}
                and geometry_center_y >= 0.56
                and geometry_width >= 0.14
                and not bool(context.get("micro_ui_source"))
            )
        )
        semantic_start = int(row.get("start_frame") or observed_first)
        semantic_end = int(row.get("end_frame") or observed_last)
        if is_editor_caption:
            # Physical concealment is the union of the semantic interval,
            # detector evidence and the all-frame proxy presence envelope.
            # The previous implementation discarded ``coverage_ranges`` for
            # non-caption UI siblings, which is exactly how a label surviving
            # a few frames past OCR's last hit leaked into the output.
            cover_start = min(observed_first, coverage_first, semantic_start)
            cover_end = max(observed_last, coverage_last, semantic_end)
            timing_mode = "semantic_observed_coverage_union"
            if coverage_ranges:
                # Keep short gaps as a separate runtime activation authority;
                # the envelope above remains continuous for endpoint safety.
                rate = max(1.0, float(fps))
                bridge = max(1, int(round(rate * CAPTION_PRESENCE_BRIDGE_SECONDS)))
                merged_ranges: list[list[int]] = []
                for start, end in sorted(coverage_ranges):
                    if not merged_ranges or start - merged_ranges[-1][1] - 1 > bridge:
                        merged_ranges.append([start, end])
                    else:
                        merged_ranges[-1][1] = max(merged_ranges[-1][1], end)
                context["physical_presence_ranges"] = merged_ranges
        else:
            cover_start = observed_first
            cover_end = observed_last
            timing_mode = "observed_detector_boundary"
        nested_shadow_extension = dict(
            row.get("nested_shadow_timing_extension") or {}
        )
        raw_shadow_start = nested_shadow_extension.get("start_frame")
        raw_shadow_end = nested_shadow_extension.get("end_frame")
        if isinstance(raw_shadow_start, (int, float)):
            cover_start = min(cover_start, int(raw_shadow_start))
        if isinstance(raw_shadow_end, (int, float)):
            cover_end = max(cover_end, int(raw_shadow_end))
        if nested_shadow_extension:
            timing_mode = f"{timing_mode}_nested_shadow_union"
        prior_start = int(
            row.get("cover_start_frame") or row.get("start_frame") or 0
        )
        prior_end = int(
            row.get("cover_end_frame") or row.get("end_frame") or prior_start
        )
        if (cover_start, cover_end) != (prior_start, prior_end):
            adjusted += 1
        row["cover_start_frame"] = max(0, cover_start)
        row["cover_end_frame"] = max(max(0, cover_start), cover_end)
        policy = dict(row.get("render_policy") or {})
        context["cover_timing_authority"] = {
            "mode": timing_mode,
            "observed_range": [observed_first, observed_last],
            "coverage_range": [coverage_first, coverage_last],
            "semantic_range": [semantic_start, semantic_end],
            "effective_range": [row["cover_start_frame"], row["cover_end_frame"]],
        }
        policy["context"] = context
        row["render_policy"] = policy
    return adjusted


def _caption_evidence_horizontal_roi(
    row: Mapping[str, Any],
    fallback: Mapping[str, Any],
) -> dict[str, float]:
    """Return a bounded per-caption horizontal envelope.

    Caption OCR boxes commonly clip the first/last outlined glyph.  Use the
    temporal geometry keyframes to recover that envelope, then add a small
    height-scaled margin.  The margin is capped below a full-width lane and is
    applied per content row, so short captions do not inherit a long sibling's
    blur width.
    """

    geometries = [
        dict(raw.get("geometry") or {})
        for raw in list(
            dict(row.get("coverage_authority") or {}).get("geometry_keyframes")
            or []
        )
        if isinstance(raw, Mapping) and isinstance(raw.get("geometry"), Mapping)
    ]
    source = dict(fallback)
    evidence_span = 0.0
    if geometries:
        lefts = [float(item.get("x") or 0.0) for item in geometries]
        rights = [
            float(item.get("x") or 0.0) + float(item.get("width") or 0.0)
            for item in geometries
        ]
        evidence_span = max(rights) - min(lefts)
        left = min(float(source.get("x") or 0.0), _linear_quantile(lefts, 0.05))
        right = max(
            float(source.get("x") or 0.0) + float(source.get("width") or 0.0),
            _linear_quantile(rights, 0.95),
        )
    else:
        left = float(source.get("x") or 0.0)
        right = left + float(source.get("width") or 0.0)
    row_geometry = dict(row.get("geometry") or {})
    row_height = float(row_geometry.get("height") or source.get("height") or 0.03)
    pad_x = (
        0.125
        if evidence_span >= 0.65
        else max(0.035, min(0.065, row_height * 2.0))
    )
    left = max(0.0, left - pad_x)
    right = min(1.0, right + pad_x)
    # Never recreate the old unconditional full-width caption lane.  Only an
    # evidence-proven long row may approach the edges, and even then a visible
    # margin remains on both sides.
    max_width = 0.985 if evidence_span >= 0.65 else 0.97
    if right - left > max_width:
        center = (left + right) * 0.5
        left = max(0.0, center - max_width * 0.5)
        right = min(1.0, left + max_width)
        left = max(0.0, right - max_width)
    return {
        "x": left,
        "y": float(source.get("y") or 0.0),
        "width": max(0.01, right - left),
        "height": float(source.get("height") or 0.01),
    }


def _slant_safe_vertical_envelope(
    row: Mapping[str, Any],
    fallback: Mapping[str, Any],
) -> tuple[float, float]:
    """Return conservative vertical bounds across temporal glyph evidence.

    Italic/rotated copy often yields alternating narrow DBNet rectangles. The
    cover must follow the union of observed corners, not the median baseline.
    Padding is height-scaled and bounded so this cannot recreate a giant lane.
    """

    evidence_geometries = [
        dict(raw.get("geometry") or {})
        for raw in list(
            dict(row.get("coverage_authority") or {}).get("geometry_keyframes")
            or []
        )
        if isinstance(raw, Mapping) and isinstance(raw.get("geometry"), Mapping)
    ]
    fallback_geometry = dict(fallback)
    if not evidence_geometries:
        y0 = float(fallback_geometry.get("y") or 0.0)
        return y0, min(
            1.0, y0 + float(fallback_geometry.get("height") or 0.0)
        )
    geometries = [
        *evidence_geometries,
        dict(row.get("geometry") or fallback),
        fallback_geometry,
    ]
    tops = [float(item.get("y") or 0.0) for item in geometries]
    bottoms = [
        float(item.get("y") or 0.0) + float(item.get("height") or 0.0)
        for item in geometries
    ]
    heights = [
        max(0.001, float(item.get("height") or 0.0)) for item in geometries
    ]
    baseline_height = max(0.008, _linear_quantile(heights, 0.75))
    observed_spread = max(bottoms) - min(tops)
    # Extra spread across keyframes is strong evidence of a slanted or stacked
    # glyph envelope; ordinary stable rows receive only the normal 0.18h pad.
    slant_extra = max(0.0, observed_spread - baseline_height) * 0.35
    pad = min(0.035, baseline_height * 0.18 + slant_extra)
    return max(0.0, min(tops) - pad), min(1.0, max(bottoms) + pad)


def _stabilize_editor_card_panels(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Bind every row of a solid editor card to one physical cover object.

    Phase 1 persists a frame-derived panel box only after strong provenance
    grouping.  At render-policy time we group synchronized, overlapping panel
    boxes into one epoch, union their timing, and assign the same cover id/ROI
    to each member.  The frame renderer will therefore process the card once,
    eliminating holes, double blur and per-row flicker.
    """

    candidates = [
        row
        for row in rows
        if len(list(row.get("editor_card_panel_box") or [])) == 4
        and str(
            dict(row.get("visual_provenance") or {}).get("classification")
            or ""
        )
        == "EDITOR_OVERLAY"
    ]
    if not candidates:
        return rows, 0

    def panel_roi(row: Mapping[str, Any]) -> dict[str, float]:
        normalized = dict(row.get("editor_card_panel_geometry") or {})
        return _rect(normalized)

    def time_overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        return not (
            int(left.get("end_frame") or 0) < int(right.get("start_frame") or 0)
            or int(right.get("end_frame") or 0) < int(left.get("start_frame") or 0)
        )

    def connected(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        if not time_overlap(left, right):
            return False
        a, b = panel_roi(left), panel_roi(right)
        return _geometry_overlap_over_smaller(a, b) >= 0.72

    neighbors = {index: set() for index in range(len(candidates))}
    for index, left in enumerate(candidates):
        for other_index in range(index + 1, len(candidates)):
            if connected(left, candidates[other_index]):
                neighbors[index].add(other_index)
                neighbors[other_index].add(index)
    visited: set[int] = set()
    components: list[list[dict[str, Any]]] = []
    for seed in range(len(candidates)):
        if seed in visited:
            continue
        pending = [seed]
        member_indices: set[int] = set()
        while pending:
            current = pending.pop()
            if current in member_indices:
                continue
            member_indices.add(current)
            pending.extend(neighbors[current])
        visited.update(member_indices)
        members = [candidates[index] for index in sorted(member_indices)]
        if len(members) >= 2:
            components.append(members)

    for group_index, component in enumerate(
        sorted(
            components,
            key=lambda group: min(int(row.get("start_frame") or 0) for row in group),
        ),
        start=1,
    ):
        rois = [panel_roi(row) for row in component]
        x0 = min(float(roi.get("x") or 0.0) for roi in rois)
        y0 = min(float(roi.get("y") or 0.0) for roi in rois)
        x1 = max(float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0) for roi in rois)
        y1 = max(float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0) for roi in rois)
        union_roi = {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
        group_id = f"editor_card_panel_{group_index:03d}"
        member_ids = sorted(str(row.get("text_id") or "") for row in component)
        cover_start = min(int(row.get("cover_start_frame") or row.get("start_frame") or 0) for row in component)
        cover_end = max(int(row.get("cover_end_frame") or row.get("end_frame") or 0) for row in component)
        for row in component:
            row["cover_start_frame"] = cover_start
            row["cover_end_frame"] = cover_end
            policy = dict(row.get("render_policy") or {})
            context = dict(policy.get("context") or {})
            cover = dict(policy.get("cover") or {})
            budget = dict(policy.get("damage_budget") or {})
            context.update({
                "editor_card_panel_id": group_id,
                "editor_card_panel_members": member_ids,
                "editor_card_panel_cover": True,
            })
            cover.update({
                "roi": union_roi,
                "editor_card_panel_id": group_id,
                "caption_cover_group_id": group_id,
                "geometry_mode": "solid_editor_card_panel_union",
            })
            budget["max_frame_change_fraction"] = min(
                0.20,
                max(float(budget.get("max_frame_change_fraction") or 0.0), (x1 - x0) * (y1 - y0) * 1.02),
            )
            policy.update({"context": context, "cover": cover, "damage_budget": budget})
            row["render_policy"] = policy
    return rows, len(components)


def _stabilize_caption_cover_groups(
    rows: list[dict[str, Any]],
    *,
    max_bridge_frames: int,
) -> tuple[list[dict[str, Any]], int, int, int]:
    """Share a bounded, temporally closed blur authority across caption rows.

    OCR content tracks are allowed to change at sentence boundaries; the blur
    plate is not.  Connected rows in the same visual lane receive a robust
    common ROI, while a genuine spatial outlier retains only the extra area it
    needs on its own interval.  Short detector gaps are split between adjacent
    rows so no uncovered frame exists and no row remains active for the whole
    video.
    """

    candidates = [
        row
        for row in rows
        if bool(
            dict(dict(row.get("render_policy") or {}).get("context") or {}).get(
                "caption_row"
            )
        )
    ]
    if not candidates:
        return rows, 0, 0, 0

    def temporal_gap(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
        left_start = int(left.get("cover_start_frame") or left.get("start_frame") or 0)
        left_end = int(left.get("cover_end_frame") or left.get("end_frame") or left_start)
        right_start = int(right.get("cover_start_frame") or right.get("start_frame") or 0)
        right_end = int(right.get("cover_end_frame") or right.get("end_frame") or right_start)
        return max(0, right_start - left_end - 1, left_start - right_end - 1)

    def same_lane(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        a = dict(left.get("geometry") or {})
        b = dict(right.get("geometry") or {})
        ah = float(a.get("height") or 0.0)
        bh = float(b.get("height") or 0.0)
        ac = float(a.get("y") or 0.0) + ah * 0.5
        bc = float(b.get("y") or 0.0) + bh * 0.5
        if abs(ac - bc) > max(0.024, 0.80 * max(ah, bh)):
            return False
        horizontal_overlap = _axis_overlap_over_smaller(
            float(a.get("x") or 0.0),
            float(a.get("width") or 0.0),
            float(b.get("x") or 0.0),
            float(b.get("width") or 0.0),
        )
        return horizontal_overlap >= 0.15 or max(
            float(a.get("width") or 0.0), float(b.get("width") or 0.0)
        ) >= 0.35

    by_id = {
        str(row.get("text_id") or ""): row
        for row in candidates
        if str(row.get("text_id") or "")
    }
    neighbors: dict[str, set[str]] = {text_id: set() for text_id in by_id}
    candidate_values = list(by_id.values())
    for index, left in enumerate(candidate_values):
        left_id = str(left.get("text_id") or "")
        for right in candidate_values[index + 1 :]:
            right_id = str(right.get("text_id") or "")
            if (
                temporal_gap(left, right) <= max(1, int(max_bridge_frames))
                and same_lane(left, right)
            ):
                neighbors[left_id].add(right_id)
                neighbors[right_id].add(left_id)

    components: list[list[dict[str, Any]]] = []
    visited: set[str] = set()
    for seed in sorted(by_id):
        if seed in visited or not neighbors.get(seed):
            continue
        pending = [seed]
        member_ids: set[str] = set()
        while pending:
            current = pending.pop()
            if current in member_ids:
                continue
            member_ids.add(current)
            pending.extend(sorted(neighbors.get(current) or set()))
        visited.update(member_ids)
        component = [by_id[text_id] for text_id in sorted(member_ids)]
        if len(component) >= 2:
            components.append(component)

    for group_index, component in enumerate(
        sorted(
            components,
            key=lambda group: min(int(row.get("start_frame") or 0) for row in group),
        ),
        start=1,
    ):
        group_id = f"caption_cover_group_{group_index:03d}"
        member_rois = [
            dict(
                dict(dict(row.get("render_policy") or {}).get("cover") or {}).get(
                    "roi"
                )
                or {}
            )
            for row in component
        ]
        y0_values = [float(roi.get("y") or 0.0) for roi in member_rois]
        y1_values = [
            float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0)
            for roi in member_rois
        ]
        robust = len(component) >= 5
        # Vertical placement is shared to prevent a one-frame y jitter from
        # producing a visible blur jump.  Horizontal placement remains
        # content-specific: a long sentence may legitimately reach the frame
        # edges while a short label should retain a compact cover.
        common = {
            "y": _linear_quantile(y0_values, 0.10) if robust else min(y0_values),
        }
        common_y1 = (
            _linear_quantile(y1_values, 0.90) if robust else max(y1_values)
        )
        common["height"] = max(0.01, common_y1 - common["y"])

        # Close short gaps by assigning the uncovered frames to the nearest
        # neighboring authority.  Text timing itself remains untouched.
        ordered = sorted(
            component,
            key=lambda row: (
                int(row.get("cover_start_frame") or row.get("start_frame") or 0),
                int(row.get("cover_end_frame") or row.get("end_frame") or 0),
                str(row.get("text_id") or ""),
            ),
        )
        for left, right in zip(ordered, ordered[1:]):
            left_end = int(
                left.get("cover_end_frame") or left.get("end_frame") or 0
            )
            right_start = int(
                right.get("cover_start_frame") or right.get("start_frame") or 0
            )
            gap = right_start - left_end - 1
            if not 0 < gap <= max(1, int(max_bridge_frames)):
                continue
            boundary = (left_end + right_start) // 2
            left["cover_end_frame"] = boundary
            right["cover_start_frame"] = boundary + 1

        member_ids = sorted(str(row.get("text_id") or "") for row in component)
        for row, member_roi in zip(component, member_rois):
            # Preserve a real outlier only on its own interval; ordinary rows
            # share exactly the same ROI and are therefore rendered once even
            # when conservative cover intervals overlap.
            evidence_roi = _caption_evidence_horizontal_roi(row, member_roi)
            evidence_y0, evidence_y1 = _slant_safe_vertical_envelope(
                row, member_roi
            )
            x0 = float(evidence_roi["x"])
            x1 = x0 + float(evidence_roi["width"])
            # All ordinary siblings retain one stable vertical plate. Only
            # genuine glyph evidence extending outside that common envelope
            # enlarges it; small baseline jitter must not move the blur.
            y0 = min(float(common["y"]), evidence_y0)
            y1 = max(common_y1, evidence_y1)
            stable_roi = {
                "x": max(0.0, x0),
                "y": max(0.0, y0),
                "width": min(1.0, x1) - max(0.0, x0),
                "height": min(1.0, y1) - max(0.0, y0),
            }
            policy = dict(row.get("render_policy") or {})
            context = dict(policy.get("context") or {})
            cover = dict(policy.get("cover") or {})
            layout = dict(policy.get("layout") or {})
            budget = dict(policy.get("damage_budget") or {})
            context.update(
                {
                    "caption_cover_group_id": group_id,
                    "caption_cover_group_members": member_ids,
                    "caption_cover_stabilized": True,
                    "caption_cover_geometry_mode": "evidence_adaptive_horizontal",
                }
            )
            cover.update(
                {
                    "roi": stable_roi,
                    "geometry_mode": "stable_caption_group_adaptive_horizontal",
                    "caption_cover_group_id": group_id,
                }
            )
            if str(layout.get("mode") or "") == "cover_aligned":
                layout["safe_area"] = _caption_layout_safe_area(stable_roi)
            budget["max_frame_change_fraction"] = min(
                0.16,
                max(
                    float(budget.get("max_frame_change_fraction") or 0.0),
                    float(stable_roi["width"])
                    * float(stable_roi["height"])
                    * 1.02,
                ),
            )
            policy.update(
                {
                    "context": context,
                    "cover": cover,
                    "layout": layout,
                    "damage_budget": budget,
                }
            )
            row["render_policy"] = policy
    # A caption can move vertically between two editor templates while staying
    # visible throughout the transition.  Keep those rows in separate spatial
    # groups, but split a short uncovered interval between their cover
    # authorities so neither the old nor new position can flash Chinese.
    transition_bridges = 0
    chronological = sorted(
        candidates,
        key=lambda row: (
            int(row.get("cover_start_frame") or row.get("start_frame") or 0),
            int(row.get("cover_end_frame") or row.get("end_frame") or 0),
        ),
    )
    for right in chronological:
        right_start = int(
            right.get("cover_start_frame") or right.get("start_frame") or 0
        )
        right_geometry = dict(right.get("geometry") or {})
        right_center_y = float(right_geometry.get("y") or 0.0) + float(
            right_geometry.get("height") or 0.0
        ) * 0.5
        predecessors: list[tuple[int, dict[str, Any]]] = []
        for left in chronological:
            if left is right:
                continue
            left_end = int(
                left.get("cover_end_frame") or left.get("end_frame") or 0
            )
            gap = right_start - left_end - 1
            if not 0 < gap <= max(1, int(max_bridge_frames)):
                continue
            left_geometry = dict(left.get("geometry") or {})
            left_center_y = float(left_geometry.get("y") or 0.0) + float(
                left_geometry.get("height") or 0.0
            ) * 0.5
            if abs(left_center_y - right_center_y) > 0.055:
                continue
            if _axis_overlap_over_smaller(
                float(left_geometry.get("x") or 0.0),
                float(left_geometry.get("width") or 0.0),
                float(right_geometry.get("x") or 0.0),
                float(right_geometry.get("width") or 0.0),
            ) < 0.15:
                continue
            predecessors.append((left_end, left))
        if not predecessors:
            continue
        left_end, left = max(predecessors, key=lambda item: item[0])
        boundary = (left_end + right_start) // 2
        left["cover_end_frame"] = boundary
        right["cover_start_frame"] = boundary + 1
        for row, direction in ((left, "outgoing"), (right, "incoming")):
            policy = dict(row.get("render_policy") or {})
            context = dict(policy.get("context") or {})
            context["caption_transition_bridge"] = {
                "direction": direction,
                "boundary_frame": boundary,
            }
            policy["context"] = context
            row["render_policy"] = policy
        transition_bridges += 1
    # Compact labels stacked above a wide caption often belong to the same
    # editor card.  OCR may lose all compact rows at once while the card remains
    # visible for several more frames.  Extend only their concealment lifetime
    # when temporal end boundaries and the card geometry agree; do not merge
    # them into one tall blur rectangle and do not extend Vietnamese text.
    stacked_sibling_extensions = 0
    for anchor in candidates:
        anchor_start = int(anchor.get("start_frame") or 0)
        anchor_end = int(anchor.get("end_frame") or anchor_start)
        anchor_geometry = dict(anchor.get("geometry") or {})
        anchor_center_x = float(anchor_geometry.get("x") or 0.0) + float(
            anchor_geometry.get("width") or 0.0
        ) * 0.5
        anchor_center_y = float(anchor_geometry.get("y") or 0.0) + float(
            anchor_geometry.get("height") or 0.0
        ) * 0.5
        for sibling in rows:
            if sibling is anchor:
                continue
            sibling_policy = dict(sibling.get("render_policy") or {})
            sibling_context = dict(sibling_policy.get("context") or {})
            if bool(sibling_context.get("caption_row")):
                continue
            geometry = dict(sibling.get("geometry") or {})
            width = float(geometry.get("width") or 0.0)
            height = float(geometry.get("height") or 0.0)
            if width <= 0.0 or height <= 0.0 or width > 0.45 or height > 0.10:
                continue
            sibling_start = int(sibling.get("start_frame") or 0)
            sibling_end = int(sibling.get("end_frame") or sibling_start)
            if abs(sibling_end - anchor_end) > 3:
                continue
            overlap = max(
                0,
                min(anchor_end, sibling_end) - max(anchor_start, sibling_start) + 1,
            )
            sibling_span = max(1, sibling_end - sibling_start + 1)
            if overlap / float(sibling_span) < 0.50:
                continue
            center_x = float(geometry.get("x") or 0.0) + width * 0.5
            center_y = float(geometry.get("y") or 0.0) + height * 0.5
            if abs(center_x - anchor_center_x) > 0.40:
                continue
            vertical_distance = abs(center_y - anchor_center_y)
            if not 0.035 <= vertical_distance <= 0.22:
                continue
            prior_cover_end = int(
                sibling.get("cover_end_frame") or sibling_end
            )
            extended_end = sibling_end + max(1, int(max_bridge_frames))
            if extended_end <= prior_cover_end:
                continue
            sibling["cover_end_frame"] = extended_end
            sibling_context["stacked_caption_sibling_cover_extension"] = {
                "anchor_text_id": str(anchor.get("text_id") or ""),
                "original_end_frame": prior_cover_end,
                "extended_end_frame": extended_end,
            }
            sibling_policy["context"] = sibling_context
            sibling["render_policy"] = sibling_policy
            stacked_sibling_extensions += 1
    return rows, len(components), transition_bridges, stacked_sibling_extensions


def _assign_soft_cover_epochs(
    rows: list[dict[str, Any]],
    *,
    fps: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Bind visually related editor tracks to one deterministic style epoch.

    An epoch does not enlarge every member to one giant rectangle. It locks the
    concealment profile (glyph scale, edge softness and reconstruction order)
    while each member keeps its approved geometry. Caption groups are already
    spatially stabilized; compact UI/title rows join only when their temporal
    gap is short and their cover regions strongly overlap.
    """

    by_id = {
        str(row.get("text_id") or ""): row
        for row in rows
        if str(row.get("text_id") or "")
    }
    neighbors: dict[str, set[str]] = {text_id: set() for text_id in by_id}
    max_gap = max(3, min(24, int(round(max(1.0, fps) * 0.45))))

    def span(row: Mapping[str, Any]) -> tuple[int, int]:
        start = int(row.get("cover_start_frame") or row.get("start_frame") or 0)
        end = int(row.get("cover_end_frame") or row.get("end_frame") or start)
        return start, end

    def gap(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
        left_start, left_end = span(left)
        right_start, right_end = span(right)
        return max(0, right_start - left_end - 1, left_start - right_end - 1)

    def cover_roi(row: Mapping[str, Any]) -> dict[str, Any]:
        policy = dict(row.get("render_policy") or {})
        return dict(dict(policy.get("cover") or {}).get("roi") or row.get("geometry") or {})

    values = list(by_id.values())
    for index, left in enumerate(values):
        left_id = str(left.get("text_id") or "")
        left_policy = dict(left.get("render_policy") or {})
        left_context = dict(left_policy.get("context") or {})
        left_caption_group = str(left_context.get("caption_cover_group_id") or "")
        left_kind = str(left_context.get("effective_kind") or left.get("kind") or "ui")
        left_roi = cover_roi(left)
        for right in values[index + 1 :]:
            right_id = str(right.get("text_id") or "")
            right_policy = dict(right.get("render_policy") or {})
            right_context = dict(right_policy.get("context") or {})
            right_caption_group = str(right_context.get("caption_cover_group_id") or "")
            right_kind = str(right_context.get("effective_kind") or right.get("kind") or "ui")
            same_caption_epoch = bool(
                left_caption_group
                and left_caption_group == right_caption_group
            )
            if not same_caption_epoch:
                if left_kind != right_kind or gap(left, right) > max_gap:
                    continue
                right_roi = cover_roi(right)
                horizontal = _axis_overlap_over_smaller(
                    float(left_roi.get("x") or 0.0),
                    float(left_roi.get("width") or 0.0),
                    float(right_roi.get("x") or 0.0),
                    float(right_roi.get("width") or 0.0),
                )
                vertical = _axis_overlap_over_smaller(
                    float(left_roi.get("y") or 0.0),
                    float(left_roi.get("height") or 0.0),
                    float(right_roi.get("y") or 0.0),
                    float(right_roi.get("height") or 0.0),
                )
                if horizontal < 0.55 or vertical < 0.55:
                    continue
            neighbors[left_id].add(right_id)
            neighbors[right_id].add(left_id)

    components: list[list[dict[str, Any]]] = []
    visited: set[str] = set()
    for seed in sorted(by_id):
        if seed in visited:
            continue
        pending = [seed]
        member_ids: set[str] = set()
        while pending:
            current = pending.pop()
            if current in member_ids:
                continue
            member_ids.add(current)
            pending.extend(sorted(neighbors.get(current) or set()))
        visited.update(member_ids)
        components.append([by_id[text_id] for text_id in sorted(member_ids)])

    epochs: list[dict[str, Any]] = []
    for epoch_index, component in enumerate(
        sorted(
            components,
            key=lambda group: min(span(row)[0] for row in group),
        ),
        start=1,
    ):
        epoch_id = f"soft_cover_epoch_{epoch_index:03d}"
        glyph_heights = sorted(
            max(0.004, float(dict(row.get("geometry") or {}).get("height") or 0.0))
            for row in component
        )
        canonical_height = _linear_quantile(glyph_heights, 0.50)
        canonical_height = max(0.008, min(0.12, canonical_height))
        member_ids = sorted(str(row.get("text_id") or "") for row in component)
        starts, ends = zip(*(span(row) for row in component))
        epoch = {
            "schema_version": SOFT_COVER_EPOCH_POLICY_VERSION,
            "epoch_id": epoch_id,
            "member_text_ids": member_ids,
            "start_frame": min(starts),
            "end_frame": max(ends),
            "canonical_glyph_height_fraction": round(canonical_height, 8),
            "strategy": UNIFIED_EDITOR_COVER_STRATEGY,
            "mask_shape": "rounded_inward_feather",
            "reconstruction_order": [
                "temporal_clean_reference",
                "spatial_surface_reconstruction",
                "stable_soft_blur",
            ],
        }
        epochs.append(epoch)
        for row in component:
            policy = dict(row.get("render_policy") or {})
            context = dict(policy.get("context") or {})
            cover = dict(policy.get("cover") or {})
            context.update(
                {
                    "soft_cover_epoch_id": epoch_id,
                    "soft_cover_epoch_members": member_ids,
                    "soft_cover_style_locked": True,
                }
            )
            cover.update(
                {
                    "soft_cover_epoch_id": epoch_id,
                    "canonical_glyph_height_fraction": round(
                        canonical_height, 8
                    ),
                    "mask_shape": "rounded_inward_feather",
                    "reconstruction_order": list(epoch["reconstruction_order"]),
                }
            )
            policy["context"] = context
            policy["cover"] = cover
            row["render_policy"] = policy
    return rows, epochs


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
    fps = float(dict(contract.get("video") or {}).get("fps") or 30.0)
    caption_bridge_frames = max(
        6,
        min(36, int(round(max(1.0, fps) * CAPTION_COVER_MAX_BRIDGE_SECONDS))),
    )
    evidence_timed_cover_tracks = _seed_cover_intervals_from_evidence(
        enriched,
        fps=fps,
    )
    enriched, editor_card_panel_groups = _stabilize_editor_card_panels(
        enriched
    )
    # A card panel is the physical authority for its rows.  Caption-lane
    # stabilization must not later widen one member into a full lower-third,
    # otherwise the panel union is lost and a giant mask trips the damage gate.
    panel_rows = [
        row
        for row in enriched
        if str(
            dict(dict(row.get("render_policy") or {}).get("context") or {}).get(
                "editor_card_panel_id"
            )
            or ""
        )
    ]
    for row in panel_rows:
        panel_id = str(
            dict(dict(row.get("render_policy") or {}).get("context") or {}).get(
                "editor_card_panel_id"
            )
            or ""
        )
        panel_geometry = dict(row.get("editor_card_panel_geometry") or {})
        if not panel_id or not panel_geometry:
            continue
        policy = dict(row.get("render_policy") or {})
        context = dict(policy.get("context") or {})
        cover = dict(policy.get("cover") or {})
        layout = dict(policy.get("layout") or {})
        context.update({
            "editor_card_panel_cover": True,
            "caption_row": False,
            "effective_kind": "ui",
            "typography_kind": "ui",
        })
        cover.update({
            "roi": panel_geometry,
            "geometry_mode": "solid_editor_card_panel_union",
            "caption_cover_group_id": panel_id,
            "editor_card_panel_id": panel_id,
        })
        layout["safe_area"] = panel_geometry
        budget = dict(policy.get("damage_budget") or {})
        budget["max_frame_change_fraction"] = min(
            0.20,
            max(
                float(budget.get("max_frame_change_fraction") or 0.0),
                float(panel_geometry.get("width") or 0.0)
                * float(panel_geometry.get("height") or 0.0)
                * 1.02,
            ),
        )
        policy.update({"context": context, "cover": cover, "layout": layout, "damage_budget": budget})
        row["render_policy"] = policy
    (
        enriched,
        stable_caption_cover_groups,
        caption_transition_bridges,
        stacked_caption_sibling_extensions,
    ) = _stabilize_caption_cover_groups(
        enriched,
        max_bridge_frames=caption_bridge_frames,
    )
    enriched, soft_cover_epochs = _assign_soft_cover_epochs(
        enriched,
        fps=fps,
    )
    output["render_tracks"] = enriched
    output["soft_cover_epochs"] = soft_cover_epochs
    output["render_policy_version"] = RENDER_POLICY_VERSION
    counts = dict(output.get("counts") or {})
    counts["stable_caption_cover_groups"] = stable_caption_cover_groups
    counts["caption_cover_bridge_frames"] = caption_bridge_frames
    counts["caption_transition_bridges"] = caption_transition_bridges
    counts["evidence_timed_cover_tracks"] = evidence_timed_cover_tracks
    counts["stacked_caption_sibling_extensions"] = (
        stacked_caption_sibling_extensions
    )
    counts["editor_card_panel_groups"] = editor_card_panel_groups
    counts["soft_cover_epochs"] = len(soft_cover_epochs)
    output["counts"] = counts
    return output
