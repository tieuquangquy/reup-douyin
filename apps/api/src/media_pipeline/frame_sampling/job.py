"""Serverless-friendly job wrapper for Phase 1 frame sampling (Cloud Run ready).

Designed to stay dependency-light for scale-to-zero:
- no DB / Redis / FastAPI required to execute
- single function entry with a plain payload dataclass
- optional HTTP/env adapter for Cloud Run in `cloud_run_entry.py`
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.media_pipeline.frame_sampling.ffmpeg_engine import extract_video_frames_detailed, normalize_sample_fps
from src.media_pipeline.frame_sampling.types import DEFAULT_SAMPLE_FPS, SampleFps

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FrameSamplingJobRequest:
    """Job input: local path or http(s) URL + output directory + STRICT fps."""

    video_source: str
    output_dir: str
    sample_fps: float | int | SampleFps = DEFAULT_SAMPLE_FPS
    ffmpeg_binary: str = "ffmpeg"


@dataclass(frozen=True)
class FrameSamplingJobResult:
    sample_fps: SampleFps
    frame_count: int
    frame_paths: list[str] = field(default_factory=list)
    frame_time_ms: list[int] = field(default_factory=list)


def run_frame_sampling_job(request: FrameSamplingJobRequest) -> FrameSamplingJobResult:
    """Execute one sampling job; safe to invoke from Cloud Run / worker / CLI."""
    fps = normalize_sample_fps(request.sample_fps)
    frames = extract_video_frames_detailed(
        request.video_source,
        Path(request.output_dir),
        sample_fps=fps,
        ffmpeg_binary=request.ffmpeg_binary,
    )
    result = FrameSamplingJobResult(
        sample_fps=fps,
        frame_count=len(frames),
        frame_paths=[str(frame.path) for frame in frames],
        frame_time_ms=[frame.time_ms for frame in frames],
    )
    logger.info(
        "frame_sampling_job_completed",
        extra={"frame_count": result.frame_count, "sample_fps": result.sample_fps},
    )
    return result
