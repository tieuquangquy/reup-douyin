"""Build one FFmpeg filtergraph: mask (delogo blur) + VI (drawtext) + anti-hash."""

from __future__ import annotations

import random
from pathlib import Path

from src.media_pipeline.video_renderer.errors import VideoRendererError, VideoRendererErrorCode
from src.media_pipeline.video_renderer.fonts import escape_fontfile_for_filter
from src.media_pipeline.video_renderer.overlays import (
    DEFAULT_HOLD_MS,
    DEFAULT_MIN_COVER_WIDTH,
    DEFAULT_PAD_X,
    DEFAULT_PAD_Y,
    OverlaySegment,
    expand_cover_rect,
    is_artifact_vi_text,
)


def escape_drawtext(text: str) -> str:
    """Escape characters that break drawtext=text='…'."""
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def normalized_rect_to_delogo_pixels(
    x0: float,
    y0: float,
    width: float,
    height: float,
    *,
    frame_width: int,
    frame_height: int,
) -> tuple[int, int, int, int]:
    """Convert normalized cover rect to integer delogo pixels (must not touch edges)."""
    fw = max(2, int(frame_width))
    fh = max(2, int(frame_height))
    px = max(1, min(fw - 2, int(round(float(x0) * fw))))
    py = max(1, min(fh - 2, int(round(float(y0) * fh))))
    pw = max(1, int(round(float(width) * fw)))
    ph = max(1, int(round(float(height) * fh)))
    # delogo requires the rectangle to stay inside the frame with a 1px border.
    pw = max(1, min(pw, fw - px - 1))
    ph = max(1, min(ph, fh - py - 1))
    return px, py, pw, ph


def build_anti_detection_filters(*, seed: int | None = None) -> list[str]:
    """
    Layer 3: light eq (±1–2%) + very light temporal noise.

    Intentionally subtle — must not look damaged to a human viewer.
    """
    rng = random.Random(seed)
    brightness = rng.uniform(0.01, 0.02) * rng.choice((-1.0, 1.0))
    contrast = 1.0 + rng.uniform(0.01, 0.02)
    saturation = 1.0 + rng.uniform(0.01, 0.02)
    noise_strength = rng.randint(1, 3)
    return [
        f"eq=brightness={brightness:.4f}:contrast={contrast:.4f}:saturation={saturation:.4f}",
        f"noise=alls={noise_strength}:allf=t",
    ]


def build_single_render_filter(
    overlays: list[OverlaySegment],
    *,
    fontfile: Path,
    frame_width: int,
    frame_height: int,
    anti_seed: int | None = None,
    pad_x: float = DEFAULT_PAD_X,
    pad_y: float = DEFAULT_PAD_Y,
    hold_ms: int = DEFAULT_HOLD_MS,
    box_color: str = "black@1",
    font_color: str = "white",
    font_size_expr: str | None = None,
) -> str:
    """
    Single-pass filter chain (comma-joined), ready for -filter_complex `[0:v]…[vout]`.

    Layer 1: timed delogo (region blur/inpaint) over source subtitle band.
    Layer 2: timed drawtext centered in that box (Vietnamese).
    Layer 3: global eq + noise (always on).

    ``delogo`` x/y/w/h are integer pixels — common FFmpeg builds reject ``iw*`` expressions.
    ``box_color`` is retained for call-site compatibility; opaque drawbox is no longer used.
    """
    del box_color
    if not overlays:
        raise VideoRendererError(
            VideoRendererErrorCode.EMPTY_OVERLAYS,
            "overlays is empty — nothing to render",
        )
    if int(frame_width) < 2 or int(frame_height) < 2:
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"frame size required for delogo pixels (got {frame_width}x{frame_height})",
        )

    font_esc = escape_fontfile_for_filter(Path(fontfile))
    hold = max(0, int(hold_ms))
    # Default font size ~4.5% of frame height (expression needs parentheses).
    fontsize = font_size_expr or "(h*0.045)"
    filters: list[str] = []

    for seg in overlays:
        if seg.kind == "dense_ui":
            x0, y0, w, h = (
                float(seg.x),
                float(seg.y),
                float(seg.width),
                float(seg.height),
            )
        else:
            min_width = DEFAULT_MIN_COVER_WIDTH if seg.kind == "hardsub" else 0.0
            pad_x_eff = 0.02 if seg.kind == "ui" else pad_x
            pad_y_eff = 0.015 if seg.kind == "ui" else pad_y
            x0, y0, w, h = expand_cover_rect(
                float(seg.x),
                float(seg.y),
                float(seg.width),
                float(seg.height),
                pad_x=pad_x_eff,
                pad_y=pad_y_eff,
                min_width=min_width,
            )
        px, py, pw, ph = normalized_rect_to_delogo_pixels(
            x0,
            y0,
            w,
            h,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        start_s = max(0.0, float(seg.start_ms) / 1000.0)
        end_s = max(start_s + 0.05, (float(seg.end_ms) + hold) / 1000.0)
        enable = f"between(t\\,{start_s:.3f}\\,{end_s:.3f})"

        # Layer 1 — blur/inpaint Chinese glyphs (keeps background texture vs black bar).
        filters.append(
            f"delogo=x={px}:y={py}:w={pw}:h={ph}:show=0:enable={enable}"
        )

        # Layer 2 — Vietnamese centered in the same box (skip empty / panel / artifacts).
        raw_text = (seg.text_vi or "").strip()
        if seg.kind == "dense_ui" or not raw_text or is_artifact_vi_text(raw_text):
            continue
        text = escape_drawtext(raw_text)
        text_x = f"w*{x0:.4f}+(w*{w:.4f}-text_w)/2"
        text_y = f"h*{y0:.4f}+(h*{h:.4f}-text_h)/2"
        filters.append(
            f"drawtext=fontfile='{font_esc}':text='{text}':fontsize={fontsize}"
            f":fontcolor={font_color}:x={text_x}:y={text_y}:enable={enable}"
        )

    # Layer 3 — anti MD5 / frame-hash (entire timeline).
    filters.extend(build_anti_detection_filters(seed=anti_seed))
    return ",".join(filters)


def wrap_filter_complex(vf_chain: str, *, output_label: str = "vout") -> str:
    """Wrap a linear chain as filter_complex for a single video input."""
    return f"[0:v]{vf_chain}[{output_label}]"
