"""Fail-closed bridge from approved Phase 2+3 artifacts to Phase 4 render tracks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.media_pipeline.video_renderer.fonts import resolve_drawtext_font
from src.media_pipeline.video_renderer.overlays import OverlaySegment, gate_vi_for_burn
from src.media_pipeline.video_renderer.render_policy import enrich_phase4_render_policies
from src.media_pipeline.video_renderer.render_policy import select_text_render_tracks
from src.media_pipeline.video_renderer.render_runtime import (
    ViGlyphCache,
    plan_vi_placements,
    resolve_vi_font_size_for_kind,
)

PHASE4_INPUT_SCHEMA_VERSION = "phase4_render_input_v1"
PHASE4_PREFLIGHT_SCHEMA_VERSION = "phase4_render_preflight_v1"
PHASE4_TIMING_NORMALIZATION_POLICY_VERSION = "transition_boundary_v2"


class Phase4InputError(RuntimeError):
    """Approved artifacts cannot be mapped safely into render tracks."""


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


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4InputError(f"Cannot read valid {path.name}") from exc


def _mapping_by_id(
    rows: Sequence[Any], *, key: str, label: str
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise Phase4InputError(f"{label} contains an invalid row")
        row = dict(raw)
        item_id = str(row.get(key) or "").strip()
        if not item_id or item_id in output:
            raise Phase4InputError(f"{label} contains a missing or duplicate {key}")
        output[item_id] = row
    return output


def _kind_for_roles(roles: Sequence[Any]) -> str:
    normalized = {str(role or "").strip().lower() for role in roles}
    # OCR can add a hardsub role to a compact app label near the lower edge.
    # Keep explicit UI chips anchored to their source widget instead of moving
    # them into the shared bottom-subtitle band.
    if "ui_chip" in normalized:
        return "ui"
    if "hardsub" in normalized:
        return "hardsub"
    if "title" in normalized:
        return "title"
    return "ui"


def _frame_ms(frame_index: int, fps: float) -> int:
    return int(round(float(frame_index) * 1000.0 / float(fps)))


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


def _normalize_shared_caption_boundaries(
    tracks: list[dict[str, Any]], *, fps: float
) -> int:
    """Assign short same-region transitions to the incoming text track."""
    adjusted = 0
    for current, following in zip(tracks, tracks[1:]):
        current_kind = str(current.get("kind") or "")
        following_kind = str(following.get("kind") or "")
        current_end = int(current.get("end_frame") or 0)
        following_start = int(following.get("start_frame") or 0)
        overlap_frames = current_end - following_start + 1
        shared_hardsub_boundary = (
            current_kind == "hardsub"
            and following_kind == "hardsub"
            and overlap_frames == 1
        )
        short_ui_transition = (
            current_kind == "ui"
            and following_kind == "ui"
            and 1 <= overlap_frames <= 6
        )
        if (
            not (shared_hardsub_boundary or short_ui_transition)
            or str(current.get("content_id") or "")
            == str(following.get("content_id") or "")
            or int(current.get("start_frame") or 0)
            >= following_start
            or _geometry_overlap_over_smaller(
                dict(current.get("geometry") or {}),
                dict(following.get("geometry") or {}),
            )
            < 0.35
        ):
            continue
        shared_frame = following_start
        current["nominal_end_frame"] = int(current["end_frame"])
        current["end_frame"] = shared_frame - 1
        current["end_ms"] = _frame_ms(shared_frame, fps)
        current["timing_adjustment"] = {
            "policy_version": PHASE4_TIMING_NORMALIZATION_POLICY_VERSION,
            "reason": (
                "short_ui_transition_assigned_to_incoming_track"
                if short_ui_transition
                else "shared_transition_frame_assigned_to_incoming_caption"
            ),
            "frames_trimmed": overlap_frames,
        }
        adjusted += 1
    return adjusted


def _suppress_weak_caption_fragments(tracks: list[dict[str, Any]]) -> int:
    """Keep OCR-empty transition fragments as cover-only geometry.

    The guard is deliberately narrow: the fragment must be a tiny, short
    hardsub with an operator EDIT but no OCR candidate, and it must sit beside
    a larger hardsub in the same temporal/lane neighborhood. This prevents a
    guessed sentence from being burned over a partial transition crop while
    preserving the geometry needed to remove the source glyph fragment.
    """

    suppressed = 0
    for track in tracks:
        if (
            not bool(track.pop("weak_ocr_fragment_candidate", False))
            or str(track.get("kind") or "") != "hardsub"
            or bool(track.get("cover_only"))
        ):
            continue
        start = int(track.get("start_frame") or 0)
        end = int(track.get("end_frame") or start)
        geometry = dict(track.get("geometry") or {})
        area = float(geometry.get("width") or 0.0) * float(
            geometry.get("height") or 0.0
        )
        if end - start + 1 > 6 or area > 0.003:
            continue
        x0 = float(geometry.get("x") or 0.0)
        y0 = float(geometry.get("y") or 0.0)
        x1 = x0 + float(geometry.get("width") or 0.0)
        y1 = y0 + float(geometry.get("height") or 0.0)
        parent: dict[str, Any] | None = None
        for candidate in tracks:
            if candidate is track or str(candidate.get("kind") or "") != "hardsub":
                continue
            candidate_start = int(candidate.get("start_frame") or 0)
            candidate_end = int(candidate.get("end_frame") or candidate_start)
            overlap_frames = max(
                0, min(end, candidate_end) - max(start, candidate_start) + 1
            )
            if overlap_frames < max(1, (end - start + 1) // 2):
                continue
            other = dict(candidate.get("geometry") or {})
            other_area = float(other.get("width") or 0.0) * float(
                other.get("height") or 0.0
            )
            if other_area < area * 1.5:
                continue
            ox0 = float(other.get("x") or 0.0)
            oy0 = float(other.get("y") or 0.0)
            ox1 = ox0 + float(other.get("width") or 0.0)
            oy1 = oy0 + float(other.get("height") or 0.0)
            vertical_intersection = max(0.0, min(y1, oy1) - max(y0, oy0))
            vertical_smaller = min(max(0.0, y1 - y0), max(0.0, oy1 - oy0))
            vertical_gap = max(0.0, oy0 - y1, y0 - oy1)
            horizontal_gap = max(0.0, ox0 - x1, x0 - ox1)
            if (
                vertical_smaller > 0.0
                and (
                    vertical_intersection / vertical_smaller >= 0.10
                    or vertical_gap <= 0.04
                )
                and horizontal_gap <= 0.05
            ):
                parent = candidate
                break
        if parent is None:
            continue
        track["text_vi"] = ""
        track["cover_only"] = True
        track["translation_status"] = "COVER_ONLY_WEAK_OCR_FRAGMENT"
        track["weak_fragment_suppression"] = {
            "policy_version": "weak_hardsub_fragment_guard_v1",
            "parent_text_id": parent.get("text_id"),
            "reason": "ocr_empty_short_adjacent_caption_fragment",
        }
        suppressed += 1
    return suppressed


def build_phase4_render_input(
    master_timeline: Sequence[Mapping[str, Any]],
    phase2_timeline: Mapping[str, Any],
    phase3_render_handoff: Mapping[str, Any],
    *,
    video_metadata: Mapping[str, Any],
    refs: Mapping[str, Any],
    cover_only_refs: Sequence[str] = (),
    protected_source_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Join by exact ``text_id``; timestamp/fuzzy lookup is intentionally forbidden."""
    if str(phase3_render_handoff.get("status") or "") != "READY_FOR_RENDER":
        raise Phase4InputError("Phase 3 render handoff is not READY_FOR_RENDER")

    frame_width = int(video_metadata.get("frame_width") or 0)
    frame_height = int(video_metadata.get("frame_height") or 0)
    frame_count = int(video_metadata.get("frame_count") or 0)
    fps = float(video_metadata.get("fps") or 0.0)
    if frame_width < 2 or frame_height < 2 or frame_count < 1 or fps <= 0:
        raise Phase4InputError("Invalid video metadata for Phase 4")

    master = _mapping_by_id(
        list(master_timeline), key="text_id", label="master_timeline"
    )
    enrichments = _mapping_by_id(
        list(phase2_timeline.get("track_enrichments") or []),
        key="text_id",
        label="phase2 track_enrichments",
    )
    content = _mapping_by_id(
        list(phase2_timeline.get("content_objects") or []),
        key="content_id",
        label="phase2 content_objects",
    )
    raw_geometry = phase3_render_handoff.get("geometry_map")
    if not isinstance(raw_geometry, Mapping):
        raise Phase4InputError("Phase 3 handoff geometry_map must be an object")
    geometry = {
        str(text_id): dict(value)
        for text_id, value in raw_geometry.items()
        if isinstance(value, Mapping)
    }
    if len(geometry) != len(raw_geometry):
        raise Phase4InputError("Phase 3 handoff contains invalid geometry rows")

    cover_ids = {str(value) for value in cover_only_refs if str(value)}
    protected_ids = {str(value) for value in protected_source_refs if str(value)}
    expected_ids = set(geometry) | cover_ids | protected_ids
    if set(master) != expected_ids:
        raise Phase4InputError(
            "Render geometry set mismatch "
            f"(master={len(master)}, translated={len(geometry)}, "
            f"cover_only={len(cover_ids)}, protected_source={len(protected_ids)})"
        )
    if not set(geometry).issubset(enrichments):
        raise Phase4InputError("Phase 2 enrichment is missing translated text_id rows")

    render_tracks: list[dict[str, Any]] = []
    protected_source_tracks: list[dict[str, Any]] = []
    for text_id, master_row in master.items():
        start_frame = int(master_row.get("start_frame") or 0)
        end_frame = int(master_row.get("end_frame") or start_frame)
        raw_best_frame = master_row.get("best_frame_index")
        best_frame_index = (
            int(raw_best_frame)
            if raw_best_frame is not None
            else (start_frame + end_frame) // 2
        )
        if not start_frame <= best_frame_index <= end_frame:
            best_frame_index = (start_frame + end_frame) // 2
        coords = list(master_row.get("box_coords") or [])
        if (
            len(coords) != 4
            or start_frame < 0
            or end_frame < start_frame
            or end_frame >= frame_count
        ):
            raise Phase4InputError(f"Invalid timing/geometry for {text_id}")
        x0, y0, x1, y1 = (float(coords[index]) for index in range(4))
        if (
            x0 < 0
            or y0 < 0
            or x1 <= x0
            or y1 <= y0
            or x1 > frame_width
            or y1 > frame_height
        ):
            raise Phase4InputError(f"Out-of-frame geometry for {text_id}")

        if text_id in protected_ids:
            protected_source_tracks.append(
                {
                    "text_id": text_id,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "geometry": {
                        "x": x0 / frame_width,
                        "y": y0 / frame_height,
                        "width": (x1 - x0) / frame_width,
                        "height": (y1 - y0) / frame_height,
                    },
                    "classification": "SOURCE_INTRINSIC",
                    "action": "PRESERVE_SOURCE_PIXELS",
                    "visual_provenance": dict(
                        master_row.get("visual_provenance") or {}
                    ),
                }
            )
            continue

        is_cover_only = text_id in cover_ids
        text_vi = ""
        content_id: str | None = None
        roles: list[str] = []
        translation_status = "COVER_ONLY"
        if not is_cover_only:
            phase3_row = geometry[text_id]
            enrichment = enrichments[text_id]
            content_id = str(phase3_row.get("content_id") or "").strip()
            if content_id != str(enrichment.get("content_id") or "").strip():
                raise Phase4InputError(f"Content mapping mismatch for {text_id}")
            content_row = content.get(content_id)
            if content_row is None:
                raise Phase4InputError(f"Missing Phase 2 content object for {text_id}")
            roles = [str(role) for role in list(content_row.get("roles") or [])]
            duplicate_transition_canonical = bool(
                content_row.get("duplicate_transition_canonicalization")
            )
            translation_status = str(phase3_row.get("translation_status") or "")
            if translation_status not in {
                "TRANSLATION_APPROVED",
                "TRANSLATION_DETERMINISTIC",
            }:
                raise Phase4InputError(f"Unapproved translation for {text_id}")
            raw_text = str(phase3_row.get("text_vi") or "").strip()
            text_vi = gate_vi_for_burn(raw_text)
            if not text_vi or text_vi != raw_text:
                raise Phase4InputError(f"Unsafe or empty Vietnamese text for {text_id}")

        render_tracks.append(
            {
                "text_id": text_id,
                "content_id": content_id,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "best_frame_index": best_frame_index,
                "start_ms": _frame_ms(start_frame, fps),
                "end_ms": _frame_ms(end_frame + 1, fps),
                "geometry": {
                    "x": x0 / frame_width,
                    "y": y0 / frame_height,
                    "width": (x1 - x0) / frame_width,
                    "height": (y1 - y0) / frame_height,
                },
                "roles": roles,
                "kind": "ui" if is_cover_only else _kind_for_roles(roles),
                "text_vi": text_vi,
                "translation_status": translation_status,
                "cover_only": is_cover_only,
                "duplicate_transition_canonical": (
                    duplicate_transition_canonical if not is_cover_only else False
                ),
                "weak_ocr_fragment_candidate": bool(
                    not list(content_row.get("ocr_text_raw_candidates") or [])
                    and str(
                        dict(content_row.get("operator_review") or {}).get(
                            "decision"
                        )
                        or ""
                    ).upper()
                    == "EDIT"
                )
                if not is_cover_only
                else False,
            }
        )

    render_tracks.sort(key=lambda row: (row["start_frame"], row["text_id"]))
    suppressed_weak_fragments = _suppress_weak_caption_fragments(render_tracks)
    adjusted_boundaries = _normalize_shared_caption_boundaries(
        render_tracks, fps=fps
    )
    return enrich_phase4_render_policies({
        "schema_version": PHASE4_INPUT_SCHEMA_VERSION,
        "status": "READY_FOR_PHASE4_PREFLIGHT",
        "refs": dict(refs),
        "video": {
            "frame_width": frame_width,
            "frame_height": frame_height,
            "frame_count": frame_count,
            "fps": fps,
        },
        "counts": {
            "render_tracks": len(render_tracks),
            "localized_tracks": sum(1 for row in render_tracks if row["text_vi"]),
            "cover_only_tracks": sum(1 for row in render_tracks if row["cover_only"]),
            "weak_caption_fragments_suppressed": suppressed_weak_fragments,
            "content_objects": len({row["content_id"] for row in render_tracks if row["content_id"]}),
            "protected_source_tracks": len(protected_source_tracks),
        },
        "timing_normalization": {
            "policy_version": PHASE4_TIMING_NORMALIZATION_POLICY_VERSION,
            "adjusted_shared_caption_boundaries": adjusted_boundaries,
            "weak_caption_fragments_suppressed": suppressed_weak_fragments,
        },
        "render_tracks": render_tracks,
        "protected_source_tracks": protected_source_tracks,
    })


def _segments_from_contract(contract: Mapping[str, Any]) -> list[OverlaySegment]:
    output: list[OverlaySegment] = []
    for row in list(contract.get("render_tracks") or []):
        geometry = dict(row.get("geometry") or {})
        output.append(
            OverlaySegment(
                start_ms=int(row.get("start_ms") or 0),
                end_ms=int(row.get("end_ms") or 0),
                x=float(geometry.get("x") or 0.0),
                y=float(geometry.get("y") or 0.0),
                width=float(geometry.get("width") or 0.0),
                height=float(geometry.get("height") or 0.0),
                text_vi=str(row.get("text_vi") or ""),
                kind=str(row.get("kind") or "ui"),
            )
        )
    return output


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    smaller = min(
        max(0, a[2] - a[0]) * max(0, a[3] - a[1]),
        max(0, b[2] - b[0]) * max(0, b[3] - b[1]),
    )
    # A few anti-aliased edge pixels and stacked subtitle baselines can share a
    # thin strip even when glyph ink remains readable.  Measure material
    # overlap against the smaller label; the 0.30 threshold matches the
    # renderer's glyph boxes and avoids blocking intentionally stacked source
    # labels (which are still covered by visual preview QA).
    return smaller > 0 and intersection / smaller >= 0.30


def analyze_phase4_typography(
    contract: Mapping[str, Any], *, fontfile: str | Path | None = None
) -> dict[str, Any]:
    """Measure responsive layouts using the same safe-area engine as Phase 4."""
    import numpy as np

    from src.media_pipeline.video_renderer.adaptive_typography import (
        TypographyLayoutError,
        plan_dense_grid_layouts,
        plan_text_layout,
    )

    video = dict(contract.get("video") or {})
    frame_width = int(video.get("frame_width") or 0)
    frame_height = int(video.get("frame_height") or 0)
    if frame_width < 2 or frame_height < 2:
        raise Phase4InputError("Cannot analyze typography without frame dimensions")
    resolved_font = resolve_drawtext_font(fontfile)
    background = np.full((frame_height, frame_width, 3), 96, dtype=np.uint8)
    tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    rows: list[dict[str, Any]] = []
    text_overflow = 0
    clamp_required = 0
    rect_by_id: dict[str, tuple[int, int, int, int]] = {}
    dense_tracks: list[dict[str, Any]] = []
    for track in tracks:
        text = str(track.get("text_vi") or "").strip()
        if not text:
            continue
        policy = dict(track.get("render_policy") or {})
        context = dict(policy.get("context") or {})
        layout_policy = dict(policy.get("layout") or {})
        if bool(context.get("dense_ui")) and str(
            layout_policy.get("mode") or ""
        ) != "cover_aligned":
            dense_tracks.append(track)
            continue
        effective_kind = str(context.get("effective_kind") or track.get("kind") or "ui")
        typography_kind = str(context.get("typography_kind") or effective_kind)
        try:
            layout = plan_text_layout(
                text,
                kind=typography_kind,
                safe_area=dict(layout_policy.get("safe_area") or {}),
                frame_width=frame_width,
                frame_height=frame_height,
                fontfile=resolved_font,
                background_bgr=background,
                max_lines=int(layout_policy.get("max_lines") or 1),
            )
        except TypographyLayoutError:
            text_overflow += 1
            rows.append(
                {
                    "text_id": track.get("text_id"),
                    "content_id": track.get("content_id"),
                    "kind": typography_kind,
                    "font_size_px": None,
                    "glyph_width_px": None,
                    "glyph_height_px": None,
                    "frame_width_fraction": None,
                    "line_count": None,
                    "text_overflow": True,
                    "clamp_required": False,
                }
            )
            continue
        text_id = str(track.get("text_id") or "")
        rect_by_id[text_id] = (
            layout.x0,
            layout.y0,
            layout.x0 + layout.width,
            layout.y0 + layout.height,
        )
        rows.append(
            {
                "text_id": text_id,
                "content_id": track.get("content_id"),
                "kind": typography_kind,
                "font_size_px": layout.font_size_px,
                "glyph_width_px": layout.width,
                "glyph_height_px": layout.height,
                "frame_width_fraction": round(layout.width / frame_width, 4),
                "line_count": len(layout.lines),
                "text_overflow": False,
                "clamp_required": False,
                "layout_rect_px": {
                    "x0": layout.x0,
                    "y0": layout.y0,
                    "x1": layout.x0 + layout.width,
                    "y1": layout.y0 + layout.height,
                },
            }
        )

    event_times = sorted(
        {
            int(value)
            for track in tracks
            if track.get("text_vi")
            for value in (
                track.get("start_ms") or 0,
                track.get("end_ms") or 0,
            )
        }
    )
    dense_rects_by_time: dict[int, dict[str, tuple[int, int, int, int]]] = {}
    dense_metrics_written: set[str] = set()
    dense_overflow_ids: set[str] = set()
    dense_layout_cache: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    if dense_tracks:
        for time_ms in event_times:
            active_dense = [
                track
                for track in dense_tracks
                if int(track.get("start_ms") or 0)
                <= time_ms
                < int(track.get("end_ms") or 0)
            ]
            active_dense = select_text_render_tracks(active_dense)
            if not active_dense:
                continue
            key = tuple(str(track.get("text_id") or "") for track in active_dense)
            layouts = dense_layout_cache.get(key)
            if layouts is None:
                first_policy = dict(active_dense[0].get("render_policy") or {})
                safe_area = dict(
                    dict(first_policy.get("layout") or {}).get("safe_area") or {}
                )
                dense_items = []
                for track in active_dense:
                    geometry = dict(track.get("geometry") or {})
                    center = float(geometry.get("x") or 0.0) + float(
                        geometry.get("width") or 0.0
                    ) * 0.5
                    dense_items.append(
                        {
                            "text_id": track.get("text_id"),
                            "content_id": track.get("content_id"),
                            "text": track.get("text_vi"),
                            "side": "left" if center < 0.5 else "right",
                        }
                    )
                try:
                    layouts = plan_dense_grid_layouts(
                        dense_items,
                        safe_area=safe_area,
                        frame_width=frame_width,
                        frame_height=frame_height,
                        fontfile=resolved_font,
                        background_bgr=background,
                    )
                except TypographyLayoutError:
                    dense_overflow_ids.update(key)
                    layouts = []
                dense_layout_cache[key] = layouts
            time_rects: dict[str, tuple[int, int, int, int]] = {}
            for item in layouts:
                layout = item["layout"]
                text_id = str(item.get("text_id") or "")
                rect = (
                    layout.x0,
                    layout.y0,
                    layout.x0 + layout.width,
                    layout.y0 + layout.height,
                )
                time_rects[text_id] = rect
                if text_id in dense_metrics_written:
                    continue
                dense_metrics_written.add(text_id)
                rows.append(
                    {
                        "text_id": text_id,
                        "content_id": item.get("content_id"),
                        "kind": "ui",
                        "font_size_px": layout.font_size_px,
                        "glyph_width_px": layout.width,
                        "glyph_height_px": layout.height,
                        "frame_width_fraction": round(layout.width / frame_width, 4),
                        "line_count": len(layout.lines),
                        "text_overflow": False,
                        "clamp_required": False,
                        "layout_rect_px": {
                            "x0": layout.x0,
                            "y0": layout.y0,
                            "x1": layout.x0 + layout.width,
                            "y1": layout.y0 + layout.height,
                        },
                    }
                )
            dense_rects_by_time[time_ms] = time_rects
        text_overflow += len(dense_overflow_ids)

    collision_events: list[dict[str, Any]] = []
    non_blocking_collision_events: list[dict[str, Any]] = []
    track_by_id = {
        str(track.get("text_id") or ""): track
        for track in tracks
        if str(track.get("text_id") or "")
    }

    def source_geometry_overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
        a = dict(left.get("geometry") or {})
        b = dict(right.get("geometry") or {})
        ax0, ay0 = float(a.get("x") or 0.0), float(a.get("y") or 0.0)
        ax1, ay1 = ax0 + float(a.get("width") or 0.0), ay0 + float(a.get("height") or 0.0)
        bx0, by0 = float(b.get("x") or 0.0), float(b.get("y") or 0.0)
        bx1, by1 = bx0 + float(b.get("width") or 0.0), by0 + float(b.get("height") or 0.0)
        intersection = max(0.0, min(ax1, bx1) - max(ax0, bx0)) * max(
            0.0, min(ay1, by1) - max(ay0, by0)
        )
        smaller = min(
            max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0),
            max(0.0, bx1 - bx0) * max(0.0, by1 - by0),
        )
        return intersection / smaller if smaller > 0.0 else 0.0
    for time_ms in event_times:
        active_tracks = [
            track
            for track in tracks
            if track.get("text_vi")
            and int(track.get("start_ms") or 0) <= time_ms < int(track.get("end_ms") or 0)
        ]
        active_tracks = select_text_render_tracks(active_tracks)
        active_ids: list[str] = []
        rects: list[tuple[int, int, int, int]] = []
        dense_time_rects = dense_rects_by_time.get(time_ms, {})
        for track in active_tracks:
            text_id = str(track.get("text_id") or "")
            context = dict(
                dict(track.get("render_policy") or {}).get("context") or {}
            )
            rect = (
                dense_time_rects.get(text_id)
                if bool(context.get("dense_ui"))
                else rect_by_id.get(text_id)
            )
            if rect is None:
                continue
            active_ids.append(text_id)
            rects.append(rect)
        if len(active_ids) < 2:
            continue
        overlap_pairs = [
            [active_ids[index], active_ids[other_index]]
            for index, rect in enumerate(rects)
            for other_index, other in enumerate(
                rects[index + 1 :], start=index + 1
            )
            if _rects_overlap(rect, other)
        ]
        if overlap_pairs:
            event = {
                "time_ms": time_ms,
                "active": len(active_ids),
                "overlaps": len(overlap_pairs),
                "overlap_pairs": overlap_pairs,
            }
            # Source-separated editor UI labels are intentionally allowed to
            # use the renderer's stable vertical packing.  Their expanded
            # Vietnamese glyph boxes may touch even though the source boxes do
            # not; visual preview still records the event for operator QA.
            source_separated = all(
                source_geometry_overlap(
                    track_by_id.get(left, {}), track_by_id.get(right, {})
                ) < 0.10
                and str(track_by_id.get(left, {}).get("kind") or "ui") != "hardsub"
                and str(track_by_id.get(right, {}).get("kind") or "ui") != "hardsub"
                for left, right in overlap_pairs
            )
            if source_separated:
                non_blocking_collision_events.append(
                    {**event, "classification": "SOURCE_SEPARATED_LAYOUT_CONTACT"}
                )
            else:
                collision_events.append(event)

    blocking_reasons: list[str] = []
    if text_overflow:
        blocking_reasons.append(f"text_overflow:{text_overflow}")
    if collision_events:
        blocking_reasons.append(f"unresolved_collisions:{len(collision_events)}")
    return {
        "schema_version": PHASE4_PREFLIGHT_SCHEMA_VERSION,
        "status": (
            "PHASE4_PREFLIGHT_BLOCKED" if blocking_reasons else "READY_FOR_PHASE4"
        ),
        "blocked_reasons": blocking_reasons,
        "font": {"name": resolved_font.name},
        "counts": {
            "measured_tracks": len(rows),
            "text_overflow": text_overflow,
            "clamp_required": clamp_required,
            "collision_events": len(collision_events),
            "non_blocking_collision_events": len(non_blocking_collision_events),
        },
        "track_metrics": rows,
        "collision_events": collision_events,
        "non_blocking_collision_events": non_blocking_collision_events,
    }


def _verify_hash_ref(payload: Mapping[str, Any], key: str, path: Path) -> None:
    ref = payload.get(key)
    expected = str(ref.get("sha256") or "") if isinstance(ref, Mapping) else ""
    if not expected or expected != _sha256_file(path):
        raise Phase4InputError(f"Stale or missing {key} hash")


def _apply_geometry_overrides(
    master: Sequence[Mapping[str, Any]],
    overrides: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for raw in overrides:
        override = dict(raw)
        text_id = str(override.get("target_text_id") or "").strip()
        if not text_id or text_id in by_id:
            raise Phase4InputError("Residual geometry override target is invalid")
        by_id[text_id] = override
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in master:
        row = dict(raw)
        text_id = str(row.get("text_id") or "")
        override = by_id.get(text_id)
        if override is None:
            output.append(row)
            continue
        original = list(override.get("original_box_coords") or [])
        replacement = list(override.get("box_coords") or [])
        if (
            len(original) != 4
            or len(replacement) != 4
            or original != list(row.get("box_coords") or [])
            or int(override.get("start_frame")) != int(row.get("start_frame"))
            or int(override.get("end_frame")) != int(row.get("end_frame"))
        ):
            raise Phase4InputError("Residual geometry override authority drifted")
        row.update(
            {
                "box_coords": replacement,
                "best_keyframe_path": override.get("best_keyframe_path"),
                "crop_path": override.get("crop_path"),
                "best_frame_index": override.get("best_frame_index"),
                "geometry_remediation": {
                    "status": "OPERATOR_APPROVED_OVERRIDE",
                    "original_box_coords": original,
                },
            }
        )
        seen.add(text_id)
        output.append(row)
    if seen != set(by_id):
        raise Phase4InputError("Residual geometry override target is missing")
    return output


def _resolve_phase1_source_path(
    root: Path,
    source_raw: str,
    *,
    api_root: Path | None = None,
) -> Path:
    """Resolve Phase-1 source paths across artifact and API working bases."""
    source_candidate = Path(source_raw)
    if source_candidate.is_absolute():
        candidates = [source_candidate]
    else:
        runtime_api_root = (
            api_root.resolve()
            if api_root is not None
            else Path(__file__).resolve().parents[3]
        )
        candidates = [
            root / source_candidate,
            runtime_api_root / source_candidate,
            root.parent / source_candidate,
        ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    raise Phase4InputError("Source video referenced by Phase 1 is missing")


def prepare_phase4_from_root(
    root_dir: str | Path,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Load and verify the immutable artifact chain, then build preflight data."""
    root = Path(root_dir).resolve()
    paths = {
        "master": root / "master_timeline.json",
        "phase2_timeline": root / "phase2_ocr_timeline.json",
        "phase2_handoff": root / "phase2_handoff.json",
        "phase3_timeline": root / "phase3_translation_timeline.json",
        "phase3_handoff": root / "phase3_render_handoff.json",
        "ocr_payload": root / "ocr_payload.json",
        "phase1_meta": root / "phase1_meta.json",
    }
    for path in paths.values():
        if not path.is_file():
            raise Phase4InputError(f"Missing required artifact: {path.name}")
    master = _load_json(paths["master"])
    phase2_timeline = _load_json(paths["phase2_timeline"])
    phase2_handoff = _load_json(paths["phase2_handoff"])
    phase3_timeline = _load_json(paths["phase3_timeline"])
    phase3_handoff = _load_json(paths["phase3_handoff"])
    ocr_payload = _load_json(paths["ocr_payload"])
    phase1_meta = _load_json(paths["phase1_meta"])
    for label, payload in (
        ("phase2_handoff", phase2_handoff),
        ("phase3_timeline", phase3_timeline),
        ("phase3_handoff", phase3_handoff),
        ("ocr_payload", ocr_payload),
        ("phase1_meta", phase1_meta),
    ):
        if not isinstance(payload, Mapping):
            raise Phase4InputError(f"{label} must be a JSON object")
    if not isinstance(master, list) or not isinstance(phase2_timeline, Mapping):
        raise Phase4InputError("Invalid Phase 1/2 timeline shape")

    _verify_hash_ref(phase2_handoff, "phase1_ref", paths["master"])
    _verify_hash_ref(phase2_handoff, "phase2_ref", paths["phase2_timeline"])
    _verify_hash_ref(phase3_timeline, "phase2_handoff_ref", paths["phase2_handoff"])
    _verify_hash_ref(phase3_handoff, "phase2_handoff_ref", paths["phase2_handoff"])
    if (
        str(dict(phase3_timeline.get("review_summary") or {}).get("status") or "")
        != "TRANSLATION_APPROVED"
    ):
        raise Phase4InputError("Phase 3 translation timeline is not approved")

    supplemental = [
        dict(row)
        for row in list(phase2_timeline.get("supplemental_occurrences") or [])
        if isinstance(row, Mapping)
    ]
    geometry_overrides = [
        dict(row)
        for row in list(phase2_timeline.get("geometry_overrides") or [])
        if isinstance(row, Mapping)
    ]
    remediation_ref = dict(
        phase2_timeline.get("residual_remediation_ref") or {}
    )
    handoff_remediation_ref = dict(
        phase2_handoff.get("residual_remediation_ref") or {}
    )
    if supplemental or geometry_overrides:
        if not remediation_ref or remediation_ref != handoff_remediation_ref:
            raise Phase4InputError("Residual remediation authority mismatch")
        remediation_path = root / str(remediation_ref.get("path") or "")
        if (
            not remediation_path.is_file()
            or _sha256_file(remediation_path)
            != str(remediation_ref.get("sha256") or "")
        ):
            raise Phase4InputError("Residual remediation authority is stale")
        remediation = _load_json(remediation_path)
        if not isinstance(remediation, Mapping):
            raise Phase4InputError("Residual remediation must be a JSON object")
        unsigned = dict(remediation)
        claimed = str(unsigned.pop("remediation_sha256", "") or "")
        if (
            str(remediation.get("status") or "")
            != "OCR_RESIDUAL_REMEDIATION_APPROVED"
            or claimed != str(remediation_ref.get("remediation_sha256") or "")
            or claimed != _sha256_json(unsigned)
        ):
            raise Phase4InputError("Residual remediation self-hash is invalid")
        approved_overrides = [
            dict(dict(row).get("geometry_override") or {})
            for row in list(remediation.get("approved_geometry_overrides") or [])
            if isinstance(row, Mapping)
        ]
        approved_by_id = {
            str(row.get("target_text_id") or ""): row
            for row in approved_overrides
            if str(row.get("target_text_id") or "")
        }
        timeline_by_id = {
            str(row.get("target_text_id") or ""): row
            for row in geometry_overrides
            if str(row.get("target_text_id") or "")
        }
        if approved_by_id != timeline_by_id:
            raise Phase4InputError("Residual geometry override authority mismatch")
    elif remediation_ref or handoff_remediation_ref:
        raise Phase4InputError("Residual remediation has no approved change")

    source_raw = str(phase1_meta.get("video") or "").strip()
    if not source_raw:
        raise Phase4InputError("phase1_meta.json has no source video reference")
    source_path = _resolve_phase1_source_path(root, source_raw)

    cover_only_refs: list[str] = []
    for item in list(phase2_handoff.get("cover_only_items") or []):
        if isinstance(item, Mapping):
            cover_only_refs.extend(str(value) for value in list(item.get("geometry_refs") or []))
    protected_source_refs: list[str] = []
    for item in list(phase2_handoff.get("preserved_source_items") or []):
        if not isinstance(item, Mapping):
            continue
        protected_source_refs.extend(
            str(value) for value in list(item.get("geometry_refs") or [])
        )
        if str(item.get("text_id") or ""):
            protected_source_refs.append(str(item.get("text_id")))
    refs = {
        "phase1_ref": phase2_handoff.get("phase1_ref"),
        "phase2_ref": phase2_handoff.get("phase2_ref"),
        "phase2_handoff_ref": {
            "path": paths["phase2_handoff"].name,
            "sha256": _sha256_file(paths["phase2_handoff"]),
        },
        "phase3_timeline_ref": {
            "path": paths["phase3_timeline"].name,
            "sha256": _sha256_file(paths["phase3_timeline"]),
        },
        "phase3_render_handoff_ref": {
            "path": paths["phase3_handoff"].name,
            "sha256": _sha256_file(paths["phase3_handoff"]),
        },
        "source_video_ref": {
            "path": source_path.name,
            "sha256": _sha256_file(source_path),
        },
    }
    if remediation_ref:
        refs["residual_remediation_ref"] = remediation_ref
    video_metadata = {
        key: ocr_payload.get(key)
        for key in ("frame_width", "frame_height", "frame_count", "fps")
    }
    master_with_overrides = _apply_geometry_overrides(master, geometry_overrides)
    master_with_supplemental = master_with_overrides + supplemental
    contract = build_phase4_render_input(
        master_with_supplemental,
        phase2_timeline,
        phase3_handoff,
        video_metadata=video_metadata,
        refs=refs,
        cover_only_refs=cover_only_refs,
        protected_source_refs=protected_source_refs,
    )
    report = analyze_phase4_typography(contract)
    contract["status"] = (
        "READY_FOR_PHASE4"
        if report["status"] == "READY_FOR_PHASE4"
        else "PHASE4_PREFLIGHT_BLOCKED"
    )
    return contract, report, source_path


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _preflight_markdown(
    contract: Mapping[str, Any], report: Mapping[str, Any]
) -> str:
    counts = dict(contract.get("counts") or {})
    qa_counts = dict(report.get("counts") or {})
    lines = [
        "# Phase 4 Render Preflight",
        "",
        f"- Trạng thái: `{report.get('status') or 'UNKNOWN'}`",
        f"- Render tracks: {counts.get('render_tracks', 0)}",
        f"- Localized tracks: {counts.get('localized_tracks', 0)}",
        f"- Cover-only tracks: {counts.get('cover_only_tracks', 0)}",
        f"- Text overflow: {qa_counts.get('text_overflow', 0)}",
        f"- Clamp required: {qa_counts.get('clamp_required', 0)}",
        f"- Collision events: {qa_counts.get('collision_events', 0)}",
        "",
        "| text_id | content_id | kind | font px | glyph px | width/frame | overflow | clamp |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    for row in list(report.get("track_metrics") or []):
        lines.append(
            "| {text_id} | {content_id} | {kind} | {font} | {width}×{height} | {ratio:.1%} | {overflow} | {clamp} |".format(
                text_id=row.get("text_id") or "",
                content_id=row.get("content_id") or "",
                kind=row.get("kind") or "",
                font=int(row.get("font_size_px") or 0),
                width=int(row.get("glyph_width_px") or 0),
                height=int(row.get("glyph_height_px") or 0),
                ratio=float(row.get("frame_width_fraction") or 0.0),
                overflow="YES" if row.get("text_overflow") else "no",
                clamp="YES" if row.get("clamp_required") else "no",
            )
        )
    lines.extend(
        [
            "",
            "Preflight chỉ xác nhận contract, typography và placement; chưa render video hoàn chỉnh.",
            "",
        ]
    )
    return "\n".join(lines)


def write_phase4_preflight_artifacts(
    *,
    root_dir: str | Path,
    contract: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, Path]:
    root = Path(root_dir)
    preview_path = root / "phase4_render_input_preview.json"
    final_path = root / "phase4_render_input.json"
    report_json_path = root / "qa" / "phase4_preflight_report.json"
    report_md_path = root / "PHASE4_PREFLIGHT_REPORT.md"
    _write_json_atomic(preview_path, dict(contract))
    _write_json_atomic(report_json_path, dict(report))
    _write_text_atomic(report_md_path, _preflight_markdown(contract, report))
    if (
        str(contract.get("status") or "") == "READY_FOR_PHASE4"
        and str(report.get("status") or "") == "READY_FOR_PHASE4"
    ):
        _write_json_atomic(final_path, dict(contract))
    elif final_path.is_file():
        stale_dir = root / "qa" / "stale"
        stale_dir.mkdir(parents=True, exist_ok=True)
        final_path.replace(
            stale_dir
            / f"{final_path.stem}_{_sha256_file(final_path)[:12]}{final_path.suffix}"
        )
    return {
        "preview": preview_path,
        "final": final_path,
        "report_json": report_json_path,
        "report_md": report_md_path,
    }
