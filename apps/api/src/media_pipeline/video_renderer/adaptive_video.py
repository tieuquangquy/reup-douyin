"""PTS-preserving adaptive Phase 4 video renderer (PyAV + explicit audio mux)."""

from __future__ import annotations

import json
import hashlib
import math
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from src.media_pipeline.video_renderer.adaptive_render import (
    AdaptiveFrameRenderer,
    AdaptiveRenderBlocked,
)
from src.media_pipeline.video_renderer.render_policy import (
    enforce_unified_editor_cover_contract,
)
from src.media_pipeline.video_renderer.reference_plate import (
    is_text_reduced_reference_candidate,
    is_usable_reference_plate_candidate,
    reference_plate_candidate_score,
)
from src.media_pipeline.frame_sampling.coverage_track_closure import (
    local_textness_mask,
)
from src.media_pipeline.video_renderer.renderer import probe_video_duration_ms
from src.media_pipeline.video_renderer.video_encoder import (
    SOFTWARE_ENCODER,
    ffmpeg_runtime_version,
    ffmpeg_video_encode_args,
    is_video_copy_args,
    probe_ffmpeg_encoder,
    select_video_encoder,
)
from src.render_pipeline.audio_loudness import (
    LoudnessMeasurementError,
    background_mix_gain,
    loudness_filter_args,
    two_pass_loudness_filter_args,
)


class AdaptiveVideoRenderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


def resolve_background_gain(contract: Mapping[str, Any]) -> float:
    """Resolve the approved mix gain, retaining a legacy-config fallback."""

    audio = dict(dict(contract.get("authorities") or {}).get("audio") or {})
    raw_gain = audio.get("background_gain")
    if raw_gain is None:
        return float(background_mix_gain())
    try:
        gain = float(raw_gain)
    except (TypeError, ValueError) as exc:
        raise AdaptiveVideoRenderError("Approved background gain is invalid") from exc
    if not math.isfinite(gain) or not 0.0 <= gain <= 1.0:
        raise AdaptiveVideoRenderError("Approved background gain is outside 0..1")
    return gain


def resolve_narration_atempo(
    narration_duration_seconds: float,
    target_duration_seconds: float,
) -> float:
    """Fit any meaningful narration overrun without exceeding the 1.20x policy."""
    ratio = float(narration_duration_seconds) / max(
        0.001, float(target_duration_seconds)
    )
    if ratio > 1.20:
        raise AdaptiveVideoRenderError(
            "Narration exceeds the bounded atempo fit policy"
        )
    return ratio if ratio > 1.0001 else 1.0


@dataclass(frozen=True)
class AdaptiveVideoRenderResult:
    output_path: Path
    frame_count: int
    qa_path: Path
    visual_preview: bool
    encoder_metadata: dict[str, Any]
    audio_mix_metadata: dict[str, Any]


def _coverage_presence_ranges(track: Mapping[str, Any]) -> list[tuple[int, int]]:
    coverage = dict(track.get("coverage_authority") or {})
    output: list[tuple[int, int]] = []
    for raw in list(coverage.get("presence_ranges") or []):
        if not isinstance(raw, Sequence) or len(raw) != 2:
            continue
        start, end = int(raw[0]), int(raw[1])
        if end >= start:
            output.append((start, end))
    return sorted(output)


def _physical_presence_ranges(track: Mapping[str, Any]) -> list[tuple[int, int]]:
    """Return the stable physical cover activation, including short bridges."""

    context = dict(dict(track.get("render_policy") or {}).get("context") or {})
    raw = context.get("physical_presence_ranges")
    ranges: list[tuple[int, int]] = []
    for item in list(raw or []):
        if not isinstance(item, Sequence) or len(item) != 2:
            continue
        start, end = int(item[0]), int(item[1])
        if end >= start:
            ranges.append((start, end))
    return sorted(ranges)


def _interpolated_coverage_geometry(
    track: Mapping[str, Any], frame_index: int
) -> dict[str, float] | None:
    coverage = dict(track.get("coverage_authority") or {})
    keyframes = sorted(
        (
            (int(raw.get("frame_index") or 0), dict(raw.get("geometry") or {}))
            for raw in list(coverage.get("geometry_keyframes") or [])
            if isinstance(raw, Mapping)
            and isinstance(raw.get("geometry"), Mapping)
        ),
        key=lambda row: row[0],
    )
    if not keyframes:
        return None

    def values(raw: Mapping[str, Any]) -> dict[str, float]:
        return {
            key: float(raw.get(key) or 0.0)
            for key in ("x", "y", "width", "height")
        }

    index = int(frame_index)
    if index <= keyframes[0][0]:
        return values(keyframes[0][1])
    if index >= keyframes[-1][0]:
        return values(keyframes[-1][1])
    for (left_index, left), (right_index, right) in zip(
        keyframes, keyframes[1:]
    ):
        if not left_index <= index <= right_index:
            continue
        ratio = (index - left_index) / float(max(1, right_index - left_index))
        return {
            key: max(
                0.0,
                min(
                    1.0,
                    float(left.get(key) or 0.0) * (1.0 - ratio)
                    + float(right.get(key) or 0.0) * ratio,
                ),
            )
            for key in ("x", "y", "width", "height")
        }
    return None


def dynamic_track_for_frame(
    track: Mapping[str, Any], frame_index: int
) -> dict[str, Any]:
    """Project frame-exact coverage geometry into cover and layout authority."""

    row = dict(track)
    dynamic = _interpolated_coverage_geometry(row, int(frame_index))
    if dynamic is None or dynamic["width"] <= 0.0 or dynamic["height"] <= 0.0:
        return row
    original = dict(row.get("geometry") or {})
    policy = dict(row.get("render_policy") or {})
    cover = dict(policy.get("cover") or {})
    cover_roi = dict(cover.get("roi") or original)
    layout = dict(policy.get("layout") or {})
    safe_area = dict(layout.get("safe_area") or {})

    # Opening stylized titles (large outlined/rotated glyphs) have a bounded
    # glyph envelope established by the high-resolution OCR authority.  The
    # all-frame proxy coverage stream is intentionally recall-biased and may
    # include outline/glow or nearby subject pixels.  Projecting those noisy
    # boxes into the cover makes the mask grow/shrink between adjacent frames,
    # which is exactly the visible flash/late-frame leak this renderer must
    # prevent.  Keep the approved title cover and text safe-area static for the
    # short intro epoch; temporal activation still follows presence ranges.
    # This is role-based and does not depend on a source-specific coordinate.
    if bool(dict(policy.get("context") or {}).get("intro_stylized_title")):
        row["coverage_geometry_frame"] = int(frame_index)
        return row

    # Outside detector-observed timing, the local outlined-caption gate proves
    # physical ink is present but cannot prove the missing line's exact width.
    # A last-keyframe box can be much narrower than the next sentence and
    # leave readable CJK on both sides. Use the approved caption lane only for
    # this visually confirmed semantic extension.
    if (
        bool(row.get("semantic_envelope_visual_confirmation"))
        and bool(row.get("semantic_dialogue_hardsub"))
    ):
        cover["roi"] = {
            **cover_roi,
            "x": 0.0,
            "width": 1.0,
        }
        cover["geometry_mode"] = "full_width_caption_lane"
        layout["safe_area"] = {
            **safe_area,
            "x": 0.04,
            "width": 0.92,
        }
        damage_budget = dict(policy.get("damage_budget") or {})
        damage_budget["max_frame_change_fraction"] = min(
            0.16,
            max(
                float(damage_budget.get("max_frame_change_fraction") or 0.0),
                float(cover["roi"].get("height") or 0.0) * 1.02,
            ),
        )
        policy["cover"] = cover
        policy["layout"] = layout
        policy["damage_budget"] = damage_budget
        row["render_policy"] = policy
        row["coverage_geometry_frame"] = int(frame_index)
        return row

    dx = dynamic["x"] - float(original.get("x") or 0.0)
    dy = dynamic["y"] - float(original.get("y") or 0.0)
    dw = dynamic["width"] - float(original.get("width") or 0.0)
    dh = dynamic["height"] - float(original.get("height") or 0.0)
    geometry_mode = str(cover.get("geometry_mode") or "")

    # Caption content boxes can move several pixels when glyphs change even
    # though the editor-owned subtitle lane is stationary.  A stabilized
    # caption cover is already the robust envelope of those observations; do
    # not project sparse keyframe jitter back into its mask or text layout.
    provenance = dict(row.get("visual_provenance") or {})
    screen_locked_semantic_caption = bool(row.get("semantic_dialogue_hardsub")) and (
        str(provenance.get("classification") or "") == "EDITOR_OVERLAY"
        and float(provenance.get("confidence") or 0.0) >= 0.90
    )
    if geometry_mode in {
        "stable_caption_envelope",
        "stable_caption_group",
        "stable_caption_group_adaptive_horizontal",
        "solid_editor_card_panel_union",
    } or screen_locked_semantic_caption:
        # High-confidence semantic editor captions are screen-locked. Sparse
        # OCR keyframes can jump from the caption row to printed text on a
        # moving product or prop. Keep the approved cover/layout envelope
        # stable and use those keyframes only as physical-presence evidence.
        # This also prevents the plate from pulsing as individual glyph boxes
        # change width between adjacent frames.
        row["geometry"] = dynamic
        row["render_policy"] = policy
        row["coverage_geometry_frame"] = int(frame_index)
        return row

    def shifted(rect: Mapping[str, Any], *, resize: bool) -> dict[str, float]:
        return {
            "x": max(0.0, min(1.0, float(rect.get("x") or 0.0) + dx)),
            "y": max(0.0, min(1.0, float(rect.get("y") or 0.0) + dy)),
            "width": max(
                0.0,
                min(
                    1.0,
                    float(rect.get("width") or 0.0) + (dw if resize else 0.0),
                ),
            ),
            "height": max(
                0.0,
                min(
                    1.0,
                    float(rect.get("height") or 0.0) + (dh if resize else 0.0),
                ),
            ),
        }

    row["geometry"] = dynamic
    cover["roi"] = shifted(cover_roi, resize=True)
    if geometry_mode == "full_width_caption_lane":
        cover["roi"]["x"] = 0.0
        cover["roi"]["width"] = 1.0
    if safe_area:
        # The static policy may intentionally allocate more typography room
        # than the source cover (for example, an approved Vietnamese phrase
        # promoted out of a one-line Chinese ``ui_chip``).  Replacing that
        # expanded area with the dynamic cover ROI made preflight pass but the
        # real frame renderer fail.  Project both rectangles through the same
        # geometry delta so their approved relative padding survives motion.
        layout["safe_area"] = (
            shifted(safe_area, resize=True)
            if str(layout.get("mode") or "") == "cover_aligned"
            else shifted(safe_area, resize=False)
        )
        if geometry_mode == "full_width_caption_lane":
            layout["safe_area"]["x"] = 0.0
            layout["safe_area"]["width"] = 1.0
    policy["cover"] = cover
    policy["layout"] = layout
    if geometry_mode == "full_width_caption_lane":
        damage_budget = dict(policy.get("damage_budget") or {})
        dynamic_cover_area = float(cover["roi"].get("width") or 0.0) * float(
            cover["roi"].get("height") or 0.0
        )
        damage_budget["max_frame_change_fraction"] = min(
            0.16,
            max(
                float(damage_budget.get("max_frame_change_fraction") or 0.0),
                dynamic_cover_area * 1.02,
            ),
        )
        policy["damage_budget"] = damage_budget
    row["render_policy"] = policy
    row["coverage_geometry_frame"] = int(frame_index)
    return row


def _outlined_caption_present(
    frame_bgr: np.ndarray,
    track: Mapping[str, Any],
) -> bool:
    """Detect a high-contrast editor caption inside its narrow visual lane.

    This detector is intentionally local and classical.  It is used only for
    the unsupported part of a semantic timing envelope, where OCR timing has
    no observation.  White glyph fill next to a dark outline is a much safer
    signal here than generic textness, which fires on hair, fabric and hands.
    """

    import cv2

    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        return False
    height, width = frame_bgr.shape[:2]
    policy = dict(track.get("render_policy") or {})
    roi = dict(dict(policy.get("cover") or {}).get("roi") or {})
    if not roi:
        return False
    x0 = max(0, int(np.floor((float(roi.get("x") or 0.0) - 0.01) * width)))
    x1 = min(
        width,
        int(
            np.ceil(
                (
                    float(roi.get("x") or 0.0)
                    + float(roi.get("width") or 0.0)
                    + 0.01
                )
                * width
            )
        ),
    )
    y0 = max(0, int(np.floor((float(roi.get("y") or 0.0) - 0.006) * height)))
    y1 = min(
        height,
        int(
            np.ceil(
                (
                    float(roi.get("y") or 0.0)
                    + float(roi.get("height") or 0.0)
                    + 0.006
                )
                * height
            )
        ),
    )
    if x1 <= x0 or y1 <= y0:
        return False
    crop = frame_bgr[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    channel_spread = np.max(crop, axis=2).astype(np.int16) - np.min(
        crop, axis=2
    ).astype(np.int16)
    white_fill = (gray >= 172) & (channel_spread <= 92)
    # Douyin editor captions are frequently light pink/yellow rather than
    # neutral white. They retain the same dark outline and baseline structure,
    # so admit bright chromatic fill here instead of dropping the entire
    # semantic extension merely because channel spread is high.
    brightest = np.max(crop, axis=2)
    bright_chromatic_fill = (
        (gray >= 125) & (brightest >= 170) & (channel_spread >= 35)
    )
    dark_outline = gray <= 105
    outline_neighborhood = cv2.dilate(
        dark_outline.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        iterations=1,
    ) > 0
    candidates = ((white_fill | bright_chromatic_fill) & outline_neighborhood).astype(
        np.uint8
    )
    candidates = cv2.morphologyEx(
        candidates,
        cv2.MORPH_OPEN,
        np.ones((2, 2), dtype=np.uint8),
    )
    component_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(
        candidates, connectivity=8
    )
    glyphs: list[tuple[float, float, int]] = []
    crop_height = max(1, y1 - y0)
    crop_width = max(1, x1 - x0)
    for index in range(1, component_count):
        component_width = int(stats[index, cv2.CC_STAT_WIDTH])
        component_height = int(stats[index, cv2.CC_STAT_HEIGHT])
        area = int(stats[index, cv2.CC_STAT_AREA])
        if (
            2 <= component_width <= max(12, int(crop_width * 0.12))
            and 3 <= component_height <= max(10, int(crop_height * 0.92))
            and area >= 5
        ):
            glyphs.append(
                (float(centroids[index][0]), float(centroids[index][1]), area)
            )
    if len(glyphs) < 3:
        return False
    # Real caption glyphs share a baseline and occupy a meaningful horizontal
    # span.  Isolated white/dark boundaries on a mirror, hand or garment may
    # satisfy the colour test but do not form this row structure.
    baseline_bin = max(4, int(round(crop_height * 0.16)))
    by_baseline: dict[int, list[tuple[float, float, int]]] = {}
    for glyph in glyphs:
        by_baseline.setdefault(int(round(glyph[1] / baseline_bin)), []).append(glyph)
    geometry = dict(track.get("geometry") or {})
    expected_center = (
        (
            float(geometry.get("y") or 0.0)
            + float(geometry.get("height") or 0.0) * 0.5
            - float(roi.get("y") or 0.0)
        )
        / max(0.001, float(roi.get("height") or 0.0) + 0.012)
    ) * crop_height
    plausible_rows = []
    for values in by_baseline.values():
        horizontal_span = (
            max(value[0] for value in values) - min(value[0] for value in values)
        ) / float(crop_width)
        if (
            len(values) >= 3
            and sum(value[2] for value in values) >= 120
            and horizontal_span >= 0.12
        ):
            plausible_rows.append(values)
    if not plausible_rows:
        return False
    # Prefer the baseline nearest this track's approved geometry.  Selecting
    # the largest component cluster instead can mistake a necklace or garment
    # pattern below the real caption for the caption row.
    aligned = min(
        plausible_rows,
        key=lambda values: (
            abs(
                sum(value[1] for value in values) / len(values)
                - expected_center
            ),
            -len(values),
        ),
    )
    horizontal_span = (
        max(value[0] for value in aligned) - min(value[0] for value in aligned)
    ) / float(crop_width)
    baseline_center = sum(value[1] for value in aligned) / len(aligned)
    return (
        len(aligned) >= 3
        and sum(value[2] for value in aligned) >= 120
        and horizontal_span >= 0.12
        and abs(baseline_center - expected_center) <= crop_height * 0.25
    )


def _semantic_extension_overlaps_protected_source(
    contract: Mapping[str, Any],
    track: Mapping[str, Any],
    frame_index: int,
) -> bool:
    """Reject source-scene text as evidence for an editor-caption extension."""

    policy = dict(track.get("render_policy") or {})
    editor = dict(dict(policy.get("cover") or {}).get("roi") or track.get("geometry") or {})
    ex0 = float(editor.get("x") or 0.0)
    ey0 = float(editor.get("y") or 0.0)
    ex1 = ex0 + float(editor.get("width") or 0.0)
    ey1 = ey0 + float(editor.get("height") or 0.0)
    for raw in list(contract.get("protected_source_tracks") or []):
        if not isinstance(raw, Mapping):
            continue
        provenance = dict(raw.get("visual_provenance") or {})
        if (
            str(provenance.get("classification") or "") != "SOURCE_INTRINSIC"
            or float(provenance.get("confidence") or 0.0) < 0.90
            or not (
                int(raw.get("start_frame") or 0)
                <= int(frame_index)
                <= int(raw.get("end_frame") or -1)
            )
        ):
            continue
        geometry = dict(raw.get("geometry") or {})
        px0 = float(geometry.get("x") or 0.0)
        py0 = float(geometry.get("y") or 0.0)
        px1 = px0 + float(geometry.get("width") or 0.0)
        py1 = py0 + float(geometry.get("height") or 0.0)
        intersection = max(0.0, min(ex1, px1) - max(ex0, px0)) * max(
            0.0, min(ey1, py1) - max(ey0, py0)
        )
        protected_area = max(0.0, px1 - px0) * max(0.0, py1 - py0)
        if protected_area > 0.0 and intersection / protected_area >= 0.60:
            return True
    return False


def active_tracks_for_frame(
    contract: Mapping[str, Any],
    frame_index: int,
    *,
    source_frame_bgr: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for raw in list(contract.get("render_tracks") or []):
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        start = int(row.get("start_frame") or 0)
        end = int(row.get("end_frame") or start)
        # ``start_frame/end_frame`` are the effective Vietnamese burn
        # authority after temporal-lane normalization.  Covering must still
        # use the original conservative OCR interval so a transition glyph is
        # never exposed while the text authority is being partitioned.
        raw_cover_start = row.get("cover_start_frame")
        raw_cover_end = row.get("cover_end_frame")
        cover_start = int(raw_cover_start) if raw_cover_start is not None else start
        cover_end = int(raw_cover_end) if raw_cover_end is not None else end
        cover = dict(dict(row.get("render_policy") or {}).get("cover") or {})
        # The policy expresses physical time and has already bounded the value
        # for the source FPS. Do not silently truncate 60-fps media back to a
        # 50-ms three-frame hold.
        hold = max(0, min(12, int(cover.get("transition_hold_frames") or 0)))
        coverage_ranges = _coverage_presence_ranges(row)
        # ``cover_start/end`` is the conservative, operator-approved source
        # concealment interval.  OCR presence ranges can have isolated gaps
        # (missed detector frames); using them as the cover authority exposes
        # the original Chinese subtitle exactly on those gaps.  Keep the
        # ranges for Vietnamese text activation only, and use the explicit
        # cover interval for concealment whenever it is present.
        explicit_cover_interval = (
            raw_cover_start is not None or raw_cover_end is not None
        )
        physical_ranges = _physical_presence_ranges(row)
        cover_ranges = (
            [(cover_start, cover_end)]
            if explicit_cover_interval
            else physical_ranges or coverage_ranges or [(cover_start, cover_end)]
        )
        in_cover = any(
            range_start - hold <= int(frame_index) <= range_end + hold
            for range_start, range_end in cover_ranges
        )
        if in_cover:
            in_core_cover = any(
                range_start <= int(frame_index) <= range_end
                for range_start, range_end in cover_ranges
            )
            # Presence ranges are detector observations, not semantic timing.
            # They may contain one-frame holes even while the same approved
            # sentence remains on screen.  Effective start/end boundaries are
            # already partitioned by Phase 4 and must be continuous here.
            text_active = (
                in_core_cover
                and start <= int(frame_index) <= end
                and not bool(row.get("cover_only"))
            )
            context = dict(dict(row.get("render_policy") or {}).get("context") or {})
            timing = dict(context.get("cover_timing_authority") or {})
            observed = list(timing.get("observed_range") or [])
            if (
                source_frame_bgr is not None
                and str(timing.get("mode") or "")
                in {
                    "semantic_observed_envelope",
                    "semantic_observed_coverage_union",
                    "approved_transcript_segment_union",
                }
                and len(observed) == 2
            ):
                observed_start, observed_end = int(observed[0]), int(observed[1])
                outside_observed = not (
                    observed_start <= int(frame_index) <= observed_end
                )
                if (
                    outside_observed
                    and (
                        not _outlined_caption_present(source_frame_bgr, row)
                        or _semantic_extension_overlaps_protected_source(
                            contract,
                            row,
                            int(frame_index),
                        )
                    )
                ):
                    continue
                if outside_observed:
                    row["semantic_envelope_visual_confirmation"] = True
            if not text_active:
                row["cover_only"] = True
                row["transition_hold_cover_only"] = not in_core_cover
            active.append(dynamic_track_for_frame(row, int(frame_index)))
    return active


def active_dense_ui_panels_for_frame(
    contract: Mapping[str, Any], frame_index: int
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in list(contract.get("dense_ui_panels") or [])
        if isinstance(row, Mapping)
        and int(row.get("start_frame") or 0)
        <= int(frame_index)
        <= int(row.get("end_frame") or -1)
    ]


def active_protected_source_regions_for_frame(
    contract: Mapping[str, Any], frame_index: int
) -> list[dict[str, Any]]:
    """Return only high-confidence source text regions for mask carve-outs."""

    protected = [
        dynamic_track_for_frame(dict(row), int(frame_index))
        for row in list(contract.get("protected_source_tracks") or [])
        if isinstance(row, Mapping)
        and int(row.get("start_frame") or 0)
        <= int(frame_index)
        <= int(row.get("end_frame") or -1)
        and str(
            dict(row.get("visual_provenance") or {}).get("classification") or ""
        )
        == "SOURCE_INTRINSIC"
        and float(
            dict(row.get("visual_provenance") or {}).get("confidence") or 0.0
        )
        >= 0.90
    ]
    semantic_dialogue = [
        row
        for row in active_tracks_for_frame(contract, int(frame_index))
        if bool(row.get("semantic_dialogue_hardsub"))
    ]

    def overlap_over_smaller(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
        a = dict(left.get("geometry") or {})
        right_policy = dict(right.get("render_policy") or {})
        semantic_cover = (
            dict(right_policy.get("cover") or {}).get("roi")
            if bool(right.get("semantic_dialogue_hardsub"))
            else None
        )
        b = dict(semantic_cover or right.get("geometry") or {})
        ax0, ay0 = float(a.get("x") or 0.0), float(a.get("y") or 0.0)
        bx0, by0 = float(b.get("x") or 0.0), float(b.get("y") or 0.0)
        ax1, ay1 = ax0 + float(a.get("width") or 0.0), ay0 + float(a.get("height") or 0.0)
        bx1, by1 = bx0 + float(b.get("width") or 0.0), by0 + float(b.get("height") or 0.0)
        intersection = max(0.0, min(ax1, bx1) - max(ax0, bx0)) * max(
            0.0, min(ay1, by1) - max(ay0, by0)
        )
        smaller = min(
            max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0),
            max(0.0, bx1 - bx0) * max(0.0, by1 - by0),
        )
        return intersection / smaller if smaller > 0.0 else 0.0

    return [
        row
        for row in protected
        if not any(
            overlap_over_smaller(row, dialogue) >= 0.65
            for dialogue in semantic_dialogue
        )
    ]


def validate_adaptive_render_contract(
    contract: Mapping[str, Any], *, visual_preview: bool
) -> None:
    if str(contract.get("status") or "") != "READY_FOR_PHASE4":
        raise AdaptiveVideoRenderError("Phase 4 input is not READY_FOR_PHASE4")
    authorities = dict(contract.get("authorities") or {})
    timebase = dict(authorities.get("timebase") or {})
    if str(timebase.get("mode") or "") == "VFR" and str(
        timebase.get("status") or ""
    ) != "READY_WITH_PTS_MAP":
        raise AdaptiveVideoRenderError("VFR input requires an approved PTS map")
    audio = dict(authorities.get("audio") or {})
    if not visual_preview and str(audio.get("status") or "") != "READY":
        raise AdaptiveVideoRenderError("Final render requires approved TTS audio authority")


def build_audio_mux_command(
    *,
    video_only: Path,
    audio_source: Path,
    background_audio_source: Path | None = None,
    output: Path,
    duration_seconds: float,
    ffmpeg_binary: str,
    audio_filter_args: Sequence[str] = (),
    background_gain: float = 1.0,
    narration_atempo: float = 1.0,
    video_codec_args: Sequence[str] = ("-c:v", "copy"),
    color_metadata: Mapping[str, Any] | None = None,
) -> list[str]:
    command = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_only),
        "-i",
        str(audio_source),
    ]
    if background_audio_source is not None:
        command.extend(["-i", str(background_audio_source)])
    resolved_video_args = [str(value) for value in video_codec_args]
    command.extend(["-map", "0:v:0", *resolved_video_args])
    if not is_video_copy_args(resolved_video_args):
        command.extend(["-fps_mode:v", "passthrough"])
    if background_audio_source is not None:
        loudnorm = next(
            (
                str(audio_filter_args[index + 1])
                for index, value in enumerate(audio_filter_args[:-1])
                if str(value) == "-af"
            ),
            "loudnorm=I=-14:TP=-1.5:LRA=11",
        )
        command.extend(
            [
                "-filter_complex",
                f"[1:a]atempo={float(narration_atempo):.6f},aresample=48000,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                "volume=1.0[narration];"
                "[2:a]aresample=48000,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"volume={max(0.0, min(1.0, float(background_gain))):.4f}[background];"
                "[narration][background]"
                "amix=inputs=2:duration=longest:dropout_transition=0,"
                f"{loudnorm},"
                "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
                "[audio_out]",
                "-map",
                "[audio_out]",
            ]
        )
    else:
        command.extend(["-map", "1:a:0?"])
        if abs(float(narration_atempo) - 1.0) > 1e-6:
            existing = next(
                (
                    str(audio_filter_args[index + 1])
                    for index, value in enumerate(audio_filter_args[:-1])
                    if str(value) == "-af"
                ),
                "",
            )
            chain = f"atempo={float(narration_atempo):.6f}"
            command.extend(["-af", f"{chain},{existing}" if existing else chain])
        else:
            command.extend([str(value) for value in audio_filter_args])
    command.extend([
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-t",
        f"{max(0.001, float(duration_seconds)):.6f}",
    ])
    color = dict(color_metadata or {})
    for key, flag in (
        ("color_range", "-color_range"),
        ("color_space", "-colorspace"),
        ("color_transfer", "-color_trc"),
        ("color_primaries", "-color_primaries"),
    ):
        value = str(color.get(key) or "").strip()
        if value:
            command.extend([flag, value])
    color_range = str(color.get("color_range") or "").strip().casefold()
    if color_range in {"tv", "limited", "mpeg"}:
        command.extend(["-bsf:v", "h264_metadata=video_full_range_flag=0"])
    elif color_range in {"pc", "full", "jpeg"}:
        command.extend(["-bsf:v", "h264_metadata=video_full_range_flag=1"])
    command.extend([
        "-movflags",
        "+faststart",
        str(output),
    ])
    return command


def execute_mux_with_fallback(
    *,
    video_only: Path,
    audio_source: Path,
    background_audio_source: Path | None,
    output: Path,
    duration_seconds: float,
    ffmpeg_binary: str,
    audio_filter_args: Sequence[str],
    background_gain: float,
    selected_encoder: str,
    selected_video_args: Sequence[str],
    selected_encoder_is_hardware: bool,
    hardware_fallback_enabled: bool,
    width: int,
    height: int,
    narration_atempo: float = 1.0,
    color_metadata: Mapping[str, Any] | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    attempts: list[dict[str, Any]] = []

    def attempt(encoder: str, video_args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        command = build_audio_mux_command(
            video_only=video_only,
            audio_source=audio_source,
            background_audio_source=background_audio_source,
            output=output,
            duration_seconds=duration_seconds,
            ffmpeg_binary=ffmpeg_binary,
            audio_filter_args=audio_filter_args,
            background_gain=background_gain,
            narration_atempo=narration_atempo,
            video_codec_args=video_args,
            color_metadata=color_metadata,
        )
        started = time.perf_counter()
        completed = run(command, capture_output=True, text=True, check=False)
        success = bool(
            completed.returncode == 0
            and output.is_file()
            and output.stat().st_size > 0
        )
        attempts.append(
            {
                "encoder": encoder,
                "return_code": int(completed.returncode),
                "elapsed_seconds": round(time.perf_counter() - started, 6),
                "success": success,
            }
        )
        return completed

    actual_encoder = str(selected_encoder)
    completed = attempt(actual_encoder, selected_video_args)
    fallback_used = False
    if (
        not attempts[-1]["success"]
        and selected_encoder_is_hardware
        and hardware_fallback_enabled
    ):
        fallback_used = True
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
        actual_encoder = SOFTWARE_ENCODER
        completed = attempt(
            actual_encoder,
            ffmpeg_video_encode_args(
                actual_encoder,
                width=width,
                height=height,
            ),
        )
    return completed, {
        "selected_encoder": actual_encoder,
        "runtime_fallback_used": fallback_used,
        "runtime_fallback_reason": (
            "hardware_final_encode_failed" if fallback_used else None
        ),
        "encode_attempts": attempts,
        "success": bool(attempts[-1]["success"]),
    }


def validate_narration_file_authority(
    narration_path: str | Path,
    contract: Mapping[str, Any],
) -> None:
    narration = Path(narration_path)
    audio = dict(dict(contract.get("authorities") or {}).get("audio") or {})
    narration_ref = dict(audio.get("narration_ref") or {})
    expected = str(narration_ref.get("sha256") or "").lower()
    if audio.get("status") != "READY" or len(expected) != 64:
        raise AdaptiveVideoRenderError("Approved narration hash authority is missing")
    if not narration.is_file():
        raise AdaptiveVideoRenderError("Approved narration file is missing")
    digest = hashlib.sha256()
    with narration.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise AdaptiveVideoRenderError("Narration file hash does not match audio authority")


def validate_background_file_authority(
    background_path: str | Path,
    contract: Mapping[str, Any],
) -> None:
    background = Path(background_path)
    audio = dict(dict(contract.get("authorities") or {}).get("audio") or {})
    background_ref = dict(audio.get("background_ref") or {})
    expected = str(background_ref.get("sha256") or "").lower()
    if len(expected) != 64 or not background.is_file():
        raise AdaptiveVideoRenderError("Approved background stem authority is missing")
    digest = hashlib.sha256()
    with background.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise AdaptiveVideoRenderError("Background stem hash does not match audio authority")


def remux_adaptive_preview_as_final(
    preview_video: str | Path,
    output_video: str | Path,
    *,
    contract: Mapping[str, Any],
    narration_path: str | Path,
    background_path: str | Path | None = None,
    expected_preview_sha256: str,
    ffmpeg_binary: str = "ffmpeg",
    qa_path: str | Path | None = None,
) -> AdaptiveVideoRenderResult:
    """Reuse an approved visual-preview bitstream and replace only its audio.

    The caller owns visual-QA authority validation.  This boundary still checks the
    exact preview file hash plus all approved audio hashes before invoking ffmpeg
    with ``-c:v copy``.  A final produced here therefore cannot drift visually from
    the operator-approved preview.
    """

    contract = enforce_unified_editor_cover_contract(contract)
    validate_adaptive_render_contract(contract, visual_preview=False)
    preview = Path(preview_video)
    output = Path(output_video)
    narration = Path(narration_path)
    background = Path(background_path) if background_path is not None else None
    expected_hash = str(expected_preview_sha256 or "").strip().lower()
    if not preview.is_file() or len(expected_hash) != 64:
        raise AdaptiveVideoRenderError("Approved visual preview authority is missing")
    digest = hashlib.sha256()
    with preview.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_hash:
        raise AdaptiveVideoRenderError("Visual preview hash does not match authority")
    validate_narration_file_authority(narration, contract)
    if background is not None:
        validate_background_file_authority(background, contract)

    video = dict(contract.get("video") or {})
    pts_map = dict(contract.get("pts_map") or {})
    timebase = dict(dict(contract.get("authorities") or {}).get("timebase") or {})
    frame_count = int(video.get("frame_count") or 0)
    # phase4_render_input_v1 uses frame_width/frame_height. Keep the aliases for
    # older pilot artifacts, but never require those legacy keys for preview
    # reuse.
    width = int(video.get("frame_width") or video.get("width") or 0)
    height = int(video.get("frame_height") or video.get("height") or 0)
    last_pts_seconds = float(pts_map.get("last_pts_seconds") or 0.0)
    fallback_last_duration = float(
        pts_map.get("fallback_last_duration_seconds") or 0.0
    )
    duration = last_pts_seconds + fallback_last_duration
    if duration <= 0:
        duration = float(video.get("duration_seconds") or 0.0)
    if duration <= 0 and str(timebase.get("mode") or "") == "CFR":
        nominal_fps = float(
            timebase.get("nominal_fps") or video.get("fps") or 0.0
        )
        if frame_count > 0 and nominal_fps > 0:
            duration = frame_count / nominal_fps
    if frame_count <= 0 or duration <= 0:
        raise AdaptiveVideoRenderError("Visual preview timebase authority is incomplete")
    if width <= 0 or height <= 0:
        raise AdaptiveVideoRenderError("Visual preview geometry authority is incomplete")

    try:
        if background is None:
            audio_filter_args = two_pass_loudness_filter_args(
                narration, ffmpeg_binary=ffmpeg_binary
            )
            normalization_mode = (
                "two_pass_loudnorm" if audio_filter_args else "disabled"
            )
        else:
            audio_filter_args = loudness_filter_args()
            normalization_mode = (
                "single_pass_post_mix_loudnorm" if audio_filter_args else "disabled"
            )
    except LoudnessMeasurementError as exc:
        raise AdaptiveVideoRenderError(str(exc)) from exc

    narration_duration_ms = probe_video_duration_ms(
        narration, ffmpeg_binary=ffmpeg_binary
    )
    if narration_duration_ms is None:
        raise AdaptiveVideoRenderError("Narration duration authority is unavailable")
    narration_duration_seconds = narration_duration_ms / 1000.0
    narration_atempo = resolve_narration_atempo(
        narration_duration_seconds, duration
    )
    background_gain = (
        resolve_background_gain(contract) if background is not None else 1.0
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    render_started = time.perf_counter()
    mux, mux_metadata = execute_mux_with_fallback(
        video_only=preview,
        audio_source=narration,
        background_audio_source=background,
        output=output,
        duration_seconds=duration,
        ffmpeg_binary=ffmpeg_binary,
        audio_filter_args=audio_filter_args,
        background_gain=background_gain,
        selected_encoder="stream_copy",
        selected_video_args=["-c:v", "copy"],
        selected_encoder_is_hardware=False,
        hardware_fallback_enabled=False,
        width=width,
        height=height,
        narration_atempo=narration_atempo,
        # The approved preview already carries the color authority.  Reapplying
        # h264_metadata here would mutate the copied packet stream.
        color_metadata={},
    )
    if not mux_metadata["success"]:
        detail = " ".join(str(mux.stderr or mux.stdout or "").split())[-300:]
        raise AdaptiveVideoRenderError(
            f"Final audio remux failed: {detail or 'ffmpeg_failed'}"
        )
    resolved_qa_path = Path(qa_path) if qa_path is not None else output.with_suffix(".qa.json")
    encoder_metadata = {
        **mux_metadata,
        "selected_encoder": "stream_copy",
        "hardware": False,
        "visual_authority_reused": True,
        "visual_authority_sha256": expected_hash,
        "ffmpeg_version": ffmpeg_runtime_version(ffmpeg_binary),
        "total_render_seconds": round(time.perf_counter() - render_started, 6),
    }
    audio_mix_metadata = {
        "strategy": (
            "narration_with_background_stem"
            if background is not None
            else "narration_only"
        ),
        "normalization_mode": normalization_mode,
        "background_present": background is not None,
        "background_gain": round(float(background_gain), 6) if background is not None else None,
        "narration_duration_seconds": narration_duration_seconds,
        "narration_atempo": round(float(narration_atempo), 6),
        "narration_fitted_duration_seconds": round(
            narration_duration_seconds / narration_atempo, 6
        ),
        "narration_complete": (
            narration_duration_seconds / narration_atempo <= duration + 0.01
        ),
    }
    _write_json_atomic(
        resolved_qa_path,
        {
            "schema_version": "phase4_visual_authority_remux_v1",
            "preview_sha256": expected_hash,
            "video_codec": "copy",
            "frame_count": frame_count,
            "audio_mix": audio_mix_metadata,
        },
    )
    return AdaptiveVideoRenderResult(
        output_path=output,
        frame_count=frame_count,
        qa_path=resolved_qa_path,
        visual_preview=False,
        encoder_metadata=encoder_metadata,
        audio_mix_metadata=audio_mix_metadata,
    )


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _reference_candidate(
    capture: Any,
    track: Mapping[str, Any],
    *,
    current: np.ndarray,
    frame_count: int,
    fps: float,
) -> np.ndarray | None:
    import cv2

    start = int(track.get("start_frame") or 0)
    end = int(track.get("end_frame") or start)
    offsets = {
        1,
        max(1, int(round(fps * 0.10))),
        max(1, int(round(fps * 0.25))),
        max(1, int(round(fps * 0.50))),
    }
    policy = dict(track.get("render_policy") or {})
    roi = dict(dict(policy.get("cover") or {}).get("roi") or {})
    height, width = current.shape[:2]
    x0 = max(0, int(round(float(roi.get("x") or 0.0) * width)))
    y0 = max(0, int(round(float(roi.get("y") or 0.0) * height)))
    x1 = min(
        width,
        int(
            round(
                (float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0))
                * width
            )
        ),
    )
    y1 = min(
        height,
        int(
            round(
                (float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0))
                * height
            )
        ),
    )
    outside = np.ones((height, width), dtype=bool)
    outside[y0:y1, x0:x1] = False
    inside = ~outside
    if x1 <= x0 or y1 <= y0:
        return None
    current_gray = cv2.cvtColor(current[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    current_textness = local_textness_mask(current_gray)
    current_textness_fraction = float(
        np.count_nonzero(current_textness) / max(1, current_textness.size)
    )
    candidates: list[tuple[float, np.ndarray]] = []
    for offset in sorted(offsets):
        for index in (start - offset, end + offset):
            if not (0 <= index < frame_count):
                continue
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, candidate = capture.read()
            if not ok or candidate is None or candidate.shape != current.shape:
                continue
            outside_mad = float(
                np.abs(
                    candidate[outside].astype(np.float32)
                    - current[outside].astype(np.float32)
                ).mean()
            )
            inside_mad = float(
                np.abs(
                    candidate[inside].astype(np.float32)
                    - current[inside].astype(np.float32)
                ).mean()
            )
            if not is_usable_reference_plate_candidate(
                outside_mad=outside_mad,
                inside_mad=inside_mad,
            ):
                continue
            candidate_gray = cv2.cvtColor(
                candidate[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY
            )
            candidate_textness = local_textness_mask(candidate_gray)
            candidate_textness_fraction = float(
                np.count_nonzero(candidate_textness)
                / max(1, candidate_textness.size)
            )
            if not is_text_reduced_reference_candidate(
                current_textness_fraction=current_textness_fraction,
                candidate_textness_fraction=candidate_textness_fraction,
            ):
                continue
            score = reference_plate_candidate_score(
                outside_mad=outside_mad,
                inside_mad=inside_mad,
            )
            candidates.append((score, candidate))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def should_seed_reference_plate(track: Mapping[str, Any]) -> bool:
    """Avoid an unalignable clean plate for a very short opening overlay."""
    policy = dict(track.get("render_policy") or {})
    mask_mode = str(dict(policy.get("cover") or {}).get("mask_mode") or "")
    cover = dict(policy.get("cover") or {})
    has_soft_epoch = bool(cover.get("soft_cover_epoch_id"))
    if mask_mode != "stylized_components" and not has_soft_epoch:
        return False
    context = dict(policy.get("context") or {})
    if has_soft_epoch and mask_mode == "full_roi_plate":
        # A neighboring subtitle frame is different inside the ROI but is not
        # necessarily clean. Automatic temporal plates can therefore preserve
        # or copy CJK under the Vietnamese text. Full-ROI caption removal uses
        # deterministic blur unless an operator explicitly approved a bound
        # reference plate for this track.
        return bool(context.get("reference_plate_operator_approved"))
    start = int(track.get("start_frame") or 0)
    end = int(track.get("end_frame") or start)
    span_frames = max(1, end - start + 1)
    return not (start <= 1 and span_frames <= 6) or bool(
        context.get("short_intro_reference_plate_approved")
    )


def _seed_reference_plates(
    source: Path,
    contract: Mapping[str, Any],
    renderer: AdaptiveFrameRenderer,
) -> int:
    import cv2

    video = dict(contract.get("video") or {})
    frame_count = int(video.get("frame_count") or 0)
    fps = float(video.get("fps") or 30.0)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise AdaptiveVideoRenderError("Cannot open source for reference plate selection")
    seeded = 0
    try:
        for track in list(contract.get("render_tracks") or []):
            if not isinstance(track, Mapping):
                continue
            if not should_seed_reference_plate(track):
                continue
            start = int(track.get("start_frame") or 0)
            capture.set(cv2.CAP_PROP_POS_FRAMES, start)
            ok, current = capture.read()
            if not ok or current is None:
                continue
            reference = _reference_candidate(
                capture,
                track,
                current=current,
                frame_count=frame_count,
                fps=fps,
            )
            context = dict(dict(track.get("render_policy") or {}).get("context") or {})
            if reference is None and bool(
                context.get("short_intro_full_frame_clean_plate_approved")
            ):
                clean_index = min(
                    max(0, frame_count - 1), int(track.get("end_frame") or start) + 1
                )
                capture.set(cv2.CAP_PROP_POS_FRAMES, clean_index)
                clean_ok, clean_frame = capture.read()
                if clean_ok and clean_frame is not None and clean_frame.shape == current.shape:
                    reference = clean_frame
            if reference is not None:
                renderer.seed_reference(str(track.get("text_id") or ""), reference)
                seeded += 1
    finally:
        capture.release()
    return seeded


def _seed_representative_masks(
    source: Path,
    contract: Mapping[str, Any],
    renderer: AdaptiveFrameRenderer,
) -> int:
    """Union start/middle/end glyph evidence before the first encoded frame."""
    import cv2

    video = dict(contract.get("video") or {})
    frame_count = int(video.get("frame_count") or 0)
    tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    samples: dict[int, list[dict[str, Any]]] = {}
    for track in tracks:
        start = max(0, min(frame_count - 1, int(track.get("start_frame") or 0)))
        end = max(start, min(frame_count - 1, int(track.get("end_frame") or start)))
        for index in {start, (start + end) // 2, end}:
            samples.setdefault(index, []).append(track)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise AdaptiveVideoRenderError("Cannot open source for representative masks")
    masks: dict[str, np.ndarray] = {}
    try:
        for index, active in sorted(samples.items()):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            for track in active:
                text_id = str(track.get("text_id") or "")
                observed = renderer.mask_builder(frame, track)
                if int(np.count_nonzero(observed)) == 0:
                    continue
                previous = masks.get(text_id)
                masks[text_id] = (
                    observed.copy()
                    if previous is None
                    else cv2.bitwise_or(previous, observed)
                )
    finally:
        capture.release()
    for text_id, mask in masks.items():
        renderer.seed_mask(text_id, mask)
    return len(masks)


def _seed_dense_ui_panels(
    source: Path,
    contract: Mapping[str, Any],
    renderer: AdaptiveFrameRenderer,
) -> int:
    """Use the first approved epoch frame to derive a stable source-aware plate."""
    import cv2

    panels = [
        dict(row)
        for row in list(contract.get("dense_ui_panels") or [])
        if isinstance(row, Mapping)
    ]
    if not panels:
        return 0
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise AdaptiveVideoRenderError("Cannot open source for dense UI panel plate")
    colors: dict[str, list[int]] = {}
    try:
        for panel in panels:
            panel_id = str(panel.get("panel_id") or "")
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(panel.get("start_frame") or 0))
            ok, frame = capture.read()
            if not ok or frame is None:
                raise AdaptiveVideoRenderError(
                    f"Cannot read dense UI panel reference frame: {panel_id}"
                )
            height, width = frame.shape[:2]
            roi = dict(panel.get("panel_roi") or {})
            x0 = max(0, min(width, int(round(float(roi.get("x") or 0.0) * width))))
            y0 = max(0, min(height, int(round(float(roi.get("y") or 0.0) * height))))
            x1 = max(x0, min(width, int(round((float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0)) * width))))
            y1 = max(y0, min(height, int(round((float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0)) * height))))
            if not panel_id or x1 <= x0 or y1 <= y0:
                raise AdaptiveVideoRenderError("Dense UI panel has invalid plate ROI")
            colors[panel_id] = [
                int(value)
                for value in np.median(frame[y0:y1, x0:x1], axis=(0, 1)).round()
            ]
    finally:
        capture.release()
    renderer.seed_dense_ui_panels(
        panels,
        list(contract.get("render_tracks") or []),
        plate_colors=colors,
    )
    return len(colors)


def _copy_color_authority(input_stream: Any, output_stream: Any) -> None:
    for attribute in ("color_range", "colorspace", "color_trc", "color_primaries"):
        try:
            value = getattr(input_stream.codec_context, attribute)
            if value is not None:
                setattr(output_stream.codec_context, attribute, value)
        except (AttributeError, TypeError, ValueError):
            continue


def render_adaptive_video(
    source_video: str | Path,
    output_video: str | Path,
    *,
    contract: Mapping[str, Any],
    visual_preview: bool,
    narration_path: str | Path | None = None,
    background_path: str | Path | None = None,
    ffmpeg_binary: str = "ffmpeg",
    qa_path: str | Path | None = None,
    progress: Callable[[int, int], None] | None = None,
    video_encoder_policy: str = "auto",
    hardware_smoke_probe: bool = True,
    hardware_fallback_enabled: bool = True,
) -> AdaptiveVideoRenderResult:
    import av

    contract = enforce_unified_editor_cover_contract(contract)
    validate_adaptive_render_contract(contract, visual_preview=visual_preview)
    source = Path(source_video)
    output = Path(output_video)
    if not source.is_file():
        raise AdaptiveVideoRenderError("Source video is missing")
    audio_source = source if visual_preview else Path(str(narration_path or ""))
    if not audio_source.is_file():
        raise AdaptiveVideoRenderError("Approved audio source is missing")
    if not visual_preview:
        validate_narration_file_authority(audio_source, contract)
    background_source = Path(str(background_path or "")) if background_path else None
    if not visual_preview and background_source is not None:
        validate_background_file_authority(background_source, contract)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        encoder_selection = select_video_encoder(
            video_encoder_policy,
            probe=lambda encoder: probe_ffmpeg_encoder(
                encoder,
                ffmpeg_binary=ffmpeg_binary,
                smoke_encode=bool(hardware_smoke_probe),
            ),
        )
    except RuntimeError as exc:
        raise AdaptiveVideoRenderError(str(exc)) from exc
    use_lossless_intermediate = encoder_selection.hardware
    video_only = output.with_suffix(
        ".video-only.mkv" if use_lossless_intermediate else ".video-only.mp4"
    )
    render_started = time.perf_counter()
    renderer = AdaptiveFrameRenderer()
    seeded = _seed_reference_plates(source, contract, renderer)
    masks_seeded = _seed_representative_masks(source, contract, renderer)
    panels_seeded = _seed_dense_ui_panels(source, contract, renderer)
    expected_frames = int(dict(contract.get("video") or {}).get("frame_count") or 0)
    qa_tracks: dict[str, dict[str, Any]] = {}
    qa_panels: dict[str, dict[str, Any]] = {}
    decoded_frames = 0

    input_container = av.open(str(source))
    input_stream = input_container.streams.video[0]
    output_container = av.open(str(video_only), mode="w")
    rate = input_stream.average_rate or input_stream.base_rate or 30
    intermediate_codec = "ffv1" if use_lossless_intermediate else SOFTWARE_ENCODER
    output_stream = output_container.add_stream(
        intermediate_codec,
        rate=rate,
        options=(
            {}
            if use_lossless_intermediate
            else {"crf": "20", "preset": "veryfast"}
        ),
    )
    frame_width = int(input_stream.codec_context.width)
    frame_height = int(input_stream.codec_context.height)
    renderer.seed_dense_layout_authority(
        list(contract.get("render_tracks") or [])
    )
    renderer.seed_cover_component_authority(
        list(contract.get("render_tracks") or [])
    )
    output_stream.width = frame_width
    output_stream.height = frame_height
    output_stream.pix_fmt = "yuv420p"
    try:
        output_stream.time_base = input_stream.time_base
    except (AttributeError, TypeError, ValueError):
        pass
    _copy_color_authority(input_stream, output_stream)
    try:
        for frame_index, frame in enumerate(input_container.decode(input_stream)):
            source_bgr = frame.to_ndarray(format="bgr24")
            active = active_tracks_for_frame(
                contract,
                frame_index,
                source_frame_bgr=source_bgr,
            )
            active_panels = active_dense_ui_panels_for_frame(contract, frame_index)
            protected_regions = active_protected_source_regions_for_frame(
                contract, frame_index
            )
            if active or active_panels:
                try:
                    rendered_bgr, frame_qa = renderer.render_frame(
                        source_bgr,
                        active,
                        frame_index=frame_index,
                        protected_source_regions=protected_regions,
                    )
                except AdaptiveRenderBlocked as exc:
                    raise AdaptiveVideoRenderError(
                        f"Adaptive frame blocked at index {frame_index}: {exc}",
                        diagnostics={
                            "frame_index": frame_index,
                            **dict(exc.diagnostics or {}),
                        },
                    ) from exc
                for item in list(frame_qa.get("tracks") or []):
                    text_id = str(item.get("text_id") or "")
                    aggregate = qa_tracks.setdefault(
                        text_id,
                        {
                            "frames": 0,
                            "temporal_modes": {},
                            "max_mask_frame_fraction": 0.0,
                            "max_changed_fraction": 0.0,
                            "max_boundary_seam_score": 0.0,
                            "max_temporal_flicker_score": 0.0,
                            "max_plate_uniformity_score": 0.0,
                            "max_background_color_drift": 0.0,
                            "aesthetic_warning_frames": 0,
                        },
                    )
                    aggregate["frames"] += 1
                    mode = str(dict(item.get("temporal") or {}).get("mode") or "unknown")
                    aggregate["temporal_modes"][mode] = (
                        int(aggregate["temporal_modes"].get(mode, 0)) + 1
                    )
                    aggregate["max_mask_frame_fraction"] = max(
                        float(aggregate["max_mask_frame_fraction"]),
                        float(
                            dict(dict(item.get("mask") or {}).get("metrics") or {}).get(
                                "frame_fraction"
                            )
                            or 0.0
                        ),
                    )
                    aggregate["max_changed_fraction"] = max(
                        float(aggregate["max_changed_fraction"]),
                        float(
                            dict(dict(item.get("damage") or {}).get("metrics") or {}).get(
                                "changed_fraction"
                            )
                            or 0.0
                        ),
                    )
                    aesthetic = dict(
                        dict(item.get("temporal") or {}).get("aesthetic_qa")
                        or {}
                    )
                    for key in (
                        "boundary_seam_score",
                        "temporal_flicker_score",
                        "plate_uniformity_score",
                        "background_color_drift",
                    ):
                        aggregate[f"max_{key}"] = max(
                            float(aggregate.get(f"max_{key}") or 0.0),
                            float(aesthetic.get(key) or 0.0),
                        )
                    if str(aesthetic.get("status") or "PASS") != "PASS":
                        aggregate["aesthetic_warning_frames"] = int(
                            aggregate.get("aesthetic_warning_frames") or 0
                        ) + 1
                for item in list(frame_qa.get("dense_ui_panels") or []):
                    panel_id = str(item.get("panel_id") or "")
                    aggregate = qa_panels.setdefault(
                        panel_id,
                        {
                            "frames": 0,
                            "panel_roi": item.get("panel_roi"),
                            "plate_bgr": item.get("plate_bgr"),
                            "max_changed_fraction": 0.0,
                            "max_frame_change_fraction": item.get("max_frame_change_fraction"),
                            "rendered_lines": item.get("layouts"),
                        },
                    )
                    aggregate["frames"] += 1
                    aggregate["max_changed_fraction"] = max(
                        float(aggregate["max_changed_fraction"]),
                        float(item.get("changed_fraction") or 0.0),
                    )
            else:
                rendered_bgr = source_bgr
            output_frame = av.VideoFrame.from_ndarray(rendered_bgr, format="bgr24")
            output_frame.pts = frame.pts
            output_frame.time_base = frame.time_base
            for packet in output_stream.encode(output_frame):
                output_container.mux(packet)
            decoded_frames += 1
            if progress is not None:
                progress(decoded_frames, expected_frames)
        for packet in output_stream.encode():
            output_container.mux(packet)
    finally:
        input_container.close()
        output_container.close()
    if decoded_frames != expected_frames:
        raise AdaptiveVideoRenderError(
            f"Decoded frame count mismatch ({decoded_frames} != {expected_frames})"
        )

    duration = float(
        dict(contract.get("pts_map") or {}).get("last_pts_seconds")
        or (decoded_frames / max(1.0, float(rate)))
    )
    duration += float(
        dict(contract.get("pts_map") or {}).get("fallback_last_duration_seconds")
        or 0.0
    )
    width = frame_width
    height = frame_height
    selected_encoder = encoder_selection.selected_encoder
    selected_video_args = (
        ffmpeg_video_encode_args(selected_encoder, width=width, height=height)
        if use_lossless_intermediate
        else ["-c:v", "copy"]
    )
    normalization_mode = "disabled_for_visual_preview"
    audio_filter_args: Sequence[str] = []
    if not visual_preview:
        try:
            if background_source is None:
                audio_filter_args = two_pass_loudness_filter_args(
                    audio_source,
                    ffmpeg_binary=ffmpeg_binary,
                )
                normalization_mode = (
                    "two_pass_loudnorm" if audio_filter_args else "disabled"
                )
            else:
                audio_filter_args = loudness_filter_args()
                normalization_mode = (
                    "single_pass_post_mix_loudnorm"
                    if audio_filter_args
                    else "disabled"
                )
        except LoudnessMeasurementError as exc:
            raise AdaptiveVideoRenderError(str(exc)) from exc
    authority_color = dict(
        dict(contract.get("authorities") or {}).get("color") or {}
    )
    authority_audio = dict(dict(contract.get("authorities") or {}).get("audio") or {})
    resolved_background_gain = (
        resolve_background_gain(contract) if background_source is not None else None
    )
    narration_duration_seconds: float | None = None
    narration_atempo = 1.0
    if not visual_preview:
        narration_duration_ms = probe_video_duration_ms(
            audio_source, ffmpeg_binary=ffmpeg_binary
        )
        if narration_duration_ms is None:
            raise AdaptiveVideoRenderError("Narration duration authority is unavailable")
        narration_duration_seconds = narration_duration_ms / 1000.0
        # Even a sub-1% overrun must be fitted: muxing with ``-t`` otherwise
        # truncates the final syllable while the metadata reports an incomplete
        # narration.  Keep a tiny epsilon to avoid needless atempo for probe
        # rounding noise.
        narration_atempo = resolve_narration_atempo(
            narration_duration_seconds,
            duration,
        )
    mux, mux_metadata = execute_mux_with_fallback(
        video_only=video_only,
        audio_source=audio_source,
        background_audio_source=(None if visual_preview else background_source),
        output=output,
        duration_seconds=duration,
        ffmpeg_binary=ffmpeg_binary,
        audio_filter_args=audio_filter_args,
        background_gain=(
            resolved_background_gain
            if resolved_background_gain is not None
            else float(background_mix_gain())
        ),
        selected_encoder=selected_encoder,
        selected_video_args=selected_video_args,
        selected_encoder_is_hardware=encoder_selection.hardware,
        hardware_fallback_enabled=hardware_fallback_enabled,
        width=width,
        height=height,
        narration_atempo=narration_atempo,
        color_metadata=authority_color,
    )
    if not mux_metadata["success"]:
        detail = " ".join(str(mux.stderr or mux.stdout or "").split())[-300:]
        raise AdaptiveVideoRenderError(
            f"Audio/video encode failed for adaptive render: {detail or 'ffmpeg_failed'}"
        )
    encoder_metadata = {
        **encoder_selection.to_dict(),
        "probe_selected_encoder": encoder_selection.selected_encoder,
        **mux_metadata,
        "hardware": mux_metadata["selected_encoder"] != SOFTWARE_ENCODER,
        "intermediate_codec": intermediate_codec,
        "ffmpeg_version": ffmpeg_runtime_version(ffmpeg_binary),
        "total_render_seconds": round(time.perf_counter() - render_started, 6),
    }
    audio_mix_metadata = {
        "strategy": (
            "source_audio_preview"
            if visual_preview
            else str(authority_audio.get("strategy") or "")
            if str(authority_audio.get("strategy") or "")
            else "narration_with_background_stem"
            if background_source is not None
            else "narration_only"
        ),
        "normalization_mode": normalization_mode,
        "background_present": bool(not visual_preview and background_source is not None),
        "background_gain": (
            round(float(resolved_background_gain), 6)
            if not visual_preview and background_source is not None
            else None
        ),
        "narration_duration_seconds": narration_duration_seconds,
        "narration_atempo": round(float(narration_atempo), 6),
        "narration_fitted_duration_seconds": (
            round(narration_duration_seconds / narration_atempo, 6)
            if narration_duration_seconds is not None
            else None
        ),
        "narration_complete": bool(
            visual_preview
            or narration_duration_seconds is not None
            and narration_duration_seconds / narration_atempo <= duration + 0.01
        ),
    }
    try:
        video_only.unlink(missing_ok=True)
    except OSError:
        pass
    resolved_qa_path = Path(qa_path) if qa_path is not None else output.with_suffix(".qa.json")
    _write_json_atomic(
        resolved_qa_path,
        {
            "schema_version": "phase4_adaptive_render_qa_v1",
            "status": "PASS",
            "visual_preview": bool(visual_preview),
            "frames": decoded_frames,
            "reference_plates_seeded": seeded,
            "representative_masks_seeded": masks_seeded,
            "dense_ui_panels_seeded": panels_seeded,
            "encoder": encoder_metadata,
            "audio_mix": audio_mix_metadata,
            "tracks": qa_tracks,
            "soft_cover_epochs": list(contract.get("soft_cover_epochs") or []),
            "dense_ui_panels": qa_panels,
        },
    )
    return AdaptiveVideoRenderResult(
        output_path=output.resolve(),
        frame_count=decoded_frames,
        qa_path=resolved_qa_path.resolve(),
        visual_preview=bool(visual_preview),
        encoder_metadata=encoder_metadata,
        audio_mix_metadata=audio_mix_metadata,
    )
