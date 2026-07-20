"""OpenCV inpaint Phase 3+4: text mask → inpaint → Pillow VI → FFmpeg pipes."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

import numpy as np

from src.media_pipeline.video_renderer.errors import VideoRendererError, VideoRendererErrorCode
from src.media_pipeline.video_renderer.filter_graph import build_anti_detection_filters
from src.media_pipeline.video_renderer.fonts import resolve_drawtext_font
from src.media_pipeline.video_renderer.overlays import (
    DENSE_UI_KIND,
    OverlaySegment,
    expand_cover_rect,
    is_artifact_vi_text,
)

logger = logging.getLogger(__name__)

OCR_RENDER_BACKEND_ENV = "OCR_RENDER_BACKEND"
BACKEND_OPENCV = "opencv_inpaint"
BACKEND_FFMPEG = "ffmpeg_delogo"

ProgressCallback = Callable[[float | None, str], None]

_MIN_MASK_FRACTION = 0.005


def resolve_render_backend() -> str:
    """Default opencv_inpaint; set OCR_RENDER_BACKEND=ffmpeg_delogo to rollback."""
    raw = os.environ.get(OCR_RENDER_BACKEND_ENV, "").strip().lower()
    if raw in {BACKEND_FFMPEG, "delogo", "ffmpeg"}:
        return BACKEND_FFMPEG
    return BACKEND_OPENCV


def _norm_box_to_pixels(
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[int, int, int, int]:
    x0 = int(max(0, min(frame_w - 1, round(float(x) * frame_w))))
    y0 = int(max(0, min(frame_h - 1, round(float(y) * frame_h))))
    x1 = int(max(x0 + 1, min(frame_w, round((float(x) + float(w)) * frame_w))))
    y1 = int(max(y0 + 1, min(frame_h, round((float(y) + float(h)) * frame_h))))
    return x0, y0, x1, y1


def _roi_text_mask(gray_roi: np.ndarray) -> np.ndarray:
    """Otsu (+ invert if needed) → binary text mask for one ROI."""
    import cv2

    if gray_roi.size < 4:
        return np.zeros(gray_roi.shape, dtype=np.uint8)
    blur = cv2.GaussianBlur(gray_roi, (3, 3), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Prefer the darker class as "ink" for typical dark-on-light subs.
    mean_on = float(gray_roi[binary == 255].mean()) if np.any(binary == 255) else 255.0
    mean_off = float(gray_roi[binary == 0].mean()) if np.any(binary == 0) else 0.0
    if mean_on <= mean_off:
        ink = binary
    else:
        ink = cv2.bitwise_not(binary)
    frac = float(np.count_nonzero(ink)) / float(ink.size)
    # White text on dark UI: if ink fraction extreme, try inverted.
    if frac < _MIN_MASK_FRACTION or frac > 0.85:
        alt = cv2.bitwise_not(ink)
        alt_frac = float(np.count_nonzero(alt)) / float(alt.size)
        if _MIN_MASK_FRACTION <= alt_frac <= 0.85:
            ink = alt
            frac = alt_frac
    if frac < _MIN_MASK_FRACTION:
        # Soft fallback: filled ellipse inside ROI so thin glyphs still get inpainted.
        h, w = ink.shape[:2]
        ink = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(
            ink,
            (w // 2, h // 2),
            (max(1, w // 2 - 1), max(1, h // 2 - 1)),
            0,
            0,
            360,
            255,
            -1,
        )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    return cv2.dilate(ink, kernel, iterations=1)


def build_text_mask(
    frame_bgr: np.ndarray,
    boxes_xywh_norm: Sequence[tuple[float, float, float, float]],
) -> np.ndarray:
    """
    Full-frame uint8 mask (0/255): text pixels from per-box Otsu + dilate.
    ``boxes_xywh_norm`` are normalized xywh already padded/expanded by caller.
    """
    import cv2

    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"frame must be HxWx3 BGR, got {getattr(frame_bgr, 'shape', None)}",
        )
    h, w = frame_bgr.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    for x, y, bw, bh in boxes_xywh_norm:
        x0, y0, x1, y1 = _norm_box_to_pixels(x, y, bw, bh, frame_w=w, frame_h=h)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        roi = gray[y0:y1, x0:x1]
        local = _roi_text_mask(roi)
        mask[y0:y1, x0:x1] = cv2.bitwise_or(mask[y0:y1, x0:x1], local)
    return mask


_TIGHT_PAD_X = 0.010
_TIGHT_PAD_Y = 0.008
_BLUR_KERNEL = 9
# Search around OCR AABB so slightly biased/narrow boxes still catch full glyphs.
_INK_SEARCH_PAD_X = 0.04
_INK_SEARCH_PAD_Y = 0.03
_INK_SEARCH_WIDTH_FACTOR = 1.25
_INK_SEARCH_HEIGHT_FACTOR = 0.90
_INK_SNAP_MIN_PIXELS = 8
_INK_SNAP_PAD_PX = 1
# Recover glyphs when Paddle AABB is shifted (still reject colorful icons).
_INK_RECOVER_PAD_X = 0.055
_INK_RECOVER_PAD_Y = 0.055
_INK_ICON_SAT_MAX = 90.0
_INK_INSIDE_MIN_AREA_FRAC = 0.08
# VI point size is larger than box_h because Pillow em-size > ink height.
_VI_FONT_HEIGHT_FRAC = 1.25
_VI_FONT_SIZE_CAP = 120


def _vi_font_size_px(*, box_h_px: int) -> int:
    """Pillow font size matched to OCR/snap box height."""
    return max(8, min(_VI_FONT_SIZE_CAP, int(max(6, box_h_px) * _VI_FONT_HEIGHT_FRAC)))


def _search_rect_for_segment(seg: OverlaySegment) -> tuple[float, float, float, float]:
    """OCR box expanded for ink detection (not the final cover footprint)."""
    pad_x = max(_INK_SEARCH_PAD_X, float(seg.width) * _INK_SEARCH_WIDTH_FACTOR)
    pad_y = max(_INK_SEARCH_PAD_Y, float(seg.height) * _INK_SEARCH_HEIGHT_FACTOR)
    return expand_cover_rect(
        float(seg.x),
        float(seg.y),
        float(seg.width),
        float(seg.height),
        pad_x=pad_x,
        pad_y=pad_y,
        min_width=0.0,
    )


def _ink_local_for_segment(
    gray: np.ndarray,
    seg: OverlaySegment,
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[np.ndarray, int, int, int, int] | None:
    """
    Ink mask for one OCR box.

    Detect inside a search pad, then keep only connected components that touch
    the original OCR core — so left-biased boxes still catch full glyphs without
    swallowing neighboring labels.
    """
    import cv2

    sx, sy, sw, sh = _search_rect_for_segment(seg)
    x0, y0, x1, y1 = _norm_box_to_pixels(sx, sy, sw, sh, frame_w=frame_w, frame_h=frame_h)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    local = _roi_text_mask(gray[y0:y1, x0:x1])
    if int(local.max()) == 0:
        return None

    cx0, cy0, cx1, cy1 = _norm_box_to_pixels(
        float(seg.x),
        float(seg.y),
        float(seg.width),
        float(seg.height),
        frame_w=frame_w,
        frame_h=frame_h,
    )
    # Core rect in local ROI coords (slightly padded).
    core = np.zeros_like(local)
    lx0 = max(0, cx0 - x0 - 2)
    ly0 = max(0, cy0 - y0 - 2)
    lx1 = min(local.shape[1], cx1 - x0 + 2)
    ly1 = min(local.shape[0], cy1 - y0 + 2)
    if lx1 <= lx0 or ly1 <= ly0:
        return local, x0, y0, x1, y1
    core[ly0:ly1, lx0:lx1] = 255

    num, labels = cv2.connectedComponents((local > 0).astype(np.uint8), connectivity=8)
    kept = np.zeros_like(local)
    for label in range(1, num):
        comp = labels == label
        if np.any(comp & (core > 0)):
            kept[comp] = 255
    if int(kept.max()) == 0:
        # Fail-soft: keep ink that intersects core via bitwise (no CC match).
        kept = cv2.bitwise_and(local, core)
        if int(kept.max()) == 0:
            kept = local
    return kept, x0, y0, x1, y1


def build_ink_cover_mask(
    frame_bgr: np.ndarray,
    segments: Sequence[OverlaySegment],
) -> np.ndarray:
    """
    Cover mask from real glyph ink inside a search pad around each OCR box.

    More accurate than solid AABB when Paddle boxes are narrow or left-biased.
    """
    import cv2

    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"frame must be HxWx3 BGR, got {getattr(frame_bgr, 'shape', None)}",
        )
    h, w = frame_bgr.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    for seg in segments:
        if seg.kind == DENSE_UI_KIND:
            continue
        got = _ink_local_for_segment(gray, seg, frame_w=w, frame_h=h)
        if got is None:
            continue
        local, x0, y0, x1, y1 = got
        mask[y0:y1, x0:x1] = cv2.bitwise_or(mask[y0:y1, x0:x1], local)
    return mask


def refine_segments_to_ink(
    frame_bgr: np.ndarray,
    segments: Sequence[OverlaySegment],
) -> list[OverlaySegment]:
    """Snap each segment's xywh to the detected ink bbox (fail-soft → original)."""
    import cv2

    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        return list(segments)
    h, w = frame_bgr.shape[:2]
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    refined: list[OverlaySegment] = []
    for seg in segments:
        if seg.kind == DENSE_UI_KIND:
            refined.append(seg)
            continue
        got = _ink_local_for_segment(gray, seg, frame_w=w, frame_h=h)
        if got is None:
            refined.append(seg)
            continue
        local, x0, y0, _x1, _y1 = got
        ys, xs = np.where(local > 0)
        if xs.size < 4 or ys.size < 4:
            refined.append(seg)
            continue
        fx0 = max(0, x0 + int(xs.min()) - 1)
        fy0 = max(0, y0 + int(ys.min()) - 1)
        fx1 = min(w, x0 + int(xs.max()) + 2)
        fy1 = min(h, y0 + int(ys.max()) + 2)
        refined.append(
            OverlaySegment(
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                x=fx0 / float(w),
                y=fy0 / float(h),
                width=max(0.01, (fx1 - fx0) / float(w)),
                height=max(0.01, (fy1 - fy0) / float(h)),
                text_vi=seg.text_vi,
                kind=seg.kind,
            )
        )
    return refined


def _contrast_ink_mask(gray_roi: np.ndarray) -> np.ndarray:
    """
    Ink mask for positioning — no ellipse fallback (that would center on empty OCR).

    Light card → dark ink; dark bar → bright ink; mid chrome (teal header) →
    near-white ink (not dark-on-light, which misses white titles).
    """
    import cv2

    if gray_roi.size < 4:
        return np.zeros(gray_roi.shape, dtype=np.uint8)
    med = float(np.median(gray_roi))
    dark_frac = float((gray_roi < 80).mean())
    bright_frac = float((gray_roi >= 230).mean())

    # Dark UI / teal-ish chrome with white titles.
    if dark_frac >= 0.35 or med < 120.0:
        thr = max(230.0, med + 70.0)
        return (gray_roi >= thr).astype(np.uint8) * 255

    # Mid chrome (e.g. teal header ~160–190): prefer scarce near-white glyphs.
    if med < 200.0 and bright_frac >= 0.015:
        thr = max(220.0, med + 40.0)
        return (gray_roi >= thr).astype(np.uint8) * 255

    # Light card → dark ink.
    thr = max(110.0, med - 35.0)
    return (gray_roi < thr).astype(np.uint8) * 255


def _dilate_ink(ink: np.ndarray) -> np.ndarray:
    import cv2

    if ink is None or int(ink.max()) == 0:
        return ink
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    return cv2.dilate(ink, kernel, iterations=1)


def _keep_darkest_ink_components(ink: np.ndarray, gray_roi: np.ndarray) -> np.ndarray:
    """
    Keep glyph CCs on the same text line; drop soft fringe and stray blobs.

    Dark ink (light card): seed = darkest CC, drop much lighter fringe.
    Bright ink (teal/dark chrome): seed = brightest CC, drop dimmer fringe.
    """
    import cv2

    if ink is None or int(ink.max()) == 0 or gray_roi.size == 0:
        return ink
    num, labels, stats, _ = cv2.connectedComponentsWithStats(
        (ink > 0).astype(np.uint8), connectivity=8
    )
    if num <= 2:
        return ink
    cands: list[tuple[int, float, float, int, int]] = []
    for i in range(1, num):
        area = float(stats[i, cv2.CC_STAT_AREA])
        if area < float(_INK_SNAP_MIN_PIXELS):
            continue
        mean = float(gray_roi[labels == i].mean())
        top = int(stats[i, cv2.CC_STAT_TOP])
        bottom = top + int(stats[i, cv2.CC_STAT_HEIGHT])
        cands.append((i, mean, area, top, bottom))
    if not cands:
        return ink
    # Prefer solid glyph CCs over 1–2px chrome fringe when seeding the line.
    solid = [c for c in cands if (c[4] - c[3]) >= 6 and c[2] >= 20.0]
    pool = solid if solid else cands
    ink_means = gray_roi[ink > 0]
    bright_ink = bool(ink_means.size and float(ink_means.mean()) >= 180.0)
    if bright_ink:
        seed_i, seed_mean, seed_area, seed_top, seed_bot = max(pool, key=lambda t: t[1])
    else:
        seed_i, seed_mean, seed_area, seed_top, seed_bot = min(pool, key=lambda t: t[1])
    seed_h = max(1, seed_bot - seed_top)
    kept = np.zeros_like(ink)
    for i, mean, area, top, bottom in cands:
        # Same horizontal text line as seed.
        y_overlap = min(seed_bot, bottom) - max(seed_top, top)
        if y_overlap < 0.35 * min(seed_h, max(1, bottom - top)):
            continue
        if bright_ink:
            if mean < seed_mean - 100.0:
                continue
        else:
            if mean > seed_mean + 100.0:
                continue
        kept[labels == i] = 255
    return kept if int(kept.max()) > 0 else ink


def _mask_icon_column(ink: np.ndarray, bgr_roi: np.ndarray) -> np.ndarray:
    """
    If the left third of the OCR box looks like a colorful thumbnail, zero it.

    Food-list rows: Paddle AABB often overlaps the circular food icon.
    """
    if ink is None or bgr_roi is None or ink.size == 0 or bgr_roi.size == 0:
        return ink
    if bgr_roi.shape[:2] != ink.shape:
        return ink
    _h, w = ink.shape[:2]
    if w < 12:
        return ink
    left_w = max(3, w // 3)
    left = bgr_roi[:, :left_w]
    spread = left.max(axis=2).astype(np.int16) - left.min(axis=2).astype(np.int16)
    if float(spread.mean()) < 18.0:
        return ink
    out = ink.copy()
    out[:, :left_w] = 0
    return out


def _ocr_sits_left_of_glyphs(gray_roi: np.ndarray) -> bool:
    """True when OCR right third is blank white while left still has content."""
    if gray_roi.size < 16:
        return False
    _h, w = gray_roi.shape[:2]
    if w < 9:
        return False
    left = gray_roi[:, : w // 3]
    right = gray_roi[:, (2 * w) // 3 :]
    return float(right.mean()) > 242.0 and float(left.mean()) < 230.0


def _is_plausible_ink_box(
    box: tuple[int, int, int, int],
    *,
    ocr_w: int,
    ocr_h: int,
) -> bool:
    """Reject hairline / runaway snaps (e.g. top-edge fringe grown across the frame)."""
    x0, y0, x1, y1 = box
    bw = max(0, x1 - x0)
    bh = max(0, y1 - y0)
    if bh < 6:
        return False
    if ocr_h >= 12 and bh < 0.35 * float(ocr_h):
        return False
    if bh > 0 and bw / float(bh) > 14.0:
        return False
    if ocr_w >= 8 and bw > 4.5 * float(ocr_w) and bh < 0.6 * float(ocr_h):
        return False
    return True


def _clip_y_before_bright_surface(
    gray: np.ndarray,
    *,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
) -> int:
    """Stop header search before a solid white card swallows the ink mask."""
    y0 = max(0, y0)
    y1 = min(gray.shape[0], y1)
    x0 = max(0, x0)
    x1 = min(gray.shape[1], max(x0 + 1, x1))
    if y1 <= y0 + 2:
        return y1
    streak = 0
    for y in range(y0, y1):
        row = gray[y, x0:x1]
        # Solid card rows are nearly all white across the search band.
        # Sparse white glyphs on teal must not trip this (bright frac stays low).
        if row.size and float((row >= 235).mean()) > 0.82:
            streak += 1
            if streak >= 2:
                return max(y0 + 1, y - 1)
        else:
            streak = 0
    return y1


def _grow_textline_right(
    frame_bgr: np.ndarray,
    gray: np.ndarray,
    sat: np.ndarray,
    box: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """
    Expand a snap box rightward to include clipped sibling glyphs.

    Paddle often left-pads onto icons and clips the last character(s) just
    outside the OCR right edge. Grow only across tight inter-char gaps.
    """
    import cv2

    fx0, fy0, fx1, fy1 = box
    fh, fw = gray.shape[:2]
    box_h = max(1, fy1 - fy0)
    box_w = max(1, fx1 - fx0)
    # Search a few glyph-widths to the right of the current snap.
    search_right = min(fw, fx1 + max(int(2.8 * box_h), int(1.2 * box_w)))
    if search_right <= fx1 + 2:
        return box
    y0 = max(0, fy0 - 2)
    y1 = min(fh, fy1 + 2)
    x0 = max(0, fx0)
    roi_bgr = frame_bgr[y0:y1, x0:search_right]
    roi_gray = gray[y0:y1, x0:search_right]
    roi_sat = sat[y0:y1, x0:search_right]
    ink = _contrast_ink_mask(roi_gray)
    ink = _mask_low_chroma(ink, roi_sat, roi_bgr)
    ink = _keep_darkest_ink_components(ink, roi_gray)
    if int(ink.max()) == 0:
        return box

    seed = roi_gray[max(0, fy0 - y0) : max(1, fy1 - y0), max(0, fx0 - x0) : max(1, fx1 - x0)]
    seed_mean = float(seed.mean()) if seed.size else 40.0
    num, labels, stats, _ = cv2.connectedComponentsWithStats(
        (ink > 0).astype(np.uint8), connectivity=8
    )
    # Collect CCs on the text line, sorted left→right.
    cands: list[tuple[int, int, int]] = []
    for i in range(1, num):
        area = float(stats[i, cv2.CC_STAT_AREA])
        if area < float(_INK_SNAP_MIN_PIXELS):
            continue
        top = int(stats[i, cv2.CC_STAT_TOP])
        bot = top + int(stats[i, cv2.CC_STAT_HEIGHT])
        y_overlap = min(fy1 - y0, bot) - max(fy0 - y0, top)
        if y_overlap < 0.35 * min(box_h, max(1, bot - top)):
            continue
        mean = float(roi_gray[labels == i].mean())
        if mean > seed_mean + 100.0:
            continue
        left = int(stats[i, cv2.CC_STAT_LEFT])
        right = left + int(stats[i, cv2.CC_STAT_WIDTH])
        cands.append((left, right, i))
    if not cands:
        return box
    cands.sort(key=lambda t: t[0])

    # Walk right from the current snap, accepting only tight gaps.
    cur_right = fx1 - x0
    max_gap = max(6, int(0.55 * box_h))
    grown_right = cur_right
    for left, right, _i in cands:
        if right <= cur_right + 1:
            # Already inside / overlapping current snap.
            grown_right = max(grown_right, right)
            continue
        gap = left - grown_right
        if gap > max_gap:
            break
        grown_right = max(grown_right, right)

    new_fx1 = min(fw, x0 + grown_right + _INK_SNAP_PAD_PX)
    if new_fx1 <= fx1:
        return box
    return (fx0, fy0, new_fx1, fy1)


def refine_segments_to_ink_inside_ocr(
    frame_bgr: np.ndarray,
    segments: Sequence[OverlaySegment],
) -> list[OverlaySegment]:
    """
    Snap each segment to real text ink near its OCR AABB.

    1. Prefer ink strictly inside the OCR box (left-padded boxes).
    2. If the AABB is shifted (glyphs mostly outside), search a modest pad and
       keep the best low-chroma text component near the OCR center — never
       colorful UI icons.
    """
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        return list(segments)
    h, w = frame_bgr.shape[:2]
    import cv2

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    refined: list[OverlaySegment] = []
    for seg in segments:
        if seg.kind == DENSE_UI_KIND:
            refined.append(seg)
            continue
        snapped = _snap_segment_to_nearby_ink(
            frame_bgr,
            gray,
            sat,
            seg,
            frame_w=w,
            frame_h=h,
        )
        refined.append(snapped if snapped is not None else seg)
    return refined


def _snap_segment_to_nearby_ink(
    frame_bgr: np.ndarray,
    gray: np.ndarray,
    sat: np.ndarray,
    seg: OverlaySegment,
    *,
    frame_w: int,
    frame_h: int,
) -> OverlaySegment | None:
    import cv2

    cx0, cy0, cx1, cy1 = _norm_box_to_pixels(
        float(seg.x),
        float(seg.y),
        float(seg.width),
        float(seg.height),
        frame_w=frame_w,
        frame_h=frame_h,
    )
    if cx1 - cx0 < 2 or cy1 - cy0 < 2:
        return None

    # Pass 1: ink inside OCR only (skip if too sparse — likely a shifted AABB).
    # Top-anchored Paddle boxes (午餐 → 0,0) often contain bright chrome fringe;
    # never trust inside-only snap — recover below.
    top_anchored = cy0 <= 2
    ocr_roi = gray[cy0:cy1, cx0:cx1]
    inside = _contrast_ink_mask(ocr_roi)
    inside = _mask_low_chroma(inside, sat[cy0:cy1, cx0:cx1], frame_bgr[cy0:cy1, cx0:cx1])
    inside = _mask_icon_column(inside, frame_bgr[cy0:cy1, cx0:cx1])
    if _ocr_sits_left_of_glyphs(ocr_roi) or top_anchored:
        # Paddle box parked in the gap/icon or glued to the top edge.
        inside = np.zeros_like(inside)
    else:
        inside = _keep_darkest_ink_components(inside, ocr_roi)
        inside = _dilate_ink(inside)
    oarea = max(1.0, float((cx1 - cx0) * (cy1 - cy0)))
    inside_area = float(np.count_nonzero(inside))
    box = _bbox_from_mask(inside, ox=cx0, oy=cy0, min_px=_INK_SNAP_MIN_PIXELS)
    ocr_w, ocr_h = cx1 - cx0, cy1 - cy0
    if (
        box is not None
        and inside_area >= _INK_INSIDE_MIN_AREA_FRAC * oarea
        and _is_plausible_ink_box(box, ocr_w=ocr_w, ocr_h=ocr_h)
    ):
        grown = _grow_textline_right(frame_bgr, gray, sat, box)
        if _is_plausible_ink_box(grown, ocr_w=ocr_w, ocr_h=ocr_h):
            return _segment_from_pixel_box(
                seg, grown, frame_w=frame_w, frame_h=frame_h, clamp_to=None
            )

    # Empty white-card OCR: do not search neighbors (would latch 525 onto 干卡).
    ocr_med = float(np.median(ocr_roi)) if ocr_roi.size else 0.0
    bright_frac = float((ocr_roi >= 230).mean()) if ocr_roi.size else 0.0
    dark_frac = float((ocr_roi < 80).mean()) if ocr_roi.size else 0.0
    sits_left = _ocr_sits_left_of_glyphs(ocr_roi)
    if ocr_med >= 140.0 and bright_frac < 0.03 and dark_frac < 0.03 and not sits_left and not top_anchored:
        return None

    # Pass 2: recover shifted AABB — search pad (bias right when box is left of glyphs;
    # bias down when OCR is glued to the top edge).
    pad_x = max(
        12,
        int(round(_INK_RECOVER_PAD_X * frame_w)),
        int(round(0.65 * (cx1 - cx0))),
    )
    pad_y = max(
        12,
        int(round(_INK_RECOVER_PAD_Y * frame_h)),
        int(round(0.65 * (cy1 - cy0))),
    )
    if top_anchored:
        # Title often sits just below a bogus (0,0) box; search enough to reach it
        # but nearest-CC selection prevents latching the white card further down.
        pad_y = max(pad_y, int(1.6 * (cy1 - cy0)), int(0.10 * frame_h))
    pad_right = pad_x * 3 if sits_left else pad_x
    x0 = max(0, cx0 - (pad_x // 4 if sits_left else pad_x))
    y0 = max(0, cy0 - (0 if top_anchored else pad_y))
    x1 = min(frame_w, cx1 + pad_right)
    y1 = min(frame_h, cy1 + pad_y)
    if top_anchored:
        y1 = _clip_y_before_bright_surface(gray, x0=x0, x1=x1, y0=cy1, y1=y1)
    local = _contrast_ink_mask(gray[y0:y1, x0:x1])
    local = _mask_low_chroma(local, sat[y0:y1, x0:x1], frame_bgr[y0:y1, x0:x1])
    local = _mask_icon_column(local, frame_bgr[y0:y1, x0:x1])
    if not top_anchored:
        # Top-anchored headers: title CCs are often smaller than chrome blobs;
        # keep all ink and select below-OCR by centroid instead.
        local = _keep_darkest_ink_components(local, gray[y0:y1, x0:x1])
    local = _dilate_ink(local)
    if int(local.max()) == 0:
        return None

    ocx = 0.5 * (cx0 + cx1)
    ocy = 0.5 * (cy0 + cy1)
    if sits_left:
        # Expect glyphs just to the right of the parked OCR box.
        ocx = float(cx1 + max(8, (cx1 - cx0)))
    if top_anchored:
        # Expect title glyphs just below the bogus top-edge OCR box.
        ocy = float(cy1 + max(8, (cy1 - cy0) // 2))
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(
        (local > 0).astype(np.uint8), connectivity=8
    )
    max_dist = (0.7 * max(cx1 - cx0, 10)) ** 2 + (0.7 * max(cy1 - cy0, 10)) ** 2
    if sits_left:
        max_dist = (2.5 * max(cx1 - cx0, 10)) ** 2 + (1.2 * max(cy1 - cy0, 10)) ** 2
    if top_anchored:
        max_dist = (1.5 * max(cx1 - cx0, 10)) ** 2 + (2.8 * max(cy1 - cy0, 10)) ** 2
    ex0, ey0 = max(0, cx0 - pad_x // 2), max(0, cy0 - pad_y // 2)
    ex1, ey1 = min(frame_w, cx1 + pad_right), min(frame_h, cy1 + pad_y)
    if sits_left:
        ex0 = cx1  # do not accept icon CCs left of OCR right edge
    if top_anchored:
        ey0 = cy1  # do not accept top-fringe CCs inside the bogus OCR box
    keepers: list[tuple[float, int]] = []
    for i in range(1, num):
        area = float(stats[i, cv2.CC_STAT_AREA])
        if area < float(_INK_SNAP_MIN_PIXELS):
            continue
        if area > oarea * 1.8:
            continue
        bw = float(stats[i, cv2.CC_STAT_WIDTH])
        bh = float(stats[i, cv2.CC_STAT_HEIGHT])
        if bw > 1.8 * max(8.0, float(cx1 - cx0)) or bh > 1.8 * max(8.0, float(cy1 - cy0)):
            continue
        lx = int(stats[i, cv2.CC_STAT_LEFT])
        ly = int(stats[i, cv2.CC_STAT_TOP])
        lw = int(stats[i, cv2.CC_STAT_WIDTH])
        lh = int(stats[i, cv2.CC_STAT_HEIGHT])
        abs_x0, abs_y0 = x0 + lx, y0 + ly
        abs_x1, abs_y1 = abs_x0 + lw, abs_y0 + lh
        intersects = not (abs_x1 <= ex0 or abs_x0 >= ex1 or abs_y1 <= ey0 or abs_y0 >= ey1)
        if not intersects:
            continue
        ccx = float(x0 + centroids[i][0])
        ccy = float(y0 + centroids[i][1])
        if top_anchored and ccy < float(cy1) - 4.0:
            continue
        dist = (ccx - ocx) ** 2 + (ccy - ocy) ** 2
        if dist > max_dist:
            continue
        keepers.append((dist, i))
    if not keepers:
        return None
    keepers.sort(key=lambda t: t[0])
    if top_anchored:
        # Nearest below-OCR CC, plus same-line siblings (full title).
        seed = keepers[0][1]
        seed_top = int(stats[seed, cv2.CC_STAT_TOP])
        seed_bot = seed_top + int(stats[seed, cv2.CC_STAT_HEIGHT])
        seed_h = max(1, seed_bot - seed_top)
        chosen: list[int] = []
        for _d, i in keepers:
            top = int(stats[i, cv2.CC_STAT_TOP])
            bot = top + int(stats[i, cv2.CC_STAT_HEIGHT])
            y_overlap = min(seed_bot, bot) - max(seed_top, top)
            if y_overlap >= 0.35 * min(seed_h, max(1, bot - top)):
                chosen.append(i)
    else:
        chosen = [i for _d, i in keepers]
    comp = np.isin(labels, chosen)
    ys, xs = np.where(comp)
    fx0 = max(0, x0 + int(xs.min()) - _INK_SNAP_PAD_PX)
    fy0 = max(0, y0 + int(ys.min()) - _INK_SNAP_PAD_PX)
    fx1 = min(frame_w, x0 + int(xs.max()) + _INK_SNAP_PAD_PX + 1)
    fy1 = min(frame_h, y0 + int(ys.max()) + _INK_SNAP_PAD_PX + 1)
    grown = _grow_textline_right(frame_bgr, gray, sat, (fx0, fy0, fx1, fy1))
    if not _is_plausible_ink_box(grown, ocr_w=cx1 - cx0, ocr_h=cy1 - cy0):
        if _is_plausible_ink_box((fx0, fy0, fx1, fy1), ocr_w=cx1 - cx0, ocr_h=cy1 - cy0):
            grown = (fx0, fy0, fx1, fy1)
        else:
            return None
    return _segment_from_pixel_box(
        seg,
        grown,
        frame_w=frame_w,
        frame_h=frame_h,
        clamp_to=None,
    )


def _mask_low_chroma(
    ink: np.ndarray,
    sat_roi: np.ndarray,
    bgr_roi: np.ndarray | None = None,
) -> np.ndarray:
    """Drop saturated / colorful pixels (food icons) from an ink mask."""
    if ink.size == 0 or sat_roi.size == 0:
        return ink
    keep = sat_roi.astype(np.float32) <= _INK_ICON_SAT_MAX
    if bgr_roi is not None and bgr_roi.size and bgr_roi.shape[:2] == ink.shape:
        spread = bgr_roi.max(axis=2).astype(np.int16) - bgr_roi.min(axis=2).astype(np.int16)
        keep = keep & (spread <= 45)
    out = ink.copy()
    out[~keep] = 0
    return out


def _bbox_from_mask(
    local: np.ndarray,
    *,
    ox: int,
    oy: int,
    min_px: int,
) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(local > 0)
    if xs.size < min_px or ys.size < min_px:
        return None
    return (
        ox + int(xs.min()) - _INK_SNAP_PAD_PX,
        oy + int(ys.min()) - _INK_SNAP_PAD_PX,
        ox + int(xs.max()) + _INK_SNAP_PAD_PX + 1,
        oy + int(ys.max()) + _INK_SNAP_PAD_PX + 1,
    )


def _segment_from_pixel_box(
    seg: OverlaySegment,
    box: tuple[int, int, int, int],
    *,
    frame_w: int,
    frame_h: int,
    clamp_to: tuple[int, int, int, int] | None,
) -> OverlaySegment:
    fx0, fy0, fx1, fy1 = box
    if clamp_to is not None:
        cx0, cy0, cx1, cy1 = clamp_to
        fx0 = max(fx0, cx0)
        fy0 = max(fy0, cy0)
        fx1 = min(fx1, cx1)
        fy1 = min(fy1, cy1)
    fx0 = max(0, min(frame_w - 1, fx0))
    fy0 = max(0, min(frame_h - 1, fy0))
    fx1 = max(fx0 + 1, min(frame_w, fx1))
    fy1 = max(fy0 + 1, min(frame_h, fy1))
    return OverlaySegment(
        start_ms=seg.start_ms,
        end_ms=seg.end_ms,
        x=fx0 / float(frame_w),
        y=fy0 / float(frame_h),
        width=(fx1 - fx0) / float(frame_w),
        height=(fy1 - fy0) / float(frame_h),
        text_vi=seg.text_vi,
        kind=seg.kind,
    )


def _expand_segment_cover(seg: OverlaySegment) -> tuple[float, float, float, float]:
    """Local cover geometry per kind — OCR/ink box + tiny pad (no wide wipe)."""
    if seg.kind == DENSE_UI_KIND:
        return (
            float(seg.x),
            float(seg.y),
            float(seg.width),
            float(seg.height),
        )
    return expand_cover_rect(
        float(seg.x),
        float(seg.y),
        float(seg.width),
        float(seg.height),
        pad_x=_TIGHT_PAD_X,
        pad_y=_TIGHT_PAD_Y,
        min_width=0.0,
    )


def build_cover_mask(
    frame_bgr: np.ndarray,
    segments: Sequence[OverlaySegment],
    *,
    include_dense_panel: bool = False,
) -> np.ndarray:
    """
    Cover mask for active overlays.

    Default: only per-box OCR rects (``ui`` / ``title`` / ``hardsub``). Dense
    slate panels are skipped unless ``include_dense_panel=True``.
    """
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"frame must be HxWx3 BGR, got {getattr(frame_bgr, 'shape', None)}",
        )
    h, w = frame_bgr.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    if not segments:
        return mask

    for seg in segments:
        if seg.kind == DENSE_UI_KIND and not include_dense_panel:
            continue
        x, y, bw, bh = _expand_segment_cover(seg)
        x0, y0, x1, y1 = _norm_box_to_pixels(x, y, bw, bh, frame_w=w, frame_h=h)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        mask[y0:y1, x0:x1] = 255
    return mask


def apply_blur_cover(
    frame_bgr: np.ndarray,
    mask: np.ndarray,
    *,
    ksize: int = _BLUR_KERNEL,
    passes: int = 2,
) -> np.ndarray:
    """
    Cover text boxes: per-region local background fill, then soft-blur.

    Each connected mask region samples its own surrounding ring so teal bars and
    white cards do not share one global fill color. Outside the mask is unchanged.
    """
    import cv2

    if mask is None or int(mask.max()) == 0:
        return frame_bgr
    cleaned = frame_bgr.copy()
    n_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        (mask > 0).astype(np.uint8), connectivity=8
    )
    ring_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))
    for label in range(1, n_labels):
        region = labels == label
        if not np.any(region):
            continue
        region_u8 = region.astype(np.uint8) * 255
        outer = cv2.dilate(region_u8, ring_k, iterations=1)
        ring = (outer > 0) & (~region)
        if np.any(ring):
            fill = np.median(frame_bgr[ring].astype(np.float64), axis=0)
        else:
            x, y, bw, bh, _area = stats[label]
            y0 = max(0, y - 2)
            x0 = max(0, x - 2)
            y1 = min(frame_bgr.shape[0], y + bh + 2)
            x1 = min(frame_bgr.shape[1], x + bw + 2)
            fill = np.median(
                frame_bgr[y0:y1, x0:x1].reshape(-1, 3).astype(np.float64),
                axis=0,
            )
        cleaned[region] = fill

    k = int(ksize)
    if k < 3:
        k = 3
    if k % 2 == 0:
        k += 1
    region_all = mask > 0
    n_pass = max(1, int(passes))
    for _ in range(n_pass):
        blurred = cv2.GaussianBlur(cleaned, (k, k), 0)
        cleaned[region_all] = blurred[region_all]
    return cleaned


def _vi_colors_for_box(
    frame_bgr: np.ndarray,
    *,
    px: int,
    py: int,
    box_w: int,
    box_h: int,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Pick VI fill/stroke for contrast against the (covered) local background."""
    h, w = frame_bgr.shape[:2]
    x0 = max(0, px)
    y0 = max(0, py)
    x1 = min(w, px + max(1, box_w))
    y1 = min(h, py + max(1, box_h))
    roi = frame_bgr[y0:y1, x0:x1]
    if roi.size == 0:
        return (255, 255, 255), (0, 0, 0)
    # BGR mean → approximate luminance.
    mean_bgr = roi.reshape(-1, 3).mean(axis=0)
    luma = float(0.114 * mean_bgr[0] + 0.587 * mean_bgr[1] + 0.299 * mean_bgr[2])
    if luma >= 140.0:
        # Light card → dark label (readable, less “sticker” look).
        return (28, 28, 28), (245, 245, 245)
    return (255, 255, 255), (0, 0, 0)


def apply_solid_cover(
    frame_bgr: np.ndarray,
    mask: np.ndarray,
    *,
    radius: int = 14,
    opaque_panel: bool = False,
) -> np.ndarray:
    """
    Cover active text regions.

    Default: blur-in-mask (``apply_blur_cover``). ``opaque_panel=True`` keeps the
    legacy neutral slate wipe for callers that still opt in.
    """
    import cv2

    del radius  # API compat.
    if mask is None or int(mask.max()) == 0:
        return frame_bgr
    if not opaque_panel:
        return apply_blur_cover(frame_bgr, mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    dilated = cv2.dilate(mask, kernel, iterations=2)
    cleaned = frame_bgr.copy()
    fill = np.array([52, 48, 46], dtype=np.float64)
    cleaned[dilated > 0] = fill
    soft = cv2.GaussianBlur(cleaned, (9, 9), 0)
    edge = cv2.dilate(dilated, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)
    edge_only = (edge > 0) & (dilated == 0)
    if np.any(edge_only):
        cleaned[edge_only] = soft[edge_only]
    return cleaned


def inpaint_frame(
    frame_bgr: np.ndarray,
    mask: np.ndarray,
    *,
    large_region: bool = False,
    radius: int = 3,
) -> np.ndarray:
    """Restore background under mask; NS for large/endcard regions, else TELEA."""
    import cv2

    if mask is None or int(mask.max()) == 0:
        return frame_bgr
    flags = cv2.INPAINT_NS if large_region else cv2.INPAINT_TELEA
    return cv2.inpaint(frame_bgr, mask, max(1, int(radius)), flags)


def _active_segments(overlays: Sequence[OverlaySegment], time_ms: int) -> list[OverlaySegment]:
    return [seg for seg in overlays if int(seg.start_ms) <= time_ms < int(seg.end_ms)]


def _expanded_boxes_for_segments(segments: Sequence[OverlaySegment]) -> list[tuple[float, float, float, float]]:
    return [_expand_segment_cover(seg) for seg in segments]


def draw_vi_overlays(
    frame_bgr: np.ndarray,
    segments: Sequence[OverlaySegment],
    *,
    fontfile: Path | str,
    align: str = "left",
) -> np.ndarray:
    """Burn Vietnamese text with Pillow; default left-aligned to the OCR box."""
    from PIL import Image, ImageDraw, ImageFont

    if not segments:
        return frame_bgr
    h, w = frame_bgr.shape[:2]
    rgb = frame_bgr[:, :, ::-1].copy()
    img = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(img)
    font_path = Path(fontfile)
    mode = (align or "left").strip().lower()
    for seg in segments:
        if seg.kind == DENSE_UI_KIND:
            continue
        text = (seg.text_vi or "").strip()
        if not text or is_artifact_vi_text(text):
            continue
        # VI uses raw OCR AABB (cover pad stays on the mask path only).
        x0 = float(seg.x)
        y0 = float(seg.y)
        bw = float(seg.width)
        bh = float(seg.height)
        # Match scanned Chinese label height; shrink if VI is wider than the box.
        size = _vi_font_size_px(box_h_px=int(bh * h))
        box_w = max(8, int(bw * w))
        box_h = max(8, int(bh * h))
        px = int(x0 * w)
        py = int(y0 * h)
        stroke = 1
        try:
            font = ImageFont.truetype(str(font_path), size=size)
        except OSError:
            font = ImageFont.load_default()
        # Shrink until text fits width / height of the OCR box.
        for _ in range(8):
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            if tw <= box_w * 0.98 and th <= box_h * 0.98:
                break
            size = max(7, int(size * 0.92))
            try:
                font = ImageFont.truetype(str(font_path), size=size)
            except OSError:
                break
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        if mode == "center":
            tx = px + max(0, (box_w - tw) // 2) - bbox[0]
        else:
            # Left-align to OCR box — matches Chinese UI label layout.
            tx = px + 1 - bbox[0]
        ty = py + max(0, (box_h - th) // 2) - bbox[1]
        fill_rgb, stroke_rgb = _vi_colors_for_box(
            frame_bgr, px=px, py=py, box_w=box_w, box_h=box_h
        )
        draw.text(
            (tx, ty),
            text,
            font=font,
            fill=fill_rgb,
            stroke_width=stroke,
            stroke_fill=stroke_rgb,
        )
    out = np.asarray(img)[:, :, ::-1].copy()
    return out


def _expand_segments_width_for_vi(
    frame_bgr: np.ndarray,
    segments: Sequence[OverlaySegment],
    *,
    fontfile: Path | str,
) -> list[OverlaySegment]:
    """Grow box width to the right when VI text is wider than the OCR AABB."""
    from PIL import Image, ImageDraw, ImageFont

    if not segments:
        return []
    h, w = frame_bgr.shape[:2]
    probe = Image.new("RGB", (max(8, w), max(8, h)), (0, 0, 0))
    draw = ImageDraw.Draw(probe)
    font_path = Path(fontfile)
    out: list[OverlaySegment] = []
    for seg in segments:
        if seg.kind == DENSE_UI_KIND:
            out.append(seg)
            continue
        text = (seg.text_vi or "").strip()
        if not text or is_artifact_vi_text(text):
            out.append(seg)
            continue
        bw = float(seg.width)
        bh = float(seg.height)
        size = _vi_font_size_px(box_h_px=int(bh * h))
        try:
            font = ImageFont.truetype(str(font_path), size=size)
        except OSError:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        tw = bbox[2] - bbox[0]
        need_w = max(float(seg.width), (tw + 4) / float(w))
        # Keep left edge; grow right, clamp to frame.
        max_w = max(0.01, 1.0 - float(seg.x) - 0.01)
        out.append(
            OverlaySegment(
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                x=float(seg.x),
                y=float(seg.y),
                width=min(max_w, max(float(seg.width), need_w)),
                height=float(seg.height),
                text_vi=seg.text_vi,
                kind=seg.kind,
            )
        )
    return out


def process_frame_bgr(
    frame_bgr: np.ndarray,
    segments: Sequence[OverlaySegment],
    *,
    fontfile: Path | str,
) -> np.ndarray:
    """Cover Chinese (dense panel and/or OCR boxes) → burn VI on label boxes.

    Dense endcards: wipe the near-full ``dense_ui`` panel (OCR authority for VI —
    no ink-snap, which otherwise drifts off white-card labels). Sparse hard-sub /
    title: snap VI to ink inside each OCR box, then local cover.
    """
    if not segments:
        return frame_bgr
    panel_segs = [seg for seg in segments if seg.kind == DENSE_UI_KIND]
    text_segs = [seg for seg in segments if seg.kind != DENSE_UI_KIND]
    if not text_segs and not panel_segs:
        return frame_bgr
    if panel_segs:
        # Full-screen Chinese UI: panel wipe + VI at OCR boxes (no refine drift).
        cover_segs = list(panel_segs) + list(text_segs)
        mask = build_cover_mask(frame_bgr, cover_segs, include_dense_panel=True)
        cleaned = apply_blur_cover(frame_bgr, mask)
        if not text_segs:
            return cleaned
        return draw_vi_overlays(cleaned, text_segs, fontfile=fontfile, align="left")
    text_segs = refine_segments_to_ink_inside_ocr(frame_bgr, text_segs)
    mask = build_cover_mask(frame_bgr, text_segs)
    cleaned = apply_blur_cover(frame_bgr, mask)
    return draw_vi_overlays(cleaned, text_segs, fontfile=fontfile, align="left")


def render_image_opencv_inpaint(
    source_image: Path | str,
    output_image: Path | str,
    overlays: Sequence[OverlaySegment],
    *,
    fontfile: Path | str | None = None,
) -> Path:
    """Still-image path (thumbnail): mask + inpaint + VI."""
    import cv2

    source = Path(source_image)
    output = Path(output_image)
    if not source.is_file():
        raise VideoRendererError(
            VideoRendererErrorCode.SOURCE_MISSING,
            f"Source image missing: {source}",
        )
    frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if frame is None:
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"Cannot read image: {source}",
        )
    font = resolve_drawtext_font(fontfile)
    # Treat as t=0 for thumbnail overlays (caller already filtered).
    active = list(overlays) if overlays else []
    out = process_frame_bgr(frame, active, fontfile=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), out):
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"Failed to write inpainted image: {output}",
        )
    return output.resolve()


def _even_dimension(value: int) -> int:
    """libx264 requires even width/height."""
    v = max(2, int(value))
    return v if v % 2 == 0 else v - 1


def read_exact_bytes(stream, size: int) -> bytes:
    """
    Read exactly ``size`` bytes (or short on EOF).

    Windows pipes often return partial reads; treating that as EOF yields 0-frame
    encodes that still produce a tiny 0s MP4 and a false COMPLETED job.
    """
    need = max(0, int(size))
    if need == 0:
        return b""
    chunks: list[bytes] = []
    got = 0
    while got < need:
        chunk = stream.read(need - got)
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode("latin1")
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def _drain_pipe(pipe) -> bytearray:
    """Read subprocess pipe to completion (avoids stderr deadlock)."""
    buf = bytearray()
    if pipe is None:
        return buf
    try:
        while True:
            chunk = pipe.read(65536)
            if not chunk:
                break
            if isinstance(chunk, str):
                buf.extend(chunk.encode("utf-8", errors="replace"))
            else:
                buf.extend(chunk)
            # Guard against mock/infinite non-empty reads.
            if len(buf) > 2_000_000:
                break
    except Exception:
        pass
    return buf


def _parse_fractional_fps(raw: str) -> float | None:
    text = str(raw or "").strip()
    if "/" not in text:
        return None
    num_s, den_s = text.split("/", 1)
    try:
        num, den = float(num_s), float(den_s)
    except ValueError:
        return None
    if den <= 0 or num <= 0:
        return None
    return max(1.0, min(60.0, num / den))


def _parse_stream_fps(stream: Mapping[str, Any] | dict[str, Any]) -> float | None:
    """Prefer nominal ``r_frame_rate`` over ``avg_frame_rate`` (avoids 29s→33s stretch)."""
    for key in ("r_frame_rate", "avg_frame_rate"):
        parsed = _parse_fractional_fps(str(stream.get(key) or ""))
        if parsed is not None:
            return parsed
    return None


def mux_output_trim_args(duration_ms: int | None) -> list[str]:
    """Cap muxed output to source duration so long audio cannot inflate container length."""
    ms = int(duration_ms or 0)
    if ms <= 0:
        return []
    return ["-t", f"{ms / 1000.0:.3f}"]


def _probe_fps(source: Path, *, ffmpeg_binary: str) -> float:
    from src.media_pipeline.video_renderer.renderer import _resolve_ffprobe_binary

    ffprobe = _resolve_ffprobe_binary(ffmpeg_binary)
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate,avg_frame_rate",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return 25.0
    import json

    try:
        payload = json.loads(completed.stdout or "{}")
        stream = (payload.get("streams") or [{}])[0]
        parsed = _parse_stream_fps(stream)
        if parsed is not None:
            return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return 25.0


def render_video_opencv_inpaint(
    source_video: Path | str,
    output_video: Path | str,
    overlays: Sequence[OverlaySegment],
    *,
    fontfile: Path | str | None = None,
    anti_seed: int | None = None,
    ffmpeg_binary: str = "ffmpeg",
    progress: bool | ProgressCallback = True,
    frame_width: int | None = None,
    frame_height: int | None = None,
    attached_pic: Path | str | None = None,
) -> Path:
    """
    Decode → per-frame inpaint+VI (passthrough when idle) → encode with anti-hash.

    Audio is remuxed from source; optional attached_pic mapped as MJPEG cover.
    """
    from src.media_pipeline.video_renderer.renderer import (
        probe_video_duration_ms,
        probe_video_frame_size,
    )

    source = Path(source_video)
    output = Path(output_video)
    if shutil.which(ffmpeg_binary) is None:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_MISSING,
            f"ffmpeg binary not found on PATH ({ffmpeg_binary})",
        )
    if not source.is_file():
        raise VideoRendererError(
            VideoRendererErrorCode.SOURCE_MISSING,
            f"Source video missing: {source}",
        )
    if not overlays:
        raise VideoRendererError(
            VideoRendererErrorCode.EMPTY_OVERLAYS,
            "overlays is empty",
        )

    width = int(frame_width or 0)
    height = int(frame_height or 0)
    if width < 2 or height < 2:
        width, height = probe_video_frame_size(source, ffmpeg_binary=ffmpeg_binary)
    width = _even_dimension(width)
    height = _even_dimension(height)
    fps = _probe_fps(source, ffmpeg_binary=ffmpeg_binary)
    duration_ms = probe_video_duration_ms(source, ffmpeg_binary=ffmpeg_binary) or 0
    total_frames = max(1, int(round((duration_ms / 1000.0) * fps))) if duration_ms else 0

    font = resolve_drawtext_font(fontfile)
    anti = ",".join(build_anti_detection_filters(seed=anti_seed)) or "null"
    output.parent.mkdir(parents=True, exist_ok=True)

    # Two-phase: encode video-only from pipe (no -shortest race with audio), then mux.
    video_only = output.with_suffix(".inpaint.mp4")
    frame_bytes = width * height * 3
    # Force CFR on decode to match encode -r (prevents VFR/avg mismatch stretching duration).
    fps_s = f"{fps:.4f}".rstrip("0").rstrip(".")
    decode_cmd = [
        ffmpeg_binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-an",
        "-vf",
        f"fps={fps_s},scale={width}:{height}:flags=bicubic,format=bgr24",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-",
    ]
    encode_cmd = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps:.4f}",
        "-i",
        "-",
        "-vf",
        anti,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(video_only),
    ]

    on_progress: ProgressCallback | None
    if progress is True:

        def _default(seconds: float | None, raw: str) -> None:
            if seconds is None:
                return
            print(f"\rinpaint render time={seconds:7.2f}s", end="", file=sys.stderr, flush=True)

        on_progress = _default
    elif progress is False:
        on_progress = None
    else:
        on_progress = progress

    try:
        import tqdm  # type: ignore

        use_tqdm = progress is True
    except ImportError:
        use_tqdm = False

    decoder = subprocess.Popen(
        decode_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=10**7,
    )
    encoder = subprocess.Popen(
        encode_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=10**7,
    )
    assert decoder.stdout is not None
    assert encoder.stdin is not None

    import threading

    enc_err_buf = bytearray()
    dec_err_buf = bytearray()

    def _drain_enc() -> None:
        enc_err_buf.extend(_drain_pipe(encoder.stderr))

    def _drain_dec() -> None:
        dec_err_buf.extend(_drain_pipe(decoder.stderr))

    enc_drain = threading.Thread(target=_drain_enc, daemon=True)
    dec_drain = threading.Thread(target=_drain_dec, daemon=True)
    enc_drain.start()
    dec_drain.start()

    frame_index = 0
    bar = None
    if use_tqdm and total_frames > 0:
        bar = tqdm.tqdm(total=total_frames, desc="inpaint", unit="frame", leave=False)
    pipe_error: BaseException | None = None

    try:
        while True:
            raw = read_exact_bytes(decoder.stdout, frame_bytes)
            if len(raw) < frame_bytes:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3)).copy()
            time_ms = int(round(frame_index * 1000.0 / fps))
            active = _active_segments(overlays, time_ms)
            out_frame = process_frame_bgr(frame, active, fontfile=font)
            try:
                encoder.stdin.write(out_frame.tobytes())
            except BrokenPipeError as exc:
                pipe_error = exc
                break
            frame_index += 1
            if bar is not None:
                bar.update(1)
            elif on_progress is not None and frame_index % max(1, int(fps)) == 0:
                on_progress(time_ms / 1000.0, f"frame={frame_index}")
    except Exception as exc:
        pipe_error = exc
    finally:
        if bar is not None:
            bar.close()
        try:
            if encoder.stdin:
                encoder.stdin.flush()
        except Exception:
            pass
        try:
            if encoder.stdin:
                encoder.stdin.close()
        except Exception:
            pass
        try:
            if decoder.stdout:
                decoder.stdout.close()
        except Exception:
            pass

    dec_code = decoder.wait(timeout=120)
    enc_code = encoder.wait(timeout=600)
    enc_drain.join(timeout=5)
    dec_drain.join(timeout=5)
    enc_err = enc_err_buf.decode("utf-8", errors="replace").strip()
    dec_err = dec_err_buf.decode("utf-8", errors="replace").strip()

    if pipe_error is not None or enc_code != 0:
        detail = enc_err or dec_err or str(pipe_error or "encode failed")
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"OpenCV inpaint render failed: {pipe_error or f'exit={enc_code}'}; ffmpeg: {detail[:500]}",
        )
    if frame_index < 1:
        detail = dec_err or enc_err or f"decode_exit={dec_code}"
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"OpenCV inpaint produced 0 frames (would be 0s video). {detail[:400]}",
        )
    if not video_only.is_file() or video_only.stat().st_size <= 0:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"OpenCV inpaint encode wrote empty file; ffmpeg: {(enc_err or dec_err)[:400]}",
        )

    encoded_ms = probe_video_duration_ms(video_only, ffmpeg_binary=ffmpeg_binary) or 0
    if encoded_ms < 200:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"OpenCV inpaint output too short ({encoded_ms}ms, frames={frame_index}); "
            f"ffmpeg: {(enc_err or dec_err)[:300]}",
        )

    attach = Path(attached_pic) if attached_pic is not None else None
    if attach is not None and not attach.is_file():
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"attached_pic missing: {attach}",
        )

    mux_cmd: list[str] = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_only),
        "-i",
        str(source),
    ]
    if attach is not None:
        mux_cmd.extend(["-i", str(attach)])
        mux_cmd.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "1:a?",
                "-map",
                "2:v:0",
                "-c:v:0",
                "copy",
                "-c:v:1",
                "mjpeg",
                "-disposition:v:1",
                "attached_pic",
                "-c:a",
                "copy",
                *mux_output_trim_args(duration_ms),
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
    else:
        mux_cmd.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "1:a?",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                *mux_output_trim_args(duration_ms),
                "-movflags",
                "+faststart",
                str(output),
            ]
        )

    mux = subprocess.run(mux_cmd, capture_output=True, text=True, check=False)
    try:
        video_only.unlink(missing_ok=True)
    except OSError:
        pass
    if mux.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"inpaint mux failed: {(mux.stderr or mux.stdout or '')[:400]}",
        )

    final_ms = probe_video_duration_ms(output, ffmpeg_binary=ffmpeg_binary) or 0
    if final_ms < 200:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"Cleaned video is {final_ms}ms after mux (expected ~{encoded_ms}ms). "
            f"mux: {(mux.stderr or '')[:300]}",
        )

    if on_progress is not None:
        print(file=sys.stderr)
    logger.info(
        "opencv_inpaint_render_done",
        extra={"frames": frame_index, "output": str(output), "fps": fps, "duration_ms": final_ms},
    )
    return output.resolve()
