"""Phase-4 runtime helpers: timebase, ROI merge, caches, role fonts, samples."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from src.media_pipeline.video_renderer.overlays import DENSE_UI_KIND, OverlaySegment

logger = logging.getLogger(__name__)

# Role-aware fixed fracs (never fit-to-ZH-box width/height).
_VI_FONT_FRAC_BY_KIND: dict[str, float] = {
    "hardsub": 0.040,
    "title": 0.045,
    "ui": 0.032,
    "caption_row": 0.028,
    "micro_ui": 0.019,
}
_VI_FONT_FRAC_DEFAULT = 0.040
_VI_FONT_MIN = 12
_VI_STROKE = 2
_INPAINT_MOTION_MAD_MAX = 8.0
_COLLISION_NUDGE_FRAC = 0.18
_SAMPLE_EVERY_N_FRAMES = 30


def frame_index_to_ms(frame_index: int, fps: float) -> int:
    """CFR decode clock — must match overlay ``start_ms``/``end_ms`` builders."""
    rate = float(fps) if float(fps) > 1e-6 else 30.0
    return int(round(float(frame_index) * 1000.0 / rate))


def segment_is_active(seg: OverlaySegment, time_ms: int) -> bool:
    """Half-open ``[start_ms, end_ms)`` — same contract as overlay finalize."""
    return int(seg.start_ms) <= int(time_ms) < int(seg.end_ms)


def resolve_vi_font_size_for_kind(frame_h: int, kind: str) -> int:
    frac = _VI_FONT_FRAC_BY_KIND.get(str(kind or "").strip().lower(), _VI_FONT_FRAC_DEFAULT)
    return max(_VI_FONT_MIN, int(round(float(frame_h) * frac)))


def merge_pixel_rois(
    boxes_xyxy: Sequence[tuple[int, int, int, int]],
    *,
    pad_px: int = 0,
) -> list[tuple[int, int, int, int]]:
    """
    Union-merge overlapping (or padded-touching) axis-aligned boxes.

    Returns non-overlapping groups as union AABBs (greedy).
    """
    if not boxes_xyxy:
        return []
    pad = max(0, int(pad_px))
    items: list[list[int]] = []
    for x0, y0, x1, y1 in boxes_xyxy:
        items.append([int(x0) - pad, int(y0) - pad, int(x1) + pad, int(y1) + pad])

    def overlaps(a: list[int], b: list[int]) -> bool:
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

    changed = True
    while changed and len(items) > 1:
        changed = False
        out: list[list[int]] = []
        used = [False] * len(items)
        for i, a in enumerate(items):
            if used[i]:
                continue
            cur = list(a)
            used[i] = True
            for j in range(i + 1, len(items)):
                if used[j]:
                    continue
                b = items[j]
                if overlaps(cur, b):
                    cur[0] = min(cur[0], b[0])
                    cur[1] = min(cur[1], b[1])
                    cur[2] = max(cur[2], b[2])
                    cur[3] = max(cur[3], b[3])
                    used[j] = True
                    changed = True
            out.append(cur)
        items = out
    return [(a[0], a[1], a[2], a[3]) for a in items]


class ViGlyphCache:
    """Rasterize VI once per (text, size, font) → RGBA."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int, str], np.ndarray] = {}

    def get_rgba(self, text: str, *, size: int, fontfile: Path | str) -> np.ndarray:
        from PIL import Image, ImageDraw, ImageFont

        key = (str(text), int(size), str(fontfile))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        try:
            font = ImageFont.truetype(str(fontfile), size=int(size))
        except OSError:
            font = ImageFont.load_default()
        stroke = _VI_STROKE
        probe = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        draw = ImageDraw.Draw(probe)
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
        tw = max(1, bbox[2] - bbox[0] + 4)
        th = max(1, bbox[3] - bbox[1] + 4)
        img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Draw at origin compensating bbox offset.
        draw.text(
            (-bbox[0] + 2, -bbox[1] + 2),
            text,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=stroke,
            stroke_fill=(0, 0, 0, 255),
        )
        arr = np.asarray(img, dtype=np.uint8).copy()
        self._cache[key] = arr
        return arr


class InpaintRoiCache:
    """Reuse Telea ROI when geometry stable and local motion is low."""

    def __init__(self) -> None:
        self.compute_count = 0
        self.hit_count = 0
        self._entries: dict[tuple[int, int, int, int], tuple[np.ndarray, np.ndarray]] = {}

    def get_or_compute(
        self,
        *,
        key: tuple[int, int, int, int],
        source_roi: np.ndarray,
        compute_fn,
    ) -> np.ndarray:
        prev = self._entries.get(key)
        if prev is not None:
            prev_src, prev_clean = prev
            if prev_src.shape == source_roi.shape:
                mad = float(np.mean(np.abs(source_roi.astype(np.float32) - prev_src.astype(np.float32))))
                if mad <= _INPAINT_MOTION_MAD_MAX:
                    self.hit_count += 1
                    return prev_clean
        cleaned = compute_fn()
        self.compute_count += 1
        self._entries[key] = (source_roi.copy(), cleaned.copy())
        return cleaned


@dataclass
class FrameRenderState:
    glyph_cache: ViGlyphCache = field(default_factory=ViGlyphCache)
    inpaint_cache: InpaintRoiCache = field(default_factory=InpaintRoiCache)
    samples_written: int = 0
    last_sample_frame: int = -10**9


@dataclass(frozen=True)
class ViPlacement:
    text: str
    kind: str
    rgba: np.ndarray
    x0: int
    y0: int


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def plan_vi_placements(
    segments: Sequence[OverlaySegment],
    *,
    frame_w: int,
    frame_h: int,
    fontfile: Path | str,
    glyph_cache: ViGlyphCache,
) -> list[ViPlacement]:
    """
    Build clamped, collision-nudged blit placements (center-bottom anchor).

    Priority: hardsub > title > ui (hardsub keeps bottom when colliding).
    """
    priority = {"hardsub": 0, "title": 1, "ui": 2}
    ordered = sorted(
        [s for s in segments if s.kind != DENSE_UI_KIND],
        key=lambda s: (priority.get(str(s.kind), 9), int(s.start_ms)),
    )
    placed_rects: list[tuple[int, int, int, int]] = []
    out: list[ViPlacement] = []
    for seg in ordered:
        text = str(seg.text_vi or "").strip()
        if not text:
            continue
        size = resolve_vi_font_size_for_kind(frame_h, str(seg.kind or ""))
        rgba = glyph_cache.get_rgba(text, size=size, fontfile=fontfile)
        th, tw = int(rgba.shape[0]), int(rgba.shape[1])
        anchor_x = (float(seg.x) + float(seg.width) * 0.5) * float(frame_w)
        anchor_y = (float(seg.y) + float(seg.height)) * float(frame_h)
        x0 = int(round(anchor_x - tw * 0.5))
        y0 = int(round(anchor_y - th))
        # Collision: nudge upward while overlapping a higher-priority placement.
        for _ in range(8):
            x1, y1 = x0 + tw, y0 + th
            rect = (x0, y0, x1, y1)
            hit = False
            for prev in placed_rects:
                if _rects_overlap(rect, prev):
                    y0 = int(prev[1] - th - max(2, int(th * _COLLISION_NUDGE_FRAC)))
                    hit = True
                    break
            if not hit:
                break
        # Clamp into frame.
        x0 = max(0, min(frame_w - tw, x0))
        y0 = max(0, min(frame_h - th, y0))
        x0 = max(0, x0)
        y0 = max(0, y0)
        placed_rects.append((x0, y0, x0 + tw, y0 + th))
        out.append(ViPlacement(text=text, kind=str(seg.kind or ""), rgba=rgba, x0=x0, y0=y0))
    return out


def blit_rgba_bgr(frame_bgr: np.ndarray, rgba: np.ndarray, *, x0: int, y0: int) -> None:
    """Alpha-composite RGBA glyph onto BGR frame (in-place)."""
    fh, fw = frame_bgr.shape[:2]
    th, tw = rgba.shape[:2]
    if tw < 1 or th < 1:
        return
    x1 = min(fw, x0 + tw)
    y1 = min(fh, y0 + th)
    if x1 <= x0 or y1 <= y0:
        return
    src = rgba[0 : y1 - y0, 0 : x1 - x0]
    dst = frame_bgr[y0:y1, x0:x1]
    alpha = src[:, :, 3:4].astype(np.float32) / 255.0
    rgb = src[:, :, :3][:, :, ::-1].astype(np.float32)  # RGBA→BGR
    out = rgb * alpha + dst.astype(np.float32) * (1.0 - alpha)
    dst[:] = np.clip(out, 0, 255).astype(np.uint8)


def write_render_sample_if_due(
    sample_dir: str | Path | None,
    *,
    frame_bgr: np.ndarray,
    frame_index: int,
    time_ms: int,
    active: Sequence[OverlaySegment],
    state: FrameRenderState | None = None,
    force: bool = False,
    every_n: int = _SAMPLE_EVERY_N_FRAMES,
) -> str | None:
    """Write ``qa/render_samples/t{ms}_f{idx}.jpg`` periodically for QA."""
    if sample_dir is None:
        return None
    import cv2

    root = Path(sample_dir)
    due = force or (frame_index % max(1, int(every_n)) == 0)
    if state is not None:
        if not force and frame_index - state.last_sample_frame < max(1, int(every_n)):
            due = False
    if not due:
        return None
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"t{int(time_ms):06d}_f{int(frame_index):06d}.jpg"
    ok = cv2.imwrite(str(path), frame_bgr)
    if not ok:
        return None
    meta = {
        "frame_index": int(frame_index),
        "time_ms": int(time_ms),
        "active": [
            {
                "start_ms": int(s.start_ms),
                "end_ms": int(s.end_ms),
                "kind": s.kind,
                "text_vi": s.text_vi,
                "x": s.x,
                "y": s.y,
                "w": s.width,
                "h": s.height,
            }
            for s in active
        ],
    }
    path.with_suffix(".json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if state is not None:
        state.samples_written += 1
        state.last_sample_frame = int(frame_index)
    logger.info("render_sample path=%s active=%s", path.as_posix(), len(active))
    return path.as_posix()
