"""Policy-driven Phase 4 frame renderer with fail-closed QA diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import re

import numpy as np

from src.media_pipeline.video_renderer.adaptive_quality import (
    TemporalInpaintState,
    assess_mask_quality,
    evaluate_damage_budget,
)
from src.media_pipeline.video_renderer.adaptive_typography import (
    TextLayout,
    TypographyLayoutError,
    plan_dense_grid_layouts,
    plan_text_layout,
)
from src.media_pipeline.video_renderer.render_policy import (
    UNIFIED_EDITOR_COVER_POLICY_VERSION,
    UNIFIED_EDITOR_COVER_STRATEGY,
    UNIFIED_EDITOR_BLUR_PROFILE,
    select_text_render_tracks,
)
from src.media_pipeline.video_renderer.source_text_provenance import (
    is_editor_caption_track,
)
from src.media_pipeline.video_renderer.fonts import resolve_drawtext_font
from src.media_pipeline.video_renderer.overlays import OverlaySegment
from src.media_pipeline.video_renderer.render_runtime import blit_rgba_bgr

MaskBuilder = Callable[[np.ndarray, Mapping[str, Any]], np.ndarray]


class AdaptiveRenderBlocked(RuntimeError):
    """A frame failed a mask, damage, or typography safety gate."""

    def __init__(self, message: str, *, diagnostics: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


def _cover_component_identity(row: Mapping[str, Any]) -> str:
    policy = dict(row.get("render_policy") or {})
    cover = dict(policy.get("cover") or {})
    context = dict(policy.get("context") or {})
    if (
        str(cover.get("strategy") or "") != UNIFIED_EDITOR_COVER_STRATEGY
        or str(cover.get("mask_mode") or "") != "full_roi_plate"
    ):
        return ""
    return str(
        cover.get("caption_cover_group_id")
        or context.get("caption_cover_group_id")
        or cover.get("soft_cover_epoch_id")
        or context.get("soft_cover_epoch_id")
        or ""
    )


def _active_cover_components(
    tracks: Sequence[Mapping[str, Any]],
    *,
    preferred_text_ids: set[str] | None = None,
    canonical_rois: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Union overlapping soft-cover members before touching frame pixels.

    OCR content tracks can overlap at an editor-caption transition. Processing
    those rectangles sequentially creates a darker double plate and a visible
    pulse. This groups only spatially connected members of the same caption
    group/style epoch; unrelated labels in the same epoch stay independent.
    """

    rows = [dict(row) for row in tracks]
    preferred = set(preferred_text_ids or set())

    def roi(row: Mapping[str, Any]) -> dict[str, Any]:
        policy = dict(row.get("render_policy") or {})
        return dict(
            dict(policy.get("cover") or {}).get("roi")
            or row.get("geometry")
            or {}
        )

    def connected(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        if not _cover_component_identity(left) or _cover_component_identity(
            left
        ) != _cover_component_identity(right):
            return False
        a, b = roi(left), roi(right)
        ax0, ay0 = float(a.get("x") or 0.0), float(a.get("y") or 0.0)
        bx0, by0 = float(b.get("x") or 0.0), float(b.get("y") or 0.0)
        ax1 = ax0 + float(a.get("width") or 0.0)
        ay1 = ay0 + float(a.get("height") or 0.0)
        bx1 = bx0 + float(b.get("width") or 0.0)
        by1 = by0 + float(b.get("height") or 0.0)
        vertical = max(0.0, min(ay1, by1) - max(ay0, by0))
        min_height = min(max(0.0, ay1 - ay0), max(0.0, by1 - by0))
        horizontal_gap = max(0.0, bx0 - ax1, ax0 - bx1)
        return min_height > 0.0 and vertical / min_height >= 0.55 and horizontal_gap <= 0.018

    neighbors = {index: set() for index in range(len(rows))}
    for index, left in enumerate(rows):
        for other_index in range(index + 1, len(rows)):
            if connected(left, rows[other_index]):
                neighbors[index].add(other_index)
                neighbors[other_index].add(index)

    output: list[dict[str, Any]] = []
    visited: set[int] = set()
    for seed in range(len(rows)):
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
        members = [rows[index] for index in sorted(member_indices)]
        if len(members) == 1:
            single = dict(members[0])
            component_id = _cover_component_identity(single)
            canonical = dict((canonical_rois or {}).get(component_id) or {})
            if canonical:
                policy = dict(single.get("render_policy") or {})
                cover = dict(policy.get("cover") or {})
                budget = dict(policy.get("damage_budget") or {})
                stable_roi = dict(
                    cover.get("roi") or single.get("geometry") or {}
                )
                stable_roi["y"] = float(canonical["y"])
                stable_roi["height"] = float(canonical["height"])
                cover["roi"] = stable_roi
                cover["component_union"] = True
                budget["max_frame_change_fraction"] = min(
                    0.20,
                    max(
                        float(budget.get("max_frame_change_fraction") or 0.0),
                        float(stable_roi["width"])
                        * float(stable_roi["height"])
                        * 1.02,
                    ),
                )
                policy["cover"] = cover
                policy["damage_budget"] = budget
                single["geometry"] = dict(stable_roi)
                single["render_policy"] = policy
                single["_cover_component_member_ids"] = [
                    str(single.get("text_id") or "")
                ]
                single["_cover_component_id"] = component_id
            output.append(single)
            continue
        representative = next(
            (
                row
                for row in members
                if str(row.get("text_id") or "") in preferred
            ),
            members[0],
        )
        merged = dict(representative)
        member_rois = [roi(row) for row in members]
        x0 = min(float(item.get("x") or 0.0) for item in member_rois)
        y0 = min(float(item.get("y") or 0.0) for item in member_rois)
        x1 = max(
            float(item.get("x") or 0.0) + float(item.get("width") or 0.0)
            for item in member_rois
        )
        y1 = max(
            float(item.get("y") or 0.0) + float(item.get("height") or 0.0)
            for item in member_rois
        )
        union_roi = {
            "x": max(0.0, x0),
            "y": max(0.0, y0),
            "width": min(1.0, x1) - max(0.0, x0),
            "height": min(1.0, y1) - max(0.0, y0),
        }
        component_id = _cover_component_identity(merged)
        canonical = dict((canonical_rois or {}).get(component_id) or {})
        if canonical:
            # Keep content-bounded horizontal extent. A short caption must not
            # inherit the widest sentence in its epoch; only vertical plate
            # placement is canonical to remove transition flicker.
            union_roi["y"] = float(canonical["y"])
            union_roi["height"] = float(canonical["height"])
        policy = dict(merged.get("render_policy") or {})
        cover = dict(policy.get("cover") or {})
        budget = dict(policy.get("damage_budget") or {})
        cover["roi"] = union_roi
        cover["component_union"] = True
        budget["max_frame_change_fraction"] = min(
            0.20,
            max(
                float(budget.get("max_frame_change_fraction") or 0.0),
                union_roi["width"] * union_roi["height"] * 1.02,
            ),
        )
        policy["cover"] = cover
        policy["damage_budget"] = budget
        merged["geometry"] = dict(union_roi)
        merged["render_policy"] = policy
        merged["_cover_component_member_ids"] = [
            str(row.get("text_id") or "") for row in members
        ]
        merged["_cover_component_id"] = component_id
        output.append(merged)
    return output


def _soft_rounded_mask(
    mask: np.ndarray,
    *,
    glyph_height_px: int,
    profile: Mapping[str, Any] | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Create a rounded binary core and inward-feathered alpha authority.

    The alpha remains zero outside the approved mask, so protected pixels and
    damage budgets stay authoritative. Closing and a small elliptical opening
    remove one-pixel corners/seams while preserving complete glyph coverage.
    """

    import cv2

    settings = dict(UNIFIED_EDITOR_BLUR_PROFILE)
    settings.update(dict(profile or {}))
    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    height_px = max(1, int(glyph_height_px))
    round_radius = max(
        0,
        min(
            24,
            int(
                round(
                    height_px
                    * float(settings["rounded_corner_text_height_fraction"])
                )
            ),
        ),
    )
    rounded = binary.copy()
    # Inward-only opening rounds hard corners without changing any pixel
    # outside the approved damage mask. Closing here would silently expand the
    # affected area and violate source-protection/damage authority.
    if round_radius >= 2:
        opening_radius = max(1, round_radius)
        opening = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (opening_radius * 2 + 1, opening_radius * 2 + 1),
        )
        rounded = cv2.morphologyEx(rounded, cv2.MORPH_OPEN, opening)
    feather_px = max(
        1.0,
        height_px * float(settings["soft_edge_text_height_fraction"]),
    )
    distance = cv2.distanceTransform(rounded, cv2.DIST_L2, 5)
    alpha = np.clip(distance / feather_px, 0.0, 1.0).astype(np.float32)
    alpha[distance >= feather_px] = 1.0
    alpha *= (rounded > 0).astype(np.float32)
    return rounded, alpha, {
        "mask_shape": "rounded_inward_feather",
        "round_radius_px": int(round_radius),
        "feather_px": round(float(feather_px), 3),
    }


def _cover_aesthetic_metrics(
    before: np.ndarray,
    after: np.ndarray,
    mask: np.ndarray,
    *,
    previous_after: np.ndarray | None = None,
    previous_mask: np.ndarray | None = None,
) -> dict[str, float]:
    """Measure visible seams, frame-to-frame breathing and colour drift."""

    import cv2

    binary = mask > 0
    if not np.any(binary):
        return {
            "boundary_seam_score": 0.0,
            "temporal_flicker_score": 0.0,
            "background_color_drift": 0.0,
        }
    kernel = np.ones((3, 3), np.uint8)
    edge = cv2.morphologyEx(binary.astype(np.uint8), cv2.MORPH_GRADIENT, kernel) > 0
    inside_edge = edge & binary
    outside_edge = edge & (~binary)
    if np.any(inside_edge) and np.any(outside_edge):
        inside_colour = np.median(after[inside_edge], axis=0).astype(np.float32)
        outside_colour = np.median(after[outside_edge], axis=0).astype(np.float32)
        seam = float(np.mean(np.abs(inside_colour - outside_colour))) / 255.0
    else:
        seam = 0.0
    outside_ring = cv2.dilate(binary.astype(np.uint8), kernel, iterations=2) > 0
    outside_ring &= ~binary
    if np.any(outside_ring):
        core_colour = np.median(after[binary], axis=0).astype(np.float32)
        background_colour = np.median(after[outside_ring], axis=0).astype(
            np.float32
        )
        color_drift = float(
            np.mean(np.abs(core_colour - background_colour))
        ) / 255.0
    else:
        color_drift = 0.0
    flicker = 0.0
    if (
        previous_after is not None
        and previous_mask is not None
        and previous_after.shape == after.shape
        and previous_mask.shape == mask.shape
    ):
        shared = binary & (previous_mask > 0)
        if np.any(shared):
            # Compare low-frequency output so legitimate source motion does
            # not dominate the score.
            current_low = cv2.GaussianBlur(after, (0, 0), sigmaX=2.0)
            previous_low = cv2.GaussianBlur(previous_after, (0, 0), sigmaX=2.0)
            flicker = float(
                np.mean(
                    np.abs(
                        current_low[shared].astype(np.float32)
                        - previous_low[shared].astype(np.float32)
                    )
                )
            ) / 255.0
    return {
        "boundary_seam_score": round(seam, 6),
        "temporal_flicker_score": round(flicker, 6),
        "background_color_drift": round(color_drift, 6),
    }


def _uses_cover_aligned_layout(track: Mapping[str, Any]) -> bool:
    """Return whether cover ROI is the placement authority for this track.

    Editor captions are kept as a compatibility fallback for older persisted
    contracts.  Current contracts declare the mode explicitly for every
    editor-overlay role, including dense UI labels and titles.
    """

    layout = dict(dict(track.get("render_policy") or {}).get("layout") or {})
    return str(layout.get("mode") or "").strip() == "cover_aligned" or (
        is_editor_caption_track(track)
    )


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


def _smooth_surface_plate(frame_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Replace a bounded flat-surface overlay with a feathered planar plate."""

    import cv2

    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    if not np.any(binary):
        return frame_bgr.copy()
    height, width = binary.shape
    border = cv2.dilate(binary, np.ones((11, 11), np.uint8), iterations=1)
    border = (border > 0) & (binary == 0)
    ys, xs = np.where(border)
    if len(xs) < 16:
        return cv2.inpaint(frame_bgr.copy(), binary, 5, cv2.INPAINT_TELEA)
    design = np.column_stack(
        (
            np.ones(len(xs), dtype=np.float64),
            xs.astype(np.float64) / max(1, width - 1),
            ys.astype(np.float64) / max(1, height - 1),
        )
    )
    prediction_design = np.column_stack(
        (
            np.ones(height * width, dtype=np.float64),
            np.tile(np.arange(width), height).astype(np.float64) / max(1, width - 1),
            np.repeat(np.arange(height), width).astype(np.float64) / max(1, height - 1),
        )
    )
    plate = np.empty_like(frame_bgr, dtype=np.float64)
    for channel in range(3):
        values = frame_bgr[ys, xs, channel].astype(np.float64)
        coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
        plate[:, :, channel] = (
            prediction_design @ coefficients
        ).reshape(height, width)
    plate = np.clip(plate, 0, 255).astype(np.uint8)
    feather_radius = max(3, min(15, int(round(min(height, width) * 0.04))))
    alpha = cv2.GaussianBlur(binary, (0, 0), sigmaX=feather_radius / 2.0)
    alpha_f = (alpha.astype(np.float32) / 255.0)[:, :, None]
    output = (
        frame_bgr.astype(np.float32) * (1.0 - alpha_f)
        + plate.astype(np.float32) * alpha_f
    )
    return np.clip(output, 0, 255).astype(np.uint8)


def _editor_blur_plate(
    frame_bgr: np.ndarray,
    mask: np.ndarray,
    *,
    frame_height_px: int,
    profile: Mapping[str, Any] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Conceal an editor overlay with one resolution-aware blurred plate."""

    import cv2

    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    ys, xs = np.where(binary > 0)
    if len(xs) == 0:
        return frame_bgr.copy(), {
            "mode": UNIFIED_EDITOR_COVER_STRATEGY,
            "mask_pixels": 0,
        }
    settings = dict(UNIFIED_EDITOR_BLUR_PROFILE)
    settings.update(dict(profile or {}))
    measured_height = max(1, int(ys.max()) - int(ys.min()) + 1)
    text_height = max(
        1,
        int(round(float(settings.get("canonical_glyph_height_px") or measured_height))),
    )
    binary, alpha, soft_mask_qa = _soft_rounded_mask(
        binary,
        glyph_height_px=text_height,
        profile=settings,
    )
    ys, xs = np.where(binary > 0)
    if len(xs) == 0:
        return frame_bgr.copy(), {
            "status": "BLOCKED",
            "mode": UNIFIED_EDITOR_COVER_STRATEGY,
            "mask_pixels": 0,
            **soft_mask_qa,
        }
    sigma = float(text_height) * float(
        settings["sigma_text_height_fraction"]
    )
    sigma_min = max(
        1.0,
        float(frame_height_px) * float(settings["sigma_frame_min_fraction"]),
    )
    sigma_max = max(
        sigma_min,
        float(frame_height_px) * float(settings["sigma_frame_max_fraction"]),
    )
    sigma = max(sigma_min, min(sigma_max, sigma))
    # A tint toward the immediate surrounding background removes the
    # low-frequency colour ghost that Gaussian blur alone cannot erase.
    ring_radius = max(2, int(round(text_height * 0.18)))
    ring_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (ring_radius * 2 + 1, ring_radius * 2 + 1),
    )
    ring = (cv2.dilate(binary, ring_kernel) > 0) & (binary == 0)
    if int(np.count_nonzero(ring)) >= 16:
        background_bgr = np.median(frame_bgr[ring], axis=0).astype(np.float32)
    else:
        background_bgr = np.median(frame_bgr[binary > 0], axis=0).astype(
            np.float32
        )
    tint_alpha = max(0.0, min(0.60, float(settings["background_tint_alpha"])))

    feather_sigma = float(soft_mask_qa["feather_px"])
    core = alpha >= 0.999
    alpha_3 = alpha[:, :, None]

    def conceal(*, blur_sigma: float, tint: float) -> np.ndarray:
        blurred = cv2.GaussianBlur(
            frame_bgr,
            (0, 0),
            sigmaX=blur_sigma,
            sigmaY=blur_sigma,
            borderType=cv2.BORDER_REFLECT101,
        ).astype(np.float32)
        target = blurred * (1.0 - tint) + background_bgr * tint
        result = (
            frame_bgr.astype(np.float32) * (1.0 - alpha_3)
            + target * alpha_3
        )
        return np.clip(result, 0, 255).astype(np.uint8)

    def stroke_metrics(image: np.ndarray) -> tuple[float, float]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Laplacian energy measures readable high-frequency glyph strokes;
        # unlike first-order gradient magnitude it does not treat a broad,
        # already-unreadable colour transition as residual text.
        gradient = np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))
        selector = core if int(np.count_nonzero(core)) >= 16 else binary > 0
        if not np.any(selector):
            return 0.0, 0.0
        selected = gradient[selector]
        strong_fraction = float(
            np.mean(
                selected
                > float(settings.get("strong_stroke_threshold") or 12.0)
            )
        )
        return float(np.mean(selected)), strong_fraction

    source_energy, source_strong_fraction = stroke_metrics(frame_bgr)
    output = conceal(blur_sigma=sigma, tint=tint_alpha)
    output_energy, output_strong_fraction = stroke_metrics(output)
    residual_ratio = output_energy / max(1e-6, source_energy)
    max_ratio = float(settings["max_residual_stroke_ratio"])
    max_output_energy = float(settings.get("max_output_stroke_energy") or 0.0)
    max_flat_source_energy = float(
        settings.get("max_source_stroke_energy_for_absolute_pass") or 0.0
    )
    absolute_low_energy_pass = bool(
        max_output_energy > 0.0
        and max_flat_source_energy > 0.0
        and source_energy <= max_flat_source_energy
        and output_energy <= max_output_energy
    )
    initial_pass = (
        residual_ratio <= max_ratio
        or absolute_low_energy_pass
    )
    adaptive_retry = not initial_pass
    if adaptive_retry:
        retry_sigma_max = max(
            sigma_max,
            float(frame_height_px)
            * float(
                settings.get("retry_sigma_frame_max_fraction")
                or settings["sigma_frame_max_fraction"]
            ),
        )
        sigma = min(
            retry_sigma_max,
            sigma * float(settings["retry_sigma_multiplier"]),
        )
        tint_alpha = min(
            0.60,
            tint_alpha + float(settings["retry_tint_increment"]),
        )
        output = conceal(blur_sigma=sigma, tint=tint_alpha)
        output_energy, output_strong_fraction = stroke_metrics(output)
        residual_ratio = output_energy / max(1e-6, source_energy)
    absolute_low_energy_pass = bool(
        max_output_energy > 0.0
        and max_flat_source_energy > 0.0
        and source_energy <= max_flat_source_energy
        and output_energy <= max_output_energy
    )
    structural_low_energy_pass = bool(
        output_strong_fraction
        <= float(settings.get("max_output_strong_stroke_fraction") or 0.0)
        and residual_ratio
        <= float(settings.get("max_structural_residual_ratio") or max_ratio)
    )
    concealment_passed = (
        residual_ratio <= max_ratio
        or absolute_low_energy_pass
        or structural_low_energy_pass
    )
    return np.clip(output, 0, 255).astype(np.uint8), {
        "status": "PASS" if concealment_passed else "BLOCKED",
        "mode": UNIFIED_EDITOR_COVER_STRATEGY,
        "reference": "current_frame_low_frequency_blur",
        "sigma_px": round(sigma, 3),
        "feather_sigma_px": round(feather_sigma, 3),
        "background_tint_alpha": round(tint_alpha, 3),
        "source_stroke_energy": round(source_energy, 4),
        "output_stroke_energy": round(output_energy, 4),
        "residual_stroke_ratio": round(residual_ratio, 6),
        "source_strong_stroke_fraction": round(source_strong_fraction, 6),
        "output_strong_stroke_fraction": round(output_strong_fraction, 6),
        "max_output_strong_stroke_fraction": round(
            float(settings.get("max_output_strong_stroke_fraction") or 0.0),
            6,
        ),
        "structural_low_energy_pass": structural_low_energy_pass,
        "max_output_stroke_energy": round(max_output_energy, 4),
        "max_source_stroke_energy_for_absolute_pass": round(
            max_flat_source_energy, 4
        ),
        "absolute_low_energy_pass": absolute_low_energy_pass,
        "adaptive_retry": bool(adaptive_retry),
        "core_alpha": 1.0,
        "mask_pixels": int(len(xs)),
        "canonical_glyph_height_px": int(text_height),
        **soft_mask_qa,
    }


def _roi_pixels(
    roi: Mapping[str, Any], *, frame_width: int, frame_height: int
) -> tuple[int, int, int, int]:
    x0 = max(0, min(frame_width, int(round(float(roi.get("x") or 0.0) * frame_width))))
    y0 = max(0, min(frame_height, int(round(float(roi.get("y") or 0.0) * frame_height))))
    x1 = max(
        x0,
        min(
            frame_width,
            int(
                round(
                    (float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0))
                    * frame_width
                )
            ),
        ),
    )
    y1 = max(
        y0,
        min(
            frame_height,
            int(
                round(
                    (float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0))
                    * frame_height
                )
            ),
        ),
    )
    return x0, y0, x1, y1


def _default_mask_builder(frame_bgr: np.ndarray, track: Mapping[str, Any]) -> np.ndarray:
    import cv2

    from src.media_pipeline.video_renderer.inpaint_render import (
        build_ink_cover_mask,
        build_text_mask,
    )

    geometry = dict(track.get("geometry") or {})
    policy = dict(track.get("render_policy") or {})
    cover = dict(policy.get("cover") or {})
    roi = dict(cover.get("roi") or geometry)
    segment = OverlaySegment(
        start_ms=int(track.get("start_ms") or 0),
        end_ms=int(track.get("end_ms") or 0),
        x=float(geometry.get("x") or 0.0),
        y=float(geometry.get("y") or 0.0),
        width=float(geometry.get("width") or 0.0),
        height=float(geometry.get("height") or 0.0),
        text_vi="",
        kind=str(track.get("kind") or "ui"),
        authority_bounds=(
            float(roi.get("x") or 0.0),
            float(roi.get("y") or 0.0),
            float(roi.get("width") or 0.0),
            float(roi.get("height") or 0.0),
        ),
    )
    mask = build_ink_cover_mask(frame_bgr, [segment])
    if str(cover.get("mask_mode") or "") == "full_roi_plate":
        height, width = mask.shape[:2]
        x0, y0, x1, y1 = _roi_pixels(
            roi, frame_width=width, frame_height=height
        )
        mask = np.zeros_like(mask)
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = 255
    if str(cover.get("mask_mode") or "") in {
        "stylized_components",
        "editor_caption_stylized_components",
    }:
        stylized = build_text_mask(
            frame_bgr,
            [
                (
                    float(roi.get("x") or 0.0),
                    float(roi.get("y") or 0.0),
                    float(roi.get("width") or 0.0),
                    float(roi.get("height") or 0.0),
                )
            ],
        )
        mask = cv2.bitwise_or(mask, stylized)
    height, width = mask.shape[:2]
    geometry_height_px = float(geometry.get("height") or 0.0) * height
    default_fraction = (
        0.10
        if str(track.get("kind") or "") == "hardsub"
        else 0.04
    )
    dilate_fraction = float(
        cover.get("mask_dilate_radius_fraction") or default_fraction
    )
    intro_stylized_title = bool(
        dict(policy.get("context") or {}).get("intro_stylized_title")
        and str(cover.get("mask_mode") or "") == "stylized_components"
    )
    if intro_stylized_title:
        # Include thick colour fill, outline and glow.  The generic 10px cap
        # was designed for normal subtitle strokes and left the saturated
        # centre of large title glyphs untouched.
        dilate_radius = max(
            8,
            min(36, int(round(geometry_height_px * max(0.24, dilate_fraction)))),
        )
    else:
        dilate_radius = max(
            2, min(10, int(round(geometry_height_px * dilate_fraction)))
        )
    if int(mask.max()) > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (dilate_radius * 2 + 1, dilate_radius * 2 + 1),
        )
        mask = cv2.dilate(mask, kernel, iterations=1)
    x0, y0, x1, y1 = _roi_pixels(roi, frame_width=width, frame_height=height)
    clipped = np.zeros_like(mask)
    if x1 > x0 and y1 > y0:
        clipped[y0:y1, x0:x1] = mask[y0:y1, x0:x1]
    return clipped


class AdaptiveFrameRenderer:
    def __init__(
        self,
        *,
        fontfile: Path | str | None = None,
        mask_builder: MaskBuilder | None = None,
    ) -> None:
        self.fontfile = resolve_drawtext_font(fontfile)
        self.mask_builder = mask_builder or _default_mask_builder
        self.temporal = TemporalInpaintState()
        self._seeded_references: set[str] = set()
        self._reference_frames: dict[str, np.ndarray] = {}
        self._temporal_reference_seeded: set[str] = set()
        self._layout_cache: dict[tuple[Any, ...], TextLayout] = {}
        self._dense_cache: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        self._dense_slot_authority: dict[str, dict[str, int | str]] = {}
        self._mask_cache: dict[tuple[str, int, int, str, str], dict[str, Any]] = {}
        self._preseeded_masks: dict[str, np.ndarray] = {}
        self._epoch_style_cache: dict[str, dict[str, Any]] = {}
        self._epoch_reference_frames: dict[str, np.ndarray] = {}
        self._epoch_temporal_seeded: set[str] = set()
        self._epoch_temporal_reference_disabled: set[str] = set()
        self._epoch_last_output: dict[str, np.ndarray] = {}
        self._epoch_last_mask: dict[str, np.ndarray] = {}
        self._epoch_last_tint: dict[str, np.ndarray] = {}
        self._epoch_last_frame_index: dict[str, int] = {}
        self._dense_ui_panels: list[dict[str, Any]] = []
        self._dense_ui_panel_tracks: dict[str, list[dict[str, Any]]] = {}
        self._dense_ui_panel_plates: dict[str, np.ndarray] = {}
        self._cover_component_rois: dict[str, dict[str, float]] = {}

    def seed_cover_component_authority(
        self, tracks: Sequence[Mapping[str, Any]]
    ) -> None:
        """Lock bounded canonical ROIs for visually continuous cover epochs."""

        grouped: dict[str, list[dict[str, Any]]] = {}
        for raw in tracks:
            if not isinstance(raw, Mapping):
                continue
            row = dict(raw)
            component_id = _cover_component_identity(row)
            if not component_id:
                continue
            policy = dict(row.get("render_policy") or {})
            roi = dict(
                dict(policy.get("cover") or {}).get("roi")
                or row.get("geometry")
                or {}
            )
            if float(roi.get("width") or 0.0) <= 0.0 or float(
                roi.get("height") or 0.0
            ) <= 0.0:
                continue
            grouped.setdefault(component_id, []).append(roi)
        authority: dict[str, dict[str, float]] = {}
        for component_id, rois in grouped.items():
            if len(rois) < 2:
                continue
            x0 = min(float(roi.get("x") or 0.0) for roi in rois)
            y0 = min(float(roi.get("y") or 0.0) for roi in rois)
            x1 = max(
                float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0)
                for roi in rois
            )
            y1 = max(
                float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0)
                for roi in rois
            )
            # Epoch assignment already requires strong spatial overlap. These
            # caps are a final guard against a malformed group becoming a
            # full-frame plate.
            if y1 - y0 > 0.16 or x1 - x0 > 0.985:
                continue
            authority[component_id] = {
                "x": max(0.0, x0),
                "y": max(0.0, y0),
                "width": min(1.0, x1) - max(0.0, x0),
                "height": min(1.0, y1) - max(0.0, y0),
            }
        self._cover_component_rois = authority

    def seed_dense_ui_panels(
        self,
        panels: Sequence[Mapping[str, Any]],
        tracks: Sequence[Mapping[str, Any]],
        *,
        plate_colors: Mapping[str, Sequence[int]] | None = None,
    ) -> None:
        """Register approved panel epochs and stable, deduplicated source labels."""
        self._dense_ui_panels = [dict(row) for row in panels if isinstance(row, Mapping)]
        by_panel: dict[str, list[dict[str, Any]]] = {}
        colors = dict(plate_colors or {})
        for panel in self._dense_ui_panels:
            panel_id = str(panel.get("panel_id") or "")
            start = int(panel.get("start_frame") or 0)
            end = int(panel.get("end_frame") or start)
            roi = dict(panel.get("panel_roi") or {})
            candidates: list[dict[str, Any]] = []
            seen_content: set[str] = set()
            seen_text: set[str] = set()
            eligible: list[dict[str, Any]] = []
            for raw in tracks:
                if not isinstance(raw, Mapping):
                    continue
                track = dict(raw)
                if int(track.get("end_frame") or -1) < start or int(track.get("start_frame") or 0) > end:
                    continue
                text = str(track.get("text_vi") or "").strip()
                if not text:
                    continue
                geometry = dict(track.get("geometry") or {})
                tx0, ty0 = float(geometry.get("x") or 0.0), float(geometry.get("y") or 0.0)
                tx1, ty1 = tx0 + float(geometry.get("width") or 0.0), ty0 + float(geometry.get("height") or 0.0)
                candidate_pad = 0.03
                raw_px0, raw_py0 = float(roi.get("x") or 0.0), float(roi.get("y") or 0.0)
                raw_px1 = raw_px0 + float(roi.get("width") or 0.0)
                raw_py1 = raw_py0 + float(roi.get("height") or 0.0)
                px0, py0 = max(0.0, raw_px0 - candidate_pad), max(0.0, raw_py0 - candidate_pad)
                px1, py1 = min(1.0, raw_px1 + candidate_pad), min(1.0, raw_py1 + candidate_pad)
                overlap = max(0.0, min(tx1, px1) - max(tx0, px0)) * max(0.0, min(ty1, py1) - max(ty0, py0))
                if overlap <= 0.0:
                    continue
                eligible.append(track)
            eligible.sort(
                key=lambda row: (
                    -sum(char.isalpha() for char in str(row.get("text_vi") or "")),
                    -len(str(row.get("text_vi") or "").strip()),
                    int(row.get("start_frame") or 0),
                    str(row.get("text_id") or ""),
                )
            )
            for track in eligible:
                text = str(track.get("text_vi") or "").strip()
                content_id = str(track.get("content_id") or "").strip()
                normalized_text = re.sub(r"\s+", " ", text).casefold()
                key = f"content:{content_id}" if content_id else f"text:{normalized_text}"
                if (
                    (content_id and content_id in seen_content)
                    or normalized_text in seen_text
                ):
                    continue
                if content_id:
                    seen_content.add(content_id)
                seen_text.add(normalized_text)
                track["_panel_dedup_key"] = key
                candidates.append(track)
            def metric_key(value: str) -> str:
                return "|".join(
                    re.findall(
                        r"\d+(?:\.\d+)?|(?<!\w)(?:kcal|ml|mg|g)\b",
                        value.casefold(),
                    )
                )

            full_metric_keys = {
                metric_key(str(row.get("text_vi") or ""))
                for row in candidates
                if sum(char.isalpha() for char in str(row.get("text_vi") or "")) > 6
                and metric_key(str(row.get("text_vi") or ""))
            }
            candidates = [
                row
                for row in candidates
                if not (
                    sum(char.isalpha() for char in str(row.get("text_vi") or "")) <= 6
                    and metric_key(str(row.get("text_vi") or "")) in full_metric_keys
                )
            ]
            def priority(row: Mapping[str, Any]) -> tuple[int, int, str]:
                text = str(row.get("text_vi") or "")
                numeric = bool(re.search(r"\\d|kcal|g(?:ram)?\\b|ml\\b|mg\\b|%", text.casefold()))
                return (0 if numeric else 1, int(row.get("start_frame") or 0), text.casefold())
            by_panel[panel_id] = sorted(candidates, key=priority)[: int(panel.get("max_rendered_lines") or 12)]
            color = colors.get(panel_id)
            if color is not None and len(color) >= 3:
                self._dense_ui_panel_plates[panel_id] = np.asarray(list(color)[:3], dtype=np.uint8)
        self._dense_ui_panel_tracks = by_panel

    def _active_dense_panels(self, frame_index: int | None) -> list[dict[str, Any]]:
        if frame_index is None:
            return []
        return [
            panel for panel in self._dense_ui_panels
            if int(panel.get("start_frame") or 0) <= frame_index <= int(panel.get("end_frame") or -1)
        ]

    def seed_reference(self, text_id: str, clean_reference_bgr: np.ndarray) -> None:
        key = str(text_id or "").strip()
        if not key:
            raise AdaptiveRenderBlocked("Cannot seed a reference without text_id")
        self._reference_frames[key] = clean_reference_bgr.copy()
        self._seeded_references.add(key)

    def seed_epoch_reference(
        self, epoch_id: str, clean_reference_bgr: np.ndarray
    ) -> None:
        key = str(epoch_id or "").strip()
        if not key:
            raise AdaptiveRenderBlocked("Cannot seed an epoch reference without id")
        self._epoch_reference_frames[key] = clean_reference_bgr.copy()

    def seed_mask(self, text_id: str, representative_mask: np.ndarray) -> None:
        key = str(text_id or "").strip()
        mask = np.asarray(representative_mask)
        if not key or mask.ndim != 2 or mask.size == 0:
            raise AdaptiveRenderBlocked("Cannot seed an invalid representative mask")
        self._preseeded_masks[key] = np.where(mask > 0, 255, 0).astype(np.uint8)

    def seed_dense_layout_authority(
        self, tracks: Sequence[Mapping[str, Any]]
    ) -> None:
        """Assign source-faithful stable slots before frame rendering.

        The previous responsive grid keyed its cache by the active-track set,
        so a track appearing/disappearing reflowed every visible label.  Slots
        are assigned once from the full temporal contract.  Tracks stay on the
        same horizontal side as their source geometry and are considered in
        source vertical order.  Overlapping intervals receive different rows,
        while non-overlapping intervals can safely reuse a row.

        Preserving source side is important for editor-authored label groups.
        Alternating global slots between left and right makes a single source
        column look like unrelated labels scattered around the frame.
        """

        dense = [
            dict(track)
            for track in tracks
            if isinstance(track, Mapping)
            and str(track.get("text_id") or "")
            and str(track.get("text_vi") or "").strip()
            and bool(
                dict(
                    dict(track.get("render_policy") or {}).get("context") or {}
                ).get("dense_ui")
            )
        ]
        assignments: dict[str, dict[str, int | str]] = {}
        ordered = sorted(
            dense,
            key=lambda row: (
                int(row.get("start_frame") or 0),
                int(row.get("end_frame") or -1),
                str(row.get("text_id") or ""),
            ),
        )
        components: list[list[dict[str, Any]]] = []
        component_end = -2
        for track in ordered:
            start = int(track.get("start_frame") or 0)
            end = int(track.get("end_frame") or start)
            if not components or start > component_end + 1:
                components.append([])
                component_end = end
            else:
                component_end = max(component_end, end)
            components[-1].append(track)
        for component in components:
            by_source_side: dict[str, list[dict[str, Any]]] = {
                "left": [],
                "right": [],
            }
            for track in component:
                geometry = dict(track.get("geometry") or {})
                center_x = float(geometry.get("x") or 0.0) + (
                    float(geometry.get("width") or 0.0) * 0.5
                )
                side = "left" if center_x < 0.5 else "right"
                by_source_side[side].append(track)

            for side, side_tracks in by_source_side.items():
                slots: list[list[tuple[int, int]]] = []
                side_assignments: list[tuple[str, int]] = []
                source_ordered = sorted(
                    side_tracks,
                    key=lambda row: (
                        float(dict(row.get("geometry") or {}).get("y") or 0.0),
                        float(dict(row.get("geometry") or {}).get("x") or 0.0),
                        int(row.get("start_frame") or 0),
                        int(row.get("end_frame") or -1),
                        str(row.get("text_id") or ""),
                    ),
                )
                for track in source_ordered:
                    start = int(track.get("start_frame") or 0)
                    end = int(track.get("end_frame") or start)
                    slot_index = next(
                        (
                            index
                            for index, intervals in enumerate(slots)
                            if all(
                                end < previous_start or start > previous_end
                                for previous_start, previous_end in intervals
                            )
                        ),
                        len(slots),
                    )
                    if slot_index == len(slots):
                        slots.append([])
                    slots[slot_index].append((start, end))
                    side_assignments.append(
                        (str(track.get("text_id") or ""), slot_index)
                    )
                for text_id, slot_index in side_assignments:
                    assignments[text_id] = {
                        "side": side,
                        "slot_index": slot_index,
                        "slot_count": len(slots),
                    }
        self._dense_slot_authority = assignments

    @staticmethod
    def _policy(track: Mapping[str, Any]) -> dict[str, Any]:
        raw = track.get("render_policy")
        if not isinstance(raw, Mapping):
            raise AdaptiveRenderBlocked("Render track has no validated policy")
        return dict(raw)

    def _layout(
        self,
        track: Mapping[str, Any],
        *,
        frame_bgr: np.ndarray,
    ) -> TextLayout:
        policy = self._policy(track)
        layout_policy = dict(policy.get("layout") or {})
        cover = dict(policy.get("cover") or {})
        if _uses_cover_aligned_layout(track):
            declared_cover_aligned = (
                str(layout_policy.get("mode") or "").strip() == "cover_aligned"
            )
            layout_policy.update(
                {
                    "mode": "cover_aligned",
                    "safe_area": dict(
                        layout_policy.get("safe_area")
                        if declared_cover_aligned
                        else cover.get("roi")
                        or track.get("geometry")
                        or {}
                    ),
                    "anchor": "center_bottom",
                }
            )
        height, width = frame_bgr.shape[:2]
        cache_key = (
            str(track.get("text_id") or ""),
            str(track.get("text_vi") or ""),
            width,
            height,
            str(self.fontfile),
            policy.get("policy_version"),
        )
        hit = self._layout_cache.get(cache_key)
        if hit is not None:
            return hit
        try:
            planned = plan_text_layout(
                str(track.get("text_vi") or ""),
                kind=str(
                    dict(policy.get("context") or {}).get("typography_kind")
                    or dict(policy.get("context") or {}).get("effective_kind")
                    or track.get("kind")
                    or "ui"
                ),
                safe_area=dict(layout_policy.get("safe_area") or {}),
                frame_width=width,
                frame_height=height,
                fontfile=self.fontfile,
                background_bgr=frame_bgr,
                max_lines=int(layout_policy.get("max_lines") or 1),
            )
        except TypographyLayoutError as exc:
            raise AdaptiveRenderBlocked(
                f"Typography blocked for {track.get('text_id')}: {exc}"
            ) from exc
        self._layout_cache[cache_key] = planned
        return planned

    def _track_mask(
        self, frame_bgr: np.ndarray, track: Mapping[str, Any]
    ) -> tuple[np.ndarray, str]:
        height, width = frame_bgr.shape[:2]
        policy = self._policy(track)
        cover = dict(policy.get("cover") or {})
        cover_geometry = dict(cover.get("roi") or track.get("geometry") or {})
        cover_signature = ":".join(
            f"{float(cover_geometry.get(name) or 0.0):.6f}"
            for name in ("x", "y", "width", "height")
        )
        key = (
            str(track.get("text_id") or ""),
            width,
            height,
            str(policy.get("policy_version") or ""),
            cover_signature,
        )
        if (
            str(cover.get("strategy") or "") == UNIFIED_EDITOR_COVER_STRATEGY
            and str(cover.get("mask_mode") or "") == "full_roi_plate"
            and self.mask_builder is _default_mask_builder
        ):
            entry = self._mask_cache.get(key)
            if entry is None:
                mask = np.zeros((height, width), dtype=np.uint8)
                x0, y0, x1, y1 = _roi_pixels(
                    dict(cover.get("roi") or track.get("geometry") or {}),
                    frame_width=width,
                    frame_height=height,
                )
                if x1 > x0 and y1 > y0:
                    mask[y0:y1, x0:x1] = 255
                self._mask_cache[key] = {"mask": mask, "samples": 1, "cacheable": True}
                return mask.copy(), "policy_full_roi_plate"
            return np.asarray(entry["mask"]).copy(), "policy_full_roi_plate_cache"
        entry = self._mask_cache.get(key)
        if entry is None:
            observed = self.mask_builder(frame_bgr, track)
            mask = observed
            source = "track_sampling"
            cacheable = True
            preseeded = self._preseeded_masks.get(str(track.get("text_id") or ""))
            if preseeded is not None:
                if preseeded.shape != mask.shape:
                    raise AdaptiveRenderBlocked("Representative mask shape mismatch")
                import cv2

                combined = cv2.bitwise_or(mask, preseeded)
                if self._dense_union_should_use_current(
                    combined=combined,
                    observed=observed,
                    track=track,
                ):
                    source = "track_sampling_dense_preseed_rejected"
                    cacheable = False
                else:
                    mask = combined
                    source = "preseed_plus_sampling"
            self._mask_cache[key] = {
                "mask": mask.copy(),
                "samples": 1,
                "cacheable": cacheable,
            }
            return mask, source
        if not bool(entry.get("cacheable", True)):
            observed = self.mask_builder(frame_bgr, track)
            entry["mask"] = observed.copy()
            entry["samples"] = int(entry.get("samples") or 0) + 1
            return observed, "track_sampling_dynamic"
        if int(entry.get("samples") or 0) < 3:
            import cv2

            observed = self.mask_builder(frame_bgr, track)
            combined = cv2.bitwise_or(np.asarray(entry["mask"]), observed)
            if self._dense_union_should_use_current(
                combined=combined,
                observed=observed,
                track=track,
            ):
                entry["mask"] = observed.copy()
                entry["samples"] = int(entry.get("samples") or 0) + 1
                entry["cacheable"] = False
                return observed, "track_sampling_dense_union_rejected"
            entry["mask"] = combined.copy()
            entry["samples"] = int(entry.get("samples") or 0) + 1
            return combined, "track_sampling"
        return np.asarray(entry["mask"]).copy(), "track_cache"

    def track_cover_mask(
        self, frame_bgr: np.ndarray, track: Mapping[str, Any]
    ) -> np.ndarray:
        """Expose the exact runtime cover mask to preflight diagnostics."""

        mask, _source = self._track_mask(frame_bgr, track)
        return mask

    @staticmethod
    def _dense_union_should_use_current(
        *,
        combined: np.ndarray,
        observed: np.ndarray,
        track: Mapping[str, Any],
    ) -> bool:
        """Keep a safe per-frame ink mask when representative unions become solid."""

        height, width = observed.shape[:2]
        policy = dict(track.get("render_policy") or {})
        cover_roi = dict(dict(policy.get("cover") or {}).get("roi") or {})
        roi_px = _roi_pixels(
            cover_roi,
            frame_width=width,
            frame_height=height,
        )
        max_fraction = float(
            dict(policy.get("damage_budget") or {}).get(
                "max_frame_change_fraction"
            )
            or 0.0
        )
        max_roi_fill_fraction = float(
            dict(policy.get("damage_budget") or {}).get(
                "max_ink_roi_fill_fraction"
            )
            or 0.80
        )
        combined_qa = assess_mask_quality(
            combined,
            cover_roi_px=roi_px,
            max_frame_change_fraction=max_fraction,
            max_roi_fill_fraction=max_roi_fill_fraction,
        )
        if list(combined_qa.get("blocked_reasons") or []) != [
            "mask_too_dense_for_ink"
        ]:
            return False
        observed_qa = assess_mask_quality(
            observed,
            cover_roi_px=roi_px,
            max_frame_change_fraction=max_fraction,
            max_roi_fill_fraction=max_roi_fill_fraction,
        )
        return str(observed_qa.get("status") or "") == "PASS"

    @staticmethod
    def _track_is_inside_panel(
        track: Mapping[str, Any], panel: Mapping[str, Any]
    ) -> bool:
        policy = dict(track.get("render_policy") or {})
        rectangle = dict(
            dict(policy.get("cover") or {}).get("roi")
            or track.get("geometry")
            or {}
        )
        roi = dict(panel.get("panel_roi") or {})
        x0, y0 = float(rectangle.get("x") or 0.0), float(rectangle.get("y") or 0.0)
        width, height = float(rectangle.get("width") or 0.0), float(rectangle.get("height") or 0.0)
        px0, py0 = float(roi.get("x") or 0.0), float(roi.get("y") or 0.0)
        px1 = px0 + float(roi.get("width") or 0.0)
        py1 = py0 + float(roi.get("height") or 0.0)
        area = width * height
        overlap = max(0.0, min(x0 + width, px1) - max(x0, px0)) * max(
            0.0, min(y0 + height, py1) - max(y0, py0)
        )
        return area > 0.0 and overlap / area >= 0.5

    def _cover_dense_panel(
        self,
        output: np.ndarray,
        panel: Mapping[str, Any],
        *,
        frame_index: int | None,
    ) -> dict[str, Any]:
        height, width = output.shape[:2]
        panel_id = str(panel.get("panel_id") or "")
        roi = dict(panel.get("panel_roi") or {})
        x0, y0, x1, y1 = _roi_pixels(roi, frame_width=width, frame_height=height)
        if not panel_id or x1 <= x0 or y1 <= y0:
            raise AdaptiveRenderBlocked("Dense UI panel has invalid geometry")
        release_frames = max(0, int(panel.get("temporal_exit_release_frames") or 0))
        end_frame = int(panel.get("end_frame") or -1)
        if (
            frame_index is not None
            and release_frames > 0
            and end_frame - int(panel.get("start_frame") or 0) + 1 > release_frames * 2
            and frame_index > end_frame - release_frames
        ):
            return {
                "panel_id": panel_id,
                "panel_roi": roi,
                "plate_bgr": None,
                "changed_fraction": 0.0,
                "max_frame_change_fraction": float(
                    panel.get("max_frame_change_fraction") or 0.0
                ),
                "status": "PASS",
                "temporal_exit_release": True,
                "layouts": [],
            }
        plate = self._dense_ui_panel_plates.get(panel_id)
        if plate is None:
            plate = np.median(output[y0:y1, x0:x1], axis=(0, 1)).round().astype(np.uint8)
            self._dense_ui_panel_plates[panel_id] = plate
        before = output.copy()
        source_crop = output[y0:y1, x0:x1].copy()
        panel_mask = np.full(source_crop.shape[:2], 255, dtype=np.uint8)
        source_aware_plate, blur_qa = _editor_blur_plate(
            source_crop,
            panel_mask,
            frame_height_px=height,
        )
        output[y0:y1, x0:x1] = source_aware_plate
        mask = np.zeros((height, width), dtype=np.uint8)
        mask[y0:y1, x0:x1] = 255
        budget = float(panel.get("max_frame_change_fraction") or 0.0)
        if budget <= 0.0:
            budget = max(
                [
                    float(
                        dict(dict(row.get("render_policy") or {}).get("damage_budget") or {}).get(
                            "max_frame_change_fraction"
                        )
                        or 0.0
                    )
                    for row in self._dense_ui_panel_tracks.get(panel_id, [])
                ]
                or [0.0]
            )
        changed_fraction = float(np.count_nonzero(np.any(before != output, axis=2))) / float(height * width)
        if budget <= 0.0 or changed_fraction > budget + 1e-9:
            raise AdaptiveRenderBlocked(
                f"Dense UI panel exceeds damage budget: {panel_id}",
                diagnostics={"dense_ui_panels": [{"panel_id": panel_id, "changed_fraction": changed_fraction, "budget": budget}]},
            )
        return {
            "panel_id": panel_id,
            "panel_roi": roi,
            "plate_bgr": [int(value) for value in plate],
            "plate_mode": UNIFIED_EDITOR_COVER_STRATEGY,
            "blur": blur_qa,
            "changed_fraction": changed_fraction,
            "max_frame_change_fraction": budget,
            "status": "PASS",
            "layouts": [],
        }

    def _render_dense_panel_text(
        self,
        output: np.ndarray,
        panel: Mapping[str, Any],
        diagnostic: dict[str, Any],
    ) -> None:
        panel_id = str(panel.get("panel_id") or "")
        tracks = self._dense_ui_panel_tracks.get(panel_id, [])
        if not tracks:
            return
        roi = dict(panel.get("panel_roi") or {})
        height, width = output.shape[:2]
        items = []
        for track in tracks:
            items.append(
                {
                    "text_id": track.get("text_id"),
                    "content_id": track.get("content_id"),
                    "text": track.get("text_vi"),
                }
            )
        cache_key = (
            "panel",
            panel_id,
            tuple(str(item.get("text_id") or "") for item in items),
            width,
            height,
            str(self.fontfile),
        )
        layouts = self._dense_cache.get(cache_key)
        if layouts is None:
            layouts = []
            row_count = max(1, len(items))
            pad_x = min(0.012, float(roi.get("width") or 0.0) * 0.04)
            pad_y = min(0.006, float(roi.get("height") or 0.0) / (row_count * 8.0))
            row_height = float(roi.get("height") or 0.0) / row_count
            for index, item in enumerate(items):
                cell = {
                    "x": float(roi.get("x") or 0.0) + pad_x,
                    "y": float(roi.get("y") or 0.0) + index * row_height + pad_y,
                    "width": max(0.01, float(roi.get("width") or 0.0) - 2 * pad_x),
                    "height": max(0.01, row_height - 2 * pad_y),
                }
                try:
                    layout = plan_text_layout(
                        str(item.get("text") or ""),
                        kind="ui",
                        safe_area=cell,
                        frame_width=width,
                        frame_height=height,
                        fontfile=self.fontfile,
                        background_bgr=output,
                        max_lines=2,
                    )
                except TypographyLayoutError as exc:
                    raise AdaptiveRenderBlocked(
                        f"Dense UI panel typography blocked for {item.get('text_id')}: {exc}",
                        diagnostics={"dense_ui_panels": [diagnostic]},
                    ) from exc
                layouts.append({**item, "layout": layout, "placement_mode": "panel_single_column"})
            self._dense_cache[cache_key] = layouts
        for item in layouts:
            layout = item["layout"]
            blit_rgba_bgr(output, layout.rgba, x0=layout.x0, y0=layout.y0)
            diagnostic["layouts"].append(
                {
                    "text_id": item.get("text_id"),
                    "content_id": item.get("content_id"),
                    "text": item.get("text"),
                    "x0": layout.x0,
                    "y0": layout.y0,
                    "width": layout.width,
                    "height": layout.height,
                    "placement_mode": item.get("placement_mode"),
                }
            )

    def render_frame(
        self,
        frame_bgr: np.ndarray,
        active_tracks: Sequence[Mapping[str, Any]],
        *,
        frame_index: int | None = None,
        protected_source_regions: Sequence[Mapping[str, Any]] = (),
    ) -> tuple[np.ndarray, dict[str, Any]]:
        if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
            raise AdaptiveRenderBlocked("Frame must be HxWx3 BGR")
        active_panels = self._active_dense_panels(frame_index)
        if not active_tracks and not active_panels:
            return frame_bgr, {"status": "PASS", "tracks": [], "layout_mode": "idle"}
        output = frame_bgr.copy()
        frame_base_mode = "source_frame"
        for raw in active_tracks:
            track = dict(raw)
            context = dict(
                dict(track.get("render_policy") or {}).get("context") or {}
            )
            text_id = str(track.get("text_id") or "")
            reference = self._reference_frames.get(text_id)
            if (
                bool(context.get("short_intro_full_frame_clean_plate_approved"))
                and reference is not None
                and reference.shape == output.shape
            ):
                output = reference.copy()
                frame_base_mode = "operator_approved_short_intro_clean_frame"
                break
        height, width = output.shape[:2]
        diagnostics: list[dict[str, Any]] = []
        # Multiple OCR tracks can overlap during a transition.  Keep a
        # per-frame concealment union so an exactly covered ROI is not blurred
        # again.  Partially overlapping rectangles still use their full mask:
        # cutting out the prior region creates a thin seam whose boundary
        # energy is larger than the text it is meant to conceal.
        concealed_mask = np.zeros((height, width), dtype=np.uint8)
        panel_diagnostics = [
            self._cover_dense_panel(output, panel, frame_index=frame_index)
            for panel in active_panels
        ]
        tracks = [
            dict(track)
            for track in active_tracks
            if not any(self._track_is_inside_panel(track, panel) for panel in active_panels)
        ]
        for raw in active_tracks:
            track = dict(raw)
            panel = next(
                (row for row in active_panels if self._track_is_inside_panel(track, row)),
                None,
            )
            if panel is not None:
                diagnostics.append(
                    {
                        "text_id": track.get("text_id"),
                        "content_id": track.get("content_id"),
                        "status": "PASS",
                        "cover_suppressed_by_panel": str(panel.get("panel_id") or ""),
                        "text_render_suppressed": "dense_ui_panel",
                    }
                )
        panel_content_ids = {
            str(row.get("content_id") or "").strip()
            for panel in active_panels
            for row in self._dense_ui_panel_tracks.get(str(panel.get("panel_id") or ""), [])
            if str(row.get("content_id") or "").strip()
        }
        panel_texts = {
            re.sub(r"\s+", " ", str(row.get("text_vi") or "").strip()).casefold()
            for panel in active_panels
            for row in self._dense_ui_panel_tracks.get(str(panel.get("panel_id") or ""), [])
            if str(row.get("text_vi") or "").strip()
        }
        panel_metric_keys = {
            "|".join(
                re.findall(
                    r"\d+(?:\.\d+)?|(?<!\w)(?:kcal|ml|mg|g)\b",
                    str(row.get("text_vi") or "").casefold(),
                )
            )
            for panel in active_panels
            for row in self._dense_ui_panel_tracks.get(str(panel.get("panel_id") or ""), [])
            if str(row.get("text_vi") or "").strip()
            and sum(char.isalpha() for char in str(row.get("text_vi") or "")) > 6
        }
        selected_text_tracks = select_text_render_tracks(tracks)
        panel_suppressed_ids = {
            str(track.get("text_id") or "")
            for track in selected_text_tracks
            if (
                str(track.get("content_id") or "").strip() in panel_content_ids
                or re.sub(r"\s+", " ", str(track.get("text_vi") or "").strip()).casefold()
                in panel_texts
                or (
                    sum(char.isalpha() for char in str(track.get("text_vi") or "")) <= 6
                    and "|".join(
                        re.findall(
                            r"\d+(?:\.\d+)?|(?<!\w)(?:kcal|ml|mg|g)\b",
                            str(track.get("text_vi") or "").casefold(),
                        )
                    )
                    in panel_metric_keys
                )
            )
        }
        text_tracks = [
            track
            for track in selected_text_tracks
            if str(track.get("text_id") or "") not in panel_suppressed_ids
        ]
        protected_text_conflict_ids = {
            str(track.get("text_id") or "")
            for track in text_tracks
            if any(
                _geometry_overlap_over_smaller(
                    dict(track.get("geometry") or {}),
                    dict(protected.get("geometry") or {}),
                )
                >= 0.50
                for protected in protected_source_regions
            )
        }
        text_tracks = [
            track
            for track in text_tracks
            if str(track.get("text_id") or "")
            not in protected_text_conflict_ids
        ]
        text_track_ids = {str(track.get("text_id") or "") for track in text_tracks}
        cover_tracks = _active_cover_components(
            tracks,
            preferred_text_ids=text_track_ids,
            canonical_rois=self._cover_component_rois,
        )
        for track in cover_tracks:
            policy = self._policy(track)
            cover = dict(policy.get("cover") or {})
            cover_roi = dict(cover.get("roi") or {})
            budget = dict(policy.get("damage_budget") or {})
            mask, mask_source = self._track_mask(output, track)
            roi_px = _roi_pixels(cover_roi, frame_width=width, frame_height=height)
            context = dict(policy.get("context") or {})
            unified_editor_cover = str(
                cover.get("consistency_policy") or ""
            ) == UNIFIED_EDITOR_COVER_POLICY_VERSION
            editor_caption_stylized_mask = (
                str(cover.get("mask_mode") or "")
                == "editor_caption_stylized_components"
                and bool(context.get("editor_caption_residual_remediation"))
            )
            intro_stylized_title_mask = bool(
                context.get("intro_stylized_title")
                and str(cover.get("mask_mode") or "")
                == "stylized_components"
            )
            full_roi_plate = str(cover.get("mask_mode") or "") == "full_roi_plate"
            protected_mask_pixels = 0
            mask_pixels_before_protection = int(np.count_nonzero(mask))
            if unified_editor_cover and full_roi_plate and protected_source_regions:
                for protected in protected_source_regions:
                    provenance = dict(protected.get("visual_provenance") or {})
                    if (
                        str(provenance.get("classification") or "")
                        != "SOURCE_INTRINSIC"
                        or float(provenance.get("confidence") or 0.0) < 0.90
                    ):
                        continue
                    protected_geometry = dict(protected.get("geometry") or {})
                    px0, py0, px1, py1 = _roi_pixels(
                        protected_geometry,
                        frame_width=width,
                        frame_height=height,
                    )
                    if px1 <= px0 or py1 <= py0:
                        continue
                    before = int(np.count_nonzero(mask[py0:py1, px0:px1]))
                    if before:
                        mask[py0:py1, px0:px1] = 0
                        protected_mask_pixels += before
                if protected_mask_pixels:
                    # Preserve carve-out holes through rounded-mask closing;
                    # reconstruction must never refill protected source text.
                    cover["preserve_mask_holes"] = True
            span_frames = max(
                1,
                int(track.get("end_frame") or 0)
                - int(track.get("start_frame") or 0)
                + 1,
            )
            dense_fallback = False
            micro_ui_fallback = False
            if int(np.count_nonzero(mask)) == 0 and bool(context.get("dense_ui")):
                x0, y0, x1, y1 = roi_px
                if x1 > x0 and y1 > y0:
                    mask = np.zeros(output.shape[:2], dtype=np.uint8)
                    mask[y0:y1, x0:x1] = 255
                    dense_fallback = True
            elif int(np.count_nonzero(mask)) == 0 and bool(
                context.get("micro_ui")
            ):
                x0, y0, x1, y1 = roi_px
                roi_fraction = (
                    max(0, x1 - x0) * max(0, y1 - y0) / float(width * height)
                )
                if (
                    x1 > x0
                    and y1 > y0
                    and span_frames <= 6
                    and roi_fraction <= 0.005
                ):
                    mask = np.zeros(output.shape[:2], dtype=np.uint8)
                    mask[y0:y1, x0:x1] = 255
                    micro_ui_fallback = True
            text_id = str(track.get("text_id") or "")
            output_residual_template = (
                str(
                    dict(track.get("output_residual_coverage") or {}).get("status")
                    or ""
                )
                in {
                    "OPERATOR_APPROVED_SOURCE_BOUNDARY_VERIFIED",
                    "OPERATOR_APPROVED_SOURCE_TEMPLATE_VERIFIED",
                    "OPERATOR_APPROVED_SOURCE_TEMPLATE_TRACKING",
                }
            )
            reference_fallback = (
                str(cover.get("mask_mode") or "") == "stylized_components"
                and text_id in self._seeded_references
                and not output_residual_template
            )
            intro_overlay_spatial_fallback = (
                not unified_editor_cover
                and str(cover.get("mask_mode") or "")
                in {"stylized_components", "full_roi_plate"}
                and int(track.get("start_frame") or 0) <= 1
                and span_frames <= 6
                and not reference_fallback
                and str(context.get("effective_kind") or track.get("kind") or "")
                == "title"
            )
            caption_panel_fallback = (
                bool(context.get("caption_row"))
                and str(cover.get("mask_mode") or "") == "ink_components"
            )
            x0, y0, x1, y1 = roi_px
            roi_fraction = (
                max(0, x1 - x0) * max(0, y1 - y0) / float(width * height)
            )
            bounded_output_micro_ui = (
                bool(context.get("output_residual_micro_ui_reference"))
                and bool(context.get("micro_ui"))
                and roi_fraction <= 0.005
            )
            bounded_output_dense_mask = (
                bool(context.get("output_residual_bounded_dense_mask"))
                and bool(context.get("micro_ui"))
                and roi_fraction <= 0.03
                and roi_fraction
                <= float(budget.get("max_frame_change_fraction") or 0.0)
            )
            if reference_fallback:
                x0, y0, x1, y1 = roi_px
                if x1 > x0 and y1 > y0:
                    mask = np.zeros(output.shape[:2], dtype=np.uint8)
                    mask[y0:y1, x0:x1] = 255
                    dense_fallback = False
            if intro_overlay_spatial_fallback:
                x0, y0, x1, y1 = roi_px
                if x1 > x0 and y1 > y0:
                    mask = np.zeros(output.shape[:2], dtype=np.uint8)
                    mask[y0:y1, x0:x1] = 255
            mask_qa = assess_mask_quality(
                mask,
                cover_roi_px=roi_px,
                max_frame_change_fraction=float(
                    budget.get("max_frame_change_fraction") or 0.0
                ),
                max_roi_fill_fraction=float(
                    budget.get("max_ink_roi_fill_fraction") or 0.80
                ),
                allow_dense_roi=(
                    dense_fallback
                    or micro_ui_fallback
                    or reference_fallback
                    or intro_overlay_spatial_fallback
                    or caption_panel_fallback
                    or bounded_output_micro_ui
                    or bounded_output_dense_mask
                    or editor_caption_stylized_mask
                    or intro_stylized_title_mask
                    or full_roi_plate
                ),
            )
            dense_mask = float(dict(mask_qa.get("metrics") or {}).get("roi_fill_fraction") or 0.0) > 0.80
            mask_qa["fallback"] = (
                "tight_roi"
                if dense_fallback
                else "micro_ui_tight_roi"
                if micro_ui_fallback
                else "reference_plate"
                if reference_fallback and dense_mask
                else "spatial_intro_overlay"
                if intro_overlay_spatial_fallback and dense_mask
                else "caption_panel"
                if caption_panel_fallback and dense_mask
                else "bounded_output_micro_ui_dense_roi"
                if bounded_output_micro_ui and dense_mask
                else "bounded_output_residual_dense_roi"
                if bounded_output_dense_mask and dense_mask
                else "editor_caption_stylized_mask"
                if editor_caption_stylized_mask and dense_mask
                else "intro_stylized_title_mask"
                if intro_stylized_title_mask and dense_mask
                else "full_roi_plate"
                if full_roi_plate and dense_mask
                else None
            )
            mask_qa["source"] = mask_source
            if protected_mask_pixels:
                mask_qa["protected_source_carve_pixels"] = protected_mask_pixels
                mask_qa["mask_pixels_before_source_protection"] = (
                    mask_pixels_before_protection
                )
            track_qa: dict[str, Any] = {
                "text_id": track.get("text_id"),
                "content_id": track.get("content_id"),
                "cover_roi": cover_roi,
                "mask": mask_qa,
            }
            component_members = list(track.get("_cover_component_member_ids") or [])
            if component_members:
                track_qa["cover_component"] = {
                    "component_id": str(track.get("_cover_component_id") or ""),
                    "member_text_ids": component_members,
                    "processed_once": True,
                }
            if (
                mask_pixels_before_protection > 0
                and protected_mask_pixels >= mask_pixels_before_protection
                and int(np.count_nonzero(mask)) == 0
            ):
                # Provenance authority has higher precedence than a cover
                # proposal. A local detector can legitimately propose a tiny
                # editor track over jewelry, printed packaging, phone UI, or
                # another high-confidence SOURCE_INTRINSIC region. If the
                # protected source union consumes the entire proposed plate,
                # processing it is a safe no-op, not a renderer failure. Do
                # not refill the ROI and do not mark it concealed: both would
                # damage source content and make false detections visible as
                # blur flashes.
                mask_qa["status"] = "PASS"
                mask_qa["blocked_reasons"] = []
                mask_qa["source_authority_precedence"] = (
                    "fully_protected_source_intrinsic"
                )
                track_qa["temporal"] = {
                    "status": "PASS",
                    "mode": "protected_source_noop",
                    "reference": "source_intrinsic_authority",
                }
                track_qa["damage"] = {
                    "status": "PASS",
                    "blocked_reasons": [],
                    "metrics": {
                        "changed_fraction": 0.0,
                        "outside_mask_mean_abs_delta": 0.0,
                        "outside_mask_ssim": 1.0,
                    },
                }
                track_qa["status"] = "PASS"
                diagnostics.append(track_qa)
                continue
            if mask_qa["status"] != "PASS":
                track_qa["status"] = "BLOCKED"
                raise AdaptiveRenderBlocked(
                    f"Mask quality blocked for {track.get('text_id')}",
                    diagnostics={"tracks": diagnostics + [track_qa]},
                )
            effective_mask = mask
            prior_overlap_fraction = 0.0
            if unified_editor_cover and full_roi_plate:
                mask_pixels = int(np.count_nonzero(mask))
                if mask_pixels > 0:
                    prior_pixels = int(
                        np.count_nonzero(
                            np.bitwise_and(mask, concealed_mask)
                        )
                    )
                    prior_overlap_fraction = prior_pixels / float(mask_pixels)
                    if prior_overlap_fraction >= 0.999:
                        effective_mask = np.zeros_like(mask)
                    mask_qa["prior_overlap_fraction"] = round(
                        prior_overlap_fraction, 6
                    )
                    mask_qa["effective_mask_pixels"] = int(
                        np.count_nonzero(effective_mask)
                    )
            if int(np.count_nonzero(effective_mask)) == 0:
                track_qa["temporal"] = {
                    "status": "PASS",
                    "mode": "covered_by_prior_track",
                    "reference": "frame_concealment_union",
                    "prior_overlap_fraction": round(
                        prior_overlap_fraction, 6
                    ),
                }
                track_qa["damage"] = {
                    "status": "PASS",
                    "blocked_reasons": [],
                    "metrics": {
                        "changed_fraction": 0.0,
                        "outside_mask_mean_abs_delta": 0.0,
                        "outside_mask_ssim": 1.0,
                    },
                }
                track_qa["status"] = "PASS"
                diagnostics.append(track_qa)
                concealed_mask = np.maximum(concealed_mask, mask)
                continue
            x0, y0, x1, y1 = roi_px
            if x1 <= x0 or y1 <= y0:
                raise AdaptiveRenderBlocked(f"Empty cover ROI for {text_id}")
            temporal_pad = max(8, int(round(max(x1 - x0, y1 - y0) * 0.15)))
            tx0 = max(0, x0 - temporal_pad)
            ty0 = max(0, y0 - temporal_pad)
            tx1 = min(width, x1 + temporal_pad)
            ty1 = min(height, y1 + temporal_pad)
            source_roi = output[ty0:ty1, tx0:tx1].copy()
            mask_roi = effective_mask[ty0:ty1, tx0:tx1].copy()
            if (
                text_id in self._reference_frames
                and text_id not in self._temporal_reference_seeded
            ):
                reference = self._reference_frames[text_id]
                if reference.shape == output.shape:
                    self.temporal.seed(text_id, reference[ty0:ty1, tx0:tx1])
                    self._temporal_reference_seeded.add(text_id)
            if (
                str(cover.get("strategy") or "") == "smooth_surface_plate"
            ):
                cleaned_roi = _smooth_surface_plate(source_roi, mask_roi)
                temporal_qa = {
                    "mode": "smooth_surface_plate",
                    "reference": "low_frequency_border_fit",
                }
            elif intro_stylized_title_mask:
                # Large stylized opening glyphs need true local removal, not a
                # colour-preserving blur that leaves their yellow fill
                # readable.  Inpaint only the source-bound glyph components;
                # the surrounding face/chest pixels remain untouched.
                import cv2

                inpaint_radius = max(
                    3,
                    min(
                        15,
                        int(
                            round(
                                float(
                                    cover.get("canonical_glyph_height_fraction")
                                    or dict(track.get("geometry") or {}).get("height")
                                    or 0.04
                                )
                                * height
                                * 0.22
                            )
                        ),
                    ),
                )
                cleaned_roi = cv2.inpaint(
                    source_roi,
                    mask_roi,
                    inpaint_radius,
                    cv2.INPAINT_TELEA,
                )
                temporal_qa = {
                    "mode": "intro_stylized_title_inpaint",
                    "reference": "current_frame_source_bound_glyph_mask",
                    "inpaint_radius": inpaint_radius,
                }
            elif str(cover.get("strategy") or "") == UNIFIED_EDITOR_COVER_STRATEGY:
                epoch_id = str(
                    cover.get("soft_cover_epoch_id")
                    or context.get("soft_cover_epoch_id")
                    or text_id
                )
                epoch_style = self._epoch_style_cache.get(epoch_id)
                if epoch_style is None:
                    canonical_fraction = float(
                        cover.get("canonical_glyph_height_fraction")
                        or dict(track.get("geometry") or {}).get("height")
                        or 0.03
                    )
                    epoch_style = {
                        **dict(cover.get("blur") or {}),
                        "canonical_glyph_height_px": max(
                            1, int(round(canonical_fraction * height))
                        ),
                    }
                    self._epoch_style_cache[epoch_id] = dict(epoch_style)
                if bool(cover.get("preserve_mask_holes")):
                    epoch_style = {
                        **epoch_style,
                        "rounded_corner_text_height_fraction": 0.0,
                    }
                reconstruction_mode = "stable_soft_blur"
                clean_reference = self._epoch_reference_frames.get(epoch_id)
                reference_ready = (
                    clean_reference is not None
                    and clean_reference.shape == output.shape
                    and epoch_id not in self._epoch_temporal_reference_disabled
                )
                if reference_ready:
                    assert clean_reference is not None
                    reference_roi = clean_reference[ty0:ty1, tx0:tx1].copy()
                    if epoch_id not in self._epoch_temporal_seeded:
                        self.temporal.seed(epoch_id, reference_roi)
                        self._epoch_temporal_seeded.add(epoch_id)
                    cleaned_roi, temporal_candidate_qa = self.temporal.clean(
                        source_roi,
                        mask_roi,
                        key=epoch_id,
                    )
                    if str(temporal_candidate_qa.get("mode") or "") in {
                        "static_plate",
                        "affine_reference_plate",
                        "flow_reference_plate",
                    }:
                        temporal_qa = {
                            **temporal_candidate_qa,
                            "status": "PASS",
                            "reconstruction_mode": "temporal_clean_reference",
                            "soft_cover_epoch_id": epoch_id,
                        }
                        reconstruction_mode = "temporal_clean_reference"
                    else:
                        # Once a seeded clean plate stops aligning, do not let
                        # TemporalInpaintState alternate between that stale
                        # plate and current-frame blur on later frames. Such
                        # mode flapping is the main source of visible cover
                        # pulsing on moving scenes. Keep the epoch on the
                        # deterministic fallback for its remaining lifetime.
                        self._epoch_temporal_reference_disabled.add(epoch_id)
                        cleaned_roi = source_roi.copy()
                        temporal_qa = {
                            **dict(temporal_candidate_qa),
                            "reference_disabled_for_epoch": True,
                        }
                else:
                    cleaned_roi = source_roi.copy()
                    temporal_qa = {}

                # A flat/coherent border can reconstruct the surface without
                # the obvious frosted-glass rectangle. It is attempted only
                # after temporal clean-plate alignment and before blur.
                allow_spatial_surface = (
                    bool(cover.get("soft_cover_epoch_id"))
                    and
                    str(context.get("effective_kind") or track.get("kind") or "")
                    == "ui"
                    and not bool(context.get("caption_row"))
                    and not bool(cover.get("preserve_mask_holes"))
                )
                if (
                    reconstruction_mode != "temporal_clean_reference"
                    and allow_spatial_surface
                ):
                    import cv2

                    binary_roi = mask_roi > 0
                    ring_radius = max(
                        2,
                        int(round(float(epoch_style["canonical_glyph_height_px"]) * 0.35)),
                    )
                    ring_kernel = cv2.getStructuringElement(
                        cv2.MORPH_ELLIPSE,
                        (ring_radius * 2 + 1, ring_radius * 2 + 1),
                    )
                    ring = (
                        cv2.dilate(binary_roi.astype(np.uint8), ring_kernel) > 0
                    ) & (~binary_roi)
                    ring_values = source_roi[ring]
                    ring_mad = 255.0
                    if len(ring_values) >= 32:
                        ring_median = np.median(ring_values, axis=0)
                        ring_mad = float(
                            np.mean(np.abs(ring_values.astype(np.float32) - ring_median))
                        )
                    if ring_mad <= float(
                        epoch_style.get("spatial_surface_max_ring_mad")
                        or UNIFIED_EDITOR_BLUR_PROFILE["spatial_surface_max_ring_mad"]
                    ):
                        cleaned_roi = _smooth_surface_plate(source_roi, mask_roi)
                        temporal_qa = {
                            "status": "PASS",
                            "mode": "spatial_surface_reconstruction",
                            "reconstruction_mode": "spatial_surface_reconstruction",
                            "soft_cover_epoch_id": epoch_id,
                            "ring_mad": round(ring_mad, 4),
                        }
                        reconstruction_mode = "spatial_surface_reconstruction"

                if reconstruction_mode == "stable_soft_blur":
                    cleaned_roi, temporal_qa = _editor_blur_plate(
                        source_roi,
                        mask_roi,
                        frame_height_px=height,
                        profile=epoch_style,
                    )
                    temporal_qa.update(
                        {
                            "reconstruction_mode": "stable_soft_blur",
                            "soft_cover_epoch_id": epoch_id,
                            "style_locked": True,
                        }
                    )
                blur_profile = dict(epoch_style)
                overlap_low_energy_pass = bool(
                    temporal_qa.get("status") == "BLOCKED"
                    and prior_overlap_fraction
                    >= float(
                        blur_profile.get(
                            "overlap_residual_min_prior_fraction"
                        )
                        or 1.0
                    )
                    and float(temporal_qa.get("source_stroke_energy") or 0.0)
                    <= float(
                        blur_profile.get(
                            "overlap_residual_max_source_energy"
                        )
                        or 0.0
                    )
                    and float(temporal_qa.get("output_stroke_energy") or 0.0)
                    <= float(
                        blur_profile.get(
                            "overlap_residual_max_output_energy"
                        )
                        or 0.0
                    )
                )
                if overlap_low_energy_pass:
                    temporal_qa["status"] = "PASS"
                    temporal_qa["overlap_low_energy_pass"] = True
                    temporal_qa["prior_overlap_fraction"] = round(
                        prior_overlap_fraction, 6
                    )
                if (
                    temporal_qa.get("status") == "BLOCKED"
                    and mask_qa.get("fallback") == "full_roi_plate"
                ):
                    context = dict(
                        dict(track.get("render_policy") or {}).get("context")
                        or {}
                    )
                    transition_safety_cover = bool(
                        track.get("transition_hold_cover_only")
                        or context.get("stacked_caption_sibling_cover_extension")
                    )
                    if transition_safety_cover:
                        # A compact sibling/hold ROI can contain hair, fabric
                        # or a face edge after the source glyph has ended.  Its
                        # stroke metric is intentionally deferred to local
                        # encoded-output OCR instead of blocking the renderer
                        # on a non-text texture false positive.
                        temporal_qa["status"] = "PASS"
                        temporal_qa["transition_safety_cover_deferred_qa"] = True
                    else:
                        track_qa["temporal"] = temporal_qa
                        track_qa["status"] = "BLOCKED"
                        raise AdaptiveRenderBlocked(
                            f"Residual stroke gate blocked for {text_id}",
                            diagnostics={"tracks": diagnostics + [track_qa]},
                        )
                last_epoch_frame = self._epoch_last_frame_index.get(epoch_id)
                consecutive_epoch_frame = bool(
                    frame_index is not None
                    and last_epoch_frame is not None
                    and int(frame_index) == last_epoch_frame + 1
                )
                previous_epoch_output = (
                    self._epoch_last_output.get(epoch_id)
                    if consecutive_epoch_frame
                    else None
                )
                previous_epoch_mask = (
                    self._epoch_last_mask.get(epoch_id)
                    if consecutive_epoch_frame
                    else None
                )
                aesthetic = _cover_aesthetic_metrics(
                    source_roi,
                    cleaned_roi,
                    mask_roi,
                    previous_after=previous_epoch_output,
                    previous_mask=previous_epoch_mask,
                )
                prior_tint = (
                    self._epoch_last_tint.get(epoch_id)
                    if consecutive_epoch_frame
                    else None
                )
                current_tint = np.median(
                    cleaned_roi[mask_roi > 0], axis=0
                ).astype(np.float32)
                if prior_tint is not None:
                    aesthetic["plate_uniformity_score"] = round(
                        float(np.mean(np.abs(current_tint - prior_tint))) / 255.0,
                        6,
                    )
                else:
                    aesthetic["plate_uniformity_score"] = 0.0
                aesthetic_limits = {
                    "max_boundary_seam_score": float(
                        epoch_style.get("max_boundary_seam_score")
                        or UNIFIED_EDITOR_BLUR_PROFILE["max_boundary_seam_score"]
                    ),
                    "max_temporal_flicker_score": float(
                        epoch_style.get("max_temporal_flicker_score")
                        or UNIFIED_EDITOR_BLUR_PROFILE["max_temporal_flicker_score"]
                    ),
                    "max_background_color_drift": float(
                        epoch_style.get("max_background_color_drift")
                        or UNIFIED_EDITOR_BLUR_PROFILE["max_background_color_drift"]
                    ),
                }
                aesthetic["limits"] = aesthetic_limits
                aesthetic["status"] = (
                    "PASS"
                    if aesthetic["boundary_seam_score"]
                    <= aesthetic_limits["max_boundary_seam_score"]
                    and aesthetic["temporal_flicker_score"]
                    <= aesthetic_limits["max_temporal_flicker_score"]
                    and aesthetic["background_color_drift"]
                    <= aesthetic_limits["max_background_color_drift"]
                    else "WARN"
                )
                if (
                    aesthetic["status"] != "PASS"
                    and reconstruction_mode != "stable_soft_blur"
                ):
                    fallback_from = reconstruction_mode
                    fallback_roi, fallback_qa = _editor_blur_plate(
                        source_roi,
                        mask_roi,
                        frame_height_px=height,
                        profile=epoch_style,
                    )
                    if str(fallback_qa.get("status") or "") == "PASS":
                        cleaned_roi = fallback_roi
                        temporal_qa = {
                            **fallback_qa,
                            "reconstruction_mode": "stable_soft_blur",
                            "soft_cover_epoch_id": epoch_id,
                            "style_locked": True,
                            "aesthetic_fallback_from": fallback_from,
                        }
                        reconstruction_mode = "stable_soft_blur"
                        aesthetic = _cover_aesthetic_metrics(
                            source_roi,
                            cleaned_roi,
                            mask_roi,
                            previous_after=previous_epoch_output,
                            previous_mask=previous_epoch_mask,
                        )
                        aesthetic["plate_uniformity_score"] = (
                            round(
                                float(
                                    np.mean(
                                        np.abs(
                                            np.median(
                                                cleaned_roi[mask_roi > 0], axis=0
                                            ).astype(np.float32)
                                            - prior_tint
                                        )
                                    )
                                )
                                / 255.0,
                                6,
                            )
                            if prior_tint is not None
                            else 0.0
                        )
                        aesthetic["limits"] = aesthetic_limits
                        aesthetic["status"] = (
                            "PASS"
                            if aesthetic["boundary_seam_score"]
                            <= aesthetic_limits["max_boundary_seam_score"]
                            and aesthetic["temporal_flicker_score"]
                            <= aesthetic_limits["max_temporal_flicker_score"]
                            and aesthetic["background_color_drift"]
                            <= aesthetic_limits["max_background_color_drift"]
                            else "WARN"
                        )
                        aesthetic["fallback_from"] = fallback_from
                        current_tint = np.median(
                            cleaned_roi[mask_roi > 0], axis=0
                        ).astype(np.float32)
                temporal_qa["aesthetic_qa"] = aesthetic
                self._epoch_last_output[epoch_id] = cleaned_roi.copy()
                self._epoch_last_mask[epoch_id] = mask_roi.copy()
                self._epoch_last_tint[epoch_id] = current_tint
                if frame_index is not None:
                    self._epoch_last_frame_index[epoch_id] = int(frame_index)
            elif str(cover.get("strategy") or "") == "spatial_telea_r9":
                import cv2

                cleaned_roi = cv2.inpaint(
                    source_roi.copy(), mask_roi.astype(np.uint8), 9, cv2.INPAINT_TELEA
                )
                temporal_qa = {
                    "mode": "spatial_telea_r9",
                    "reference": "legacy_tight_residual_roi",
                }
            else:
                cleaned_roi, temporal_qa = self.temporal.clean(
                    source_roi,
                    mask_roi,
                    key=text_id,
                )
            if (
                mask_qa.get("fallback") == "reference_plate"
                and temporal_qa.get("mode") == "spatial_fallback"
            ):
                track_qa["temporal"] = temporal_qa
                track_qa["status"] = "BLOCKED"
                raise AdaptiveRenderBlocked(
                    f"Reference plate alignment failed for {text_id}",
                    diagnostics={"tracks": diagnostics + [track_qa]},
                )
            damage_qa = evaluate_damage_budget(
                source_roi,
                cleaned_roi,
                mask_roi,
                budget,
                frame_pixel_count=height * width,
            )
            if (
                damage_qa["status"] != "PASS"
                and unified_editor_cover
                and full_roi_plate
                and str(temporal_qa.get("reconstruction_mode") or "")
                in {
                    "spatial_surface_reconstruction",
                    "temporal_clean_reference",
                }
            ):
                # Reconstruction methods can interpolate a few pixels outside
                # an inward-rounded mask even though assignment is scoped to
                # the padded ROI. Fall back to the invariant stable blur and
                # re-run both temporal and damage QA; never relax the source
                # damage limits and never keep the rejected reconstruction.
                fallback_roi, fallback_qa = _editor_blur_plate(
                    source_roi,
                    mask_roi,
                    frame_height_px=height,
                    profile=dict(epoch_style),
                )
                fallback_damage = evaluate_damage_budget(
                    source_roi,
                    fallback_roi,
                    mask_roi,
                    budget,
                    frame_pixel_count=height * width,
                )
                if (
                    str(fallback_qa.get("status") or "") == "PASS"
                    and str(fallback_damage.get("status") or "") == "PASS"
                ):
                    rejected_mode = str(
                        temporal_qa.get("reconstruction_mode") or ""
                    )
                    cleaned_roi = fallback_roi
                    temporal_qa = {
                        **fallback_qa,
                        "reconstruction_mode": "stable_soft_blur",
                        "soft_cover_epoch_id": str(
                            cover.get("soft_cover_epoch_id")
                            or context.get("soft_cover_epoch_id")
                            or text_id
                        ),
                        "style_locked": True,
                        "damage_fallback_from": rejected_mode,
                    }
                    damage_qa = fallback_damage
            track_qa["temporal"] = temporal_qa
            track_qa["damage"] = damage_qa
            if damage_qa["status"] != "PASS":
                track_qa["status"] = "BLOCKED"
                raise AdaptiveRenderBlocked(
                    f"Damage budget blocked for {track.get('text_id')}",
                    diagnostics={"tracks": diagnostics + [track_qa]},
                )
            output[ty0:ty1, tx0:tx1] = cleaned_roi
            if unified_editor_cover and full_roi_plate:
                concealed_mask = np.maximum(concealed_mask, mask)
            track_qa["status"] = "PASS"
            diagnostics.append(track_qa)

        # Every original text authority keeps a diagnostic/layout anchor even
        # when its cover pixels were processed once by a union component.
        diagnostic_ids = {str(row.get("text_id") or "") for row in diagnostics}
        for component in cover_tracks:
            member_ids = list(component.get("_cover_component_member_ids") or [])
            if not member_ids:
                continue
            representative_id = str(component.get("text_id") or "")
            representative_qa = next(
                (
                    row
                    for row in diagnostics
                    if str(row.get("text_id") or "") == representative_id
                ),
                {},
            )
            for member_id in member_ids:
                if not member_id or member_id in diagnostic_ids:
                    continue
                diagnostics.append(
                    {
                        "text_id": member_id,
                        "status": "PASS",
                        "cover_suppressed_by_component": representative_id,
                        "cover_component": dict(
                            representative_qa.get("cover_component") or {}
                        ),
                        "mask": dict(representative_qa.get("mask") or {}),
                        "temporal": {
                            "status": "PASS",
                            "mode": "covered_by_union_component",
                        },
                        "damage": {
                            "status": "PASS",
                            "blocked_reasons": [],
                            "metrics": {},
                        },
                    }
                )
                diagnostic_ids.add(member_id)

        dense_tracks = [
            track
            for track in text_tracks
            if dict(self._policy(track).get("context") or {}).get("dense_ui")
            and not _uses_cover_aligned_layout(track)
            and str(track.get("text_vi") or "").strip()
        ]
        dense_ids = {str(track.get("text_id") or "") for track in dense_tracks}
        if dense_tracks:
            layout_mode = "responsive_grid"
        elif text_tracks and all(_uses_cover_aligned_layout(track) for track in text_tracks):
            layout_mode = "cover_aligned"
        else:
            layout_mode = "anchored_text"
        dense_qa: list[dict[str, Any]] = []
        if dense_tracks:
            first_policy = self._policy(dense_tracks[0])
            safe_area = dict(dict(first_policy.get("layout") or {}).get("safe_area") or {})
            items = []
            for track in dense_tracks:
                geometry = dict(track.get("geometry") or {})
                side = (
                    "left"
                    if float(geometry.get("x") or 0.0)
                    + float(geometry.get("width") or 0.0) * 0.5
                    < 0.5
                    else "right"
                )
                slot_authority = dict(
                    self._dense_slot_authority.get(
                        str(track.get("text_id") or "")
                    )
                    or {}
                )
                if slot_authority:
                    side = str(slot_authority.get("side") or side)
                items.append(
                    {
                        "text_id": track.get("text_id"),
                        "content_id": track.get("content_id"),
                        "text": track.get("text_vi"),
                        "geometry": dict(track.get("geometry") or {}),
                        "side": side,
                        **(
                            {
                                "stable_slot": slot_authority
                            }
                            if str(track.get("text_id") or "")
                            in self._dense_slot_authority
                            else {}
                        ),
                    }
                )
            cache_key = (
                tuple(str(item["text_id"]) for item in items),
                width,
                height,
                str(self.fontfile),
            )
            layouts = self._dense_cache.get(cache_key)
            if layouts is None:
                try:
                    layouts = plan_dense_grid_layouts(
                        items,
                        safe_area=safe_area,
                        frame_width=width,
                        frame_height=height,
                        fontfile=self.fontfile,
                        background_bgr=output,
                    )
                except TypographyLayoutError as exc:
                    raise AdaptiveRenderBlocked(
                        f"Dense UI typography blocked: {exc}",
                        diagnostics={
                            "dense_ui": {
                                "text_ids": [str(item["text_id"]) for item in items],
                                "texts": [str(item["text"]) for item in items],
                                "safe_area": safe_area,
                            }
                        },
                    ) from exc
                self._dense_cache[cache_key] = layouts
            for item in layouts:
                layout = item["layout"]
                blit_rgba_bgr(output, layout.rgba, x0=layout.x0, y0=layout.y0)
                dense_qa.append(
                    {
                        "text_id": item.get("text_id"),
                        "x0": layout.x0,
                        "y0": layout.y0,
                        "width": layout.width,
                        "height": layout.height,
                        "placement_mode": item.get("placement_mode"),
                    }
                )

        by_id = {str(row.get("text_id") or ""): row for row in diagnostics}
        for row in diagnostics:
            if str(row.get("text_id") or "") in panel_suppressed_ids:
                row["text_render_suppressed"] = "deduplicated_by_dense_ui_panel"
            elif str(row.get("text_id") or "") in protected_text_conflict_ids:
                row["text_render_suppressed"] = "protected_source_geometry_conflict"
            elif str(row.get("text_id") or "") not in text_track_ids:
                row["text_render_suppressed"] = "overlapping_same_semantic_geometry"
        for track in text_tracks:
            text_id = str(track.get("text_id") or "")
            if text_id in dense_ids or not str(track.get("text_vi") or "").strip():
                continue
            layout = self._layout(track, frame_bgr=output)
            blit_rgba_bgr(output, layout.rgba, x0=layout.x0, y0=layout.y0)
            by_id[text_id]["layout"] = {
                "safe_area": dict(
                    dict(self._policy(track).get("layout") or {}).get("safe_area") or {}
                ),
                "lines": list(layout.lines),
                "font_size_px": layout.font_size_px,
                "x0": layout.x0,
                "y0": layout.y0,
                "width": layout.width,
                "height": layout.height,
                "fill_rgb": list(layout.fill_rgb),
                "stroke_rgb": list(layout.stroke_rgb),
                "placement_mode": (
                    "cover_aligned"
                    if _uses_cover_aligned_layout(track)
                    else "anchored_text"
                ),
            }
        for panel, diagnostic in zip(active_panels, panel_diagnostics):
            if not diagnostic.get("temporal_exit_release"):
                self._render_dense_panel_text(output, panel, diagnostic)
        return output, {
            "status": "PASS",
            "tracks": diagnostics,
            "layout_mode": "dense_ui_panel" if active_panels else layout_mode,
            "dense_layouts": dense_qa,
            "dense_ui_panels": panel_diagnostics,
            "frame_base_mode": frame_base_mode,
        }
