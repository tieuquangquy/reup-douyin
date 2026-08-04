"""Conservative provenance classification for source-scene text planes.

Only high-density, bounded, non-hardsub UI components are classified
automatically. Wide hardsubs remain editor overlays even when they overlap the
same frames. Sparse or ambiguous labels are left unchanged for explicit review.
"""

from __future__ import annotations

from statistics import median
from typing import Any, Mapping, Sequence


SOURCE_SCENE_POLICY_VERSION = "phase4_source_text_provenance_v3"
SOURCE_INTRINSIC_REGION_POLICY_VERSION = (
    "operator_hash_bound_moving_object_region_v1"
)


def is_editor_caption_track(track: Mapping[str, Any]) -> bool:
    """Distinguish wide editor hardsubs from source-phone micro UI labels."""

    context = dict(dict(track.get("render_policy") or {}).get("context") or {})
    roles = {str(value) for value in list(track.get("roles") or [])}
    kind = str(track.get("kind") or "")
    source_kind = str(context.get("source_kind") or "")
    geometry = dict(track.get("geometry") or {})
    width = float(geometry.get("width") or 0.0)
    y = float(geometry.get("y") or 0.0)
    if kind == "hardsub" or source_kind == "hardsub":
        return True
    # Some legacy OCR rows inherited a hardsub role despite being a small UI
    # label filmed on the phone.  The source-kind/micro-UI evidence wins.
    # Phase-2 legacy rows can call a short, isolated bottom-lane editor
    # caption ``ui/micro_ui``.  A translated generic phrase in that lane is
    # still editor-added text.  Dense/simultaneous phone panels deliberately
    # do not satisfy this branch.
    if (
        source_kind == "ui"
        and "generic" in roles
        and not bool(context.get("dense_ui"))
        and int(context.get("simultaneous_count") or 0) <= 2
        and y >= 0.72
        and width >= 0.18
        and len(str(track.get("text_vi") or "").strip()) >= 8
    ):
        return True
    if source_kind == "ui" and bool(context.get("micro_ui")):
        return False
    # Legacy OCR rows can be typed as generic UI even when render policy has
    # already established a wide editor caption lane.
    if bool(context.get("caption_row")) and not bool(context.get("micro_ui")):
        return True
    if "hardsub" not in roles:
        return False
    return True


def _rect(track: Mapping[str, Any]) -> tuple[float, float, float, float]:
    geometry = dict(track.get("geometry") or {})
    x0 = float(geometry.get("x") or 0.0)
    y0 = float(geometry.get("y") or 0.0)
    return (
        x0,
        y0,
        x0 + float(geometry.get("width") or 0.0),
        y0 + float(geometry.get("height") or 0.0),
    )


def _candidate(track: Mapping[str, Any]) -> bool:
    context = dict(dict(track.get("render_policy") or {}).get("context") or {})
    return (
        bool(str(track.get("text_id") or ""))
        and str(track.get("kind") or "") != "hardsub"
        and bool(context.get("dense_ui"))
        and int(context.get("simultaneous_count") or 0) >= 8
    )


def _source_plane_candidate(track: Mapping[str, Any]) -> bool:
    """Return small scene-bound labels while rejecting editor caption shapes."""

    roles = {str(value) for value in list(track.get("roles") or [])}
    geometry = dict(track.get("geometry") or {})
    width = float(geometry.get("width") or 0.0)
    height = float(geometry.get("height") or 0.0)
    y = float(geometry.get("y") or 0.0)
    return (
        bool(str(track.get("text_id") or ""))
        and str(track.get("kind") or "") != "hardsub"
        and "generic" not in roles
        and not is_editor_caption_track(track)
        and 0.0 < width <= 0.25
        and 0.0 < height
        and width * height <= 0.03
    )


def classify_source_scene_components(
    tracks: Sequence[Mapping[str, Any]],
    *,
    frame_count: int,
    seed_regions: Sequence[Mapping[str, Any]] = (),
    max_component_frames: int = 240,
    min_tracks: int = 6,
    temporal_gap: int = 3,
    plane_temporal_gap: int = 90,
) -> list[dict[str, Any]]:
    """Return dense device/UI planes that must remain untouched in source."""

    candidates = [dict(row) for row in tracks if isinstance(row, Mapping) and _candidate(row)]
    ordered = sorted(
        candidates,
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
        if not components or start > component_end + int(temporal_gap):
            components.append([])
            component_end = end
        else:
            component_end = max(component_end, end)
        components[-1].append(track)

    dense_seeds: list[dict[str, Any]] = [
        dict(row)
        for row in seed_regions
        if isinstance(row, Mapping)
        and str(row.get("classification") or "") == "SOURCE_SCENE_TEXT"
    ]
    for index, component in enumerate(components, start=1):
        if len(component) < int(min_tracks):
            continue
        start = min(int(row.get("start_frame") or 0) for row in component)
        end = max(int(row.get("end_frame") or start) for row in component)
        if end - start + 1 > int(max_component_frames):
            continue
        rectangles = [_rect(row) for row in component]
        areas = [max(0.0, x1 - x0) * max(0.0, y1 - y0) for x0, y0, x1, y1 in rectangles]
        x0 = min(row[0] for row in rectangles)
        y0 = min(row[1] for row in rectangles)
        x1 = max(row[2] for row in rectangles)
        y1 = max(row[3] for row in rectangles)
        union_area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        if not (0.08 <= union_area <= 0.70) or float(median(areas)) > 0.03:
            continue
        pad = 0.012
        rx0, ry0 = max(0.0, x0 - pad), max(0.0, y0 - pad)
        rx1, ry1 = min(1.0, x1 + pad), min(1.0, y1 + pad)
        dense_seeds.append(
            {
                "region_id": f"source_scene_dense_{index:02d}",
                "classification": "SOURCE_SCENE_TEXT",
                "start_frame": max(0, start),
                "end_frame": min(max(0, int(frame_count) - 1), end),
                "region_roi": {
                    "x": round(rx0, 9),
                    "y": round(ry0, 9),
                    "width": round(rx1 - rx0, 9),
                    "height": round(ry1 - ry0, 9),
                },
                "track_ids": sorted(str(row.get("text_id") or "") for row in component),
                "evidence": {
                    "policy_version": SOURCE_SCENE_POLICY_VERSION,
                    "track_count": len(component),
                    "component_frame_span": end - start + 1,
                    "union_area_fraction": round(union_area, 9),
                    "median_track_area_fraction": round(float(median(areas)), 9),
                    "max_simultaneous_count": max(
                        int(dict(dict(row.get("render_policy") or {}).get("context") or {}).get("simultaneous_count") or 0)
                        for row in component
                    ),
                    "reasons": [
                        "dense_non_hardsub_ui_component",
                        "bounded_device_panel_geometry",
                        "editor_hardsub_explicitly_excluded",
                    ],
                },
            }
        )

    source_candidates = [
        dict(row)
        for row in tracks
        if isinstance(row, Mapping) and _source_plane_candidate(row)
    ]
    plane_components: list[list[dict[str, Any]]] = []
    plane_end = -int(plane_temporal_gap) - 2
    for track in sorted(
        source_candidates,
        key=lambda row: (
            int(row.get("start_frame") or 0),
            int(row.get("end_frame") or -1),
            str(row.get("text_id") or ""),
        ),
    ):
        start = int(track.get("start_frame") or 0)
        end = int(track.get("end_frame") or start)
        if not plane_components or start > plane_end + int(plane_temporal_gap):
            plane_components.append([])
            plane_end = end
        else:
            plane_end = max(plane_end, end)
        plane_components[-1].append(track)

    output: list[dict[str, Any]] = []
    for index, component in enumerate(plane_components, start=1):
        start = min(int(row.get("start_frame") or 0) for row in component)
        end = max(int(row.get("end_frame") or start) for row in component)
        matched_seeds = [
            seed
            for seed in dense_seeds
            if not (
                end + int(plane_temporal_gap)
                < int(seed.get("start_frame") or 0)
                or start - int(plane_temporal_gap)
                > int(seed.get("end_frame") or -1)
            )
        ]
        if not matched_seeds:
            continue
        rectangles = [_rect(row) for row in component]
        x0 = min(row[0] for row in rectangles)
        y0 = min(row[1] for row in rectangles)
        x1 = max(row[2] for row in rectangles)
        y1 = max(row[3] for row in rectangles)
        pad = 0.012
        rx0, ry0 = max(0.0, x0 - pad), max(0.0, y0 - pad)
        rx1, ry1 = min(1.0, x1 + pad), min(1.0, y1 + pad)
        output.append(
            {
                "region_id": f"source_scene_plane_{index:02d}",
                "classification": "SOURCE_SCENE_TEXT",
                "start_frame": max(0, start),
                "end_frame": min(max(0, int(frame_count) - 1), end),
                "region_roi": {
                    "x": round(rx0, 9),
                    "y": round(ry0, 9),
                    "width": round(rx1 - rx0, 9),
                    "height": round(ry1 - ry0, 9),
                },
                "track_ids": sorted(
                    str(row.get("text_id") or "") for row in component
                ),
                "evidence": {
                    "policy_version": SOURCE_SCENE_POLICY_VERSION,
                    "track_count": len(component),
                    "component_frame_span": end - start + 1,
                    "dense_seed_region_ids": sorted(
                        str(seed.get("region_id") or "") for seed in matched_seeds
                    ),
                    "reasons": [
                        "dense_ui_seeded_source_plane",
                        "temporally_connected_small_scene_labels",
                        "editor_caption_shapes_excluded",
                    ],
                },
            }
        )
    return output
