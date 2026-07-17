"""Single-pass FFmpeg renderer: mask + Vietnamese burn-in + anti-detection."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from src.media_pipeline.video_renderer.errors import VideoRendererError, VideoRendererErrorCode
from src.media_pipeline.video_renderer.filter_graph import (
    build_single_render_filter,
    wrap_filter_complex,
)
from src.media_pipeline.video_renderer.fonts import resolve_drawtext_font
from src.media_pipeline.video_renderer.overlays import (
    DEFAULT_HOLD_MS,
    OverlaySegment,
    overlays_from_ocr_payload,
)

logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"time=(\d{2}):(\d{2}):(\d{2}\.\d+)")
ProgressCallback = Callable[[float | None, str], None]


def _parse_ffmpeg_time_seconds(line: str) -> float | None:
    match = _TIME_RE.search(line)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _default_progress(seconds: float | None, raw: str) -> None:
    if seconds is None:
        return
    # Simple single-line progress (no total duration required).
    msg = f"\rffmpeg render time={seconds:7.2f}s"
    print(msg, end="", file=sys.stderr, flush=True)


def render_video_single_pass(
    source_video: Path | str,
    output_video: Path | str,
    overlays: list[OverlaySegment] | None = None,
    *,
    ocr_payload: Mapping[str, Any] | list[Mapping[str, Any]] | None = None,
    vi_texts: Mapping[Any, str] | None = None,
    fontfile: Path | str | None = None,
    anti_seed: int | None = None,
    hold_ms: int = DEFAULT_HOLD_MS,
    ffmpeg_binary: str = "ffmpeg",
    progress: bool | ProgressCallback = True,
) -> Path:
    """
    Render once: Layer1 drawbox + Layer2 drawtext + Layer3 eq/noise in one FFmpeg call.

    Provide either `overlays` or (`ocr_payload` + `vi_texts`).
    """
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

    if overlays is None:
        if ocr_payload is None:
            raise VideoRendererError(
                VideoRendererErrorCode.INVALID_INPUT,
                "Provide overlays= or ocr_payload= (+ vi_texts=)",
            )
        overlays = overlays_from_ocr_payload(
            ocr_payload,
            vi_texts or {},
            hold_ms=hold_ms,
        )
    if not overlays:
        raise VideoRendererError(
            VideoRendererErrorCode.EMPTY_OVERLAYS,
            "overlays is empty",
        )

    font = resolve_drawtext_font(fontfile)
    # hold already baked into overlay end_ms from Phase 2 mapping; avoid double-extend.
    chain = build_single_render_filter(
        overlays,
        fontfile=font,
        anti_seed=anti_seed,
        hold_ms=0,
    )
    filter_complex = wrap_filter_complex(chain)

    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-i",
        str(source),
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(output),
    ]

    on_progress: ProgressCallback | None
    if progress is True:
        on_progress = _default_progress
    elif progress is False:
        on_progress = None
    else:
        on_progress = progress

    logger.info(
        "video_renderer_single_pass_start",
        extra={
            "source": source.name,
            "output": str(output),
            "overlays": len(overlays),
            "anti_seed": anti_seed,
        },
    )

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"Failed to start ffmpeg: {exc}",
        ) from exc

    stderr_lines: list[str] = []
    assert proc.stderr is not None
    try:
        while True:
            line = proc.stderr.readline()
            if not line:
                break
            stderr_lines.append(line)
            if on_progress is not None:
                on_progress(_parse_ffmpeg_time_seconds(line), line.rstrip())
        returncode = proc.wait()
    except Exception as exc:  # noqa: BLE001
        proc.kill()
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"ffmpeg render interrupted: {exc}",
        ) from exc
    finally:
        if on_progress is _default_progress:
            print(file=sys.stderr)

    if returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        detail = "".join(stderr_lines[-40:]).strip() or "ffmpeg failed"
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"ffmpeg single-pass render failed: {detail[:600]}",
        )

    logger.info(
        "video_renderer_single_pass_done",
        extra={"output": str(output), "bytes": output.stat().st_size},
    )
    return output
