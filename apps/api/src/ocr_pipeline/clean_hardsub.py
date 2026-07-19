"""Timed hard-sub region blur → cleaned video (Pilot A).

Sampled OCR events (≈1–2 fps) drive delogo masks with enable=between(t,…),
using each event's bbox — not one static full-width bar for the whole clip.
Scene/title text outside the hard-sub band remains out of scope.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from src.media_pipeline.video_renderer.overlays import (
    DEFAULT_PAD_X,
    DEFAULT_PAD_Y,
    expand_cover_rect,
)
from src.ocr_pipeline.errors import OcrPipelineError, OcrPipelineErrorCode
from src.ocr_pipeline.types import DEFAULT_HARD_SUB_BAND_RATIO, HardSubEvent

logger = logging.getLogger(__name__)

# Extend cover past last sample so glyphs stay hidden until the next absent sample.
DEFAULT_HOLD_MS = 500


def build_timed_cover_vf(
    events: list[HardSubEvent],
    *,
    frame_width: int,
    frame_height: int,
    hold_ms: int = DEFAULT_HOLD_MS,
    pad_x: float = DEFAULT_PAD_X,
    pad_y: float = DEFAULT_PAD_Y,
) -> str:
    """Build ffmpeg -vf chain: one delogo blur per hard-sub event, timed + geometric."""
    from src.media_pipeline.video_renderer.filter_graph import normalized_rect_to_delogo_pixels

    if not events:
        raise OcrPipelineError(
            OcrPipelineErrorCode.CLEAN_HARD_SUB_FAILED,
            "No hard-sub events to cover",
        )
    if int(frame_width) < 2 or int(frame_height) < 2:
        raise OcrPipelineError(
            OcrPipelineErrorCode.CLEAN_HARD_SUB_FAILED,
            f"frame size required for delogo pixels (got {frame_width}x{frame_height})",
        )
    hold = max(0, int(hold_ms))
    filters: list[str] = []
    for event in events:
        x0, y0, w, h = expand_cover_rect(
            float(event.x),
            float(event.y),
            float(event.width),
            float(event.height),
            pad_x=pad_x,
            pad_y=pad_y,
        )
        px, py, pw, ph = normalized_rect_to_delogo_pixels(
            x0,
            y0,
            w,
            h,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        start_s = max(0.0, float(event.start_ms) / 1000.0)
        end_s = max(start_s + 0.05, (float(event.end_ms) + hold) / 1000.0)
        # Commas inside enable= must be escaped for filtergraph parsing.
        enable = f"between(t\\,{start_s:.3f}\\,{end_s:.3f})"
        filters.append(f"delogo=x={px}:y={py}:w={pw}:h={ph}:show=0:enable={enable}")
    return ",".join(filters)


def blur_hard_sub_band(
    source_video: Path,
    output_video: Path,
    events: list[HardSubEvent],
    *,
    band_ratio: float = DEFAULT_HARD_SUB_BAND_RATIO,
    hold_ms: int = DEFAULT_HOLD_MS,
    ffmpeg_binary: str = "ffmpeg",
) -> Path:
    """Cover hard-sub regions per timed OCR event so source glyphs cannot bleed through."""
    del band_ratio  # retained for call-site compatibility; geometry comes from events.
    if shutil.which(ffmpeg_binary) is None:
        raise OcrPipelineError(
            OcrPipelineErrorCode.CLEAN_HARD_SUB_FAILED,
            f"ffmpeg binary not found on PATH ({ffmpeg_binary})",
        )
    if not source_video.is_file():
        raise OcrPipelineError(
            OcrPipelineErrorCode.CLEAN_HARD_SUB_FAILED,
            f"Source video missing: {source_video}",
        )

    from src.media_pipeline.video_renderer.renderer import probe_video_frame_size

    try:
        frame_width, frame_height = probe_video_frame_size(
            source_video, ffmpeg_binary=ffmpeg_binary
        )
    except Exception as exc:  # noqa: BLE001
        raise OcrPipelineError(
            OcrPipelineErrorCode.CLEAN_HARD_SUB_FAILED,
            f"Could not probe video size for delogo: {exc}",
        ) from exc

    vf = build_timed_cover_vf(
        events,
        hold_ms=hold_ms,
        frame_width=frame_width,
        frame_height=frame_height,
    )
    output_video.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            ffmpeg_binary,
            "-y",
            "-i",
            str(source_video),
            "-vf",
            vf,
            "-map",
            "0:v:0",
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
            str(output_video),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not output_video.is_file() or output_video.stat().st_size <= 0:
        detail = (completed.stderr or completed.stdout or "ffmpeg clean failed").strip()
        raise OcrPipelineError(
            OcrPipelineErrorCode.CLEAN_HARD_SUB_FAILED,
            f"ffmpeg hard-sub cover failed: {detail[:400]}",
        )
    logger.info(
        "ocr_hardsub_cleaned",
        extra={
            "output": str(output_video),
            "events": len(events),
            "hold_ms": hold_ms,
            "clean_method": "ffmpeg_delogo_timed_boxes",
        },
    )
    return output_video
