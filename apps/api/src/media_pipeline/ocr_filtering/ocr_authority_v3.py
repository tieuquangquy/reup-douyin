"""Evidence-gated OCR geometry authority.

Local geometry alone cannot create a renderable box. Verified text evidence
comes from Cloud OCR or local CTC recognition (CJK). This boundary prevents
food, knives, and bright UI surfaces from being treated as subtitles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

from src.media_pipeline.ocr_filtering.box_timeline_tracker import TimedBox, box_iou
from src.media_pipeline.ocr_filtering.overlay_zones import (
    is_endcard_dense,
    is_mid_title_box,
)
from src.media_pipeline.ocr_filtering.script_filter import contains_cjk
from src.media_pipeline.ocr_filtering.subtitle_band import is_in_subtitle_band
from src.media_pipeline.ocr_filtering.types import DetectedTextBox

FrameState = Literal["blank", "hardsub", "title", "endcard"]

DEFAULT_EVIDENCE_CONFIDENCE = 0.75
MAX_HARDSUB_HEIGHT = 0.12
MAX_HARDSUB_AREA = 0.08
MAX_HARDSUB_WIDTH = 0.90
LOCAL_MATCH_MIN_IOU = 0.12
LOCAL_MATCH_MAX_CENTER_DISTANCE = 0.08
ENDCARD_LOCAL_MIN_RATIO = 0.75


@dataclass(frozen=True)
class FrameEvidence:
    frame_index: int
    time_ms: int
    local_boxes: tuple[TimedBox, ...] = ()
    ocr_boxes: tuple[TimedBox, ...] = ()
    timeline_ratio: float = 0.0


@dataclass(frozen=True)
class EndcardSegment:
    segment_id: int
    start_ms: int
    end_ms: int
    candidate_times_ms: tuple[int, ...]


def _to_detected(box: TimedBox) -> DetectedTextBox:
    return DetectedTextBox(
        x=float(box.x),
        y=float(box.y),
        width=max(0.001, float(box.w)),
        height=max(0.001, float(box.h)),
        text=str(box.text or ""),
        confidence=float(box.confidence),
    )


def _has_box_evidence(
    box: TimedBox,
    *,
    min_confidence: float = DEFAULT_EVIDENCE_CONFIDENCE,
) -> bool:
    return (
        bool((box.text or "").strip())
        and float(box.confidence) >= float(min_confidence)
        and float(box.w) > 0.0
        and float(box.h) > 0.0
        and 0.0 <= float(box.x) < 1.0
        and 0.0 <= float(box.y) < 1.0
    )


def _has_text_evidence(
    box: TimedBox,
    *,
    min_confidence: float = DEFAULT_EVIDENCE_CONFIDENCE,
) -> bool:
    return _has_box_evidence(box, min_confidence=min_confidence) and contains_cjk(
        box.text
    )


def local_verified_title_boxes(
    local_boxes: Sequence[TimedBox],
    *,
    min_confidence: float = DEFAULT_EVIDENCE_CONFIDENCE,
) -> list[TimedBox]:
    """Mid-title boxes that already carry local CTC CJK text evidence."""
    return [
        box
        for box in local_boxes
        if is_mid_title_box(_to_detected(box))
        and _has_text_evidence(box, min_confidence=min_confidence)
    ]


def verified_endcard_boxes(
    boxes: Sequence[TimedBox],
    *,
    min_confidence: float = DEFAULT_EVIDENCE_CONFIDENCE,
) -> list[TimedBox]:
    """End-card policy is text-only, but includes dates/numbers as text."""
    return [
        box
        for box in boxes
        if _has_box_evidence(box, min_confidence=min_confidence)
    ]


def _local_dense_endcard(boxes: Sequence[TimedBox], timeline_ratio: float) -> bool:
    if float(timeline_ratio) < ENDCARD_LOCAL_MIN_RATIO or len(boxes) < 4:
        return False
    return is_endcard_dense([_to_detected(box) for box in boxes])


def _timed_from_mapping(raw: dict[str, Any]) -> TimedBox:
    return TimedBox(
        x=float(raw.get("x") or 0.0),
        y=float(raw.get("y") or 0.0),
        w=float(raw.get("w") if "w" in raw else raw.get("width") or 0.0),
        h=float(raw.get("h") if "h" in raw else raw.get("height") or 0.0),
    )


def detect_endcard_segments(
    position_rows: Sequence[dict[str, Any]],
    *,
    duration_ms: int,
    min_consecutive: int = 2,
    max_candidates: int = 3,
) -> list[EndcardSegment]:
    """Detect stable late dense-UI runs from full-frame local DBNet layout."""
    dense_rows: list[tuple[int, int]] = []
    for row in position_rows:
        time_ms = int(row.get("time_ms") or 0)
        ratio = float(time_ms) / float(duration_ms) if duration_ms > 0 else 0.0
        boxes = tuple(
            _timed_from_mapping(raw)
            for raw in row.get("boxes") or []
            if isinstance(raw, dict)
        )
        if _local_dense_endcard(boxes, ratio):
            dense_rows.append((int(row.get("frame_index") or 0), time_ms))

    runs: list[list[tuple[int, int]]] = []
    for item in dense_rows:
        if not runs or item[0] != runs[-1][-1][0] + 1:
            runs.append([item])
        else:
            runs[-1].append(item)

    out: list[EndcardSegment] = []
    for run in runs:
        if len(run) < max(1, int(min_consecutive)):
            continue
        start_ms = int(run[0][1])
        # Terminal late panels often lose low-res density after CTC; keep the
        # segment open through video end so high-res still covers the card.
        if float(start_ms) >= float(ENDCARD_LOCAL_MIN_RATIO) * float(duration_ms):
            end_ms = int(duration_ms) + 1
        else:
            end_ms = min(int(duration_ms) + 1, int(run[-1][1]) + 1000)
        center = (start_ms + end_ms) / 2.0
        ranked = sorted(
            run,
            key=lambda item: (abs(float(item[1]) - center), -int(item[1])),
        )
        out.append(
            EndcardSegment(
                segment_id=len(out),
                start_ms=start_ms,
                end_ms=end_ms,
                candidate_times_ms=tuple(
                    int(time_ms)
                    for _frame_index, time_ms in ranked[: max(1, int(max_candidates))]
                ),
            )
        )
    return out


def classify_frame_state(evidence: FrameEvidence) -> FrameState:
    """Classify a frame from local layout plus verified OCR evidence."""
    verified = [box for box in evidence.ocr_boxes if _has_text_evidence(box)]
    if is_endcard_dense([_to_detected(box) for box in verified]) or _local_dense_endcard(
        evidence.local_boxes,
        evidence.timeline_ratio,
    ):
        return "endcard"
    if any(is_in_subtitle_band(_to_detected(box)) for box in verified):
        return "hardsub"
    if any(is_mid_title_box(_to_detected(box)) for box in verified):
        return "title"
    return "blank"


def _plausible_local_hardsub(box: TimedBox) -> bool:
    detected = _to_detected(box)
    return (
        is_in_subtitle_band(detected)
        and 0.01 <= float(box.w) <= MAX_HARDSUB_WIDTH
        and 0.01 <= float(box.h) <= MAX_HARDSUB_HEIGHT
        and float(box.w) * float(box.h) <= MAX_HARDSUB_AREA
    )


def _center_distance(a: TimedBox, b: TimedBox) -> float:
    acx = float(a.x) + float(a.w) / 2.0
    acy = float(a.y) + float(a.h) / 2.0
    bcx = float(b.x) + float(b.w) / 2.0
    bcy = float(b.y) + float(b.h) / 2.0
    return ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5


def _hardsub_geometry(
    ocr_box: TimedBox,
    local_boxes: Sequence[TimedBox],
) -> TimedBox:
    """Use local geometry only when it tightly agrees with the OCR authority."""
    candidates = [
        box
        for box in local_boxes
        if _plausible_local_hardsub(box)
        and box_iou(box, ocr_box) >= LOCAL_MATCH_MIN_IOU
        and _center_distance(box, ocr_box) <= LOCAL_MATCH_MAX_CENTER_DISTANCE
    ]
    if not candidates:
        return ocr_box
    best = max(candidates, key=lambda box: box_iou(box, ocr_box))
    return TimedBox(
        x=best.x,
        y=best.y,
        w=best.w,
        h=best.h,
        text=ocr_box.text,
        confidence=ocr_box.confidence,
    )


def _has_local_hardsub_signal(
    ocr_box: TimedBox,
    local_boxes: Sequence[TimedBox],
) -> bool:
    x0 = float(ocr_box.x) - 0.06
    y0 = float(ocr_box.y) - 0.04
    x1 = float(ocr_box.x) + float(ocr_box.w) + 0.06
    y1 = float(ocr_box.y) + float(ocr_box.h) + 0.04
    for local in local_boxes:
        if not _plausible_local_hardsub(local):
            continue
        cx = float(local.x) + float(local.w) / 2.0
        cy = float(local.y) + float(local.h) / 2.0
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return True
    return False


def authority_boxes_for_frame(
    evidence: FrameEvidence,
    *,
    min_confidence: float = DEFAULT_EVIDENCE_CONFIDENCE,
) -> list[TimedBox]:
    """Return renderable boxes. Every result has verified CJK text evidence."""
    all_verified = verified_endcard_boxes(
        evidence.ocr_boxes,
        min_confidence=min_confidence,
    )
    verified = [
        box
        for box in all_verified
        if _has_text_evidence(box, min_confidence=min_confidence)
    ]
    state = classify_frame_state(
        FrameEvidence(
            frame_index=evidence.frame_index,
            time_ms=evidence.time_ms,
            local_boxes=evidence.local_boxes,
            ocr_boxes=tuple(verified),
            timeline_ratio=evidence.timeline_ratio,
        )
    )
    if state == "blank" or not verified:
        return []
    if state == "endcard":
        return list(all_verified)
    if state == "title":
        title_boxes = [box for box in verified if is_mid_title_box(_to_detected(box))]
        title_active = any(
            is_mid_title_box(_to_detected(local))
            and any(
                box_iou(local, title) >= 0.10
                or _center_distance(local, title) <= 0.10
                for title in title_boxes
            )
            for local in evidence.local_boxes
        )
        return title_boxes if title_active else []

    hardsubs = [box for box in verified if is_in_subtitle_band(_to_detected(box))]
    return [
        _hardsub_geometry(box, evidence.local_boxes)
        for box in hardsubs
        if _has_local_hardsub_signal(box, evidence.local_boxes)
    ]
