"""FFmpeg core engine: extract still frames at STRICT 1|2 fps."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from src.media_pipeline.frame_sampling.errors import FrameSamplingError, FrameSamplingErrorCode
from src.media_pipeline.frame_sampling.resolve_source import resolve_video_source
from src.media_pipeline.frame_sampling.types import (
    ALLOWED_SAMPLE_FPS,
    DEFAULT_SAMPLE_FPS,
    ExtractedFrame,
    SampleFps,
)

logger = logging.getLogger(__name__)


def normalize_sample_fps(sample_fps: float | int) -> SampleFps:
    """STRICT: only exactly 1 or 2 fps are allowed."""
    value = float(sample_fps)
    if value in (1.0, 1):
        return 1
    if value in (2.0, 2):
        return 2
    raise FrameSamplingError(
        FrameSamplingErrorCode.INVALID_SAMPLE_FPS,
        f"sample_fps must be exactly 1 or 2 (got {sample_fps!r}). Full-video extraction is forbidden.",
    )


def extract_thumbnail_frame(
    video_source: str | Path,
    output_path: str | Path,
    *,
    ffmpeg_binary: str = "ffmpeg",
) -> Path:
    """Force-extract the cover frame at t=00:00:00.000 as ``thumbnail.jpg`` (or given path)."""
    if shutil.which(ffmpeg_binary) is None:
        raise FrameSamplingError(
            FrameSamplingErrorCode.FFMPEG_MISSING,
            f"ffmpeg binary not found on PATH ({ffmpeg_binary})",
        )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with resolve_video_source(video_source) as video_path:
        completed = subprocess.run(
            [
                ffmpeg_binary,
                "-y",
                "-ss",
                "00:00:00.000",
                "-i",
                str(video_path),
                "-an",
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(destination),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    if completed.returncode != 0 or not destination.is_file() or destination.stat().st_size <= 0:
        detail = (completed.stderr or completed.stdout or "ffmpeg thumbnail failed").strip()
        raise FrameSamplingError(
            FrameSamplingErrorCode.FFMPEG_FAILED,
            f"ffmpeg thumbnail extract failed: {detail[:400]}",
        )
    logger.info("frame_thumbnail_extracted path=%s", destination)
    return destination


def extract_video_frames(
    video_source: str | Path,
    output_dir: str | Path,
    *,
    sample_fps: float | int | SampleFps = DEFAULT_SAMPLE_FPS,
    ffmpeg_binary: str = "ffmpeg",
) -> list[Path]:
    """Extract JPEG stills from a video path/URL at 1 or 2 fps.

    Returns the list of successfully written frame image paths (sorted).
    Never extracts every frame of the source video — FFmpeg `fps=` filter only.
    """
    detailed = extract_video_frames_detailed(
        video_source,
        output_dir,
        sample_fps=sample_fps,
        ffmpeg_binary=ffmpeg_binary,
    )
    return [frame.path for frame in detailed]


def extract_video_frames_detailed(
    video_source: str | Path,
    output_dir: str | Path,
    *,
    sample_fps: float | int | SampleFps = DEFAULT_SAMPLE_FPS,
    ffmpeg_binary: str = "ffmpeg",
) -> list[ExtractedFrame]:
    """Same as extract_video_frames but includes frame_index and approximate time_ms."""
    fps = normalize_sample_fps(sample_fps)
    if fps not in ALLOWED_SAMPLE_FPS:
        raise FrameSamplingError(
            FrameSamplingErrorCode.INVALID_SAMPLE_FPS,
            f"sample_fps must be 1 or 2 (got {fps})",
        )

    if shutil.which(ffmpeg_binary) is None:
        raise FrameSamplingError(
            FrameSamplingErrorCode.FFMPEG_MISSING,
            f"ffmpeg binary not found on PATH ({ffmpeg_binary})",
        )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "frame_%06d.jpg"

    with resolve_video_source(video_source) as video_path:
        completed = subprocess.run(
            [
                ffmpeg_binary,
                "-y",
                "-i",
                str(video_path),
                # Frame sampling does not need audio — keeps minimal FFmpeg builds small.
                "-an",
                "-vf",
                f"fps={fps}",
                "-q:v",
                "3",
                str(pattern),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "ffmpeg sample failed").strip()
            raise FrameSamplingError(
                FrameSamplingErrorCode.FFMPEG_FAILED,
                f"ffmpeg frame sample failed: {detail[:400]}",
            )

        thumb_path = out_dir / "thumbnail.jpg"
        thumb_done = subprocess.run(
            [
                ffmpeg_binary,
                "-y",
                "-ss",
                "00:00:00.000",
                "-i",
                str(video_path),
                "-an",
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(thumb_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if (
            thumb_done.returncode != 0
            or not thumb_path.is_file()
            or thumb_path.stat().st_size <= 0
        ):
            detail = (thumb_done.stderr or thumb_done.stdout or "ffmpeg thumbnail failed").strip()
            raise FrameSamplingError(
                FrameSamplingErrorCode.FFMPEG_FAILED,
                f"ffmpeg thumbnail extract failed: {detail[:400]}",
            )

    paths = sorted(out_dir.glob("frame_*.jpg"))
    if not paths:
        raise FrameSamplingError(
            FrameSamplingErrorCode.NO_FRAMES,
            "ffmpeg produced no sample frames",
        )

    interval_ms = int(round(1000.0 / float(fps)))
    frames: list[ExtractedFrame] = [
        ExtractedFrame(path=thumb_path, frame_index=0, time_ms=0),
    ]
    for index, path in enumerate(paths):
        frames.append(
            ExtractedFrame(path=path, frame_index=index + 1, time_ms=index * interval_ms)
        )

    logger.info(
        "frame_sampling_completed",
        extra={
            "count": len(frames),
            "sample_fps": fps,
            "output_dir": str(out_dir),
            "thumbnail": str(thumb_path),
        },
    )
    return frames
