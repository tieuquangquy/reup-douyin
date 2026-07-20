"""Best-effort OCR box authority for production payloads (Phase 2 post-process)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2

from src.media_pipeline.ocr_filtering.box_geometry_refine import refine_timed_boxes_from_jpeg
from src.media_pipeline.ocr_filtering.box_timeline_tracker import OcrObservation, TimedBox
from src.media_pipeline.ocr_filtering.clean_box_authority import (
    apply_temporal_consensus,
    clean_observation_boxes,
    collapse_nearby_observations,
)
from src.media_pipeline.ocr_filtering.per_frame_ink_scan import scan_refine_boxes_on_frame

logger = logging.getLogger(__name__)


def _timed_from_dict(b: dict[str, Any]) -> TimedBox:
    return TimedBox(
        x=float(b["x"]),
        y=float(b["y"]),
        w=float(b.get("w") if "w" in b else b.get("width") or 0),
        h=float(b.get("h") if "h" in b else b.get("height") or 0),
        text=str(b.get("text") or ""),
        confidence=float(b.get("confidence") or b.get("score") or 0.0),
    )


def _boxes_to_dicts(boxes: list[TimedBox]) -> list[dict[str, Any]]:
    return [b.to_dict() for b in boxes]


def _observations_from_payload(frames: list[dict[str, Any]]) -> list[OcrObservation]:
    out: list[OcrObservation] = []
    for fr in frames:
        if not isinstance(fr, dict):
            continue
        time_ms = int(fr.get("time_ms") or 0)
        raw = [_timed_from_dict(b) for b in fr.get("boxes") or [] if isinstance(b, dict)]
        cleaned = clean_observation_boxes(raw)
        out.append(OcrObservation(time_ms=time_ms, boxes=tuple(cleaned)))
    return out


def apply_best_box_authority(
    ocr_payload: dict[str, Any],
    *,
    frame_paths: list[Path] | None = None,
    consensus_min_hits: int = 2,
    collapse_gap_ms: int = 900,
) -> dict[str, Any]:
    """
    Clean + temporal consensus + collapse + per-frame ink/band scan.

    Keeps the original frame list shape (one entry per Phase-1 sample) so render
    hold logic is unchanged; box geometry/text are upgraded in place.
    """
    frames = list(ocr_payload.get("frames") or [])
    if not frames:
        return ocr_payload

    observations = _observations_from_payload(frames)
    observations = apply_temporal_consensus(
        observations,
        min_hits=int(consensus_min_hits),
    )
    collapsed = collapse_nearby_observations(observations, gap_ms=int(collapse_gap_ms))
    by_time = {int(o.time_ms): o for o in collapsed}

    path_by_time: dict[int, Path] = {}
    if frame_paths:
        for i, fr in enumerate(frames):
            if i >= len(frame_paths):
                break
            if isinstance(fr, dict):
                path_by_time[int(fr.get("time_ms") or 0)] = Path(frame_paths[i])

    upgraded: list[dict[str, Any]] = []
    for fr in frames:
        if not isinstance(fr, dict):
            upgraded.append(fr)
            continue
        time_ms = int(fr.get("time_ms") or 0)
        obs = by_time.get(time_ms)
        if obs is None:
            # Nearest collapsed observation within gap (caption hold).
            nearest: OcrObservation | None = None
            best_dt = collapse_gap_ms + 1
            for t_ms, candidate in by_time.items():
                dt = abs(int(t_ms) - time_ms)
                if dt <= collapse_gap_ms and dt < best_dt:
                    best_dt = dt
                    nearest = candidate
            obs = nearest
        boxes = list(obs.boxes) if obs is not None else []

        jpeg = path_by_time.get(time_ms)
        if jpeg is not None and jpeg.is_file() and boxes:
            bgr = cv2.imread(str(jpeg))
            if bgr is not None:
                boxes = scan_refine_boxes_on_frame(bgr, boxes, use_band_scan=True)
            else:
                boxes = refine_timed_boxes_from_jpeg(jpeg, boxes, expand_hardsub=True)
        elif jpeg is not None and jpeg.is_file() and not boxes:
            pass

        new_fr = dict(fr)
        new_fr["boxes"] = _boxes_to_dicts(boxes)
        upgraded.append(new_fr)

    out = dict(ocr_payload)
    out["frames"] = upgraded
    out["box_authority"] = "best_v6_inkscan"
    logger.info(
        "ocr_box_authority_applied frames=%s collapsed_ticks=%s",
        len(upgraded),
        len(collapsed),
    )
    return out
