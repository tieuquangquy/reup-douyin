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
    dilate_radius = max(2, min(10, int(round(geometry_height_px * dilate_fraction))))
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
        self._mask_cache: dict[tuple[str, int, int, str], dict[str, Any]] = {}
        self._preseeded_masks: dict[str, np.ndarray] = {}
        self._dense_ui_panels: list[dict[str, Any]] = []
        self._dense_ui_panel_tracks: dict[str, list[dict[str, Any]]] = {}
        self._dense_ui_panel_plates: dict[str, np.ndarray] = {}

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
        key = (
            str(track.get("text_id") or ""),
            width,
            height,
            str(policy.get("policy_version") or ""),
        )
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
        # Preserve low-frequency scene motion while destroying glyph-scale
        # detail. This keeps the phone UI plate opaque to OCR without the
        # boundary flash caused by a single static color across a moving shot.
        import cv2

        source_crop = output[y0:y1, x0:x1].copy()
        low_width = min(32, max(8, x1 - x0))
        low_height = min(64, max(8, y1 - y0))
        low = cv2.resize(
            source_crop, (low_width, low_height), interpolation=cv2.INTER_AREA
        )
        source_aware_plate = cv2.resize(
            low, (x1 - x0, y1 - y0), interpolation=cv2.INTER_CUBIC
        )
        source_aware_plate = cv2.GaussianBlur(source_aware_plate, (9, 9), 0)
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
            "plate_mode": "source_aware_low_frequency",
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
        text_track_ids = {str(track.get("text_id") or "") for track in text_tracks}
        for track in tracks:
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
            full_roi_plate = str(cover.get("mask_mode") or "") == "full_roi_plate"
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
                else "full_roi_plate"
                if full_roi_plate and dense_mask
                else None
            )
            mask_qa["source"] = mask_source
            track_qa: dict[str, Any] = {
                "text_id": track.get("text_id"),
                "content_id": track.get("content_id"),
                "cover_roi": cover_roi,
                "mask": mask_qa,
            }
            if mask_qa["status"] != "PASS":
                track_qa["status"] = "BLOCKED"
                raise AdaptiveRenderBlocked(
                    f"Mask quality blocked for {track.get('text_id')}",
                    diagnostics={"tracks": diagnostics + [track_qa]},
                )
            x0, y0, x1, y1 = roi_px
            if x1 <= x0 or y1 <= y0:
                raise AdaptiveRenderBlocked(f"Empty cover ROI for {text_id}")
            temporal_pad = max(8, int(round(max(x1 - x0, y1 - y0) * 0.15)))
            tx0 = max(0, x0 - temporal_pad)
            ty0 = max(0, y0 - temporal_pad)
            tx1 = min(width, x1 + temporal_pad)
            ty1 = min(height, y1 + temporal_pad)
            source_roi = output[ty0:ty1, tx0:tx1].copy()
            mask_roi = mask[ty0:ty1, tx0:tx1].copy()
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
                or intro_overlay_spatial_fallback
            ):
                cleaned_roi = _smooth_surface_plate(source_roi, mask_roi)
                temporal_qa = {
                    "mode": "smooth_surface_plate",
                    "reference": "low_frequency_border_fit",
                }
            elif str(cover.get("strategy") or "") == "spatial_telea_r9":
                import cv2

                cleaned_roi = cv2.inpaint(
                    source_roi.copy(), mask_roi.astype(np.uint8), 9, cv2.INPAINT_TELEA
                )
                temporal_qa = {
                    "mode": "spatial_telea_r9",
                    "reference": "tight_residual_roi",
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
            track_qa["temporal"] = temporal_qa
            track_qa["damage"] = damage_qa
            if damage_qa["status"] != "PASS":
                track_qa["status"] = "BLOCKED"
                raise AdaptiveRenderBlocked(
                    f"Damage budget blocked for {track.get('text_id')}",
                    diagnostics={"tracks": diagnostics + [track_qa]},
                )
            output[ty0:ty1, tx0:tx1] = cleaned_roi
            track_qa["status"] = "PASS"
            diagnostics.append(track_qa)

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
