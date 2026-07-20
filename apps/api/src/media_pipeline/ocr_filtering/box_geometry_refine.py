"""Refine TimedBox geometry using frame ink + hardsub cover expand."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from src.media_pipeline.ocr_filtering.box_timeline_tracker import TimedBox
from src.media_pipeline.ocr_filtering.overlay_zones import is_mid_title_box
from src.media_pipeline.ocr_filtering.subtitle_band import is_in_subtitle_band
from src.media_pipeline.ocr_filtering.types import DetectedTextBox
from src.media_pipeline.video_renderer.inpaint_render import refine_segments_to_ink_inside_ocr
from src.media_pipeline.video_renderer.overlays import (
    DEFAULT_MIN_COVER_WIDTH,
    DEFAULT_PAD_X,
    DEFAULT_PAD_Y,
    OverlaySegment,
    expand_cover_rect,
)


def _to_detected(box: TimedBox) -> DetectedTextBox:
    return DetectedTextBox(
        x=box.x,
        y=box.y,
        width=max(0.001, box.w),
        height=max(0.001, box.h),
        text=box.text,
        confidence=box.confidence,
    )


def _segment_kind(box: TimedBox) -> str:
    det = _to_detected(box)
    if is_mid_title_box(det):
        return "title"
    if is_in_subtitle_band(det):
        return "hardsub"
    return "ui"


def _timed_from_segment(seg: OverlaySegment, *, text: str, confidence: float) -> TimedBox:
    return TimedBox(
        x=float(seg.x),
        y=float(seg.y),
        w=float(seg.width),
        h=float(seg.height),
        text=text,
        confidence=confidence,
    )


def expand_hardsub_cover_box(box: TimedBox) -> TimedBox:
    """Pad and enforce min width for bottom hardsub lines."""
    det = _to_detected(box)
    if not is_in_subtitle_band(det):
        return box
    x0, y0, w, h = expand_cover_rect(
        float(box.x),
        float(box.y),
        float(box.w),
        float(box.h),
        pad_x=DEFAULT_PAD_X,
        pad_y=DEFAULT_PAD_Y,
        min_width=DEFAULT_MIN_COVER_WIDTH,
    )
    return TimedBox(x=x0, y=y0, w=w, h=h, text=box.text, confidence=box.confidence)


def refine_timed_boxes_on_frame(
    frame_bgr: np.ndarray,
    boxes: Sequence[TimedBox],
    *,
    expand_hardsub: bool = True,
) -> list[TimedBox]:
    """Ink-snap each box to glyph pixels; optionally expand hardsub cover width."""
    if frame_bgr is None or not boxes:
        return list(boxes)
    segments = [
        OverlaySegment(
            start_ms=0,
            end_ms=0,
            x=float(b.x),
            y=float(b.y),
            width=float(b.w),
            height=float(b.h),
            text_vi=b.text,
            kind=_segment_kind(b),
        )
        for b in boxes
    ]
    refined = refine_segments_to_ink_inside_ocr(frame_bgr, segments)
    out: list[TimedBox] = []
    for seg, src in zip(refined, boxes, strict=True):
        box = _timed_from_segment(seg, text=src.text, confidence=src.confidence)
        if expand_hardsub and _segment_kind(src) == "hardsub":
            box = expand_hardsub_cover_box(box)
        out.append(box)
    return out


def refine_timed_boxes_from_jpeg(
    jpeg_path: str | Path,
    boxes: Sequence[TimedBox],
    *,
    expand_hardsub: bool = True,
) -> list[TimedBox]:
    path = Path(jpeg_path)
    bgr = cv2.imread(str(path))
    if bgr is None:
        return list(boxes)
    return refine_timed_boxes_on_frame(bgr, boxes, expand_hardsub=expand_hardsub)
