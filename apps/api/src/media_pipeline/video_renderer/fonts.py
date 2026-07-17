"""Resolve a TTF/OTF path usable by FFmpeg drawtext (Windows-safe)."""

from __future__ import annotations

import os
from pathlib import Path

from src.media_pipeline.video_renderer.errors import VideoRendererError, VideoRendererErrorCode

_CANDIDATES = (
    # Windows
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf",
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arialuni.ttf",
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeui.ttf",
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "tahoma.ttf",
    # Linux
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    # macOS
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/Library/Fonts/Arial.ttf"),
)


def resolve_drawtext_font(explicit: Path | str | None = None) -> Path:
    """Pick a font file for drawtext; override with DRAWTEXT_FONTFILE or explicit path."""
    if explicit is not None:
        path = Path(explicit)
        if path.is_file():
            return path.resolve()
        raise VideoRendererError(
            VideoRendererErrorCode.FONT_MISSING,
            f"Font file not found: {path}",
        )
    env = os.environ.get("DRAWTEXT_FONTFILE", "").strip()
    if env:
        path = Path(env)
        if path.is_file():
            return path.resolve()
        raise VideoRendererError(
            VideoRendererErrorCode.FONT_MISSING,
            f"DRAWTEXT_FONTFILE not found: {path}",
        )
    for candidate in _CANDIDATES:
        if candidate.is_file():
            return candidate.resolve()
    raise VideoRendererError(
        VideoRendererErrorCode.FONT_MISSING,
        "No TTF font found for drawtext. Set DRAWTEXT_FONTFILE to a .ttf path.",
    )


def escape_fontfile_for_filter(path: Path) -> str:
    """Escape Windows drive colon for FFmpeg filtergraph (C\\:/Windows/...)."""
    posix = path.resolve().as_posix()
    if len(posix) >= 2 and posix[1] == ":":
        return f"{posix[0]}\\:{posix[2:]}"
    return posix
