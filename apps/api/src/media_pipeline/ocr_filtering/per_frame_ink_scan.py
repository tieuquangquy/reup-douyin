"""Per-frame bottom-band ink scan for hardsub position authority."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from src.media_pipeline.ocr_filtering.box_geometry_refine import (
    _segment_kind,
    refine_timed_boxes_on_frame,
)
from src.media_pipeline.ocr_filtering.box_timeline_tracker import TimedBox

DEFAULT_BAND_Y0 = 0.82
DEFAULT_MIN_INK_ROW_FRAC = 0.004
DEFAULT_PAD_X_NORM = 0.012
DEFAULT_PAD_Y_NORM = 0.006


def _contrast_ink_mask(gray_roi: np.ndarray) -> np.ndarray:
    """Bright-on-dark vs dark-on-light ink mask (positioning only)."""
    if gray_roi.size < 4:
        return np.zeros(gray_roi.shape, dtype=np.uint8)
    med = float(np.median(gray_roi))
    dark_frac = float((gray_roi < 80).mean())
    if dark_frac >= 0.35 or med < 120.0:
        thr = max(230.0, med + 70.0)
        return (gray_roi >= thr).astype(np.uint8) * 255
    thr = max(110.0, med - 35.0)
    return (gray_roi < thr).astype(np.uint8) * 255


def scan_hardsub_ink_box(
    frame_bgr: np.ndarray,
    *,
    band_y0: float = DEFAULT_BAND_Y0,
    hint: TimedBox | None = None,
    min_ink_row_frac: float = DEFAULT_MIN_INK_ROW_FRAC,
) -> TimedBox | None:
    """
    Sweep the bottom band for subtitle ink; return tight normalized xywh.

    Uses OCR text from ``hint`` when present; geometry comes from pixels.
    Search is gated horizontally around ``hint`` so wok motion does not
    pull the box across the frame.
    """
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    h, w = frame_bgr.shape[:2]
    y0_px = max(0, min(h - 1, int(round(h * float(band_y0)))))
    if hint is not None and float(hint.y) > 0.0:
        y0_px = max(y0_px, int(round(h * max(0.0, float(hint.y) - 0.05))))
        y1_hint = int(round(h * min(1.0, float(hint.y) + float(hint.h) + 0.04)))
    else:
        y1_hint = h
    y1_px = min(h, max(y0_px + 4, y1_hint))
    roi = frame_bgr[y0_px:y1_px, :]
    if roi.size == 0:
        return None
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    ink = _contrast_ink_mask(gray)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    ink = cv2.dilate(ink, kernel, iterations=1)

    if hint is not None:
        hx0 = int(max(0, round((float(hint.x) - 0.08) * w)))
        hx1 = int(min(w, round((float(hint.x) + float(hint.w) + 0.08) * w)))
        mask = np.zeros_like(ink)
        lx0 = max(0, hx0)
        lx1 = min(ink.shape[1], hx1)
        if lx1 > lx0:
            mask[:, lx0:lx1] = 255
            ink = cv2.bitwise_and(ink, mask)

    row_sum = ink.sum(axis=1).astype(np.float64)
    if row_sum.size == 0 or float(row_sum.max()) < w * 255.0 * float(min_ink_row_frac):
        return None
    thresh = float(row_sum.max()) * 0.25
    rows = np.where(row_sum >= thresh)[0]
    if rows.size == 0:
        return None
    r0, r1 = int(rows.min()), int(rows.max()) + 1
    band = ink[r0:r1, :]
    col_sum = band.sum(axis=0)
    cols = np.where(col_sum > 0)[0]
    if cols.size == 0:
        return None
    c0, c1 = int(cols.min()), int(cols.max()) + 1

    pad_x = max(2, int(round(w * DEFAULT_PAD_X_NORM)))
    pad_y = max(1, int(round(h * DEFAULT_PAD_Y_NORM)))
    fx0 = max(0, c0 - pad_x)
    fx1 = min(w, c1 + pad_x)
    fy0 = max(0, y0_px + r0 - pad_y)
    fy1 = min(h, y0_px + r1 + pad_y)
    if fx1 - fx0 < 4 or fy1 - fy0 < 2:
        return None

    if hint is not None:
        hx0n = max(0.0, float(hint.x) - 0.02)
        hx1n = min(1.0, float(hint.x) + float(hint.w) + 0.02)
        fx0 = min(fx0, int(round(hx0n * w)))
        fx1 = max(fx1, int(round(hx1n * w)))
        fx0 = max(0, min(fx0, w - 4))
        fx1 = max(fx0 + 4, min(w, fx1))
        bw = (fx1 - fx0) / float(w)
        if bw < max(0.12, float(hint.w) * 0.45):
            return None
        if bw > min(0.94, max(0.75, float(hint.w) * 1.35)):
            return None
        cy = (fy0 + fy1) / 2.0 / float(h)
        if cy < 0.84:
            return None

    text = (hint.text if hint else "") or ""
    conf = float(hint.confidence if hint else 0.0)
    return TimedBox(
        x=fx0 / float(w),
        y=fy0 / float(h),
        w=(fx1 - fx0) / float(w),
        h=(fy1 - fy0) / float(h),
        text=text,
        confidence=conf,
    )


def _timed_from_dict(b: dict[str, Any]) -> TimedBox:
    return TimedBox(
        x=float(b["x"]),
        y=float(b["y"]),
        w=float(b["w"]),
        h=float(b["h"]),
        text=str(b.get("text") or ""),
        confidence=float(b.get("confidence") or 0.0),
    )


def scan_refine_boxes_on_frame(
    frame_bgr: np.ndarray,
    boxes: Sequence[TimedBox],
    *,
    use_band_scan: bool = True,
) -> list[TimedBox]:
    """Per-frame position: band ink scan for hardsub; ink snap for mid-title."""
    if not boxes:
        return []
    out: list[TimedBox] = []
    for box in boxes:
        kind = _segment_kind(box)
        if use_band_scan and kind == "hardsub":
            scanned = scan_hardsub_ink_box(frame_bgr, hint=box)
            if scanned is not None and float(scanned.w) >= 0.08:
                out.append(scanned)
                continue
            refined = refine_timed_boxes_on_frame(
                frame_bgr, [box], expand_hardsub=False
            )
            snapped = refined[0] if refined else box
            # Tight ink snap + modest horizontal pad for cover.
            from src.media_pipeline.video_renderer.overlays import expand_cover_rect

            x0, y0, bw, bh = expand_cover_rect(
                float(snapped.x),
                float(snapped.y),
                float(snapped.w),
                float(snapped.h),
                pad_x=0.03,
                pad_y=0.02,
                min_width=max(0.55, float(box.w) * 0.85),
            )
            out.append(
                TimedBox(
                    x=x0,
                    y=y0,
                    w=bw,
                    h=bh,
                    text=box.text,
                    confidence=box.confidence,
                )
            )
            continue
        refined = refine_timed_boxes_on_frame(frame_bgr, [box], expand_hardsub=False)
        out.append(refined[0] if refined else box)
    return out


def scan_refine_dense_timeline(
    video_path: str | Path,
    dense_frames: list[dict[str, Any]],
    *,
    use_band_scan: bool = True,
) -> list[dict[str, Any]]:
    """Sweep every dense frame — update box geometry from local ink scan."""
    path = Path(video_path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    out: list[dict[str, Any]] = []
    try:
        for i, row in enumerate(dense_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
            ok, bgr = cap.read()
            boxes_raw = row.get("boxes") or []
            if not ok or bgr is None or not boxes_raw:
                out.append(dict(row))
                continue
            timed = [_timed_from_dict(b) for b in boxes_raw]
            refined = scan_refine_boxes_on_frame(
                bgr, timed, use_band_scan=use_band_scan
            )
            new_row = dict(row)
            new_row["boxes"] = [b.to_dict() for b in refined]
            out.append(new_row)
    finally:
        cap.release()
    return out
