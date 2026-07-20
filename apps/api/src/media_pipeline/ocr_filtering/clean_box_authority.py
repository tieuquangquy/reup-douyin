"""Clean OCR boxes into blur/sub authority: CJK + conf + zone + line merge + consensus."""

from __future__ import annotations

from typing import Sequence

from src.media_pipeline.ocr_filtering.box_timeline_tracker import (
    OcrObservation,
    TimedBox,
    box_iou,
    match_boxes_by_iou,
)
from src.media_pipeline.ocr_filtering.overlay_zones import is_mid_title_box
from src.media_pipeline.ocr_filtering.script_filter import contains_cjk
from src.media_pipeline.ocr_filtering.subtitle_band import (
    BOTTOM_BAND_RATIO,
    is_in_subtitle_band,
)
from src.media_pipeline.ocr_filtering.types import DetectedTextBox

DEFAULT_MIN_CONFIDENCE = 0.75
DEFAULT_MIN_CJK_CHARS = 2
DEFAULT_LINE_Y_GAP = 0.04
DEFAULT_CONSENSUS_IOU = 0.3
DEFAULT_CONSENSUS_MAX_GAP_MS = 1500
# Hard-sub glyphs sit near the bottom edge; band-top (~0.67) hits are almost always wrong.
DEFAULT_HARDSUB_MIN_CENTER_Y = 0.85
DEFAULT_HARDSUB_SNAP_Y = 0.91
DEFAULT_HARDSUB_SNAP_H = 0.055


def _cjk_char_count(text: str) -> int:
    return sum(1 for ch in (text or "") if "\u4e00" <= ch <= "\u9fff")


def _to_detected(box: TimedBox) -> DetectedTextBox:
    return DetectedTextBox(
        x=box.x,
        y=box.y,
        width=max(0.001, box.w),
        height=max(0.001, box.h),
        text=box.text,
        confidence=box.confidence,
    )


def repair_implausible_caption_geometry(box: TimedBox) -> TimedBox:
    """
    Cloud OCR sometimes returns hardsub CJK with absurd geometry (y≈0, ultra-tall)
    or stuck near the subtitle-band top (cy≈0.67–0.72) while text is correct.

    Never snap mid-title boxes — that moved dish titles to the bottom (f0 bug).
    """
    if _cjk_char_count(box.text) < 4:
        return box
    if is_mid_title_box(_to_detected(box)):
        return box
    cy = float(box.y) + float(box.h) / 2.0
    # Soft mid-zone guard (titles below band) even if width gate fails.
    if 0.22 <= cy < 0.65 and float(box.h) <= 0.12:
        return box

    band_stuck = (
        float(box.w) >= 0.2
        and float(box.h) <= 0.12
        and 0.65 <= cy < float(DEFAULT_HARDSUB_MIN_CENTER_Y)
    )
    implausible = float(box.h) > 0.2 or (cy < 0.35 and float(box.h) > 0.12)
    if not band_stuck and not implausible:
        return box
    width = float(box.w)
    if width < 0.25:
        width = 0.55
    x = float(box.x)
    if x < 0.0 or x > 0.7:
        x = max(0.08, (1.0 - width) / 2.0)
    return TimedBox(
        x=min(0.85, max(0.02, x)),
        y=DEFAULT_HARDSUB_SNAP_Y,
        w=min(0.9, width),
        h=DEFAULT_HARDSUB_SNAP_H,
        text=box.text,
        confidence=box.confidence,
    )


def filter_authority_boxes(
    boxes: Sequence[TimedBox],
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    min_cjk_chars: int = DEFAULT_MIN_CJK_CHARS,
    band_ratio: float = BOTTOM_BAND_RATIO,
    hardsub_min_center_y: float = DEFAULT_HARDSUB_MIN_CENTER_Y,
) -> list[TimedBox]:
    """Keep CJK boxes in hardsub band (low enough) or mid-title zone with enough confidence."""
    kept: list[TimedBox] = []
    for box in boxes:
        box = repair_implausible_caption_geometry(box)
        text = (box.text or "").strip()
        if not contains_cjk(text):
            continue
        if _cjk_char_count(text) < int(min_cjk_chars):
            continue
        if float(box.confidence) < float(min_confidence):
            continue
        detected = _to_detected(box)
        if is_in_subtitle_band(detected, band_ratio=band_ratio):
            if float(detected.center_y) + 1e-9 < float(hardsub_min_center_y):
                continue
            kept.append(box)
            continue
        if is_mid_title_box(detected):
            kept.append(box)
    return kept


def merge_horizontal_line_boxes(
    boxes: Sequence[TimedBox],
    *,
    y_gap: float = DEFAULT_LINE_Y_GAP,
) -> list[TimedBox]:
    """Merge same-row boxes (sorted by x) into one line box per row cluster."""
    if not boxes:
        return []
    ordered = sorted(boxes, key=lambda b: (b.y + b.h / 2.0, b.x))
    clusters: list[list[TimedBox]] = [[ordered[0]]]
    for box in ordered[1:]:
        prev = clusters[-1][-1]
        cy = box.y + box.h / 2.0
        py = prev.y + prev.h / 2.0
        if abs(cy - py) <= float(y_gap):
            clusters[-1].append(box)
        else:
            clusters.append([box])

    merged: list[TimedBox] = []
    for group in clusters:
        group = sorted(group, key=lambda b: b.x)
        if len(group) >= 2:
            widest = max(group, key=lambda b: float(b.w))
            total_chars = sum(_cjk_char_count(b.text) for b in group)
            if float(widest.w) >= 0.42 and _cjk_char_count(widest.text) >= int(total_chars * 0.65):
                group = [widest]
        x0 = min(b.x for b in group)
        y0 = min(b.y for b in group)
        x1 = max(b.x + b.w for b in group)
        y1 = max(b.y + b.h for b in group)
        text = "".join((b.text or "").strip() for b in group)
        conf = max(b.confidence for b in group)
        merged.append(
            TimedBox(
                x=x0,
                y=y0,
                w=max(0.001, x1 - x0),
                h=max(0.001, y1 - y0),
                text=text,
                confidence=conf,
            )
        )
    return merged


def _box_score(box: TimedBox) -> float:
    det = _to_detected(box)
    if is_in_subtitle_band(det):
        return _cjk_char_count(box.text) * 100.0 + float(box.w)
    if is_mid_title_box(det):
        return _cjk_char_count(box.text) * 50.0 + float(box.w)
    return 0.0


def collapse_nearby_observations(
    observations: Sequence[OcrObservation],
    *,
    gap_ms: int = 900,
) -> list[OcrObservation]:
    """
    Merge OCR bursts within ``gap_ms`` — assign best hardsub line to earliest tick.

    Fixes fragmented Paddle boxes (wrong x-order merge) when a later tick in the
    same caption has a full-width line.
    """
    obs = sorted(observations, key=lambda o: o.time_ms)
    if not obs:
        return []
    out: list[OcrObservation] = []
    i = 0
    while i < len(obs):
        group = [obs[i]]
        j = i + 1
        while j < len(obs) and int(obs[j].time_ms) - int(group[0].time_ms) <= int(gap_ms):
            group.append(obs[j])
            j += 1

        earliest_ms = int(group[0].time_ms)
        best_hard: TimedBox | None = None
        best_hard_score = -1.0
        mid_boxes: list[TimedBox] = []
        for o in group:
            for box in o.boxes:
                det = _to_detected(box)
                if is_mid_title_box(det):
                    mid_boxes.append(box)
                elif is_in_subtitle_band(det):
                    score = _box_score(box)
                    if score > best_hard_score:
                        best_hard_score = score
                        best_hard = box

        kept: list[TimedBox] = []
        seen_mid: list[TimedBox] = []
        for box in mid_boxes:
            if not any(box_iou(box, s) >= 0.5 for s in seen_mid):
                seen_mid.append(box)
                kept.append(box)
        if best_hard is not None:
            kept.append(best_hard)
        out.append(OcrObservation(time_ms=earliest_ms, boxes=tuple(kept)))
        i = j
    return out


def clean_observation_boxes(
    boxes: Sequence[TimedBox],
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    min_cjk_chars: int = DEFAULT_MIN_CJK_CHARS,
) -> list[TimedBox]:
    """Filter then merge lines — one observation's authority boxes."""
    return merge_horizontal_line_boxes(
        filter_authority_boxes(
            boxes,
            min_confidence=min_confidence,
            min_cjk_chars=min_cjk_chars,
        )
    )


def apply_temporal_consensus(
    observations: Sequence[OcrObservation],
    *,
    min_hits: int = 2,
    iou_thresh: float = DEFAULT_CONSENSUS_IOU,
    max_gap_ms: int = DEFAULT_CONSENSUS_MAX_GAP_MS,
    allow_single_mid_title: bool = True,
    allow_single_strong_line: bool = True,
    mid_title_min_confidence: float = 0.85,
    strong_line_min_confidence: float = 0.9,
    strong_line_min_cjk: int = 4,
    strong_line_min_width: float = 0.2,
) -> list[OcrObservation]:
    """
    Keep a box only if it matches a neighbor tick (IoU) within ``max_gap_ms``.

    Exceptions (single tick allowed):
    - Mid-title with high confidence
    - Long CJK hardsub/title line (conf + width) — sparse OCR often hits once
    """
    obs = sorted(observations, key=lambda o: o.time_ms)
    if not obs:
        return []
    if int(min_hits) <= 1:
        return [
            OcrObservation(time_ms=o.time_ms, boxes=tuple(clean_observation_boxes(o.boxes)))
            for o in obs
        ]

    cleaned = [
        OcrObservation(time_ms=o.time_ms, boxes=tuple(clean_observation_boxes(o.boxes)))
        for o in obs
    ]
    out: list[OcrObservation] = []
    for i, cur in enumerate(cleaned):
        kept: list[TimedBox] = []
        for box in cur.boxes:
            hits = 1
            for j, other in enumerate(cleaned):
                if i == j:
                    continue
                if abs(other.time_ms - cur.time_ms) > int(max_gap_ms):
                    continue
                matched = match_boxes_by_iou([box], other.boxes, iou_thresh=iou_thresh)
                if matched:
                    hits += 1
            if hits >= int(min_hits):
                kept.append(box)
                continue
            detected = _to_detected(box)
            if (
                allow_single_mid_title
                and is_mid_title_box(detected)
                and float(box.confidence) >= float(mid_title_min_confidence)
                and contains_cjk(box.text)
            ):
                kept.append(box)
                continue
            if (
                allow_single_strong_line
                and (is_in_subtitle_band(detected) or is_mid_title_box(detected))
                and _cjk_char_count(box.text) >= int(strong_line_min_cjk)
                and float(box.confidence) >= float(strong_line_min_confidence)
                and float(box.w) >= float(strong_line_min_width)
            ):
                kept.append(box)
        out.append(OcrObservation(time_ms=cur.time_ms, boxes=tuple(kept)))
    return out
