"""Phase 1 Smart Keyframe Extractor → frames + summary.json for crop OCR."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import cv2

from src.media_pipeline.frame_sampling.smart_keyframe_extractor import (
    KeyframeResult,
    SmartKeyframeExtractor,
)
from src.media_pipeline.frame_sampling.types import ExtractedFrame

logger = logging.getLogger(__name__)

SUMMARY_NAME = "summary.json"


def _video_meta(video_path: Path) -> tuple[float, int, float]:
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            return 30.0, 0, 0.0
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
        nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        dur = (nframes / fps) if fps > 0 and nframes > 0 else 0.0
        return fps, nframes, dur
    finally:
        cap.release()


def write_ske_run_dir(
    results: list[KeyframeResult],
    output_dir: str | Path,
    *,
    video_path: Path | None = None,
    fps: float = 30.0,
    frame_count: int = 0,
    duration_s: float = 0.0,
) -> list[ExtractedFrame]:
    """
    Persist SKE keyframes + ``summary.json`` (bridge contract for crop OCR).

    Returns ``ExtractedFrame`` list pointing at written JPEGs.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary: dict = {
        "video": str(video_path) if video_path is not None else "",
        "video_name": video_path.name if video_path is not None else "",
        "fps": float(fps),
        "frame_count": int(frame_count),
        "duration_s": float(duration_s),
        "keyframe_count": len(results),
        "keyframes": [],
    }
    extracted: list[ExtractedFrame] = []
    for i, kf in enumerate(results):
        frame_name = f"keyframe_{i:03d}_f{kf.frame_index:06d}.jpg"
        frame_path = out / frame_name
        cv2.imwrite(str(frame_path), kf.frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        boxes_json = [
            {"x0": box.x0, "y0": box.y0, "x1": box.x1, "y1": box.y1} for box in kf.boxes
        ]
        approx_s = round(kf.frame_index / float(fps), 3) if fps > 0 else 0.0
        time_ms = int(round(approx_s * 1000.0))
        summary["keyframes"].append(
            {
                "index": i,
                "frame_index": int(kf.frame_index),
                "approx_time_s": approx_s,
                "boxes": boxes_json,
                "n_crops": len(kf.enhanced_crops),
                "frame_file": frame_name,
                "crop_files": [],
                "boxed_file": "",
            }
        )
        extracted.append(
            ExtractedFrame(path=frame_path, frame_index=int(kf.frame_index), time_ms=time_ms)
        )
    (out / SUMMARY_NAME).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return extracted


def extract_ske_phase1_frames(
    video_source: str | Path,
    output_dir: str | Path,
    *,
    extractor: SmartKeyframeExtractor | None = None,
) -> list[ExtractedFrame]:
    """
    Run SmartKeyframeExtractor and write Phase-1 frames + summary.json.

    Returns empty list when no keyframes (caller may fall back to text_onnx).
    """
    video = Path(video_source)
    out = Path(output_dir)
    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")
    fps, nframes, dur = _video_meta(video)
    eng = extractor if extractor is not None else SmartKeyframeExtractor()
    results = eng.extract(video)
    if not results:
        logger.info("ske_phase1_empty video=%s", video.name)
        return []
    extracted = write_ske_run_dir(
        results,
        out,
        video_path=video,
        fps=fps,
        frame_count=nframes,
        duration_s=dur,
    )
    logger.info(
        "ske_phase1_done video=%s keyframes=%s out=%s",
        video.name,
        len(extracted),
        out,
    )
    return extracted
