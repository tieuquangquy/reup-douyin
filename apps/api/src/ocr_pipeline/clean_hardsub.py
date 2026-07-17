"""Timed hard-sub box cover → cleaned video (Pilot A).

Sampled OCR events (≈1–2 fps) drive opaque drawbox masks with enable=between(t,…),
using each event's bbox — not one static full-width bar for the whole clip.
Scene/title text outside the hard-sub band remains out of scope.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from src.ocr_pipeline.errors import OcrPipelineError, OcrPipelineErrorCode
from src.ocr_pipeline.types import DEFAULT_HARD_SUB_BAND_RATIO, HardSubEvent

logger = logging.getLogger(__name__)

# Extend cover past last sample so glyphs stay hidden until the next absent sample.
DEFAULT_HOLD_MS = 500
# Slight pad so OCR box edges do not leave glyph crumbs.
DEFAULT_PAD_X = 0.015
DEFAULT_PAD_Y = 0.02


def build_timed_cover_vf(
    events: list[HardSubEvent],
    *,
    hold_ms: int = DEFAULT_HOLD_MS,
    pad_x: float = DEFAULT_PAD_X,
    pad_y: float = DEFAULT_PAD_Y,
) -> str:
    """Build ffmpeg -vf chain: one drawbox per hard-sub event, timed + geometric."""
    if not events:
        raise OcrPipelineError(
            OcrPipelineErrorCode.CLEAN_HARD_SUB_FAILED,
            "No hard-sub events to cover",
        )
    hold = max(0, int(hold_ms))
    filters: list[str] = []
    for event in events:
        x0 = max(0.0, float(event.x) - pad_x)
        y0 = max(0.0, float(event.y) - pad_y)
        x1 = min(1.0, float(event.x) + float(event.width) + pad_x)
        y1 = min(1.0, float(event.y) + float(event.height) + pad_y)
        w = max(0.01, x1 - x0)
        h = max(0.01, y1 - y0)
        start_s = max(0.0, float(event.start_ms) / 1000.0)
        end_s = max(start_s + 0.05, (float(event.end_ms) + hold) / 1000.0)
        # Commas inside enable= must be escaped for filtergraph parsing.
        enable = f"between(t\\,{start_s:.3f}\\,{end_s:.3f})"
        filters.append(
            f"drawbox=x=iw*{x0:.4f}:y=ih*{y0:.4f}:w=iw*{w:.4f}:h=ih*{h:.4f}"
            f":color=black@1:t=fill:enable={enable}"
        )
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

    vf = build_timed_cover_vf(events, hold_ms=hold_ms)
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
            "clean_method": "ffmpeg_drawbox_timed_boxes",
        },
    )
    return output_video
