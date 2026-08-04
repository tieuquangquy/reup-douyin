"""Zones for hard-sub + mid-title overlays (+ dense end-card).

Pilot A kept only the bottom band. Mid-frame titles (dish name / kcal) and
dense end-card UIs need keep rules without OCR-ing tiny top logos.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.media_pipeline.ocr_filtering.subtitle_band import (
    BOTTOM_BAND_RATIO,
    is_in_subtitle_band,
)
from src.media_pipeline.ocr_filtering.types import DetectedTextBox

# OCR crop starts here so mid titles are visible without full-frame upload.
OVERLAY_CROP_TOP = 0.20

MID_TITLE_Y_MIN = 0.22
# Stay above hardsub band top (~0.667); overlap caused band-stuck captions to be
# treated as mid-titles and then dropped by hardsub_min_center_y.
MID_TITLE_Y_MAX = 0.65
MID_TITLE_MIN_HEIGHT = 0.035
MID_TITLE_MIN_WIDTH = 0.18
MID_TITLE_CENTER_X_MIN = 0.12
MID_TITLE_CENTER_X_MAX = 0.88

# Compact action labels (加盐 / 花): narrower than mid-title but still mid-frame.
COMPACT_LABEL_Y_MIN = 0.28
COMPACT_LABEL_Y_MAX = 0.62
COMPACT_LABEL_MIN_HEIGHT = 0.028
COMPACT_LABEL_MIN_WIDTH = 0.055
COMPACT_LABEL_MAX_WIDTH = 0.35
COMPACT_LABEL_CENTER_X_MIN = 0.05
COMPACT_LABEL_CENTER_X_MAX = 0.95

ENDCARD_MIN_BOXES = 4
ENDCARD_MANY_BOXES = 6
# Real PaddleOCR UI crumbs are tiny; allow lower area when count/span is high.
ENDCARD_MIN_AREA = 0.08
ENDCARD_MIN_Y_SPAN = 0.50
ENDCARD_MANY_MIN_Y_SPAN = 0.35
ENDCARD_MULTI_CLUSTER = 3
# Last 20% of the clip: any OCR text → force opaque UI panel (endcard nuke).
ENDCARD_LATE_CLIP_RATIO = 0.80

CLUSTER_Y_GAP = 0.08


def _as_box_mapping(box: DetectedTextBox | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(box, DetectedTextBox):
        return {
            "x": box.x,
            "y": box.y,
            "width": box.width,
            "height": box.height,
            "text": box.text,
            "confidence": box.confidence,
        }
    return box


def _box_center_x(box: DetectedTextBox | Mapping[str, Any]) -> float:
    if isinstance(box, DetectedTextBox):
        return box.x + box.width / 2.0
    x = float(box.get("x") or 0.0)
    w = float(box.get("width") or 0.0)
    return x + w / 2.0


def _box_center_y(box: DetectedTextBox | Mapping[str, Any]) -> float:
    if isinstance(box, DetectedTextBox):
        return box.center_y
    y = float(box.get("y") or 0.0)
    h = float(box.get("height") or 0.0)
    return y + h / 2.0


def _box_width(box: DetectedTextBox | Mapping[str, Any]) -> float:
    if isinstance(box, DetectedTextBox):
        return box.width
    return float(box.get("width") or 0.0)


def _box_height(box: DetectedTextBox | Mapping[str, Any]) -> float:
    if isinstance(box, DetectedTextBox):
        return box.height
    return float(box.get("height") or 0.0)


def boxes_area_sum(boxes: Sequence[DetectedTextBox | Mapping[str, Any]]) -> float:
    area = 0.0
    for box in boxes:
        area += max(0.0, _box_width(box)) * max(0.0, _box_height(box))
    return area


def boxes_y_span(boxes: Sequence[DetectedTextBox | Mapping[str, Any]]) -> float:
    if not boxes:
        return 0.0
    tops: list[float] = []
    bottoms: list[float] = []
    for box in boxes:
        y = float(_as_box_mapping(box).get("y") or 0.0)
        h = max(0.0, _box_height(box))
        tops.append(y)
        bottoms.append(y + h)
    return max(0.0, max(bottoms) - min(tops))


def is_mid_title_box(box: DetectedTextBox | Mapping[str, Any]) -> bool:
    """Large, roughly centered text in the middle third (not bottom hard-sub)."""
    cy = _box_center_y(box)
    cx = _box_center_x(box)
    w = _box_width(box)
    h = _box_height(box)
    if cy < MID_TITLE_Y_MIN or cy > MID_TITLE_Y_MAX:
        return False
    if h < MID_TITLE_MIN_HEIGHT:
        return False
    # Always require width — tall-narrow action labels (加盐) are compact, not titles.
    if w < MID_TITLE_MIN_WIDTH:
        return False
    if cx < MID_TITLE_CENTER_X_MIN or cx > MID_TITLE_CENTER_X_MAX:
        return False
    return True


def is_compact_overlay_label(box: DetectedTextBox | Mapping[str, Any]) -> bool:
    """Short mid-frame action labels (e.g. 加盐) that fail the wide mid-title gate."""
    if is_mid_title_box(box):
        return False
    cy = _box_center_y(box)
    cx = _box_center_x(box)
    w = _box_width(box)
    h = _box_height(box)
    if cy < COMPACT_LABEL_Y_MIN or cy > COMPACT_LABEL_Y_MAX:
        return False
    if h < COMPACT_LABEL_MIN_HEIGHT or h > 0.09:
        return False
    if w < COMPACT_LABEL_MIN_WIDTH or w > COMPACT_LABEL_MAX_WIDTH:
        return False
    if cx < COMPACT_LABEL_CENTER_X_MIN or cx > COMPACT_LABEL_CENTER_X_MAX:
        return False
    return True


def is_endcard_dense(boxes: Sequence[DetectedTextBox | Mapping[str, Any]]) -> bool:
    """
    True when the frame looks like a full-screen nutrition/UI card.

    OR of several signals — PaddleOCR often returns many tiny boxes whose
    summed area stays below the old 0.15 floor.
    """
    n = len(boxes)
    if n < 3:
        return False
    area = boxes_area_sum(boxes)
    span = boxes_y_span(boxes)
    if n >= ENDCARD_MANY_BOXES and (area >= 0.05 or span >= ENDCARD_MANY_MIN_Y_SPAN):
        return True
    if n >= ENDCARD_MIN_BOXES and area >= ENDCARD_MIN_AREA:
        return True
    if n >= ENDCARD_MIN_BOXES and span >= ENDCARD_MIN_Y_SPAN:
        return True
    clusters = cluster_boxes_by_y(boxes)
    if len(clusters) >= ENDCARD_MULTI_CLUSTER and n >= 4 and span >= 0.40:
        return True
    return False


def is_late_clip_ui_frame(
    time_ms: int,
    duration_ms: int | None,
    boxes: Sequence[DetectedTextBox | Mapping[str, Any]],
) -> bool:
    """True when timeline is in the last 20% and OCR saw any boxes.

    Kept for diagnostics / callers; overlay build no longer force-panels on late
    alone (that produced the ugly slate when OCR only returned the caption).
    """
    if not boxes:
        return False
    dur = int(duration_ms or 0)
    if dur <= 0:
        return False
    return int(time_ms) >= int(dur * ENDCARD_LATE_CLIP_RATIO)


def overlay_kind_for_box(box: DetectedTextBox | Mapping[str, Any]) -> str:
    """Classify one OCR box: bottom hard-sub strip vs mid title vs generic UI label."""
    if isinstance(box, DetectedTextBox):
        detected = box
    else:
        detected = DetectedTextBox(
            x=float(box.get("x") or 0.0),
            y=float(box.get("y") or 0.0),
            width=max(0.01, float(box.get("width") or 0.01)),
            height=max(0.01, float(box.get("height") or 0.01)),
            text=str(box.get("text") or ""),
            confidence=float(box.get("confidence") or 0.0),
        )
    if is_in_subtitle_band(detected):
        return "hardsub"
    if is_mid_title_box(detected):
        return "title"
    return "ui"


def filter_overlay_boxes(
    boxes: list[DetectedTextBox],
    *,
    band_ratio: float = BOTTOM_BAND_RATIO,
) -> list[DetectedTextBox]:
    """Keep bottom hard-sub, mid titles, or all boxes on dense end-cards."""
    if not boxes:
        return []
    if is_endcard_dense(boxes):
        return list(boxes)
    kept: list[DetectedTextBox] = []
    for box in boxes:
        if is_in_subtitle_band(box, band_ratio=band_ratio) or is_mid_title_box(box):
            kept.append(box)
    return kept


def cluster_boxes_by_y(
    boxes: Sequence[DetectedTextBox | Mapping[str, Any]],
    *,
    gap: float = CLUSTER_Y_GAP,
) -> list[list[Mapping[str, Any]]]:
    """Group boxes that sit on nearby horizontal bands (title vs hard-sub)."""
    mapped = [_as_box_mapping(b) for b in boxes]
    if not mapped:
        return []
    ordered = sorted(mapped, key=lambda b: float(b.get("y") or 0.0))
    clusters: list[list[Mapping[str, Any]]] = [[ordered[0]]]
    for box in ordered[1:]:
        prev = clusters[-1][-1]
        prev_bottom = float(prev.get("y") or 0.0) + float(prev.get("height") or 0.0)
        y = float(box.get("y") or 0.0)
        if y - prev_bottom <= gap:
            clusters[-1].append(box)
        else:
            clusters.append([box])
    return clusters


def overlay_kind_for_cluster(cluster: Sequence[Mapping[str, Any]]) -> str:
    """Classify a cluster for pad/expand policy."""
    if not cluster:
        return "hardsub"
    # Synthetic DetectedTextBox for helpers.
    boxes = [
        DetectedTextBox(
            x=float(b.get("x") or 0.0),
            y=float(b.get("y") or 0.0),
            width=max(0.01, float(b.get("width") or 0.01)),
            height=max(0.01, float(b.get("height") or 0.01)),
            text=str(b.get("text") or ""),
            confidence=float(b.get("confidence") or 0.0),
        )
        for b in cluster
    ]
    if is_endcard_dense(boxes):
        return "endcard"
    # Majority vote by center_y.
    mid = sum(1 for b in boxes if is_mid_title_box(b))
    bottom = sum(1 for b in boxes if is_in_subtitle_band(b))
    if bottom > mid and bottom > 0:
        return "hardsub"
    if mid > 0:
        return "title"
    # Top / misc on-screen text: pad only (do not force full-width hard-sub strip).
    return "title"


def overlay_crop_top_normalized(*, include_mid_title: bool = True) -> float:
    if include_mid_title:
        return OVERLAY_CROP_TOP
    return 1.0 - BOTTOM_BAND_RATIO
