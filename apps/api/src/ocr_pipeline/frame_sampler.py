"""OCR adapter over independent media_pipeline frame sampling (STRICT 1|2 fps)."""

from __future__ import annotations

import logging
from pathlib import Path

from src.media_pipeline.frame_sampling.backend import extract_phase1_frames
from src.media_pipeline.frame_sampling.errors import FrameSamplingError
from src.media_pipeline.frame_sampling.ffmpeg_engine import normalize_sample_fps
from src.ocr_pipeline.errors import OcrPipelineError, OcrPipelineErrorCode
from src.ocr_pipeline.types import DEFAULT_SAMPLE_FPS

logger = logging.getLogger(__name__)


def sample_video_frames(
    video_path: Path,
    output_dir: Path,
    *,
    sample_fps: float = DEFAULT_SAMPLE_FPS,
    ffmpeg_binary: str = "ffmpeg",
) -> list[tuple[int, Path]]:
    """Extract JPEG frames for OCR. Backend via ``OCR_FRAME_BACKEND`` (default text_onnx).

    Delegates to `media_pipeline.frame_sampling` so OCR does not own FFmpeg sampling.
    """
    try:
        fps = normalize_sample_fps(sample_fps)
        frames = extract_phase1_frames(
            video_path,
            output_dir,
            sample_fps=fps,
            ffmpeg_binary=ffmpeg_binary,
        )
    except FrameSamplingError as exc:
        raise OcrPipelineError(
            OcrPipelineErrorCode.FRAME_SAMPLE_FAILED,
            exc.message,
        ) from exc

    result = [(frame.time_ms, frame.path) for frame in frames]
    logger.info("ocr_frames_sampled", extra={"count": len(result), "fps": fps})
    return result
