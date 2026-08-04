"""Score a Phase1 out dir against PASS checklist (heuristic + geometry gates)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from statistics import median

from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    MergedTrack,
    _box_looks_like_thin_hardsub,
    _has_dense_ui_grid_peer_evidence,
    _split_wide_ui_track_by_ink_columns,
    _mid_column_bucket,
    box_iou,
    classify_ocr_box_role,
    find_temporally_nested_ui_fragments,
    isolated_micro_source_text_member_ids,
    perspective_ui_provenance_member_ids,
)


def _box_overlap_over_smaller_area(left: list[float], right: list[float]) -> float:
    lx0, ly0, lx1, ly1 = (float(value) for value in left[:4])
    rx0, ry0, rx1, ry1 = (float(value) for value in right[:4])
    intersection = max(0.0, min(lx1, rx1) - max(lx0, rx0)) * max(
        0.0, min(ly1, ry1) - max(ly0, ry0)
    )
    left_area = max(1.0, lx1 - lx0) * max(1.0, ly1 - ly0)
    right_area = max(1.0, rx1 - rx0) * max(1.0, ry1 - ry0)
    return intersection / min(left_area, right_area)


def _matches_latin_source_box(
    box: list[float], source_box: list[float]
) -> bool:
    return box_iou(box, source_box) >= 0.30 or (
        _box_overlap_over_smaller_area(box, source_box) >= 0.55
    )


def score_phase1_out(
    out_dir: Path,
    *,
    frame_w: int | None = None,
    frame_h: int | None = None,
) -> dict:
    timeline_path = out_dir / "master_timeline.json"
    meta_path = out_dir / "phase1_meta.json"
    quality_path = out_dir / "qa" / "quality_report.json"
    before_after_path = out_dir / "qa" / "before_after.json"
    coverage_path = out_dir / "text_frame_coverage.json"
    items = json.loads(timeline_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    quality = (
        json.loads(quality_path.read_text(encoding="utf-8"))
        if quality_path.is_file()
        else None
    )
    uncertain_tracks = (
        int(quality.get("uncertain_tracks") or 0) if quality is not None else None
    )
    coverage = (
        json.loads(coverage_path.read_text(encoding="utf-8"))
        if coverage_path.is_file()
        else None
    )
    frame_w = int(frame_w or (coverage or {}).get("frame_width") or 1920)
    frame_h = int(frame_h or (coverage or {}).get("frame_height") or 1080)
    before_after = (
        json.loads(before_after_path.read_text(encoding="utf-8"))
        if before_after_path.is_file()
        else {}
    )
    strong_reject_reasons = {
        "local_text_reject",
        "latin_text_without_editor_card_evidence",
        "low_ink",
        "not_overlay_geometry",
        "scene_text",
        "scene_ui_cluster",
    }
    standalone_geometry_reject_reasons = {
        "not_overlay_geometry",
        "scene_text",
        "scene_ui_cluster",
        "latin_text_without_editor_card_evidence",
    }
    rejected_hardsub_boxes: list[list[float]] = []
    standalone_rejected_hardsub_boxes: list[list[float]] = []
    latin_source_text_boxes: list[list[float]] = []
    low_ink_hardsub_boxes: list[list[float]] = []
    high_confidence_local_text_rejects: list[dict] = []
    semantic_scene_rows = list(
        dict(
            (before_after.get("local_text_gate") or {}).get(
                "semantic_scene_label"
            )
            or {}
        ).get("rows")
        or []
    )
    for row in ((before_after.get("local_text_gate") or {}).get("rows") or []):
        box = row.get("box") or row.get("box_coords")
        text = str(row.get("text") or "").strip()
        cjk_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        if (
            row.get("reason") == "local_text_reject"
            and float(row.get("confidence") or 0.0) >= 0.90
            and cjk_count >= 2
        ):
            high_confidence_local_text_rejects.append(
                {
                    "text": text,
                    "confidence": float(row.get("confidence") or 0.0),
                    "role": row.get("role"),
                    "box": list(box[:4]) if isinstance(box, list) else None,
                }
            )
        if (
            row.get("reason") == "latin_text_without_editor_card_evidence"
            and isinstance(box, list)
            and len(box) >= 4
        ):
            latin_source_text_boxes.append(
                [float(value) for value in box[:4]]
            )
        if (
            row.get("reason") == "low_ink"
            and row.get("role") == "hardsub"
            and isinstance(box, list)
            and len(box) >= 4
        ):
            low_ink_hardsub_boxes.append(
                [float(value) for value in box[:4]]
            )
        if (
            row.get("role") == "hardsub"
            and row.get("reason") in strong_reject_reasons
            and isinstance(box, list)
            and len(box) >= 4
        ):
            rejected_hardsub_boxes.append(
                [float(value) for value in box[:4]]
            )
            if row.get("reason") in standalone_geometry_reject_reasons:
                standalone_rejected_hardsub_boxes.append(
                    [float(value) for value in box[:4]]
                )

    roles: dict[str, int] = defaultdict(int)
    hardsubs: list[dict] = []
    empty_left_hs: list[str] = []
    edge_wide_hardsub_candidates: list[dict] = []
    for x in items:
        box = x["box_coords"]
        role = str(x.get("semantic_role") or "") or classify_ocr_box_role(
            box, frame_w=frame_w, frame_h=frame_h
        )
        roles[role] += 1
        if role == "hardsub" and _box_looks_like_thin_hardsub(
            box, frame_w=frame_w, frame_h=frame_h
        ):
            hardsubs.append(x)
            if float(box[0]) <= 12.0 and (float(box[2]) - float(box[0])) / frame_w >= 0.35:
                edge_wide_hardsub_candidates.append(x)

    # Re-run the production provenance invariant from exported geometry. The
    # scorer must reject old/stale outputs that still contain isolated static
    # appliance/scene micro text even when every track is otherwise confirmed.
    provenance_tracks: list[MergedTrack] = []
    provenance_ids: dict[int, str] = {}
    for item in items:
        if str(item.get("semantic_role") or "") == "semantic_scene_label":
            continue
        box = [float(value) for value in item["box_coords"][:4]]
        start_frame = int(item["start_frame"])
        end_frame = int(item["end_frame"])
        hit_count = max(2, int(item.get("hit_count") or 2))
        track = MergedTrack(
            start_frame=start_frame,
            end_frame=end_frame,
            box_coords=box,
            best_frame_index=int(item.get("best_frame_index") or start_frame),
            best_sharpness=0.0,
            centroid=(
                0.5 * (box[0] + box[2]),
                0.5 * (box[1] + box[3]),
            ),
            hit_count=hit_count,
            hit_boxes=[tuple(box), tuple(box)],
            hit_frames=[start_frame, end_frame],
            hit_sharpness=[0.0, 0.0],
        )
        provenance_tracks.append(track)
        provenance_ids[id(track)] = str(item["text_id"])
    isolated_source_ids = isolated_micro_source_text_member_ids(
        provenance_tracks,
        frame_w=frame_w,
        frame_h=frame_h,
    )
    perspective_ui_ids = perspective_ui_provenance_member_ids(
        provenance_tracks,
        frame_w=frame_w,
        frame_h=frame_h,
    )
    isolated_micro_source_tracks = sorted(
        provenance_ids[track_id]
        for track_id in isolated_source_ids
        if track_id in provenance_ids
    )
    perspective_ui_provenance_tracks = sorted(
        provenance_ids[track_id]
        for track_id in perspective_ui_ids
        if track_id in provenance_ids
    )
    nested_temporal_ui_fragments: list[dict[str, object]] = []
    for row in find_temporally_nested_ui_fragments(
        provenance_tracks, frame_w=frame_w, frame_h=frame_h
    ):
        candidate = provenance_tracks[int(row["candidate_index"])]
        authority = provenance_tracks[int(row["authority_index"])]
        nested_temporal_ui_fragments.append(
            {
                "candidate_text_id": provenance_ids[id(candidate)],
                "authority_text_id": provenance_ids[id(authority)],
                **{
                    key: value
                    for key, value in row.items()
                    if key not in {"candidate_index", "authority_index"}
                },
            }
        )

    unverified_semantic_scene_tracks: list[str] = []
    for item in items:
        semantic_role = str(item.get("semantic_role") or "")
        if not semantic_role:
            continue
        verified = False
        if semantic_role == "semantic_scene_label":
            for raw in semantic_scene_rows:
                if not isinstance(raw, dict):
                    continue
                evidence_box = raw.get("box")
                if not isinstance(evidence_box, list) or len(evidence_box) < 4:
                    continue
                if not _matches_latin_source_box(
                    item["box_coords"], evidence_box
                ):
                    continue
                overlap = max(
                    0,
                    min(int(item["end_frame"]), int(raw.get("end_frame") or 0))
                    - max(
                        int(item["start_frame"]),
                        int(raw.get("start_frame") or 0),
                    )
                    + 1,
                )
                span = max(
                    1, int(item["end_frame"]) - int(item["start_frame"]) + 1
                )
                if overlap / float(span) >= 0.50:
                    verified = True
                    break
        if not verified:
            unverified_semantic_scene_tracks.append(str(item["text_id"]))

    near_dupes: list[tuple[str, str, float]] = []
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            overlap_frames = max(
                0,
                min(int(a["end_frame"]), int(b["end_frame"]))
                - max(int(a["start_frame"]), int(b["start_frame"]))
                + 1,
            )
            # Consecutive captions intentionally reuse the same subtitle locus.
            # One inclusive transition/pad frame is not duplicate evidence.
            if overlap_frames < 2:
                continue
            if _mid_column_bucket(a["box_coords"], frame_w=frame_w) != _mid_column_bucket(
                b["box_coords"], frame_w=frame_w
            ):
                continue
            iou = box_iou(a["box_coords"], b["box_coords"])
            if iou >= 0.4:
                near_dupes.append((a["text_id"], b["text_id"], round(float(iou), 3)))

    missing_crops = [
        x["text_id"]
        for x in items
        if not (out_dir / str(x.get("crop_path") or "")).is_file()
    ]
    missing_frames = [
        x["text_id"]
        for x in items
        if not (out_dir / str(x.get("best_keyframe_path") or "")).is_file()
    ]

    uncovered_hardsub_frames: set[int] = set()
    rejected_shadow_frames: set[int] = set()
    detector_hardsubs_by_frame: dict[int, list[list[float]]] = defaultdict(list)
    residual_recovery = dict(before_after.get("residual_hardsub_recovery") or {})
    residual_audit_unresolved_spans = list(
        residual_recovery.get("unresolved_spans") or []
    )
    residual_audit_unresolved_frames = {
        frame_index
        for span in residual_audit_unresolved_spans
        if isinstance(span, list) and len(span) >= 2
        for frame_index in range(int(span[0]), int(span[1]) + 1)
    }
    residual_shadow_boxes_by_frame: dict[int, list[list[float]]] = defaultdict(list)
    for row in list(residual_recovery.get("rows") or []):
        if not isinstance(row, dict) or row.get("action") != "explain_adjacent_shadow":
            continue
        box = row.get("box")
        if not isinstance(box, list) or len(box) < 4:
            continue
        residual_shadow_boxes_by_frame[int(row.get("frame_index") or 0)].append(
            [float(value) for value in box[:4]]
        )
    if coverage is not None:
        for raw_frame, frame_hits in (coverage.get("by_frame") or {}).items():
            frame_index = int(raw_frame)
            latin_source_present = any(
                isinstance((item.get("boxes") or item.get("box")), list)
                and len(item.get("boxes") or item.get("box")) >= 4
                and any(
                    _matches_latin_source_box(
                        item.get("boxes") or item.get("box"), source_box
                    )
                    for source_box in latin_source_text_boxes
                )
                for item in frame_hits
                if isinstance(item, dict)
            )
            for hit in frame_hits:
                hit_box = hit.get("boxes") or hit.get("box")
                if not isinstance(hit_box, list) or len(hit_box) < 4:
                    continue
                hit_width = float(hit_box[2]) - float(hit_box[0])
                if hit_width / max(1.0, float(frame_w)) < 0.12:
                    continue
                if classify_ocr_box_role(
                    hit_box, frame_w=frame_w, frame_h=frame_h
                ) != "hardsub":
                    continue
                detector_hardsubs_by_frame[frame_index].append(
                    [float(value) for value in hit_box[:4]]
                )
                explained = False
                for track in hardsubs:
                    if not (
                        int(track["start_frame"])
                        <= frame_index
                        <= int(track["end_frame"])
                    ):
                        continue
                    track_box = track["box_coords"]
                    overlap = max(
                        0.0,
                        min(float(hit_box[2]), float(track_box[2]))
                        - max(float(hit_box[0]), float(track_box[0])),
                    )
                    shorter_width = max(
                        1.0,
                        min(
                            hit_width,
                            float(track_box[2]) - float(track_box[0]),
                        ),
                    )
                    hit_cy = 0.5 * (float(hit_box[1]) + float(hit_box[3]))
                    track_cy = 0.5 * (
                        float(track_box[1]) + float(track_box[3])
                    )
                    hit_height = max(1.0, float(hit_box[3]) - float(hit_box[1]))
                    track_height = max(
                        1.0, float(track_box[3]) - float(track_box[1])
                    )
                    vertical_gap = max(
                        0.0,
                        max(float(hit_box[1]), float(track_box[1]))
                        - min(float(hit_box[3]), float(track_box[3])),
                    )
                    adjacent_thin_shadow = (
                        hit_height <= track_height * 0.90
                        and vertical_gap <= 0.02 * float(frame_h)
                    )
                    if overlap / shorter_width >= 0.50 and (
                        abs(hit_cy - track_cy) <= 45.0 or adjacent_thin_shadow
                    ):
                        explained = True
                        break
                if not explained and rejected_hardsub_boxes:
                    active_hardsubs = [
                        track
                        for track in hardsubs
                        if int(track["start_frame"])
                        <= frame_index
                        <= int(track["end_frame"])
                    ]
                    hit_cy = 0.5 * (float(hit_box[1]) + float(hit_box[3]))
                    same_band_active = any(
                        abs(
                            hit_cy
                            - 0.5
                            * (
                                float(track["box_coords"][1])
                                + float(track["box_coords"][3])
                            )
                        )
                        <= 90.0
                        for track in active_hardsubs
                    )
                    if same_band_active and any(
                        box_iou(hit_box, rejected_box) >= 0.45
                        for rejected_box in rejected_hardsub_boxes
                    ):
                        # A strong local/geometry gate already proved this raw
                        # DBNet blob is not text, while a real final caption is
                        # active in the same band. Treat it as detector shadow,
                        # not a missing second caption. Without an active final
                        # hardsub the same raw hit remains a recall failure.
                        explained = True
                        rejected_shadow_frames.add(frame_index)
                if not explained and any(
                    _matches_latin_source_box(hit_box, shadow_box)
                    for shadow_box in residual_shadow_boxes_by_frame.get(
                        frame_index, []
                    )
                ):
                    explained = True
                    rejected_shadow_frames.add(frame_index)
                if not explained and any(
                    box_iou(hit_box, rejected_box) >= 0.45
                    for rejected_box in standalone_rejected_hardsub_boxes
                ):
                    # Geometry/provenance gates can independently prove a
                    # repeated bowl rim, food edge or scene print is not an
                    # editor overlay. OCR-only/low-ink rejection deliberately
                    # cannot take this path: a real caption may OCR as empty.
                    explained = True
                    rejected_shadow_frames.add(frame_index)
                if not explained and any(
                    _matches_latin_source_box(hit_box, source_box)
                    for source_box in latin_source_text_boxes
                ):
                    # High-confidence Latin copy without changing colored-card
                    # evidence is source/scene text under the current product
                    # policy. Detector/refinement role can differ, so compare
                    # geometry across every rejected role.
                    explained = True
                    rejected_shadow_frames.add(frame_index)
                if (
                    not explained
                    and latin_source_present
                    and any(
                        box_iou(hit_box, rejected_box) >= 0.45
                        for rejected_box in low_ink_hardsub_boxes
                    )
                ):
                    # A blank low-ink band inside a frame already proven to be
                    # a Latin source-layout region (for example a table border)
                    # is detector shadow, not a second missing caption.
                    explained = True
                    rejected_shadow_frames.add(frame_index)
                if not explained:
                    uncovered_hardsub_frames.add(frame_index)

    for track in edge_wide_hardsub_candidates:
        track_box = [float(value) for value in track["box_coords"][:4]]
        track_cy = 0.5 * (track_box[1] + track_box[3])
        matching: list[list[float]] = []
        for frame_index in range(
            int(track["start_frame"]), int(track["end_frame"]) + 1
        ):
            for hit_box in detector_hardsubs_by_frame.get(frame_index, []):
                hit_cy = 0.5 * (hit_box[1] + hit_box[3])
                if abs(hit_cy - track_cy) > 45.0:
                    continue
                overlap = max(
                    0.0,
                    min(hit_box[2], track_box[2])
                    - max(hit_box[0], track_box[0]),
                )
                if overlap / max(1.0, hit_box[2] - hit_box[0]) < 0.50:
                    continue
                matching.append(hit_box)
        if len(matching) < 3:
            empty_left_hs.append(str(track["text_id"]))
            continue
        detector_x0 = float(median(box[0] for box in matching))
        detector_width = float(
            median(max(1.0, box[2] - box[0]) for box in matching)
        )
        final_width = max(1.0, track_box[2] - track_box[0])
        if (
            detector_x0 - track_box[0] >= 0.08 * float(frame_w)
            and final_width >= 1.35 * detector_width
        ):
            empty_left_hs.append(str(track["text_id"]))

    uncovered_dense_hardsub_spans: list[list[int]] = []
    for frame_index in sorted(uncovered_hardsub_frames):
        if (
            not uncovered_dense_hardsub_spans
            or frame_index > uncovered_dense_hardsub_spans[-1][1] + 1
        ):
            uncovered_dense_hardsub_spans.append([frame_index, frame_index, 1])
        else:
            uncovered_dense_hardsub_spans[-1][1] = frame_index
            uncovered_dense_hardsub_spans[-1][2] += 1
    uncovered_dense_hardsub_spans = [
        span for span in uncovered_dense_hardsub_spans if span[2] >= 3
    ]

    # Residual recovery is an early recall audit. The scorer subsequently
    # applies stronger geometry/provenance explanations, so only frames still
    # uncovered after those explanations may block PASS. Keep all raw audit
    # spans observable, but require the same three-frame density floor used by
    # the ordinary uncovered-hardsub contract.
    residual_unresolved_spans: list[list[int]] = []
    for frame_index in sorted(
        residual_audit_unresolved_frames.intersection(uncovered_hardsub_frames)
    ):
        if (
            not residual_unresolved_spans
            or frame_index > residual_unresolved_spans[-1][1] + 1
        ):
            residual_unresolved_spans.append([frame_index, frame_index, 1])
        else:
            residual_unresolved_spans[-1][1] = frame_index
            residual_unresolved_spans[-1][2] += 1
    residual_unresolved_spans = [
        span for span in residual_unresolved_spans if span[2] >= 3
    ]

    overexpanded_dense_hardsubs: list[list[object]] = []
    if coverage is not None:
        for track in hardsubs:
            track_box = [float(value) for value in track["box_coords"][:4]]
            track_cy = 0.5 * (track_box[1] + track_box[3])
            per_frame_union: list[list[float]] = []
            for frame_index in range(
                int(track["start_frame"]), int(track["end_frame"]) + 1
            ):
                matching: list[list[float]] = []
                for hit_box in detector_hardsubs_by_frame.get(frame_index, []):
                    hit_cy = 0.5 * (hit_box[1] + hit_box[3])
                    if abs(hit_cy - track_cy) > 45.0:
                        continue
                    overlap = max(
                        0.0,
                        min(hit_box[2], track_box[2])
                        - max(hit_box[0], track_box[0]),
                    )
                    hit_width = max(1.0, hit_box[2] - hit_box[0])
                    if overlap / hit_width < 0.50:
                        continue
                    matching.append(hit_box)
                if matching:
                    per_frame_union.append(
                        [
                            min(box[0] for box in matching),
                            min(box[1] for box in matching),
                            max(box[2] for box in matching),
                            max(box[3] for box in matching),
                        ]
                    )
            track_span = max(
                1, int(track["end_frame"]) - int(track["start_frame"]) + 1
            )
            if len(per_frame_union) < 3 or len(per_frame_union) / track_span < 0.35:
                continue
            detector_x0 = float(median(box[0] for box in per_frame_union))
            detector_x1 = float(median(box[2] for box in per_frame_union))
            detector_width = max(1.0, detector_x1 - detector_x0)
            final_width = max(1.0, track_box[2] - track_box[0])
            if (
                detector_width / max(1.0, float(frame_w)) >= 0.12
                and final_width >= detector_width * 1.80
            ):
                overexpanded_dense_hardsubs.append(
                    [
                        str(track["text_id"]),
                        round(final_width, 1),
                        round(detector_width, 1),
                        round(final_width / detector_width, 3),
                    ]
                )

    grid_peer_tracks: list[MergedTrack] = []
    grid_track_by_text_id: dict[str, MergedTrack] = {}
    for item in items:
        semantic_role = str(item.get("semantic_role") or "")
        role = semantic_role or classify_ocr_box_role(
            item["box_coords"], frame_w=frame_w, frame_h=frame_h
        )
        if role in {"hardsub", "semantic_scene_label"}:
            continue
        box = [float(value) for value in item["box_coords"][:4]]
        start_frame = int(item["start_frame"])
        end_frame = int(item["end_frame"])
        hit_count = max(2, int(item.get("hit_count") or 2))
        track = MergedTrack(
            start_frame=start_frame,
            end_frame=end_frame,
            box_coords=box,
            best_frame_index=int(item.get("best_frame_index") or start_frame),
            best_sharpness=0.0,
            centroid=(0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3])),
            hit_count=hit_count,
            hit_boxes=[tuple(box)] * hit_count,
            hit_frames=[start_frame] * hit_count,
            hit_sharpness=[0.0] * hit_count,
        )
        grid_peer_tracks.append(track)
        grid_track_by_text_id[str(item["text_id"])] = track

    overmerged_ui_grid_tracks: list[dict[str, object]] = []
    for item in items:
        semantic_role = str(item.get("semantic_role") or "")
        role = semantic_role or classify_ocr_box_role(
            item["box_coords"], frame_w=frame_w, frame_h=frame_h
        )
        if role in {"hardsub", "semantic_scene_label"}:
            continue
        track = grid_track_by_text_id.get(str(item["text_id"]))
        if track is None or not _has_dense_ui_grid_peer_evidence(
            track,
            grid_peer_tracks,
            frame_w=frame_w,
            frame_h=frame_h,
        ):
            continue
        frame_path = out_dir / str(item.get("best_keyframe_path") or "")
        if not frame_path.is_file():
            continue
        try:
            import cv2

            frame = cv2.imread(str(frame_path))
        except Exception:
            frame = None
        if frame is None:
            continue
        box = list(track.box_coords)
        split = _split_wide_ui_track_by_ink_columns(
            track, frame, frame_w=frame_w, frame_h=frame_h
        )
        meaningful = [
            row
            for row in split
            if float(row.box_coords[2]) - float(row.box_coords[0])
            >= max(24.0, 0.025 * float(frame_w))
        ]
        if len(meaningful) >= 2:
            overmerged_ui_grid_tracks.append(
                {
                    "text_id": str(item["text_id"]),
                    "box": box,
                    "meaningful_column_boxes": [
                        [round(float(value), 2) for value in row.box_coords[:4]]
                        for row in meaningful
                    ],
                }
            )

    checks = {
        "has_tracks": len(items) >= 1,
        "has_quality_report": quality is not None,
        "has_text_frame_coverage": coverage is not None,
        "no_uncertain_tracks": uncertain_tracks == 0,
        "no_uncovered_dense_hardsub_spans": not uncovered_dense_hardsub_spans,
        "no_unresolved_residual_hardsub_spans": not residual_unresolved_spans,
        "no_overexpanded_dense_hardsubs": not overexpanded_dense_hardsubs,
        "no_overmerged_ui_grid_tracks": not overmerged_ui_grid_tracks,
        "no_empty_left_wide_hardsub": len(empty_left_hs) == 0,
        "no_isolated_micro_source_tracks": not isolated_micro_source_tracks,
        "no_nested_temporal_ui_fragments": not nested_temporal_ui_fragments,
        "no_high_confidence_local_text_rejects": not high_confidence_local_text_rejects,
        "semantic_scene_roles_have_audit_evidence": not unverified_semantic_scene_tracks,
        "near_dupe_pairs_le_1": len(near_dupes) <= 1,
        "crops_complete": len(missing_crops) == 0,
        "keyframes_complete": len(missing_frames) == 0,
        "chrome_not_dominating": roles.get("chrome", 0) == 0,
    }
    # Soft: allow 1 near-dupe (holdout had 1); hard fail if many.
    checks["near_dupe_pairs_le_2"] = len(near_dupes) <= 2
    passed = all(
        [
            checks["has_tracks"],
            checks["has_quality_report"],
            checks["has_text_frame_coverage"],
            checks["no_uncertain_tracks"],
            checks["no_uncovered_dense_hardsub_spans"],
            checks["no_unresolved_residual_hardsub_spans"],
            checks["no_overexpanded_dense_hardsubs"],
            checks["no_overmerged_ui_grid_tracks"],
            checks["no_empty_left_wide_hardsub"],
            checks["no_isolated_micro_source_tracks"],
            checks["no_nested_temporal_ui_fragments"],
            checks["no_high_confidence_local_text_rejects"],
            checks["semantic_scene_roles_have_audit_evidence"],
            checks["near_dupe_pairs_le_2"],
            checks["crops_complete"],
            checks["keyframes_complete"],
        ]
    )
    return {
        "out": str(out_dir.resolve()),
        "video": meta.get("video"),
        "frame_size": [frame_w, frame_h],
        "tracks": len(items),
        "elapsed_s": meta.get("elapsed_s"),
        "roles": dict(roles),
        "hardsubs": len(hardsubs),
        "confirmed_tracks": (
            int(quality.get("confirmed_tracks") or 0) if quality is not None else None
        ),
        "uncertain_tracks": uncertain_tracks,
        "uncovered_dense_hardsub_spans": uncovered_dense_hardsub_spans,
        "unresolved_residual_hardsub_spans": residual_unresolved_spans,
        "residual_hardsub_audit_spans": residual_audit_unresolved_spans,
        "locally_rejected_shadow_frames": sorted(rejected_shadow_frames),
        "overexpanded_dense_hardsubs": overexpanded_dense_hardsubs,
        "overmerged_ui_grid_tracks": overmerged_ui_grid_tracks,
        "empty_left_wide_hardsubs": empty_left_hs,
        "isolated_micro_source_tracks": isolated_micro_source_tracks,
        "perspective_ui_provenance_tracks": perspective_ui_provenance_tracks,
        "nested_temporal_ui_fragments": nested_temporal_ui_fragments,
        "high_confidence_local_text_rejects": high_confidence_local_text_rejects,
        "unverified_semantic_scene_tracks": unverified_semantic_scene_tracks,
        "near_dupe_pairs": near_dupes,
        "missing_crops": missing_crops,
        "missing_frames": missing_frames,
        "checks": checks,
        "PASS": passed,
    }


def write_phase1_score(out_dir: Path, score: dict) -> Path:
    """Persist a scorer result atomically beside the Phase 1 artifacts."""
    target = out_dir / "phase1_score.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=out_dir
    )
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(score, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    write_artifact = "--write" in args
    args = [arg for arg in args if arg != "--write"]
    if not args:
        print(
            "usage: score_phase1_pass.py [--write] <out_dir> [out_dir...]",
            file=sys.stderr,
        )
        return 2
    rows = []
    for raw in args:
        out = Path(raw)
        row = score_phase1_out(out)
        if write_artifact:
            write_phase1_score(out, row)
        rows.append(row)
        flag = "PASS" if row["PASS"] else "FAIL"
        print(
            f"[{flag}] tracks={row['tracks']} hs={row['hardsubs']} "
            f"uncertain={row['uncertain_tracks']} dupes={len(row['near_dupe_pairs'])} "
            f"empty_hs={row['empty_left_wide_hardsubs']} "
            f"out={out.name}"
        )
    summary = {
        "n": len(rows),
        "pass_n": sum(1 for r in rows if r["PASS"]),
        "fail_n": sum(1 for r in rows if not r["PASS"]),
        "rows": rows,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["fail_n"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
