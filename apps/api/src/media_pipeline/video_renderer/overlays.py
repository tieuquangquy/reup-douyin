"""Overlay segments for Single Render (mask box + Vietnamese text)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.media_pipeline.video_renderer.errors import VideoRendererError, VideoRendererErrorCode

DEFAULT_HOLD_MS = 500
# Pads larger than OCR crumbs so stylized glyph edges are not left uncovered.
DEFAULT_PAD_X = 0.08
DEFAULT_PAD_Y = 0.07
# Hard-sub lines are usually near full-width; expand narrow OCR unions.
DEFAULT_MIN_COVER_WIDTH = 0.88
DEFAULT_SIDE_MARGIN = 0.04
# delogo must not touch frame edges.
DEFAULT_EDGE_INSET = 0.01
# Dense UI / nutrition end-card: one near-full content panel.
ENDCARD_PANEL_INSET = 0.04
ENDCARD_PANEL_MIN_WIDTH = 0.90
ENDCARD_PANEL_MIN_HEIGHT = 0.72
ENDCARD_VI_MAX_CHARS = 40

DENSE_UI_KIND = "dense_ui"
DENSE_UI_PANEL_INSET = 0.04
DENSE_UI_BOTTOM_GAP = 0.02

# Cover-safety (all videos): refuse detector false-positives that are too big
# to be a subtitle / UI label line — those wipe food when covered.
# Thresholds from size-class invariants (line/label vs mid-frame slab), not one clip.
# Keep compact vertical labels (e.g. 加盐): small area + height under the line cap.
MAX_TEXT_COVER_HEIGHT = 0.12
MAX_TEXT_COVER_AREA = 0.05
MAX_TEXT_COVER_WIDTH = 0.92


def is_plausible_text_cover_segment(seg: OverlaySegment) -> bool:
    """
    True when ``seg`` is small enough to be on-screen text cover.

    Oversized mid-frame boxes (food mis-detected as text) must not be painted.
    Dense UI panels are always allowed (explicit full-card wipe).
    Compact vertical labels stay allowed when under height/area caps.
    """
    kind = str(getattr(seg, "kind", "") or "")
    if kind == DENSE_UI_KIND:
        return True
    width = float(getattr(seg, "width", 0.0) or 0.0)
    height = float(getattr(seg, "height", 0.0) or 0.0)
    if width <= 0.0 or height <= 0.0:
        return False
    if width > MAX_TEXT_COVER_WIDTH:
        return False
    if (width * height) > MAX_TEXT_COVER_AREA:
        return False
    if height > MAX_TEXT_COVER_HEIGHT:
        return False
    return True


def dense_ui_content_panel(
    *,
    band_ratio: float | None = None,
    inset: float = DENSE_UI_PANEL_INSET,
    bottom_gap: float = DENSE_UI_BOTTOM_GAP,
) -> tuple[float, float, float, float]:
    """
    Near-full-frame wipe for dense Chinese UI (nutrition / endcard overlays).

    ``band_ratio`` / ``bottom_gap`` are kept for call-site compat but ignored —
    full-screen CJK UI needs the panel to cover past the old subtitle cut.
    """
    del band_ratio, bottom_gap  # compat kwargs; full-frame wipe is intentional
    edge = max(0.02, float(inset))
    span = max(0.50, 1.0 - 2.0 * edge)
    return edge, edge, span, span


def is_artifact_vi_text(text: str) -> bool:
    """True for pipeline/filename strings that must never be burned as captions."""
    raw = (text or "").strip()
    if not raw:
        return False
    if raw == "...":
        return True
    if raw.startswith("[vi]") or (raw.startswith("[") and raw.endswith("]")):
        return True
    lowered = raw.lower()
    if "ocr_pipeline" in lowered:
        return True
    if lowered.endswith(".mp4") or lowered.endswith(".mp"):
        return True
    if "__v" in lowered and "_cleaned" in lowered:
        return True
    return False


def gate_vi_for_burn(text: str) -> str:
    """
    Fail-closed for burn-in: empty / ``...`` / artifact / residual CJK → ``\"\"``.

    Cover geometry still runs; only the Vietnamese draw string is suppressed.
    """
    from src.media_pipeline.ocr_filtering.script_filter import contains_cjk

    raw = str(text or "").strip()
    if not raw:
        return ""
    if is_artifact_vi_text(raw):
        return ""
    if contains_cjk(raw):
        return ""
    return raw


@dataclass(frozen=True)
class OverlaySegment:
    """One timed subtitle cover + Vietnamese burn-in (normalized xywh 0–1)."""

    start_ms: int
    end_ms: int
    x: float
    y: float
    width: float
    height: float
    text_vi: str
    kind: str = "hardsub"
    authority_bounds: tuple[float, float, float, float] | None = None


def expand_cover_rect(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    pad_x: float = DEFAULT_PAD_X,
    pad_y: float = DEFAULT_PAD_Y,
    min_width: float = DEFAULT_MIN_COVER_WIDTH,
    side_margin: float = DEFAULT_SIDE_MARGIN,
    edge_inset: float = DEFAULT_EDGE_INSET,
) -> tuple[float, float, float, float]:
    """Pad OCR box, then expand horizontally so hard-sub glyphs are fully covered."""
    inset = max(0.0, float(edge_inset))
    side = max(inset, float(side_margin))
    x0 = max(inset, float(x) - float(pad_x))
    y0 = max(inset, float(y) - float(pad_y))
    x1 = min(1.0 - inset, float(x) + float(width) + float(pad_x))
    y1 = min(1.0 - inset, float(y) + float(height) + float(pad_y))
    bw = max(0.01, x1 - x0)
    bh = max(0.01, y1 - y0)

    target_w = min(float(min_width), 1.0 - 2.0 * side)
    if bw < target_w:
        cx = x0 + bw / 2.0
        bw = target_w
        x0 = max(side, min(1.0 - side - bw, cx - bw / 2.0))

    # Keep clear of frame edges (required by ffmpeg delogo).
    x0 = max(inset, min(x0, 1.0 - inset - 0.01))
    y0 = max(inset, min(y0, 1.0 - inset - 0.01))
    bw = min(bw, 1.0 - inset - x0)
    bh = min(bh, 1.0 - inset - y0)
    return x0, y0, max(0.01, bw), max(0.01, bh)


def expand_endcard_panel(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    inset: float = ENDCARD_PANEL_INSET,
    min_width: float = ENDCARD_PANEL_MIN_WIDTH,
    min_height: float = ENDCARD_PANEL_MIN_HEIGHT,
) -> tuple[float, float, float, float]:
    """
    Grow OCR union into one near-full content panel for dense UI screenshots.

    Per-line covers leave Chinese labels readable; one opaque panel is the Phase-1
    optimal path for nutrition / app end-cards.
    """
    edge = max(0.02, float(inset))
    x0 = max(edge, float(x) - 0.04)
    y0 = max(edge, float(y) - 0.04)
    x1 = min(1.0 - edge, float(x) + float(width) + 0.04)
    y1 = min(1.0 - edge, float(y) + float(height) + 0.04)
    bw = max(0.01, x1 - x0)
    bh = max(0.01, y1 - y0)
    target_w = min(float(min_width), 1.0 - 2.0 * edge)
    target_h = min(float(min_height), 1.0 - 2.0 * edge)
    if bw < target_w:
        cx = x0 + bw / 2.0
        bw = target_w
        x0 = max(edge, min(1.0 - edge - bw, cx - bw / 2.0))
    if bh < target_h:
        cy = y0 + bh / 2.0
        bh = target_h
        y0 = max(edge, min(1.0 - edge - bh, cy - bh / 2.0))
    bw = min(bw, 1.0 - edge - x0)
    bh = min(bh, 1.0 - edge - y0)
    return x0, y0, max(0.01, bw), max(0.01, bh)


def summarize_endcard_vi(text: str, *, max_chars: int = ENDCARD_VI_MAX_CHARS) -> str:
    """Keep a single short Vietnamese caption for the opaque endcard panel."""
    raw = (text or "").strip()
    if not raw:
        return "Tong quan bua an"
    for sep in ("、", "，", ",", ";", "；", "|", "/"):
        if sep in raw:
            raw = raw.split(sep, 1)[0].strip()
            break
    limit = max(12, int(max_chars))
    if len(raw) <= limit:
        return raw
    cut = raw[: limit - 1].rsplit(" ", 1)[0].strip()
    if len(cut) < 8:
        cut = raw[: limit - 1].strip()
    return cut + "…"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _authority_bounds_from_box(
    box: Mapping[str, Any],
) -> tuple[float, float, float, float] | None:
    raw = box.get("cover_bounds")
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    x, y, w, h = (_as_float(value) for value in raw)
    if w <= 0.0 or h <= 0.0:
        return None
    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))
    w = max(0.001, min(w, 1.0 - x))
    h = max(0.001, min(h, 1.0 - y))
    return x, y, w, h


def _union_boxes(boxes: list[Mapping[str, Any]]) -> tuple[float, float, float, float] | None:
    if not boxes:
        return None
    xs0: list[float] = []
    ys0: list[float] = []
    xs1: list[float] = []
    ys1: list[float] = []
    for box in boxes:
        x = _as_float(box.get("x"))
        y = _as_float(box.get("y"))
        w = max(0.01, _as_float(box.get("width"), 0.01))
        h = max(0.01, _as_float(box.get("height"), 0.01))
        xs0.append(x)
        ys0.append(y)
        xs1.append(x + w)
        ys1.append(y + h)
    x0 = max(0.0, min(xs0))
    y0 = max(0.0, min(ys0))
    x1 = min(1.0, max(xs1))
    y1 = min(1.0, max(ys1))
    return x0, y0, max(0.01, x1 - x0), max(0.01, y1 - y0)


def _lookup_vi(
    vi_texts: Mapping[Any, str],
    *,
    time_ms: int,
    frame_id: str,
    cluster_index: int | None = None,
) -> str:
    if cluster_index is not None:
        cluster_key = f"{time_ms}#{cluster_index}"
        if cluster_key in vi_texts:
            return str(vi_texts[cluster_key])
    if time_ms in vi_texts:
        return str(vi_texts[time_ms])
    key_str = str(time_ms)
    if key_str in vi_texts:
        return str(vi_texts[key_str])
    if frame_id in vi_texts:
        return str(vi_texts[frame_id])
    # Loose match: nearest lower key among int-like keys.
    int_keys = sorted(k for k in vi_texts.keys() if isinstance(k, int))
    candidates = [k for k in int_keys if k <= time_ms]
    if candidates:
        return str(vi_texts[candidates[-1]])
    return "[VI mock]"


def overlays_from_ocr_payload(
    payload: Mapping[str, Any] | list[Mapping[str, Any]],
    vi_texts: Mapping[Any, str],
    *,
    hold_ms: int = DEFAULT_HOLD_MS,
    pad_x: float = DEFAULT_PAD_X,
    pad_y: float = DEFAULT_PAD_Y,
    video_duration_ms: int | None = None,
) -> list[OverlaySegment]:
    """
    Build timed overlays from Phase 2 OCR (+ VI map).

    - Latin/VI-only boxes are skipped for per-label VI (CJK gate).
    - Sparse frames: one segment per CJK box (local cover + VI).
    - Truly dense endcards (``is_endcard_dense``): also emit a ``dense_ui``
      slate panel above the subtitle band. Late-clip alone does **not** force
      a panel (avoids the ugly wipe when OCR only saw the bottom caption).
    """
    from src.media_pipeline.ocr_filtering.box_payload import box_norm_xywh
    from src.media_pipeline.ocr_filtering.overlay_zones import (
        is_endcard_dense,
        overlay_kind_for_box,
    )
    from src.media_pipeline.ocr_filtering.script_filter import contains_cjk
    from src.media_pipeline.ocr_filtering.types import DetectedTextBox

    del pad_x, pad_y
    endcard_mode = ""
    if isinstance(payload, list):
        frames = list(payload)
    else:
        frames = list(payload.get("frames") or [])
        endcard_mode = str(payload.get("endcard_mode") or "").strip().lower()
    if not frames:
        raise VideoRendererError(
            VideoRendererErrorCode.EMPTY_OVERLAYS,
            "OCR payload has no frames",
        )

    duration_ms = int(video_duration_ms) if video_duration_ms is not None else 0

    # (time_ms, frame_id, box_index, xywh, kind, authority_bounds)
    # dense_ui panel uses box_index=-1.
    prepared: list[
        tuple[
            int,
            str,
            int,
            tuple[float, float, float, float],
            str,
            tuple[float, float, float, float] | None,
        ]
    ] = []
    for frame in frames:
        if not isinstance(frame, Mapping):
            continue
        raw_boxes = [b for b in list(frame.get("boxes") or []) if isinstance(b, Mapping)]
        if not raw_boxes:
            continue
        time_ms = int(frame.get("time_ms") or 0)
        frame_id = str(frame.get("frame_id") or f"t{time_ms}")
        frame_state = str(frame.get("frame_state") or "").strip().lower()

        text_boxes = [
            b for b in raw_boxes if str(b.get("text") or "").strip()
        ]
        cover_only_boxes = [
            b for b in raw_boxes if bool(b.get("cover_only"))
        ]
        if not text_boxes and not cover_only_boxes:
            continue

        cjk_items: list[tuple[DetectedTextBox, tuple[float, float, float, float], str]] = []
        for box in text_boxes:
            text = str(box.get("text") or "").strip()
            if not contains_cjk(text):
                continue
            x, y, w, h = box_norm_xywh(box)
            detected = DetectedTextBox(
                x=x,
                y=y,
                width=w,
                height=h,
                text=text,
                confidence=float(box.get("confidence") or 0.0),
            )
            kind = overlay_kind_for_box(detected)
            cjk_items.append((detected, (x, y, w, h), kind))

        dense_endcard = bool(cjk_items) and is_endcard_dense(
            [item[0] for item in cjk_items]
        )
        # Prefer per-box cover for text_only endcards (full panel blur samples
        # food background and paints an ugly brown slate).
        force_panel = dense_endcard and endcard_mode != "text_only"

        if not cjk_items and not cover_only_boxes and not force_panel:
            continue

        if force_panel:
            prepared.append(
                (
                    time_ms,
                    frame_id,
                    -1,
                    dense_ui_content_panel(),
                    DENSE_UI_KIND,
                    None,
                )
            )

        for box_index, (_detected, xywh, kind) in enumerate(cjk_items):
            source = next(
                (
                    box
                    for box in text_boxes
                    if box_norm_xywh(box) == xywh
                    and str(box.get("text") or "").strip() == _detected.text
                ),
                None,
            )
            bounds = _authority_bounds_from_box(source) if source is not None else None
            prepared.append((time_ms, frame_id, box_index, xywh, kind, bounds))

        # Cover-only geometry (chrome / missed OCR) — every frame, not only endcard.
        for box in cover_only_boxes:
            x, y, w, h = box_norm_xywh(box)
            prepared.append(
                (
                    time_ms,
                    frame_id,
                    -2,
                    (x, y, w, h),
                    "ui",
                    _authority_bounds_from_box(box),
                )
            )
        if dense_endcard and endcard_mode == "text_only":
            for box in text_boxes:
                text = str(box.get("text") or "").strip()
                if contains_cjk(text):
                    continue
                x, y, w, h = box_norm_xywh(box)
                prepared.append(
                    (
                        time_ms,
                        frame_id,
                        -2,
                        (x, y, w, h),
                        "ui",
                        _authority_bounds_from_box(box),
                    )
                )

    if not prepared:
        raise VideoRendererError(
            VideoRendererErrorCode.EMPTY_OVERLAYS,
            "No Chinese boxes left to cover after OCR payload parse",
        )

    prepared.sort(key=lambda item: (item[0], item[2]))
    hold = max(0, int(hold_ms))
    unique_times = sorted({item[0] for item in prepared})
    next_time: dict[int, int] = {}
    for i, t in enumerate(unique_times):
        if i + 1 < len(unique_times):
            next_time[t] = unique_times[i + 1]
        else:
            end = t + hold
            if duration_ms > t:
                end = max(end, duration_ms)
            next_time[t] = end

    overlays: list[OverlaySegment] = []
    for time_ms, frame_id, box_index, (x, y, w, h), kind, bounds in prepared:
        end_ms = next_time[time_ms]
        if end_ms <= time_ms:
            end_ms = time_ms + max(hold, 50)
        if kind == DENSE_UI_KIND or box_index < 0:
            text_vi = ""
        else:
            text_vi = _lookup_vi(
                vi_texts,
                time_ms=time_ms,
                frame_id=frame_id,
                cluster_index=box_index,
            )
            text_vi = gate_vi_for_burn(text_vi)
        overlays.append(
            OverlaySegment(
                start_ms=time_ms,
                end_ms=end_ms,
                x=x,
                y=y,
                width=w,
                height=h,
                text_vi=text_vi,
                kind=kind,
                authority_bounds=bounds,
            )
        )
    return overlays
