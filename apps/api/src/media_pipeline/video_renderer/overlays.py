"""Overlay segments for Single Render (mask box + Vietnamese text)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.media_pipeline.video_renderer.errors import VideoRendererError, VideoRendererErrorCode

DEFAULT_HOLD_MS = 500
DEFAULT_PAD_X = 0.015
DEFAULT_PAD_Y = 0.02


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


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
) -> str:
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
) -> list[OverlaySegment]:
    """
    Build timed overlays from Phase 2 `OcrFilteringResult.to_dict()` (+ VI map).

    Geometry: union of filtered boxes per frame (bottom-band already applied upstream).
    Timing: [time_ms, next_time_ms) ; last frame extends by hold_ms.
    Padding is applied later in `build_single_render_filter` (pad_x/pad_y kept for API compat).
    """
    del pad_x, pad_y
    if isinstance(payload, list):
        frames = list(payload)
    else:
        frames = list(payload.get("frames") or [])
    if not frames:
        raise VideoRendererError(
            VideoRendererErrorCode.EMPTY_OVERLAYS,
            "OCR payload has no frames",
        )

    prepared: list[tuple[int, str, tuple[float, float, float, float]]] = []
    for frame in frames:
        if not isinstance(frame, Mapping):
            continue
        boxes = list(frame.get("boxes") or [])
        union = _union_boxes([b for b in boxes if isinstance(b, Mapping)])
        if union is None:
            continue
        time_ms = int(frame.get("time_ms") or 0)
        frame_id = str(frame.get("frame_id") or f"t{time_ms}")
        prepared.append((time_ms, frame_id, union))

    if not prepared:
        raise VideoRendererError(
            VideoRendererErrorCode.EMPTY_OVERLAYS,
            "No boxes left to cover after OCR payload parse",
        )

    prepared.sort(key=lambda item: item[0])
    hold = max(0, int(hold_ms))
    overlays: list[OverlaySegment] = []
    for index, (time_ms, frame_id, (x, y, w, h)) in enumerate(prepared):
        if index + 1 < len(prepared):
            end_ms = prepared[index + 1][0]
        else:
            end_ms = time_ms + hold
        if end_ms <= time_ms:
            end_ms = time_ms + max(hold, 50)

        overlays.append(
            OverlaySegment(
                start_ms=time_ms,
                end_ms=end_ms,
                x=x,
                y=y,
                width=w,
                height=h,
                text_vi=_lookup_vi(vi_texts, time_ms=time_ms, frame_id=frame_id),
            )
        )
    return overlays
