"""Keyframe extraction gated by ONNX text-box appearance (IoU vs previous).

Main Phase 1 path when ``OCR_FRAME_BACKEND=text_onnx`` (default).
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.ensure_dbnet_model import ensure_dbnet_onnx
from src.media_pipeline.frame_sampling.errors import FrameSamplingError, FrameSamplingErrorCode
from src.media_pipeline.frame_sampling.ffmpeg_engine import (
    _EOF_SAMPLE_BACK_MS,
    _EOF_SAMPLE_GAP_MS,
    _extract_still_at,
    extract_thumbnail_frame,
    probe_duration_ms,
)
from src.media_pipeline.frame_sampling.local_text_detector import (
    LocalTextDetector,
    TextBox,
    has_new_text_boxes,
)
from src.media_pipeline.frame_sampling.resolve_source import resolve_video_source
from src.media_pipeline.frame_sampling.types import ExtractedFrame

logger = logging.getLogger(__name__)

DEFAULT_FRAME_STRIDE = 5
# New text if max IoU vs previous boxes is below this threshold.
DEFAULT_IOU_NEW_THRESH = 0.3
# Skip additional keyframes closer than this (ms), even if IoU says "new".
DEFAULT_MIN_KEYFRAME_GAP_MS = 1000


def _format_timestamp(time_ms: int) -> str:
    total_ms = max(0, int(time_ms))
    minutes = total_ms // 60_000
    seconds = (total_ms % 60_000) // 1000
    millis = total_ms % 1000
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def _write_jpeg(path: Path, frame_bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok or not path.is_file() or path.stat().st_size <= 0:
        raise FrameSamplingError(
            FrameSamplingErrorCode.FFMPEG_FAILED,
            f"Failed to write keyframe JPEG: {path}",
        )


def _progress_iter(total_frames: int):
    """Yield a tqdm bar when available; otherwise a no-op updater."""
    try:
        from tqdm import tqdm  # type: ignore
    except ImportError:
        class _NoBar:
            def update(self, _n: int = 1) -> None:
                return None

            def close(self) -> None:
                return None

            def __enter__(self):
                return self

            def __exit__(self, *_exc) -> None:
                return None

        return _NoBar()

    return tqdm(
        total=max(0, total_frames),
        desc="[ONNX-Extract] scanning",
        unit="frame",
        leave=True,
    )


def extract_text_change_keyframes(
    video_source: str | Path,
    output_dir: str | Path,
    *,
    frame_stride: int = DEFAULT_FRAME_STRIDE,
    iou_new_thresh: float = DEFAULT_IOU_NEW_THRESH,
    min_keyframe_gap_ms: int = DEFAULT_MIN_KEYFRAME_GAP_MS,
    ffmpeg_binary: str = "ffmpeg",
    detector: LocalTextDetector | None = None,
    model_path: Path | str | None = None,
) -> list[ExtractedFrame]:
    """
    Scan video every ``frame_stride`` frames; keep JPEG when new text boxes appear.

    Returns ``ExtractedFrame(path, frame_index, time_ms)`` for Phase 2 Cloud OCR.
    Always emits ``thumbnail.jpg`` at t=0. If the last kept keyframe is far from
    EOF, appends one near-EOF still (same invariant as FFmpeg backend).
    """
    stride = max(1, int(frame_stride))
    gap_ms = max(0, int(min_keyframe_gap_ms))
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    det = detector
    if det is None:
        # Default: apps/api/models/dbnet.onnx (auto-download if missing)
        path = ensure_dbnet_onnx(Path(model_path) if model_path else None)
        logger.info("[ONNX-Extract] LocalTextDetector model=%s", path)
        det = LocalTextDetector(path)

    frames: list[ExtractedFrame] = []
    with resolve_video_source(video_source) as video_path:
        thumb_path = out_dir / "thumbnail.jpg"
        extract_thumbnail_frame(video_path, thumb_path, ffmpeg_binary=ffmpeg_binary)
        frames.append(ExtractedFrame(path=thumb_path, frame_index=0, time_ms=0))

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise FrameSamplingError(
                FrameSamplingErrorCode.SOURCE_RESOLVE_FAILED,
                f"OpenCV cannot open video: {video_path}",
            )

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps <= 1e-3:
            fps = 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        previous_boxes: list[TextBox] = []
        kept_index = 0
        frame_count = 0
        last_kept_ms = 0
        has_text_keyframe = False

        bar = _progress_iter(total_frames)
        try:
            while True:
                ok, bgr = cap.read()
                if not ok or bgr is None:
                    break

                bar.update(1)

                # Skip frames: only evaluate every Nth frame (~6fps @ 30fps when N=5)
                if frame_count % stride != 0:
                    frame_count += 1
                    continue

                time_ms = int(round(frame_count * 1000.0 / fps))
                current_boxes = det.detect(bgr)

                if has_new_text_boxes(
                    current_boxes,
                    previous_boxes,
                    iou_new_thresh=iou_new_thresh,
                ):
                    too_soon = (
                        has_text_keyframe
                        and gap_ms > 0
                        and (time_ms - last_kept_ms) < gap_ms
                    )
                    if not too_soon:
                        kept_index += 1
                        dest = out_dir / f"frame_{kept_index:06d}.jpg"
                        _write_jpeg(dest, bgr)
                        frames.append(
                            ExtractedFrame(
                                path=dest,
                                frame_index=kept_index,
                                time_ms=time_ms,
                            )
                        )
                        last_kept_ms = time_ms
                        has_text_keyframe = True
                        ts = _format_timestamp(time_ms)
                        msg = (
                            f"[ONNX-Extract] Đã lưu keyframe tại {ts} "
                            f"(Phát hiện text mới)"
                        )
                        logger.info(msg)
                        try:
                            print(msg, flush=True)
                        except UnicodeEncodeError:
                            print(msg.encode("ascii", "replace").decode("ascii"), flush=True)

                # Always track latest detections for the next IoU comparison
                previous_boxes = list(current_boxes)

                frame_count += 1
                if total_frames > 0 and frame_count > total_frames + stride:
                    break
        finally:
            bar.close()
            cap.release()

        duration_ms = probe_duration_ms(video_path, ffmpeg_binary=ffmpeg_binary)
        if (
            duration_ms is not None
            and duration_ms - last_kept_ms > _EOF_SAMPLE_GAP_MS
        ):
            eof_ms = max(last_kept_ms + 1, duration_ms - _EOF_SAMPLE_BACK_MS)
            eof_path = out_dir / f"frame_{kept_index + 1:06d}_eof.jpg"
            eof_ok = _extract_still_at(
                video_path,
                eof_path,
                ffmpeg_binary=ffmpeg_binary,
                seek_args=["-sseof", "-0.05"],
            )
            if not eof_ok:
                seek_s = max(0.0, (duration_ms - _EOF_SAMPLE_BACK_MS) / 1000.0)
                eof_ok = _extract_still_at(
                    video_path,
                    eof_path,
                    ffmpeg_binary=ffmpeg_binary,
                    seek_args=["-ss", f"{seek_s:.3f}"],
                )
            if eof_ok:
                eof_img = cv2.imread(str(eof_path), cv2.IMREAD_COLOR)
                keep_eof = True
                if eof_img is not None and kept_index > 0:
                    eof_boxes = det.detect(eof_img)
                    keep_eof = has_new_text_boxes(
                        eof_boxes,
                        previous_boxes,
                        iou_new_thresh=iou_new_thresh,
                    ) or bool(eof_boxes and not previous_boxes)
                if keep_eof:
                    frames.append(
                        ExtractedFrame(
                            path=eof_path,
                            frame_index=kept_index + 1,
                            time_ms=eof_ms,
                        )
                    )
                    ts = _format_timestamp(eof_ms)
                    msg = (
                        f"[ONNX-Extract] Đã lưu keyframe tại {ts} "
                        f"(EOF sample)"
                    )
                    logger.info(msg)
                    try:
                        print(msg, flush=True)
                    except UnicodeEncodeError:
                        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)
                elif eof_path.is_file():
                    eof_path.unlink(missing_ok=True)

    if len(frames) <= 1:
        raise FrameSamplingError(
            FrameSamplingErrorCode.NO_FRAMES,
            "text_onnx produced no text-change keyframes (only thumbnail)",
        )

    logger.info(
        "[ONNX-Extract] done keyframes=%s stride=%s output=%s",
        len(frames),
        stride,
        out_dir,
    )
    return frames
