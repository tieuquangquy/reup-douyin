"""Build one FFmpeg filtergraph: mask (drawbox) + VI (drawtext) + anti-hash."""

from __future__ import annotations

import random
from pathlib import Path

from src.media_pipeline.video_renderer.errors import VideoRendererError, VideoRendererErrorCode
from src.media_pipeline.video_renderer.fonts import escape_fontfile_for_filter
from src.media_pipeline.video_renderer.overlays import (
    DEFAULT_HOLD_MS,
    DEFAULT_PAD_X,
    DEFAULT_PAD_Y,
    OverlaySegment,
)


def escape_drawtext(text: str) -> str:
    """Escape characters that break drawtext=text='…'."""
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


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

    Layer 1: timed drawbox fill over source subtitle band.
    Layer 2: timed drawtext centered in that box (Vietnamese).
    Layer 3: global eq + noise (always on).
    """
    if not overlays:
        raise VideoRendererError(
            VideoRendererErrorCode.EMPTY_OVERLAYS,
            "overlays is empty — nothing to render",
        )

    font_esc = escape_fontfile_for_filter(Path(fontfile))
    hold = max(0, int(hold_ms))
    # Default font size ~4.5% of frame height (expression needs parentheses).
    fontsize = font_size_expr or "(h*0.045)"
    filters: list[str] = []

    for seg in overlays:
        x0 = max(0.0, float(seg.x) - pad_x)
        y0 = max(0.0, float(seg.y) - pad_y)
        x1 = min(1.0, float(seg.x) + float(seg.width) + pad_x)
        y1 = min(1.0, float(seg.y) + float(seg.height) + pad_y)
        w = max(0.01, x1 - x0)
        h = max(0.01, y1 - y0)
        start_s = max(0.0, float(seg.start_ms) / 1000.0)
        end_s = max(start_s + 0.05, (float(seg.end_ms) + hold) / 1000.0)
        enable = f"between(t\\,{start_s:.3f}\\,{end_s:.3f})"

        # Layer 1 — opaque cover over Chinese glyphs.
        filters.append(
            f"drawbox=x=iw*{x0:.4f}:y=ih*{y0:.4f}:w=iw*{w:.4f}:h=ih*{h:.4f}"
            f":color={box_color}:t=fill:enable={enable}"
        )

        # Layer 2 — Vietnamese centered in the same box.
        # drawtext exprs use w/h (not iw/ih) — iw is undefined in drawtext eval.
        text = escape_drawtext(seg.text_vi.strip() or " ")
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
