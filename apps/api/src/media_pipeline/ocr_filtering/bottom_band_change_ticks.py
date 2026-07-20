"""Cheap bottom-band pixel change → OCR tick times (no ONNX).

Used by the OCR-track prototype so Cloud OCR runs at caption change points
instead of a blind fixed fps grid.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_FRAME_STRIDE = 2
DEFAULT_CHANGE_MAE_THRESH = 18.0
DEFAULT_MIN_GAP_MS = 800
DEFAULT_NEIGHBOR_PAD_FRAMES = 1
# Prefer true hardsub strip (not full bottom-third) so wok motion does not spam ticks.
DEFAULT_CHANGE_BAND_TOP = 0.85


def sample_bottom_band_change_times_ms(
    video_path: str | Path,
    *,
    y0_norm: float | None = None,
    frame_stride: int = DEFAULT_FRAME_STRIDE,
    change_mae_thresh: float = DEFAULT_CHANGE_MAE_THRESH,
    min_gap_ms: int = DEFAULT_MIN_GAP_MS,
    neighbor_pad_frames: int = DEFAULT_NEIGHBOR_PAD_FRAMES,
    always_include_ends: bool = True,
) -> list[int]:
    """
    Scan the video; emit times (ms) where the bottom band grayscale MAE jumps.

    Always can include t=0 and last frame. Neighbor pad expands each change
    hit by ±N stride frames so OCR catches the stable glyph after motion.
    """
    path = Path(video_path)
    band_top = float(y0_norm) if y0_norm is not None else float(DEFAULT_CHANGE_BAND_TOP)
    band_top = max(0.0, min(0.95, band_top))
    stride = max(1, int(frame_stride))
    gap_ms = max(0, int(min_gap_ms))
    pad = max(0, int(neighbor_pad_frames))
    thresh = float(change_mae_thresh)

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        prev_band: np.ndarray | None = None
        change_indices: list[int] = []
        frame_i = 0
        while True:
            ok, bgr = cap.read()
            if not ok or bgr is None:
                break
            if frame_i % stride != 0:
                frame_i += 1
                continue
            h = int(bgr.shape[0])
            y0 = max(0, min(h - 1, int(round(h * band_top))))
            gray = cv2.cvtColor(bgr[y0:h, :], cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (160, 48), interpolation=cv2.INTER_AREA)
            if prev_band is not None:
                mae = float(np.mean(np.abs(small.astype(np.float32) - prev_band.astype(np.float32))))
                if mae >= thresh:
                    change_indices.append(frame_i)
            prev_band = small
            frame_i += 1

        if total <= 0:
            total = frame_i

        picked: set[int] = set()
        if always_include_ends:
            picked.add(0)
            if total > 0:
                picked.add(max(0, total - 1))

        for idx in change_indices:
            for d in range(-pad, pad + 1):
                j = idx + d * stride
                if 0 <= j < max(total, 1):
                    picked.add(j)

        # Enforce min gap in time
        ordered = sorted(picked)
        kept_idx: list[int] = []
        last_ms = -10**9
        for idx in ordered:
            t_ms = int(round(idx * 1000.0 / fps))
            if kept_idx and (t_ms - last_ms) < gap_ms and idx not in (0, max(0, total - 1)):
                continue
            kept_idx.append(idx)
            last_ms = t_ms

        times = sorted({int(round(i * 1000.0 / fps)) for i in kept_idx})
        logger.info(
            "bottom_band_change_ticks video=%s frames=%s changes=%s ticks=%s",
            path.name,
            total,
            len(change_indices),
            len(times),
        )
        return times
    finally:
        cap.release()
