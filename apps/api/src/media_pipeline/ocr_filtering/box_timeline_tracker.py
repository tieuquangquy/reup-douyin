"""Temporal box hold/track: sparse OCR observations → dense per-frame boxes.

Cloud OCR is the box authority. Between OCR ticks, the last observation is held
forward (no interpolation). Matching across ticks is IoU-based for logging /
segment identity only; densify uses hold-forward of the latest OCR frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class TimedBox:
    """Normalized xywh box at one OCR observation."""

    x: float
    y: float
    w: float
    h: float
    text: str = ""
    confidence: float = 0.0
    cover_only: bool = False
    cover_bounds: tuple[float, float, float, float] | None = None

    def as_xyxy(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": round(float(self.x), 6),
            "y": round(float(self.y), 6),
            "w": round(float(self.w), 6),
            "h": round(float(self.h), 6),
            "text": self.text,
            "confidence": round(float(self.confidence), 4),
            **({"cover_only": True} if self.cover_only else {}),
            **(
                {"cover_bounds": [round(float(value), 6) for value in self.cover_bounds]}
                if self.cover_bounds is not None
                else {}
            ),
        }


@dataclass(frozen=True)
class OcrObservation:
    time_ms: int
    boxes: tuple[TimedBox, ...]


def box_iou(a: TimedBox, b: TimedBox) -> float:
    ax0, ay0, ax1, ay1 = a.as_xyxy()
    bx0, by0, bx1, by1 = b.as_xyxy()
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    if union <= 1e-12:
        return 0.0
    return float(inter / union)


def match_boxes_by_iou(
    previous: Sequence[TimedBox],
    current: Sequence[TimedBox],
    *,
    iou_thresh: float = 0.3,
) -> list[tuple[int, int, float]]:
    """
    Greedy one-to-one matches (prev_idx, curr_idx, iou) with IoU >= thresh.
    """
    pairs: list[tuple[float, int, int]] = []
    for i, a in enumerate(previous):
        for j, b in enumerate(current):
            iou = box_iou(a, b)
            if iou >= float(iou_thresh):
                pairs.append((iou, i, j))
    pairs.sort(reverse=True)
    used_prev: set[int] = set()
    used_curr: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for iou, i, j in pairs:
        if i in used_prev or j in used_curr:
            continue
        used_prev.add(i)
        used_curr.add(j)
        matches.append((i, j, iou))
    return matches


def densify_hold_forward(
    observations: Sequence[OcrObservation],
    frame_times_ms: Sequence[int],
    *,
    skip_empty: bool = False,
) -> list[dict[str, Any]]:
    """
    For each frame time, emit boxes from the latest OCR observation at or before it.

    Frames before the first observation get ``boxes=[]``.

    When ``skip_empty`` is True, empty OCR ticks (misses) do not wipe the previous
    non-empty hold — required so sparse Cloud OCR misses do not clear hardsubs.
    """
    if not frame_times_ms:
        return []
    obs = sorted(observations, key=lambda o: o.time_ms)
    if skip_empty:
        obs = [o for o in obs if o.boxes]
    out: list[dict[str, Any]] = []
    oi = -1
    for time_ms in frame_times_ms:
        while oi + 1 < len(obs) and obs[oi + 1].time_ms <= int(time_ms):
            oi += 1
        if oi < 0:
            boxes: list[dict[str, Any]] = []
            source_ms = None
        else:
            boxes = [b.to_dict() for b in obs[oi].boxes]
            source_ms = obs[oi].time_ms
        out.append(
            {
                "time_ms": int(time_ms),
                "boxes": boxes,
                "ocr_source_ms": source_ms,
            }
        )
    return out


def observations_from_ocr_payload(
    frames: Sequence[dict[str, Any]],
    *,
    min_confidence: float = 0.3,
    require_text: bool = True,
) -> list[OcrObservation]:
    """Build observations from OCR JSON-like frame dicts (path/time_ms/boxes)."""
    out: list[OcrObservation] = []
    for fr in frames:
        time_ms = int(fr.get("time_ms") or 0)
        raw_boxes = fr.get("boxes") or []
        kept: list[TimedBox] = []
        for b in raw_boxes:
            text = str(b.get("text") or "").strip()
            conf = float(b.get("confidence") or b.get("conf") or 0.0)
            if require_text and not text:
                continue
            if conf < float(min_confidence):
                continue
            w = float(b.get("w") if "w" in b else b.get("width") or 0.0)
            h = float(b.get("h") if "h" in b else b.get("height") or 0.0)
            if w <= 0 or h <= 0:
                continue
            kept.append(
                TimedBox(
                    x=float(b.get("x") or 0.0),
                    y=float(b.get("y") or 0.0),
                    w=w,
                    h=h,
                    text=text,
                    confidence=conf,
                )
            )
        out.append(OcrObservation(time_ms=time_ms, boxes=tuple(kept)))
    return out
