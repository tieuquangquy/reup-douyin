"""Select Phase 1 frame backend: text_onnx (default), ske, or ffmpeg_fps (rollback)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from src.media_pipeline.frame_sampling.errors import FrameSamplingError, FrameSamplingErrorCode
from src.media_pipeline.frame_sampling.ffmpeg_engine import extract_video_frames_detailed
from src.media_pipeline.frame_sampling.types import DEFAULT_SAMPLE_FPS, ExtractedFrame, SampleFps

logger = logging.getLogger(__name__)

OCR_FRAME_BACKEND_ENV = "OCR_FRAME_BACKEND"
BACKEND_TEXT_ONNX = "text_onnx"
BACKEND_FFMPEG_FPS = "ffmpeg_fps"
BACKEND_SKE = "ske"
DEFAULT_FRAME_BACKEND = BACKEND_TEXT_ONNX


def resolve_frame_backend(override: str | None = None) -> str:
    """Return ``text_onnx``, ``ske``, or ``ffmpeg_fps``."""
    raw = (override if override is not None else os.environ.get(OCR_FRAME_BACKEND_ENV, "")).strip().lower()
    if not raw:
        return DEFAULT_FRAME_BACKEND
    if raw in {BACKEND_TEXT_ONNX, "onnx", "dbnet"}:
        return BACKEND_TEXT_ONNX
    if raw in {BACKEND_SKE, "smart_keyframe", "smart-keyframe"}:
        return BACKEND_SKE
    if raw in {BACKEND_FFMPEG_FPS, "ffmpeg", "fps"}:
        return BACKEND_FFMPEG_FPS
    raise FrameSamplingError(
        FrameSamplingErrorCode.INVALID_BACKEND,
        f"OCR_FRAME_BACKEND must be text_onnx, ske, or ffmpeg_fps (got {raw!r})",
    )


def _extract_text_onnx(
    video_source: str | Path,
    output_dir: str | Path,
    *,
    ffmpeg_binary: str,
) -> list[ExtractedFrame]:
    from src.media_pipeline.frame_sampling.text_change_sampler import (
        extract_text_change_keyframes,
    )

    return extract_text_change_keyframes(
        video_source,
        output_dir,
        ffmpeg_binary=ffmpeg_binary,
    )


def extract_phase1_frames(
    video_source: str | Path,
    output_dir: str | Path,
    *,
    sample_fps: float | int | SampleFps = DEFAULT_SAMPLE_FPS,
    ffmpeg_binary: str = "ffmpeg",
    backend: str | None = None,
) -> list[ExtractedFrame]:
    """
    Phase 1 entry used by hardsub E2E.

    Default ``text_onnx``: ONNX DBNet + IoU new-text gate.
    ``ske``: SmartKeyframeExtractor (writes ``summary.json`` for crop OCR); empty → text_onnx.
    Rollback ``ffmpeg_fps``: legacy strict 1|2 fps FFmpeg grid (+ EOF).
    """
    chosen = resolve_frame_backend(backend)
    logger.info("phase1_frame_backend backend=%s", chosen)
    if chosen == BACKEND_FFMPEG_FPS:
        return extract_video_frames_detailed(
            video_source,
            output_dir,
            sample_fps=sample_fps,
            ffmpeg_binary=ffmpeg_binary,
        )
    if chosen == BACKEND_SKE:
        from src.media_pipeline.frame_sampling.ske_phase1 import extract_ske_phase1_frames

        try:
            frames = extract_ske_phase1_frames(video_source, output_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ske_phase1_failed fallback=text_onnx err=%s", exc)
            frames = []
        if frames:
            return frames
        logger.info("ske_phase1_fallback backend=text_onnx")
        return _extract_text_onnx(
            video_source,
            output_dir,
            ffmpeg_binary=ffmpeg_binary,
        )
    return _extract_text_onnx(
        video_source,
        output_dir,
        ffmpeg_binary=ffmpeg_binary,
    )
