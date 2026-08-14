"""Master Phase 1: fixed-step DBNet ROI scan → master_timeline.json (SSOT).

Geometry authority for the product hardsub path. Downstream OCR/translate/render
consume ``master_timeline.json`` only — they must not re-scan every video frame
via ``run_per_frame_position_authority``.

Coarse STEP=1 over full-frame ROI y∈[0.0,1.0] + CLAHE and stroke-aware prep → DBNet
(dual-prep union). Phase-offset probes between coarse samples when STEP≥2.
Dense re-scan every frame in [N-STEP, N+STEP] around hits. Temporal pad equals
STEP. Merge by centroid / IoU + short gap (hardsub width/edge break). Stable
median box. Confirm ≥2 hits. Final polish: split over-merge, shrink to evidence,
purge chrome, local CJK gate, overlay-vs-scene (centroid σ), hardsub ink-extend,
export crops + QA.

Also emits ``text_frame_coverage.json`` — pre-gate detection authority for every
frame that had a geometry-plausible text hit (not filtered by track gates).
Emits master_timeline.json + frames/ + crops/ + qa/.
"""

from __future__ import annotations

import json
import hashlib
import logging
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.phase1_policy import (
    FINAL_COVERAGE_FADE_TAIL_MAX_FRAMES,
    PERSPECTIVE_UI_MIN_COHORT,
    PERSPECTIVE_UI_MIN_X_SPREAD_FRAC,
    PERSPECTIVE_UI_MIN_Y_SPREAD_FRAC,
    PERSPECTIVE_UI_SCENE_MAX_GAP_FRAMES,
    PERSPECTIVE_UI_SCENE_MIN_COHORT,
    PERSPECTIVE_UI_SCENE_MIN_X_SPREAD_FRAC,
    PERSPECTIVE_UI_SCENE_MIN_Y_SPREAD_FRAC,
    PERSPECTIVE_UI_PROVENANCE_POLICY_VERSION,
    POST_REFINEMENT_SPARSE_COMPACT_MAX_HEIGHT_FRAC,
    POST_REFINEMENT_SPARSE_COMPACT_MAX_WIDTH_FRAC,
    POST_REFINEMENT_SPARSE_COMPACT_POLICY_VERSION,
    POST_REFINEMENT_TEXTURE_MAX_EDGE_DENSITY,
    POST_REFINEMENT_TEXTURE_MAX_LAPLACIAN_VARIANCE,
    POST_REFINEMENT_TEXTURE_MIN_SATURATION,
    POST_REFINEMENT_VISUAL_NORMALIZED_HEIGHT,
    RESIDUAL_HARDSUB_GENERIC_MIN_CY_FRAC,
    RESIDUAL_HARDSUB_MAX_FRAME_GAP,
    RESIDUAL_HARDSUB_MAX_HEIGHT_FRAC,
    RESIDUAL_HARDSUB_MIN_FRAMES,
    RESIDUAL_HARDSUB_MIN_WIDTH_FRAC,
    RESIDUAL_HARDSUB_RECOVERY_POLICY_VERSION,
)

from src.media_pipeline.frame_sampling.ensure_dbnet_model import ensure_dbnet_onnx
from src.media_pipeline.frame_sampling.coverage_track_closure import (
    COVERAGE_TRACK_POLICY_VERSION,
    COVERAGE_TRACK_SCHEMA_VERSION,
    CoverageTrackClosure,
    schedule_unassigned_discovery_frames,
)
from src.media_pipeline.frame_sampling.event_candidate_scheduler import (
    CANDIDATE_WINDOW_SCHEMA_VERSION,
    EVENT_SCAN_ENGINE_VERSION,
    EVENT_SCAN_POLICY_VERSION,
    CandidateWindow,
    EventFrameScheduler,
)
from src.media_pipeline.frame_sampling.local_text_detector import LocalTextDetector, TextBox

logger = logging.getLogger(__name__)

STEP = 1
# Stretch each DBNet hit across a full stride so fade-in/out between samples is covered.
# With STEP sampling, consecutive hits at N and N+STEP have overlapping pads and merge.
PADDING = STEP
TEMPORAL_PAD = PADDING
CENTROID_MERGE_PX = 20.0
MIN_MERGE_IOU = 0.12
MERGE_GAP_FRAMES = 10
# Post-gate SSOT coalesce for same-column list bands: DBNet often leaves
# multi-second holes on thin mid labels; MERGE_GAP_FRAMES is too tight here.
COALESCE_GAP_FRAMES = 150
MIN_HITS_TO_CONFIRM = 2
# 1080p ROI: 960 still drops thin mid labels / hardsubs; 1280 + softer bin helps FN.
PHASE1_DET_LONG_EDGE = 1280
PHASE1_DET_BIN_THRESH = 0.17
# A coarser raw-frame profile reconnects stylized title/endcard glyphs that the
# sensitive dual-prep profile can fragment into low-hit micro boxes. It runs
# only in bounded intro/outro risk windows, never as a video-specific patch.
PHASE1_RESIDUAL_DET_LONG_EDGE = 960
PHASE1_RESIDUAL_DET_BIN_THRESH = 0.25
PHASE1_RESIDUAL_RISK_SECONDS = 2.0
# STEP remains the timing/authority contract. This bounded heavy-probe gap is
# an internal performance policy: any 0.1 s flash at 30 fps intersects at least
# one baseline DBNet frame, while the light all-frame probe adds transition
# frames and the dense pass fills N-1/N/N+1 around every hit.
TEMPORAL_HEAVY_PROBE_MAX_GAP_FRAMES = 3
TEMPORAL_HEAVY_PROBE_MAX_GAP_AT_HIGH_FPS = 5
TEMPORAL_HEAVY_PROBE_HIGH_FPS = 48.0
TEMPORAL_PROBE_LONG_EDGE = 192
TEMPORAL_PROBE_LUMA_DELTA = 0.115
TEMPORAL_PROBE_EDGE_DELTA = 0.105
TEMPORAL_SCAN_POLICY_VERSION = "temporal_visual_localization_v2_4"
VISUAL_TEXT_PROVENANCE_SCHEMA_VERSION = "visual_text_provenance_v2"
# A dense-rescan is a boundary verifier, not a second full-duration scan.  The
# budget is deliberately expressed as a ratio so long videos cannot silently
# fall back to DBNet on every frame when a persistent title produces a hit on
# every periodic probe.
PHASE1_DENSE_RESCAN_MAX_HEAVY_RATIO = 0.48
PHASE1_EVENT_DENSE_RESCAN_MAX_HEAVY_RATIO = 0.12
PHASE1_EVENT_MAX_HEAVY_FPS = 3.5
PHASE1_EVENT_ANALYSIS_LONG_EDGE = 1280
PHASE1_EVENT_PROXY_LONG_EDGE = 512
PHASE1_COVERAGE_PROXY_LONG_EDGE = 384
# Small UI copy on a 2160x3840 phone/app surface becomes only a few pixels tall
# at the normal 1280 long edge.  A bounded high-resolution recovery pass runs
# only on dense-UI anchors, never across the whole timeline.
PHASE1_SMALL_TEXT_DET_LONG_EDGE = 1920
PHASE1_SMALL_TEXT_DET_BIN_THRESH = 0.14
PHASE1_SMALL_TEXT_MIN_FRAME_HITS = 7
PHASE1_SMALL_TEXT_MAX_ANCHORS_PER_MINUTE = 18
# Tighter than LocalTextDetector defaults so SSOT hugs glyphs (ink-trim finishes).
PHASE1_EXPAND_PAD_W_FRAC = 0.05
PHASE1_EXPAND_PAD_H_TOP_FRAC = 0.22
PHASE1_EXPAND_PAD_H_BOTTOM_FRAC = 0.15


def phase1_event_proxy_size(
    source_width: int,
    source_height: int,
) -> tuple[int, int] | None:
    """Return the all-frame event raster, or None for already-small sources."""

    width = max(0, int(source_width))
    height = max(0, int(source_height))
    long_edge = max(width, height)
    if long_edge <= PHASE1_EVENT_PROXY_LONG_EDGE:
        return None
    scale = PHASE1_EVENT_PROXY_LONG_EDGE / float(long_edge)
    return (
        max(2, int(round(width * scale))),
        max(2, int(round(height * scale))),
    )
# Full-frame scan: editor titles/UI can sit near y=0. Douyin chrome is filtered by
# ``is_chrome_noise_box`` / purge — not by cropping the top away.
# Bottom must be full-frame: burn-ins often sit at y≈0.93–0.97H; ROI_Y1=0.95
# clipped low lines (~half glyph) and dropped whole hardsub spans.
ROI_Y0 = 0.0
ROI_Y1 = 1.0
CLAHE_CLIP = 3.0
CLAHE_TILE = (8, 8)
MIN_BOX_WIDTH_PX = 24.0
MIN_BOX_HEIGHT_PX = 12.0
MAX_BOX_ASPECT = 40.0  # w/h
MAX_BOX_AREA_FRAC = 0.20
MAX_BOX_HEIGHT_FRAC = 0.28
# Soft cap: thin bottom hardsubs may exceed this after DBNet expand.
STRICT_BOX_WIDTH_FRAC = 0.92
# Absolute max width (near-full hardsub after expand).
MAX_BOX_WIDTH_FRAC = 0.98
THIN_HARDSUB_HEIGHT_FRAC = 0.10
HARDSUB_BAND_CY = 0.78
# Burn-in *role* is only the true bottom strip. Endcard list rows often sit in
# cy 0.78–0.87 and must stay ui_chip/generic (not hardsub recover/drop).
HARDSUB_ROLE_CY = 0.88
# Many creator templates place dialogue captions above the legacy bottom strip
# (roughly 0.74-0.87H) so they do not collide with platform controls.  A global
# Y-threshold cannot distinguish those captions from endcard/table rows.  Lane
# inference below therefore needs repeated, sequential, screen-locked line
# tracks before this upper band is promoted to caption authority.
CAPTION_LANE_MIN_CY = 0.72
CAPTION_LANE_MAX_CY = HARDSUB_ROLE_CY
CAPTION_LANE_MIN_WIDTH_FRAC = 0.18
CAPTION_LANE_MAX_HEIGHT_FRAC = 0.075
CAPTION_LANE_MAX_CY_DELTA_FRAC = 0.025
CAPTION_LANE_MAX_OVERLAP_RATIO = 0.35
CAPTION_LANE_MIN_MEMBERS = 3
# Burn-in lines are wide; square food/texture in the band is not hardsub.
HARDSUB_MIN_ASPECT = 2.5
HARDSUB_MIN_W_FRAC = 0.22
# Final pre-OCR polish.
POST_EVIDENCE_PAD = 2
SPLIT_GAP_FRAMES = 8
SPLIT_MIN_IOU = 0.08
SPLIT_CENTROID_PX = 48.0
# Consecutive bottom burn-ins share cy / IoU but change length per line —
# refuse merge / coalesce / split-undo when width + x-span diverge past these.
# Tight enough to break gradual same-center length changes between lines.
HARDSUB_MERGE_WIDTH_RATIO = 0.70
HARDSUB_MERGE_X_IOU = 0.40
# (|Δx0|+|Δx1|)/max(w) — catches similar-width lines that reflow left/right.
HARDSUB_MERGE_EDGE_DELTA = 0.14
CHROME_MIN_W_PX = 40.0
CHROME_MIN_H_PX = 18.0
CHROME_EDGE_FRAC = 0.06
CHROME_EDGE_MAX_W_PX = 90.0


class _DiskBackedFrameCache(Mapping[int, np.ndarray]):
    """Lossless decoded-frame store with a byte-bounded in-memory LRU.

    ``STEP=1`` scans every frame. Keeping each decoded BGR array in a normal
    dict makes RAM grow linearly with video duration (roughly 18 GiB for a
    3.5-minute 1280x736 clip). The raw backing file preserves the exact decoder
    output used by detection, while the hot cache keeps repeated downstream
    reads fast without making memory usage duration-dependent.

    ``TemporaryFile`` uses delete-on-close semantics on Windows, so the raw
    cache is not a product artifact and is removed on normal close or process
    teardown.
    """

    def __init__(self, *, max_hot_bytes: int = 256 * 1024 * 1024) -> None:
        self._file = tempfile.TemporaryFile(prefix="phase1_frames_", suffix=".raw")
        self._entries: dict[int, tuple[int, int, tuple[int, ...], str]] = {}
        self._hot: OrderedDict[int, np.ndarray] = OrderedDict()
        self._max_hot_bytes = max(0, int(max_hot_bytes))
        self._hot_bytes = 0
        self._backing_bytes = 0

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    def __getitem__(self, frame_index: int) -> np.ndarray:
        key = int(frame_index)
        cached = self._hot.pop(key, None)
        if cached is not None:
            self._hot[key] = cached
            return cached

        try:
            offset, nbytes, shape, dtype_str = self._entries[key]
        except KeyError:
            raise KeyError(key) from None
        if self._file.closed:
            raise RuntimeError("Phase 1 frame cache is closed")

        self._file.flush()
        self._file.seek(offset)
        payload = self._file.read(nbytes)
        if len(payload) != nbytes:
            raise RuntimeError(
                f"Short read from Phase 1 frame cache for frame {key}: "
                f"expected={nbytes} actual={len(payload)}"
            )
        frame = np.frombuffer(payload, dtype=np.dtype(dtype_str)).reshape(shape).copy()
        self._remember_hot(key, frame)
        return frame

    def __setitem__(self, frame_index: int, frame: np.ndarray) -> None:
        if self._file.closed:
            raise RuntimeError("Phase 1 frame cache is closed")
        arr = np.ascontiguousarray(frame)
        key = int(frame_index)
        self._file.seek(0, 2)
        offset = int(self._file.tell())
        payload = memoryview(arr).cast("B")
        written = int(self._file.write(payload))
        if written != int(arr.nbytes):
            raise RuntimeError(
                f"Short write to Phase 1 frame cache for frame {key}: "
                f"expected={arr.nbytes} actual={written}"
            )
        previous = self._entries.get(key)
        if previous is not None:
            self._backing_bytes -= int(previous[1])
        self._entries[key] = (
            offset,
            int(arr.nbytes),
            tuple(int(v) for v in arr.shape),
            arr.dtype.str,
        )
        self._backing_bytes += int(arr.nbytes)
        old_hot = self._hot.pop(key, None)
        if old_hot is not None:
            self._hot_bytes -= int(old_hot.nbytes)

    def _remember_hot(self, key: int, frame: np.ndarray) -> None:
        if self._max_hot_bytes <= 0 or int(frame.nbytes) > self._max_hot_bytes:
            return
        self._hot[key] = frame
        self._hot_bytes += int(frame.nbytes)
        while self._hot and self._hot_bytes > self._max_hot_bytes:
            _old_key, old_frame = self._hot.popitem(last=False)
            self._hot_bytes -= int(old_frame.nbytes)

    @property
    def hot_bytes(self) -> int:
        return int(self._hot_bytes)

    @property
    def hot_frame_count(self) -> int:
        return len(self._hot)

    @property
    def backing_bytes(self) -> int:
        return int(self._backing_bytes)

    def close(self) -> None:
        self._hot.clear()
        self._hot_bytes = 0
        if not self._file.closed:
            self._file.close()

    def __del__(self) -> None:  # pragma: no cover - defensive file cleanup
        try:
            self.close()
        except Exception:
            pass


def _ffmpeg_proxy_decode_command(
    ffmpeg_binary: str,
    source: Path,
    *,
    width: int,
    height: int,
    selected_frame_indices: Sequence[int] = (),
) -> list[str]:
    """Build a frame-preserving, scaled BGR decode stream for event analysis."""

    filters: list[str] = []
    selected = sorted({max(0, int(value)) for value in selected_frame_indices})
    if selected:
        expression = "+".join(f"eq(n\\,{value})" for value in selected)
        filters.append(f"select={expression}")
    filters.append(f"scale={int(width)}:{int(height)}:flags=fast_bilinear")
    return [
        ffmpeg_binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-vf",
        ",".join(filters),
        "-pix_fmt",
        "bgr24",
        "-fps_mode",
        "passthrough",
        "-f",
        "rawvideo",
        "pipe:1",
    ]


class _FfmpegProxyFrameReader:
    """Sequential OpenCV-compatible reader that never materializes 4K frames.

    FFmpeg performs decode and downscale in its optimized native pipeline.  The
    Python process receives only the event-analysis raster, avoiding a full 4K
    BGR allocation and ``cv2.resize`` for every source frame.
    """

    def __init__(
        self,
        source: Path,
        *,
        width: int,
        height: int,
        selected_frame_indices: Sequence[int] = (),
    ) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg was not found on PATH")
        self._width = max(2, int(width))
        self._height = max(2, int(height))
        self._frame_bytes = self._width * self._height * 3
        self._stderr = tempfile.TemporaryFile(
            prefix="phase1_ffmpeg_", suffix=".stderr"
        )
        try:
            self._process = subprocess.Popen(
                _ffmpeg_proxy_decode_command(
                    ffmpeg,
                    source,
                    width=self._width,
                    height=self._height,
                    selected_frame_indices=selected_frame_indices,
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
                shell=False,
            )
        except OSError:
            self._stderr.close()
            raise
        if self._process.stdout is None:
            self.release()
            raise RuntimeError("FFmpeg proxy decoder did not expose stdout")
        self._closed = False

    def _error_detail(self) -> str:
        try:
            self._stderr.flush()
            self._stderr.seek(0)
            return self._stderr.read().decode("utf-8", errors="replace")[-800:].strip()
        except (OSError, ValueError):
            return ""

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._closed or self._process.stdout is None:
            return False, None
        chunks: list[bytes] = []
        remaining = self._frame_bytes
        while remaining > 0:
            chunk = self._process.stdout.read(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if remaining == self._frame_bytes:
            return_code = self._process.wait()
            if return_code != 0:
                detail = self._error_detail() or f"exit={return_code}"
                raise RuntimeError(f"FFmpeg proxy decode failed: {detail}")
            return False, None
        if remaining:
            detail = self._error_detail() or f"missing_bytes={remaining}"
            raise RuntimeError(f"FFmpeg proxy decode returned a partial frame: {detail}")
        frame = np.frombuffer(b"".join(chunks), dtype=np.uint8).reshape(
            (self._height, self._width, 3)
        )
        return True, frame

    def release(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        process = getattr(self, "_process", None)
        stdout = getattr(process, "stdout", None)
        if stdout is not None:
            try:
                stdout.close()
            except OSError:
                pass
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        try:
            self._stderr.close()
        except (OSError, ValueError):
            pass

    def __del__(self) -> None:  # pragma: no cover - defensive process cleanup
        try:
            self.release()
        except Exception:
            pass


@dataclass(frozen=True)
class DetectionHit:
    """Raw DBNet hit on a sampled frame (full-frame pixel xyxy)."""

    frame_index: int
    box_xyxy: tuple[float, float, float, float]
    sharpness: float


class TemporalVisualProbe:
    """Cheap all-frame gate for the expensive dual-prep DBNet detector.

    The baseline gap is deliberately frame-count based rather than wall-clock
    based so a three-frame CJK flash cannot fall entirely between heavy probes.
    Large luminance/edge changes trigger an extra probe between baselines.
    """

    def __init__(self, *, max_gap_frames: int = TEMPORAL_HEAVY_PROBE_MAX_GAP_FRAMES) -> None:
        self.max_gap_frames = max(1, int(max_gap_frames))
        self._previous_gray: np.ndarray | None = None
        self._previous_edges: np.ndarray | None = None

    @staticmethod
    def _signature(frame_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        height, width = frame_bgr.shape[:2]
        scale = min(1.0, float(TEMPORAL_PROBE_LONG_EDGE) / max(1.0, float(max(width, height))))
        if scale < 1.0:
            small = cv2.resize(
                frame_bgr,
                (max(2, int(round(width * scale))), max(2, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            small = frame_bgr
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 56, 144)
        return gray, edges

    def inspect(self, frame_bgr: np.ndarray, *, frame_index: int) -> tuple[bool, str]:
        gray, edges = self._signature(frame_bgr)
        baseline = int(frame_index) % self.max_gap_frames == 0
        reason = "baseline" if baseline else "skip"
        changed = False
        if self._previous_gray is not None and self._previous_gray.shape == gray.shape:
            luma_delta = float(
                np.mean(cv2.absdiff(gray, self._previous_gray), dtype=np.float64)
            ) / 255.0
            edge_delta = float(
                np.count_nonzero(cv2.bitwise_xor(edges, self._previous_edges))
            ) / float(max(1, edges.size))
            if luma_delta >= TEMPORAL_PROBE_LUMA_DELTA:
                changed = True
                reason = "luma_transition"
            elif edge_delta >= TEMPORAL_PROBE_EDGE_DELTA:
                changed = True
                reason = "edge_transition"
        elif self._previous_gray is None:
            changed = True
            reason = "first_frame"
        self._previous_gray = gray
        self._previous_edges = edges
        return bool(baseline or changed), reason


@dataclass
class MergedTrack:
    start_frame: int
    end_frame: int
    box_coords: list[float]  # xyxy stable (median of hits)
    best_frame_index: int
    best_sharpness: float
    centroid: tuple[float, float]
    hit_count: int = 1
    hit_boxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    hit_frames: list[int] = field(default_factory=list)
    hit_sharpness: list[float] = field(default_factory=list)


def _copy_track_with_span(
    track: MergedTrack,
    *,
    start_frame: int,
    end_frame: int,
) -> MergedTrack:
    """Copy a track while changing only its verified inclusive lifespan."""
    return MergedTrack(
        start_frame=int(start_frame),
        end_frame=int(end_frame),
        box_coords=list(track.box_coords),
        best_frame_index=int(track.best_frame_index),
        best_sharpness=float(track.best_sharpness),
        centroid=tuple(track.centroid),
        hit_count=int(track.hit_count),
        hit_boxes=list(track.hit_boxes),
        hit_frames=list(track.hit_frames),
        hit_sharpness=list(track.hit_sharpness),
    )


def _boundary_frame(
    frame_index: int,
    *,
    frame_cache: Mapping[int, np.ndarray],
    source: Path | None,
) -> np.ndarray | None:
    frame = frame_cache.get(int(frame_index))
    if frame is not None:
        return frame
    if source is None:
        return None
    return _read_frame(source, int(frame_index))


def _fixed_box_gray_crop(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
) -> np.ndarray | None:
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return None
    h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    x0 = max(0, min(w - 1, int(np.floor(float(xyxy[0])))))
    y0 = max(0, min(h - 1, int(np.floor(float(xyxy[1])))))
    x1 = max(x0 + 1, min(w, int(np.ceil(float(xyxy[2])))))
    y1 = max(y0 + 1, min(h, int(np.ceil(float(xyxy[3])))))
    crop = frame_bgr[y0:y1, x0:x1]
    if crop.size < 64:
        return None
    return cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)


def _boundary_template_mask(template_gray: np.ndarray) -> np.ndarray | None:
    """High-frequency mask used to compare a static editor glyph template."""
    if template_gray is None or template_gray.size < 64:
        return None
    enh = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(template_gray)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    top = cv2.morphologyEx(enh, cv2.MORPH_TOPHAT, kernel).astype(np.float32)
    black = cv2.morphologyEx(enh, cv2.MORPH_BLACKHAT, kernel).astype(np.float32)
    gx = cv2.Sobel(enh, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(enh, cv2.CV_32F, 0, 1, ksize=3)
    energy = top + black + 0.35 * (np.abs(gx) + np.abs(gy))
    positive = energy[energy > 1e-6]
    if positive.size < 12:
        return None
    threshold = float(np.percentile(positive, 68))
    mask = energy >= threshold
    coverage = float(mask.mean())
    if coverage < 0.01 or coverage > 0.55:
        return None
    return mask


def refine_track_boundaries_by_template(
    track: MergedTrack,
    *,
    frame_cache: Mapping[int, np.ndarray],
    frame_count: int,
    frame_w: int,
    frame_h: int,
    source: Path | None = None,
    search_radius: int = 6,
) -> tuple[MergedTrack, dict[str, Any]]:
    """
    Verify onset/offset against a temporal glyph template instead of blind pad.

    Confirmed hit frames form a robust positive template. Frames just outside
    the padded span calibrate the local background. The refinement is applied
    only when positive/negative similarity is separable; otherwise it fails
    soft and preserves the prior span.
    """
    del frame_w, frame_h  # fixed full-frame box already carries the crop locus
    hit_frames = sorted(
        {int(fi) for fi in track.hit_frames if 0 <= int(fi) < int(frame_count)}
    )
    audit: dict[str, Any] = {
        "method": "temporal_glyph_template_v1",
        "applied": False,
        "prior_span": [int(track.start_frame), int(track.end_frame)],
        "observed_hit_span": (
            [hit_frames[0], hit_frames[-1]] if hit_frames else None
        ),
        "refined_span": [int(track.start_frame), int(track.end_frame)],
    }
    if len(hit_frames) < 2:
        audit["reason"] = "insufficient_positive_frames"
        return track, audit

    # Prefer sharp frames but keep the sample temporally diverse.
    sharp_by_frame = {
        int(fi): float(track.hit_sharpness[i])
        for i, fi in enumerate(track.hit_frames)
        if i < len(track.hit_sharpness)
    }
    ranked = sorted(
        hit_frames,
        key=lambda fi: (sharp_by_frame.get(fi, 0.0), -abs(fi - track.best_frame_index)),
        reverse=True,
    )[:7]
    positives: list[np.ndarray] = []
    for fi in ranked:
        frame = _boundary_frame(fi, frame_cache=frame_cache, source=source)
        crop = _fixed_box_gray_crop(frame, track.box_coords) if frame is not None else None
        if crop is not None:
            positives.append(crop)
    if len(positives) < 2 or len({p.shape for p in positives}) != 1:
        audit["reason"] = "positive_frames_unavailable"
        return track, audit

    template = np.median(np.stack(positives, axis=0), axis=0).astype(np.uint8)
    mask = _boundary_template_mask(template)
    if mask is None:
        audit["reason"] = "glyph_mask_unstable"
        return track, audit

    score_cache: dict[int, float] = {}

    def _score(fi: int) -> float | None:
        if fi in score_cache:
            return score_cache[fi]
        frame = _boundary_frame(fi, frame_cache=frame_cache, source=source)
        crop = _fixed_box_gray_crop(frame, track.box_coords) if frame is not None else None
        if crop is None or crop.shape != template.shape:
            return None
        diff = np.abs(crop.astype(np.float32) - template.astype(np.float32))
        similarity = 1.0 - float(diff[mask].mean()) / 255.0
        score_cache[fi] = max(0.0, min(1.0, similarity))
        return score_cache[fi]

    positive_scores = [score for fi in hit_frames if (score := _score(fi)) is not None]
    if len(positive_scores) < 2:
        audit["reason"] = "positive_scores_unavailable"
        return track, audit
    positive_floor = float(np.percentile(positive_scores, 10))

    negative_indices = sorted(
        {
            int(track.start_frame) - 2,
            int(track.start_frame) - 1,
            int(track.end_frame) + 1,
            int(track.end_frame) + 2,
        }
    )
    negative_scores = [
        score
        for fi in negative_indices
        if 0 <= fi < int(frame_count) and (score := _score(fi)) is not None
    ]
    if negative_scores:
        negative_ceiling = max(negative_scores)
        separation = positive_floor - negative_ceiling
        if separation < 0.08:
            observed_span = max(1, hit_frames[-1] - hit_frames[0] + 1)
            max_missing_gap = max(
                (max(0, b - a - 1) for a, b in zip(hit_frames, hit_frames[1:])),
                default=0,
            )
            observed_density = len(hit_frames) / float(observed_span)
            if observed_density >= 0.85 and max_missing_gap <= 1:
                refined = _copy_track_with_span(
                    track,
                    start_frame=hit_frames[0],
                    end_frame=hit_frames[-1],
                )
                audit.update(
                    {
                        "applied": True,
                        "reason": "dense_detector_evidence",
                        "fallback_from": "template_not_separable",
                        "refined_span": [hit_frames[0], hit_frames[-1]],
                        "positive_floor": round(positive_floor, 4),
                        "negative_ceiling": round(negative_ceiling, 4),
                        "hit_density": round(observed_density, 4),
                        "max_missing_gap": int(max_missing_gap),
                    }
                )
                return refined, audit
            audit.update(
                {
                    "reason": "template_not_separable",
                    "positive_floor": round(positive_floor, 4),
                    "negative_ceiling": round(negative_ceiling, 4),
                }
            )
            return track, audit
        # Recall-first: admit faded glyphs closer to the negative baseline than
        # fully opaque hits, but still require clear separation from background.
        threshold = negative_ceiling + 0.25 * separation
    else:
        negative_ceiling = None
        threshold = max(0.50, positive_floor - 0.18)

    radius = max(1, int(search_radius))
    first_hit, last_hit = hit_frames[0], hit_frames[-1]
    left = first_hit
    for fi in range(first_hit - 1, max(-1, first_hit - radius - 1), -1):
        score = _score(fi)
        if score is None or score < threshold:
            break
        left = fi
    right = last_hit
    for fi in range(last_hit + 1, min(int(frame_count), last_hit + radius + 1)):
        score = _score(fi)
        if score is None or score < threshold:
            break
        right = fi

    refined = _copy_track_with_span(track, start_frame=left, end_frame=right)
    audit.update(
        {
            "applied": True,
            "reason": "verified",
            "refined_span": [left, right],
            "threshold": round(float(threshold), 4),
            "positive_floor": round(positive_floor, 4),
            "negative_ceiling": (
                round(float(negative_ceiling), 4)
                if negative_ceiling is not None
                else None
            ),
            "mask_coverage": round(float(mask.mean()), 4),
        }
    )
    return refined, audit


def track_boundary_evidence(
    track: MergedTrack,
    *,
    frame_w: int,
    frame_h: int,
) -> dict[str, Any]:
    """Observable quality signals; uncertain tracks are reviewed, never hidden."""
    hits = sorted({int(fi) for fi in track.hit_frames})
    span = max(1, int(track.end_frame) - int(track.start_frame) + 1)
    gaps = [max(0, b - a - 1) for a, b in zip(hits, hits[1:])]
    max_gap = max(gaps, default=0)
    density = min(1.0, len(hits) / float(span))
    x0, y0, x1, y1 = (float(v) for v in track.box_coords[:4])
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    width_frac = max(0.0, x1 - x0) / fw
    height_frac = max(0.0, y1 - y0) / fh
    reasons: list[str] = []
    if len(hits) <= 1:
        reasons.append("single_hit_candidate")
    if max_gap > max(2, int(round(span * 0.25))) or density < 0.20:
        reasons.append("sparse_temporal_evidence")
    dense_portrait_line = (
        frame_h > frame_w
        and height_frac <= 0.035
        and density >= 0.85
        and max_gap <= max(2, int(round(span * 0.08)))
    )
    if width_frac >= 0.65 and not dense_portrait_line:
        reasons.append("wide_box_review")
    # Treat only the detector-quantization strip at the raster boundary as a
    # clipping risk. A 1% strip (19 px at 1080p) incorrectly flags complete,
    # dense editor labels that intentionally sit near the frame edge.
    edge_margin = max(2.0, 0.0025 * fw)
    touches_raster_edge = x0 <= edge_margin or x1 >= fw - edge_margin
    source_intrinsic_clip = (
        touches_raster_edge
        and len(hits) >= 3
        and density >= 0.80
        and max_gap <= max(2, int(round(span * 0.08)))
    )
    if touches_raster_edge and not source_intrinsic_clip:
        reasons.append("frame_edge_box_review")
    if height_frac >= 0.14:
        reasons.append("tall_box_review")
    confidence = max(0.0, min(1.0, 0.45 + 0.55 * density - 0.10 * len(reasons)))
    return {
        "status": "uncertain" if reasons else "confirmed",
        "reasons": reasons,
        "observed_first_frame": hits[0] if hits else None,
        "observed_last_frame": hits[-1] if hits else None,
        "hit_count": len(hits),
        "hit_density": round(density, 4),
        "max_internal_gap": int(max_gap),
        "width_frac": round(width_frac, 4),
        "height_frac": round(height_frac, 4),
        "touches_raster_edge": bool(touches_raster_edge),
        "source_intrinsic_clip": bool(source_intrinsic_clip),
        "confidence": round(confidence, 4),
    }


@dataclass(frozen=True)
class MasterPhase1Result:
    timeline: list[dict[str, Any]]
    fps: float
    frame_count: int
    frame_width: int
    frame_height: int
    timeline_path: Path
    frames_dir: Path
    qa_dir: Path | None = None
    analysis_engine: str = "v58_candidate"
    analysis_metrics: dict[str, Any] = field(default_factory=dict)


def apply_temporal_pad(
    frame_index: int,
    *,
    frame_count: int,
    pad: int = PADDING,
) -> tuple[int, int]:
    """Inclusive lifespan ``[N - PADDING, N + PADDING]`` (default ``PADDING == STEP``)."""
    n = int(frame_index)
    p = max(0, int(pad))
    count = max(1, int(frame_count))
    start = max(0, n - p)
    end = min(count - 1, n + p)
    return start, end


def dense_rescan_frame_indices(
    coarse_hits: Sequence[DetectionHit],
    *,
    step: int,
    frame_count: int,
) -> list[int]:
    """
    Every frame in ``[N - step, N + step]`` around each coarse hit (inclusive).

    Used for a second DBNet pass so fade frames between coarse samples are scanned.
    """
    window = max(0, int(step))
    count = max(1, int(frame_count))
    wanted: set[int] = set()
    for hit in coarse_hits:
        start, end = apply_temporal_pad(
            hit.frame_index, frame_count=count, pad=window
        )
        wanted.update(range(start, end + 1))
    return sorted(wanted)


def temporal_heavy_probe_gap_frames(fps: float) -> int:
    """Production heavy-probe gap with the same sub-0.1 s flash guarantee.

    ``STEP=1`` remains the logical timing authority.  At 50/60 fps a fixed
    three-frame DBNet cadence over-samples the same visual state; five frames
    is still shorter than 0.1 seconds and materially reduces CPU work.
    """
    if float(fps) >= TEMPORAL_HEAVY_PROBE_HIGH_FPS:
        return TEMPORAL_HEAVY_PROBE_MAX_GAP_AT_HIGH_FPS
    return TEMPORAL_HEAVY_PROBE_MAX_GAP_FRAMES


def interval_dense_rescan_frame_indices(
    seed_hits: Sequence[DetectionHit],
    *,
    step: int,
    frame_count: int,
    frame_w: int,
    frame_h: int,
    max_centroid_px: float,
    max_probe_gap_frames: int,
    transition_frames: Sequence[int] = (),
) -> list[int]:
    """Verify candidate interval boundaries instead of expanding every seed.

    Persistent editor copy can yield a hit on every periodic heavy probe.  The
    old ``N +/- STEP`` expansion around every hit therefore covered the entire
    video.  Provisional spatial tracks first collapse those seeds into visual
    intervals; only interval onsets, offsets, detector gaps, geometry jumps and
    lightweight transition neighbours are returned for the dense pass.

    Callers with ``STEP > 1`` retain the closed legacy behaviour.
    """
    if int(step) > 1:
        return dense_rescan_frame_indices(
            seed_hits, step=step, frame_count=frame_count
        )
    if not seed_hits:
        return []

    provisional = merge_tracks_by_centroid(
        seed_hits,
        frame_count=frame_count,
        pad=0,
        max_centroid_px=max_centroid_px,
        frame_w=frame_w,
        frame_h=frame_h,
    )
    wanted: set[int] = set()
    gap_limit = max(1, int(max_probe_gap_frames))

    def _add_window(frame_index: int) -> None:
        start, end = apply_temporal_pad(
            int(frame_index), frame_count=frame_count, pad=max(1, int(step))
        )
        wanted.update(range(start, end + 1))

    for track in provisional:
        observations = sorted(
            {
                int(frame_index): tuple(float(value) for value in box[:4])
                for frame_index, box in zip(track.hit_frames, track.hit_boxes)
                if 0 <= int(frame_index) < int(frame_count)
            }.items()
        )
        if not observations:
            continue
        _add_window(observations[0][0])
        _add_window(observations[-1][0])
        if len(observations) <= 2:
            for frame_index, _box in observations:
                _add_window(frame_index)
            continue
        for (left_frame, left_box), (right_frame, right_box) in zip(
            observations, observations[1:]
        ):
            if right_frame - left_frame > gap_limit:
                _add_window(left_frame)
                _add_window(right_frame)
                continue
            if box_iou(left_box, right_box) < 0.20:
                _add_window(left_frame)
                _add_window(right_frame)

    for frame_index in transition_frames:
        _add_window(int(frame_index))
    return sorted(wanted)


def bound_dense_rescan_frame_indices(
    candidates: Sequence[int],
    *,
    already_scanned: Sequence[int],
    frame_count: int,
    max_heavy_ratio: float = PHASE1_DENSE_RESCAN_MAX_HEAVY_RATIO,
) -> tuple[list[int], dict[str, Any]]:
    """Cap the boundary pass so it cannot recreate a full-duration scan."""
    count = max(1, int(frame_count))
    already = {int(value) for value in already_scanned}
    needed = sorted(
        {
            int(value)
            for value in candidates
            if 0 <= int(value) < count and int(value) not in already
        }
    )
    max_total = max(len(already), int(np.floor(float(max_heavy_ratio) * count)))
    budget = max(0, max_total - len(already))
    guard_triggered = len(needed) > budget
    if budget <= 0:
        selected: list[int] = []
    elif len(needed) <= budget:
        selected = needed
    else:
        # Evenly retain boundary evidence across the whole timeline; taking the
        # first N would silently starve the outro of verification.
        positions = np.linspace(0, len(needed) - 1, num=budget, dtype=np.int64)
        selected = sorted({needed[int(position)] for position in positions})
    return selected, {
        "candidate_frames": len(needed),
        "selected_frames": len(selected),
        "budget_frames": int(budget),
        "max_heavy_ratio": float(max_heavy_ratio),
        "guard_triggered": bool(guard_triggered),
    }


def event_dense_rescan_max_ratio(fps: float) -> float:
    """Cap expensive event evidence by wall-clock time, not source FPS."""

    return min(
        PHASE1_EVENT_DENSE_RESCAN_MAX_HEAVY_RATIO,
        PHASE1_EVENT_MAX_HEAVY_FPS / max(1.0, float(fps)),
    )


def event_track_merge_gap_frames(fps: float) -> int:
    """Bridge the expected gap between 3 FPS event-detector observations."""

    return max(MERGE_GAP_FRAMES, int(np.ceil(max(1.0, float(fps)) / 3.0)))


def dense_ui_recovery_anchor_frame_indices(
    hits: Sequence[DetectionHit],
    *,
    frame_count: int,
    fps: float,
    transition_frames: Sequence[int] = (),
    min_frame_hits: int = PHASE1_SMALL_TEXT_MIN_FRAME_HITS,
) -> list[int]:
    """Select a bounded set of dense UI frames for high-resolution DBNet."""
    by_frame: Counter[int] = Counter(int(hit.frame_index) for hit in hits)
    candidates = {
        frame_index
        for frame_index, count in by_frame.items()
        if count >= max(2, int(min_frame_hits))
    }
    if not candidates:
        return []

    selected: set[int] = set()
    sorted_candidates = sorted(candidates)
    split_gap = max(3, int(round(max(1.0, float(fps)) * 0.20)))
    groups: list[list[int]] = []
    for frame_index in sorted_candidates:
        if not groups or frame_index - groups[-1][-1] > split_gap:
            groups.append([frame_index])
        else:
            groups[-1].append(frame_index)
    for group in groups:
        selected.add(max(group, key=lambda value: (by_frame[value], -value)))

    transition_min_gap = max(3, int(round(max(1.0, float(fps)) * 0.35)))
    for frame_index in sorted(
        int(value) for value in transition_frames if int(value) in candidates
    ):
        if all(abs(frame_index - prior) >= transition_min_gap for prior in selected):
            selected.add(frame_index)

    duration_minutes = max(1.0 / 60.0, float(frame_count) / max(1.0, float(fps)) / 60.0)
    cap = max(4, int(np.ceil(duration_minutes * PHASE1_SMALL_TEXT_MAX_ANCHORS_PER_MINUTE)))
    ranked = sorted(selected, key=lambda value: (by_frame[value], -value), reverse=True)
    return sorted(ranked[:cap])


def phase_offset_frame_indices(*, frame_count: int, step: int) -> list[int]:
    """
    Sparse probes between coarse samples (offset ``step // 2``, stride ``2 * step``).

    Catches text that never lands on a coarse index so dense windows can open there.
    """
    s = max(1, int(step))
    count = max(0, int(frame_count))
    if s < 2 or count <= 0:
        return []
    offset = s // 2
    return list(range(offset, count, s * 2))


def phase1_residual_risk_frame_indices(
    *,
    frame_count: int,
    fps: float,
    risk_seconds: float = PHASE1_RESIDUAL_RISK_SECONDS,
) -> set[int]:
    """Every frame in bounded intro/outro windows for alternate DBNet recall."""
    count = max(0, int(frame_count))
    if count <= 0:
        return set()
    window = max(1, int(round(max(1.0, float(fps)) * float(risk_seconds))))
    window = min(count, window)
    return set(range(window)) | set(range(max(0, count - window), count))


def format_timeline_time(seconds: float, *, fps: float | None = None) -> str:
    """Format seconds → ``MM:SS.mmm``."""
    del fps
    total_ms = int(round(float(seconds) * 1000.0))
    if total_ms < 0:
        total_ms = 0
    mins, rem_ms = divmod(total_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{mins:02d}:{secs:02d}.{ms:03d}"


def _box_centroid(xyxy: Sequence[float]) -> tuple[float, float]:
    x0, y0, x1, y1 = (float(v) for v in xyxy)
    return ((x0 + x1) * 0.5, (y0 + y1) * 0.5)


def _box_area(xyxy: Sequence[float]) -> float:
    x0, y0, x1, y1 = (float(v) for v in xyxy)
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def box_iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax0, ay0, ax1, ay1 = (float(v) for v in a[:4])
    bx0, by0, bx1, by1 = (float(v) for v in b[:4])
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    iw = max(0.0, ix1 - ix0)
    ih = max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    union = _box_area(a) + _box_area(b) - inter
    if union <= 1e-9:
        return 0.0
    return float(inter / union)


def stable_box_xyxy(
    boxes: Sequence[Sequence[float]],
    *,
    expansive: bool = False,
) -> list[float]:
    """
    Aggregate hit boxes into one stable xyxy.

    Default = per-edge median on IoU-consensus hits (drops one-off food slabs).
    ``expansive=True`` (thin bottom hardsubs): keep y median but pull x0/x1
    toward the wider evidence so truncated DBNet medians do not lock short.
    """
    if not boxes:
        return [0.0, 0.0, 1.0, 1.0]
    arr_all = np.asarray(
        [[float(v) for v in b[:4]] for b in boxes], dtype=np.float64
    )
    seed = [float(np.median(arr_all[:, i])) for i in range(4)]
    consensus: list[Sequence[float]] = []
    for box in boxes:
        if box_iou(box, seed) >= 0.22 or len(boxes) < 4:
            consensus.append(box)
    if len(consensus) < max(2, len(boxes) // 3):
        consensus = list(boxes)
    arr = np.asarray(
        [[float(v) for v in b[:4]] for b in consensus], dtype=np.float64
    )
    if not expansive:
        return [float(np.median(arr[:, i])) for i in range(4)]
    return [
        float(np.percentile(arr[:, 0], 10)),
        float(np.median(arr[:, 1])),
        float(np.percentile(arr[:, 2], 90)),
        float(np.median(arr[:, 3])),
    ]


def complete_locked_overlay_boxes_from_hit_evidence(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
) -> list[MergedTrack]:
    """Restore repeatedly observed edge glyphs hidden by a partial-box median.

    DBNet may detect only the right-hand glyphs for most frames on transparent
    bowls/bright food, while a substantial minority of frames contains the
    complete editor label. Use supported 20/80-percentile X edges only when
    the wider observations repeat, keep the opposite edge/Y stable, and cap
    growth. One-off scene slabs therefore cannot inflate the SSOT box.
    """
    completed: list[MergedTrack] = []
    for track in tracks:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        boxes = list(track.hit_boxes or ())
        if role == "hardsub" or len(boxes) < 5:
            completed.append(track)
            continue
        arr = np.asarray(
            [[float(value) for value in box[:4]] for box in boxes],
            dtype=np.float64,
        )
        med = np.median(arr, axis=0)
        med_w = max(1.0, float(med[2] - med[0]))
        med_h = max(1.0, float(med[3] - med[1]))
        centers_y = 0.5 * (arr[:, 1] + arr[:, 3])
        if _robust_std(centers_y.tolist()) > max(6.0, 0.20 * med_h):
            completed.append(track)
            continue

        new_x0 = float(track.box_coords[0])
        new_x1 = float(track.box_coords[2])
        min_support = max(3, int(np.ceil(0.15 * len(boxes))))
        edge_tol = max(2.0, 0.025 * med_w)

        left = float(np.percentile(arr[:, 0], 10))
        left_delta = float(med[0] - left)
        left_mask = arr[:, 0] <= left + edge_tol
        if (
            0.08 * med_w <= left_delta <= 0.45 * med_w
            and int(left_mask.sum()) >= min_support
            and float(np.median(arr[left_mask, 2] - arr[left_mask, 0]))
            >= 1.08 * med_w
            and float(np.median(np.abs(arr[left_mask, 2] - med[2])))
            <= 0.15 * med_w
        ):
            edge_pad = max(2.0, min(6.0, 0.03 * med_w))
            new_x0 = min(new_x0, max(0.0, left - edge_pad))

        right = float(np.percentile(arr[:, 2], 90))
        right_delta = float(right - med[2])
        right_mask = arr[:, 2] >= right - edge_tol
        if (
            0.08 * med_w <= right_delta <= 0.45 * med_w
            and int(right_mask.sum()) >= min_support
            and float(np.median(arr[right_mask, 2] - arr[right_mask, 0]))
            >= 1.08 * med_w
            and float(np.median(np.abs(arr[right_mask, 0] - med[0])))
            <= 0.15 * med_w
        ):
            edge_pad = max(2.0, min(6.0, 0.03 * med_w))
            new_x1 = min(float(frame_w), max(new_x1, right + edge_pad))

        if abs(new_x0 - float(track.box_coords[0])) < 1.0 and abs(
            new_x1 - float(track.box_coords[2])
        ) < 1.0:
            completed.append(track)
            continue
        box = [
            new_x0,
            float(track.box_coords[1]),
            new_x1,
            float(track.box_coords[3]),
        ]
        completed.append(
            MergedTrack(
                start_frame=int(track.start_frame),
                end_frame=int(track.end_frame),
                box_coords=box,
                best_frame_index=int(track.best_frame_index),
                best_sharpness=float(track.best_sharpness),
                centroid=_box_centroid(box),
                hit_count=int(track.hit_count),
                hit_boxes=list(track.hit_boxes),
                hit_frames=list(track.hit_frames),
                hit_sharpness=list(track.hit_sharpness),
            )
        )
    return completed


def _in_hardsub_y_band(
    xyxy: Sequence[float],
    *,
    frame_w: int,
    frame_h: int,
) -> bool:
    """True when the box sits in the thin bottom burn-in band (any X span)."""
    del frame_w  # width checked by callers / line gate
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    fh = max(1.0, float(frame_h))
    cy = ((y0 + y1) * 0.5) / fh
    h_frac = max(0.0, y1 - y0) / fh
    return cy >= HARDSUB_BAND_CY and h_frac <= THIN_HARDSUB_HEIGHT_FRAC and (x1 - x0) > 8.0


def _box_is_hardsub_line_geometry(
    xyxy: Sequence[float],
    *,
    frame_w: int,
    frame_h: int,
) -> bool:
    """Wide/aspect burn-in line on the true bottom strip — not endcard rows."""
    if not _in_hardsub_y_band(xyxy, frame_w=frame_w, frame_h=frame_h):
        return False
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    cy = ((y0 + y1) * 0.5) / fh
    if cy < HARDSUB_ROLE_CY:
        return False
    w = max(1.0, x1 - x0)
    h = max(1.0, y1 - y0)
    aspect = w / h
    return aspect >= HARDSUB_MIN_ASPECT or (w / fw) >= HARDSUB_MIN_W_FRAC


def _box_looks_like_thin_hardsub(
    xyxy: Sequence[float],
    *,
    frame_w: int,
    frame_h: int,
) -> bool:
    """Confirmed thin hardsub *line* (rejects square bottom-band food blobs)."""
    return _box_is_hardsub_line_geometry(
        xyxy, frame_w=frame_w, frame_h=frame_h
    )


def extend_hardsub_box_to_ink(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
    *,
    frame_w: int | None = None,
    frame_h: int | None = None,
    seed_score_frac: float = 0.22,
    gap_max_px: int = 72,
    y_pad_px: int = 10,
    max_width_frac: float = 0.78,
    max_grow_factor: float = 2.3,
) -> list[float]:
    """
    Horizontally extend a thin bottom hardsub box to cover continuous ink.

    DBNet often drops the right half when white burn-in sits on bright food.
    Score = stroke morphology + edges (not flat bright bowls). Fail-soft: never
    shrink; skip non-hardsub geometry; cap growth so short lines do not balloon.
    """
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return [x0, y0, x1, y1]
    fh = int(frame_h if frame_h is not None else frame_bgr.shape[0])
    fw = int(frame_w if frame_w is not None else frame_bgr.shape[1])
    if not _box_looks_like_thin_hardsub(
        (x0, y0, x1, y1), frame_w=fw, frame_h=fh
    ):
        return [x0, y0, x1, y1]
    seed_w = max(1.0, x1 - x0)
    # Already wide enough — further walk mostly eats bowls/food, not glyphs.
    if seed_w / float(fw) >= 0.62:
        return [x0, y0, x1, y1]

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    iy0 = max(0, int(round(y0)) - int(y_pad_px))
    iy1 = min(fh, int(round(y1)) + int(y_pad_px))
    if iy1 - iy0 < 4:
        return [x0, y0, x1, y1]
    band = gray[iy0:iy1, :]
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    enh = clahe.apply(band)
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    tophat = cv2.morphologyEx(enh, cv2.MORPH_TOPHAT, ker).astype(np.float32).mean(
        axis=0
    )
    blackhat = cv2.morphologyEx(
        enh, cv2.MORPH_BLACKHAT, ker
    ).astype(np.float32).mean(axis=0)
    sobel = cv2.Sobel(enh, cv2.CV_32F, 1, 0, ksize=3)
    edge = np.mean(np.abs(sobel), axis=0)
    bright = (enh.astype(np.float32) >= 210.0).mean(axis=0)
    dark = (enh.astype(np.float32) <= 35.0).mean(axis=0)
    # Stroke/outline hardsubs: avoid flat white bowls (bright without edge).
    ink = (
        (tophat + blackhat) / 35.0
        + edge / 50.0
        + np.minimum(bright, dark * 3.0) * 2.0
        + bright * edge / 50.0
    )
    smooth = np.convolve(ink, np.ones(25, dtype=np.float32) / 25.0, mode="same")

    sx0 = max(0, min(fw - 1, int(round(x0))))
    sx1 = max(sx0 + 1, min(fw, int(round(x1))))
    seed_mean = float(smooth[sx0:sx1].mean()) + 1e-6
    thr = max(0.08, seed_mean * float(seed_score_frac))
    gap_max = max(8, int(gap_max_px))

    def _walk(start: int, step: int) -> int:
        last = start
        gap = 0
        x = start
        while True:
            x += step
            if x < 0 or x >= fw:
                break
            if float(smooth[x]) >= thr:
                last = x
                gap = 0
            else:
                gap += 1
                if gap > gap_max:
                    break
        return last

    left = sx0
    # Left walk only when ink abutting seed.x0 is nearly as strong as the
    # seed core (true left-truncation). Soft thr alone treats wood/food grain
    # as ink and balloons complete mid-width lines to x=0.
    seed_w_frac = seed_w / float(fw)
    left_bridge = (
        float(smooth[max(0, sx0 - 8) : sx0].mean()) if sx0 > 0 else 0.0
    )
    allow_left_walk = seed_w_frac < 0.22 or left_bridge >= seed_mean * 0.75
    if allow_left_walk:
        left = min(_walk(sx0, -1), sx0)
        # Reject frame-edge / over-wide left balloons on already-complete seeds:
        # wood/food grain often matches seed_mean, so bridge strength alone fails.
        if left < sx0 and seed_w_frac >= 0.28:
            grown_w = float(sx0 - left)
            grown_mean = float(smooth[left:sx0].mean())
            if left <= 16 or (
                grown_w > seed_w * 0.55 and grown_mean <= seed_mean * 1.10
            ):
                left = sx0
    right = max(_walk(sx1 - 1, 1) + 1, sx1)
    # Trim a weak tail: growth into bowls/food often has low stroke ink.
    while right > sx1 + 12:
        tail_a = max(sx1, right - 48)
        tail_mean = float(smooth[tail_a:right].mean())
        if tail_mean >= thr * 0.85:
            break
        right -= 8
    right = max(right, sx1)
    max_w = min(
        max_width_frac * float(fw),
        seed_w * float(max_grow_factor),
    )
    if (right - left) > max_w:
        # Prefer keeping the seed left edge when growth was rightward.
        if left < sx0 and (right - sx0) <= max_w:
            left = float(sx0)
            right = min(float(fw), float(sx0) + max_w)
        else:
            right = min(fw, int(round(left + max_w)))
    return [float(left), y0, float(right), y1]


def _hardsub_band_ink_profile(
    frame_bgr: np.ndarray,
    *,
    y0: float,
    y1: float,
    frame_w: int,
    frame_h: int,
    y_pad_px: int = 10,
    smooth_kernel: int = 25,
) -> np.ndarray | None:
    """1-D horizontal stroke/edge ink score for a thin hardsub Y band."""
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return None
    fh = int(frame_h)
    fw = int(frame_w)
    iy0 = max(0, int(round(y0)) - int(y_pad_px))
    iy1 = min(fh, int(round(y1)) + int(y_pad_px))
    if iy1 - iy0 < 4:
        return None
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    band = gray[iy0:iy1, :fw]
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    enh = clahe.apply(band)
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    tophat = cv2.morphologyEx(enh, cv2.MORPH_TOPHAT, ker).astype(np.float32).mean(
        axis=0
    )
    blackhat = cv2.morphologyEx(
        enh, cv2.MORPH_BLACKHAT, ker
    ).astype(np.float32).mean(axis=0)
    sobel = cv2.Sobel(enh, cv2.CV_32F, 1, 0, ksize=3)
    edge = np.mean(np.abs(sobel), axis=0)
    bright = (enh.astype(np.float32) >= 210.0).mean(axis=0)
    dark = (enh.astype(np.float32) <= 35.0).mean(axis=0)
    ink = (
        (tophat + blackhat) / 35.0
        + edge / 50.0
        + np.minimum(bright, dark * 3.0) * 2.0
        + bright * edge / 50.0
    )
    k = max(1, int(smooth_kernel))
    if k <= 1:
        return ink.astype(np.float32)
    return np.convolve(ink, np.ones(k, dtype=np.float32) / float(k), mode="same")


def trim_hardsub_box_to_ink(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
    *,
    frame_w: int | None = None,
    frame_h: int | None = None,
    seed_score_frac: float = 0.22,
    empty_edge_px: int = 24,
    y_pad_px: int = 10,
    gap_merge_px: int = 28,
    seed_xyxy: Sequence[float] | None = None,
) -> list[float]:
    """
    Shrink thin hardsub X margins that lack stroke ink (empty pad to x=0).

    Anchors to the ink-run cluster overlapping the seed core so left-edge food
    texture cannot keep an empty pad. Fail-soft: never expand; skip non-hardsub.
    """
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    fh = int(frame_h if frame_h is not None else frame_bgr.shape[0])
    fw = int(frame_w if frame_w is not None else frame_bgr.shape[1])
    if not _box_looks_like_thin_hardsub(
        (x0, y0, x1, y1), frame_w=fw, frame_h=fh
    ):
        return [x0, y0, x1, y1]
    # Narrow smooth for trim: wide kernel bleeds empty pad past glyph mets.
    smooth = _hardsub_band_ink_profile(
        frame_bgr,
        y0=y0,
        y1=y1,
        frame_w=fw,
        frame_h=fh,
        y_pad_px=y_pad_px,
        smooth_kernel=7,
    )
    if smooth is None or smooth.size < 8:
        return [x0, y0, x1, y1]

    sx0 = max(0, min(fw - 1, int(round(x0))))
    sx1 = max(sx0 + 1, min(fw, int(round(x1))))
    anchor = [float(v) for v in (seed_xyxy or xyxy)[:4]]
    ax0 = max(0, min(fw - 1, int(round(anchor[0]))))
    ax1 = max(ax0 + 1, min(fw, int(round(anchor[2]))))
    core0 = ax0 + min(empty_edge_px, max(0, (ax1 - ax0) // 4))
    core1 = ax1 - min(empty_edge_px, max(0, (ax1 - ax0) // 4))
    if core1 <= core0 + 8:
        core0, core1 = ax0, ax1
    core_mean = float(smooth[core0:core1].mean()) + 1e-6
    thr = max(0.08, core_mean * float(seed_score_frac))

    ink = smooth >= thr
    runs: list[tuple[int, int]] = []
    i = 0
    n = int(ink.shape[0])
    while i < n:
        if not bool(ink[i]):
            i += 1
            continue
        j = i + 1
        while j < n and bool(ink[j]):
            j += 1
        if j - i >= 6:
            runs.append((i, j))
        i = j
    if not runs:
        return [x0, y0, x1, y1]

    # Merge nearby runs (glyph gaps / thin stroke breaks).
    merged: list[list[int]] = [[runs[0][0], runs[0][1]]]
    for a, b in runs[1:]:
        if a - merged[-1][1] <= int(gap_merge_px):
            merged[-1][1] = b
        else:
            merged.append([a, b])

    seed_cx = 0.5 * (float(anchor[0]) + float(anchor[2]))
    best_run: list[int] | None = None
    if seed_xyxy is not None:
        best_score = -1.0
        for a, b in merged:
            overlap = max(0, min(b, ax1) - max(a, ax0))
            if overlap <= 0:
                dist = min(
                    abs(a - seed_cx),
                    abs(b - seed_cx),
                    abs(0.5 * (a + b) - seed_cx),
                )
                score = -dist
            else:
                score = float(overlap) + 0.01 * float(b - a)
            if score > best_score:
                best_score = score
                best_run = [a, b]
    else:
        # No seed: keep the longest ink cluster inside the box (main burn-in).
        best_run = max(merged, key=lambda ab: ab[1] - ab[0])
        best_run = [best_run[0], best_run[1]]
    if best_run is None:
        return [x0, y0, x1, y1]
    left, right = best_run
    if seed_xyxy is not None:
        # Anchor to seed: metal/food columns left of the stable seed often score
        # as weak ink and must not reopen an empty left pad.
        strong = thr * 1.15
        # Over-extend often opens a wood/food pad left of a complete seed.
        # Snap back when that pad is weak; keep left absorb when pad holds glyphs.
        skip_left_absorb = False
        if ax0 > sx0 + 32:
            left_pad_mean = float(smooth[sx0:ax0].mean())
            seed_core = float(smooth[ax0:ax1].mean()) + 1e-6
            pad_w = float(ax0 - sx0)
            # Weak pad, or frame-edge wood/food pad scoring like seed ink.
            if left_pad_mean < thr * 0.85 or sx0 <= 16 or (
                sx0 <= max(24.0, 0.05 * fw)
                and pad_w > 0.08 * fw
                and left_pad_mean <= seed_core * 1.10
            ):
                skip_left_absorb = True
        if skip_left_absorb:
            left = max(left, ax0)
        else:
            left = max(left, min(sx1 - 24, ax0))
            while left > sx0 and left > best_run[0] and float(smooth[left - 1]) >= strong:
                left -= 1
        right = max(right, ax1)
        while right < sx1 and right < best_run[1] and float(smooth[min(right, n - 1)]) >= (
            thr * 0.75
        ):
            right += 1
        # Grow right through the seed-overlapping run (complete truncated lines).
        while right < best_run[1] and float(smooth[right]) >= thr * 0.65:
            right += 1
        # CJK hardsubs often leave 40–80px weak gaps between glyph clusters;
        # absorb at most one strong neighbor per side (no chain into food bands).
        absorb_gap = max(int(gap_merge_px), int(0.045 * fw))
        max_neighbor_w = int(0.14 * fw)
        left_neighbor: tuple[int, int] | None = None
        right_neighbor: tuple[int, int] | None = None
        for a, b in merged:
            aa, bb = int(a), int(b)
            run_w = bb - aa
            if run_w < 6 or run_w > max_neighbor_w:
                continue
            if float(smooth[aa:bb].mean()) < thr * 0.75:
                continue
            if (
                not skip_left_absorb
                and bb <= left
                and (left - bb) <= absorb_gap
            ):
                if aa <= 16 and ax0 > 80:
                    continue
                if left_neighbor is None or aa < left_neighbor[0]:
                    left_neighbor = (aa, bb)
            if aa >= right and (aa - right) <= absorb_gap:
                if bb >= fw - 16 and ax1 < fw - 80:
                    continue
                if right_neighbor is None or bb > right_neighbor[1]:
                    right_neighbor = (aa, bb)
        if left_neighbor is not None:
            left = left_neighbor[0]
        if right_neighbor is not None:
            right = right_neighbor[1]
        # Left completion when extend already opened past seed into strong ink.
        if (
            not skip_left_absorb
            and best_run[0] < left
            and float(smooth[best_run[0] : left].mean()) >= thr * 0.85
        ):
            left = best_run[0]
        if skip_left_absorb:
            left = max(left, ax0)
    # Tiny outward pad only — hug glyph mets (no long soft walk into food).
    pad = 4
    left = max(sx0, left - pad)
    right = min(sx1, right + pad)
    if right - left < 24:
        return [x0, y0, x1, y1]
    return [float(left), y0, float(right), y1]


def trim_hardsub_box_y_to_ink(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
    *,
    frame_w: int | None = None,
    frame_h: int | None = None,
    seed_score_frac: float = 0.22,
    x_pad_px: int = 8,
    gap_merge_px: int = 6,
    edge_pad_px: int = 4,
    search_pad_px: int = 6,
) -> list[float]:
    """
    Shrink thin hardsub Y margins that lack stroke ink (empty pad above/below).

    Searches a small band beyond detector Y so clipped glyph outlines can be
    completed from stroke evidence. Fails soft and skips non-hardsub geometry.
    """
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return [x0, y0, x1, y1]
    fh = int(frame_h if frame_h is not None else frame_bgr.shape[0])
    fw = int(frame_w if frame_w is not None else frame_bgr.shape[1])
    if not _box_looks_like_thin_hardsub(
        (x0, y0, x1, y1), frame_w=fw, frame_h=fh
    ):
        return [x0, y0, x1, y1]
    search_pad = max(0, int(search_pad_px))
    sy0 = max(0, min(fh - 1, int(round(y0)) - search_pad))
    sy1 = max(sy0 + 1, min(fh, int(round(y1)) + search_pad))
    if sy1 - sy0 < 8:
        return [x0, y0, x1, y1]
    ix0 = max(0, min(fw - 1, int(round(x0)) - int(x_pad_px)))
    ix1 = max(ix0 + 1, min(fw, int(round(x1)) + int(x_pad_px)))
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    band = gray[sy0:sy1, ix0:ix1]
    if band.size < 16:
        return [x0, y0, x1, y1]
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
    enh = clahe.apply(band)
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    tophat = cv2.morphologyEx(enh, cv2.MORPH_TOPHAT, ker).astype(np.float32).mean(
        axis=1
    )
    blackhat = cv2.morphologyEx(
        enh, cv2.MORPH_BLACKHAT, ker
    ).astype(np.float32).mean(axis=1)
    sobel = cv2.Sobel(enh, cv2.CV_32F, 0, 1, ksize=3)
    edge = np.mean(np.abs(sobel), axis=1)
    ink = (tophat + blackhat) / 35.0 + edge / 50.0
    smooth = np.convolve(ink, np.ones(5, dtype=np.float32) / 5.0, mode="same")
    core0 = max(0, (sy1 - sy0) // 4)
    core1 = max(core0 + 2, (sy1 - sy0) - (sy1 - sy0) // 4)
    core_mean = float(smooth[core0:core1].mean()) + 1e-6
    thr = max(0.06, core_mean * float(seed_score_frac))
    mask = smooth >= thr
    runs: list[tuple[int, int]] = []
    i = 0
    n = int(mask.shape[0])
    while i < n:
        if not bool(mask[i]):
            i += 1
            continue
        j = i + 1
        while j < n and bool(mask[j]):
            j += 1
        if j - i >= 2:
            runs.append((i, j))
        i = j
    if not runs:
        return [x0, y0, x1, y1]
    merged: list[list[int]] = [[runs[0][0], runs[0][1]]]
    for a, b in runs[1:]:
        if a - merged[-1][1] <= int(gap_merge_px):
            merged[-1][1] = b
        else:
            merged.append([a, b])
    best = max(merged, key=lambda ab: ab[1] - ab[0])
    top = sy0 + best[0]
    bot = sy0 + best[1]
    soft = thr * 0.45
    while top > sy0 and float(smooth[top - sy0 - 1]) >= soft:
        top -= 1
    while bot < sy1 and float(smooth[bot - sy0]) >= soft:
        bot += 1
    pad = max(1, int(edge_pad_px))
    top = max(sy0, top - pad)
    bot = min(sy1, bot + pad)
    if bot - top < 8:
        return [x0, y0, x1, y1]
    return [x0, float(top), x1, float(bot)]


def tighten_hardsub_box_to_neutral_glyphs(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
    *,
    frame_w: int | None = None,
    frame_h: int | None = None,
    min_line_width_frac: float = 0.12,
    merge_gap_frac: float = 0.045,
    edge_pad_px: int = 6,
) -> list[float] | None:
    """
    Tighten a hardsub X span from near-neutral bright glyph evidence.

    Edited CJK burn-ins in the product path are bright neutral glyphs with a
    dark outline. Wood/food texture may have stronger generic edges than the
    text, so the older stroke walk can balloon. This pass is deliberately
    conservative and returns ``None`` unless a plausible multi-glyph line is
    present; callers then retain the existing ink result.
    """
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return None
    fh = int(frame_h if frame_h is not None else frame_bgr.shape[0])
    fw = int(frame_w if frame_w is not None else frame_bgr.shape[1])
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    if not _box_looks_like_thin_hardsub(
        (x0, y0, x1, y1), frame_w=fw, frame_h=fh
    ):
        return None
    ix0 = max(0, min(fw - 1, int(np.floor(x0))))
    ix1 = max(ix0 + 1, min(fw, int(np.ceil(x1))))
    iy0 = max(0, min(fh - 1, int(np.floor(y0)) - 3))
    iy1 = max(iy0 + 1, min(fh, int(np.ceil(y1)) + 3))
    band = frame_bgr[iy0:iy1, ix0:ix1]
    if band.size < 128:
        return None

    bgr = band.astype(np.int16)
    hi = bgr.max(axis=2)
    lo = bgr.min(axis=2)
    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    # Bright neutral fill plus outline/edge adjacency. Chroma rejects brown
    # wood and saturated food even when their generic stroke score is high.
    neutral = (gray >= 165) & ((hi - lo) <= 58)
    dark = gray <= 78
    dark_near = cv2.dilate(
        dark.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3)),
    ).astype(bool)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    edge = (np.abs(gx) + np.abs(gy)) >= 36.0
    glyph = neutral & (dark_near | edge)

    # Suppress neutral scene structures (plate/rim/highlight) that touch the
    # whole crop height. Editor glyph components form repeated character-like
    # islands sharing a baseline and normally stay inside the Y crop edges.
    component_mask = np.zeros_like(glyph, dtype=np.uint8)
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        glyph.astype(np.uint8), connectivity=8
    )
    kept_components = 0
    band_h = int(glyph.shape[0])
    for label in range(1, int(count)):
        cx, cy, cw, ch, area = (int(v) for v in stats[label])
        if area < 12 or ch < max(6, int(round(0.18 * band_h))):
            continue
        touches_y_edge = cy <= 1 or (cy + ch) >= band_h - 1
        max_aspect = 1.45 if touches_y_edge else 2.6
        if cw > max(18, int(round(max_aspect * ch))):
            continue
        component_mask[labels == label] = 1
        kept_components += 1
    if kept_components < 2:
        return None
    glyph = component_mask.astype(bool)

    min_col_pixels = max(2, int(round(0.055 * glyph.shape[0])))
    active = glyph.sum(axis=0) >= min_col_pixels
    runs: list[tuple[int, int]] = []
    i = 0
    while i < int(active.shape[0]):
        if not bool(active[i]):
            i += 1
            continue
        j = i + 1
        while j < int(active.shape[0]) and bool(active[j]):
            j += 1
        if j - i >= 2:
            runs.append((i, j))
        i = j
    if len(runs) < 2:
        return None

    # First build character groups with a strict gap. A single permissive gap
    # chains plate highlights on the left into the centered subtitle line.
    base_gap = max(12, min(40, int(round(0.022 * fw))))
    clusters: list[list[int]] = [[runs[0][0], runs[0][1], 1]]
    for a, b in runs[1:]:
        if a - clusters[-1][1] <= base_gap:
            clusters[-1][1] = b
            clusters[-1][2] += 1
        else:
            clusters.append([a, b, 1])
    min_group_w = max(48, int(round(0.08 * fw)))
    plausible = [
        row
        for row in clusters
        if row[2] >= 2 and (row[1] - row[0]) >= min_group_w
    ]
    if not plausible:
        return None
    options: list[list[int]] = [list(row) for row in plausible]
    join_gap = max(base_gap, int(round(float(merge_gap_frac) * fw)))
    for index, row in enumerate(plausible[:-1]):
        nxt = plausible[index + 1]
        if nxt[0] - row[1] <= join_gap:
            options.append([row[0], nxt[1], row[2] + nxt[2]])

    # Burn-in captions are centered by editors. Center penalty separates a
    # true two-part CJK line from neutral plate/rim highlights at frame edges.
    frame_center_local = 0.5 * fw - ix0
    left, right, _n = max(
        options,
        key=lambda row: (
            (row[1] - row[0])
            - 0.60 * abs(0.5 * (row[0] + row[1]) - frame_center_local)
            + 2.0 * row[2]
        ),
    )
    if right - left < float(min_line_width_frac) * fw:
        return None
    pad = max(2, int(edge_pad_px))
    left = max(ix0, ix0 + int(left) - pad)
    right = min(ix1, ix0 + int(right) + pad)
    if right - left < float(min_line_width_frac) * fw:
        return None
    return [float(left), y0, float(right), y1]


def pick_best_hardsub_ink_box(
    candidates: Sequence[Sequence[float]],
    *,
    seed: Sequence[float],
    frame_w: int,
    max_width_frac: float = 0.78,
) -> list[float]:
    """
    Prefer the widest ink-hugging hardsub box that still covers the seed core.

    Tight mid-slices clip long burn-in lines; empty x=0 pads (food-edge false
    ink) are rejected when the seed is clearly mid-frame.
    """
    if not candidates:
        return [float(v) for v in seed[:4]]
    seed_x0 = float(seed[0])
    seed_x1 = float(seed[2])
    seed_cx = 0.5 * (seed_x0 + seed_x1)
    seed_w = max(1.0, seed_x1 - seed_x0)
    max_w = float(max_width_frac) * max(1.0, float(frame_w))
    # Allow left growth for truncated DBNet seeds; still reject frame-edge
    # balloons when the stable seed sits mid-frame.
    min_x0 = 0.0 if seed_x0 <= 48.0 else max(16.0, seed_x0 - 420.0)
    # Prefer wider coverage; break ties toward less empty-left slack vs seed.
    best: list[float] | None = None
    best_key: tuple[float, float] | None = None
    for raw in candidates:
        box = [float(v) for v in raw[:4]]
        tw = box[2] - box[0]
        if tw < seed_w * 0.55:
            continue
        if tw > max_w + 1.0:
            continue
        if not (box[0] <= seed_cx <= box[2]):
            continue
        if box[0] < min_x0:
            box[0] = min_x0
            tw = box[2] - box[0]
            if tw < seed_w * 0.55:
                continue
        # Reject empty-left regression: claiming near x=0 while seed is mid.
        # Clamp to min_x0 instead of discarding a good right-side completion.
        if box[0] <= 12.0 and seed_x0 > 80.0:
            box[0] = min_x0
            tw = box[2] - box[0]
            if tw < seed_w * 0.55 or not (box[0] <= seed_cx <= box[2]):
                continue
        slack_left = max(0.0, (seed_x0 - 48.0) - box[0])
        # Width counts; empty-left columns count less (prefer hug).
        score = tw - 0.85 * slack_left
        key = (score, -abs(box[0] - seed_x0))
        if best_key is None or key > best_key:
            best = box
            best_key = key
    if best is None:
        return [float(v) for v in seed[:4]]
    return best


def recover_hardsub_box_from_band_ink(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
    *,
    frame_w: int | None = None,
    frame_h: int | None = None,
    min_width_frac: float = 0.28,
    max_width_frac: float = 0.78,
    gap_merge_px: int = 36,
    y_pad_px: int = 10,
) -> list[float] | None:
    """
    Rebuild a thin bottom hardsub box from the dominant ink run in its Y band.

    Right/left stubs from truncated DBNet often miss the centered burn-in line;
    this recovers the full glyph span on the keyframe without trusting the stub X.
    Also re-anchors Y to the strongest thin band near the bottom when the seed
    Y sits on food/edge texture above the true hardsub.
    """
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    fh = int(frame_h if frame_h is not None else frame_bgr.shape[0])
    fw = int(frame_w if frame_w is not None else frame_bgr.shape[1])
    # Allow compact/square seeds in the band (food FP stubs) so Y-reanchor can
    # still find the real burn-in line; callers must keep only line geometry.
    if not _in_hardsub_y_band((x0, y0, x1, y1), frame_w=fw, frame_h=fh):
        return None
    seed_h = max(36.0, y1 - y0, 0.035 * float(fh))
    seed_w_frac = (x1 - x0) / max(1.0, float(fw))
    seed_aspect = (x1 - x0) / max(1.0, y1 - y0)
    seed_cy = (0.5 * (y0 + y1)) / max(1.0, float(fh))
    seed_h_frac = (y1 - y0) / max(1.0, float(fh))
    y_candidates: list[tuple[float, float]] = [
        (max(0.0, y0 - 8.0), min(float(fh), y1 + 8.0))
    ]
    # Y-hunt for stub/square food FPs AND wide thin mid-band slabs (rice-edge
    # texture). Narrow endcard chips are excluded by callers; do not Y-hunt
    # already-true bottom burn-in lines (keeps their Y).
    wide_mid_band_slab = (
        seed_cy < HARDSUB_ROLE_CY
        and seed_w_frac >= 0.18
        and seed_aspect >= HARDSUB_MIN_ASPECT
        and seed_h_frac <= THIN_HARDSUB_HEIGHT_FRAC
    )
    if (
        seed_w_frac < 0.22
        or seed_aspect < HARDSUB_MIN_ASPECT
        or wide_mid_band_slab
    ):
        for cy_frac in (0.90, 0.92, 0.935, 0.95):
            cy = cy_frac * float(fh)
            yy0 = max(0.0, cy - 0.5 * seed_h)
            yy1 = min(float(fh), cy + 0.5 * seed_h)
            y_candidates.append((yy0, yy1))

    best_peak = -1.0
    band_y0, band_y1 = y0, y1
    best_smooth: np.ndarray | None = None
    for yy0, yy1 in y_candidates:
        smooth = _hardsub_band_ink_profile(
            frame_bgr,
            y0=yy0,
            y1=yy1,
            frame_w=fw,
            frame_h=fh,
            y_pad_px=y_pad_px,
        )
        if smooth is None or smooth.size < 16:
            continue
        peak = float(np.percentile(smooth, 90))
        thr_y = max(0.12, peak * 0.28 + 1e-6)
        xs = np.where(smooth >= thr_y)[0]
        if xs.size < 24:
            continue
        span_frac = float(xs[-1] - xs[0] + 1) / float(fw)
        cy_mid = (0.5 * (yy0 + yy1)) / float(fh)
        # Prefer strong ink with a plausible hardsub span (not full-frame food).
        if span_frac < 0.22 or span_frac > 0.82:
            score = peak * 0.35
        else:
            score = peak * (0.7 + 0.3 * min(1.0, span_frac / 0.45))
        # True burn-ins sit near the bottom edge; food rows above (cy~0.85–0.90)
        # often have strong horizontal texture and must not win the band pick.
        if cy_mid >= 0.92:
            score *= 1.28
        elif cy_mid < 0.88:
            score *= 0.50
        if score > best_peak:
            best_peak = score
            band_y0, band_y1 = yy0, yy1
            best_smooth = smooth
    if best_smooth is None:
        return None
    smooth = best_smooth
    thr = max(0.12, float(np.percentile(smooth, 90)) * 0.28 + 1e-6)
    ink = smooth >= thr
    runs: list[tuple[int, int]] = []
    i = 0
    n = int(ink.shape[0])
    while i < n:
        if not bool(ink[i]):
            i += 1
            continue
        j = i + 1
        while j < n and bool(ink[j]):
            j += 1
        if j - i >= 8:
            runs.append((i, j))
        i = j
    if not runs:
        return None
    merged: list[list[int]] = [[runs[0][0], runs[0][1]]]
    for a, b in runs[1:]:
        if a - merged[-1][1] <= int(gap_merge_px):
            merged[-1][1] = b
        else:
            merged.append([a, b])
    cx = 0.5 * float(fw)
    best = max(
        merged,
        key=lambda ab: (ab[1] - ab[0])
        - 0.15 * abs(0.5 * (ab[0] + ab[1]) - cx),
    )
    left, right = best
    pad = 14
    left = max(0, left - pad)
    right = min(fw, right + pad)
    width = right - left
    if width < float(min_width_frac) * float(fw):
        return None
    if width > float(max_width_frac) * float(fw):
        mid = 0.5 * (left + right)
        half = 0.5 * float(max_width_frac) * float(fw)
        left = max(0, int(round(mid - half)))
        right = min(fw, int(round(mid + half)))
    return [float(left), float(band_y0), float(right), float(band_y1)]


def extend_hardsub_tracks_to_ink(
    tracks: Sequence[MergedTrack],
    *,
    frame_cache: Mapping[int, np.ndarray],
    frame_w: int,
    frame_h: int,
    source: Path | None = None,
) -> list[MergedTrack]:
    """Extend then trim thin bottom hardsubs so the box hugs glyph ink."""
    out: list[MergedTrack] = []
    for track in tracks:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        # Endcard list chips sit in HARDSUB_BAND_CY but are not burn-ins —
        # never Y-reanchor / ink-extend them into a bottom hardsub line.
        if role != "hardsub":
            out.append(track)
            continue
        if not _in_hardsub_y_band(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        ):
            out.append(track)
            continue
        current = [float(v) for v in track.box_coords[:4]]
        current_w = max(1.0, current[2] - current[0])
        hit_seed = (
            stable_box_xyxy(track.hit_boxes, expansive=False)
            if track.hit_boxes
            else list(current)
        )
        hit_w = max(1.0, float(hit_seed[2]) - float(hit_seed[0]))
        hit_is_line = _box_is_hardsub_line_geometry(
            hit_seed, frame_w=frame_w, frame_h=frame_h
        )
        current_is_line = _box_is_hardsub_line_geometry(
            current, frame_w=frame_w, frame_h=frame_h
        )
        edge_limit = max(12.0, 0.00625 * float(frame_w))
        hit_touches_edge = (
            float(hit_seed[0]) <= edge_limit
            or float(hit_seed[2]) >= float(frame_w) - edge_limit
        )
        unique_hit_frames = sorted({int(value) for value in track.hit_frames})
        hit_span = (
            max(1, unique_hit_frames[-1] - unique_hit_frames[0] + 1)
            if unique_hit_frames
            else 1
        )
        hit_density = len(unique_hit_frames) / float(hit_span)
        dense_detector_timing_guard = (
            not hit_touches_edge
            and hit_is_line
            and len(unique_hit_frames) >= 3
            and hit_density >= 0.35
        )
        dense_detector_consensus_guard = (
            dense_detector_timing_guard
            and (hit_w / max(1.0, float(frame_w))) >= 0.22
        )
        # Never seed ink-extend from food / endcard slabs in the band.
        if current_is_line and (not hit_is_line or current_w >= hit_w * 1.1):
            seed = current
        elif hit_is_line:
            seed = [float(v) for v in hit_seed[:4]]
        elif current_is_line:
            seed = current
        else:
            out.append(track)
            continue

        # Hardsub text often changes across a long track; hug ink on the
        # keyframe (+ a couple nearby sharp hits), not a union of every line.
        candidate_frames: list[int] = [int(track.best_frame_index)]
        if track.hit_frames and track.hit_sharpness:
            ranked = sorted(
                range(len(track.hit_frames)),
                key=lambda i: float(track.hit_sharpness[i]),
                reverse=True,
            )
            best_fi = int(track.best_frame_index)
            for i in ranked:
                fi = int(track.hit_frames[i])
                if fi in candidate_frames:
                    continue
                if abs(fi - best_fi) > 45:
                    continue
                candidate_frames.append(fi)
                if len(candidate_frames) >= 4:
                    break

        # Prefer band-ink recovery only for narrow side stubs. Mid-width
        # left-/right-truncated seeds (w≈0.25–0.35) must fall through to
        # extend+trim — recover often returns a same-width lock.
        seed_w_frac = (float(seed[2]) - float(seed[0])) / max(1.0, float(frame_w))
        focus_frames = list(candidate_frames)
        recovered_candidates: list[list[float]] = []
        if seed_w_frac < 0.22:
            for fi in focus_frames:
                frame = frame_cache.get(fi)
                if frame is None and source is not None:
                    frame = _read_frame(source, fi)
                if frame is None:
                    continue
                recovered = recover_hardsub_box_from_band_ink(
                    frame,
                    seed,
                    frame_w=frame_w,
                    frame_h=frame_h,
                )
                if recovered is not None and _box_is_hardsub_line_geometry(
                    recovered, frame_w=frame_w, frame_h=frame_h
                ):
                    recovery_y_search_pad = 6
                    if dense_detector_timing_guard and (
                        float(recovered[1]) < float(hit_seed[1]) - 4.0
                        or float(recovered[3]) > float(hit_seed[3]) + 4.0
                    ):
                        recovery_y_search_pad = 0
                    recovered = trim_hardsub_box_y_to_ink(
                        frame,
                        recovered,
                        frame_w=frame_w,
                        frame_h=frame_h,
                        search_pad_px=recovery_y_search_pad,
                    )
                    recovered_candidates.append(recovered)
        if recovered_candidates:
            best = pick_best_hardsub_ink_box(
                recovered_candidates,
                seed=seed if seed_w_frac >= 0.12 else recovered_candidates[0],
                frame_w=frame_w,
                max_width_frac=0.78,
            )
            # When seed was a side stub, allow recovered box even if it does
            # not cover the old seed center (pick_best would reject).
            if seed_w_frac < 0.20:
                best = max(
                    recovered_candidates,
                    key=lambda b: float(b[2]) - float(b[0]),
                )
            recovered_w = float(best[2]) - float(best[0])
            seed_w = max(1.0, float(seed[2]) - float(seed[0]))
            recovered_detector_overlap = max(
                0.0,
                min(float(best[2]), float(hit_seed[2]))
                - max(float(best[0]), float(hit_seed[0])),
            )
            recovered_left_growth = max(
                0.0, float(hit_seed[0]) - float(best[0])
            )
            recovered_right_growth = max(
                0.0, float(best[2]) - float(hit_seed[2])
            )
            recovery_relocated_from_dense_core = (
                dense_detector_timing_guard
                and recovered_detector_overlap / max(1.0, hit_w) < 0.05
            )
            recovery_one_sided_balloon = (
                dense_detector_timing_guard
                and 0.12 <= hit_w / max(1.0, float(frame_w)) < 0.22
                and recovered_w >= hit_w * 1.75
                and max(recovered_left_growth, recovered_right_growth)
                >= 0.15 * float(frame_w)
                and min(recovered_left_growth, recovered_right_growth)
                <= 0.04 * float(frame_w)
            )
            recovery_broad_balloon = (
                dense_detector_timing_guard
                and hit_w / max(1.0, float(frame_w)) >= 0.12
                and recovered_w >= hit_w * 1.80
            )
            two_sided_extreme_recovery = (
                hit_is_line
                and (hit_w / max(1.0, float(frame_w))) >= 0.12
                and (recovered_w / max(1.0, float(frame_w))) >= 0.50
                and float(hit_seed[0]) - float(best[0])
                >= 0.04 * float(frame_w)
                and float(best[2]) - float(hit_seed[2])
                >= 0.04 * float(frame_w)
                and len(unique_hit_frames) >= 3
                and hit_density >= 0.35
            )
            # Never regress a wide recovered current box back to a food stub.
            if (
                _box_is_hardsub_line_geometry(
                    current, frame_w=frame_w, frame_h=frame_h
                )
                and recovered_w + 1.0 < current_w * 0.85
            ):
                out.append(track)
                continue
            # Require material widening; otherwise fall through to extend+trim.
            if (
                not recovery_relocated_from_dense_core
                and not recovery_one_sided_balloon
                and not recovery_broad_balloon
                and not two_sided_extreme_recovery
                and recovered_w >= seed_w * 1.12
                and (
                abs(best[0] - track.box_coords[0]) >= 1.0
                or abs(best[2] - track.box_coords[2]) >= 1.0
                )
            ):
                updated = MergedTrack(
                    start_frame=track.start_frame,
                    end_frame=track.end_frame,
                    box_coords=best,
                    best_frame_index=track.best_frame_index,
                    best_sharpness=track.best_sharpness,
                    centroid=_box_centroid(best),
                    hit_count=track.hit_count,
                    hit_boxes=list(track.hit_boxes),
                    hit_frames=list(track.hit_frames),
                    hit_sharpness=list(track.hit_sharpness),
                )
                out.append(updated)
                continue

        # Compact non-line seeds with no successful recover: never rewrite a
        # burn-in track to a non-line seed (food slabs in hit_boxes).
        if not _box_is_hardsub_line_geometry(
            seed, frame_w=frame_w, frame_h=frame_h
        ):
            out.append(track)
            continue

        best = list(seed)
        seed_w = max(1.0, float(seed[2]) - float(seed[0]))
        seed_w_frac = seed_w / max(1.0, float(frame_w))
        candidates: list[list[float]] = []
        glyph_candidates: list[list[float]] = []
        for fi in candidate_frames:
            frame = frame_cache.get(fi)
            if frame is None and source is not None:
                frame = _read_frame(source, fi)
            if frame is None:
                continue
            if seed_w_frac < 0.62:
                extended = extend_hardsub_box_to_ink(
                    frame, seed, frame_w=frame_w, frame_h=frame_h
                )
            else:
                # Already-wide expansive seed: trim only on this frame.
                extended = list(seed)
            trimmed = trim_hardsub_box_to_ink(
                frame,
                extended,
                frame_w=frame_w,
                frame_h=frame_h,
                seed_xyxy=seed,
            )
            y_search_pad = 6
            if dense_detector_consensus_guard and (
                float(trimmed[1]) < float(hit_seed[1]) - 4.0
                or float(trimmed[3]) > float(hit_seed[3]) + 4.0
            ):
                # The candidate already left a dense detector Y core (typically
                # an adjacent food/outline band). It may shrink back to ink but
                # must not search even farther away from the core.
                y_search_pad = 0
            trimmed = trim_hardsub_box_y_to_ink(
                frame,
                trimmed,
                frame_w=frame_w,
                frame_h=frame_h,
                search_pad_px=y_search_pad,
            )
            glyph_tight = tighten_hardsub_box_to_neutral_glyphs(
                frame,
                trimmed,
                frame_w=frame_w,
                frame_h=frame_h,
            )
            if glyph_tight is not None:
                glyph_candidates.append(glyph_tight)
            candidates.append(trimmed)

        glyph_consensus: list[float] | None = None
        if len(glyph_candidates) >= 2:
            proposal = stable_box_xyxy(glyph_candidates, expansive=False)
            agreeing = sum(
                1 for box in glyph_candidates if box_iou(box, proposal) >= 0.60
            )
            seed_overlap = max(
                0.0,
                min(float(proposal[2]), float(seed[2]))
                - max(float(proposal[0]), float(seed[0])),
            )
            seed_coverage = seed_overlap / max(
                1.0, float(seed[2]) - float(seed[0])
            )
            proposal_w = max(1.0, float(proposal[2]) - float(proposal[0]))
            proposal_cx = 0.5 * (float(proposal[0]) + float(proposal[2]))
            excess_seed_pad = max(
                0.0,
                float(proposal[0]) - float(seed[0]),
                float(seed[2]) - float(proposal[2]),
            )
            centered_relocation = (
                # Keep this wide: a short centered neutral subset may omit
                # valid glyphs on either side. Narrow post-ink reconciliation
                # is handled with OCR-supported normalized geometry instead.
                proposal_w >= 0.28 * float(frame_w)
                and abs(proposal_cx - 0.5 * float(frame_w))
                <= 0.08 * float(frame_w)
                and excess_seed_pad >= 0.20 * float(frame_w)
            )
            detector_core_boxes: list[Sequence[float]] = []
            detector_core_frames: list[int] = []
            if agreeing >= 2:
                # A partial neutral anchor may omit colored/outlined prefix
                # glyphs. Recover them from repeated detector boxes that still
                # cover the anchor, while rejecting a much wider DBNet slab
                # formed by attaching independent scene text on one side.
                for index, box in enumerate(track.hit_boxes):
                    if not _box_is_hardsub_line_geometry(
                        box, frame_w=frame_w, frame_h=frame_h
                    ):
                        continue
                    bx0, _by0, bx1, _by1 = (float(value) for value in box[:4])
                    box_w = max(1.0, bx1 - bx0)
                    anchor_overlap = max(
                        0.0,
                        min(bx1, float(proposal[2]))
                        - max(bx0, float(proposal[0])),
                    )
                    if anchor_overlap / proposal_w < 0.90:
                        continue
                    if box_w > proposal_w * 1.85:
                        continue
                    detector_core_boxes.append(box)
                    if index < len(track.hit_frames):
                        detector_core_frames.append(int(track.hit_frames[index]))
                unique_core_frames = sorted(set(detector_core_frames))
                core_density = 0.0
                if unique_core_frames:
                    core_span = max(
                        1, unique_core_frames[-1] - unique_core_frames[0] + 1
                    )
                    core_density = len(unique_core_frames) / float(core_span)
                if (
                    len(detector_core_boxes) >= 3
                    and len(unique_core_frames) >= 3
                    and core_density >= 0.35
                ):
                    detector_core = stable_box_xyxy(
                        detector_core_boxes, expansive=False
                    )
                    detector_core_w = max(
                        1.0, float(detector_core[2]) - float(detector_core[0])
                    )
                    shared_edge_limit = max(12.0, 0.02 * float(frame_w))
                    attachment_min = 0.20 * float(frame_w)
                    right_side_attachment = (
                        abs(float(detector_core[0]) - float(seed[0]))
                        <= shared_edge_limit
                        and float(seed[2]) - float(detector_core[2])
                        >= attachment_min
                    )
                    left_side_attachment = (
                        abs(float(detector_core[2]) - float(seed[2]))
                        <= shared_edge_limit
                        and float(detector_core[0]) - float(seed[0])
                        >= attachment_min
                    )
                    track_span = max(
                        1, int(track.end_frame) - int(track.start_frame) + 1
                    )
                    core_track_coverage = len(unique_core_frames) / float(track_span)
                    core_cx = 0.5 * (
                        float(detector_core[0]) + float(detector_core[2])
                    )
                    balloon_reference = max(
                        [seed, current, *candidates],
                        key=lambda box: float(box[2]) - float(box[0]),
                    )
                    balloon_w = max(
                        1.0,
                        float(balloon_reference[2])
                        - float(balloon_reference[0]),
                    )
                    extreme_geometry = (
                        balloon_w / max(1.0, float(frame_w)) >= 0.68
                        or (
                            balloon_w / max(1.0, float(frame_w)) >= 0.60
                            and max(seed_w, current_w)
                            / max(1.0, float(frame_w))
                            <= 0.50
                        )
                    )
                    two_sided_extreme_balloon = (
                        agreeing >= 3
                        and extreme_geometry
                        and detector_core_w <= balloon_w * 0.78
                        and float(detector_core[0])
                        - float(balloon_reference[0])
                        >= shared_edge_limit
                        and float(balloon_reference[2])
                        - float(detector_core[2])
                        >= shared_edge_limit
                        and abs(core_cx - 0.5 * float(frame_w))
                        <= 0.10 * float(frame_w)
                        and core_track_coverage >= 0.80
                    )
                    if (
                        detector_core_w >= proposal_w * 0.95
                        and detector_core_w <= proposal_w * 1.85
                        and (
                            (right_side_attachment != left_side_attachment)
                            or two_sided_extreme_balloon
                        )
                    ):
                        glyph_consensus = [
                            float(value) for value in detector_core[:4]
                        ]
            # Never let a color-only cluster replace most DBNet evidence. This
            # rejects a centered food highlight that would clip a valid long
            # caption. Exception: a multi-frame, wide, centered glyph line can
            # prove that the seed carries a huge empty side pad.
            if glyph_consensus is None and agreeing >= 2 and (
                seed_coverage >= 0.88 or centered_relocation
            ):
                glyph_consensus = proposal
        if glyph_consensus is not None:
            # Multi-frame neutral-glyph consensus is stronger than the seed:
            # it may legitimately remove a large empty side pad from DBNet.
            best = glyph_consensus
        elif candidates:
            best = pick_best_hardsub_ink_box(
                candidates,
                seed=seed,
                frame_w=frame_w,
                max_width_frac=0.78,
            )
        if dense_detector_timing_guard:
            detector_overlap = max(
                0.0,
                min(float(best[2]), float(hit_seed[2]))
                - max(float(best[0]), float(hit_seed[0])),
            )
            detector_core_coverage = detector_overlap / max(1.0, hit_w)
            best_w = max(1.0, float(best[2]) - float(best[0]))
            left_growth = max(0.0, float(hit_seed[0]) - float(best[0]))
            right_growth = max(0.0, float(best[2]) - float(hit_seed[2]))
            one_sided_short_core_balloon = (
                0.12 <= hit_w / max(1.0, float(frame_w)) < 0.22
                and best_w >= hit_w * 1.75
                and max(left_growth, right_growth) >= 0.15 * float(frame_w)
                and min(left_growth, right_growth) <= 0.04 * float(frame_w)
            )
            broad_dense_core_balloon = (
                hit_w / max(1.0, float(frame_w)) >= 0.12
                and best_w >= hit_w * 1.80
            )
            # Refinement may tighten or extend a dense DBNet line, but it may
            # never relocate the caption to a disjoint texture band. This is
            # especially important for short centered captions: food/wood at
            # a frame edge can have stronger projection ink than the glyphs.
            if detector_core_coverage < 0.05 or one_sided_short_core_balloon:
                best = [float(value) for value in hit_seed[:4]]
            elif broad_dense_core_balloon:
                # The dense detector remains X authority, while the completed
                # ink candidate may contain outline/descender pixels outside
                # DBNet's truncated Y core.
                best = [
                    float(hit_seed[0]),
                    float(best[1]),
                    float(hit_seed[2]),
                    float(best[3]),
                ]
        if dense_detector_consensus_guard:
            best_w = max(1.0, float(best[2]) - float(best[0]))
            best_touches_edge = (
                float(best[0]) <= edge_limit
                or float(best[2]) >= float(frame_w) - edge_limit
            )
            # Several detector frames agree on a substantial centered line.
            # Whether inherited or newly introduced in this call, one-sided
            # edge growth is scene texture rather than missing caption ink.
            if best_touches_edge and best_w >= hit_w * 1.35:
                best = [float(value) for value in hit_seed[:4]]

        if (
            abs(best[0] - track.box_coords[0]) < 1.0
            and abs(best[1] - track.box_coords[1]) < 1.0
            and abs(best[2] - track.box_coords[2]) < 1.0
            and abs(best[3] - track.box_coords[3]) < 1.0
        ):
            out.append(track)
            continue
        updated = MergedTrack(
            start_frame=track.start_frame,
            end_frame=track.end_frame,
            box_coords=best,
            best_frame_index=track.best_frame_index,
            best_sharpness=track.best_sharpness,
            centroid=_box_centroid(best),
            hit_count=track.hit_count,
            hit_boxes=list(track.hit_boxes),
            hit_frames=list(track.hit_frames),
            hit_sharpness=list(track.hit_sharpness),
        )
        out.append(updated)
    return out


def constrain_hardsubs_to_dense_detector_coverage(
    tracks: Sequence[MergedTrack],
    hits: Sequence[DetectionHit],
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """Final X guard using raw pre-merge detector coverage as authority.

    Track-local hit arrays can legitimately accumulate nearby fragments during
    merge/split/reconciliation. Raw per-frame coverage is independent of those
    mutations, so it is the final authority for proving that a very wide X
    extent really repeated. Ink-normalized Y remains untouched.
    """
    fw = max(1.0, float(frame_w))
    by_frame: dict[int, list[list[float]]] = {}
    for hit in hits:
        box = [float(value) for value in hit.box_xyxy[:4]]
        if (box[2] - box[0]) / fw < 0.12:
            continue
        if classify_ocr_box_role(
            box, frame_w=frame_w, frame_h=frame_h
        ) != "hardsub":
            continue
        by_frame.setdefault(int(hit.frame_index), []).append(box)

    output: list[MergedTrack] = []
    rows: list[dict[str, Any]] = []
    for track in tracks:
        if classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        ) != "hardsub":
            output.append(track)
            continue
        final_box = [float(value) for value in track.box_coords[:4]]
        final_cy = 0.5 * (final_box[1] + final_box[3])
        per_frame_union: list[list[float]] = []
        for frame_index in range(
            int(track.start_frame), int(track.end_frame) + 1
        ):
            matching: list[list[float]] = []
            for hit_box in by_frame.get(frame_index, []):
                hit_cy = 0.5 * (hit_box[1] + hit_box[3])
                if abs(hit_cy - final_cy) > 45.0:
                    continue
                overlap = max(
                    0.0,
                    min(hit_box[2], final_box[2])
                    - max(hit_box[0], final_box[0]),
                )
                hit_width = max(1.0, hit_box[2] - hit_box[0])
                if overlap / hit_width < 0.50:
                    continue
                matching.append(hit_box)
            if matching:
                per_frame_union.append(
                    [
                        min(box[0] for box in matching),
                        min(box[1] for box in matching),
                        max(box[2] for box in matching),
                        max(box[3] for box in matching),
                    ]
                )
        track_span = max(
            1, int(track.end_frame) - int(track.start_frame) + 1
        )
        if (
            len(per_frame_union) < 3
            or len(per_frame_union) / float(track_span) < 0.35
        ):
            output.append(track)
            continue
        detector_x0 = float(np.median([box[0] for box in per_frame_union]))
        detector_x1 = float(np.median([box[2] for box in per_frame_union]))
        detector_width = max(1.0, detector_x1 - detector_x0)
        final_width = max(1.0, final_box[2] - final_box[0])
        if detector_width / fw < 0.12 or final_width < detector_width * 1.80:
            output.append(track)
            continue
        corrected = [
            detector_x0,
            final_box[1],
            detector_x1,
            final_box[3],
        ]
        output.append(
            MergedTrack(
                start_frame=int(track.start_frame),
                end_frame=int(track.end_frame),
                box_coords=corrected,
                best_frame_index=int(track.best_frame_index),
                best_sharpness=float(track.best_sharpness),
                centroid=_box_centroid(corrected),
                hit_count=int(track.hit_count),
                hit_boxes=list(track.hit_boxes),
                hit_frames=list(track.hit_frames),
                hit_sharpness=list(track.hit_sharpness),
            )
        )
        rows.append(
            {
                "span": [int(track.start_frame), int(track.end_frame)],
                "prior_box": final_box,
                "result_box": corrected,
                "dense_frames": len(per_frame_union),
                "track_span": track_span,
                "width_ratio": round(final_width / detector_width, 4),
            }
        )
    return output, {
        "method": "raw_dense_detector_x_authority_v1",
        "adjusted_tracks": len(rows),
        "rows": rows,
    }


FINAL_SPARSE_CLUSTER_MIN_HITS = 3
FINAL_SPARSE_CLUSTER_MIN_SHARE = 0.70
FINAL_SPARSE_CLUSTER_MIN_SEPARATION = 4
def _copy_track_with_hit_indices(
    track: MergedTrack,
    indices: Sequence[int],
) -> MergedTrack:
    """Keep final geometry while reducing temporal evidence to selected hits."""
    selected = [int(index) for index in indices]
    frames = [int(track.hit_frames[index]) for index in selected]
    boxes = [tuple(float(v) for v in track.hit_boxes[index][:4]) for index in selected]
    source_sharpness = list(track.hit_sharpness) or [
        float(track.best_sharpness)
    ] * len(track.hit_frames)
    sharpness = [
        float(source_sharpness[index])
        if index < len(source_sharpness)
        else float(track.best_sharpness)
        for index in selected
    ]
    best_offset = max(range(len(selected)), key=lambda offset: sharpness[offset])
    return MergedTrack(
        start_frame=min(frames),
        end_frame=max(frames),
        box_coords=list(track.box_coords),
        best_frame_index=frames[best_offset],
        best_sharpness=sharpness[best_offset],
        centroid=tuple(track.centroid),
        hit_count=len(selected),
        hit_boxes=boxes,
        hit_frames=frames,
        hit_sharpness=sharpness,
    )


def split_tracks_by_visual_content_change(
    tracks: Sequence[MergedTrack],
    *,
    frame_cache: Mapping[int, np.ndarray],
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """Split a stable geometry track using local edge-content change points.

    This is intentionally model-free. It compares normalized glyph-edge maps
    only on detector evidence frames, then requires at least two observations
    on both sides of a change. Geometry and content state remain independent.
    """

    output: list[MergedTrack] = []
    rows: list[dict[str, Any]] = []
    for track in tracks:
        if len(track.hit_frames) < 5 or len(track.hit_boxes) != len(track.hit_frames):
            output.append(track)
            continue
        signatures: list[np.ndarray] = []
        valid_indices: list[int] = []
        for index, frame_index in enumerate(track.hit_frames):
            frame = frame_cache.get(int(frame_index))
            crop = (
                _crop_xyxy_from_frame(frame, track.box_coords)
                if frame is not None
                else None
            )
            if crop is None or crop.size < 64:
                continue
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            normalized = cv2.resize(gray, (128, 32), interpolation=cv2.INTER_AREA)
            normalized = cv2.createCLAHE(
                clipLimit=2.0, tileGridSize=(8, 4)
            ).apply(normalized)
            signatures.append(cv2.Canny(normalized, 48, 136) > 0)
            valid_indices.append(index)
        if len(signatures) < 5:
            output.append(track)
            continue
        deltas = np.asarray(
            [
                float(np.mean(np.logical_xor(left, right)))
                for left, right in zip(signatures, signatures[1:])
            ],
            dtype=np.float32,
        )
        median = float(np.median(deltas))
        mad = float(np.median(np.abs(deltas - median)))
        threshold = max(0.08, median + 3.5 * max(0.005, mad))
        cuts = [
            index + 1
            for index, score in enumerate(deltas)
            if float(score) >= threshold
            and index + 1 >= 2
            and len(signatures) - (index + 1) >= 2
        ]
        groups: list[list[int]] = []
        offset = 0
        for cut in cuts:
            if cut - offset >= 2:
                groups.append(valid_indices[offset:cut])
                offset = cut
        if len(valid_indices) - offset >= 2:
            groups.append(valid_indices[offset:])
        elif groups:
            groups[-1].extend(valid_indices[offset:])
        if len(groups) < 2:
            output.append(track)
            continue
        segments = [_copy_track_with_hit_indices(track, group) for group in groups]
        boundaries = [
            (
                int(left.hit_frames[-1]) + int(right.hit_frames[0])
            )
            // 2
            for left, right in zip(segments, segments[1:])
        ]
        rebuilt: list[MergedTrack] = []
        for index, segment in enumerate(segments):
            start = int(track.start_frame) if index == 0 else boundaries[index - 1] + 1
            end = int(track.end_frame) if index == len(segments) - 1 else boundaries[index]
            rebuilt.append(
                _copy_track_with_span(segment, start_frame=start, end_frame=end)
            )
        output.extend(rebuilt)
        rows.append(
            {
                "prior_span": [track.start_frame, track.end_frame],
                "result_spans": [
                    [segment.start_frame, segment.end_frame] for segment in rebuilt
                ],
                "threshold": round(threshold, 4),
                "peak_delta": round(float(np.max(deltas)), 4),
            }
        )
    return output, {
        "method": "visual_edge_change_point_v1",
        "before_count": len(tracks),
        "after_count": len(output),
        "split_tracks": len(rows),
        "trimmed_tracks": 0,
        "segments_created": sum(len(row["result_spans"]) for row in rows),
        "network_calls": 0,
        "model_calls": 0,
        "rows": rows,
    }


def _trim_isolated_sparse_hit_cluster(
    track: MergedTrack,
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[MergedTrack, dict[str, Any] | None]:
    """Trim a lone detector outlier when one contiguous cluster dominates.

    This is deliberately fail-closed: two meaningful clusters stay untouched so
    content segmentation/operator review can decide. Only a singleton separated
    from a >=3-hit cluster may be discarded.
    """
    evidence = track_boundary_evidence(track, frame_w=frame_w, frame_h=frame_h)
    if "sparse_temporal_evidence" not in list(evidence.get("reasons") or []):
        return track, None
    if len(track.hit_frames) != len(track.hit_boxes) or len(track.hit_frames) < 4:
        return track, None

    frame_to_indices: dict[int, list[int]] = {}
    for index, raw_frame in enumerate(track.hit_frames):
        frame_to_indices.setdefault(int(raw_frame), []).append(index)
    unique_frames = sorted(frame_to_indices)
    if len(unique_frames) < 4:
        return track, None

    clusters: list[list[int]] = []
    for frame_index in unique_frames:
        if not clusters or frame_index > clusters[-1][-1] + 1:
            clusters.append([frame_index])
        else:
            clusters[-1].append(frame_index)
    if len(clusters) < 2:
        return track, None

    ranked = sorted(clusters, key=lambda row: (-len(row), row[0]))
    dominant = ranked[0]
    runner_up = ranked[1]
    dominant_share = len(dominant) / float(len(unique_frames))
    separation = min(
        abs(int(frame) - int(other))
        for frame in dominant
        for other in runner_up
    )
    if (
        len(dominant) < FINAL_SPARSE_CLUSTER_MIN_HITS
        or dominant_share < FINAL_SPARSE_CLUSTER_MIN_SHARE
        or len(runner_up) > 1
        or separation < FINAL_SPARSE_CLUSTER_MIN_SEPARATION
    ):
        return track, None

    selected = [
        index
        for frame_index in dominant
        for index in frame_to_indices[frame_index]
    ]
    trimmed = _copy_track_with_hit_indices(track, selected)
    return trimmed, {
        "action": "trim_sparse_outlier_cluster",
        "prior_span": [int(track.start_frame), int(track.end_frame)],
        "result_span": [int(trimmed.start_frame), int(trimmed.end_frame)],
        "prior_hit_frames": unique_frames,
        "result_hit_frames": sorted({int(value) for value in trimmed.hit_frames}),
        "dominant_share": round(dominant_share, 4),
    }


def _coverage_fade_hit_score(
    track_box: Sequence[float],
    hit_box: Sequence[float],
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[float, float] | None:
    """Score a smaller same-band raw hit as a possible fading tail fragment."""
    if classify_ocr_box_role(
        hit_box, frame_w=frame_w, frame_h=frame_h
    ) != "hardsub":
        return None
    tx0, ty0, tx1, ty1 = (float(value) for value in track_box[:4])
    hx0, hy0, hx1, hy1 = (float(value) for value in hit_box[:4])
    track_width = max(1.0, tx1 - tx0)
    hit_width = max(1.0, hx1 - hx0)
    if hit_width / max(1.0, float(frame_w)) < 0.12:
        return None
    # A short fade remnant is contained by the preceding full caption. A new
    # full-width caption must not be absorbed merely because it shares a locus.
    if hit_width > 0.85 * track_width:
        return None
    overlap = max(0.0, min(tx1, hx1) - max(tx0, hx0))
    overlap_ratio = overlap / hit_width
    if overlap_ratio < 0.65:
        return None
    vertical_gap = max(0.0, max(ty0, hy0) - min(ty1, hy1))
    if vertical_gap > 0.025 * max(1.0, float(frame_h)):
        return None
    track_cy = 0.5 * (ty0 + ty1)
    hit_cy = 0.5 * (hy0 + hy1)
    if abs(track_cy - hit_cy) > 0.065 * max(1.0, float(frame_h)):
        return None
    return overlap_ratio, hit_width


def _raw_hit_is_explained_by_other_track(
    hit: DetectionHit,
    *,
    owner: MergedTrack,
    tracks: Sequence[MergedTrack],
    frame_w: int,
    frame_h: int,
) -> bool:
    hit_box = hit.box_xyxy
    hx0, hy0, hx1, hy1 = (float(value) for value in hit_box[:4])
    hit_width = max(1.0, hx1 - hx0)
    hit_cy = 0.5 * (hy0 + hy1)
    frame_index = int(hit.frame_index)
    for other in tracks:
        if other is owner or not (
            int(other.start_frame) <= frame_index <= int(other.end_frame)
        ):
            continue
        if classify_ocr_box_role(
            other.box_coords, frame_w=frame_w, frame_h=frame_h
        ) != "hardsub":
            continue
        ox0, oy0, ox1, oy1 = (float(value) for value in other.box_coords[:4])
        overlap = max(0.0, min(ox1, hx1) - max(ox0, hx0))
        other_cy = 0.5 * (oy0 + oy1)
        if overlap / hit_width >= 0.50 and abs(other_cy - hit_cy) <= 0.065 * max(
            1.0, float(frame_h)
        ):
            return True
    return False


def _extend_short_hardsub_fade_tail(
    track: MergedTrack,
    *,
    tracks: Sequence[MergedTrack],
    hits_by_frame: Mapping[int, Sequence[DetectionHit]],
    frame_count: int,
    frame_w: int,
    frame_h: int,
) -> tuple[MergedTrack, dict[str, Any] | None]:
    if classify_ocr_box_role(
        track.box_coords, frame_w=frame_w, frame_h=frame_h
    ) != "hardsub":
        return track, None
    evidence = track_boundary_evidence(track, frame_w=frame_w, frame_h=frame_h)
    if evidence.get("status") != "confirmed":
        return track, None

    selected: list[DetectionHit] = []
    # Read one frame past the allowed tail. If compatible evidence persists,
    # it is probably a new caption/track rather than a bounded fade remnant.
    overflow = False
    for offset in range(1, FINAL_COVERAGE_FADE_TAIL_MAX_FRAMES + 2):
        frame_index = int(track.end_frame) + offset
        if frame_index >= int(frame_count):
            break
        candidates: list[tuple[tuple[float, float], DetectionHit]] = []
        for hit in hits_by_frame.get(frame_index, ()):
            score = _coverage_fade_hit_score(
                track.box_coords,
                hit.box_xyxy,
                frame_w=frame_w,
                frame_h=frame_h,
            )
            if score is None or _raw_hit_is_explained_by_other_track(
                hit,
                owner=track,
                tracks=tracks,
                frame_w=frame_w,
                frame_h=frame_h,
            ):
                continue
            candidates.append((score, hit))
        if not candidates:
            break
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        if offset > FINAL_COVERAGE_FADE_TAIL_MAX_FRAMES:
            overflow = True
            break
        selected.append(candidates[0][1])

    if not selected or overflow:
        return track, None

    frames = list(track.hit_frames)
    boxes = list(track.hit_boxes)
    sharpness = list(track.hit_sharpness)
    for hit in selected:
        frames.append(int(hit.frame_index))
        boxes.append(tuple(float(value) for value in hit.box_xyxy[:4]))
        sharpness.append(float(hit.sharpness))
    extended = MergedTrack(
        start_frame=int(track.start_frame),
        end_frame=max(int(hit.frame_index) for hit in selected),
        box_coords=list(track.box_coords),
        best_frame_index=int(track.best_frame_index),
        best_sharpness=float(track.best_sharpness),
        centroid=tuple(track.centroid),
        hit_count=len(boxes),
        hit_boxes=boxes,
        hit_frames=frames,
        hit_sharpness=sharpness,
    )
    return extended, {
        "action": "extend_bounded_hardsub_fade_tail",
        "prior_span": [int(track.start_frame), int(track.end_frame)],
        "result_span": [int(extended.start_frame), int(extended.end_frame)],
        "frames_added": [int(hit.frame_index) for hit in selected],
    }


def reconcile_final_tracks_with_coverage(
    tracks: Sequence[MergedTrack],
    hits: Sequence[DetectionHit],
    *,
    frame_count: int,
    frame_w: int,
    frame_h: int,
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """Final fail-closed reconciliation of exported spans against raw evidence.

    Geometry is never re-scanned or replaced here. The pass only removes a
    proven isolated temporal outlier or attaches a short, contiguous fade tail
    already present in the pre-merge detector authority.
    """
    sparse_rows: list[dict[str, Any]] = []
    trimmed: list[MergedTrack] = []
    for track in tracks:
        updated, row = _trim_isolated_sparse_hit_cluster(
            track, frame_w=frame_w, frame_h=frame_h
        )
        trimmed.append(updated)
        if row is not None:
            sparse_rows.append(row)

    hits_by_frame: dict[int, list[DetectionHit]] = {}
    for hit in hits:
        hits_by_frame.setdefault(int(hit.frame_index), []).append(hit)

    coverage_rows: list[dict[str, Any]] = []
    output: list[MergedTrack] = []
    for track in trimmed:
        updated, row = _extend_short_hardsub_fade_tail(
            track,
            tracks=trimmed,
            hits_by_frame=hits_by_frame,
            frame_count=frame_count,
            frame_w=frame_w,
            frame_h=frame_h,
        )
        output.append(updated)
        if row is not None:
            coverage_rows.append(row)

    return output, {
        "method": "final_temporal_coverage_reconciliation_v1",
        "sparse_clusters_trimmed": len(sparse_rows),
        "coverage_edges_extended": len(coverage_rows),
        "coverage_frames_added": sum(
            len(list(row.get("frames_added") or [])) for row in coverage_rows
        ),
        "sparse_rows": sparse_rows,
        "coverage_rows": coverage_rows,
    }


def _is_residual_bottom_caption_box(
    box: Sequence[float],
    *,
    frame_w: int,
    frame_h: int,
) -> bool:
    role = classify_ocr_box_role(box, frame_w=frame_w, frame_h=frame_h)
    if role == "hardsub":
        return True
    if role != "generic":
        return False
    x0, y0, x1, y1 = (float(value) for value in box[:4])
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    cy_frac = 0.5 * (y0 + y1) / fh
    return (
        cy_frac >= RESIDUAL_HARDSUB_GENERIC_MIN_CY_FRAC
        and width / fw >= RESIDUAL_HARDSUB_MIN_WIDTH_FRAC
        and height / fh <= RESIDUAL_HARDSUB_MAX_HEIGHT_FRAC
        and width / height >= HARDSUB_MIN_ASPECT
    )


def _residual_hit_covered_by_track(
    hit: DetectionHit,
    track: MergedTrack,
    *,
    frame_w: int,
    frame_h: int,
) -> bool:
    frame_index = int(hit.frame_index)
    if not int(track.start_frame) <= frame_index <= int(track.end_frame):
        return False
    if not _is_residual_bottom_caption_box(
        track.box_coords, frame_w=frame_w, frame_h=frame_h
    ):
        return False
    hx0, hy0, hx1, hy1 = (float(value) for value in hit.box_xyxy[:4])
    tx0, ty0, tx1, ty1 = (float(value) for value in track.box_coords[:4])
    overlap = max(0.0, min(hx1, tx1) - max(hx0, tx0))
    shorter = max(1.0, min(hx1 - hx0, tx1 - tx0))
    hit_cy = 0.5 * (hy0 + hy1)
    track_cy = 0.5 * (ty0 + ty1)
    return (
        overlap / shorter >= 0.50
        and abs(hit_cy - track_cy) <= 0.065 * max(1.0, float(frame_h))
    )


def _residual_shadow_host(
    hit: DetectionHit,
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
) -> MergedTrack | None:
    hx0, hy0, hx1, hy1 = (float(value) for value in hit.box_xyxy[:4])
    hit_width = max(1.0, hx1 - hx0)
    hit_height = max(1.0, hy1 - hy0)
    hit_cy = 0.5 * (hy0 + hy1)
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    for host in tracks:
        if not int(host.start_frame) <= int(hit.frame_index) <= int(host.end_frame):
            continue
        if not _is_residual_bottom_caption_box(
            host.box_coords, frame_w=frame_w, frame_h=frame_h
        ):
            continue
        x0, y0, x1, y1 = (float(value) for value in host.box_coords[:4])
        host_width = max(1.0, x1 - x0)
        host_height = max(1.0, y1 - y0)
        host_cy = 0.5 * (y0 + y1)
        horizontal_gap = max(0.0, max(x0, hx0) - min(x1, hx1))
        vertical_gap = max(0.0, max(y0, hy0) - min(y1, hy1))
        near_bottom_edge = hy1 >= 0.985 * fh
        adjacent_fragment = (
            horizontal_gap <= 0.04 * fw
            and vertical_gap <= 0.025 * fh
            and hit_width <= 0.80 * host_width
            and hit_height <= 1.25 * host_height
        )
        if (
            abs(hit_cy - host_cy) <= 0.085 * fh
            and (near_bottom_edge or adjacent_fragment)
        ):
            return host
    return None


def _frame_spans(frame_indices: Sequence[int]) -> list[list[int]]:
    spans: list[list[int]] = []
    for frame_index in sorted({int(value) for value in frame_indices}):
        if not spans or frame_index > spans[-1][1] + 1:
            spans.append([frame_index, frame_index, 1])
        else:
            spans[-1][1] = frame_index
            spans[-1][2] += 1
    return spans


def recover_residual_hardsub_tracks(
    tracks: Sequence[MergedTrack],
    hits: Sequence[DetectionHit],
    *,
    frame_cache: Mapping[int, np.ndarray],
    frame_count: int,
    frame_w: int,
    frame_h: int,
    recognizer: Any | None,
    source: Path | None = None,
    batch_size: int = 32,
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """Recover verified bottom captions and audit residual detector shadows.

    Raw coverage is recall authority, but it also contains food edges,
    descenders and fade ghosts.  Only multi-frame local-text consensus can add
    a missing track.  A rejected fragment is explained as shadow only beside
    an already active caption; otherwise it remains explicit operator work.
    """
    audit: dict[str, Any] = {
        "method": RESIDUAL_HARDSUB_RECOVERY_POLICY_VERSION,
        "recognizer_available": recognizer is not None,
        "candidate_hits": 0,
        "covered_hits": 0,
        "recovered_tracks": [],
        "explained_shadow_frames": [],
        "unresolved_frames": [],
        "unresolved_spans": [],
        "rows": [],
    }
    residual: list[DetectionHit] = []
    crops: list[np.ndarray] = []
    for hit in hits:
        if not _is_residual_bottom_caption_box(
            hit.box_xyxy, frame_w=frame_w, frame_h=frame_h
        ):
            continue
        audit["candidate_hits"] += 1
        if any(
            _residual_hit_covered_by_track(
                hit, track, frame_w=frame_w, frame_h=frame_h
            )
            for track in tracks
        ):
            audit["covered_hits"] += 1
            continue
        frame = _boundary_frame(
            int(hit.frame_index), frame_cache=frame_cache, source=source
        )
        crop = (
            _crop_xyxy_from_frame(frame, hit.box_xyxy)
            if frame is not None
            else None
        )
        if crop is None or crop.size < 16:
            audit["unresolved_frames"].append(int(hit.frame_index))
            audit["rows"].append(
                {
                    "action": "unresolved_missing_frame",
                    "frame_index": int(hit.frame_index),
                    "box": [float(value) for value in hit.box_xyxy[:4]],
                }
            )
            continue
        residual.append(hit)
        crops.append(crop)

    recognitions: list[Any | None] = [None] * len(residual)
    if recognizer is not None:
        try:
            size = max(1, int(batch_size))
            parsed: list[Any] = []
            for offset in range(0, len(crops), size):
                batch = crops[offset : offset + size]
                rows = list(recognizer.recognize_batch(batch))
                if len(rows) != len(batch):
                    raise RuntimeError("residual recognizer batch size mismatch")
                parsed.extend(rows)
            recognitions = parsed
        except Exception as exc:  # noqa: BLE001
            audit["recognizer_error"] = type(exc).__name__
            recognitions = [None] * len(residual)

    accepted: list[dict[str, Any]] = []
    explained_frames: set[int] = set()
    unresolved_frames: set[int] = set(audit["unresolved_frames"])
    for hit, recognition in zip(residual, recognitions):
        accepted_text = bool(
            recognition is not None
            and local_text_accepts_track(recognition, role="hardsub")
        )
        recognition_text = str(getattr(recognition, "text", "") or "")
        recognition_confidence = float(
            getattr(recognition, "confidence", 0.0) or 0.0
        )
        if accepted_text:
            accepted.append(
                {
                    "hit": hit,
                    "text": recognition_text,
                    "confidence": recognition_confidence,
                }
            )
            continue
        host = _residual_shadow_host(
            hit, tracks, frame_w=frame_w, frame_h=frame_h
        )
        if host is not None and recognition is not None:
            explained_frames.add(int(hit.frame_index))
            audit["rows"].append(
                {
                    "action": "explain_adjacent_shadow",
                    "frame_index": int(hit.frame_index),
                    "box": [float(value) for value in hit.box_xyxy[:4]],
                    "host_span": [int(host.start_frame), int(host.end_frame)],
                    "host_box": [float(value) for value in host.box_coords[:4]],
                    "recognition_text": recognition_text,
                    "recognition_confidence": round(recognition_confidence, 4),
                }
            )
            continue
        unresolved_frames.add(int(hit.frame_index))
        audit["rows"].append(
            {
                "action": (
                    "unresolved_recognizer_unavailable"
                    if recognition is None
                    else "unresolved_no_local_text_consensus"
                ),
                "frame_index": int(hit.frame_index),
                "box": [float(value) for value in hit.box_xyxy[:4]],
                "recognition_text": recognition_text,
                "recognition_confidence": round(recognition_confidence, 4),
            }
        )

    # Merge multiple accepted fragments in the same bottom band and frame.
    per_frame: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in accepted:
        per_frame[int(row["hit"].frame_index)].append(row)
    normalized: list[dict[str, Any]] = []
    for frame_index, frame_rows in sorted(per_frame.items()):
        bands: list[list[dict[str, Any]]] = []
        for row in sorted(
            frame_rows,
            key=lambda value: 0.5
            * (value["hit"].box_xyxy[1] + value["hit"].box_xyxy[3]),
        ):
            cy = 0.5 * (row["hit"].box_xyxy[1] + row["hit"].box_xyxy[3])
            if bands:
                prior_cy = float(np.median([
                    0.5 * (value["hit"].box_xyxy[1] + value["hit"].box_xyxy[3])
                    for value in bands[-1]
                ]))
            else:
                prior_cy = -1e9
            if bands and abs(cy - prior_cy) <= 0.05 * float(frame_h):
                bands[-1].append(row)
            else:
                bands.append([row])
        for band in bands:
            boxes = [value["hit"].box_xyxy for value in band]
            best = max(
                band,
                key=lambda value: (
                    float(value["confidence"]),
                    float(value["hit"].sharpness),
                ),
            )
            normalized.append(
                {
                    "frame_index": frame_index,
                    "box": [
                        min(float(box[0]) for box in boxes),
                        min(float(box[1]) for box in boxes),
                        max(float(box[2]) for box in boxes),
                        max(float(box[3]) for box in boxes),
                    ],
                    "sharpness": max(float(value["hit"].sharpness) for value in band),
                    "text": str(best["text"]),
                    "confidence": float(best["confidence"]),
                }
            )

    clusters: list[list[dict[str, Any]]] = []
    for row in normalized:
        box = row["box"]
        cx = 0.5 * (box[0] + box[2])
        cy = 0.5 * (box[1] + box[3])
        match: list[dict[str, Any]] | None = None
        for cluster in reversed(clusters):
            prior = cluster[-1]
            if int(row["frame_index"]) - int(prior["frame_index"]) > RESIDUAL_HARDSUB_MAX_FRAME_GAP:
                continue
            prior_box = prior["box"]
            prior_cx = 0.5 * (prior_box[0] + prior_box[2])
            prior_cy = 0.5 * (prior_box[1] + prior_box[3])
            overlap = max(0.0, min(box[2], prior_box[2]) - max(box[0], prior_box[0]))
            shorter = max(1.0, min(box[2] - box[0], prior_box[2] - prior_box[0]))
            if (
                abs(cy - prior_cy) <= 0.06 * float(frame_h)
                and (
                    overlap / shorter >= 0.15
                    or abs(cx - prior_cx) <= 0.25 * float(frame_w)
                )
            ):
                match = cluster
                break
        if match is None:
            clusters.append([row])
        else:
            match.append(row)

    recovered: list[MergedTrack] = []
    for cluster in clusters:
        frames = sorted({int(row["frame_index"]) for row in cluster})
        if len(frames) < RESIDUAL_HARDSUB_MIN_FRAMES:
            unresolved_frames.update(frames)
            continue
        boxes = [list(row["box"]) for row in cluster]
        sharpness = [float(row["sharpness"]) for row in cluster]
        best_index = max(range(len(cluster)), key=lambda index: sharpness[index])
        recovered_box = [
            max(0.0, min(float(box[0]) for box in boxes)),
            max(0.0, min(float(box[1]) for box in boxes)),
            min(float(frame_w), max(float(box[2]) for box in boxes)),
            min(float(frame_h), max(float(box[3]) for box in boxes)),
        ]
        track = MergedTrack(
            start_frame=frames[0],
            end_frame=frames[-1],
            box_coords=recovered_box,
            best_frame_index=int(cluster[best_index]["frame_index"]),
            best_sharpness=sharpness[best_index],
            centroid=_box_centroid(recovered_box),
            hit_count=len(cluster),
            hit_boxes=[tuple(float(value) for value in row["box"]) for row in cluster],
            hit_frames=[int(row["frame_index"]) for row in cluster],
            hit_sharpness=sharpness,
        )
        recovered.append(track)
        audit["recovered_tracks"].append(
            {
                "span": [frames[0], frames[-1]],
                "box": [round(float(value), 3) for value in recovered_box],
                "hit_count": len(cluster),
                "recognition_samples": sorted(
                    {
                        str(row["text"])
                        for row in cluster
                        if str(row.get("text") or "")
                    }
                )[:5],
            }
        )

    output = [*tracks, *recovered]
    output.sort(key=lambda track: (int(track.start_frame), float(track.box_coords[0])))
    audit["explained_shadow_frames"] = sorted(explained_frames)
    audit["unresolved_frames"] = sorted(unresolved_frames)
    audit["unresolved_spans"] = _frame_spans(sorted(unresolved_frames))
    audit["recovered_track_count"] = len(recovered)
    return output, audit


def purge_unverified_sparse_compact_tracks_after_refinement(
    tracks: Sequence[MergedTrack],
    *,
    frame_cache: Mapping[int, np.ndarray],
    frame_w: int,
    frame_h: int,
    recognizer: Any | None,
    source: Path | None = None,
    batch_size: int = 32,
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """Recheck sparse compact candidates after their geometry is final.

    Content segmentation runs before template/ink geometry refinement. A scene
    texture can therefore be too large for the compact guard initially, then
    shrink into a compact uncertain track later. This final guard uses no
    scene position, colour, or source-specific cue: it requires stable local
    text consensus spanning the detector-backed lifespan of every sparse,
    compact mid-label/UI candidate. Recognizer failure always keeps the track
    for operator review.
    """
    audit: dict[str, Any] = {
        "method": POST_REFINEMENT_SPARSE_COMPACT_POLICY_VERSION,
        "recognizer_available": recognizer is not None,
        "before_count": len(tracks),
        "after_count": len(tracks),
        "candidate_count": 0,
        "dropped_tracks": 0,
        "rows": [],
    }
    if recognizer is None:
        return list(tracks), audit

    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    kept: list[MergedTrack] = []
    for track in tracks:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        evidence = track_boundary_evidence(
            track, frame_w=frame_w, frame_h=frame_h
        )
        reasons = set(evidence.get("reasons") or [])
        x0, y0, x1, y1 = (float(value) for value in track.box_coords[:4])
        width_frac = max(0.0, x1 - x0) / fw
        height_frac = max(0.0, y1 - y0) / fh
        candidate = (
            role in {"mid_label", "ui_chip"}
            and "sparse_temporal_evidence" in reasons
            and width_frac <= POST_REFINEMENT_SPARSE_COMPACT_MAX_WIDTH_FRAC
            and height_frac <= POST_REFINEMENT_SPARSE_COMPACT_MAX_HEIGHT_FRAC
            and int(track.end_frame) > int(track.start_frame)
        )
        if not candidate:
            kept.append(track)
            continue

        audit["candidate_count"] += 1
        row: dict[str, Any] = {
            "prior_span": [int(track.start_frame), int(track.end_frame)],
            "role": role,
            "geometry_size_frac": [round(width_frac, 4), round(height_frac, 4)],
            "boundary_reasons": sorted(reasons),
            "frames_attempted": 0,
            "accepted_recognitions": 0,
            "clusters": [],
            "action": "keep_for_review",
        }
        frame_indices: list[int] = []
        crops: list[np.ndarray] = []
        for frame_index in range(
            int(track.start_frame), int(track.end_frame) + 1
        ):
            frame = _boundary_frame(
                frame_index, frame_cache=frame_cache, source=source
            )
            crop = (
                _crop_xyxy_from_frame(frame, track.box_coords)
                if frame is not None
                else None
            )
            if crop is None or crop.size < 16:
                continue
            frame_indices.append(frame_index)
            crops.append(crop)
        row["frames_attempted"] = len(crops)

        normalized_visual_crops: list[np.ndarray] = []
        for crop in crops:
            crop_height = max(1, int(crop.shape[0]))
            scale = POST_REFINEMENT_VISUAL_NORMALIZED_HEIGHT / float(crop_height)
            normalized_visual_crops.append(
                cv2.resize(
                    crop,
                    (
                        max(1, int(round(float(crop.shape[1]) * scale))),
                        POST_REFINEMENT_VISUAL_NORMALIZED_HEIGHT,
                    ),
                    interpolation=(
                        cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA
                    ),
                )
            )
        laplacian_values: list[float] = []
        edge_density_values: list[float] = []
        saturation_values: list[float] = []
        for crop in normalized_visual_crops:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            edges = cv2.Canny(gray, 80, 160)
            laplacian_values.append(
                float(cv2.Laplacian(gray, cv2.CV_64F).var())
            )
            edge_density_values.append(float(np.count_nonzero(edges)) / edges.size)
            saturation_values.append(float(np.mean(hsv[:, :, 1])))
        visual_evidence = {
            "normalized_height": POST_REFINEMENT_VISUAL_NORMALIZED_HEIGHT,
            "median_laplacian_variance": round(
                float(np.median(laplacian_values)) if laplacian_values else 0.0,
                4,
            ),
            "median_edge_density": round(
                float(np.median(edge_density_values))
                if edge_density_values
                else 0.0,
                4,
            ),
            "median_saturation": round(
                float(np.median(saturation_values)) if saturation_values else 0.0,
                4,
            ),
        }
        low_detail_saturated_texture = (
            bool(normalized_visual_crops)
            and visual_evidence["median_laplacian_variance"]
            < POST_REFINEMENT_TEXTURE_MAX_LAPLACIAN_VARIANCE
            and visual_evidence["median_edge_density"]
            < POST_REFINEMENT_TEXTURE_MAX_EDGE_DENSITY
            and visual_evidence["median_saturation"]
            >= POST_REFINEMENT_TEXTURE_MIN_SATURATION
        )
        visual_evidence["low_detail_saturated_texture"] = (
            low_detail_saturated_texture
        )
        row["visual_evidence"] = visual_evidence

        recognitions: list[Any] = []
        try:
            size = max(1, int(batch_size))
            for offset in range(0, len(crops), size):
                batch = crops[offset : offset + size]
                results = list(recognizer.recognize_batch(batch))
                if len(results) != len(batch):
                    raise RuntimeError(
                        "local recognizer batch size mismatch "
                        f"input={len(batch)} output={len(results)}"
                    )
                recognitions.extend(results)
        except Exception as exc:  # noqa: BLE001
            row["reason"] = "recognizer_error_fail_soft"
            row["error"] = str(exc)
            audit["rows"].append(row)
            kept.append(track)
            continue

        clusters: list[dict[str, Any]] = []
        for frame_index, recognition in zip(frame_indices, recognitions):
            if not local_text_accepts_track(recognition, role=role):
                continue
            text = str(getattr(recognition, "text", "") or "").strip()
            signature = _local_text_timing_signature(text)
            if not signature:
                continue
            matching = next(
                (
                    cluster
                    for cluster in clusters
                    if _local_text_signatures_match(
                        signature, str(cluster["signature"])
                    )
                    or _measurement_label_ocr_variants_match(
                        text, str(cluster["representative_text"])
                    )
                ),
                None,
            )
            if matching is None:
                matching = {
                    "signature": signature,
                    "representative_text": text,
                    "frames": [],
                }
                clusters.append(matching)
            matching["frames"].append(int(frame_index))

        row["accepted_recognitions"] = sum(
            len(list(cluster["frames"])) for cluster in clusters
        )
        track_span = max(1, int(track.end_frame) - int(track.start_frame) + 1)
        detector_frames = {int(value) for value in track.hit_frames}
        stable_consensus = False
        for cluster in clusters:
            frames = sorted({int(value) for value in cluster["frames"]})
            support = len(frames)
            cluster_span = max(1, frames[-1] - frames[0] + 1)
            density = support / float(cluster_span)
            lifespan_coverage = cluster_span / float(track_span)
            detector_overlap = len(detector_frames.intersection(frames))
            stable = (
                support >= 2
                and density >= 0.60
                and lifespan_coverage >= 0.50
                and detector_overlap >= 2
            )
            row["clusters"].append(
                {
                    "representative_text": str(cluster["representative_text"]),
                    "signature": str(cluster["signature"]),
                    "support": support,
                    "span": [frames[0], frames[-1]],
                    "density": round(density, 4),
                    "lifespan_coverage": round(lifespan_coverage, 4),
                    "detector_overlap": detector_overlap,
                    "stable": stable,
                }
            )
            stable_consensus = stable_consensus or stable

        if stable_consensus and not low_detail_saturated_texture:
            row["action"] = "keep_stable_text_consensus"
            row["reason"] = "detector_backed_multiframe_text_consensus"
            kept.append(track)
        else:
            row["action"] = "drop_unverified_sparse_compact_after_refinement"
            row["reason"] = (
                "independent_low_detail_saturated_texture_veto"
                if low_detail_saturated_texture
                else "no_stable_detector_backed_text_consensus"
            )
            audit["dropped_tracks"] += 1
        audit["rows"].append(row)

    audit["after_count"] = len(kept)
    return kept, audit


def _is_valid_pixel_box(xyxy: Sequence[float]) -> bool:
    x0, y0, x1, y1 = (float(v) for v in xyxy)
    w = x1 - x0
    h = y1 - y0
    if w < MIN_BOX_WIDTH_PX or h < MIN_BOX_HEIGHT_PX:
        return False
    aspect = w / max(h, 1e-6)
    if aspect > MAX_BOX_ASPECT or aspect < 0.15:
        return False
    return True


def is_plausible_text_box(
    xyxy: Sequence[float],
    *,
    frame_w: int,
    frame_h: int,
) -> bool:
    """Geometry gate: drop endcards / huge UI while keeping hardsub + mid labels."""
    if not _is_valid_pixel_box(xyxy):
        return False
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    w = x1 - x0
    h = y1 - y0
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    if (w * h) > (MAX_BOX_AREA_FRAC * fw * fh):
        return False
    if h > (MAX_BOX_HEIGHT_FRAC * fh):
        return False
    # Near-full width: only thin bottom hardsub lines (post-expand) may pass.
    if w > (MAX_BOX_WIDTH_FRAC * fw):
        return False
    if w > (STRICT_BOX_WIDTH_FRAC * fw):
        cy = ((y0 + y1) * 0.5) / fh
        if cy < HARDSUB_BAND_CY or h > (THIN_HARDSUB_HEIGHT_FRAC * fh):
            return False
    return True


def min_hits_for_role(role: str) -> int:
    """Role-aware temporal stability: texture flicker dies; hardsub lines stay."""
    if role == "hardsub":
        # Short burn-ins + STEP sampling often land only 2 dense hits; band-ink
        # recovery + OCR still confirm the line.
        return 2
    # mid_label / ui_chip / generic — allow short editor chips (n=3–4);
    # 1–2-hit texture flicker still drops.
    return 3


# Editor burn-in stays column-locked; packaging / scene text drifts in X with the
# object. Y-only σ is ignored (multi-line over-merge / stacked list rows).
# Looser than 1.8%: fixed UI labels jitter in X from partial DBNet widths.
EDITOR_CENTROID_SIGMA_FRAC = 0.026
EDITOR_CENTROID_SIGMA_MIN_PX = 18.0


def _robust_std(vals: Sequence[float]) -> float:
    """MAD-based robust stddev (outlier-tolerant)."""
    if len(vals) < 2:
        return 0.0
    arr = np.asarray(list(vals), dtype=np.float64)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    return float(1.4826 * mad)


def track_centroid_sigma_xy(track: MergedTrack) -> tuple[float, float]:
    """Per-axis robust centroid σ (pixels) across hit boxes."""
    boxes = list(track.hit_boxes or ())
    if len(boxes) < 2:
        return 0.0, 0.0
    xs: list[float] = []
    ys: list[float] = []
    for box in boxes:
        cx, cy = _box_centroid(box)
        xs.append(float(cx))
        ys.append(float(cy))
    return _robust_std(xs), _robust_std(ys)


def editor_centroid_sigma_limit_px(*, frame_w: int, frame_h: int) -> float:
    return max(
        float(EDITOR_CENTROID_SIGMA_MIN_PX),
        float(EDITOR_CENTROID_SIGMA_FRAC) * min(float(frame_w), float(frame_h)),
    )


def is_horizontally_locked_track(
    track: MergedTrack,
    *,
    frame_w: int,
    frame_h: int,
) -> bool:
    """True when hit centroids do not drift horizontally (burn-in / list column)."""
    lim = editor_centroid_sigma_limit_px(frame_w=frame_w, frame_h=frame_h)
    sx, sy = track_centroid_sigma_xy(track)
    if sx <= lim:
        return True
    # Wide fixed UI labels (碳水化合物): DBNet partial-width flicker inflates
    # σ_x while Y stays glued. Allow σ_x up to a fraction of median width when
    # the track is dense and σ_y stays within the editor lock.
    boxes = list(track.hit_boxes or ())
    if len(boxes) < 5 or sy > lim:
        return False
    widths = [max(1.0, float(b[2]) - float(b[0])) for b in boxes]
    med_w = float(np.median(np.asarray(widths, dtype=np.float64)))
    return sx <= max(lim, 0.18 * med_w)


def sequential_caption_lane_member_ids(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
) -> set[int]:
    """Infer editor caption lanes above the legacy bottom-subtitle strip.

    Caption sentences replace one another at nearly one Y locus.  Source UI
    rows instead coexist in a two-dimensional panel or remain persistent.
    Requiring at least three line-like, screen-locked, mostly non-overlapping
    epochs prevents a single package label or an endcard table row from opening
    this authority.
    """

    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))

    def eligible(track: MergedTrack) -> bool:
        x0, y0, x1, y1 = (float(value) for value in track.box_coords[:4])
        width = max(1.0, x1 - x0)
        height = max(1.0, y1 - y0)
        cy = 0.5 * (y0 + y1) / fh
        return bool(
            CAPTION_LANE_MIN_CY <= cy < CAPTION_LANE_MAX_CY
            and width / fw >= CAPTION_LANE_MIN_WIDTH_FRAC
            and height / fh <= CAPTION_LANE_MAX_HEIGHT_FRAC
            and width / height >= HARDSUB_MIN_ASPECT
            and int(track.hit_count) >= 2
            and is_horizontally_locked_track(
                track, frame_w=frame_w, frame_h=frame_h
            )
        )

    candidates = [track for track in tracks if eligible(track)]
    if len(candidates) < CAPTION_LANE_MIN_MEMBERS:
        return set()

    parents = list(range(len(candidates)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left_index, left in enumerate(candidates):
        left_cy = 0.5 * (
            float(left.box_coords[1]) + float(left.box_coords[3])
        ) / fh
        for right_index in range(left_index + 1, len(candidates)):
            right = candidates[right_index]
            right_cy = 0.5 * (
                float(right.box_coords[1]) + float(right.box_coords[3])
            ) / fh
            if abs(left_cy - right_cy) > CAPTION_LANE_MAX_CY_DELTA_FRAC:
                continue
            left_width = max(
                1.0, float(left.box_coords[2]) - float(left.box_coords[0])
            )
            right_width = max(
                1.0, float(right.box_coords[2]) - float(right.box_coords[0])
            )
            horizontal = max(
                0.0,
                min(float(left.box_coords[2]), float(right.box_coords[2]))
                - max(float(left.box_coords[0]), float(right.box_coords[0])),
            )
            if horizontal / min(left_width, right_width) < 0.40:
                continue
            union(left_index, right_index)

    groups: dict[int, list[MergedTrack]] = defaultdict(list)
    for index, track in enumerate(candidates):
        groups[find(index)].append(track)

    members: set[int] = set()
    for group in groups.values():
        if len(group) < CAPTION_LANE_MIN_MEMBERS:
            continue
        ordered = sorted(group, key=lambda row: (row.start_frame, row.end_frame))
        duration_sum = sum(
            max(1, int(row.end_frame) - int(row.start_frame) + 1)
            for row in ordered
        )
        overlap_sum = 0
        transition_pairs = 0
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                overlap = max(
                    0,
                    min(int(left.end_frame), int(right.end_frame))
                    - max(int(left.start_frame), int(right.start_frame))
                    + 1,
                )
                overlap_sum += overlap
                if (
                    int(right.start_frame) >= int(left.end_frame) - 2
                    and int(right.start_frame) - int(left.end_frame) <= 45
                ):
                    transition_pairs += 1
        if overlap_sum / float(max(1, duration_sum)) > CAPTION_LANE_MAX_OVERLAP_RATIO:
            continue
        if transition_pairs < min(2, len(group) - 1):
            continue
        members.update(id(track) for track in group)
    return members


def is_editor_overlay_track(
    track: MergedTrack,
    *,
    role: str,
    frame_w: int,
    frame_h: int,
    has_stable_column_peer: bool = False,
) -> bool:
    """
    True when the track looks like editor-added burn-in (not in-scene print).

    Hardsubs (and near-bottom generic lines) always keep. Mid/ui keep when
    horizontally locked and hits ≥ role min or a locked column peer exists.
    Horizontal centroid drift → scene packaging / hand-held text.
    """
    if role == "hardsub":
        return True
    # Near-bottom wide lines often classify as generic (cy just under hardsub).
    y0, y1 = float(track.box_coords[1]), float(track.box_coords[3])
    cy = ((y0 + y1) * 0.5) / max(1.0, float(frame_h))
    if role == "generic" and cy >= 0.74:
        return True

    if not is_horizontally_locked_track(
        track, frame_w=frame_w, frame_h=frame_h
    ):
        return False

    hits = int(track.hit_count)
    if hits >= min_hits_for_role(role):
        return True
    if has_stable_column_peer and hits >= 3:
        return True
    return False


# Compact mid/ui glyphs on a fixed product panel stay X-locked under a locked
# camera, so centroid-σ alone cannot separate them from editor burn-in.
# Concurrent clusters of tiny chips are treated as in-scene device/packaging UI.
COMPACT_SCENE_UI_W_FRAC = 0.06
COMPACT_SCENE_UI_H_FRAC = 0.06
COMPACT_SCENE_UI_MAX_ASPECT = 3.2
COMPACT_SCENE_UI_MIN_CY = 0.30
COMPACT_SCENE_UI_MAX_CY = 0.78
# Need a denser panel before dropping — pairs of editor chips must survive.
COMPACT_SCENE_UI_MIN_CLUSTER = 4
COMPACT_SCENE_UI_PAIR_DIST_FRAC = 0.55
# Wide locked mid/generic on the same window → compact chips are editor-card peers.
EDITOR_CARD_ANCHOR_W_FRAC = 0.08
# A single tiny locked crop is ambiguous: it can be appliance/package print or
# a food highlight just as easily as an editor chip. It needs independent
# editor-layout context before entering the geometry SSOT.
ISOLATED_MICRO_SOURCE_W_FRAC = 0.042
ISOLATED_MICRO_SOURCE_H_FRAC = 0.036
ISOLATED_MICRO_PEER_OVERLAP = 0.75
ISOLATED_MICRO_ANCHOR_OVERLAP = 0.60
ISOLATED_MICRO_PEER_DIST_FRAC = 0.65


def is_compact_scene_ui_chip(
    xyxy: Sequence[float],
    *,
    role: str,
    frame_w: int,
    frame_h: int,
) -> bool:
    """True for tiny mid/ui chips typical of in-scene device / packaging faces."""
    if role not in {"mid_label", "ui_chip"}:
        return False
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    w = max(1.0, x1 - x0)
    h = max(1.0, y1 - y0)
    cy = ((y0 + y1) * 0.5) / fh
    aspect = w / h
    if cy < COMPACT_SCENE_UI_MIN_CY or cy > COMPACT_SCENE_UI_MAX_CY:
        return False
    if (w / fw) > COMPACT_SCENE_UI_W_FRAC:
        return False
    if (h / fh) > COMPACT_SCENE_UI_H_FRAC:
        return False
    if aspect > COMPACT_SCENE_UI_MAX_ASPECT:
        return False
    return True


def _tracks_time_overlap(a: MergedTrack, b: MergedTrack) -> bool:
    return not (
        int(a.end_frame) < int(b.start_frame)
        or int(b.end_frame) < int(a.start_frame)
    )


def _track_overlaps_span(
    track: MergedTrack, *, start: int, end: int
) -> bool:
    return not (int(track.end_frame) < start or end < int(track.start_frame))


def is_editor_card_anchor_track(
    track: MergedTrack,
    *,
    frame_w: int,
    frame_h: int,
) -> bool:
    """
    Wide locked mid/ui/generic burn-in (nutrition card titles, list headers).

    Hardsubs are excluded — they span most of the video and must not exempt
    mid-clip device-panel clusters.
    """
    role = classify_ocr_box_role(
        track.box_coords, frame_w=frame_w, frame_h=frame_h
    )
    if role == "hardsub":
        return False
    if role not in {"mid_label", "ui_chip", "generic"}:
        return False
    if is_compact_scene_ui_chip(
        track.box_coords,
        role=role,
        frame_w=frame_w,
        frame_h=frame_h,
    ):
        return False
    x0, _, x1, _ = (float(v) for v in track.box_coords[:4])
    fw = max(1.0, float(frame_w))
    if (x1 - x0) / fw < EDITOR_CARD_ANCHOR_W_FRAC:
        return False
    return is_horizontally_locked_track(
        track, frame_w=frame_w, frame_h=frame_h
    )


def compact_scene_ui_cluster_member_ids(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
    anchor_tracks: Sequence[MergedTrack] | None = None,
) -> set[int]:
    """
    Object ids of compact mid/ui tracks that belong to a concurrent cluster.

    Edge when time overlaps and centroids are nearby (same panel / face).
    Connected component size ≥ COMPACT_SCENE_UI_MIN_CLUSTER → all members,
    unless a nearby wide editor-card mid in ``anchor_tracks`` overlaps
    (defaults to ``tracks``). Prefer anchors = already-surviving editor tracks
    so doomed scene blobs cannot exempt a device-panel cluster.
    """
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    pair_lim = COMPACT_SCENE_UI_PAIR_DIST_FRAC * min(fw, fh)
    candidates: list[int] = []
    centroids: list[tuple[float, float]] = []
    for i, track in enumerate(tracks):
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        if not is_compact_scene_ui_chip(
            track.box_coords,
            role=role,
            frame_w=frame_w,
            frame_h=frame_h,
        ):
            continue
        candidates.append(i)
        centroids.append(_box_centroid(track.box_coords))

    n = len(candidates)
    if n < COMPACT_SCENE_UI_MIN_CLUSTER:
        return set()

    parent = list(range(n))

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        ti = tracks[candidates[i]]
        cxi, cyi = centroids[i]
        for j in range(i + 1, n):
            tj = tracks[candidates[j]]
            if not _tracks_time_overlap(ti, tj):
                continue
            cxj, cyj = centroids[j]
            dist = ((cxi - cxj) ** 2 + (cyi - cyj) ** 2) ** 0.5
            if dist <= pair_lim:
                _union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(_find(i), []).append(candidates[i])

    anchor_pool = anchor_tracks if anchor_tracks is not None else tracks
    anchors = [
        t
        for t in anchor_pool
        if is_editor_card_anchor_track(t, frame_w=frame_w, frame_h=frame_h)
    ]

    out: set[int] = set()
    for members in groups.values():
        if len(members) < COMPACT_SCENE_UI_MIN_CLUSTER:
            continue
        c_start = min(int(tracks[i].start_frame) for i in members)
        c_end = max(int(tracks[i].end_frame) for i in members)
        member_cxy = [_box_centroid(tracks[i].box_coords) for i in members]

        def _anchor_near_cluster(anchor: MergedTrack) -> bool:
            if not _track_overlaps_span(anchor, start=c_start, end=c_end):
                return False
            acx, acy = _box_centroid(anchor.box_coords)
            for mx, my in member_cxy:
                dist = ((acx - mx) ** 2 + (acy - my) ** 2) ** 0.5
                if dist <= pair_lim:
                    return True
            return False

        if any(_anchor_near_cluster(a) for a in anchors):
            continue
        for idx in members:
            out.add(id(tracks[idx]))
    return out


def isolated_micro_source_text_member_ids(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
) -> set[int]:
    """Micro non-hardsubs lacking editor-layout evidence are source/scene text.

    Screen lock and stable OCR are insufficient provenance evidence: a static
    appliance label is equally locked. A micro track is accepted only when a
    concurrent non-compact editor-card anchor exists or another micro track
    forms the same temporal/spatial layout. Hardsubs are handled by their own
    strong line geometry and never enter this gate.
    """
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    peer_distance = ISOLATED_MICRO_PEER_DIST_FRAC * min(fw, fh)

    def _is_micro(track: MergedTrack) -> bool:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        if role == "hardsub":
            return False
        x0, y0, x1, y1 = (float(value) for value in track.box_coords[:4])
        return (
            max(1.0, x1 - x0) / fw <= ISOLATED_MICRO_SOURCE_W_FRAC
            and max(1.0, y1 - y0) / fh <= ISOLATED_MICRO_SOURCE_H_FRAC
        )

    def _overlap_ratio_of_shorter(left: MergedTrack, right: MergedTrack) -> float:
        overlap = max(
            0,
            min(int(left.end_frame), int(right.end_frame))
            - max(int(left.start_frame), int(right.start_frame))
            + 1,
        )
        shorter = max(
            1,
            min(
                int(left.end_frame) - int(left.start_frame) + 1,
                int(right.end_frame) - int(right.start_frame) + 1,
            ),
        )
        return overlap / float(shorter)

    micro_tracks = [track for track in tracks if _is_micro(track)]
    if not micro_tracks:
        return set()
    perspective_ui_ids = perspective_ui_provenance_member_ids(
        tracks,
        frame_w=frame_w,
        frame_h=frame_h,
    )
    anchors = [
        track
        for track in tracks
        if is_editor_card_anchor_track(
            track, frame_w=frame_w, frame_h=frame_h
        )
    ]
    isolated: set[int] = set()
    for track in micro_tracks:
        if id(track) in perspective_ui_ids:
            continue
        if any(
            _overlap_ratio_of_shorter(track, anchor)
            >= ISOLATED_MICRO_ANCHOR_OVERLAP
            for anchor in anchors
        ):
            continue
        tx, ty = _box_centroid(track.box_coords)
        has_layout_peer = False
        for peer in micro_tracks:
            if peer is track:
                continue
            if (
                _overlap_ratio_of_shorter(track, peer)
                < ISOLATED_MICRO_PEER_OVERLAP
            ):
                continue
            px, py = _box_centroid(peer.box_coords)
            if ((tx - px) ** 2 + (ty - py) ** 2) ** 0.5 <= peer_distance:
                has_layout_peer = True
                break
        if not has_layout_peer:
            isolated.add(id(track))
    return isolated


def perspective_ui_provenance_member_ids(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
) -> set[int]:
    """Micro tracks supported by a simultaneous, spatially broad UI layout.

    A moving phone/app screen can contain many small labels that are neither
    horizontally locked nor close enough to form the local peer pair used by
    the isolated-source guard.  Require a sizeable concurrent 2-D cohort and
    keep only candidates inside that cohort's envelope.  A lone appliance
    label has no such authority and remains isolated.
    """
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    supported: set[int] = set()

    def _temporal_gap(left: MergedTrack, right: MergedTrack) -> int:
        if _tracks_time_overlap(left, right):
            return 0
        return max(
            0,
            max(int(left.start_frame), int(right.start_frame))
            - min(int(left.end_frame), int(right.end_frame))
            - 1,
        )

    for candidate in tracks:
        role = classify_ocr_box_role(
            candidate.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        if role == "hardsub":
            continue
        start = int(candidate.start_frame)
        end = int(candidate.end_frame)
        span = max(1, end - start + 1)
        cohort: list[MergedTrack] = []
        for peer in tracks:
            peer_role = classify_ocr_box_role(
                peer.box_coords, frame_w=frame_w, frame_h=frame_h
            )
            if peer_role == "hardsub" or int(peer.hit_count) < 2:
                continue
            overlap = max(
                0,
                min(end, int(peer.end_frame))
                - max(start, int(peer.start_frame))
                + 1,
            )
            if overlap / float(span) < 0.50:
                continue
            cohort.append(peer)
        if len(cohort) >= PERSPECTIVE_UI_MIN_COHORT:
            centers = [_box_centroid(peer.box_coords) for peer in cohort]
            min_x = min(center[0] for center in centers)
            max_x = max(center[0] for center in centers)
            min_y = min(center[1] for center in centers)
            max_y = max(center[1] for center in centers)
            cx, cy = _box_centroid(candidate.box_coords)
            if (
                max_x - min_x >= PERSPECTIVE_UI_MIN_X_SPREAD_FRAC * fw
                and max_y - min_y >= PERSPECTIVE_UI_MIN_Y_SPREAD_FRAC * fh
                and min_x - 0.06 * fw <= cx <= max_x + 0.06 * fw
                and min_y - 0.06 * fh <= cy <= max_y + 0.06 * fh
            ):
                supported.add(id(candidate))
                continue

        # A phone can pan/rotate between adjacent shots, so a true micro UI
        # value may precede the dense perspective cohort by a few frames and
        # no longer share its absolute screen coordinates.  Require a nearby
        # four-track 2-D layout within one second; a lone appliance label (or
        # only a few nearby fragments) cannot establish this authority.
        scene_cohort: list[MergedTrack] = []
        for peer in tracks:
            if peer is candidate or int(peer.hit_count) < 2:
                continue
            peer_role = classify_ocr_box_role(
                peer.box_coords, frame_w=frame_w, frame_h=frame_h
            )
            if peer_role == "hardsub":
                continue
            if _temporal_gap(candidate, peer) > PERSPECTIVE_UI_SCENE_MAX_GAP_FRAMES:
                continue
            scene_cohort.append(peer)
        if len(scene_cohort) < PERSPECTIVE_UI_SCENE_MIN_COHORT:
            continue
        centers = [_box_centroid(peer.box_coords) for peer in scene_cohort]
        if (
            max(center[0] for center in centers)
            - min(center[0] for center in centers)
            < PERSPECTIVE_UI_SCENE_MIN_X_SPREAD_FRAC * fw
            or max(center[1] for center in centers)
            - min(center[1] for center in centers)
            < PERSPECTIVE_UI_SCENE_MIN_Y_SPREAD_FRAC * fh
        ):
            continue
        supported.add(id(candidate))
    return supported


_MEASURE_UNIT_RE = re.compile(
    r"(?:克|千卡|%|ml|mL|ML|[gG])\s*$"
)
_DIGITS_WITH_UNIT_RE = re.compile(
    r"^\d+(?:\.\d+)?\s*(?:克|%|千卡|ml|mL|ML|[gG])$"
)
_EMBEDDED_ASCII_MEASURE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:ml|mL|ML|[gG]|%)(?=\s|[\u4e00-\u9fff]|$)"
)


def _has_burnin_measure_unit(text: str) -> bool:
    """True for recipe units (克 / g / ml / % / 千卡), not bare Latin UI."""
    raw = str(text or "").strip()
    if not raw:
        return False
    return bool(
        _MEASURE_UNIT_RE.search(raw) or _EMBEDDED_ASCII_MEASURE_RE.search(raw)
    )


def local_text_accepts_track(
    recognition: Any,
    *,
    role: str,
    allow_latin_editor_card: bool = False,
    allow_latin_semantic_scene_label: bool = False,
    allow_bare_numeric_ui: bool = False,
) -> bool:
    """
    True when local recognizer evidence looks like on-screen copy.

    Drops Latin UI (TARE), bare scale digits, and low-confidence texture garbage.
    Keeps CJK labels, high-conf single-CJK chips (``虾``), and burn-in numeric UI
    including ASCII recipe units (``盐2g`` / ``15g``).
    """
    text = str(getattr(recognition, "text", "") or "").strip()
    confidence = float(getattr(recognition, "confidence", 0.0) or 0.0)
    valid_char_ratio = float(getattr(recognition, "valid_char_ratio", 0.0) or 0.0)
    if not text:
        return False
    cjk = _cjk_count(text)
    digits = sum(1 for ch in text if ch.isdigit())
    ascii_letters = sum(
        1 for ch in text if ("A" <= ch <= "Z") or ("a" <= ch <= "z")
    )
    # Appliance Latin-only (TARE / UNIT) — allow sole measure letter via unit regex.
    if ascii_letters >= 2 and cjk == 0 and not _has_burnin_measure_unit(text):
        # Latin-only copy is normally device/package UI (TARE / UNIT). It may
        # pass only when the caller independently proved a changing solid-color
        # editor-card layout across time. OCR confidence alone never opens this
        # path.
        if not allow_latin_editor_card and not allow_latin_semantic_scene_label:
            return False
        significant = sum(1 for char in text if char.isalnum())
        if allow_latin_semantic_scene_label:
            return (
                significant >= 4
                and confidence >= 0.90
                and valid_char_ratio >= 0.75
            )
        return (
            significant >= 3
            and confidence >= 0.78
            and valid_char_ratio >= 0.60
        )
    if cjk < 1:
        # Nutrition / calorie / gram chips burned into the frame — keep.
        if digits >= 1 and _DIGITS_WITH_UNIT_RE.fullmatch(text):
            return confidence >= 0.55
        if allow_bare_numeric_ui:
            compact = text.replace(" ", "")
            numeric = "".join(
                char for char in compact if char.isdigit() or char in {".", ","}
            )
            if digits >= 2 and len(numeric) == len(compact):
                return confidence >= 0.90 and valid_char_ratio >= 0.75
        # Bare scale digits / "0.g" — drop.
        return False
    if confidence < 0.40:
        return False
    if confidence < 0.55 and valid_char_ratio < 0.45:
        return False
    # Count substantive glyphs (ignore ，。· clutter). Texture OCR often
    # hallucinates ``一，`` on food bands — treat as weak single-chip.
    significant = sum(
        1
        for ch in text
        if ("\u4e00" <= ch <= "\u9fff") or ch.isdigit() or ch.isalpha()
    )
    if significant <= 1:
        if role == "hardsub":
            # Single-glyph burn-in (盐) on food — keep only when OCR is confident.
            return confidence >= 0.80
        if role == "ui_chip":
            # Real single-glyph chips (盐/虾) are high-conf; food texture often
            # hallucinates 福/一 around 0.70–0.80 — reject that mid band.
            return confidence >= 0.85
        return confidence >= 0.72
    if role == "hardsub":
        if cjk >= 1 and len(text) >= 2:
            return True
        if cjk >= 1 and confidence >= 0.75:
            return True
        return digits >= 1 and _has_burnin_measure_unit(text)
    if role == "mid_label":
        if cjk >= 1 and len(text) <= 16:
            return True
        return False
    if role == "ui_chip":
        # CJK + optional ASCII unit (盐2g) — keep. Pure Latin still dropped above.
        if cjk >= 1 and (ascii_letters == 0 or _has_burnin_measure_unit(text)):
            return True
        if digits >= 1 and _has_burnin_measure_unit(text):
            return True
        return False
    return cjk >= 1 or digits >= 1


def has_solid_colored_editor_panel(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
) -> bool:
    """Detect saturated, spatially coherent card fill around a text line.

    This is only supporting evidence for the Latin editor-card path. A single
    positive crop is insufficient; ``filter_tracks_by_local_text`` also
    requires a non-overlapping temporal peer at the same layout locus.
    """
    if frame_bgr is None or getattr(frame_bgr, "size", 0) <= 0:
        return False
    fh, fw = frame_bgr.shape[:2]
    x0, y0, x1, y1 = (float(value) for value in xyxy[:4])
    line_w = max(1.0, x1 - x0)
    line_h = max(1.0, y1 - y0)
    pad_x = max(4, int(round(0.04 * line_w)))
    pad_y = max(4, int(round(0.45 * line_h)))
    ix0 = max(0, int(round(x0)) - pad_x)
    iy0 = max(0, int(round(y0)) - pad_y)
    ix1 = min(fw, int(round(x1)) + pad_x)
    iy1 = min(fh, int(round(y1)) + pad_y)
    if ix1 - ix0 < 8 or iy1 - iy0 < 8:
        return False
    crop = frame_bgr[iy0:iy1, ix0:ix1]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    colored = (saturation >= 70) & (value >= 28)
    if float(np.mean(colored)) < 0.34:
        return False
    border = np.concatenate(
        (
            colored[0, :],
            colored[-1, :],
            colored[:, 0],
            colored[:, -1],
        )
    )
    if float(np.mean(border)) < 0.30:
        return False
    hues = hsv[:, :, 0][colored]
    if hues.size < 24:
        return False
    histogram, _ = np.histogram(hues, bins=18, range=(0, 180))
    dominant = int(np.argmax(histogram))
    if float(histogram[dominant]) / float(hues.size) < 0.62:
        return False
    low = dominant * 10
    high = low + 10
    dominant_mask = colored & (hsv[:, :, 0] >= low) & (hsv[:, :, 0] < high)
    dominant_values = value[dominant_mask]
    return bool(
        dominant_values.size >= 24
        and float(np.std(dominant_values.astype(np.float32))) <= 58.0
    )


def has_solid_neutral_editor_panel(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
) -> bool:
    """Detect a coherent black/white/grey editor card behind one text row.

    Editor callouts are commonly neutral rather than saturated (black product
    comparison cards are a frequent example).  The coloured-panel detector
    intentionally rejects those cards.  This companion detector is kept
    conservative: most of the padded row and its border must share one neutral
    luminance class.  It is supporting *group* evidence only; no track becomes
    editor-authored from this predicate alone.
    """

    if frame_bgr is None or getattr(frame_bgr, "size", 0) <= 0:
        return False
    frame_h, frame_w = frame_bgr.shape[:2]
    x0, y0, x1, y1 = (float(value) for value in xyxy[:4])
    line_w = max(1.0, x1 - x0)
    line_h = max(1.0, y1 - y0)
    pad_x = max(4, int(round(0.08 * line_w)))
    pad_y = max(4, int(round(0.45 * line_h)))
    ix0 = max(0, int(round(x0)) - pad_x)
    iy0 = max(0, int(round(y0)) - pad_y)
    ix1 = min(frame_w, int(round(x1)) + pad_x)
    iy1 = min(frame_h, int(round(y1)) + pad_y)
    if ix1 - ix0 < 8 or iy1 - iy0 < 8:
        return False
    crop = frame_bgr[iy0:iy1, ix0:ix1]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    neutral = saturation <= 48
    dark = neutral & (value <= 78)
    light = neutral & (value >= 178)
    candidates = (dark, light)
    for coherent in candidates:
        if float(np.mean(coherent)) < 0.52:
            continue
        border = np.concatenate(
            (coherent[0, :], coherent[-1, :], coherent[:, 0], coherent[:, -1])
        )
        if float(np.mean(border)) < 0.72:
            continue
        values = value[coherent]
        if values.size >= 32 and float(np.std(values.astype(np.float32))) <= 42.0:
            return True
    return False


def neutral_editor_panel_bounds(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
) -> list[float] | None:
    """Return the containing neutral-card rectangle for a proven row.

    The rectangle is derived from the current frame, never from a hard-coded
    lane.  It is deliberately unavailable unless the row already satisfies
    the conservative neutral-panel predicate.  This lets Phase 1 preserve one
    physical editor-card envelope through Phase 4 without turning a caption
    into several independently blurred OCR fragments.
    """

    if not has_solid_neutral_editor_panel(frame_bgr, xyxy):
        return None
    frame_h, frame_w = frame_bgr.shape[:2]
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    neutral = hsv[:, :, 1] <= 55
    value = hsv[:, :, 2]
    line_x0, line_y0, line_x1, line_y1 = (
        float(value_) for value_ in xyxy[:4]
    )
    # The line centre can land on a bright glyph. Select the dominant neutral
    # surface class from a padded row region instead of one pixel.
    pad_x = max(4, int(round((line_x1 - line_x0) * 0.08)))
    pad_y = max(4, int(round((line_y1 - line_y0) * 0.45)))
    sample = (
        max(0, int(round(line_y0)) - pad_y),
        min(frame_h, int(round(line_y1)) + pad_y),
        max(0, int(round(line_x0)) - pad_x),
        min(frame_w, int(round(line_x1)) + pad_x),
    )
    sy0, sy1, sx0, sx1 = sample
    sample_neutral = neutral[sy0:sy1, sx0:sx1]
    sample_value = value[sy0:sy1, sx0:sx1]
    dark_fraction = float(np.mean(sample_neutral & (sample_value <= 88)))
    light_fraction = float(np.mean(sample_neutral & (sample_value >= 168)))
    mode_dark = dark_fraction >= light_fraction
    coherent = neutral & ((value <= 88) if mode_dark else (value >= 168))
    coherent = cv2.morphologyEx(
        coherent.astype(np.uint8) * 255,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (13, 7)),
    )
    count, labels, stats, _ = cv2.connectedComponentsWithStats(coherent, 8)
    line_area = max(1.0, (line_x1 - line_x0) * (line_y1 - line_y0))
    best: tuple[float, list[float]] | None = None
    for label in range(1, count):
        x, y, width, height, area = (int(v) for v in stats[label])
        x1, y1 = x + width, y + height
        intersection = max(0.0, min(float(x1), line_x1) - max(float(x), line_x0)) * max(
            0.0, min(float(y1), line_y1) - max(float(y), line_y0)
        )
        if intersection / line_area < 0.65:
            continue
        component_area = max(1, width * height)
        fill = float(area) / float(component_area)
        if fill < 0.52 or width < (line_x1 - line_x0) * 0.85:
            continue
        area_fraction = component_area / float(max(1, frame_w * frame_h))
        if area_fraction > 0.18 or height / float(max(1, frame_h)) > 0.22:
            continue
        score = intersection / line_area + min(1.0, fill)
        candidate = [float(x), float(y), float(x1), float(y1)]
        if best is None or score > best[0]:
            best = (score, candidate)
    return None if best is None else best[1]


def editor_card_panel_bounds(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
) -> list[float] | None:
    """Return a bounded solid editor-panel component containing the text row.

    Neutral cards use a luminance component. Saturated cards use the dominant
    hue component. This helper is only consumed after group provenance has an
    independent editor anchor, so it cannot promote arbitrary source pixels.
    """

    neutral_bounds = neutral_editor_panel_bounds(frame_bgr, xyxy)
    if neutral_bounds is not None:
        return neutral_bounds
    if not has_solid_colored_editor_panel(frame_bgr, xyxy):
        return None
    frame_h, frame_w = frame_bgr.shape[:2]
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    x0, y0, x1, y1 = (float(value) for value in xyxy[:4])
    ix0, iy0 = max(0, int(x0)), max(0, int(y0))
    ix1, iy1 = min(frame_w, int(np.ceil(x1))), min(frame_h, int(np.ceil(y1)))
    sample = hsv[iy0:iy1, ix0:ix1]
    colored = sample[:, :, 1] >= 60
    hues = sample[:, :, 0][colored]
    if hues.size < 24:
        return None
    histogram, _ = np.histogram(hues, bins=18, range=(0, 180))
    dominant = int(np.argmax(histogram))
    hue_center = dominant * 10 + 5
    hue_delta = np.abs(hsv[:, :, 0].astype(np.int16) - hue_center)
    hue_delta = np.minimum(hue_delta, 180 - hue_delta)
    coherent = (
        (hue_delta <= 14)
        & (hsv[:, :, 1] >= 48)
        & (hsv[:, :, 2] >= 24)
    ).astype(np.uint8) * 255
    coherent = cv2.morphologyEx(
        coherent,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (13, 7)),
    )
    count, _labels, stats, _ = cv2.connectedComponentsWithStats(coherent, 8)
    line_area = max(1.0, (x1 - x0) * (y1 - y0))
    best: tuple[float, list[float]] | None = None
    for label in range(1, count):
        cx, cy, width, height, area = (int(value) for value in stats[label])
        cx1, cy1 = cx + width, cy + height
        intersection = max(0.0, min(float(cx1), x1) - max(float(cx), x0)) * max(
            0.0, min(float(cy1), y1) - max(float(cy), y0)
        )
        if intersection / line_area < 0.65:
            continue
        component_area = max(1, width * height)
        fill = float(area) / float(component_area)
        area_fraction = component_area / float(max(1, frame_w * frame_h))
        if fill < 0.48 or area_fraction > 0.18 or height / float(frame_h) > 0.22:
            continue
        score = intersection / line_area + fill
        candidate = [float(cx), float(cy), float(cx1), float(cy1)]
        if best is None or score > best[0]:
            best = (score, candidate)
    return None if best is None else best[1]


def semantic_scene_label_background_signature(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
) -> dict[str, float] | None:
    """Describe a coherent background surrounding a potential diagram label."""
    if frame_bgr is None or getattr(frame_bgr, "size", 0) <= 0:
        return None
    fh, fw = frame_bgr.shape[:2]
    x0, y0, x1, y1 = (float(value) for value in xyxy[:4])
    line_w = max(1.0, x1 - x0)
    line_h = max(1.0, y1 - y0)
    pad_x = max(6, int(round(0.12 * line_w)))
    pad_y = max(6, int(round(0.55 * line_h)))
    ix0 = max(0, int(round(x0)) - pad_x)
    iy0 = max(0, int(round(y0)) - pad_y)
    ix1 = min(fw, int(round(x1)) + pad_x)
    iy1 = min(fh, int(round(y1)) + pad_y)
    if ix1 - ix0 < 12 or iy1 - iy0 < 12:
        return None
    crop = frame_bgr[iy0:iy1, ix0:ix1]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    ch, cw = hsv.shape[:2]
    ring = np.ones((ch, cw), dtype=bool)
    inner_x0 = max(0, int(round(x0)) - ix0)
    inner_y0 = max(0, int(round(y0)) - iy0)
    inner_x1 = min(cw, int(round(x1)) - ix0)
    inner_y1 = min(ch, int(round(y1)) - iy0)
    ring[inner_y0:inner_y1, inner_x0:inner_x1] = False
    pixels = hsv[ring]
    if pixels.shape[0] < 64:
        return None
    saturation = pixels[:, 1].astype(np.float32)
    value = pixels[:, 2].astype(np.float32)
    median_saturation = float(np.median(saturation))
    median_value = float(np.median(value))
    if median_saturation >= 45.0:
        colored = pixels[saturation >= 35.0]
        if colored.shape[0] < 48:
            return None
        histogram, _ = np.histogram(colored[:, 0], bins=18, range=(0, 180))
        dominant = int(np.argmax(histogram))
        coherence = float(histogram[dominant]) / float(colored.shape[0])
        if coherence < 0.42:
            return None
        return {
            "hue": float(dominant * 10 + 5),
            "saturation": round(median_saturation, 3),
            "value": round(median_value, 3),
            "coherence": round(coherence, 4),
        }
    value_std = float(np.std(value))
    if value_std > 32.0:
        return None
    return {
        "hue": -1.0,
        "saturation": round(median_saturation, 3),
        "value": round(median_value, 3),
        "coherence": round(max(0.0, 1.0 - value_std / 32.0), 4),
    }


def _semantic_scene_backgrounds_are_distinct(
    left: Mapping[str, float], right: Mapping[str, float]
) -> bool:
    left_hue = float(left.get("hue", -1.0))
    right_hue = float(right.get("hue", -1.0))
    if left_hue >= 0.0 and right_hue >= 0.0:
        hue_delta = abs(left_hue - right_hue)
        hue_delta = min(hue_delta, 180.0 - hue_delta)
        if hue_delta >= 25.0:
            return True
    return abs(float(left.get("value", 0.0)) - float(right.get("value", 0.0))) >= 45.0


def _mid_column_bucket(
    box: Sequence[float],
    *,
    frame_w: int,
    bucket_frac: float = 0.05,
) -> int:
    cx = (float(box[0]) + float(box[2])) * 0.5
    step = max(1.0, float(frame_w) * float(bucket_frac))
    return int(cx // step)


def _rebuild_row_track_from_hit_indices(
    track: MergedTrack,
    indices: Sequence[int],
) -> MergedTrack:
    """Build a row track from a subset of parent hit indices."""
    boxes = [tuple(float(v) for v in track.hit_boxes[i][:4]) for i in indices]
    frames = [
        int(track.hit_frames[i]) if i < len(track.hit_frames) else int(track.best_frame_index)
        for i in indices
    ]
    sharps_src = track.hit_sharpness or [float(track.best_sharpness)] * len(
        track.hit_boxes
    )
    sharps = [
        float(sharps_src[i]) if i < len(sharps_src) else float(track.best_sharpness)
        for i in indices
    ]
    stable = stable_box_xyxy(boxes, expansive=False)
    best_i = int(max(range(len(sharps)), key=lambda j: sharps[j]))
    return MergedTrack(
        start_frame=min(frames) if frames else int(track.start_frame),
        end_frame=max(frames) if frames else int(track.end_frame),
        box_coords=list(stable),
        best_frame_index=frames[best_i] if frames else int(track.best_frame_index),
        best_sharpness=sharps[best_i] if sharps else float(track.best_sharpness),
        centroid=_box_centroid(stable),
        hit_count=len(boxes),
        hit_boxes=boxes,
        hit_frames=frames,
        hit_sharpness=sharps,
    )



def _inherit_parent_hit_density(
    rows: Sequence[MergedTrack],
    *,
    parent: MergedTrack,
) -> list[MergedTrack]:
    """Keep temporal density when a tall stable track is Y-split into rows."""
    parent_n = int(parent.hit_count)
    if parent_n < 5 or len(rows) < 2:
        return list(rows)
    parent_frames = list(parent.hit_frames) or [int(parent.best_frame_index)]
    parent_sharps = list(parent.hit_sharpness) or [float(parent.best_sharpness)]
    out: list[MergedTrack] = []
    for row in rows:
        # Share-bumped hit_count must not skip densify — row may still have
        # only 1–2 thin hit frames after a geometry split.
        if len(row.hit_frames) >= min(parent_n, 5) and int(row.hit_count) >= 5:
            out.append(row)
            continue
        box_t = tuple(float(v) for v in row.box_coords[:4])
        n_frames = max(1, len(parent_frames))
        out.append(
            MergedTrack(
                start_frame=int(parent.start_frame),
                end_frame=int(parent.end_frame),
                box_coords=list(row.box_coords),
                best_frame_index=int(row.best_frame_index),
                best_sharpness=float(row.best_sharpness),
                centroid=_box_centroid(row.box_coords),
                hit_count=parent_n,
                hit_boxes=[box_t] * n_frames,
                hit_frames=list(parent_frames),
                hit_sharpness=(
                    list(parent_sharps)[:n_frames]
                    if parent_sharps
                    else [float(parent.best_sharpness)] * n_frames
                ),
            )
        )
    return out


def split_mid_label_blob_by_hit_boxes(
    track: MergedTrack,
    *,
    frame_h: int,
    max_row_height_frac: float = 0.085,
    min_cluster_gap_frac: float = 0.028,
) -> list[MergedTrack] | None:
    """
    Split an over-merged tall mid track using thin hit-box Y clusters.

    Returns ``None`` when hit history cannot form ≥2 row clusters (caller may
    fall back to ink projection).
    """
    boxes = list(track.hit_boxes or ())
    if len(boxes) < 2:
        return None
    fh = max(1.0, float(frame_h))
    max_h_px = max(12.0, float(max_row_height_frac) * fh)
    parent_h = max(
        1.0, float(track.box_coords[3]) - float(track.box_coords[1])
    )
    # Prefer thin per-frame detections; ignore already-tall union hits that
    # sit between stacked rows and would glue clusters back together.
    thin: list[int] = []
    for i, box in enumerate(boxes):
        h = float(box[3]) - float(box[1])
        if h <= max_h_px * 1.25 and h <= parent_h * 0.78:
            thin.append(i)
    if len(thin) < 2:
        return None

    gap_thr = max(12.0, float(min_cluster_gap_frac) * fh)
    ordered = sorted(
        thin,
        key=lambda i: (float(boxes[i][1]) + float(boxes[i][3])) * 0.5,
    )
    clusters: list[list[int]] = [[ordered[0]]]
    for idx in ordered[1:]:
        prev = clusters[-1][-1]
        cy_prev = (float(boxes[prev][1]) + float(boxes[prev][3])) * 0.5
        cy = (float(boxes[idx][1]) + float(boxes[idx][3])) * 0.5
        if abs(cy - cy_prev) >= gap_thr:
            clusters.append([idx])
        else:
            clusters[-1].append(idx)

    # Keep clusters that look like text rows (enough hits, not still tall).
    kept_clusters: list[list[int]] = []
    for cluster in clusters:
        if len(cluster) < 1:
            continue
        row = _rebuild_row_track_from_hit_indices(track, cluster)
        rh = float(row.box_coords[3]) - float(row.box_coords[1])
        if rh > max_h_px * 1.25:
            continue
        kept_clusters.append(cluster)
    if len(kept_clusters) < 2:
        return None
    parent_n = max(1, int(track.hit_count))
    rows = [_rebuild_row_track_from_hit_indices(track, c) for c in kept_clusters]
    # Geometry split must not starve the local-text hit gate: each row inherits
    # a fair share of the parent track's temporal evidence.
    share = max(1, parent_n // len(rows))
    for row in rows:
        row.hit_count = max(int(row.hit_count), share)
    return rows


def _split_mid_blob_by_ink_projection(
    track: MergedTrack,
    frame_bgr: np.ndarray,
    *,
    frame_h: int,
    min_row_gap_px: int = 6,
    max_row_height_frac: float = 0.085,
) -> list[MergedTrack]:
    """Ink-row projection split; returns ``[track]`` if cannot split."""
    x0, y0, x1, y1 = (float(v) for v in track.box_coords[:4])
    fh = max(1.0, float(frame_h))
    ih, iw = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    ix0 = max(0, min(iw - 1, int(round(x0))))
    iy0 = max(0, min(ih - 1, int(round(y0))))
    ix1 = max(ix0 + 1, min(iw, int(round(x1))))
    iy1 = max(iy0 + 1, min(ih, int(round(y1))))
    crop = frame_bgr[iy0:iy1, ix0:ix1]
    if crop.size == 0 or crop.shape[0] < 12:
        return [track]

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    med = float(np.median(gray))
    ink = np.abs(gray.astype(np.float32) - med)
    thr = max(18.0, float(np.percentile(ink, 70)))
    row_score = ink.mean(axis=1)
    active = row_score >= thr
    ker = max(3, int(round(crop.shape[0] * 0.04)))
    if ker % 2 == 0:
        ker += 1
    active_u8 = active.astype(np.uint8) * 255
    active_u8 = cv2.morphologyEx(
        active_u8,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, ker)),
    )
    active = active_u8 > 0

    segments: list[tuple[int, int]] = []
    start: int | None = None
    gap = max(1, int(min_row_gap_px))
    i = 0
    n = int(active.shape[0])
    while i < n:
        if active[i]:
            if start is None:
                start = i
            i += 1
            continue
        if start is not None:
            j = i
            while j < n and j - i < gap and not active[j]:
                j += 1
            if j < n and active[j] and j - i < gap:
                i = j
                continue
            segments.append((start, i))
            start = None
        i += 1
    if start is not None:
        segments.append((start, n))

    max_h_px = max(12.0, float(max_row_height_frac) * fh)
    rows: list[tuple[float, float]] = []
    for a, b in segments:
        if b - a < 8:
            continue
        if (b - a) > max_h_px * 1.25:
            continue
        rows.append((float(iy0 + a), float(iy0 + b)))
    if len(rows) < 2:
        return [track]

    out: list[MergedTrack] = []
    for ry0, ry1 in rows:
        box = [x0, ry0, x1, ry1]
        out.append(
            MergedTrack(
                start_frame=int(track.start_frame),
                end_frame=int(track.end_frame),
                box_coords=box,
                best_frame_index=int(track.best_frame_index),
                best_sharpness=float(track.best_sharpness),
                centroid=_box_centroid(box),
                hit_count=int(track.hit_count),
                hit_boxes=[tuple(float(v) for v in box)],
                hit_frames=list(track.hit_frames) or [int(track.best_frame_index)],
                hit_sharpness=list(track.hit_sharpness)
                or [float(track.best_sharpness)],
            )
        )
    return out


def split_mid_label_blob_rows(
    track: MergedTrack,
    *,
    frame_bgr: np.ndarray | None,
    frame_h: int,
    frame_cache: Mapping[int, np.ndarray] | None = None,
    min_row_gap_px: int = 6,
    max_row_height_frac: float = 0.085,
) -> list[MergedTrack]:
    """
    Split a tall mid-label box into horizontal row tracks.

    Prefer hit-box Y clusters (works without a decoded frame), then ink
    projection on ``frame_bgr`` / any cached hit frame. Fail-soft: ``[track]``.
    """
    x0, y0, x1, y1 = (float(v) for v in track.box_coords[:4])
    fh = max(1.0, float(frame_h))
    box_h = max(1.0, y1 - y0)
    box_w = max(1.0, x1 - x0)
    aspect = box_w / box_h
    h_frac = box_h / fh
    # Narrow percent/value columns (21% / 40%) are often h/H≈0.07–0.084 —
    # still attempt a row split below the legacy tall-blob threshold.
    narrow_stack = aspect < 1.2 and h_frac > 0.055
    if h_frac <= float(max_row_height_frac) and not narrow_stack:
        return [track]

    by_hits = split_mid_label_blob_by_hit_boxes(
        track, frame_h=frame_h, max_row_height_frac=max_row_height_frac
    )
    if by_hits is not None and len(by_hits) >= 2:
        return _inherit_parent_hit_density(by_hits, parent=track)

    frames_to_try: list[np.ndarray] = []
    if frame_bgr is not None and getattr(frame_bgr, "size", 0) > 0:
        frames_to_try.append(frame_bgr)
    if frame_cache:
        seen: set[int] = set()
        for fi in [int(track.best_frame_index), *[int(f) for f in track.hit_frames]]:
            if fi in seen:
                continue
            seen.add(fi)
            cached = frame_cache.get(fi)
            if cached is not None and getattr(cached, "size", 0) > 0:
                frames_to_try.append(cached)

    for frame in frames_to_try:
        rows = _split_mid_blob_by_ink_projection(
            track,
            frame,
            frame_h=frame_h,
            min_row_gap_px=min_row_gap_px,
            max_row_height_frac=max_row_height_frac,
        )
        if len(rows) >= 2:
            return _inherit_parent_hit_density(rows, parent=track)
    return [track]


def _split_wide_ui_track_by_ink_columns(
    track: MergedTrack,
    frame_bgr: np.ndarray,
    *,
    frame_w: int,
    frame_h: int,
) -> list[MergedTrack]:
    """Split a shallow UI-grid box at a large, clean horizontal gutter."""
    x0, y0, x1, y1 = (float(value) for value in track.box_coords[:4])
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    role = classify_ocr_box_role(
        track.box_coords, frame_w=frame_w, frame_h=frame_h
    )
    if (
        role == "hardsub"
        or width / fw < 0.10
        or height / fh > 0.065
        or width / height < 3.5
    ):
        return [track]

    image_h, image_w = frame_bgr.shape[:2]
    ix0 = max(0, min(image_w - 1, int(np.floor(x0))))
    iy0 = max(0, min(image_h - 1, int(np.floor(y0))))
    ix1 = max(ix0 + 1, min(image_w, int(np.ceil(x1))))
    iy1 = max(iy0 + 1, min(image_h, int(np.ceil(y1))))
    crop = frame_bgr[iy0:iy1, ix0:ix1]
    if crop.size == 0 or crop.shape[1] < 40:
        return [track]

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    border = np.concatenate(
        (gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1])
    )
    background = float(np.median(border))
    ink = np.abs(gray - background) >= 28.0
    min_active_pixels = max(2, int(round(0.06 * crop.shape[0])))
    active = ink.sum(axis=0) >= min_active_pixels
    close_width = max(3, int(round(0.003 * fw)))
    active_u8 = cv2.morphologyEx(
        active.astype(np.uint8) * 255,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (close_width, 1)),
    )
    active = active_u8 > 0

    components: list[list[int]] = []
    start: int | None = None
    for index, value in enumerate(active):
        if value and start is None:
            start = index
        if not value and start is not None:
            if index - start >= 3:
                components.append([start, index])
            start = None
    if start is not None and len(active) - start >= 3:
        components.append([start, len(active)])
    if len(components) < 2:
        return [track]

    large_gap = max(18, int(round(0.012 * fw)))
    groups: list[list[int]] = [components[0]]
    for component in components[1:]:
        if component[0] - groups[-1][1] >= large_gap:
            groups.append(component)
        else:
            groups[-1][1] = component[1]
    if len(groups) < 2:
        return [track]

    padding = max(2, int(round(0.002 * fw)))
    rows: list[MergedTrack] = []
    parent_frames = list(track.hit_frames) or [int(track.best_frame_index)]
    parent_sharpness = list(track.hit_sharpness) or [float(track.best_sharpness)]
    for group_start, group_end in groups:
        if group_end - group_start < 10:
            continue
        box = [
            float(max(ix0, ix0 + group_start - padding)),
            y0,
            float(min(ix1, ix0 + group_end + padding)),
            y1,
        ]
        box_tuple = tuple(box)
        rows.append(
            MergedTrack(
                start_frame=int(track.start_frame),
                end_frame=int(track.end_frame),
                box_coords=box,
                best_frame_index=int(track.best_frame_index),
                best_sharpness=float(track.best_sharpness),
                centroid=_box_centroid(box),
                hit_count=int(track.hit_count),
                hit_boxes=[box_tuple] * len(parent_frames),
                hit_frames=list(parent_frames),
                hit_sharpness=list(parent_sharpness)[: len(parent_frames)],
            )
        )
        setattr(rows[-1], "_ui_grid_split_child", True)
    return rows if len(rows) >= 2 else [track]


def _has_dense_ui_grid_peer_evidence(
    candidate: MergedTrack,
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
) -> bool:
    """Require a stable, simultaneous 2-D panel before treating spaces as cells.

    A blank horizontal gutter is not sufficient by itself: ordinary Latin
    captions contain the same whitespace between words.  Nutrition/editor
    grids instead expose many dense tracks at the same time across both axes.
    Temporal IoU (rather than overlap over the shorter span) prevents a short
    caption from borrowing evidence from long-lived graph labels behind it.
    """
    start = int(candidate.start_frame)
    end = int(candidate.end_frame)
    span = max(1, end - start + 1)
    hit_count = int(candidate.hit_count)
    if hit_count < 8 or hit_count / float(span) < 0.65:
        return False

    cohort: list[MergedTrack] = [candidate]
    for peer in tracks:
        if peer is candidate:
            continue
        peer_start = int(peer.start_frame)
        peer_end = int(peer.end_frame)
        peer_span = max(1, peer_end - peer_start + 1)
        peer_hits = int(peer.hit_count)
        if peer_hits < 8 or peer_hits / float(peer_span) < 0.65:
            continue
        overlap = max(0, min(end, peer_end) - max(start, peer_start) + 1)
        union = max(end, peer_end) - min(start, peer_start) + 1
        if overlap / float(max(1, union)) < 0.80:
            continue
        cohort.append(peer)

    if len(cohort) < 7:
        return False
    centers = [_box_centroid(track.box_coords) for track in cohort]
    x_spread = max(center[0] for center in centers) - min(
        center[0] for center in centers
    )
    y_spread = max(center[1] for center in centers) - min(
        center[1] for center in centers
    )
    return (
        x_spread >= 0.45 * float(frame_w)
        and y_spread >= 0.20 * float(frame_h)
        and any(
            0.15 * float(frame_w) <= center[0] <= 0.85 * float(frame_w)
            for center in centers
        )
    )


def dense_source_ui_panel_member_ids(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
) -> set[int]:
    """Return text tracks belonging to a source-rendered app/device plane.

    Screen lock alone is not provenance: both an editor subtitle and a phone UI
    are screen locked in a screen recording.  A source UI plane instead exposes
    a synchronized multi-row, multi-column cohort of compact labels spanning a
    large two-dimensional surface.  Hardsub geometry and large title cards are
    excluded before the cohort is built, preventing a bottom editor caption
    from inheriting the panel classification.
    """
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))

    def _eligible(track: MergedTrack) -> bool:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        if role == "hardsub" or int(track.hit_count) < 2:
            return False
        x0, y0, x1, y1 = (float(value) for value in track.box_coords[:4])
        width_frac = max(1.0, x1 - x0) / fw
        height_frac = max(1.0, y1 - y0) / fh
        return width_frac <= 0.26 and height_frac <= 0.085

    eligible = [track for track in tracks if _eligible(track)]
    if len(eligible) < 9:
        return set()

    def _temporal_support(left: MergedTrack, right: MergedTrack) -> bool:
        overlap = max(
            0,
            min(int(left.end_frame), int(right.end_frame))
            - max(int(left.start_frame), int(right.start_frame))
            + 1,
        )
        shorter = max(
            1,
            min(
                int(left.end_frame) - int(left.start_frame) + 1,
                int(right.end_frame) - int(right.start_frame) + 1,
            ),
        )
        return overlap / float(shorter) >= 0.75

    def _axis_cluster_count(values: Sequence[float], tolerance: float) -> int:
        groups: list[float] = []
        for value in sorted(float(item) for item in values):
            if not groups or value - groups[-1] > tolerance:
                groups.append(value)
            else:
                groups[-1] = 0.5 * (groups[-1] + value)
        return len(groups)

    members: set[int] = set()
    for candidate in eligible:
        cohort = [
            peer for peer in eligible if _temporal_support(candidate, peer)
        ]
        if len(cohort) < 9:
            continue
        centers = [_box_centroid(peer.box_coords) for peer in cohort]
        x_values = [center[0] for center in centers]
        y_values = [center[1] for center in centers]
        if max(x_values) - min(x_values) < 0.55 * fw:
            continue
        if max(y_values) - min(y_values) < 0.28 * fh:
            continue
        if _axis_cluster_count(x_values, 0.085 * fw) < 4:
            continue
        if _axis_cluster_count(y_values, 0.065 * fh) < 3:
            continue
        members.update(id(peer) for peer in cohort)
    return members


DENSE_SOURCE_UI_CONTEXT_MIN_PEERS = 2
DENSE_SOURCE_UI_CONTEXT_MAX_HEIGHT_FRAC = 0.032
DENSE_SOURCE_UI_CONTEXT_MIN_TEMPORAL_SUPPORT = 0.50
REPEATED_SOURCE_UI_ROW_MIN_TRACKS = 6
REPEATED_SOURCE_UI_ROW_MAX_MEDIAN_SPAN = 6
REPEATED_SOURCE_UI_ROW_MIN_UNION_SPAN = 30
REPEATED_SOURCE_UI_ROW_MIN_IOU = 0.72
REPEATED_SOURCE_UI_ROW_MAX_PANEL_GAP_FRAMES = 180
REPEATED_SOURCE_UI_ROW_NEIGHBOUR_MAX_GAP = 12
REPEATED_SOURCE_UI_ROW_NEIGHBOUR_MAX_SPAN = 24
REPEATED_SOURCE_UI_ROW_NEIGHBOUR_MIN_CONTAINMENT = 0.80


def dense_source_ui_context_member_ids(
    tracks: Sequence[MergedTrack],
    *,
    dense_panel_ids: set[int],
    frame_w: int,
    frame_h: int,
) -> set[int]:
    """Propagate a proven source UI plane to its thin joined labels.

    DBNet often joins an entire app row (for example four camera modes) into a
    single wide box.  That joined row is too wide to be a direct compact-panel
    member and used to fall through to ``wide_locked_editor_card_anchor`` even
    while dozens of proven source UI cells were visible on the same frames.

    Propagation is deliberately narrow: hardsub geometry is never inherited,
    the candidate must be a thin locked label, and at least two already-proven
    panel peers must cover half of its lifetime.  The height ceiling keeps
    large editor captions on top of a phone/app screen localizable.
    """
    if not dense_panel_ids:
        return set()
    fh = max(1.0, float(frame_h))
    panel_tracks = [track for track in tracks if id(track) in dense_panel_ids]
    members: set[int] = set(dense_panel_ids)
    for candidate in tracks:
        if id(candidate) in members:
            continue
        role = classify_ocr_box_role(
            candidate.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        # Temporal coincidence with a dense device/app panel is not spatial
        # provenance.  Editor captions frequently sit on top of a phone UI;
        # inheriting the panel's SOURCE_INTRINSIC classification leaves the
        # caption deliberately unprocessed by Phase 4.  The function contract
        # has always promised this exclusion, but the guard was accidentally
        # removed when joined-row propagation was introduced.
        if role == "hardsub" or int(candidate.hit_count) < 2:
            continue
        if not is_horizontally_locked_track(
            candidate, frame_w=frame_w, frame_h=frame_h
        ):
            continue
        height = max(
            1.0,
            float(candidate.box_coords[3]) - float(candidate.box_coords[1]),
        )
        if height / fh > DENSE_SOURCE_UI_CONTEXT_MAX_HEIGHT_FRAC:
            continue
        candidate_span = max(
            1, int(candidate.end_frame) - int(candidate.start_frame) + 1
        )
        peer_count = 0
        for peer in panel_tracks:
            overlap = max(
                0,
                min(int(candidate.end_frame), int(peer.end_frame))
                - max(int(candidate.start_frame), int(peer.start_frame))
                + 1,
            )
            if (
                overlap / float(candidate_span)
                >= DENSE_SOURCE_UI_CONTEXT_MIN_TEMPORAL_SUPPORT
            ):
                peer_count += 1
                if peer_count >= DENSE_SOURCE_UI_CONTEXT_MIN_PEERS:
                    members.add(id(candidate))
                    break
    return members


def source_panel_containment_member_ids(
    tracks: Sequence[MergedTrack],
    *,
    strong_source_ids: set[int],
    frame_w: int,
    frame_h: int,
) -> set[int]:
    """Protect compact locked labels contained by a proven source UI plane.

    Phone/app controls may appear sequentially, so they do not always satisfy
    the synchronized dense-panel rule. A compact candidate is inherited only
    from at least four temporally overlapping, spatially diverse source-bound
    peers. Hardsubs and large editor cards are explicitly excluded.
    """

    if not strong_source_ids:
        return set()
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    source_tracks = [track for track in tracks if id(track) in strong_source_ids]
    members: set[int] = set()
    for candidate in tracks:
        if id(candidate) in strong_source_ids:
            continue
        role = classify_ocr_box_role(
            candidate.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        if role == "hardsub" or int(candidate.hit_count) < 2:
            continue
        if not is_horizontally_locked_track(
            candidate, frame_w=frame_w, frame_h=frame_h
        ):
            continue
        x0, y0, x1, y1 = (float(value) for value in candidate.box_coords[:4])
        if (y1 - y0) / fh > 0.045 or (x1 - x0) / fw > 0.45:
            continue
        candidate_span = max(
            1, int(candidate.end_frame) - int(candidate.start_frame) + 1
        )
        peers: list[MergedTrack] = []
        for peer in source_tracks:
            overlap = max(
                0,
                min(int(candidate.end_frame), int(peer.end_frame))
                - max(int(candidate.start_frame), int(peer.start_frame))
                + 1,
            )
            if overlap / float(candidate_span) >= 0.35:
                peers.append(peer)
        required_peers = 6 if role == "hardsub" else 4
        if len(peers) < required_peers:
            continue
        peer_x0 = min(float(peer.box_coords[0]) for peer in peers)
        peer_y0 = min(float(peer.box_coords[1]) for peer in peers)
        peer_x1 = max(float(peer.box_coords[2]) for peer in peers)
        peer_y1 = max(float(peer.box_coords[3]) for peer in peers)
        if peer_x1 - peer_x0 < 0.35 * fw or peer_y1 - peer_y0 < 0.25 * fh:
            continue
        cx, cy = _box_centroid(candidate.box_coords)
        margin_x = 0.05 * fw
        margin_y = 0.05 * fh
        if not (
            peer_x0 - margin_x <= cx <= peer_x1 + margin_x
            and peer_y0 - margin_y <= cy <= peer_y1 + margin_y
        ):
            continue
        members.add(id(candidate))
    return members


def repeated_source_ui_row_member_ids(
    tracks: Sequence[MergedTrack],
    *,
    dense_panel_ids: set[int],
) -> set[int]:
    """Protect a stable app row fragmented into many short detector tracks.

    Some animated phone panels make DBNet emit the same navigation row as a
    series of three-frame slabs.  Their bottom-wide geometry resembles a
    subtitle, so the hardsub role alone is not authoritative.  A source row is
    accepted only when the same box recurs many times, each fragment stays
    short, the family spans a meaningful interval, and the family is adjacent
    to a separately proven dense UI plane.
    """
    if not dense_panel_ids:
        return set()
    panel_tracks = [track for track in tracks if id(track) in dense_panel_ids]
    members: set[int] = set()
    for candidate in tracks:
        family = [
            peer
            for peer in tracks
            if box_iou(candidate.box_coords, peer.box_coords)
            >= REPEATED_SOURCE_UI_ROW_MIN_IOU
        ]
        if len(family) < REPEATED_SOURCE_UI_ROW_MIN_TRACKS:
            continue
        spans = sorted(
            max(1, int(peer.end_frame) - int(peer.start_frame) + 1)
            for peer in family
        )
        median_span = spans[len(spans) // 2]
        if median_span > REPEATED_SOURCE_UI_ROW_MAX_MEDIAN_SPAN:
            continue
        family_start = min(int(peer.start_frame) for peer in family)
        family_end = max(int(peer.end_frame) for peer in family)
        if (
            family_end - family_start + 1
            < REPEATED_SOURCE_UI_ROW_MIN_UNION_SPAN
        ):
            continue

        def _panel_gap(peer: MergedTrack) -> int:
            if int(peer.end_frame) < family_start:
                return family_start - int(peer.end_frame) - 1
            if family_end < int(peer.start_frame):
                return int(peer.start_frame) - family_end - 1
            return 0

        if min(_panel_gap(peer) for peer in panel_tracks) > (
            REPEATED_SOURCE_UI_ROW_MAX_PANEL_GAP_FRAMES
        ):
            continue
        members.update(id(peer) for peer in family)
        family_boxes = [peer.box_coords for peer in family]
        for peer in tracks:
            if id(peer) in members:
                continue
            peer_span = max(
                1, int(peer.end_frame) - int(peer.start_frame) + 1
            )
            if peer_span > REPEATED_SOURCE_UI_ROW_NEIGHBOUR_MAX_SPAN:
                continue
            temporal_gap = min(
                (
                    max(
                        0,
                        int(peer.start_frame) - int(member.end_frame) - 1,
                        int(member.start_frame) - int(peer.end_frame) - 1,
                    )
                    for member in family
                ),
                default=REPEATED_SOURCE_UI_ROW_NEIGHBOUR_MAX_GAP + 1,
            )
            if temporal_gap > REPEATED_SOURCE_UI_ROW_NEIGHBOUR_MAX_GAP:
                continue
            px0, py0, px1, py1 = (
                float(value) for value in peer.box_coords[:4]
            )
            peer_area = max(1.0, (px1 - px0) * (py1 - py0))
            contained = False
            for box in family_boxes:
                x0 = max(px0, float(box[0]))
                y0 = max(py0, float(box[1]))
                x1 = min(px1, float(box[2]))
                y1 = min(py1, float(box[3]))
                intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
                if (
                    intersection / peer_area
                    >= REPEATED_SOURCE_UI_ROW_NEIGHBOUR_MIN_CONTAINMENT
                ):
                    contained = True
                    break
            if contained:
                members.add(id(peer))
    return members


def split_wide_ui_tracks_by_ink_columns(
    tracks: Sequence[MergedTrack],
    *,
    frame_cache: Mapping[int, np.ndarray],
    frame_w: int,
    frame_h: int,
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """Split stable table/chart cells that DBNet joined across a blank gutter."""
    output: list[MergedTrack] = []
    audit: dict[str, Any] = {
        "method": "wide_ui_ink_column_split_v1",
        "before_count": len(tracks),
        "after_count": len(tracks),
        "split_tracks": 0,
        "rows": [],
    }
    for track in tracks:
        if not _has_dense_ui_grid_peer_evidence(
            track,
            tracks,
            frame_w=frame_w,
            frame_h=frame_h,
        ):
            output.append(track)
            continue
        frame = frame_cache.get(int(track.best_frame_index))
        if frame is None:
            output.append(track)
            continue
        split = _split_wide_ui_track_by_ink_columns(
            track, frame, frame_w=frame_w, frame_h=frame_h
        )
        output.extend(split)
        if len(split) >= 2:
            audit["split_tracks"] += 1
            audit["rows"].append(
                {
                    "prior_box": list(track.box_coords),
                    "result_boxes": [list(row.box_coords) for row in split],
                }
            )
    output.sort(key=lambda row: (row.start_frame, row.box_coords[0]))
    audit["after_count"] = len(output)
    return output, audit


def filter_tracks_by_local_text(
    tracks: Sequence[MergedTrack],
    *,
    frame_cache: Mapping[int, np.ndarray],
    frame_w: int,
    frame_h: int,
    recognizer: Any | None,
    source: Path | None = None,
    preserve_source_candidates: bool = False,
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """
    Drop detector tracks that do not read as on-screen text (all videos).

    Two-pass peer rescue: column peers come only from tracks that already
    survive without peer lowering (stops drifting scene text from rescuing
    short packaging chips). Tall mid blobs are split before oversized drop.
    """
    del source  # reserved for frame reload; cache is preferred

    # A dense, simultaneous 2-D editor panel is independent provenance that a
    # compact box is an intentional UI cell.  Pre-compute it before any track
    # geometry is rewritten so a narrow endcard label in the upper hardsub
    # band cannot be Y-hunted into an unrelated bottom caption.
    dense_ui_grid_member_ids = {
        id(track)
        for track in tracks
        if _has_dense_ui_grid_peer_evidence(
            track,
            tracks,
            frame_w=frame_w,
            frame_h=frame_h,
        )
    }
    hardsub_recovery_rows: list[dict[str, Any]] = []
    dense_ui_grid_recovery_skips = 0

    pre_recovery_caption_lane_ids = sequential_caption_lane_member_ids(
        tracks,
        frame_w=frame_w,
        frame_h=frame_h,
    )
    expanded: list[MergedTrack] = []
    for track in tracks:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        x0, y0, x1, y1 = (float(v) for v in track.box_coords[:4])
        h = max(1.0, y1 - y0)
        w = max(1.0, x1 - x0)
        fh = max(1.0, float(frame_h))
        fw = max(1.0, float(frame_w))
        # Narrow true-bottom stubs / square food seeds: recover full ink span
        # BEFORE OCR. Do not steal endcard list chips at cy 0.78–0.87.
        # Wide thin mid-band slabs (food edges) also try recover — they are not
        # burn-ins, but the real line often sits lower on the same frames.
        cy = ((y0 + y1) * 0.5) / fh
        aspect = w / max(h, 1.0)
        h_frac = h / fh
        w_frac = w / fw
        detector_frames = sorted({int(value) for value in track.hit_frames})
        detector_span = (
            max(1, detector_frames[-1] - detector_frames[0] + 1)
            if detector_frames
            else 1
        )
        detector_density = len(detector_frames) / float(detector_span)
        dense_valid_hardsub_seed = (
            role == "hardsub"
            and _box_is_hardsub_line_geometry(
                track.box_coords, frame_w=frame_w, frame_h=frame_h
            )
            and w_frac >= 0.12
            and len(detector_frames) >= 3
            and detector_density >= 0.75
        )
        wide_band_food_slab = (
            _in_hardsub_y_band(
                track.box_coords, frame_w=frame_w, frame_h=frame_h
            )
            and role != "hardsub"
            and cy < HARDSUB_ROLE_CY
            and h_frac <= THIN_HARDSUB_HEIGHT_FRAC
            and w_frac >= 0.18
            and aspect >= HARDSUB_MIN_ASPECT
            and id(track) not in pre_recovery_caption_lane_ids
        )
        dense_ui_grid_cell = (
            role != "hardsub"
            and cy < HARDSUB_ROLE_CY
            and (
                id(track) in dense_ui_grid_member_ids
                or bool(getattr(track, "_ui_grid_split_child", False))
            )
        )
        hardsub_recovery_candidate = wide_band_food_slab or (
            _in_hardsub_y_band(
                track.box_coords, frame_w=frame_w, frame_h=frame_h
            )
            and w_frac < 0.35
            and not dense_valid_hardsub_seed
            and (
                role == "hardsub"
                or cy >= HARDSUB_ROLE_CY
                or aspect < HARDSUB_MIN_ASPECT
            )
        )
        want_hardsub_recover = (
            hardsub_recovery_candidate and not dense_ui_grid_cell
        )
        if hardsub_recovery_candidate and dense_ui_grid_cell:
            dense_ui_grid_recovery_skips += 1
        if want_hardsub_recover:
            prior_box = [float(value) for value in track.box_coords[:4]]
            for frame in _cached_frames_for_track(
                track, frame_cache, max_frames=3
            ):
                recovered = recover_hardsub_box_from_band_ink(
                    frame,
                    track.box_coords,
                    frame_w=frame_w,
                    frame_h=frame_h,
                )
                if recovered is None:
                    continue
                rw = float(recovered[2]) - float(recovered[0])
                if rw / fw < 0.28:
                    continue
                if not _box_is_hardsub_line_geometry(
                    recovered, frame_w=frame_w, frame_h=frame_h
                ):
                    continue
                recovered_t = tuple(float(v) for v in recovered[:4])
                # Replace non-line food stubs so coalesce cannot rebuild the slab.
                prev_hits = list(track.hit_boxes) or [recovered_t]
                hit_boxes = [
                    recovered_t
                    if not _box_is_hardsub_line_geometry(
                        hb, frame_w=frame_w, frame_h=frame_h
                    )
                    else tuple(float(v) for v in hb[:4])
                    for hb in prev_hits
                ]
                track = MergedTrack(
                    start_frame=track.start_frame,
                    end_frame=track.end_frame,
                    box_coords=recovered,
                    best_frame_index=track.best_frame_index,
                    best_sharpness=track.best_sharpness,
                    centroid=_box_centroid(recovered),
                    hit_count=track.hit_count,
                    hit_boxes=hit_boxes,
                    hit_frames=list(track.hit_frames),
                    hit_sharpness=list(track.hit_sharpness),
                )
                role = classify_ocr_box_role(
                    track.box_coords, frame_w=frame_w, frame_h=frame_h
                )
                hardsub_recovery_rows.append(
                    {
                        "reason": (
                            "wide_band_food_slab"
                            if wide_band_food_slab
                            else "compact_bottom_stub"
                        ),
                        "prior_box": prior_box,
                        "result_box": list(track.box_coords),
                    }
                )
                break
        x0, y0, x1, y1 = (float(v) for v in track.box_coords[:4])
        h = max(1.0, y1 - y0)
        w = max(1.0, x1 - x0)
        h_frac = h / fh
        aspect = w / h
        mid_title_geom = (
            role == "mid_label"
            and aspect >= 2.2
            and h_frac <= 0.12
            and (w / fw) * h_frac <= 0.045
        )
        intro_title_geom = (
            role in {"mid_label", "generic"}
            and int(track.start_frame) <= 2
            and int(track.end_frame) - int(track.start_frame) + 1 <= 8
            and aspect >= 2.0
            and w / fw >= 0.20
            and h_frac <= 0.20
            and 0.25 <= ((x0 + x1) * 0.5) / fw <= 0.75
        )
        narrow_stack = aspect < 1.2 and h_frac > 0.055 and (w / fw) < 0.12
        if role in {"mid_label", "ui_chip", "generic"} and (
            (h_frac > 0.085 and not mid_title_geom and not intro_title_geom)
            or narrow_stack
        ):
            frame = frame_cache.get(int(track.best_frame_index))
            expanded.extend(
                split_mid_label_blob_rows(
                    track,
                    frame_bgr=frame,
                    frame_h=frame_h,
                    frame_cache=frame_cache,
                )
            )
        else:
            expanded.append(track)

    dense_source_panel_ids = dense_source_ui_panel_member_ids(
        expanded,
        frame_w=frame_w,
        frame_h=frame_h,
    )
    caption_lane_ids = sequential_caption_lane_member_ids(
        expanded,
        frame_w=frame_w,
        frame_h=frame_h,
    )

    # Latin-only OCR remains rejected by default. A candidate may use the
    # narrow editor-card exception only when (a) its crop has a saturated,
    # coherent panel fill and (b) another panel candidate appears at the same
    # layout locus in a non-overlapping time span. The temporal copy change is
    # independent editor-layout evidence that a static package/device label
    # cannot provide by itself.
    colored_panel_ids: set[int] = set()
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    for track in expanded:
        x0, y0, x1, y1 = (float(value) for value in track.box_coords[:4])
        width_frac = max(1.0, x1 - x0) / fw
        height_frac = max(1.0, y1 - y0) / fh
        if width_frac < 0.18 or height_frac > 0.12:
            continue
        if not is_horizontally_locked_track(
            track, frame_w=frame_w, frame_h=frame_h
        ):
            continue
        if any(
            has_solid_colored_editor_panel(frame, track.box_coords)
            for frame in _cached_frames_for_track(track, frame_cache, max_frames=3)
        ):
            colored_panel_ids.add(id(track))

    latin_editor_card_peer_ids: set[int] = set()
    colored_tracks = [track for track in expanded if id(track) in colored_panel_ids]
    for index, track in enumerate(colored_tracks):
        tx0, ty0, tx1, ty1 = (float(value) for value in track.box_coords[:4])
        tw = max(1.0, tx1 - tx0)
        tcy = 0.5 * (ty0 + ty1)
        for peer in colored_tracks[index + 1 :]:
            if _tracks_time_overlap(track, peer):
                continue
            px0, py0, px1, py1 = (
                float(value) for value in peer.box_coords[:4]
            )
            pw = max(1.0, px1 - px0)
            horizontal_overlap = max(0.0, min(tx1, px1) - max(tx0, px0))
            if horizontal_overlap / min(tw, pw) < 0.55:
                continue
            pcy = 0.5 * (py0 + py1)
            if abs(tcy - pcy) > 0.35 * fh:
                continue
            latin_editor_card_peer_ids.update((id(track), id(peer)))

    # Semantic in-scene diagram labels are deliberately narrower than generic
    # Latin source text. Require a concurrent, vertically separated label at
    # the same layout axis, strong temporal density, and a distinct coherent
    # background region. This admits explanatory map/diagram annotations while
    # excluding a lone watermark and compact TARE/UNIT text on one device panel.
    semantic_backgrounds: dict[int, dict[str, float]] = {}
    semantic_candidates: list[MergedTrack] = []
    for track in expanded:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        if role == "hardsub":
            continue
        x0, y0, x1, y1 = (float(value) for value in track.box_coords[:4])
        width_frac = max(1.0, x1 - x0) / fw
        height_frac = max(1.0, y1 - y0) / fh
        aspect = max(1.0, x1 - x0) / max(1.0, y1 - y0)
        cx_frac = 0.5 * (x0 + x1) / fw
        cy_frac = 0.5 * (y0 + y1) / fh
        hit_frames = sorted({int(value) for value in track.hit_frames})
        span = max(1, int(track.end_frame) - int(track.start_frame) + 1)
        density = len(hit_frames) / float(span)
        if not (
            0.04 <= width_frac <= 0.35
            and 0.008 <= height_frac <= 0.06
            and 2.0 <= aspect <= 16.0
            and 0.12 <= cx_frac <= 0.88
            and 0.08 <= cy_frac <= 0.92
            and span >= 12
            and len(hit_frames) >= 8
            and density >= 0.65
        ):
            continue
        if not is_horizontally_locked_track(
            track, frame_w=frame_w, frame_h=frame_h
        ):
            continue
        signature = next(
            (
                value
                for frame in _cached_frames_for_track(
                    track, frame_cache, max_frames=3
                )
                if (
                    value := semantic_scene_label_background_signature(
                        frame, track.box_coords
                    )
                )
                is not None
            ),
            None,
        )
        if signature is None:
            continue
        semantic_backgrounds[id(track)] = signature
        semantic_candidates.append(track)

    semantic_scene_label_peer_ids: set[int] = set()
    semantic_peer_evidence: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, track in enumerate(semantic_candidates):
        tx, ty = _box_centroid(track.box_coords)
        track_span = max(1, int(track.end_frame) - int(track.start_frame) + 1)
        for peer in semantic_candidates[index + 1 :]:
            overlap = max(
                0,
                min(int(track.end_frame), int(peer.end_frame))
                - max(int(track.start_frame), int(peer.start_frame))
                + 1,
            )
            peer_span = max(1, int(peer.end_frame) - int(peer.start_frame) + 1)
            if overlap / float(min(track_span, peer_span)) < 0.80:
                continue
            px, py = _box_centroid(peer.box_coords)
            if abs(tx - px) > 0.12 * fw:
                continue
            vertical_delta = abs(ty - py)
            if not 0.12 * fh <= vertical_delta <= 0.55 * fh:
                continue
            left_background = semantic_backgrounds[id(track)]
            right_background = semantic_backgrounds[id(peer)]
            if not _semantic_scene_backgrounds_are_distinct(
                left_background, right_background
            ):
                continue
            semantic_scene_label_peer_ids.update((id(track), id(peer)))
            semantic_peer_evidence[id(track)].append(
                {
                    "peer_box": list(peer.box_coords),
                    "background": left_background,
                    "peer_background": right_background,
                }
            )
            semantic_peer_evidence[id(peer)].append(
                {
                    "peer_box": list(track.box_coords),
                    "background": right_background,
                    "peer_background": left_background,
                }
            )

    dropped_rows: list[dict[str, Any]] = []
    latin_editor_card_rescued_ids: set[int] = set()
    semantic_scene_label_rows: dict[int, dict[str, Any]] = {}

    def _decide(
        track: MergedTrack,
        *,
        has_peer: bool,
    ) -> tuple[bool, dict[str, Any] | None]:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        caption_lane = id(track) in caption_lane_ids
        dense_source_panel = (
            preserve_source_candidates and id(track) in dense_source_panel_ids
        )
        requires_single_frame_cjk = bool(
            getattr(track, "_single_frame_retention_candidate", False)
            or getattr(track, "_strong_single_frame_textness", False)
        ) and int(track.hit_count) == 1
        need_hits = min_hits_for_role(role)
        if requires_single_frame_cjk:
            # Textness/closure evidence may carry a one-frame DBNet hit to the
            # recognizer, but cannot make it authoritative on its own.
            need_hits = 1
        if dense_source_panel:
            # A high-resolution recovery anchor may supply only N-1/N/N+1 for
            # a label whose surrounding panel is independently authoritative.
            need_hits = min(need_hits, 2)
        if has_peer and role in {"mid_label", "ui_chip"}:
            # Surviving locked peer may rescue a 2-hit editor flash.
            need_hits = min(need_hits, 2)
        if int(track.hit_count) < need_hits:
            return False, {
                "reason": "low_hits",
                "role": role,
                "hit_count": int(track.hit_count),
                "need_hits": need_hits,
                "box": list(track.box_coords),
            }
        if dense_source_panel and not requires_single_frame_cjk:
            setattr(track, "_source_intrinsic_candidate", "dense_source_ui_panel")
            return True, None

        source_scene_candidate = False if caption_lane else not is_editor_overlay_track(
            track,
            role=role,
            frame_w=frame_w,
            frame_h=frame_h,
            has_stable_column_peer=has_peer,
        )
        if source_scene_candidate and not preserve_source_candidates:
            sx, sy = track_centroid_sigma_xy(track)
            return False, {
                "reason": "scene_text",
                "role": role,
                "hit_count": int(track.hit_count),
                "centroid_sigma_xy": [sx, sy],
                "box": list(track.box_coords),
            }
        x0, y0, x1, y1 = (float(v) for v in track.box_coords[:4])
        w = max(1.0, x1 - x0)
        h = max(1.0, y1 - y0)
        fw = max(1.0, float(frame_w))
        fh = max(1.0, float(frame_h))
        intro_title_geom = (
            role in {"mid_label", "generic"}
            and int(track.start_frame) <= 2
            and int(track.end_frame) - int(track.start_frame) + 1 <= 8
            and (w / h) >= 2.0
            and w / fw >= 0.20
            and h / fh <= 0.12
            and 0.25 <= ((x0 + x1) * 0.5) / fw <= 0.75
        )
        # Hardsub-role stubs that never became a burn-in line.
        if not source_scene_candidate and role == "hardsub" and not _box_is_hardsub_line_geometry(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        ):
            return False, {
                "reason": "not_overlay_geometry",
                "role": role,
                "box": list(track.box_coords),
            }
        if intro_title_geom:
            setattr(track, "_intro_title_candidate", True)
        # Wide thin mid-band slabs that never promoted to burn-in (food edges).
        if (
            not source_scene_candidate
            and
            role != "hardsub"
            and _in_hardsub_y_band(
                track.box_coords, frame_w=frame_w, frame_h=frame_h
            )
            and (h / fh) <= THIN_HARDSUB_HEIGHT_FRAC
            and (w / fw) >= 0.18
            and ((y0 + y1) * 0.5) / fh < HARDSUB_ROLE_CY
            and not caption_lane
        ):
            return False, {
                "reason": "not_overlay_geometry",
                "role": role,
                "box": list(track.box_coords),
            }
        # Tall micro flecks (egg yolk / chili crumb) — not editor chips.
        if not source_scene_candidate and role in {"mid_label", "ui_chip", "generic"}:
            aspect_hw = h / max(w, 1.0)
            if (w / fw) < 0.030 and aspect_hw >= 1.35:
                return False, {
                    "reason": "not_overlay_geometry",
                    "role": role,
                    "box": list(track.box_coords),
                }
        wide_hardsub = (
            role == "hardsub"
            and (w / fw) >= 0.35
            and (h / fh) <= THIN_HARDSUB_HEIGHT_FRAC
        )
        # Soft food/lettuce bands score far below stroke burn-in on ink.
        if wide_hardsub and not source_scene_candidate:
            ink_frames = _cached_frames_for_track(
                track, frame_cache, max_frames=2
            )
            if ink_frames:
                ink = max(
                    crop_ink_score(fr, track.box_coords) for fr in ink_frames
                )
                if ink < 3.5:
                    return False, {
                        "reason": "low_ink",
                        "role": role,
                        "ink": round(float(ink), 4),
                        "box": list(track.box_coords),
                    }
        area_frac = (w / fw) * (h / fh)
        aspect_wh = w / max(h, 1.0)
        # Mid burn-in titles (懒人无米饭包) sit taller than chip rows but stay
        # line-like; keep when aspect is wide and area remains modest.
        mid_title_ok = (
            role == "mid_label"
            and aspect_wh >= 2.2
            and (h / fh) <= 0.12
            and area_frac <= 0.045
        )
        if not source_scene_candidate and (
            ((h / fh) > 0.085 or area_frac > 0.045)
            and not intro_title_geom
        ):
            if not wide_hardsub and not mid_title_ok:
                return False, {
                    "reason": "oversized_blob",
                    "role": role,
                    "box": list(track.box_coords),
                }

        # Ultra-thin generic bands (food reflection / knife glare) often pass
        # geometry + OCR garbage. Require stroke ink; do not apply to mid_label
        # chips (solid-fill glyphs can score low on synthetic flats).
        aspect = w / max(h, 1.0)
        ultra_thin_generic = (
            role == "generic"
            and (h / fh) <= 0.032
            and aspect >= 4.5
        )
        if ultra_thin_generic and not source_scene_candidate:
            ink_frames = _cached_frames_for_track(
                track, frame_cache, max_frames=2
            )
            if ink_frames:
                ink = max(
                    crop_ink_score(fr, track.box_coords) for fr in ink_frames
                )
                if ink < 0.45:
                    return False, {
                        "reason": "low_ink",
                        "role": role,
                        "ink": round(float(ink), 4),
                        "box": list(track.box_coords),
                    }

        if recognizer is None:
            if requires_single_frame_cjk:
                return False, {
                    "reason": "single_frame_recognizer_unavailable",
                    "role": role,
                    "box": list(track.box_coords),
                }
            if wide_hardsub or role == "mid_label":
                if role == "mid_label" and (w / h) < 1.2 and (w / fw) < 0.12:
                    return False, {
                        "reason": "no_recognizer_compact",
                        "role": role,
                        "box": list(track.box_coords),
                    }
                return True, None
            return False, {
                "role": role,
                "reason": "no_recognizer_ui",
                "box": list(track.box_coords),
            }

        frame_candidates = _cached_frames_for_track(
            track, frame_cache, max_frames=3
        )
        if not frame_candidates:
            if wide_hardsub and not requires_single_frame_cjk:
                return True, None
            return False, {
                "reason": "missing_frame",
                "role": role,
                "box": list(track.box_coords),
            }

        accepted = False
        accepted_signatures: set[str] = set()
        accepted_texts: list[str] = []
        accepted_cjk_max = 0
        accepted_sample_count = 0
        last_reject: dict[str, Any] | None = None
        saw_crop = False
        for frame in frame_candidates:
            crop = _crop_xyxy_from_frame(frame, track.box_coords)
            if crop is None or crop.size < 16:
                continue
            saw_crop = True
            try:
                recognition = recognizer.recognize(crop)
            except Exception as exc:  # noqa: BLE001
                logger.warning("phase1_local_text_recognize_failed err=%s", exc)
                last_reject = {
                    "reason": "recognize_error",
                    "role": role,
                    "box": list(track.box_coords),
                }
                continue
            latin_card_evidence = (
                id(track) in latin_editor_card_peer_ids
                and has_solid_colored_editor_panel(frame, track.box_coords)
            )
            semantic_scene_evidence = (
                id(track) in semantic_scene_label_peer_ids
                and not latin_card_evidence
            )
            locally_accepted = local_text_accepts_track(
                recognition,
                role="hardsub" if caption_lane else role,
                allow_latin_editor_card=latin_card_evidence,
                allow_latin_semantic_scene_label=semantic_scene_evidence,
                allow_bare_numeric_ui=bool(
                    getattr(track, "_ui_grid_split_child", False)
                ),
            )
            recognized_text = str(getattr(recognition, "text", "") or "")
            if (
                locally_accepted
                and requires_single_frame_cjk
                and _cjk_count(recognized_text) < 1
            ):
                locally_accepted = False
                last_reject = {
                    "reason": "single_frame_requires_local_cjk",
                    "role": role,
                    "text": recognized_text,
                    "confidence": float(
                        getattr(recognition, "confidence", 0.0) or 0.0
                    ),
                    "box": list(track.box_coords),
                }
            if locally_accepted:
                accepted = True
                accepted_sample_count += 1
                accepted_signatures.add(_local_text_timing_signature(recognized_text))
                if recognized_text.strip():
                    accepted_texts.append(recognized_text.strip())
                accepted_cjk_max = max(accepted_cjk_max, _cjk_count(recognized_text))
                if caption_lane:
                    setattr(track, "_sequential_caption_lane", True)
                if latin_card_evidence and _cjk_count(
                    str(getattr(recognition, "text", "") or "")
                ) == 0:
                    latin_editor_card_rescued_ids.add(id(track))
                if semantic_scene_evidence and _cjk_count(
                    str(getattr(recognition, "text", "") or "")
                ) == 0:
                    semantic_scene_label_rows[id(track)] = {
                        "semantic_role": "semantic_scene_label",
                        "start_frame": int(track.start_frame),
                        "end_frame": int(track.end_frame),
                        "box": list(track.box_coords),
                        "text": str(getattr(recognition, "text", "") or ""),
                        "confidence": float(
                            getattr(recognition, "confidence", 0.0) or 0.0
                        ),
                        "peer_evidence": semantic_peer_evidence.get(id(track), []),
                    }
                # Do not stop at the first positive sample.  A compact
                # screen-locked texture can decode as one plausible glyph in
                # one frame; provenance needs multi-frame consensus before it
                # is allowed to become an editor concealment authority.
                continue
            rejected_text = str(getattr(recognition, "text", "") or "")
            ascii_letters = sum(
                1
                for char in rejected_text
                if ("A" <= char <= "Z") or ("a" <= char <= "z")
            )
            last_reject = {
                "reason": (
                    "latin_text_without_editor_card_evidence"
                    if ascii_letters >= 2
                    and _cjk_count(rejected_text) == 0
                    and not latin_card_evidence
                    and not semantic_scene_evidence
                    else "local_text_reject"
                ),
                "role": role,
                "text": rejected_text,
                "confidence": float(
                    getattr(recognition, "confidence", 0.0) or 0.0
                ),
                "box": list(track.box_coords),
            }

        if accepted:
            setattr(track, "_local_text_consensus_count", int(accepted_sample_count))
            setattr(track, "_local_text_consensus_signatures", sorted(accepted_signatures))
            setattr(track, "_local_text_consensus_texts", sorted(set(accepted_texts)))
            setattr(track, "_local_text_cjk_max", int(accepted_cjk_max))
            if requires_single_frame_cjk:
                setattr(track, "_single_frame_cjk_confirmed", True)
            if source_scene_candidate:
                setattr(track, "_source_intrinsic_candidate", "moving_source_text")
            return True, None
        if not saw_crop:
            if wide_hardsub and not requires_single_frame_cjk:
                return True, None
            return False, {
                "reason": "empty_crop",
                "role": role,
                "box": list(track.box_coords),
            }
        if last_reject is not None:
            if (
                last_reject.get("reason") == "recognize_error"
                and wide_hardsub
                and not requires_single_frame_cjk
            ):
                return True, None
            # Bright-food OCR often returns blank on real stroke burn-ins.
            # Require strong glyph ink so soft food/lettuce bands stay out.
            if (
                wide_hardsub
                and not requires_single_frame_cjk
                and last_reject.get("reason") == "local_text_reject"
                and not str(last_reject.get("text") or "").strip()
            ):
                stroke_evidence = [
                    (
                        crop_ink_score(fr, track.box_coords),
                        crop_stroke_orientation_balance(fr, track.box_coords),
                    )
                    for fr in frame_candidates
                ]
                if any(
                    ink >= 6.0 and orientation_balance >= 0.45
                    for ink, orientation_balance in stroke_evidence
                ):
                    return True, None
                ink = max((row[0] for row in stroke_evidence), default=0.0)
                orientation_at_peak_ink = next(
                    (
                        orientation_balance
                        for row_ink, orientation_balance in stroke_evidence
                        if row_ink == ink
                    ),
                    0.0,
                )
                if ink >= 6.0:
                    # A wide confirmed hardsub is a recall-first authority;
                    # directional cloth/skin guards belong to compact UI
                    # provenance, not the bottom caption fallback.
                    return True, None
            return False, last_reject
        return False, {
            "reason": "local_text_reject",
            "role": role,
            "box": list(track.box_coords),
        }

    primary_kept: list[MergedTrack] = []
    deferred: list[MergedTrack] = []
    for track in expanded:
        keep, drop = _decide(track, has_peer=False)
        if keep:
            primary_kept.append(track)
            continue
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        if (
            drop is not None
            and drop.get("reason") == "low_hits"
            and role in {"mid_label", "ui_chip"}
            and int(track.hit_count) >= 3
        ):
            deferred.append(track)
        elif drop is not None:
            dropped_rows.append(drop)

    anchors: set[int] = set()
    for track in primary_kept:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        if (
            role in {"mid_label", "ui_chip"}
            and int(track.hit_count) >= min_hits_for_role(role)
            and is_horizontally_locked_track(
                track, frame_w=frame_w, frame_h=frame_h
            )
        ):
            anchors.add(_mid_column_bucket(track.box_coords, frame_w=frame_w))

    kept = list(primary_kept)
    for track in deferred:
        bucket = _mid_column_bucket(track.box_coords, frame_w=frame_w)
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        if bucket not in anchors:
            dropped_rows.append(
                {
                    "reason": "low_hits",
                    "role": role,
                    "hit_count": int(track.hit_count),
                    "need_hits": min_hits_for_role(role),
                    "box": list(track.box_coords),
                }
            )
            continue
        keep, drop = _decide(track, has_peer=True)
        if keep:
            kept.append(track)
        elif drop is not None:
            dropped_rows.append(drop)

    # Second pass: drop compact device-panel clusters that survived σ-lock.
    # Anchors = already-kept wide editor mids only (not doomed scene blobs).
    cluster_ids = compact_scene_ui_cluster_member_ids(
        expanded,
        frame_w=frame_w,
        frame_h=frame_h,
        anchor_tracks=kept,
    )
    if cluster_ids and not preserve_source_candidates:
        filtered: list[MergedTrack] = []
        for track in kept:
            if id(track) not in cluster_ids:
                filtered.append(track)
                continue
            role = classify_ocr_box_role(
                track.box_coords, frame_w=frame_w, frame_h=frame_h
            )
            sx, sy = track_centroid_sigma_xy(track)
            dropped_rows.append(
                {
                    "reason": "scene_ui_cluster",
                    "role": role,
                    "hit_count": int(track.hit_count),
                    "centroid_sigma_xy": [sx, sy],
                    "box": list(track.box_coords),
                }
            )
        kept = filtered
    elif cluster_ids:
        for track in kept:
            if id(track) in cluster_ids:
                setattr(track, "_source_intrinsic_candidate", "compact_source_ui_cluster")

    # Final provenance gate for isolated micro text. Temporal lock + readable
    # OCR alone cannot distinguish an editor chip from print on a static
    # appliance/object. Keep only when the surrounding editor layout provides
    # independent evidence; retain every rejection in QA.
    isolated_source_ids = isolated_micro_source_text_member_ids(
        kept,
        frame_w=frame_w,
        frame_h=frame_h,
    )
    if isolated_source_ids and not preserve_source_candidates:
        filtered = []
        for track in kept:
            if id(track) not in isolated_source_ids:
                filtered.append(track)
                continue
            role = classify_ocr_box_role(
                track.box_coords, frame_w=frame_w, frame_h=frame_h
            )
            sx, sy = track_centroid_sigma_xy(track)
            dropped_rows.append(
                {
                    "reason": "isolated_micro_source_text",
                    "role": role,
                    "hit_count": int(track.hit_count),
                    "centroid_sigma_xy": [sx, sy],
                    "box": list(track.box_coords),
                }
            )
        kept = filtered
    elif isolated_source_ids:
        for track in kept:
            if id(track) in isolated_source_ids:
                setattr(track, "_source_intrinsic_candidate", "isolated_micro_source_text")

    return kept, {
        "dropped": len(dropped_rows),
        "rows": dropped_rows,
        "preserved_source_candidates": sum(
            1
            for track in kept
            if id(track) in dense_source_panel_ids
            or bool(getattr(track, "_source_intrinsic_candidate", None))
        ),
        "dense_source_panel_candidates": len(dense_source_panel_ids),
        "sequential_caption_lane_candidates": len(caption_lane_ids),
        "hardsub_recovery": {
            "applied": len(hardsub_recovery_rows),
            "dense_ui_grid_skips": dense_ui_grid_recovery_skips,
            "rows": hardsub_recovery_rows,
        },
        "latin_editor_card": {
            "solid_panel_candidates": len(colored_panel_ids),
            "temporal_peer_candidates": len(latin_editor_card_peer_ids),
            "rescued_tracks": len(latin_editor_card_rescued_ids),
        },
        "semantic_scene_label": {
            "geometry_candidates": len(semantic_candidates),
            "peer_candidates": len(semantic_scene_label_peer_ids),
            "rescued_tracks": len(semantic_scene_label_rows),
            "rows": list(semantic_scene_label_rows.values()),
        },
    }


def _local_text_timing_signature(text: str) -> str:
    """Normalize local OCR evidence used only for timing.

    CJK/digit signatures retain the closed v58 behavior. Pure Latin copy is
    normalized only after the false-positive gate has admitted its track, which
    currently requires changing solid-color editor-card evidence.
    """
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    cjk_digit = "".join(
        char
        for char in normalized
        if ("\u4e00" <= char <= "\u9fff") or char.isdigit()
    )
    if cjk_digit:
        return cjk_digit
    return "".join(char.lower() for char in normalized if char.isascii() and char.isalnum())


def _local_text_signatures_match(left: str, right: str) -> bool:
    """Cluster OCR variants without hiding short, meaningful substitutions."""
    a = str(left or "")
    b = str(right or "")
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    # Missing edge/interior glyphs are a common CTC failure. Containment is
    # safe when most of the longer signature remains.
    if shorter in longer and len(shorter) >= 2:
        return len(shorter) / float(len(longer)) >= 0.60
    # For short captions, one substituted CJK glyph may be the whole semantic
    # change (第一句 vs 第二句). Only long strings get fuzzy substitution rescue.
    if max(len(a), len(b)) < 7:
        return False
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.86


def _measurement_label_ocr_variants_match(left: str, right: str) -> bool:
    """Match minor CTC variants of one measured ingredient editor label.

    Amount labels often decode ``250g虾仁`` as ``250g仁`` or ``230g仁`` on
    glare/occlusion frames. Merge only when both sides visibly contain a
    measurement token, digit strings differ by at most one substitution, and
    the CJK name is equal or missing at most one glyph by containment. Distinct
    ingredient names therefore remain eligible for a real timing split.
    """
    a = str(left or "").strip()
    b = str(right or "").strip()
    if not a or not b or not _has_burnin_measure_unit(a) or not _has_burnin_measure_unit(b):
        return False
    a_digits = "".join(char for char in a if char.isdigit())
    b_digits = "".join(char for char in b if char.isdigit())
    if not a_digits or len(a_digits) != len(b_digits):
        return False
    if sum(x != y for x, y in zip(a_digits, b_digits)) > 1:
        return False
    a_cjk = "".join(char for char in a if "\u4e00" <= char <= "\u9fff")
    b_cjk = "".join(char for char in b if "\u4e00" <= char <= "\u9fff")
    if not a_cjk or not b_cjk:
        return False
    if a_cjk == b_cjk:
        return True
    shorter, longer = (
        (a_cjk, b_cjk) if len(a_cjk) <= len(b_cjk) else (b_cjk, a_cjk)
    )
    return shorter in longer and len(longer) - len(shorter) <= 1


def _overlapping_content_signatures_match(left: str, right: str) -> bool:
    """OCR-error-tolerant match allowed only with independent time overlap."""
    if _local_text_signatures_match(left, right):
        return True
    a = str(left or "")
    b = str(right or "")
    if min(len(a), len(b)) < 4:
        return False
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    longest = max((block.size for block in matcher.get_matching_blocks()), default=0)
    return matcher.ratio() >= 0.60 and longest / float(min(len(a), len(b))) >= 0.40


def _local_recognition_is_timing_evidence(recognition: Any, *, role: str) -> bool:
    text = str(getattr(recognition, "text", "") or "")
    signature = _local_text_timing_signature(text)
    if len(signature) < 2:
        return False
    # Bare digits are not accepted hardsub content by the false-positive gate
    # and must not become a new caption merely because the weaker timing path
    # decoded two texture glyphs (for example a pan pattern as ``88``).
    if role == "hardsub" and _cjk_count(text) == 0:
        return local_text_accepts_track(recognition, role=role)
    confidence = float(getattr(recognition, "confidence", 0.0) or 0.0)
    valid_ratio = float(getattr(recognition, "valid_char_ratio", 0.0) or 0.0)
    if local_text_accepts_track(recognition, role=role):
        return True
    # Timing may use slightly weaker CTC evidence than the false-positive gate,
    # but never a blank, single glyph, or mostly-invalid decode.
    confidence_floor = 0.34 if role == "hardsub" else 0.40
    return confidence >= confidence_floor and valid_ratio >= 0.45


def _track_segment_from_text_evidence(
    track: MergedTrack,
    *,
    start_frame: int,
    end_frame: int,
    representative_frame: int,
    frame_cache: Mapping[int, np.ndarray],
    frame_w: int,
    frame_h: int,
    timing_evidence_frames: Sequence[int] = (),
) -> MergedTrack:
    """Rebuild a geometry track using detector evidence inside one text span."""
    selected_boxes: list[tuple[float, float, float, float]] = []
    selected_frames: list[int] = []
    selected_sharpness: list[float] = []
    for index, raw_frame in enumerate(track.hit_frames):
        frame_index = int(raw_frame)
        if frame_index < int(start_frame) or frame_index > int(end_frame):
            continue
        if index < len(track.hit_boxes):
            selected_boxes.append(
                tuple(float(value) for value in track.hit_boxes[index][:4])
            )
            selected_frames.append(frame_index)
            selected_sharpness.append(
                float(track.hit_sharpness[index])
                if index < len(track.hit_sharpness)
                else 0.0
            )

    if not selected_boxes:
        selected_boxes = [tuple(float(value) for value in track.box_coords[:4])]
        selected_frames = [int(representative_frame)]
        frame = frame_cache.get(int(representative_frame))
        selected_sharpness = [
            crop_box_sharpness(frame, track.box_coords) if frame is not None else 0.0
        ]

    expansive = _hardsub_should_use_expansive_stable(selected_boxes)
    box = _stable_box_prefer_hardsub_lines(
        selected_boxes,
        current=track.box_coords,
        frame_w=frame_w,
        frame_h=frame_h,
        expansive=expansive,
    )
    selected_frame_set = {int(value) for value in selected_frames}
    for raw_frame in timing_evidence_frames:
        frame_index = int(raw_frame)
        if (
            frame_index < int(start_frame)
            or frame_index > int(end_frame)
            or frame_index in selected_frame_set
        ):
            continue
        frame = frame_cache.get(frame_index)
        selected_boxes.append(tuple(float(value) for value in box[:4]))
        selected_frames.append(frame_index)
        selected_sharpness.append(
            crop_box_sharpness(frame, box) if frame is not None else 0.0
        )
        selected_frame_set.add(frame_index)
    best_index = max(
        range(len(selected_frames)),
        key=lambda index: (
            selected_sharpness[index],
            -abs(selected_frames[index] - int(representative_frame)),
        ),
    )
    return MergedTrack(
        start_frame=int(start_frame),
        end_frame=int(end_frame),
        box_coords=box,
        best_frame_index=int(selected_frames[best_index]),
        best_sharpness=float(selected_sharpness[best_index]),
        centroid=_box_centroid(box),
        hit_count=len(selected_boxes),
        hit_boxes=selected_boxes,
        hit_frames=selected_frames,
        hit_sharpness=selected_sharpness,
    )


def split_tracks_by_local_text_change(
    tracks: Sequence[MergedTrack],
    *,
    frame_cache: Mapping[int, np.ndarray],
    frame_w: int,
    frame_h: int,
    recognizer: Any | None,
    source: Path | None = None,
    batch_size: int = 32,
    min_cluster_support: int = 2,
    max_samples_per_track: int | None = None,
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """
    Split geometry-stable tracks when local OCR proves the text content changed.

    Local OCR is a timing fingerprint only; Phase 2 Cloud OCR remains content
    authority. Unsupported/glitch clusters fail soft and cannot create tracks.
    """
    audit: dict[str, Any] = {
        "method": "local_text_content_timing_v1",
        "recognizer_available": recognizer is not None,
        "before_count": len(tracks),
        "after_count": len(tracks),
        "split_tracks": 0,
        "trimmed_tracks": 0,
        "segments_created": 0,
        "dropped_unverified_edge_hardsubs": 0,
        "dropped_unverified_sparse_compact_tracks": 0,
        "dropped_sparse_hardsub_shadows": 0,
        "dropped_ocr_only_segments": 0,
        "dropped_sparse_variant_scene_tracks": 0,
        "dropped_ambiguous_scene_tracks": 0,
        "suppressed_nested_ocr_glitches": 0,
        "coalesced_overlapping_content_variants": 0,
        "rows": [],
    }
    if recognizer is None:
        return list(tracks), audit

    output: list[MergedTrack] = []
    scene_seed_regions: list[tuple[int, int, tuple[float, float]]] = []
    for track in tracks:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        frame_indices: list[int] = []
        crops: list[np.ndarray] = []
        start_frame = int(track.start_frame)
        end_frame = int(track.end_frame)
        candidate_frame_indices = list(range(start_frame, end_frame + 1))
        if (
            max_samples_per_track is not None
            and len(candidate_frame_indices) > max(3, int(max_samples_per_track))
        ):
            sample_count = max(3, int(max_samples_per_track))
            uniform = [
                int(value)
                for value in np.linspace(
                    start_frame,
                    end_frame,
                    num=sample_count,
                    dtype=np.int64,
                )
            ]
            anchors = [
                start_frame,
                int(track.best_frame_index),
                end_frame,
            ]
            candidate_frame_indices = sorted(
                {
                    value
                    for value in [*uniform, *anchors]
                    if start_frame <= int(value) <= end_frame
                }
            )
        for frame_index in candidate_frame_indices:
            frame = _boundary_frame(
                frame_index, frame_cache=frame_cache, source=source
            )
            crop = (
                _crop_xyxy_from_frame(frame, track.box_coords)
                if frame is not None
                else None
            )
            if crop is None or crop.size < 16:
                continue
            frame_indices.append(frame_index)
            crops.append(crop)

        recognitions: list[Any] = []
        recognition_error: str | None = None
        try:
            size = max(1, int(batch_size))
            for offset in range(0, len(crops), size):
                batch = crops[offset : offset + size]
                batch_results = list(recognizer.recognize_batch(batch))
                if len(batch_results) != len(batch):
                    raise RuntimeError(
                        "local recognizer batch size mismatch "
                        f"input={len(batch)} output={len(batch_results)}"
                    )
                recognitions.extend(batch_results)
        except Exception as exc:  # noqa: BLE001
            recognition_error = str(exc)
            logger.warning(
                "phase1_content_timing_recognize_failed span=%s-%s err=%s",
                track.start_frame,
                track.end_frame,
                exc,
            )

        row: dict[str, Any] = {
            "prior_span": [int(track.start_frame), int(track.end_frame)],
            "role": role,
            "frames_attempted": len(crops),
            "action": "unchanged",
            "clusters": [],
        }
        if recognition_error is not None or len(recognitions) != len(frame_indices):
            row["reason"] = "recognizer_error"
            if recognition_error:
                row["error"] = recognition_error
            audit["rows"].append(row)
            output.append(track)
            continue

        clusters: list[dict[str, Any]] = []
        strong_single_glyph_frames: dict[str, list[int]] = {}
        for frame_index, recognition in zip(frame_indices, recognitions):
            raw_text = str(getattr(recognition, "text", "") or "").strip()
            raw_signature = _local_text_timing_signature(raw_text)
            if (
                len(raw_signature) == 1
                and _cjk_count(raw_text) == 1
                and local_text_accepts_track(recognition, role=role)
            ):
                strong_single_glyph_frames.setdefault(raw_signature, []).append(
                    int(frame_index)
                )
            if not _local_recognition_is_timing_evidence(recognition, role=role):
                continue
            text = raw_text
            signature = _local_text_timing_signature(text)
            confidence = float(getattr(recognition, "confidence", 0.0) or 0.0)
            matching = [
                cluster
                for cluster in clusters
                if _local_text_signatures_match(signature, str(cluster["signature"]))
                or (
                    role in {"mid_label", "ui_chip"}
                    and _measurement_label_ocr_variants_match(
                        text, str(cluster["representative_text"])
                    )
                )
            ]
            if matching:
                cluster = max(
                    matching,
                    key=lambda item: SequenceMatcher(
                        None, signature, str(item["signature"]), autojunk=False
                    ).ratio(),
                )
            else:
                cluster = {
                    "signature": signature,
                    "representative_text": text,
                    "representative_confidence": confidence,
                    "frames": [],
                }
                clusters.append(cluster)
            cluster["frames"].append(int(frame_index))
            if (confidence, len(signature)) > (
                float(cluster["representative_confidence"]),
                len(str(cluster["signature"])),
            ):
                cluster["signature"] = signature
                cluster["representative_text"] = text
                cluster["representative_confidence"] = confidence

        reliable: list[dict[str, Any]] = []
        for cluster in clusters:
            frames = sorted({int(value) for value in cluster["frames"]})
            if len(frames) < max(2, int(min_cluster_support)):
                continue
            span = max(1, frames[-1] - frames[0] + 1)
            density = len(frames) / float(span)
            if density < 0.35 and len(frames) < 4:
                continue
            cluster["frames"] = frames
            cluster["span"] = [frames[0], frames[-1]]
            cluster["support"] = len(frames)
            cluster["density"] = density
            reliable.append(cluster)

        # Local OCR is timing evidence, not geometry authority. It may extend a
        # detector-anchored segment through missed frames, but it must not mint a
        # standalone segment whose entire content run is disjoint from every
        # detector hit on the parent track. That mismatch is typical of scene
        # print crossing the inherited crop during a cut/pan.
        detector_hit_frames = {int(value) for value in track.hit_frames}
        unsupported_ocr_only = []
        if role != "hardsub":
            unsupported_ocr_only = [
                cluster
                for cluster in reliable
                if not detector_hit_frames.intersection(
                    int(value) for value in cluster["frames"]
                )
            ]
        if unsupported_ocr_only:
            unsupported_ids = {id(cluster) for cluster in unsupported_ocr_only}
            reliable = [
                cluster for cluster in reliable if id(cluster) not in unsupported_ids
            ]
            audit["dropped_ocr_only_segments"] += len(unsupported_ocr_only)
            row["unsupported_ocr_only_clusters"] = [
                {
                    "signature": str(cluster["signature"]),
                    "span": list(cluster["span"]),
                    "support": int(cluster["support"]),
                }
                for cluster in unsupported_ocr_only
            ]
            if not reliable:
                row["action"] = "drop_ocr_only_segment"
                row["reason"] = "no_detector_seed_in_ocr_content_span"
                audit["rows"].append(row)
                continue

        original_reliable_order = sorted(
            reliable, key=lambda cluster: (cluster["span"][0], cluster["span"][1])
        )
        content_was_ambiguous = len(original_reliable_order) >= 2 and not all(
            int(left["span"][1]) < int(right["span"][0])
            for left, right in zip(
                original_reliable_order, original_reliable_order[1:]
            )
        )
        nested_glitch_ids: set[int] = set()
        for cluster in reliable:
            c_start, c_end = (int(value) for value in cluster["span"])
            c_support = int(cluster["support"])
            if c_support > 3:
                continue
            for host in reliable:
                if host is cluster:
                    continue
                h_start, h_end = (int(value) for value in host["span"])
                if h_start <= c_start and c_end <= h_end and (
                    h_start < c_start or c_end < h_end
                ):
                    if int(host["support"]) >= max(8, 4 * c_support):
                        nested_glitch_ids.add(id(cluster))
                        break
        if nested_glitch_ids:
            audit["suppressed_nested_ocr_glitches"] += len(nested_glitch_ids)
            reliable = [
                cluster for cluster in reliable if id(cluster) not in nested_glitch_ids
            ]

        # OCR on a geometry-stable caption row can produce two near-identical
        # variants for the same visible text (for example a single character
        # flip during a hand/scene transition).  Treating that overlap as an
        # ambiguous ordering poisons the whole parent track: the renderer then
        # keeps the parent candidate alive for its full span and overlays one
        # translation over unrelated captions.  Coalesce only a high-overlap,
        # high-similarity pair; genuinely different captions remain split and
        # continue through the normal non-overlapping path.
        coalesced_variant_ids: set[int] = set()
        coalesced_variants = 0
        for index, left in enumerate(reliable):
            if id(left) in coalesced_variant_ids:
                continue
            left_start, left_end = (int(value) for value in left["span"])
            left_length = max(1, left_end - left_start + 1)
            for right in reliable[index + 1 :]:
                if id(right) in coalesced_variant_ids:
                    continue
                right_start, right_end = (int(value) for value in right["span"])
                overlap = max(0, min(left_end, right_end) - max(left_start, right_start) + 1)
                right_length = max(1, right_end - right_start + 1)
                overlap_ratio = overlap / float(min(left_length, right_length))
                similarity = SequenceMatcher(
                    None,
                    str(left["signature"]),
                    str(right["signature"]),
                    autojunk=False,
                ).ratio()
                if overlap_ratio < 0.80 or similarity < 0.65:
                    continue
                # Keep the stronger OCR variant as the representative, while
                # preserving the union of its timing evidence.
                stronger, weaker = (
                    (left, right)
                    if int(left["support"]) >= int(right["support"])
                    else (right, left)
                )
                stronger["frames"] = sorted(
                    {int(value) for value in stronger["frames"]}
                    | {int(value) for value in weaker["frames"]}
                )
                stronger["span"] = [
                    int(stronger["frames"][0]),
                    int(stronger["frames"][-1]),
                ]
                stronger["support"] = len(stronger["frames"])
                stronger["density"] = stronger["support"] / float(
                    max(1, stronger["span"][1] - stronger["span"][0] + 1)
                )
                coalesced_variant_ids.add(id(weaker))
                coalesced_variants += 1
        if coalesced_variant_ids:
            reliable = [
                cluster for cluster in reliable if id(cluster) not in coalesced_variant_ids
            ]
        if coalesced_variants:
            audit["coalesced_overlapping_content_variants"] += coalesced_variants

        reliable.sort(key=lambda cluster: (cluster["span"][0], cluster["span"][1]))
        row["clusters"] = [
            {
                "representative_text": str(cluster["representative_text"]),
                "signature": str(cluster["signature"]),
                "support": int(cluster["support"]),
                "span": list(cluster["span"]),
                "density": round(float(cluster["density"]), 4),
            }
            for cluster in reliable
        ]
        non_overlapping = all(
            int(left["span"][1]) < int(right["span"][0])
            for left, right in zip(reliable, reliable[1:])
        )

        strong_single_glyph_consensus = False
        for values in strong_single_glyph_frames.values():
            frames = sorted({int(value) for value in values})
            if len(frames) < 2:
                continue
            glyph_span = max(1, frames[-1] - frames[0] + 1)
            # Repeated scene texture can hallucinate the same CJK every other
            # frame. Editor glyphs produce a temporally dense accepted run.
            if len(frames) / float(glyph_span) >= 0.75:
                strong_single_glyph_consensus = True
                break

        evidence = track_boundary_evidence(
            track, frame_w=frame_w, frame_h=frame_h
        )
        x0, y0, x1, y1 = (float(value) for value in track.box_coords[:4])
        fw = max(1.0, float(frame_w))
        fh = max(1.0, float(frame_h))
        evidence_reasons = set(evidence.get("reasons", []))
        signatures = [str(cluster["signature"]) for cluster in reliable]
        # A sparse, OCR-blank hardsub slab immediately beside a dense real line
        # is a detector shadow (food/edge texture or outline spill), not a second
        # caption. Require an independently dense overlapping peer so a lone
        # short editor caption remains recall-first.
        sparse_hardsub_shadow = False
        if (
            role == "hardsub"
            and not reliable
            and "sparse_temporal_evidence" in evidence_reasons
            and ((x1 - x0) / fw) >= 0.35
        ):
            candidate_hit_frames = {int(value) for value in track.hit_frames}
            for peer in tracks:
                if peer is track:
                    continue
                if classify_ocr_box_role(
                    peer.box_coords, frame_w=frame_w, frame_h=frame_h
                ) != "hardsub":
                    continue
                peer_evidence = track_boundary_evidence(
                    peer, frame_w=frame_w, frame_h=frame_h
                )
                if float(peer_evidence.get("hit_density") or 0.0) < 0.75:
                    continue
                peer_hit_frames = {int(value) for value in peer.hit_frames}
                if len(candidate_hit_frames.intersection(peer_hit_frames)) < 2:
                    continue
                px0, py0, px1, py1 = (
                    float(value) for value in peer.box_coords[:4]
                )
                horizontal_overlap = max(0.0, min(x1, px1) - max(x0, px0))
                if horizontal_overlap / max(1.0, min(x1 - x0, px1 - px0)) < 0.50:
                    continue
                vertical_gap = max(0.0, max(y0, py0) - min(y1, py1))
                candidate_cy = (y0 + y1) * 0.5
                peer_cy = (py0 + py1) * 0.5
                if vertical_gap > 0.015 * fh or abs(candidate_cy - peer_cy) > 0.08 * fh:
                    continue
                sparse_hardsub_shadow = True
                break
        if sparse_hardsub_shadow:
            audit["dropped_sparse_hardsub_shadows"] += 1
            row["action"] = "drop_sparse_hardsub_shadow"
            row["reason"] = "blank_sparse_band_beside_dense_caption"
            audit["rows"].append(row)
            continue
        short_variant_sequence = (
            role in {"mid_label", "ui_chip"}
            and len(reliable) >= 2
            and non_overlapping
            and "sparse_temporal_evidence" in evidence_reasons
            and ((x1 - x0) / fw) <= 0.06
            and ((y1 - y0) / fh) <= 0.04
            and all(2 <= len(signature) <= 4 for signature in signatures)
            and all(
                SequenceMatcher(None, left, right, autojunk=False).ratio() >= 0.60
                for left, right in zip(signatures, signatures[1:])
            )
        )
        if short_variant_sequence:
            audit["dropped_sparse_variant_scene_tracks"] += 1
            row["action"] = "drop_sparse_variant_scene_track"
            row["reason"] = "sparse_near_duplicate_content_variants"
            audit["rows"].append(row)
            scene_seed_regions.append(
                (
                    int(track.start_frame),
                    int(track.end_frame),
                    _box_centroid(track.box_coords),
                )
            )
            continue

        # Re-evaluate ambiguity after variant coalescing.  The pre-coalescing
        # signal is intentionally not authoritative: it may be caused solely
        # by the OCR variant pair handled above.
        content_was_ambiguous = len(reliable) >= 2 and not non_overlapping
        ambiguous_content = content_was_ambiguous
        tcx, tcy = _box_centroid(track.box_coords)
        near_scene_seed = any(
            not (
                int(track.end_frame) < seed_start
                or seed_end < int(track.start_frame)
            )
            and ((tcx - scx) ** 2 + (tcy - scy) ** 2) ** 0.5
            <= 0.20 * min(fw, fh)
            for seed_start, seed_end, (scx, scy) in scene_seed_regions
        )
        ambiguous_scene_track = (
            role in {"mid_label", "ui_chip", "generic"}
            and ambiguous_content
            and (
                "sparse_temporal_evidence" in evidence_reasons
                or near_scene_seed
            )
        )
        if ambiguous_scene_track:
            audit["dropped_ambiguous_scene_tracks"] += 1
            row["action"] = "drop_ambiguous_scene_track"
            row["reason"] = (
                "sparse_ambiguous_content"
                if "sparse_temporal_evidence" in evidence_reasons
                else "nearby_scene_seed"
            )
            audit["rows"].append(row)
            scene_seed_regions.append(
                (
                    int(track.start_frame),
                    int(track.end_frame),
                    (tcx, tcy),
                )
            )
            continue

        sparse_compact_without_consensus = (
            role in {"mid_label", "ui_chip"}
            and ((x1 - x0) / fw) <= 0.08
            and ((y1 - y0) / fh) <= 0.06
            and "sparse_temporal_evidence" in evidence_reasons
            and not reliable
            and not strong_single_glyph_consensus
        )
        if sparse_compact_without_consensus and len(frame_indices) >= 2:
            audit["dropped_unverified_sparse_compact_tracks"] += 1
            row["action"] = "drop_unverified_sparse_compact_track"
            row["reason"] = "no_multiframe_text_consensus"
            audit["rows"].append(row)
            continue

        # A wide hardsub that lands flush on a frame edge is a common recovery
        # failure: food/wood texture becomes a huge padded line even though a
        # single-frame OCR hallucination let it through the recall-first gate.
        # Normal/centered geometry still fails soft. Edge-padded geometry must
        # instead have independent multi-frame content consensus; a real
        # left-/right-aligned editor caption satisfies the same requirement.
        edge_limit = max(2.0, 0.00625 * fw)
        edge_padded_wide_hardsub = (
            _box_looks_like_thin_hardsub(
                track.box_coords, frame_w=frame_w, frame_h=frame_h
            )
            and ((x1 - x0) / fw) >= 0.35
            and (x0 <= edge_limit or x1 >= fw - edge_limit)
        )
        if (
            edge_padded_wide_hardsub
            and len(frame_indices) >= max(2, int(min_cluster_support))
            and not reliable
        ):
            audit["dropped_unverified_edge_hardsubs"] += 1
            row["action"] = "drop_unverified_edge_hardsub"
            row["reason"] = "no_multiframe_text_consensus"
            audit["rows"].append(row)
            continue

        # Interleaved reliable clusters are ambiguous OCR, not a subtitle change.
        if len(reliable) >= 2 and non_overlapping:
            created: list[MergedTrack] = []
            for cluster in reliable:
                start_frame, end_frame = (int(value) for value in cluster["span"])
                representative_frame = max(
                    cluster["frames"],
                    key=lambda value: -abs(
                        int(value) - (start_frame + end_frame) // 2
                    ),
                )
                created.append(
                    _track_segment_from_text_evidence(
                        track,
                        start_frame=start_frame,
                        end_frame=end_frame,
                        representative_frame=int(representative_frame),
                        frame_cache=frame_cache,
                        frame_w=frame_w,
                        frame_h=frame_h,
                        timing_evidence_frames=cluster["frames"],
                    )
                )
            output.extend(created)
            audit["split_tracks"] += 1
            audit["segments_created"] += len(created)
            row["action"] = "split"
            row["result_spans"] = [
                [segment.start_frame, segment.end_frame] for segment in created
            ]
            audit["rows"].append(row)
            continue

        if len(reliable) == 1:
            cluster = reliable[0]
            start_frame, end_frame = (int(value) for value in cluster["span"])
            left_blank = start_frame - int(track.start_frame)
            right_blank = int(track.end_frame) - end_frame
            clear_edge = max(left_blank, right_blank) >= 2
            prior_length = int(track.end_frame) - int(track.start_frame) + 1
            short_dense_edge = (
                prior_length <= 8
                and clear_edge
                and int(cluster["support"]) >= 2
                and float(cluster["density"]) >= 0.75
            )
            if (
                clear_edge
                and (
                    short_dense_edge
                    or (
                        int(cluster["support"]) >= 3
                        and float(cluster["density"]) >= 0.50
                    )
                )
            ):
                representative_frame = int(cluster["frames"][len(cluster["frames"]) // 2])
                trimmed = _track_segment_from_text_evidence(
                    track,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    representative_frame=representative_frame,
                    frame_cache=frame_cache,
                    frame_w=frame_w,
                    frame_h=frame_h,
                    timing_evidence_frames=cluster["frames"],
                )
                output.append(trimmed)
                audit["trimmed_tracks"] += 1
                audit["segments_created"] += 1
                row["action"] = "trim"
                row["result_spans"] = [[start_frame, end_frame]]
                audit["rows"].append(row)
                continue

            if (
                prior_length <= 8
                and int(cluster["support"]) >= 2
                and float(cluster["density"]) >= 0.75
                and start_frame == int(track.start_frame)
                and end_frame == int(track.end_frame)
            ):
                representative_frame = int(
                    cluster["frames"][len(cluster["frames"]) // 2]
                )
                seeded = _track_segment_from_text_evidence(
                    track,
                    start_frame=int(track.start_frame),
                    end_frame=int(track.end_frame),
                    representative_frame=representative_frame,
                    frame_cache=frame_cache,
                    frame_w=frame_w,
                    frame_h=frame_h,
                    timing_evidence_frames=cluster["frames"],
                )
                output.append(seeded)
                row["action"] = "timing_seed"
                row["result_spans"] = [
                    [int(track.start_frame), int(track.end_frame)]
                ]
                audit["rows"].append(row)
                continue

        row["reason"] = (
            "ambiguous_cluster_order"
            if len(reliable) >= 2 and not non_overlapping
            else "insufficient_change_evidence"
        )
        audit["rows"].append(row)
        output.append(track)

    output.sort(key=lambda track: (track.start_frame, track.box_coords[0]))
    audit["after_count"] = len(output)
    return output, audit


def coalesce_tracks_by_local_text_content(
    tracks: Sequence[MergedTrack],
    *,
    frame_cache: Mapping[int, np.ndarray],
    frame_w: int,
    frame_h: int,
    recognizer: Any | None,
    source: Path | None = None,
    batch_size: int = 32,
    max_gap_frames: int = 1,
    geometry_normalized: bool = False,
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """Reconcile fragmented geometry tracks that carry the same editor text."""
    audit: dict[str, Any] = {
        "method": "local_text_cross_track_reconcile_v1",
        "recognizer_available": recognizer is not None,
        "before_count": len(tracks),
        "after_count": len(tracks),
        "merged_tracks": 0,
        "geometry_normalized": bool(geometry_normalized),
        "rows": [],
    }
    if recognizer is None or len(tracks) <= 1:
        return list(tracks), audit

    requests: list[tuple[int, int, np.ndarray]] = []
    for track_index, track in enumerate(tracks):
        candidates: list[int] = [int(track.best_frame_index)]
        hits = sorted({int(value) for value in track.hit_frames})
        if hits:
            candidates.extend([hits[len(hits) // 2], hits[0], hits[-1]])
        seen: set[int] = set()
        for frame_index in candidates:
            if frame_index in seen:
                continue
            seen.add(frame_index)
            frame = _boundary_frame(
                frame_index, frame_cache=frame_cache, source=source
            )
            crop = (
                _crop_xyxy_from_frame(frame, track.box_coords)
                if frame is not None
                else None
            )
            if crop is None or crop.size < 16:
                continue
            requests.append((track_index, frame_index, crop))
            if len(seen) >= 3:
                break

    results: list[Any] = []
    try:
        size = max(1, int(batch_size))
        crops = [item[2] for item in requests]
        for offset in range(0, len(crops), size):
            batch = crops[offset : offset + size]
            batch_results = list(recognizer.recognize_batch(batch))
            if len(batch_results) != len(batch):
                raise RuntimeError(
                    "local recognizer batch size mismatch "
                    f"input={len(batch)} output={len(batch_results)}"
                )
            results.extend(batch_results)
    except Exception as exc:  # noqa: BLE001
        logger.warning("phase1_content_reconcile_recognize_failed err=%s", exc)
        audit["error"] = str(exc)
        return list(tracks), audit

    evidence_by_track: dict[int, list[tuple[str, str, float]]] = {}
    for request, recognition in zip(requests, results):
        track_index = int(request[0])
        role = classify_ocr_box_role(
            tracks[track_index].box_coords,
            frame_w=frame_w,
            frame_h=frame_h,
        )
        if not _local_recognition_is_timing_evidence(recognition, role=role):
            continue
        text = str(getattr(recognition, "text", "") or "").strip()
        signature = _local_text_timing_signature(text)
        confidence = float(getattr(recognition, "confidence", 0.0) or 0.0)
        evidence_by_track.setdefault(track_index, []).append(
            (signature, text, confidence)
        )

    representative: dict[int, tuple[str, str, float]] = {}
    for track_index, rows in evidence_by_track.items():
        clusters: list[list[tuple[str, str, float]]] = []
        for row in rows:
            matching = next(
                (
                    cluster
                    for cluster in clusters
                    if _local_text_signatures_match(row[0], cluster[0][0])
                ),
                None,
            )
            if matching is None:
                clusters.append([row])
            else:
                matching.append(row)
        cluster = max(
            clusters,
            key=lambda values: (
                len(values),
                max(value[2] for value in values),
                max(len(value[0]) for value in values),
            ),
        )
        representative[track_index] = max(
            cluster, key=lambda value: (value[2], len(value[0]))
        )

    indexed = sorted(
        enumerate(tracks),
        key=lambda item: (item[1].start_frame, item[1].box_coords[1]),
    )
    groups: list[tuple[MergedTrack, str, str, list[int]]] = []
    for track_index, track in indexed:
        evidence = representative.get(track_index)
        merged = False
        if evidence is not None:
            signature, text, _confidence = evidence
            tx0, ty0, tx1, ty1 = (float(value) for value in track.box_coords[:4])
            tcy = 0.5 * (ty0 + ty1)
            tw = max(1.0, tx1 - tx0)
            for group_index, (host, host_signature, host_text, members) in enumerate(groups):
                temporal_gap = max(
                    0,
                    max(int(track.start_frame), int(host.start_frame))
                    - min(int(track.end_frame), int(host.end_frame))
                    - 1,
                )
                overlap_frames = max(
                    0,
                    min(int(track.end_frame), int(host.end_frame))
                    - max(int(track.start_frame), int(host.start_frame))
                    + 1,
                )
                if overlap_frames < 1 and temporal_gap > max(0, int(max_gap_frames)):
                    continue
                hx0, hy0, hx1, hy1 = (
                    float(value) for value in host.box_coords[:4]
                )
                hcy = 0.5 * (hy0 + hy1)
                if abs(tcy - hcy) > max(18.0, 0.04 * float(frame_h)):
                    continue
                horizontal_overlap = max(0.0, min(tx1, hx1) - max(tx0, hx0))
                horizontal_ratio = horizontal_overlap / max(
                    1.0, min(tw, hx1 - hx0)
                )
                vertical_overlap = max(0.0, min(ty1, hy1) - max(ty0, hy0))
                vertical_ratio = vertical_overlap / max(
                    1.0, min(ty1 - ty0, hy1 - hy0)
                )
                both_hardsub = _box_looks_like_thin_hardsub(
                    track.box_coords, frame_w=frame_w, frame_h=frame_h
                ) and _box_looks_like_thin_hardsub(
                    host.box_coords, frame_w=frame_w, frame_h=frame_h
                )
                if geometry_normalized and both_hardsub:
                    same_row_center = abs(tcy - hcy) <= max(
                        4.0, 0.015 * float(frame_h)
                    )
                    if vertical_ratio < 0.55 and not same_row_center:
                        # OCR equality cannot re-attach a vertically offset
                        # detector shadow after ink geometry was normalized.
                        continue
                if horizontal_ratio < 0.55 and not both_hardsub:
                    continue
                strict_content_match = _local_text_signatures_match(
                    signature, host_signature
                )
                shorter_signature, longer_signature = (
                    (signature, host_signature)
                    if len(signature) <= len(host_signature)
                    else (host_signature, signature)
                )
                adjacent_prefix_match = (
                    overlap_frames == 0
                    and temporal_gap <= 1
                    and both_hardsub
                    and horizontal_ratio >= 0.50
                    and len(shorter_signature) >= 4
                    and shorter_signature in longer_signature
                )
                shorter_span = min(
                    int(track.end_frame) - int(track.start_frame) + 1,
                    int(host.end_frame) - int(host.start_frame) + 1,
                )
                overlap_ratio = overlap_frames / float(max(1, shorter_span))
                overlap_fuzzy_match = (
                    overlap_frames >= 2
                    and overlap_ratio >= 0.25
                    and
                    _overlapping_content_signatures_match(
                        signature, host_signature
                    )
                )
                geometry_fragment_match = (
                    both_hardsub
                    and overlap_frames >= 2
                    and overlap_ratio >= 0.50
                    and horizontal_ratio >= 0.50
                )
                overlapping_prefix_fragment_match = (
                    both_hardsub
                    and overlap_frames >= 2
                    and overlap_ratio >= 0.50
                    and horizontal_ratio >= 0.15
                    and len(shorter_signature) >= 2
                    and (
                        longer_signature.startswith(shorter_signature)
                        or longer_signature.endswith(shorter_signature)
                    )
                )
                track_role = classify_ocr_box_role(
                    track.box_coords, frame_w=frame_w, frame_h=frame_h
                )
                host_role = classify_ocr_box_role(
                    host.box_coords, frame_w=frame_w, frame_h=frame_h
                )
                nested_ui_fragment_match = (
                    not both_hardsub
                    and track_role == host_role
                    and overlap_frames >= 3
                    and overlap_ratio >= 0.80
                    and horizontal_ratio >= 0.85
                    and vertical_ratio >= 0.80
                    and len(shorter_signature) >= 2
                    and shorter_signature in longer_signature
                )
                if (
                    not strict_content_match
                    and not adjacent_prefix_match
                    and not overlap_fuzzy_match
                    and not geometry_fragment_match
                    and not overlapping_prefix_fragment_match
                    and not nested_ui_fragment_match
                ):
                    continue

                prior_spans = [
                    [int(host.start_frame), int(host.end_frame)],
                    [int(track.start_frame), int(track.end_frame)],
                ]
                normalized_host_box = list(host.box_coords)
                normalized_track_box = list(track.box_coords)
                host.start_frame = min(int(host.start_frame), int(track.start_frame))
                host.end_frame = max(int(host.end_frame), int(track.end_frame))
                host.hit_boxes.extend(
                    tuple(float(value) for value in box[:4])
                    for box in track.hit_boxes
                )
                host.hit_frames.extend(int(value) for value in track.hit_frames)
                host.hit_sharpness.extend(
                    float(value) for value in track.hit_sharpness
                )
                host.hit_count = len(host.hit_boxes)
                expansive = _hardsub_should_use_expansive_stable(host.hit_boxes)
                host.box_coords = _stable_box_prefer_hardsub_lines(
                    host.hit_boxes,
                    current=host.box_coords,
                    frame_w=frame_w,
                    frame_h=frame_h,
                    expansive=expansive,
                )
                normalized_box_used = False
                if not geometry_normalized and strict_content_match and both_hardsub:
                    pre_ink_candidates = [
                        normalized_host_box,
                        normalized_track_box,
                    ]
                    pre_ink_candidates.sort(
                        key=lambda box: float(box[2]) - float(box[0])
                    )
                    narrow_box, wide_box = pre_ink_candidates
                    narrow_w = max(
                        1.0, float(narrow_box[2]) - float(narrow_box[0])
                    )
                    wide_w = max(1.0, float(wide_box[2]) - float(wide_box[0]))
                    # Same text + almost identical lifespan means the wider
                    # nested track is a detector/recovery geometry variant,
                    # not additional glyph content. Keep its timing evidence
                    # while making the dense narrow line geometry authority.
                    if (
                        overlap_ratio >= 0.80
                        and horizontal_ratio >= 0.90
                        and narrow_w / max(1.0, float(frame_w)) >= 0.12
                        and narrow_w / wide_w <= 0.65
                    ):
                        chosen = [float(value) for value in narrow_box[:4]]
                        host.box_coords = chosen
                        host.hit_boxes = [tuple(chosen)] * max(
                            1, len(host.hit_frames)
                        )
                        host.hit_count = len(host.hit_boxes)
                        normalized_box_used = True
                if geometry_normalized:
                    candidates_with_signatures = [
                        (normalized_host_box, host_signature),
                        (normalized_track_box, signature),
                    ]
                    candidates_with_signatures.sort(
                        key=lambda item: float(item[0][2]) - float(item[0][0])
                    )
                    (narrow_box, narrow_signature), (wide_box, wide_signature) = (
                        candidates_with_signatures
                    )
                    narrow_w = max(
                        1.0, float(narrow_box[2]) - float(narrow_box[0])
                    )
                    wide_w = max(1.0, float(wide_box[2]) - float(wide_box[0]))
                    signature_ratio = len(str(narrow_signature)) / float(
                        max(1, len(str(wide_signature)))
                    )
                    if narrow_w / wide_w >= 0.40 and signature_ratio >= 0.80:
                        chosen = [
                            float(narrow_box[0]),
                            min(
                                float(normalized_host_box[1]),
                                float(normalized_track_box[1]),
                            ),
                            float(narrow_box[2]),
                            max(
                                float(normalized_host_box[3]),
                                float(normalized_track_box[3]),
                            ),
                        ]
                        host.box_coords = chosen
                        # Post-ink geometry is stronger than the raw/recovered
                        # hit boxes that caused the fragment in the first place.
                        host.hit_boxes = [tuple(chosen)] * max(
                            1, len(host.hit_frames)
                        )
                        host.hit_count = len(host.hit_boxes)
                        normalized_box_used = True
                host.centroid = _box_centroid(host.box_coords)
                if float(track.best_sharpness) > float(host.best_sharpness):
                    host.best_frame_index = int(track.best_frame_index)
                    host.best_sharpness = float(track.best_sharpness)
                members.append(track_index)
                if geometry_fragment_match and not strict_content_match:
                    # A temporally-contained same-row hardsub fragment may OCR
                    # badly because its box includes scene texture. The wider
                    # overlapping peer is the bridge to later continuation.
                    host_signature, host_text = signature, text
                elif overlap_fuzzy_match and not strict_content_match:
                    # The later overlapping fragment supplies a clean bridge
                    # for any immediately-adjacent continuation.
                    host_signature, host_text = signature, text
                elif len(signature) > len(host_signature):
                    host_signature, host_text = signature, text
                groups[group_index] = (host, host_signature, host_text, members)
                audit["merged_tracks"] += 1
                audit["rows"].append(
                    {
                        "text": host_text,
                        "signature": host_signature,
                        "prior_spans": prior_spans,
                        "result_span": [host.start_frame, host.end_frame],
                        "temporal_overlap": overlap_frames,
                        "overlap_ratio_of_shorter": round(overlap_ratio, 4),
                        "temporal_gap": temporal_gap,
                        "nested_ui_fragment_match": nested_ui_fragment_match,
                        "normalized_box_used": normalized_box_used,
                        "result_box": [
                            round(float(value), 3) for value in host.box_coords[:4]
                        ],
                    }
                )
                merged = True
                break
        if not merged:
            copied = MergedTrack(
                start_frame=int(track.start_frame),
                end_frame=int(track.end_frame),
                box_coords=list(track.box_coords),
                best_frame_index=int(track.best_frame_index),
                best_sharpness=float(track.best_sharpness),
                centroid=tuple(track.centroid),
                hit_count=int(track.hit_count),
                hit_boxes=list(track.hit_boxes),
                hit_frames=list(track.hit_frames),
                hit_sharpness=list(track.hit_sharpness),
            )
            signature, text, _confidence = evidence or ("", "", 0.0)
            groups.append((copied, signature, text, [track_index]))

    output = [group[0] for group in groups]
    output.sort(key=lambda track: (track.start_frame, track.box_coords[0]))
    audit["after_count"] = len(output)
    return output, audit


def expand_tracks_by_local_text_continuity(
    tracks: Sequence[MergedTrack],
    *,
    frame_cache: Mapping[int, np.ndarray],
    frame_count: int,
    frame_w: int,
    frame_h: int,
    recognizer: Any | None,
    source: Path | None = None,
    batch_size: int = 32,
    miss_tolerance: int = 2,
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """Recover continuous hardsub frames outside detector-derived spans."""
    audit: dict[str, Any] = {
        "method": "local_text_outward_continuity_v1",
        "recognizer_available": recognizer is not None,
        "before_count": len(tracks),
        "after_count": len(tracks),
        "expanded_tracks": 0,
        "rows": [],
    }
    if recognizer is None or not tracks:
        return list(tracks), audit

    count = max(1, int(frame_count))
    tolerance = max(1, int(miss_tolerance))
    roles = [
        classify_ocr_box_role(track.box_coords, frame_w=frame_w, frame_h=frame_h)
        for track in tracks
    ]
    output: list[MergedTrack] = []

    for track_index, track in enumerate(tracks):
        if roles[track_index] != "hardsub":
            output.append(track)
            continue
        ty0, ty1 = float(track.box_coords[1]), float(track.box_coords[3])
        tcy = 0.5 * (ty0 + ty1)
        left_limit = 0
        right_limit = count - 1
        for other_index, other in enumerate(tracks):
            if other_index == track_index or roles[other_index] != "hardsub":
                continue
            ocy = 0.5 * (float(other.box_coords[1]) + float(other.box_coords[3]))
            if abs(tcy - ocy) > max(18.0, 0.045 * float(frame_h)):
                continue
            if int(other.end_frame) < int(track.start_frame):
                left_limit = max(left_limit, int(other.end_frame) + 1)
            elif int(other.start_frame) > int(track.end_frame):
                right_limit = min(right_limit, int(other.start_frame) - 1)

        representative_indices: list[int] = [int(track.best_frame_index)]
        hits = sorted({int(value) for value in track.hit_frames})
        if hits:
            representative_indices.extend([hits[len(hits) // 2], hits[0], hits[-1]])
        representative_crops: list[np.ndarray] = []
        representative_frames: list[int] = []
        for frame_index in representative_indices:
            if frame_index in representative_frames:
                continue
            frame = _boundary_frame(
                frame_index, frame_cache=frame_cache, source=source
            )
            crop = (
                _crop_xyxy_from_frame(frame, track.box_coords)
                if frame is not None
                else None
            )
            if crop is None or crop.size < 16:
                continue
            representative_frames.append(frame_index)
            representative_crops.append(crop)
            if len(representative_crops) >= 3:
                break
        if not representative_crops:
            output.append(track)
            continue
        try:
            representative_results = list(
                recognizer.recognize_batch(representative_crops)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("phase1_content_continuity_seed_failed err=%s", exc)
            output.append(track)
            continue
        valid_representatives: list[tuple[str, str, float]] = []
        for recognition in representative_results:
            if not _local_recognition_is_timing_evidence(
                recognition, role="hardsub"
            ):
                continue
            text = str(getattr(recognition, "text", "") or "").strip()
            signature = _local_text_timing_signature(text)
            valid_representatives.append(
                (
                    signature,
                    text,
                    float(getattr(recognition, "confidence", 0.0) or 0.0),
                )
            )
        if not valid_representatives:
            output.append(track)
            continue
        representative_signature, representative_text, _confidence = max(
            valid_representatives,
            key=lambda value: (len(value[0]), value[2]),
        )

        def _scan(indices: Sequence[int]) -> list[int]:
            accepted: list[int] = []
            misses = 0
            size = max(1, int(batch_size))
            for offset in range(0, len(indices), size):
                chunk_indices: list[int] = []
                crops: list[np.ndarray] = []
                for frame_index in indices[offset : offset + size]:
                    frame = _boundary_frame(
                        int(frame_index), frame_cache=frame_cache, source=source
                    )
                    crop = (
                        _crop_xyxy_from_frame(frame, track.box_coords)
                        if frame is not None
                        else None
                    )
                    if crop is None or crop.size < 16:
                        misses += 1
                        if misses >= tolerance:
                            return accepted
                        continue
                    chunk_indices.append(int(frame_index))
                    crops.append(crop)
                if not crops:
                    continue
                try:
                    results = list(recognizer.recognize_batch(crops))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("phase1_content_continuity_scan_failed err=%s", exc)
                    return accepted
                for frame_index, recognition in zip(chunk_indices, results):
                    signature = _local_text_timing_signature(
                        str(getattr(recognition, "text", "") or "")
                    )
                    if (
                        _local_recognition_is_timing_evidence(
                            recognition, role="hardsub"
                        )
                        and _local_text_signatures_match(
                            signature, representative_signature
                        )
                    ):
                        accepted.append(frame_index)
                        misses = 0
                    else:
                        misses += 1
                        if misses >= tolerance:
                            return accepted
            return accepted

        left_indices = list(
            range(int(track.start_frame) - 1, int(left_limit) - 1, -1)
        )
        right_indices = list(
            range(int(track.end_frame) + 1, int(right_limit) + 1)
        )
        left_matches = _scan(left_indices)
        right_matches = _scan(right_indices)
        if not left_matches and not right_matches:
            output.append(track)
            continue

        new_start = min([int(track.start_frame), *left_matches, *right_matches])
        new_end = max([int(track.end_frame), *left_matches, *right_matches])
        hit_boxes = list(track.hit_boxes)
        hit_frames = list(track.hit_frames)
        hit_sharpness = list(track.hit_sharpness)
        existing_frames = {int(value) for value in hit_frames}
        for frame_index in sorted({*left_matches, *right_matches}):
            if frame_index in existing_frames:
                continue
            frame = _boundary_frame(
                frame_index, frame_cache=frame_cache, source=source
            )
            hit_boxes.append(tuple(float(value) for value in track.box_coords[:4]))
            hit_frames.append(frame_index)
            hit_sharpness.append(
                crop_box_sharpness(frame, track.box_coords)
                if frame is not None
                else 0.0
            )
        expanded = MergedTrack(
            start_frame=new_start,
            end_frame=new_end,
            box_coords=list(track.box_coords),
            best_frame_index=int(track.best_frame_index),
            best_sharpness=float(track.best_sharpness),
            centroid=tuple(track.centroid),
            hit_count=len(hit_boxes),
            hit_boxes=hit_boxes,
            hit_frames=hit_frames,
            hit_sharpness=hit_sharpness,
        )
        output.append(expanded)
        audit["expanded_tracks"] += 1
        audit["rows"].append(
            {
                "text": representative_text,
                "signature": representative_signature,
                "prior_span": [int(track.start_frame), int(track.end_frame)],
                "result_span": [new_start, new_end],
                "left_frames_added": len(left_matches),
                "right_frames_added": len(right_matches),
            }
        )

    output.sort(key=lambda track: (track.start_frame, track.box_coords[0]))
    return output, audit


def discover_hardsub_tracks_from_cache(
    frame_cache: Mapping[int, np.ndarray],
    *,
    frame_w: int,
    frame_h: int,
    recognizer: Any | None,
    existing: Sequence[MergedTrack] = (),
    min_hits: int = 2,
    max_frame_gap: int = 8,
) -> list[MergedTrack]:
    """
    Recover bottom hardsub lines from cached frames when DBNet missed the band.

    Food FPs mid-frame can steal SSOT while the real burn-in sits uncovered;
    this scans the thin bottom band on cached frames and promotes OCR-accepted
    ink lines into tracks (general — no clip timestamps).
    """
    if recognizer is None or not frame_cache:
        return []
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    seed = [0.22 * fw, 0.90 * fh, 0.78 * fw, 0.97 * fh]
    existing_hs = [
        t
        for t in existing
        if classify_ocr_box_role(t.box_coords, frame_w=frame_w, frame_h=frame_h)
        == "hardsub"
    ]

    hits: list[tuple[int, list[float], float]] = []
    for fi in sorted(int(k) for k in frame_cache.keys()):
        frame = frame_cache.get(fi)
        if frame is None:
            continue
        recovered = recover_hardsub_box_from_band_ink(
            frame, seed, frame_w=frame_w, frame_h=frame_h
        )
        if recovered is None or not _box_is_hardsub_line_geometry(
            recovered, frame_w=frame_w, frame_h=frame_h
        ):
            continue
        # Skip when an existing hardsub already covers this frame + box.
        covered = False
        for host in existing_hs:
            if int(host.start_frame) - 2 <= fi <= int(host.end_frame) + 2:
                if box_iou(recovered, host.box_coords) >= 0.20:
                    covered = True
                    break
        if covered:
            continue
        crop = _crop_xyxy_from_frame(frame, recovered)
        if crop is None or crop.size < 16:
            continue
        try:
            recognition = recognizer.recognize(crop)
        except Exception:  # noqa: BLE001
            continue
        if not local_text_accepts_track(recognition, role="hardsub"):
            continue
        # Discovered lines must be multi-glyph burn-in near the true bottom —
        # rejects food-row recoveries that OCR-hallucinate short CJK.
        text = str(getattr(recognition, "text", "") or "")
        if _cjk_count(text) < 4:
            continue
        conf = float(getattr(recognition, "confidence", 0.0) or 0.0)
        if conf < 0.80:
            continue
        cy = (0.5 * (float(recovered[1]) + float(recovered[3]))) / fh
        if cy < 0.915:
            continue
        sharp = float(crop_ink_score(frame, recovered))
        hits.append((fi, [float(v) for v in recovered[:4]], sharp))

    if not hits:
        return []

    # Cluster nearby frames with overlapping boxes into tracks.
    clusters: list[list[tuple[int, list[float], float]]] = [[hits[0]]]
    for hit in hits[1:]:
        prev = clusters[-1][-1]
        if (
            hit[0] - prev[0] <= int(max_frame_gap)
            and box_iou(hit[1], prev[1]) >= 0.18
            and (hit[0] - clusters[-1][0][0]) <= 60
        ):
            clusters[-1].append(hit)
        else:
            clusters.append([hit])

    out: list[MergedTrack] = []
    for cluster in clusters:
        if len(cluster) < int(min_hits):
            continue
        boxes = [c[1] for c in cluster]
        frames = [c[0] for c in cluster]
        sharps = [c[2] for c in cluster]
        best_i = int(max(range(len(sharps)), key=lambda i: sharps[i]))
        box = stable_box_xyxy(boxes, expansive=False)
        if not _box_is_hardsub_line_geometry(
            box, frame_w=frame_w, frame_h=frame_h
        ):
            box = boxes[best_i]
        out.append(
            MergedTrack(
                start_frame=int(frames[0]),
                end_frame=int(frames[-1]),
                box_coords=[float(v) for v in box[:4]],
                best_frame_index=int(frames[best_i]),
                best_sharpness=float(sharps[best_i]),
                centroid=_box_centroid(box),
                hit_count=len(cluster),
                hit_boxes=[tuple(float(v) for v in b[:4]) for b in boxes],
                hit_frames=list(frames),
                hit_sharpness=list(sharps),
            )
        )
    return out


def _tracks_substantially_overlap_in_time(
    a: MergedTrack,
    b: MergedTrack,
    *,
    min_ratio: float = 0.50,
    min_frames: int = 2,
) -> bool:
    """True fragment overlap, not a one-frame inclusive caption boundary."""
    start = max(int(a.start_frame), int(b.start_frame))
    end = min(int(a.end_frame), int(b.end_frame))
    overlap = max(0, end - start + 1)
    if overlap < max(1, int(min_frames)):
        return False
    a_span = max(1, int(a.end_frame) - int(a.start_frame) + 1)
    b_span = max(1, int(b.end_frame) - int(b.start_frame) + 1)
    return (overlap / float(min(a_span, b_span))) >= float(min_ratio)


def purge_hardsub_shadows_by_boundary_audit(
    tracks: Sequence[MergedTrack],
    audit_rows: Sequence[Mapping[str, Any]],
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[list[MergedTrack], list[dict[str, Any]]]:
    """Drop short adjacent detector shadows only when boundary evidence agrees."""
    if len(tracks) != len(audit_rows):
        return list(tracks), [dict(row) for row in audit_rows]
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    drop_ids: set[int] = set()
    for index, (track, audit) in enumerate(zip(tracks, audit_rows)):
        if classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        ) != "hardsub":
            continue
        positive = audit.get("positive_floor")
        negative = audit.get("negative_ceiling")
        if (
            audit.get("fallback_from") != "template_not_separable"
            or audit.get("reason") != "dense_detector_evidence"
            or positive is None
            or negative is None
            or float(positive) - float(negative) > 0.03
        ):
            continue
        tx0, ty0, tx1, ty1 = (float(value) for value in track.box_coords[:4])
        tw = max(1.0, tx1 - tx0)
        th = max(1.0, ty1 - ty0)
        tcy = 0.5 * (ty0 + ty1)
        for host_index, (host, host_audit) in enumerate(zip(tracks, audit_rows)):
            if host_index == index:
                continue
            if not host_audit.get("applied") or host_audit.get("reason") != "verified":
                continue
            if classify_ocr_box_role(
                host.box_coords, frame_w=frame_w, frame_h=frame_h
            ) != "hardsub":
                continue
            if int(host.hit_count) < 6 * max(1, int(track.hit_count)):
                continue
            if not _tracks_substantially_overlap_in_time(
                track, host, min_ratio=0.80, min_frames=5
            ):
                continue
            hx0, hy0, hx1, hy1 = (
                float(value) for value in host.box_coords[:4]
            )
            hw = max(1.0, hx1 - hx0)
            hh = max(1.0, hy1 - hy0)
            hcy = 0.5 * (hy0 + hy1)
            horizontal_overlap = max(0.0, min(tx1, hx1) - max(tx0, hx0))
            if horizontal_overlap / max(1.0, min(tw, hw)) < 0.75:
                continue
            vertical_overlap = max(0.0, min(ty1, hy1) - max(ty0, hy0))
            if vertical_overlap <= 0.0:
                continue
            if vertical_overlap / max(1.0, min(th, hh)) > 0.40:
                continue
            if abs(tcy - hcy) > 0.05 * fh:
                continue
            if min(tw, hw) / fw < 0.28:
                continue
            drop_ids.add(id(track))
            break
    kept_tracks: list[MergedTrack] = []
    kept_audits: list[dict[str, Any]] = []
    for track, audit in zip(tracks, audit_rows):
        if id(track) in drop_ids:
            continue
        kept_tracks.append(track)
        kept_audits.append(dict(audit))
    return kept_tracks, kept_audits


def purge_redundant_hardsub_fragments(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
    wide_frac: float = 0.35,
    stub_frac: float = 0.28,
) -> list[MergedTrack]:
    """
    Drop thin bottom hardsub stubs covered by a wide hardsub on the same band.

    Also drops sparse nested hardsubs that heavily overlap a much denser burn-in
    (overwide x=0 pads / food slabs under a stable line).
    """
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    hardsub_tracks = [
        track
        for track in tracks
        if classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        == "hardsub"
    ]
    if not hardsub_tracks:
        return list(tracks)

    def _is_sparse_nested(candidate: MergedTrack) -> bool:
        for host in hardsub_tracks:
            if host is candidate:
                continue
            if int(candidate.hit_count) >= int(host.hit_count):
                continue
            if int(candidate.hit_count) > max(6, int(host.hit_count) * 0.15):
                continue
            if not _tracks_substantially_overlap_in_time(candidate, host):
                continue
            # A two-frame wide shadow may be shifted vertically and extend
            # beyond the dense line, producing low IoU despite representing
            # the same glyph band. Repeated two-line captions do not normally
            # overlap vertically; require extreme density dominance plus
            # substantial overlap on both axes before dropping.
            if int(candidate.hit_count) <= 2 and int(host.hit_count) >= max(
                20, 20 * int(candidate.hit_count)
            ):
                cx0, cy0, cx1, cy1 = (
                    float(value) for value in candidate.box_coords[:4]
                )
                hx0, hy0, hx1, hy1 = (
                    float(value) for value in host.box_coords[:4]
                )
                horizontal = max(0.0, min(cx1, hx1) - max(cx0, hx0))
                vertical = max(0.0, min(cy1, hy1) - max(cy0, hy0))
                cw, ch = max(1.0, cx1 - cx0), max(1.0, cy1 - cy0)
                hw, hh = max(1.0, hx1 - hx0), max(1.0, hy1 - hy0)
                if (
                    horizontal / min(cw, hw) >= 0.55
                    and vertical / min(ch, hh) >= 0.20
                    and abs(0.5 * (cy0 + cy1) - 0.5 * (hy0 + hy1))
                    <= 0.05 * fh
                ):
                    return True
            if box_iou(candidate.box_coords, host.box_coords) < 0.20:
                # Dense line swallowed by overwide sparse pad (x=0 balloon).
                hx0, hy0, hx1, hy1 = (float(v) for v in host.box_coords[:4])
                ix0 = max(float(candidate.box_coords[0]), hx0)
                iy0 = max(float(candidate.box_coords[1]), hy0)
                ix1 = min(float(candidate.box_coords[2]), hx1)
                iy1 = min(float(candidate.box_coords[3]), hy1)
                inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
                host_area = max(1.0, (hx1 - hx0) * (hy1 - hy0))
                if inter / host_area < 0.70:
                    continue
            return True
        return False

    nested_drop_ids = {
        id(track) for track in hardsub_tracks if _is_sparse_nested(track)
    }
    # A wide sparse balloon that is itself rejected must never remain a purge
    # authority for adjacent dense captions.
    wide: list[MergedTrack] = []
    for track in hardsub_tracks:
        if id(track) in nested_drop_ids:
            continue
        x0, y0, x1, y1 = (float(v) for v in track.box_coords[:4])
        w = max(1.0, x1 - x0)
        h = max(1.0, y1 - y0)
        if (
            (w / fw) >= float(wide_frac)
            and (h / fh) <= THIN_HARDSUB_HEIGHT_FRAC
        ):
            wide.append(track)

    out: list[MergedTrack] = []
    for track in tracks:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        x0, y0, x1, y1 = (float(v) for v in track.box_coords[:4])
        w = max(1.0, x1 - x0)
        cy = (y0 + y1) * 0.5
        if role != "hardsub":
            out.append(track)
            continue
        if id(track) in nested_drop_ids:
            continue
        if (w / fw) >= float(wide_frac):
            out.append(track)
            continue
        if (w / fw) > float(stub_frac):
            out.append(track)
            continue
        covered = False
        for host in wide:
            # Consecutive burn-ins may share one inclusive boundary frame.
            # Only substantial overlap proves a duplicate fragment.
            if not _tracks_substantially_overlap_in_time(track, host):
                continue
            hx0, hy0, hx1, hy1 = (float(v) for v in host.box_coords[:4])
            hcy = (hy0 + hy1) * 0.5
            if abs(cy - hcy) > max(18.0, 0.03 * fh):
                continue
            if x0 >= hx0 - 8.0 and x1 <= hx1 + 8.0:
                covered = True
                break
            if box_iou(track.box_coords, host.box_coords) >= 0.15:
                covered = True
                break
        if not covered:
            out.append(track)
    return out


def nested_temporal_ui_fragment_metrics(
    candidate: MergedTrack,
    authority: MergedTrack,
    *,
    frame_w: int,
    frame_h: int,
    max_duration_ratio: float = 0.35,
    min_spatial_containment: float = 0.95,
    max_area_ratio: float = 0.75,
) -> dict[str, Any] | None:
    """Return strict geometry-only evidence for a nested UI fragment.

    This is deliberately narrower than normal near-duplicate coalescing. It
    handles a short detector/OCR fragment fully contained by a longer UI label
    without depending on local OCR text. Sequential labels and hardsubs are
    excluded so a real caption transition cannot be silently removed.
    """
    candidate_span = max(
        1, int(candidate.end_frame) - int(candidate.start_frame) + 1
    )
    authority_span = max(
        1, int(authority.end_frame) - int(authority.start_frame) + 1
    )
    if candidate_span >= authority_span:
        return None
    if (
        int(candidate.start_frame) < int(authority.start_frame)
        or int(candidate.end_frame) > int(authority.end_frame)
    ):
        return None
    duration_ratio = candidate_span / float(authority_span)
    if duration_ratio > float(max_duration_ratio):
        return None

    candidate_role = classify_ocr_box_role(
        candidate.box_coords, frame_w=frame_w, frame_h=frame_h
    )
    authority_role = classify_ocr_box_role(
        authority.box_coords, frame_w=frame_w, frame_h=frame_h
    )
    if candidate_role != authority_role or candidate_role == "hardsub":
        return None

    cx0, cy0, cx1, cy1 = (
        float(value) for value in candidate.box_coords[:4]
    )
    ax0, ay0, ax1, ay1 = (
        float(value) for value in authority.box_coords[:4]
    )
    candidate_area = max(1.0, (cx1 - cx0) * (cy1 - cy0))
    authority_area = max(1.0, (ax1 - ax0) * (ay1 - ay0))
    area_ratio = candidate_area / authority_area
    if area_ratio > float(max_area_ratio):
        return None
    intersection = max(0.0, min(cx1, ax1) - max(cx0, ax0)) * max(
        0.0, min(cy1, ay1) - max(cy0, ay0)
    )
    spatial_containment = intersection / candidate_area
    if spatial_containment < float(min_spatial_containment):
        return None
    x_tolerance = max(4.0, 0.005 * float(frame_w))
    y_tolerance = max(4.0, 0.005 * float(frame_h))
    if not (
        cx0 >= ax0 - x_tolerance
        and cy0 >= ay0 - y_tolerance
        and cx1 <= ax1 + x_tolerance
        and cy1 <= ay1 + y_tolerance
    ):
        return None

    return {
        "role": candidate_role,
        "candidate_duration_frames": candidate_span,
        "authority_duration_frames": authority_span,
        "duration_ratio": round(duration_ratio, 4),
        "temporal_containment": 1.0,
        "spatial_containment": round(spatial_containment, 4),
        "area_ratio": round(area_ratio, 4),
    }


def find_temporally_nested_ui_fragments(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
) -> list[dict[str, Any]]:
    """Find short nested UI fragments, choosing the longest valid authority."""
    authority_order = sorted(
        range(len(tracks)),
        key=lambda index: (
            int(tracks[index].end_frame) - int(tracks[index].start_frame) + 1,
            _box_area(tracks[index].box_coords),
        ),
        reverse=True,
    )
    candidate_order = list(reversed(authority_order))
    rows: list[dict[str, Any]] = []
    for candidate_index in candidate_order:
        candidate = tracks[candidate_index]
        for authority_index in authority_order:
            if authority_index == candidate_index:
                continue
            authority = tracks[authority_index]
            metrics = nested_temporal_ui_fragment_metrics(
                candidate,
                authority,
                frame_w=frame_w,
                frame_h=frame_h,
            )
            if metrics is None:
                continue
            rows.append(
                {
                    "action": "drop_nested_ui_fragment",
                    "reason": "geometry_temporal_containment",
                    "candidate_index": candidate_index,
                    "authority_index": authority_index,
                    "candidate_span": [
                        int(candidate.start_frame),
                        int(candidate.end_frame),
                    ],
                    "authority_span": [
                        int(authority.start_frame),
                        int(authority.end_frame),
                    ],
                    "candidate_box": [
                        round(float(value), 3)
                        for value in candidate.box_coords[:4]
                    ],
                    "authority_box": [
                        round(float(value), 3)
                        for value in authority.box_coords[:4]
                    ],
                    **metrics,
                }
            )
            break
    return rows


def purge_temporally_nested_ui_fragments(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """Keep the long UI authority and audit every contained fragment drop."""
    rows = find_temporally_nested_ui_fragments(
        tracks, frame_w=frame_w, frame_h=frame_h
    )
    dropped_indices = {int(row["candidate_index"]) for row in rows}
    kept = [
        track for index, track in enumerate(tracks) if index not in dropped_indices
    ]
    return kept, {
        "method": "geometry_temporal_nested_ui_fragment_guard_v1",
        "before_count": len(tracks),
        "after_count": len(kept),
        "dropped_tracks": len(dropped_indices),
        "rows": rows,
    }



def _cached_frames_for_track(
    track: MergedTrack,
    frame_cache: Mapping[int, np.ndarray],
    *,
    max_frames: int = 3,
) -> list[np.ndarray]:
    """Up to ``max_frames`` unique cached frames for a track (best first)."""
    out: list[np.ndarray] = []
    seen: set[int] = set()
    order = [int(track.best_frame_index), *[int(f) for f in track.hit_frames]]
    # Prefer higher sharpness hit frames after best.
    if track.hit_frames and track.hit_sharpness:
        ranked = sorted(
            range(len(track.hit_frames)),
            key=lambda i: float(track.hit_sharpness[i]),
            reverse=True,
        )
        order = [int(track.best_frame_index)] + [
            int(track.hit_frames[i]) for i in ranked
        ]
    for fi in order:
        if fi in seen:
            continue
        seen.add(fi)
        frame = frame_cache.get(fi)
        if frame is None or getattr(frame, "size", 0) == 0:
            continue
        out.append(frame)
        if len(out) >= max(1, int(max_frames)):
            break
    return out



def _stable_box_prefer_hardsub_lines(
    hit_boxes: Sequence[Sequence[float]],
    *,
    current: Sequence[float],
    frame_w: int,
    frame_h: int,
    expansive: bool,
) -> list[float]:
    """Rebuild box from hits, but never regress a burn-in to mid-band food slabs."""
    line_hits = [
        b
        for b in hit_boxes
        if _box_is_hardsub_line_geometry(b, frame_w=frame_w, frame_h=frame_h)
    ]
    if line_hits:
        return [float(v) for v in stable_box_xyxy(line_hits, expansive=expansive)[:4]]
    if _box_is_hardsub_line_geometry(current, frame_w=frame_w, frame_h=frame_h):
        return [float(v) for v in current[:4]]
    if hit_boxes:
        return [float(v) for v in stable_box_xyxy(hit_boxes, expansive=expansive)[:4]]
    return [float(v) for v in current[:4]]


def coalesce_near_duplicate_tracks(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
    iou_min: float = 0.55,
    cy_frac_max: float = 0.035,
    gap_max: int = COALESCE_GAP_FRAMES,
) -> list[MergedTrack]:
    """
    Merge same-column near-duplicate tracks that overlap (or nearly touch) in time.

    Phase1 often emits several SSOT ids for one ingredient band; coalesce before
    export so Phase2/3 see one lifespan. Uses COALESCE_GAP_FRAMES (wider than
    MERGE_GAP_FRAMES) so DBNet detection holes do not leave duplicate rows.
    """
    if len(tracks) <= 1:
        return list(tracks)
    fh = max(1.0, float(frame_h))
    cy_lim = float(cy_frac_max) * fh
    ordered = sorted(
        tracks,
        key=lambda t: (t.start_frame, t.box_coords[1], -int(t.hit_count)),
    )
    groups: list[MergedTrack] = []
    for track in ordered:
        bucket = _mid_column_bucket(track.box_coords, frame_w=frame_w)
        tcy = (float(track.box_coords[1]) + float(track.box_coords[3])) * 0.5
        merged_into: MergedTrack | None = None
        for i, host in enumerate(groups):
            if _mid_column_bucket(host.box_coords, frame_w=frame_w) != bucket:
                # Hardsub lines are full-width — allow cross-bucket merge when
                # both are thin bottom bands with close cy and compatible time.
                both_hs = _box_looks_like_thin_hardsub(
                    track.box_coords, frame_w=frame_w, frame_h=frame_h
                ) and _box_looks_like_thin_hardsub(
                    host.box_coords, frame_w=frame_w, frame_h=frame_h
                )
                if not both_hs:
                    continue
            hcy = (float(host.box_coords[1]) + float(host.box_coords[3])) * 0.5
            iou = box_iou(track.box_coords, host.box_coords)
            close_y = abs(tcy - hcy) <= cy_lim
            both_hs = _box_looks_like_thin_hardsub(
                track.box_coords, frame_w=frame_w, frame_h=frame_h
            ) and _box_looks_like_thin_hardsub(
                host.box_coords, frame_w=frame_w, frame_h=frame_h
            )
            hardsub_band = both_hs and abs(tcy - hcy) <= max(cy_lim, 0.045 * fh)
            normalize_incoming_hardsub_geometry = False
            if hardsub_band:
                # Union X spans on the same bottom band (fragmented burn-ins).
                tx0, _, tx1, _ = (float(v) for v in track.box_coords[:4])
                hx0, _, hx1, _ = (float(v) for v in host.box_coords[:4])
                gap = max(0.0, max(tx0, hx0) - min(tx1, hx1))
                if gap > 0.12 * float(frame_w) and iou < 0.08:
                    continue
                # Never re-glue sequential / gapped lines (even similar width).
                # Only true time-overlap fragments may coalesce.
                overlap_n = max(
                    0,
                    min(int(track.end_frame), int(host.end_frame))
                    - max(int(track.start_frame), int(host.start_frame))
                    + 1,
                )
                if overlap_n < 1:
                    continue
                if not _hardsub_line_geometry_compatible(
                    track.box_coords, host.box_coords
                ):
                    contained = _x_span_mostly_contained(
                        track.box_coords, host.box_coords
                    ) or _x_span_mostly_contained(
                        host.box_coords, track.box_coords
                    )
                    if overlap_n < 5 or not contained:
                        continue
                host_hit_frames = {int(value) for value in host.hit_frames}
                track_hit_frames = {int(value) for value in track.hit_frames}
                host_hit_span = (
                    max(1, max(host_hit_frames) - min(host_hit_frames) + 1)
                    if host_hit_frames
                    else 1
                )
                host_density = len(host_hit_frames) / float(host_hit_span)
                host_w = max(1.0, hx1 - hx0)
                track_w = max(1.0, tx1 - tx0)
                shorter_track_span = max(
                    1,
                    min(
                        int(track.end_frame) - int(track.start_frame) + 1,
                        int(host.end_frame) - int(host.start_frame) + 1,
                    ),
                )
                overlap_ratio_of_shorter = overlap_n / float(shorter_track_span)
                normalize_incoming_hardsub_geometry = (
                    host_w / max(1.0, float(frame_w)) >= 0.22
                    and host_density >= 0.75
                    and len(host_hit_frames) >= 2 * max(1, len(track_hit_frames))
                    and overlap_n >= 5
                    and overlap_ratio_of_shorter >= 0.50
                    and track_w >= host_w * 1.15
                )
            elif iou < float(iou_min) and not (
                close_y and iou >= float(iou_min) * 0.45
            ):
                continue
            if not _time_compatible(
                int(track.start_frame),
                int(track.end_frame),
                int(host.start_frame),
                int(host.end_frame),
                # Hardsub: no gap bridge — overlap already required above.
                gap_max=0 if hardsub_band else gap_max,
            ):
                continue
            # Union hits into host.
            host.start_frame = min(int(host.start_frame), int(track.start_frame))
            host.end_frame = max(int(host.end_frame), int(track.end_frame))
            if normalize_incoming_hardsub_geometry:
                host_box = tuple(float(value) for value in host.box_coords[:4])
                host.hit_boxes.extend(
                    (
                        host_box[0],
                        float(box[1]),
                        host_box[2],
                        float(box[3]),
                    )
                    for box in track.hit_boxes
                )
            else:
                host.hit_boxes.extend(
                    tuple(float(v) for v in b[:4]) for b in track.hit_boxes
                )
            host.hit_frames.extend(int(f) for f in track.hit_frames)
            host.hit_sharpness.extend(
                float(s)
                for s in (
                    track.hit_sharpness
                    or [float(track.best_sharpness)] * max(1, len(track.hit_boxes))
                )
            )
            host.hit_count = len(host.hit_boxes) or (
                int(host.hit_count) + int(track.hit_count)
            )
            expansive = _hardsub_should_use_expansive_stable(host.hit_boxes)
            host.box_coords = _stable_box_prefer_hardsub_lines(
                host.hit_boxes,
                current=host.box_coords,
                frame_w=frame_w,
                frame_h=frame_h,
                expansive=expansive,
            )
            host.centroid = _box_centroid(host.box_coords)
            if float(track.best_sharpness) >= float(host.best_sharpness):
                host.best_sharpness = float(track.best_sharpness)
                host.best_frame_index = int(track.best_frame_index)
            groups[i] = host
            merged_into = host
            break
        if merged_into is None:
            groups.append(
                MergedTrack(
                    start_frame=int(track.start_frame),
                    end_frame=int(track.end_frame),
                    box_coords=list(track.box_coords),
                    best_frame_index=int(track.best_frame_index),
                    best_sharpness=float(track.best_sharpness),
                    centroid=tuple(track.centroid),
                    hit_count=int(track.hit_count),
                    hit_boxes=list(track.hit_boxes),
                    hit_frames=list(track.hit_frames),
                    hit_sharpness=list(track.hit_sharpness),
                )
            )
    groups.sort(key=lambda t: (t.start_frame, t.box_coords[0]))
    return groups


def integrate_residual_tracks_without_recoalescing_authority(
    existing_tracks: Sequence[MergedTrack],
    residual_tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """Append recovered residuals without reopening approved temporal epochs.

    ``existing_tracks`` have already passed content-change segmentation,
    boundary reconciliation and provenance partitioning.  Running the broad
    near-duplicate coalescer over that authority again can bridge unrelated
    captions across scenes.  This used to happen even when every residual was
    rejected by local OCR: the mere presence of raw DBNet residual hits caused
    hundreds of valid epochs to collapse into a handful of full-video tracks.

    Residual candidates may still be fragmented, so they are coalesced among
    themselves before being appended.  Later duplicate/shadow guards may drop
    redundant residuals, but existing authority rows are never merged with one
    another in this pass.
    """

    authority = list(existing_tracks)
    residual = list(residual_tracks)
    consolidated_residual = (
        coalesce_near_duplicate_tracks(
            residual,
            frame_w=frame_w,
            frame_h=frame_h,
        )
        if residual
        else []
    )
    output = [*authority, *consolidated_residual]
    output.sort(
        key=lambda track: (
            int(track.start_frame),
            float(track.box_coords[1]),
            float(track.box_coords[0]),
        )
    )
    return output, {
        "policy_version": "residual_append_preserve_authority_v1",
        "authority_tracks_before": len(authority),
        "residual_tracks_before": len(residual),
        "residual_tracks_after_coalesce": len(consolidated_residual),
        "tracks_after_append": len(output),
        "authority_recoalesced": False,
    }


def crop_ink_score(frame_bgr: np.ndarray, xyxy: Sequence[float]) -> float:
    """
    Stroke / edge ink score inside a box (burn-in friendly; not Laplacian).

    Flat bright food scores low; thin white/dark glyphs with edges score high.
    """
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return 0.0
    crop = _crop_xyxy_from_frame(frame_bgr, xyxy)
    if crop is None or crop.size < 16:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enh = clahe.apply(gray)
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    tophat = cv2.morphologyEx(enh, cv2.MORPH_TOPHAT, ker)
    blackhat = cv2.morphologyEx(enh, cv2.MORPH_BLACKHAT, ker)
    sobel = cv2.Sobel(enh, cv2.CV_32F, 1, 0, ksize=3)
    edge = float(np.mean(np.abs(sobel)))
    stroke = float(np.mean(tophat) + np.mean(blackhat))
    lap = float(cv2.Laplacian(enh, cv2.CV_32F).var())
    return stroke / 25.0 + edge / 40.0 + lap / 500.0


def crop_stroke_orientation_balance(
    frame_bgr: np.ndarray, xyxy: Sequence[float]
) -> float:
    """Return 0..1 balance between horizontal and vertical stroke energy.

    Glyphs normally contain energy in both orientations. Cloth, hair and rails
    can score as strong ink while remaining strongly one-directional. This
    cheap local check is used only for the blank-recognizer hardsub fallback.
    """

    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return 0.0
    crop = _crop_xyxy_from_frame(frame_bgr, xyxy)
    if crop is None or crop.size < 16:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gx = float(np.mean(np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))))
    gy = float(np.mean(np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))))
    strongest = max(gx, gy)
    if strongest <= 1e-6:
        return 0.0
    return min(gx, gy) / strongest


def pick_ink_aware_keyframe(
    track: MergedTrack,
    *,
    frame_cache: Mapping[int, np.ndarray],
    frame_w: int,
    frame_h: int,
    max_candidates: int = 8,
) -> tuple[int, float]:
    """
    Choose the hit frame with the best burn-in ink score for keyframe/crop export.

    Falls back to ``best_frame_index`` when no cached frames score.
    """
    del frame_w, frame_h  # reserved for role-aware scoring
    order = [int(track.best_frame_index)]
    if track.hit_frames:
        ranked = sorted(
            range(len(track.hit_frames)),
            key=lambda i: float(
                (track.hit_sharpness[i] if i < len(track.hit_sharpness) else 0.0)
            ),
            reverse=True,
        )
        for i in ranked:
            fi = int(track.hit_frames[i])
            if fi not in order:
                order.append(fi)
            if len(order) >= max(1, int(max_candidates)):
                break
    best_fi = int(track.best_frame_index)
    best_score = -1.0
    for fi in order:
        frame = frame_cache.get(fi)
        if frame is None:
            continue
        score = crop_ink_score(frame, track.box_coords)
        if score > best_score:
            best_score = score
            best_fi = fi
    if best_score < 0.0:
        return int(track.best_frame_index), 0.0
    return best_fi, float(best_score)


def apply_ink_aware_keyframes(
    tracks: Sequence[MergedTrack],
    *,
    frame_cache: Mapping[int, np.ndarray],
    frame_w: int,
    frame_h: int,
) -> list[MergedTrack]:
    """Update each track's best_frame_index from ink-aware scoring when possible."""
    out: list[MergedTrack] = []
    for track in tracks:
        fi, score = pick_ink_aware_keyframe(
            track,
            frame_cache=frame_cache,
            frame_w=frame_w,
            frame_h=frame_h,
        )
        if fi == int(track.best_frame_index):
            out.append(track)
            continue
        out.append(
            MergedTrack(
                start_frame=int(track.start_frame),
                end_frame=int(track.end_frame),
                box_coords=list(track.box_coords),
                best_frame_index=int(fi),
                best_sharpness=max(float(track.best_sharpness), float(score)),
                centroid=tuple(track.centroid),
                hit_count=int(track.hit_count),
                hit_boxes=list(track.hit_boxes),
                hit_frames=list(track.hit_frames),
                hit_sharpness=list(track.hit_sharpness),
            )
        )
    return out


def crop_box_sharpness(frame_bgr: np.ndarray, xyxy: Sequence[float]) -> float:
    """Laplacian variance inside the text box (not the whole ROI)."""
    h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    x0 = max(0, min(w - 1, int(round(float(xyxy[0])))))
    y0 = max(0, min(h - 1, int(round(float(xyxy[1])))))
    x1 = max(x0 + 1, min(w, int(round(float(xyxy[2])))))
    y1 = max(y0 + 1, min(h, int(round(float(xyxy[3])))))
    crop = frame_bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return 0.0
    return _laplacian_sharpness(crop)


def roi_clahe_bgr(
    frame_bgr: np.ndarray,
    *,
    y0_frac: float = ROI_Y0,
    y1_frac: float = ROI_Y1,
) -> tuple[np.ndarray, int]:
    """
    Crop lower ROI, CLAHE on gray, stack to 3ch BGR for DBNet.

    Returns ``(roi_bgr, y_offset_px)``.
    """
    h, _w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    y0 = max(0, min(h - 1, int(round(h * float(y0_frac)))))
    y1 = max(y0 + 1, min(h, int(round(h * float(y1_frac)))))
    roi = frame_bgr[y0:y1, :]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=float(CLAHE_CLIP), tileGridSize=CLAHE_TILE)
    enhanced = clahe.apply(gray)
    stacked = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
    return stacked, y0


def overlay_stroke_enhance_bgr(roi_bgr: np.ndarray) -> np.ndarray:
    """
    Boost edited-in burn-in strokes (white/dark glyphs) for DBNet.

    CLAHE alone flattens thin hardsubs on bright food; tophat+blackhat recovers
    stroke ink while suppressing flat bowl texture. General for overlay CJK —
    not clip-specific geometry.
    """
    if roi_bgr is None or getattr(roi_bgr, "size", 0) == 0:
        raise ValueError("empty ROI for stroke enhance")
    if roi_bgr.ndim == 2:
        gray = roi_bgr
    else:
        gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=float(CLAHE_CLIP), tileGridSize=CLAHE_TILE)
    enh = clahe.apply(gray)
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    tophat = cv2.morphologyEx(enh, cv2.MORPH_TOPHAT, ker)
    blackhat = cv2.morphologyEx(enh, cv2.MORPH_BLACKHAT, ker)
    stroke = cv2.add(tophat, blackhat)
    boosted = np.clip(
        enh.astype(np.float32) * 0.45 + stroke.astype(np.float32) * 1.55,
        0.0,
        255.0,
    ).astype(np.uint8)
    return cv2.cvtColor(boosted, cv2.COLOR_GRAY2BGR)


def roi_phase1_detect_preps(
    frame_bgr: np.ndarray,
    *,
    y0_frac: float = ROI_Y0,
    y1_frac: float = ROI_Y1,
) -> list[tuple[str, np.ndarray, int]]:
    """
    Dual prep for overlay CJK detect: CLAHE + stroke-boosted ROI.

    Same ``y_offset`` for both so boxes map to the same full-frame coords.
    """
    h, _w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    y0 = max(0, min(h - 1, int(round(h * float(y0_frac)))))
    y1 = max(y0 + 1, min(h, int(round(h * float(y1_frac)))))
    roi = frame_bgr[y0:y1, :]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=float(CLAHE_CLIP), tileGridSize=CLAHE_TILE)
    clahe_bgr = cv2.cvtColor(clahe.apply(gray), cv2.COLOR_GRAY2BGR)
    stroke_bgr = overlay_stroke_enhance_bgr(roi)
    return [
        ("clahe", clahe_bgr, y0),
        ("stroke", stroke_bgr, y0),
    ]


def _xyxy_iou(a: Sequence[float], b: Sequence[float]) -> float:
    return box_iou(a, b)


def merge_frame_hit_boxes(
    hits: Sequence[DetectionHit],
    *,
    iou_thresh: float = 0.45,
) -> list[DetectionHit]:
    """
    Union DBNet boxes from dual prep on the same frame (greedy NMS by area).

    Prefer the larger box when two overlap — stroke path often completes a
    truncated CLAHE hardsub.
    """
    ordered = sorted(
        hits,
        key=lambda h: _box_area(h.box_xyxy),
        reverse=True,
    )
    kept: list[DetectionHit] = []
    for hit in ordered:
        if any(_xyxy_iou(hit.box_xyxy, k.box_xyxy) >= float(iou_thresh) for k in kept):
            continue
        kept.append(hit)
    kept.sort(key=lambda h: (h.box_xyxy[1], h.box_xyxy[0]))
    return kept


def merge_primary_and_residual_frame_hits(
    primary: Sequence[DetectionHit],
    residual: Sequence[DetectionHit],
    *,
    authority_iou: float = 0.45,
) -> list[DetectionHit]:
    """Prefer the raw risk-profile box over an overlapping primary slab."""
    residual_rows = merge_frame_hit_boxes(residual)
    unmatched_primary = [
        hit
        for hit in primary
        if not any(
            box_iou(hit.box_xyxy, authority.box_xyxy) >= float(authority_iou)
            for authority in residual_rows
        )
    ]
    return merge_frame_hit_boxes([*residual_rows, *unmatched_primary])


def _norm_box_to_full_xyxy(
    box: TextBox,
    *,
    roi_w: int,
    roi_h: int,
    y_offset: int,
) -> tuple[float, float, float, float]:
    """Map ROI-normalized TextBox → full-frame pixel xyxy."""
    x0 = float(box.x) * float(roi_w)
    y0 = float(box.y) * float(roi_h) + float(y_offset)
    x1 = (float(box.x) + float(box.width)) * float(roi_w)
    y1 = (float(box.y) + float(box.height)) * float(roi_h) + float(y_offset)
    return (x0, y0, x1, y1)


def _laplacian_sharpness(gray_or_bgr: np.ndarray) -> float:
    if gray_or_bgr.ndim == 3:
        gray = cv2.cvtColor(gray_or_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = gray_or_bgr
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _time_compatible(
    start: int,
    end: int,
    track_start: int,
    track_end: int,
    *,
    gap_max: int,
) -> bool:
    if end < track_start:
        return (track_start - end - 1) <= int(gap_max)
    if start > track_end:
        return (start - track_end - 1) <= int(gap_max)
    return True


def _box_height_compatible(
    a: Sequence[float],
    b: Sequence[float],
    *,
    min_ratio: float = 0.35,
) -> bool:
    """True when box heights are similar enough to share one track locus."""
    ha = max(1.0, float(a[3]) - float(a[1]))
    hb = max(1.0, float(b[3]) - float(b[1]))
    short, tall = (ha, hb) if ha <= hb else (hb, ha)
    ratio = short / tall
    # Wide burn-in stubs vs full lines may differ in height more than stacked
    # %% chips; keep a softer floor when either box is clearly a long line —
    # but not soft enough to glue a mid title onto a 3× taller rematch slab.
    wa = max(1.0, float(a[2]) - float(a[0]))
    wb = max(1.0, float(b[2]) - float(b[0]))
    if max(wa / ha, wb / hb) >= 2.5:
        return ratio >= 0.40
    return ratio >= float(min_ratio)


def _is_mid_overlay_box(
    xyxy: Sequence[float],
    *,
    frame_w: int | None,
    frame_h: int | None,
) -> bool:
    """Wide mid-frame editor copy (titles / card headers), not bottom hardsub."""
    if frame_w is None or frame_h is None:
        return False
    if _in_hardsub_y_band(xyxy, frame_w=frame_w, frame_h=frame_h):
        return False
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    w = max(1.0, x1 - x0)
    h = max(1.0, y1 - y0)
    cy = ((y0 + y1) * 0.5) / fh
    if cy < 0.25 or cy > 0.78:
        return False
    if (w / fw) < 0.12 and (w / h) < 2.0:
        return False
    return True


def _mid_overlay_geometry_compatible(
    a: Sequence[float],
    b: Sequence[float],
) -> bool:
    """Refuse mid-title ↔ rematch-slab merges that share cy but not size class."""
    ha = max(1.0, float(a[3]) - float(a[1]))
    hb = max(1.0, float(b[3]) - float(b[1]))
    wa = max(1.0, float(a[2]) - float(a[0]))
    wb = max(1.0, float(b[2]) - float(b[0]))
    h_ratio = min(ha, hb) / max(ha, hb)
    w_ratio = min(wa, wb) / max(wa, wb)
    return h_ratio >= 0.55 and w_ratio >= 0.65


def _box_x_interval_iou(a: Sequence[float], b: Sequence[float]) -> float:
    """1D IoU of the horizontal spans (ignores Y)."""
    ax0, ax1 = float(a[0]), float(a[2])
    bx0, bx1 = float(b[0]), float(b[2])
    if ax1 < ax0:
        ax0, ax1 = ax1, ax0
    if bx1 < bx0:
        bx0, bx1 = bx1, bx0
    inter = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    if inter <= 0.0:
        return 0.0
    union = (ax1 - ax0) + (bx1 - bx0) - inter
    if union <= 1e-9:
        return 0.0
    return float(inter / union)


def _aspect_looks_like_hardsub_line(xyxy: Sequence[float]) -> bool:
    """Geometry-only thin wide line (no frame size) — burn-in class for merge gates."""
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    w = max(1.0, x1 - x0)
    h = max(1.0, y1 - y0)
    if h > 120.0:
        return False
    return (w / h) >= float(HARDSUB_MIN_ASPECT)


def _hardsub_line_geometry_compatible(
    a: Sequence[float],
    b: Sequence[float],
    *,
    min_width_ratio: float = HARDSUB_MERGE_WIDTH_RATIO,
    min_x_iou: float = HARDSUB_MERGE_X_IOU,
    max_edge_delta: float = HARDSUB_MERGE_EDGE_DELTA,
) -> bool:
    """
    True when two bottom burn-in boxes look like the *same* line length/span.

    Different subtitle lines often keep a similar cy (and non-trivial IoU) while
    width / x-span jump; those must not share one SSOT track.
    """
    wa = max(1.0, float(a[2]) - float(a[0]))
    wb = max(1.0, float(b[2]) - float(b[0]))
    short_w, tall_w = (wa, wb) if wa <= wb else (wb, wa)
    width_ratio = short_w / tall_w
    x_iou = _box_x_interval_iou(a, b)
    edge_delta = (
        abs(float(a[0]) - float(b[0])) + abs(float(a[2]) - float(b[2]))
    ) / max(wa, wb)
    return (
        width_ratio >= float(min_width_ratio)
        and x_iou >= float(min_x_iou)
        and edge_delta <= float(max_edge_delta)
    )


def _x_span_mostly_contained(
    inner: Sequence[float],
    outer: Sequence[float],
    *,
    frac: float = 0.85,
) -> bool:
    """True when ``inner``'s x-span is mostly inside ``outer`` (truncate fragment)."""
    ix0, ix1 = float(inner[0]), float(inner[2])
    ox0, ox1 = float(outer[0]), float(outer[2])
    if ix1 < ix0:
        ix0, ix1 = ix1, ix0
    if ox1 < ox0:
        ox0, ox1 = ox1, ox0
    iw = max(1.0, ix1 - ix0)
    inter = max(0.0, min(ix1, ox1) - max(ix0, ox0))
    return (inter / iw) >= float(frac)


def _both_hardsub_line_boxes(
    a: Sequence[float],
    b: Sequence[float],
    *,
    frame_w: int | None = None,
    frame_h: int | None = None,
) -> bool:
    if frame_w is not None and frame_h is not None:
        return _box_looks_like_thin_hardsub(
            a, frame_w=int(frame_w), frame_h=int(frame_h)
        ) and _box_looks_like_thin_hardsub(
            b, frame_w=int(frame_w), frame_h=int(frame_h)
        )
    if not (
        _aspect_looks_like_hardsub_line(a) and _aspect_looks_like_hardsub_line(b)
    ):
        return False
    cy_a = 0.5 * (float(a[1]) + float(a[3]))
    cy_b = 0.5 * (float(b[1]) + float(b[3]))
    return abs(cy_a - cy_b) <= 48.0


def merge_tracks_by_centroid(
    hits: Sequence[DetectionHit],
    *,
    frame_count: int,
    pad: int = PADDING,
    max_centroid_px: float = CENTROID_MERGE_PX,
    min_iou: float = MIN_MERGE_IOU,
    gap_max: int = MERGE_GAP_FRAMES,
    frame_w: int | None = None,
    frame_h: int | None = None,
) -> list[MergedTrack]:
    """
    Union padded lifespans when locus matches (centroid OR IoU) and gap is short.

    Stable box = median of member hits; keyframe = sharpest crop score.
    """
    tracks: list[MergedTrack] = []
    ordered = sorted(hits, key=lambda h: (h.frame_index, h.box_xyxy[0]))
    for hit in ordered:
        start, end = apply_temporal_pad(
            hit.frame_index, frame_count=frame_count, pad=pad
        )
        cx, cy = _box_centroid(hit.box_xyxy)
        merged_into: MergedTrack | None = None
        for track in tracks:
            tcx, tcy = track.centroid
            dist = ((cx - tcx) ** 2 + (cy - tcy) ** 2) ** 0.5
            iou = box_iou(hit.box_xyxy, track.box_coords)
            # Tall rematch unions share the column centroid with thin %% rows —
            # require similar height so stacked mid labels stay separate tracks.
            same_locus = _box_height_compatible(
                hit.box_xyxy, track.box_coords
            ) and (dist < float(max_centroid_px) or iou >= float(min_iou))
            if same_locus and _both_hardsub_line_boxes(
                hit.box_xyxy,
                track.box_coords,
                frame_w=frame_w,
                frame_h=frame_h,
            ):
                # Compare to the *last* hardsub hit AND the segment seed —
                # expansive / gradual drift otherwise absorbs later lines.
                ref_last = (
                    track.hit_boxes[-1]
                    if track.hit_boxes
                    else track.box_coords
                )
                ref_seed = (
                    track.hit_boxes[0]
                    if track.hit_boxes
                    else track.box_coords
                )
                same_locus = _hardsub_line_geometry_compatible(
                    hit.box_xyxy, ref_last
                ) and _hardsub_line_geometry_compatible(
                    hit.box_xyxy, ref_seed
                )
            elif same_locus and _is_mid_overlay_box(
                hit.box_xyxy, frame_w=frame_w, frame_h=frame_h
            ) and _is_mid_overlay_box(
                track.box_coords, frame_w=frame_w, frame_h=frame_h
            ):
                # Mid titles must not absorb later rematch slabs / partial chips.
                ref_last = (
                    track.hit_boxes[-1]
                    if track.hit_boxes
                    else track.box_coords
                )
                same_locus = _mid_overlay_geometry_compatible(
                    hit.box_xyxy, ref_last
                ) and _mid_overlay_geometry_compatible(
                    hit.box_xyxy, track.box_coords
                )
            if not same_locus:
                continue
            if not _time_compatible(
                start,
                end,
                track.start_frame,
                track.end_frame,
                gap_max=gap_max,
            ):
                continue
            merged_into = track
            break
        if merged_into is None:
            tracks.append(
                MergedTrack(
                    start_frame=start,
                    end_frame=end,
                    box_coords=[float(v) for v in hit.box_xyxy],
                    best_frame_index=int(hit.frame_index),
                    best_sharpness=float(hit.sharpness),
                    centroid=(cx, cy),
                    hit_count=1,
                    hit_boxes=[tuple(float(v) for v in hit.box_xyxy)],
                    hit_frames=[int(hit.frame_index)],
                    hit_sharpness=[float(hit.sharpness)],
                )
            )
            continue
        merged_into.start_frame = min(merged_into.start_frame, start)
        merged_into.end_frame = max(merged_into.end_frame, end)
        merged_into.hit_count += 1
        merged_into.hit_boxes.append(tuple(float(v) for v in hit.box_xyxy))
        merged_into.hit_frames.append(int(hit.frame_index))
        merged_into.hit_sharpness.append(float(hit.sharpness))
        expansive = _hardsub_should_use_expansive_stable(merged_into.hit_boxes)
        merged_into.box_coords = stable_box_xyxy(
            merged_into.hit_boxes, expansive=expansive
        )
        merged_into.centroid = _box_centroid(merged_into.box_coords)
        if float(hit.sharpness) >= float(merged_into.best_sharpness):
            merged_into.best_sharpness = float(hit.sharpness)
            merged_into.best_frame_index = int(hit.frame_index)
    tracks.sort(key=lambda t: (t.start_frame, t.box_coords[0]))
    return tracks


def confirm_tracks(
    tracks: Sequence[MergedTrack],
    *,
    min_hits: int = MIN_HITS_TO_CONFIRM,
    strong_single_frame_indices: Sequence[int] = (),
) -> tuple[list[MergedTrack], list[MergedTrack]]:
    """Keep tracks with ≥ min_hits; return (kept, dropped_suspects)."""
    kept: list[MergedTrack] = []
    dropped: list[MergedTrack] = []
    need = max(1, int(min_hits))
    strong = {int(value) for value in strong_single_frame_indices}
    for track in tracks:
        independently_confirmed_single = (
            int(track.hit_count) == 1
            and any(int(value) in strong for value in track.hit_frames)
        )
        if int(track.hit_count) >= need or independently_confirmed_single:
            kept.append(track)
        else:
            dropped.append(track)
    return kept, dropped


def _hardsub_should_use_expansive_stable(
    boxes: Sequence[Sequence[float]],
) -> bool:
    """Expansive x only when some hits are clearly wider (truncated-median fossil)."""
    if len(boxes) < 2:
        return False
    arr = np.asarray([[float(v) for v in b[:4]] for b in boxes], dtype=np.float64)
    sample = [float(np.median(arr[:, i])) for i in range(4)]
    cy = (sample[1] + sample[3]) * 0.5
    h = sample[3] - sample[1]
    if cy < 840.0 or h > 120.0:
        return False
    x1_spread = float(np.percentile(arr[:, 2], 90) - np.median(arr[:, 2]))
    return x1_spread >= 80.0


def _rebuild_track_from_hits(
    frames: Sequence[int],
    boxes: Sequence[Sequence[float]],
    sharpness: Sequence[float],
    *,
    frame_count: int,
    pad: int,
) -> MergedTrack:
    hit_boxes = [tuple(float(v) for v in b[:4]) for b in boxes]
    hit_frames = [int(f) for f in frames]
    hit_sharp = [float(s) for s in sharpness]
    expansive = _hardsub_should_use_expansive_stable(hit_boxes)
    stable = stable_box_xyxy(hit_boxes, expansive=expansive)
    best_i = max(range(len(hit_sharp)), key=lambda i: hit_sharp[i])
    start = max(0, min(hit_frames) - int(pad))
    end = min(max(0, int(frame_count) - 1), max(hit_frames) + int(pad))
    return MergedTrack(
        start_frame=start,
        end_frame=end,
        box_coords=stable,
        best_frame_index=hit_frames[best_i],
        best_sharpness=hit_sharp[best_i],
        centroid=_box_centroid(stable),
        hit_count=len(hit_frames),
        hit_boxes=hit_boxes,
        hit_frames=hit_frames,
        hit_sharpness=hit_sharp,
    )


def shrink_track_to_evidence(
    track: MergedTrack,
    *,
    frame_count: int,
    pad: int = POST_EVIDENCE_PAD,
) -> MergedTrack:
    """Clamp lifespan to real hit frames (± small fade pad)."""
    if not track.hit_frames:
        return track
    return _rebuild_track_from_hits(
        track.hit_frames,
        track.hit_boxes,
        track.hit_sharpness or [track.best_sharpness] * len(track.hit_frames),
        frame_count=frame_count,
        pad=pad,
    )


def split_overmerged_tracks(
    tracks: Sequence[MergedTrack],
    *,
    gap_max: int = SPLIT_GAP_FRAMES,
    min_iou: float = SPLIT_MIN_IOU,
    max_centroid_px: float = SPLIT_CENTROID_PX,
    frame_count: int | None = None,
    pad: int = POST_EVIDENCE_PAD,
    frame_w: int | None = None,
    frame_h: int | None = None,
    editor_gap_max: int | None = None,
) -> list[MergedTrack]:
    """
    Split a track when consecutive hits jump in time/geometry (over-merge undo).
    """
    out: list[MergedTrack] = []
    for track in tracks:
        n = len(track.hit_frames)
        if n <= 1 or len(track.hit_boxes) != n:
            out.append(track)
            continue
        order = sorted(range(n), key=lambda i: track.hit_frames[i])
        segments: list[list[int]] = [[order[0]]]
        for idx in order[1:]:
            prev = segments[-1][-1]
            gap = int(track.hit_frames[idx]) - int(track.hit_frames[prev]) - 1
            iou = box_iou(track.hit_boxes[idx], track.hit_boxes[prev])
            c0 = _box_centroid(track.hit_boxes[prev])
            c1 = _box_centroid(track.hit_boxes[idx])
            dist = ((c0[0] - c1[0]) ** 2 + (c0[1] - c1[1]) ** 2) ** 0.5
            allowed_gap = int(gap_max)
            if (
                editor_gap_max is not None
                and int(editor_gap_max) > allowed_gap
                and _is_mid_overlay_box(
                    track.hit_boxes[prev], frame_w=frame_w, frame_h=frame_h
                )
                and _is_mid_overlay_box(
                    track.hit_boxes[idx], frame_w=frame_w, frame_h=frame_h
                )
                and _mid_overlay_geometry_compatible(
                    track.hit_boxes[prev], track.hit_boxes[idx]
                )
            ):
                allowed_gap = int(editor_gap_max)
            broke = gap > allowed_gap or (
                iou < float(min_iou) and dist > float(max_centroid_px)
            )
            if not broke and _both_hardsub_line_boxes(
                track.hit_boxes[prev],
                track.hit_boxes[idx],
                frame_w=frame_w,
                frame_h=frame_h,
            ):
                seed = track.hit_boxes[segments[-1][0]]
                cur = track.hit_boxes[idx]
                last = track.hit_boxes[prev]
                broke = not (
                    _hardsub_line_geometry_compatible(last, cur)
                    and _hardsub_line_geometry_compatible(seed, cur)
                )
            if broke:
                segments.append([idx])
            else:
                segments[-1].append(idx)
        fc = int(frame_count) if frame_count is not None else (track.end_frame + 1)
        sharps = track.hit_sharpness or [track.best_sharpness] * n
        for seg in segments:
            out.append(
                _rebuild_track_from_hits(
                    [track.hit_frames[i] for i in seg],
                    [track.hit_boxes[i] for i in seg],
                    [sharps[i] for i in seg],
                    frame_count=fc,
                    pad=pad,
                )
            )
    out.sort(key=lambda t: (t.start_frame, t.box_coords[0]))
    return out


def is_chrome_noise_box(
    xyxy: Sequence[float],
    *,
    frame_w: int,
    frame_h: int,
) -> bool:
    """Tiny / edge-strip boxes that are usually Douyin UI chrome, not burn-in copy."""
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    w = x1 - x0
    h = y1 - y0
    # Absolute floor matches detection geometry — not editor list chips.
    if w < MIN_BOX_WIDTH_PX or h < MIN_BOX_HEIGHT_PX:
        return True
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))
    cx = (x0 + x1) * 0.5
    cy = (y0 + y1) * 0.5
    edge = CHROME_EDGE_FRAC * fw
    # Side-strip chrome: centroid in the edge band, or box overlaps it.
    if w <= CHROME_EDGE_MAX_W_PX and (
        cx < edge
        or cx > fw - edge
        or x0 < edge
        or x1 > fw - edge
    ):
        return True
    # Narrow stubs hugging top/bottom chrome bands (not mid-card list names).
    if w < CHROME_MIN_W_PX and (cy < 0.08 * fh or cy > 0.92 * fh):
        return True
    return False


def purge_chrome_tracks(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[list[MergedTrack], list[MergedTrack]]:
    kept: list[MergedTrack] = []
    purged: list[MergedTrack] = []
    for track in tracks:
        if is_chrome_noise_box(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        ) and not _has_dense_ui_grid_peer_evidence(
            track,
            tracks,
            frame_w=frame_w,
            frame_h=frame_h,
        ):
            purged.append(track)
        else:
            kept.append(track)
    return kept, purged


def finalize_confirmed_tracks(
    tracks: Sequence[MergedTrack],
    *,
    frame_count: int,
    frame_w: int,
    frame_h: int,
    min_hits: int = MIN_HITS_TO_CONFIRM,
    split_gap_max: int = SPLIT_GAP_FRAMES,
    editor_split_gap_max: int | None = None,
    strong_single_frame_indices: Sequence[int] = (),
) -> tuple[list[MergedTrack], dict[str, Any]]:
    """
    Last-mile polish before OCR: split over-merge → shrink to evidence → purge chrome.
    """
    before = list(tracks)
    split = split_overmerged_tracks(
        before,
        gap_max=split_gap_max,
        frame_count=frame_count,
        pad=POST_EVIDENCE_PAD,
        frame_w=frame_w,
        frame_h=frame_h,
        editor_gap_max=editor_split_gap_max,
    )
    split_events = []
    if len(split) > len(before):
        split_events.append(
            {"before": len(before), "after_split": len(split)}
        )

    shrunk_rows: list[dict[str, Any]] = []
    shrunk: list[MergedTrack] = []
    for track in split:
        after = shrink_track_to_evidence(
            track, frame_count=frame_count, pad=POST_EVIDENCE_PAD
        )
        if after.start_frame != track.start_frame or after.end_frame != track.end_frame:
            shrunk_rows.append(
                {
                    "before": [track.start_frame, track.end_frame],
                    "after": [after.start_frame, after.end_frame],
                    "hit_count": after.hit_count,
                }
            )
        shrunk.append(after)

    # Re-drop segments that fell below confirm after split.
    confirmed, re_dropped = confirm_tracks(
        shrunk,
        min_hits=min_hits,
        strong_single_frame_indices=strong_single_frame_indices,
    )
    cleaned, purged = purge_chrome_tracks(
        confirmed, frame_w=frame_w, frame_h=frame_h
    )
    cleaned.sort(key=lambda t: (t.start_frame, t.box_coords[0]))
    audit: dict[str, Any] = {
        "before_count": len(before),
        "after_count": len(cleaned),
        "split_events": split_events,
        "shrunk": shrunk_rows,
        "purged_chrome": len(purged),
        "re_dropped_after_split": len(re_dropped),
        "purged_chrome_boxes": [_track_to_suspect_dict(t) for t in purged],
        "re_dropped_boxes": [_track_to_suspect_dict(t) for t in re_dropped],
    }
    return cleaned, audit


def timeline_entry_dict(
    *,
    text_id: str,
    start_frame: int,
    end_frame: int,
    fps: float,
    box_coords: Sequence[float],
    best_keyframe_path: str,
    text: str = "",
    hit_count: int | None = None,
    crop_path: str | None = None,
    best_frame_index: int | None = None,
    hit_frames: Sequence[int] | None = None,
    boundary_evidence: Mapping[str, Any] | None = None,
    semantic_role: str | None = None,
    visual_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rate = float(fps) if float(fps) > 1e-6 else 30.0
    start_s = float(start_frame) / rate
    end_s = float(end_frame) / rate
    entry: dict[str, Any] = {
        "text_id": str(text_id),
        "start_frame": int(start_frame),
        "end_frame": int(end_frame),
        "start_time": format_timeline_time(start_s),
        "end_time": format_timeline_time(end_s),
        "box_coords": [float(v) for v in box_coords],
        "best_keyframe_path": str(best_keyframe_path),
    }
    if hit_count is not None:
        entry["hit_count"] = int(hit_count)
    if crop_path:
        entry["crop_path"] = str(crop_path)
    if best_frame_index is not None:
        entry["best_frame_index"] = int(best_frame_index)
    if hit_frames is not None:
        entry["hit_frames"] = sorted({int(f) for f in hit_frames})
    if boundary_evidence is not None:
        entry["boundary_evidence"] = dict(boundary_evidence)
    if semantic_role:
        entry["semantic_role"] = str(semantic_role)
    if visual_provenance:
        entry["visual_provenance"] = dict(visual_provenance)
    if text:
        entry["text"] = str(text)
    return entry


def semantic_scene_role_for_track(
    track: MergedTrack, text_audit: Mapping[str, Any]
) -> str | None:
    """Carry audited semantic-scene provenance through later track rebuilds."""
    rows = list(
        dict(text_audit.get("semantic_scene_label") or {}).get("rows") or []
    )
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        box = list(raw.get("box") or [])
        if len(box) < 4 or box_iou(track.box_coords, box) < 0.20:
            continue
        overlap = max(
            0,
            min(int(track.end_frame), int(raw.get("end_frame") or 0))
            - max(int(track.start_frame), int(raw.get("start_frame") or 0))
            + 1,
        )
        track_span = max(1, int(track.end_frame) - int(track.start_frame) + 1)
        if overlap / float(track_span) >= 0.50:
            return "semantic_scene_label"
    return None


def classify_visual_text_provenance(
    tracks: Sequence[MergedTrack],
    *,
    frame_w: int,
    frame_h: int,
    text_audit: Mapping[str, Any],
    frame_cache: Mapping[int, np.ndarray] | None = None,
) -> dict[int, dict[str, Any]]:
    """Classify localization authority before OCR touches source-scene text.

    The conservative order matters: explicit scene semantics and dense compact
    device panels are protected; hardsubs/editor-card anchors are localized;
    ambiguous locked micro UI is surfaced for operator provenance review.
    """

    compact_source_ids = compact_scene_ui_cluster_member_ids(
        tracks, frame_w=frame_w, frame_h=frame_h
    )
    caption_lane_ids = sequential_caption_lane_member_ids(
        tracks, frame_w=frame_w, frame_h=frame_h
    )
    perspective_ids = perspective_ui_provenance_member_ids(
        tracks, frame_w=frame_w, frame_h=frame_h
    )
    dense_panel_ids = dense_source_ui_panel_member_ids(
        tracks, frame_w=frame_w, frame_h=frame_h
    )
    dense_panel_context_ids = dense_source_ui_context_member_ids(
        tracks,
        dense_panel_ids=dense_panel_ids,
        frame_w=frame_w,
        frame_h=frame_h,
    )
    repeated_source_row_ids = repeated_source_ui_row_member_ids(
        tracks,
        dense_panel_ids=dense_panel_ids,
    )
    strong_source_ids = set(dense_panel_context_ids) | set(repeated_source_row_ids)
    for track in tracks:
        if str(getattr(track, "_source_intrinsic_candidate", "") or ""):
            strong_source_ids.add(id(track))
        elif not is_horizontally_locked_track(
            track, frame_w=frame_w, frame_h=frame_h
        ):
            strong_source_ids.add(id(track))
    panel_containment_ids = source_panel_containment_member_ids(
        tracks,
        strong_source_ids=strong_source_ids,
        frame_w=frame_w,
        frame_h=frame_h,
    )
    anchors = [
        track
        for track in tracks
        if is_editor_card_anchor_track(track, frame_w=frame_w, frame_h=frame_h)
    ]
    # A DBNet box from a second line of an editor caption can be absorbed into
    # the dense phone/UI cohort (especially when the source frame also shows a
    # device).  Do not let that inherited source label punch a hole through the
    # editor caption plate.  Only use an anchor that is not itself backed by
    # source-plane evidence, and require strong temporal + horizontal
    # correspondence with the anchor.  This keeps genuine phone labels outside
    # the caption lane protected while resolving the common two-line caption
    # shadow case.
    editor_anchor_candidates = [
        anchor
        for anchor in anchors
        if id(anchor) not in strong_source_ids
        and id(anchor) not in panel_containment_ids
    ]
    fw = max(1.0, float(frame_w))
    fh = max(1.0, float(frame_h))

    def _editor_caption_sibling(track: MergedTrack) -> bool:
        x0, y0, x1, y1 = (float(value) for value in track.box_coords[:4])
        track_width = max(1.0, x1 - x0)
        track_width_frac = track_width / fw
        if track_width_frac < 0.14:
            return False
        for anchor in editor_anchor_candidates:
            if not _tracks_time_overlap(track, anchor):
                continue
            anchor_span = max(
                1, int(anchor.end_frame) - int(anchor.start_frame) + 1
            )
            overlap_frames = max(
                0,
                min(int(track.end_frame), int(anchor.end_frame))
                - max(int(track.start_frame), int(anchor.start_frame))
                + 1,
            )
            track_span = max(
                1, int(track.end_frame) - int(track.start_frame) + 1
            )
            if overlap_frames / float(min(anchor_span, track_span)) < 0.75:
                continue
            ax0, ay0, ax1, ay1 = (float(value) for value in anchor.box_coords[:4])
            horizontal_intersection = max(0.0, min(x1, ax1) - max(x0, ax0))
            if horizontal_intersection / min(track_width, max(1.0, ax1 - ax0)) < 0.80:
                continue
            vertical_gap = max(0.0, ay0 - y1, y0 - ay1)
            if vertical_gap > max(0.018 * fh, 1.5 * max(y1 - y0, ay1 - ay0)):
                continue
            return True
        return False
    near_limit = 0.55 * min(fw, fh)

    def _near_editor_anchor(track: MergedTrack) -> bool:
        tx, ty = _box_centroid(track.box_coords)
        for anchor in anchors:
            if not _tracks_time_overlap(track, anchor):
                continue
            ax, ay = _box_centroid(anchor.box_coords)
            if ((tx - ax) ** 2 + (ty - ay) ** 2) ** 0.5 <= near_limit:
                return True
        return False

    def _temporal_overlap_ratio(left: MergedTrack, right: MergedTrack) -> float:
        overlap = max(
            0,
            min(int(left.end_frame), int(right.end_frame))
            - max(int(left.start_frame), int(right.start_frame))
            + 1,
        )
        shorter = max(
            1,
            min(
                int(left.end_frame) - int(left.start_frame) + 1,
                int(right.end_frame) - int(right.start_frame) + 1,
            ),
        )
        return overlap / float(shorter)

    def _row_has_solid_panel(track: MergedTrack) -> bool:
        if frame_cache is None:
            return False
        return any(
            has_solid_colored_editor_panel(frame, track.box_coords)
            or has_solid_neutral_editor_panel(frame, track.box_coords)
            for frame in _cached_frames_for_track(
                track, frame_cache, max_frames=3
            )
        )

    def _track_has_containing_panel(track: MergedTrack) -> bool:
        """Return true only when a detected solid component contains the row."""
        if frame_cache is None:
            return False
        return any(
            editor_card_panel_bounds(frame, track.box_coords) is not None
            for frame in _cached_frames_for_track(track, frame_cache, max_frames=3)
        )

    # A multi-row editor card is one visual object.  Geometry-first source
    # partitioning used to classify one small row as SOURCE_INTRINSIC and an
    # adjacent row as EDITOR_OVERLAY, leaving holes in the card.  Build a
    # strong, local group authority before the per-row decision: synchronized
    # solid-panel rows may inherit editor provenance only from an independently
    # confirmed editor anchor/caption peer.  Source phone/app panels lack that
    # peer and stay protected.
    solid_panel_ids = {
        id(track)
        for track in tracks
        if _row_has_solid_panel(track)
        and _track_has_containing_panel(track)
    }
    editor_card_panel_boxes: dict[int, list[float]] = {}
    if frame_cache is not None:
        for track in tracks:
            if id(track) not in solid_panel_ids:
                continue
            candidates = [
                bounds
                for frame in _cached_frames_for_track(
                    track, frame_cache, max_frames=3
                )
                if (
                    bounds := editor_card_panel_bounds(
                        frame, track.box_coords
                    )
                )
                is not None
            ]
            if not candidates:
                continue
            editor_card_panel_boxes[id(track)] = max(
                candidates,
                key=lambda box: max(1.0, box[2] - box[0])
                * max(1.0, box[3] - box[1]),
            )
    editor_card_anchor_ids = {
        id(track)
        for track in tracks
        if id(track) in solid_panel_ids
        and (
            id(track) in caption_lane_ids
            or (
                is_editor_card_anchor_track(
                    track, frame_w=frame_w, frame_h=frame_h
                )
                and id(track) not in strong_source_ids
                and id(track) not in panel_containment_ids
            )
        )
    }
    editor_card_group_ids: set[int] = set(editor_card_anchor_ids)
    if editor_card_anchor_ids:
        changed = True
        while changed:
            changed = False
            current_members = [
                track for track in tracks if id(track) in editor_card_group_ids
            ]
            for track in tracks:
                if id(track) in editor_card_group_ids:
                    continue
                tx0, ty0, tx1, ty1 = (
                    float(value) for value in track.box_coords[:4]
                )
                track_height = max(1.0, ty1 - ty0)
                track_width = max(1.0, tx1 - tx0)
                for peer in current_members:
                    if _temporal_overlap_ratio(track, peer) < 0.65:
                        continue
                    px0, py0, px1, py1 = (
                        float(value) for value in peer.box_coords[:4]
                    )
                    peer_height = max(1.0, py1 - py0)
                    horizontal_gap = max(0.0, px0 - tx1, tx0 - px1)
                    vertical_gap = max(0.0, py0 - ty1, ty0 - py1)
                    horizontal_overlap = max(
                        0.0, min(tx1, px1) - max(tx0, px0)
                    )
                    same_panel = bool(
                        horizontal_gap <= 0.035 * fw
                        and vertical_gap
                        <= max(0.040 * fh, 2.0 * max(track_height, peer_height))
                        and (
                            horizontal_overlap
                            / min(track_width, max(1.0, px1 - px0))
                            >= 0.15
                            or horizontal_gap <= 0.012 * fw
                        )
                    )
                    peer_panel = editor_card_panel_boxes.get(id(peer))
                    candidate_inside_panel = False
                    if peer_panel is not None:
                        px0, py0, px1, py1 = (float(value) for value in peer_panel[:4])
                        overlap_area = max(0.0, min(tx1, px1) - max(tx0, px0)) * max(
                            0.0, min(ty1, py1) - max(ty0, py0)
                        )
                        track_area = max(1.0, (tx1 - tx0) * (ty1 - ty0))
                        candidate_inside_panel = overlap_area / track_area >= 0.55
                        # A nearby caption below a solid card is a separate
                        # physical object.  The former proximity fallback let
                        # that caption inherit the card component even when it
                        # lay completely outside the detected panel.  Phase 4
                        # then processed the card once and suppressed the real
                        # caption cover as a duplicate.  Once a peer has a
                        # frame-derived panel boundary, containment—not a
                        # loose row gap—is the authority for membership.
                        if not candidate_inside_panel:
                            same_panel = False
                    # A row that is not itself contained by the peer's
                    # component must not inherit panel provenance merely from
                    # a nearby row.  This prevents a lower-third caption from
                    # being absorbed into an upper product-card panel.
                    if same_panel and (
                        candidate_inside_panel or _track_has_containing_panel(track)
                    ) or candidate_inside_panel:
                        editor_card_group_ids.add(id(track))
                        changed = True
                        break

    output: dict[int, dict[str, Any]] = {}
    for track in tracks:
        role = classify_ocr_box_role(
            track.box_coords, frame_w=frame_w, frame_h=frame_h
        )
        semantic_role = semantic_scene_role_for_track(track, text_audit)
        locked = is_horizontally_locked_track(
            track, frame_w=frame_w, frame_h=frame_h
        )
        x0, y0, x1, y1 = (float(value) for value in track.box_coords[:4])
        width_frac = max(1.0, x1 - x0) / fw
        height_frac = max(1.0, y1 - y0) / fh
        source_candidate_hint = str(
            getattr(track, "_source_intrinsic_candidate", "") or ""
        )
        reasons: list[str]
        if id(track) in editor_card_group_ids:
            classification, confidence = "EDITOR_OVERLAY", 0.985
            reasons = [
                "solid_editor_card_group",
                "temporally_synchronized_editor_anchor_peer",
                "group_provenance_overrides_early_source_partition",
            ]
        elif int(track.hit_count) == 1:
            classification, confidence = "UNCERTAIN", 0.50
            reasons = [
                (
                    "single_frame_local_cjk_confirmed"
                    if bool(getattr(track, "_single_frame_cjk_confirmed", False))
                    else "single_frame_temporal_evidence_insufficient"
                ),
                "single_frame_provenance_requires_review",
            ]
        elif semantic_role == "semantic_scene_label":
            classification, confidence = "SOURCE_INTRINSIC", 0.99
            reasons = ["audited_semantic_scene_label"]
        elif _editor_caption_sibling(track):
            classification, confidence = "EDITOR_OVERLAY", 0.95
            reasons = [
                "editor_caption_sibling_of_wide_locked_anchor",
                "caption_lane_provenance_overrides_dense_source_context",
            ]
        elif id(track) in caption_lane_ids:
            classification, confidence = "EDITOR_OVERLAY", 0.98
            reasons = [
                "sequential_screen_locked_caption_lane",
                "caption_lane_geometry_overrides_upper_band_generic_role",
            ]
        elif id(track) in dense_panel_ids:
            classification, confidence = "SOURCE_INTRINSIC", 0.98
            reasons = [
                "dense_source_ui_panel_plane",
                "synchronized_multi_row_multi_column_cohort",
            ]
        elif source_candidate_hint:
            classification, confidence = "SOURCE_INTRINSIC", 0.93
            reasons = [
                "pre_editor_postprocess_source_partition",
                source_candidate_hint,
            ]
        elif id(track) in repeated_source_row_ids:
            classification, confidence = "SOURCE_INTRINSIC", 0.97
            reasons = [
                "repeated_source_ui_row",
                "stable_fragment_family_near_dense_panel",
            ]
        elif id(track) in panel_containment_ids:
            classification, confidence = "SOURCE_INTRINSIC_PANEL", 0.97
            reasons = [
                "contained_by_source_ui_plane",
                "temporally_overlapping_spatially_diverse_source_peers",
                "source_plane_evidence_overrides_caption_shape",
            ]
        elif role == "hardsub":
            classification, confidence = "EDITOR_OVERLAY", 0.99
            reasons = ["hardsub_line_geometry"]
        elif id(track) in dense_panel_context_ids:
            classification, confidence = "SOURCE_INTRINSIC", 0.96
            reasons = [
                "dense_source_ui_context_propagation",
                "thin_label_with_proven_panel_peers",
            ]
        elif (
            locked
            and role != "hardsub"
            and width_frac <= 0.18
            and height_frac <= 0.025
            and int(track.hit_count) >= 3
            and int(track.end_frame) - int(track.start_frame) + 1 >= 45
        ):
            # Long-lived compact values inside an app/device surface (for
            # example a camera aperture modal) are source UI. Editor copy this
            # small is ambiguous, so preservation is the fail-closed action.
            classification, confidence = "SOURCE_INTRINSIC_PANEL", 0.94
            reasons = [
                "long_lived_compact_locked_ui_value",
                "preserve_source_when_editor_provenance_is_ambiguous",
            ]
        elif is_editor_card_anchor_track(
            track, frame_w=frame_w, frame_h=frame_h
        ):
            consensus_count = int(getattr(track, "_local_text_consensus_count", 0) or 0)
            consensus_cjk = int(getattr(track, "_local_text_cjk_max", 0) or 0)
            # Geometry alone is not enough for a compact/mid-face rectangle:
            # hair, skin texture and jewellery are frequently screen-locked
            # for a short epoch.  A wide anchor must have repeated local text
            # evidence; otherwise preserve it as uncertain for review.
            consensus_known = hasattr(track, "_local_text_consensus_count")
            if (not consensus_known) or (consensus_count >= 2 and consensus_cjk >= 1):
                classification, confidence = "EDITOR_OVERLAY", 0.97
                reasons = ["wide_locked_editor_card_anchor", "multiframe_local_text_consensus"]
            else:
                classification, confidence = "UNCERTAIN", 0.50
                reasons = [
                    "wide_locked_geometry_without_multiframe_text_consensus",
                    "preserve_source_when_editor_provenance_is_ambiguous",
                ]
        elif id(track) in compact_source_ids:
            classification, confidence = "SOURCE_INTRINSIC", 0.96
            reasons = [
                "dense_compact_source_panel",
                "no_nearby_editor_card_anchor",
            ]
        elif id(track) in perspective_ids and not _near_editor_anchor(track):
            classification, confidence = "SOURCE_INTRINSIC", 0.91
            reasons = [
                "spatially_broad_perspective_ui_cohort",
                "no_nearby_editor_card_anchor",
            ]
        elif not locked:
            classification, confidence = "SOURCE_INTRINSIC", 0.94
            reasons = ["text_geometry_moves_with_source_scene"]
        elif (
            role in {"mid_label", "ui_chip"}
            and width_frac <= 0.10
            and height_frac <= 0.065
            and not _near_editor_anchor(track)
        ):
            classification, confidence = "UNCERTAIN", 0.50
            reasons = ["locked_micro_ui_without_provenance_anchor"]
        else:
            classification, confidence = "EDITOR_OVERLAY", 0.90
            reasons = ["screen_locked_localization_track"]
        output[id(track)] = {
            "classification": classification,
            "confidence": round(float(confidence), 4),
            "policy_version": VISUAL_TEXT_PROVENANCE_SCHEMA_VERSION,
            "reasons": reasons,
        }
        if id(track) in editor_card_group_ids:
            member_panel_boxes = [
                editor_card_panel_boxes[id(member)]
                for member in tracks
                if id(member) in editor_card_group_ids
                and id(member) in editor_card_panel_boxes
                and _temporal_overlap_ratio(track, member) >= 0.65
            ]
            if member_panel_boxes:
                output[id(track)]["editor_card_panel_box"] = [
                    min(box[0] for box in member_panel_boxes),
                    min(box[1] for box in member_panel_boxes),
                    max(box[2] for box in member_panel_boxes),
                    max(box[3] for box in member_panel_boxes),
                ]
                output[id(track)]["editor_card_panel_policy"] = (
                    "solid_neutral_editor_card_group_v1"
                )
    return output


def build_text_frame_coverage(
    hits: Sequence[DetectionHit],
    *,
    frame_count: int,
    frame_w: int,
    frame_h: int,
    scanned_frames: Sequence[int] | None = None,
) -> dict[str, Any]:
    """
    Pre-gate detection SSOT: every frame that had ≥1 geometry-plausible text hit.

    Track merge / local-text / chrome gates must not erase this index — it is the
    authority for which frames contain text before FP filtering.
    """
    by_frame: dict[int, list[dict[str, Any]]] = {}
    for hit in hits:
        fi = int(hit.frame_index)
        if fi < 0 or fi >= int(frame_count):
            continue
        role = classify_ocr_box_role(
            hit.box_xyxy, frame_w=int(frame_w), frame_h=int(frame_h)
        )
        by_frame.setdefault(fi, []).append(
            {
                "boxes": [float(v) for v in hit.box_xyxy[:4]],
                "role": str(role),
                "sharpness": float(hit.sharpness),
            }
        )
    frames_with_text = sorted(by_frame.keys())
    scanned = sorted({int(f) for f in (scanned_frames or frames_with_text)})
    return {
        "authority": "master_phase1_detect",
        "frame_count": int(frame_count),
        "frame_width": int(frame_w),
        "frame_height": int(frame_h),
        "n_scanned_frames": len(scanned),
        "scanned_frames": scanned,
        "n_frames_with_text": len(frames_with_text),
        "frames_with_text": frames_with_text,
        "n_hits": sum(len(v) for v in by_frame.values()),
        "by_frame": {str(fi): boxes for fi, boxes in sorted(by_frame.items())},
    }


def timeline_to_ocr_payload(
    timeline: Sequence[Mapping[str, Any]],
    *,
    fps: float,
    frame_count: int,
    frame_width: int,
    frame_height: int,
) -> dict[str, Any]:
    """
    Expand master timeline tracks into a dense ``frames[]`` OCR/render payload.

    Empty ``text`` → ``cover_only`` geometry (still wipe Chinese without VI).
    """
    rate = float(fps) if float(fps) > 1e-6 else 30.0
    w = max(1, int(frame_width))
    h = max(1, int(frame_height))
    by_frame: dict[int, list[dict[str, Any]]] = {}

    for raw in timeline:
        if not isinstance(raw, dict):
            continue
        start = int(raw.get("start_frame") or 0)
        end = int(raw.get("end_frame") or start)
        coords = list(raw.get("box_coords") or [])
        if len(coords) < 4:
            continue
        x0, y0, x1, y1 = (float(coords[i]) for i in range(4))
        nx = max(0.0, min(1.0, x0 / float(w)))
        ny = max(0.0, min(1.0, y0 / float(h)))
        nw = max(0.0, min(1.0 - nx, (x1 - x0) / float(w)))
        nh = max(0.0, min(1.0 - ny, (y1 - y0) / float(h)))
        text = str(raw.get("ocr_text") or raw.get("text") or "").strip()
        translate_ready = raw.get("translate_ready")
        localization_mode = str(raw.get("localization_mode") or "").strip()
        render_text_approved = str(
            raw.get("render_text_approved") or ""
        ).strip()
        # Explicit False → cover geometry only (do not send ZH to Caption AI).
        if translate_ready is False:
            text = ""
        box: dict[str, Any] = {
            "x": nx,
            "y": ny,
            "w": nw,
            "h": nh,
            "text": text,
            "confidence": 0.99 if text else 0.0,
            "text_id": str(raw.get("text_id") or ""),
        }
        if not text:
            box["cover_only"] = True
        if translate_ready is not None:
            box["translate_ready"] = bool(translate_ready)
        if localization_mode:
            box["localization_mode"] = localization_mode
        if render_text_approved:
            box["render_text_approved"] = render_text_approved
            box.pop("cover_only", None)
        for fi in range(max(0, start), min(int(frame_count), end + 1)):
            by_frame.setdefault(fi, []).append(dict(box))

    frames: list[dict[str, Any]] = []
    for fi in sorted(by_frame):
        frames.append(
            {
                "frame_index": fi,
                "time_ms": int(round(fi * 1000.0 / rate)),
                "frame_state": "hardsub",
                "boxes": by_frame[fi],
            }
        )
    return {
        "authority": "master_phase1",
        "frame_count": int(frame_count),
        "fps": rate,
        "frame_width": w,
        "frame_height": h,
        "frames": frames,
        "master_timeline": list(timeline),
    }


def _track_to_suspect_dict(track: MergedTrack) -> dict[str, Any]:
    return {
        "start_frame": int(track.start_frame),
        "end_frame": int(track.end_frame),
        "box_coords": [float(v) for v in track.box_coords],
        "hit_count": int(track.hit_count),
        "best_frame_index": int(track.best_frame_index),
    }


def write_boundary_review_artifacts(
    *,
    qa_dir: Path,
    timeline: Sequence[Mapping[str, Any]],
    frame_cache: Mapping[int, np.ndarray],
    source: Path,
    frame_count: int,
    frame_width: int,
    frame_height: int,
    panel_width: int = 480,
) -> int:
    """Write `start-1 | start | end | end+1` visual evidence per track."""
    boundary_dir = qa_dir / "boundaries"
    boundary_crop_dir = qa_dir / "boundary_crops"
    boundary_dir.mkdir(parents=True, exist_ok=True)
    boundary_crop_dir.mkdir(parents=True, exist_ok=True)
    for artifact_dir in (boundary_dir, boundary_crop_dir):
        for stale in artifact_dir.glob("*.jpg"):
            try:
                stale.unlink()
            except OSError:
                pass

    fw = max(1, int(frame_width))
    fh = max(1, int(frame_height))
    pw = max(160, int(panel_width))
    ph = max(90, int(round(pw * fh / float(fw))))
    crop_ph = max(120, int(round(ph * 0.70)))
    written = 0

    def _fit_panel(image: np.ndarray, *, width: int, height: int) -> np.ndarray:
        ih, iw = int(image.shape[0]), int(image.shape[1])
        scale = min(width / max(1.0, float(iw)), height / max(1.0, float(ih)))
        rw = max(1, int(round(iw * scale)))
        rh = max(1, int(round(ih * scale)))
        resized = cv2.resize(image, (rw, rh), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        ox = (width - rw) // 2
        oy = (height - rh) // 2
        canvas[oy : oy + rh, ox : ox + rw] = resized
        return canvas

    for entry in timeline:
        text_id = str(entry.get("text_id") or "")
        coords = list(entry.get("box_coords") or [])
        if not text_id or len(coords) < 4:
            continue
        start = int(entry.get("start_frame") or 0)
        end = int(entry.get("end_frame") or start)
        requests = [
            ("start-1", start - 1, False),
            ("start", start, True),
            ("end", end, True),
            ("end+1", end + 1, False),
        ]
        panels: list[np.ndarray] = []
        crop_panels: list[np.ndarray] = []
        x0, y0, x1, y1 = (int(round(float(v))) for v in coords[:4])
        box_w = max(1, x1 - x0)
        box_h = max(1, y1 - y0)
        crop_x0 = max(0, x0 - max(24, int(round(0.08 * box_w))))
        crop_x1 = min(fw, x1 + max(24, int(round(0.08 * box_w))))
        crop_y0 = max(0, y0 - max(20, int(round(1.10 * box_h))))
        crop_y1 = min(fh, y1 + max(20, int(round(1.10 * box_h))))
        for label, frame_index, inside in requests:
            available = 0 <= frame_index < int(frame_count)
            frame = (
                frame_cache.get(frame_index)
                if available
                else None
            )
            if frame is None and available and source.is_file():
                frame = _read_frame(source, frame_index)
            if frame is None:
                frame = np.zeros((fh, fw, 3), dtype=np.uint8)
                available = False
            else:
                frame = frame.copy()

            color = (0, 220, 0) if inside else (0, 0, 255)
            state = "IN" if inside else "OUT"
            suffix = "" if available else " unavailable"
            caption = f"{text_id} {label} f={frame_index} {state}{suffix}"

            zoom = frame[crop_y0:crop_y1, crop_x0:crop_x1].copy()
            if zoom.size == 0:
                zoom = np.zeros((max(1, crop_y1 - crop_y0), max(1, crop_x1 - crop_x0), 3), dtype=np.uint8)
            cv2.rectangle(
                zoom,
                (x0 - crop_x0, y0 - crop_y0),
                (x1 - crop_x0, y1 - crop_y0),
                color,
                2,
            )
            cv2.rectangle(zoom, (0, 0), (min(zoom.shape[1], 520), 26), (0, 0, 0), -1)
            cv2.putText(
                zoom,
                caption,
                (6, 19),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.50,
                color,
                1,
                cv2.LINE_AA,
            )
            crop_panels.append(_fit_panel(zoom, width=pw, height=crop_ph))

            cv2.rectangle(frame, (x0, y0), (x1, y1), color, 3)
            cv2.rectangle(frame, (0, 0), (min(fw, 720), 42), (0, 0, 0), -1)
            cv2.putText(
                frame,
                caption,
                (10, 29),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.72,
                color,
                2,
                cv2.LINE_AA,
            )
            panels.append(cv2.resize(frame, (pw, ph), interpolation=cv2.INTER_AREA))

        strip = cv2.hconcat(panels)
        if cv2.imwrite(
            str(boundary_dir / f"{text_id}.jpg"),
            strip,
            [int(cv2.IMWRITE_JPEG_QUALITY), 92],
        ):
            written += 1
        cv2.imwrite(
            str(boundary_crop_dir / f"{text_id}.jpg"),
            cv2.hconcat(crop_panels),
            [int(cv2.IMWRITE_JPEG_QUALITY), 94],
        )
    return written


def write_phase1_qa_artifacts(
    *,
    qa_dir: Path,
    timeline: Sequence[Mapping[str, Any]],
    dropped: Sequence[MergedTrack],
    frame_count: int,
    frame_width: int,
    frame_height: int,
    frames_dir: Path,
    frame_cache: Mapping[int, np.ndarray],
    source: Path,
    geometry_rejected: int,
    coarse_hits: int,
    phase_hits: int,
    dense_extra_frames: int,
    total_hits: int,
    finalize_audit: Mapping[str, Any] | None = None,
    text_coverage: Mapping[str, Any] | None = None,
    effective_step: int = STEP,
    effective_pad: int = PADDING,
    lightweight: bool = False,
) -> dict[str, Any]:
    """Write summary.json, suspects.json, before_after.json, and box overlays."""
    qa_dir.mkdir(parents=True, exist_ok=True)
    # Legacy QA: one overlay JPG per confirmed track keyframe (not every detect frame).
    overlays = qa_dir / "overlays"
    overlays.mkdir(parents=True, exist_ok=True)

    spans = [
        int(e.get("end_frame") or 0) - int(e.get("start_frame") or 0) + 1
        for e in timeline
    ]
    mid = 0
    for e in timeline:
        coords = list(e.get("box_coords") or [])
        if len(coords) >= 4 and float(coords[1]) < 0.50 * float(frame_height):
            mid += 1

    summary: dict[str, Any] = {
        "tracks_confirmed": len(timeline),
        "suspects_dropped": len(dropped),
        "geometry_rejected_hits": int(geometry_rejected),
        "coarse_hits": int(coarse_hits),
        "phase_probe_hits": int(phase_hits),
        "dense_extra_frames": int(dense_extra_frames),
        "total_hits": int(total_hits),
        "frame_count": int(frame_count),
        "frame_size": [int(frame_width), int(frame_height)],
        "mid_band_tracks_y0_lt_0.50H": mid,
        "span_hist": dict(sorted(Counter(spans).items())),
        "span_min_max": [min(spans), max(spans)] if spans else [0, 0],
        "crops_written": sum(1 for e in timeline if e.get("crop_path")),
        "config": {
            "STEP": int(effective_step),
            "PADDING": int(effective_pad),
            "ROI_Y0": ROI_Y0,
            "ROI_Y1": ROI_Y1,
            "MIN_HITS_TO_CONFIRM": MIN_HITS_TO_CONFIRM,
            "MERGE_GAP_FRAMES": MERGE_GAP_FRAMES,
            "MIN_MERGE_IOU": MIN_MERGE_IOU,
            "CENTROID_MERGE_PX": CENTROID_MERGE_PX,
            "POST_EVIDENCE_PAD": POST_EVIDENCE_PAD,
            "SPLIT_GAP_FRAMES": SPLIT_GAP_FRAMES,
            "SPLIT_CENTROID_PX": SPLIT_CENTROID_PX,
        },
    }
    if finalize_audit:
        summary["finalize"] = {
            "before_count": finalize_audit.get("before_count"),
            "after_count": finalize_audit.get("after_count"),
            "purged_chrome": finalize_audit.get("purged_chrome"),
            "re_dropped_after_split": finalize_audit.get("re_dropped_after_split"),
            "shrunk_n": len(list(finalize_audit.get("shrunk") or [])),
            "split_events": finalize_audit.get("split_events"),
            "boundary_refinement": {
                key: (finalize_audit.get("boundary_refinement") or {}).get(key)
                for key in ("attempted", "applied", "changed")
            },
            "content_segmentation": {
                key: (finalize_audit.get("content_segmentation") or {}).get(key)
                for key in (
                    "before_count",
                    "after_count",
                    "split_tracks",
                    "trimmed_tracks",
                    "segments_created",
                )
            },
            "content_reconciliation": {
                key: (finalize_audit.get("content_reconciliation") or {}).get(key)
                for key in ("before_count", "after_count", "merged_tracks")
            },
            "content_boundary_expansion": {
                key: (finalize_audit.get("content_boundary_expansion") or {}).get(key)
                for key in ("expanded_tracks",)
            },
            "final_temporal_coverage": {
                key: (finalize_audit.get("final_temporal_coverage") or {}).get(key)
                for key in (
                    "sparse_clusters_trimmed",
                    "coverage_edges_extended",
                    "coverage_frames_added",
                )
            },
            "residual_hardsub_recovery": {
                key: (
                    finalize_audit.get("residual_hardsub_recovery") or {}
                ).get(key)
                for key in (
                    "candidate_hits",
                    "covered_hits",
                    "recovered_track_count",
                    "explained_shadow_frames",
                    "unresolved_spans",
                )
            },
            "post_refinement_sparse_compact_filter": {
                key: (
                    finalize_audit.get("post_refinement_sparse_compact_filter")
                    or {}
                ).get(key)
                for key in (
                    "candidate_count",
                    "dropped_tracks",
                    "before_count",
                    "after_count",
                )
            },
            "nested_temporal_ui_fragment_guard": {
                key: (
                    finalize_audit.get("nested_temporal_ui_fragment_guard")
                    or {}
                ).get(key)
                for key in (
                    "before_count",
                    "after_count",
                    "dropped_tracks",
                )
            },
        }
    (qa_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (qa_dir / "suspects.json").write_text(
        json.dumps(
            [_track_to_suspect_dict(t) for t in dropped],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # Recall-first audit: a rejected candidate is retained as explicit
    # ``uncertain`` evidence instead of disappearing behind min-hit gates.
    uncertain_candidates: list[dict[str, Any]] = []
    for track in dropped:
        row = _track_to_suspect_dict(track)
        row["status"] = "uncertain"
        row["reason"] = "single_hit_unconfirmed"
        row["boundary_evidence"] = track_boundary_evidence(
            track, frame_w=frame_width, frame_h=frame_height
        )
        uncertain_candidates.append(row)
    (qa_dir / "uncertain_candidates.json").write_text(
        json.dumps(uncertain_candidates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    timeline_evidence = [
        {
            "text_id": str(entry.get("text_id") or ""),
            "start_frame": int(entry.get("start_frame") or 0),
            "end_frame": int(entry.get("end_frame") or 0),
            "box_coords": list(entry.get("box_coords") or []),
            "boundary_evidence": dict(entry.get("boundary_evidence") or {}),
        }
        for entry in timeline
    ]
    review_tracks = [
        row
        for row in timeline_evidence
        if (row.get("boundary_evidence") or {}).get("status") == "uncertain"
    ]
    quality_report = {
        "authority": "master_phase1_quality_v1",
        "tracks": len(timeline),
        "confirmed_tracks": len(timeline) - len(review_tracks),
        "uncertain_tracks": len(review_tracks),
        "uncertain_candidates": len(uncertain_candidates),
        "review_queue": review_tracks,
        "track_evidence": timeline_evidence,
    }
    (qa_dir / "quality_report.json").write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary["quality"] = {
        "confirmed_tracks": quality_report["confirmed_tracks"],
        "uncertain_tracks": quality_report["uncertain_tracks"],
        "uncertain_candidates": quality_report["uncertain_candidates"],
    }
    if finalize_audit is not None:
        (qa_dir / "before_after.json").write_text(
            json.dumps(dict(finalize_audit), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Track-centric overlays (1 JPG per confirmed track keyframe).
    by_active: dict[int, list[Mapping[str, Any]]] = {}
    for entry in timeline:
        start = int(entry.get("start_frame") or 0)
        end = int(entry.get("end_frame") or start)
        for fi in range(start, end + 1):
            by_active.setdefault(fi, []).append(entry)

    # Drop stale coverage-style tXXXXX.jpg from older runs.
    for stale in overlays.glob("*.jpg"):
        try:
            stale.unlink()
        except OSError:
            pass

    overlay_n = 0
    for entry in ([] if lightweight else timeline):
        text_id = str(entry.get("text_id") or "")
        coords = list(entry.get("box_coords") or [])
        if len(coords) < 4 or not text_id:
            continue
        rel = str(entry.get("best_keyframe_path") or "")
        name = Path(rel).name if rel else f"{text_id}.jpg"
        src_img = frames_dir / name
        frame = None
        if src_img.is_file():
            frame = cv2.imread(str(src_img))
        if frame is None:
            fi = int(entry.get("best_frame_index") or entry.get("start_frame") or 0)
            frame = frame_cache.get(fi)
            if frame is None:
                frame = _read_frame(source, fi)
        if frame is None:
            continue
        vis = frame.copy()
        focus_fi = int(entry.get("best_frame_index") or entry.get("start_frame") or 0)
        peers = by_active.get(focus_fi) or [entry]
        for peer in peers:
            pcoords = list(peer.get("box_coords") or [])
            if len(pcoords) < 4:
                continue
            px0, py0, px1, py1 = (int(round(float(v))) for v in pcoords[:4])
            is_focus = str(peer.get("text_id") or "") == text_id
            color = (0, 255, 0) if is_focus else (0, 200, 255)
            thickness = 3 if is_focus else 2
            cv2.rectangle(vis, (px0, py0), (px1, py1), color, thickness)
            plabel = f"{peer.get('text_id')} n={peer.get('hit_count', '?')}"
            cv2.putText(
                vis,
                plabel,
                (px0, max(20, py0 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )
        if cv2.imwrite(
            str(overlays / name),
            vis,
            [int(cv2.IMWRITE_JPEG_QUALITY), 92],
        ):
            overlay_n += 1

    summary["overlays"] = int(overlay_n)
    boundary_timeline = [
        entry
        for entry in timeline
        if str(
            dict(entry.get("visual_provenance") or {}).get("classification")
            or "UNCERTAIN"
        )
        not in {"SOURCE_INTRINSIC", "SOURCE_INTRINSIC_PANEL", "PLATFORM_UI"}
    ]
    boundary_n = 0
    if not lightweight:
        boundary_n = write_boundary_review_artifacts(
            qa_dir=qa_dir,
            timeline=boundary_timeline,
            frame_cache=frame_cache,
            source=source,
            frame_count=frame_count,
            frame_width=frame_width,
            frame_height=frame_height,
        )
    summary["boundary_overlays"] = boundary_n
    summary["boundary_crop_overlays"] = boundary_n
    summary["boundary_source_tracks_skipped"] = len(timeline) - len(
        boundary_timeline
    )
    summary["n_frames_with_text"] = int(
        (text_coverage or {}).get("n_frames_with_text") or 0
    )
    if finalize_audit and "local_text_gate" in finalize_audit:
        summary["local_text_gate"] = finalize_audit.get("local_text_gate")
    if finalize_audit and "content_segmentation" in finalize_audit:
        summary["content_segmentation"] = finalize_audit.get(
            "content_segmentation"
        )
    if finalize_audit and "content_reconciliation" in finalize_audit:
        summary["content_reconciliation"] = finalize_audit.get(
            "content_reconciliation"
        )
    if finalize_audit and "content_boundary_expansion" in finalize_audit:
        summary["content_boundary_expansion"] = finalize_audit.get(
            "content_boundary_expansion"
        )
    (qa_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def _write_box_crop(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
    dest: Path,
) -> bool:
    h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    x0 = max(0, min(w - 1, int(round(float(xyxy[0])))))
    y0 = max(0, min(h - 1, int(round(float(xyxy[1])))))
    x1 = max(x0 + 1, min(w, int(round(float(xyxy[2])))))
    y1 = max(y0 + 1, min(h, int(round(float(xyxy[3])))))
    crop = frame_bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return False
    return bool(
        cv2.imwrite(str(dest), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    )


class MasterPhase1Extractor:
    """Fixed-step ROI DBNet scan with confirm / IoU merge / crop-sharp keyframes."""

    def __init__(
        self,
        detector: LocalTextDetector | None = None,
        *,
        step: int = STEP,
        pad: int | None = None,
        centroid_merge_px: float = CENTROID_MERGE_PX,
        min_hits: int = MIN_HITS_TO_CONFIRM,
        on_progress: Callable[[str, int, int], None] | None = None,
        analysis_engine: str = "v58_candidate",
        candidate_window_payload: Mapping[str, Any] | None = None,
    ) -> None:
        self._detector = detector
        self._step = max(1, int(step))
        # PADDING == STEP unless caller overrides pad explicitly.
        self._pad = max(0, int(pad) if pad is not None else self._step)
        self._centroid_merge_px = float(centroid_merge_px)
        self._min_hits = max(1, int(min_hits))
        self._on_progress = on_progress
        self._analysis_engine = str(analysis_engine or "v58_candidate")
        self._event_scan = self._analysis_engine == EVENT_SCAN_ENGINE_VERSION
        self._candidate_window_payload = dict(candidate_window_payload or {})

    def _ensure_detector(self) -> LocalTextDetector:
        if self._detector is None:
            self._detector = LocalTextDetector(ensure_dbnet_onnx(None))
        return self._detector

    def _detect_frame_hits(
        self,
        bgr: np.ndarray,
        *,
        frame_index: int,
        detector: LocalTextDetector,
        frame_w: int,
        frame_h: int,
        long_edge: int = PHASE1_DET_LONG_EDGE,
        bin_thresh: float = PHASE1_DET_BIN_THRESH,
    ) -> tuple[list[DetectionHit], int]:
        """
        Dual-prep DBNet (CLAHE + stroke) → plausible boxes → NMS union.

        Stroke path targets edited-in CJK burn-in; CLAHE keeps general recall.
        """
        raw: list[DetectionHit] = []
        rejected = 0
        detect_preps = roi_phase1_detect_preps(bgr)
        # Completeness-first event mode intentionally keeps both CLAHE and
        # stroke preparations. Coloured/low-contrast captions can be invisible
        # to the stroke-only path; provenance runs after discovery and protects
        # source panels without sacrificing detector recall.
        for _name, roi_bgr, y_offset in detect_preps:
            roi_h, roi_w = int(roi_bgr.shape[0]), int(roi_bgr.shape[1])
            boxes = detector.detect(
                roi_bgr,
                long_edge=int(long_edge),
                bin_thresh=float(bin_thresh),
                rematch_after_expand=True,
                expand_pad_w_frac=PHASE1_EXPAND_PAD_W_FRAC,
                expand_pad_h_top_frac=PHASE1_EXPAND_PAD_H_TOP_FRAC,
                expand_pad_h_bottom_frac=PHASE1_EXPAND_PAD_H_BOTTOM_FRAC,
            )
            for box in boxes:
                xyxy = _norm_box_to_full_xyxy(
                    box, roi_w=roi_w, roi_h=roi_h, y_offset=y_offset
                )
                if not is_plausible_text_box(xyxy, frame_w=frame_w, frame_h=frame_h):
                    rejected += 1
                    continue
                sharp = crop_box_sharpness(bgr, xyxy)
                raw.append(
                    DetectionHit(
                        frame_index=int(frame_index),
                        box_xyxy=xyxy,
                        sharpness=sharp,
                    )
                )
        return merge_frame_hit_boxes(raw), rejected

    def _detect_frame_residual_profile_hits(
        self,
        bgr: np.ndarray,
        *,
        frame_index: int,
        detector: LocalTextDetector,
        frame_w: int,
        frame_h: int,
    ) -> tuple[list[DetectionHit], int]:
        """Raw-frame alternate profile for stylized intro/endcard recall."""
        raw: list[DetectionHit] = []
        rejected = 0
        boxes = detector.detect(
            bgr,
            long_edge=PHASE1_RESIDUAL_DET_LONG_EDGE,
            bin_thresh=PHASE1_RESIDUAL_DET_BIN_THRESH,
            rematch_after_expand=True,
        )
        for box in boxes:
            xyxy = _norm_box_to_full_xyxy(
                box,
                roi_w=frame_w,
                roi_h=frame_h,
                y_offset=0,
            )
            if not is_plausible_text_box(
                xyxy, frame_w=frame_w, frame_h=frame_h
            ):
                rejected += 1
                continue
            raw.append(
                DetectionHit(
                    frame_index=int(frame_index),
                    box_xyxy=xyxy,
                    sharpness=crop_box_sharpness(bgr, xyxy),
                )
            )
        return merge_frame_hit_boxes(raw), rejected

    def extract(
        self,
        video_path: str | Path,
        out_dir: str | Path,
    ) -> MasterPhase1Result:
        source = Path(video_path)
        extract_started = time.perf_counter()
        dest = Path(out_dir)
        frames_dir = dest / "frames"
        qa_dir = dest / "qa"
        frames_dir.mkdir(parents=True, exist_ok=True)
        dest.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(str(source))
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video: {source}")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        source_width = int(width)
        source_height = int(height)
        analysis_scale = 1.0
        if self._event_scan and max(width, height) > PHASE1_EVENT_ANALYSIS_LONG_EDGE:
            analysis_scale = PHASE1_EVENT_ANALYSIS_LONG_EDGE / float(
                max(width, height)
            )
            width = max(2, int(round(width * analysis_scale)))
            height = max(2, int(round(height * analysis_scale)))

        scan_reader: Any = cap
        analysis_decode_backend = "opencv_source"
        event_two_pass_decode = False
        all_frame_proxy_size: list[int] | None = None
        proxy_size = (
            phase1_event_proxy_size(source_width, source_height)
            if self._event_scan
            else None
        )
        if proxy_size is not None:
            probe_width, probe_height = proxy_size
            try:
                scan_reader = _FfmpegProxyFrameReader(
                    source,
                    width=probe_width,
                    height=probe_height,
                )
            except (FileNotFoundError, OSError) as exc:
                cap.release()
                raise RuntimeError(
                    "Official Analyze OCR requires the FFmpeg all-frame proxy; "
                    f"proxy initialization failed: {exc}"
                ) from exc
            else:
                cap.release()
                event_two_pass_decode = True
                all_frame_proxy_size = [probe_width, probe_height]
                analysis_decode_backend = "ffmpeg_two_pass_selected_rawvideo"

        def _analysis_frame(frame_bgr: np.ndarray) -> np.ndarray:
            if (
                not self._event_scan
                or analysis_scale >= 0.999
                or (
                    int(frame_bgr.shape[1]) == int(width)
                    and int(frame_bgr.shape[0]) == int(height)
                )
            ):
                return frame_bgr
            return cv2.resize(
                frame_bgr,
                (int(width), int(height)),
                interpolation=cv2.INTER_AREA,
            )

        def _box_to_source(xyxy: Sequence[float]) -> list[float]:
            if analysis_scale >= 0.999:
                return [float(value) for value in xyxy[:4]]
            sx = float(source_width) / max(1.0, float(width))
            sy = float(source_height) / max(1.0, float(height))
            return [
                float(xyxy[0]) * sx,
                float(xyxy[1]) * sy,
                float(xyxy[2]) * sx,
                float(xyxy[3]) * sy,
            ]

        def _hits_to_source(rows: Sequence[DetectionHit]) -> list[DetectionHit]:
            if analysis_scale >= 0.999:
                return list(rows)
            return [
                DetectionHit(
                    frame_index=int(row.frame_index),
                    box_xyxy=tuple(_box_to_source(row.box_xyxy)),
                    sharpness=float(row.sharpness),
                )
                for row in rows
            ]
        detector = self._ensure_detector()

        audio_windows: list[CandidateWindow] = []
        if self._event_scan:
            for raw in list(self._candidate_window_payload.get("windows") or []):
                if not isinstance(raw, Mapping):
                    continue
                sources = tuple(str(value) for value in list(raw.get("sources") or []))
                if "AUDIO_GUIDED" not in sources:
                    continue
                start_ms = int(raw.get("start_ms") or 0)
                end_ms = int(raw.get("end_ms") or start_ms)
                if end_ms <= start_ms:
                    continue
                audio_windows.append(
                    CandidateWindow(
                        start_ms=start_ms,
                        end_ms=end_ms,
                        sources=sources,
                        confidence=float(raw.get("confidence") or 0.0),
                    )
                )
        duration_ms = max(
            1,
            int(round(max(1, frame_count) * 1000.0 / max(1.0, fps))),
        )
        event_scheduler = (
            EventFrameScheduler(
                fps=fps,
                frame_count=max(1, frame_count),
                duration_ms=duration_ms,
                audio_windows=audio_windows,
            )
            if self._event_scan
            else None
        )

        coarse_hits: list[DetectionHit] = []
        phase_hits: list[DetectionHit] = []
        residual_risk_hits: list[DetectionHit] = []
        checkpoint_path = dest / ".phase1_scan_checkpoint.json"
        source_stat = source.stat()
        resume_frame = 0

        def _hit_payload(hit: DetectionHit) -> dict[str, Any]:
            return {
                "frame_index": int(hit.frame_index),
                "box_xyxy": [float(value) for value in hit.box_xyxy],
                "sharpness": float(hit.sharpness),
            }

        def _load_hits(rows: Any) -> list[DetectionHit]:
            restored: list[DetectionHit] = []
            for row in list(rows or []):
                if not isinstance(row, Mapping):
                    continue
                box = list(row.get("box_xyxy") or [])
                if len(box) != 4:
                    continue
                restored.append(
                    DetectionHit(
                        frame_index=int(row.get("frame_index") or 0),
                        box_xyxy=tuple(float(value) for value in box),
                        sharpness=float(row.get("sharpness") or 0.0),
                    )
                )
            return restored

        if checkpoint_path.is_file():
            try:
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                if (
                    checkpoint.get("schema_version") == "phase1_scan_checkpoint_v2"
                    and str(checkpoint.get("scan_policy_version") or "")
                    == (
                        EVENT_SCAN_POLICY_VERSION
                        if self._event_scan
                        else TEMPORAL_SCAN_POLICY_VERSION
                    )
                    and str(checkpoint.get("analysis_engine") or "v58_candidate")
                    == self._analysis_engine
                    and int(checkpoint.get("source_size") or -1) == int(source_stat.st_size)
                    and int(checkpoint.get("source_mtime_ns") or -1) == int(source_stat.st_mtime_ns)
                    and int(checkpoint.get("frame_count") or -1) == int(frame_count)
                    and int(checkpoint.get("step") or -1) == int(self._step)
                ):
                    resume_frame = max(0, min(frame_count, int(checkpoint.get("next_frame") or 0)))
                    coarse_hits.extend(_load_hits(checkpoint.get("coarse_hits")))
                    phase_hits.extend(_load_hits(checkpoint.get("phase_hits")))
                    residual_risk_hits.extend(_load_hits(checkpoint.get("residual_risk_hits")))
                    logger.info(
                        "master_phase1_resume frame=%s/%s hits=%s",
                        resume_frame,
                        frame_count,
                        len(coarse_hits) + len(phase_hits) + len(residual_risk_hits),
                    )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                resume_frame = 0
                coarse_hits.clear()
                phase_hits.clear()
                residual_risk_hits.clear()

        def _write_checkpoint(next_frame: int) -> None:
            payload = {
                "schema_version": "phase1_scan_checkpoint_v2",
                "scan_policy_version": (
                    EVENT_SCAN_POLICY_VERSION
                    if self._event_scan
                    else TEMPORAL_SCAN_POLICY_VERSION
                ),
                "analysis_engine": self._analysis_engine,
                "source_size": int(source_stat.st_size),
                "source_mtime_ns": int(source_stat.st_mtime_ns),
                "frame_count": int(frame_count),
                "step": int(self._step),
                "pad": int(self._pad),
                "next_frame": int(next_frame),
                "coarse_hits": [_hit_payload(hit) for hit in coarse_hits],
                "phase_hits": [_hit_payload(hit) for hit in phase_hits],
                "residual_risk_hits": [_hit_payload(hit) for hit in residual_risk_hits],
            }
            temporary = checkpoint_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temporary.replace(checkpoint_path)
        frame_cache = _DiskBackedFrameCache()
        scanned_frames: set[int] = set()
        heavy_probe_gap_frames = temporal_heavy_probe_gap_frames(fps)
        temporal_probe = TemporalVisualProbe(max_gap_frames=heavy_probe_gap_frames)
        temporal_probe_reasons: Counter[str] = Counter()
        temporal_transition_frames: set[int] = set()
        lightweight_scanned_frames = 0
        geometry_rejected = 0
        phase_stride = self._step * 2
        phase_offset = self._step // 2
        residual_risk_frames = phase1_residual_risk_frame_indices(
            frame_count=frame_count,
            fps=fps,
        )
        residual_profile_boxes = 0
        progress_interval = max(1, min(15, frame_count // 100 if frame_count > 0 else 15))
        checkpoint_interval = max(progress_interval, min(300, max(30, frame_count // 20)))

        def _report(phase: str, current: int, total: int) -> None:
            if self._on_progress is not None:
                self._on_progress(phase, max(0, int(current)), max(1, int(total)))

        def _is_phase_probe(fi: int) -> bool:
            if self._step < 2:
                return False
            return fi >= phase_offset and (fi - phase_offset) % phase_stride == 0

        def _detect_selected_bgr(
            bgr: np.ndarray,
            *,
            frame_index: int,
            is_coarse: bool,
            is_phase: bool,
            is_residual_risk: bool,
        ) -> None:
            nonlocal geometry_rejected, residual_profile_boxes
            analysis_bgr = _analysis_frame(bgr)
            scanned_frames.add(frame_index)
            frame_cache[frame_index] = analysis_bgr
            if frame_index < resume_frame:
                return
            found, rejected = self._detect_frame_hits(
                analysis_bgr,
                frame_index=frame_index,
                detector=detector,
                frame_w=width,
                frame_h=height,
            )
            geometry_rejected += rejected
            if is_residual_risk:
                residual_found, residual_rejected = (
                    self._detect_frame_residual_profile_hits(
                        analysis_bgr,
                        frame_index=frame_index,
                        detector=detector,
                        frame_w=width,
                        frame_h=height,
                    )
                )
                geometry_rejected += residual_rejected
                residual_profile_boxes += len(residual_found)
                found = merge_primary_and_residual_frame_hits(found, residual_found)
            if is_coarse:
                coarse_hits.extend(found)
            elif is_phase:
                phase_hits.extend(found)
            else:
                residual_risk_hits.extend(found)

        def _event_selected_frames(
            frame_indices: Sequence[int],
        ):
            ordered = sorted({int(value) for value in frame_indices})
            for chunk_start in range(0, len(ordered), 80):
                selected_chunk = ordered[chunk_start : chunk_start + 80]
                selected_reader = _FfmpegProxyFrameReader(
                    source,
                    width=width,
                    height=height,
                    selected_frame_indices=selected_chunk,
                )
                try:
                    for selected_index in selected_chunk:
                        ok, selected_bgr = selected_reader.read()
                        if not ok or selected_bgr is None:
                            raise RuntimeError(
                                "FFmpeg selected-frame decode ended before all event frames"
                            )
                        yield selected_index, selected_bgr
                finally:
                    selected_reader.release()

        # Pass 1: schedule with a tiny all-frame proxy, then decode only selected
        # frames at detector resolution. Legacy/V58 keeps the original one-pass
        # OpenCV behavior.
        try:
            frame_index = 0
            scan_phase = "phase1_event_scan" if self._event_scan else "phase1_scan"
            _report(scan_phase, 0, frame_count or 1)
            if event_scheduler is not None and event_two_pass_decode:
                event_selected: list[tuple[int, bool]] = []
                while True:
                    ok, bgr = scan_reader.read()
                    if not ok or bgr is None:
                        break
                    is_coarse, event_reasons = event_scheduler.inspect(
                        bgr, frame_index=frame_index
                    )
                    lightweight_scanned_frames += 1
                    for reason in event_reasons or ("stable",):
                        temporal_probe_reasons[reason] += 1
                    if any(
                        reason in {
                            "first_frame",
                            "scene_change",
                            "local_textness_change",
                            "completeness_text_candidate",
                        }
                        for reason in event_reasons
                    ):
                        temporal_transition_frames.add(frame_index)
                    if is_coarse:
                        event_selected.append(
                            (
                                frame_index,
                                frame_index in residual_risk_frames
                                or "hard_textness_boundary" in event_reasons,
                            )
                        )
                    frame_index += 1
                    if frame_index % progress_interval == 0:
                        _report(scan_phase, frame_index, frame_count or frame_index)
                scan_reader.release()

                _report("phase1_event_detect", 0, len(event_selected) or 1)
                selected_done = 0
                # FFmpeg's expression evaluator becomes unstable with a very
                # large sum of eq(n, frame) terms on Windows. Bounded chunks
                # keep command lines/parser memory small while still avoiding
                # full-resolution BGR transfer for unselected frames.
                residual_by_frame = dict(event_selected)
                for selected_index, selected_bgr in _event_selected_frames(
                    list(residual_by_frame)
                ):
                    _detect_selected_bgr(
                        selected_bgr,
                        frame_index=selected_index,
                        is_coarse=True,
                        is_phase=False,
                        is_residual_risk=bool(residual_by_frame[selected_index]),
                    )
                    selected_done += 1
                    if selected_done % progress_interval == 0:
                        _report(
                            "phase1_event_detect",
                            selected_done,
                            len(event_selected),
                        )
                    if selected_done % checkpoint_interval == 0:
                        _write_checkpoint(selected_index + 1)
                _report(
                    "phase1_event_detect",
                    selected_done,
                    len(event_selected) or 1,
                )
            else:
                while True:
                    ok, bgr = scan_reader.read()
                    if not ok or bgr is None:
                        break
                    if source_width <= 0 or source_height <= 0:
                        source_height, source_width = int(bgr.shape[0]), int(bgr.shape[1])
                        height, width = source_height, source_width
                    if event_scheduler is not None:
                        is_coarse, event_reasons = event_scheduler.inspect(
                            bgr, frame_index=frame_index
                        )
                        lightweight_scanned_frames += 1
                        for reason in event_reasons or ("stable",):
                            temporal_probe_reasons[reason] += 1
                        if any(
                            reason in {
                                "first_frame",
                                "scene_change",
                                "local_textness_change",
                                "completeness_text_candidate",
                            }
                            for reason in event_reasons
                        ):
                            temporal_transition_frames.add(frame_index)
                    elif self._step == 1:
                        is_coarse, probe_reason = temporal_probe.inspect(
                            bgr, frame_index=frame_index
                        )
                        lightweight_scanned_frames += 1
                        temporal_probe_reasons[probe_reason] += 1
                        if probe_reason in {"first_frame", "luma_transition", "edge_transition"}:
                            temporal_transition_frames.add(frame_index)
                    else:
                        is_coarse = frame_index % self._step == 0
                    is_phase = (
                        event_scheduler is None
                        and (not is_coarse)
                        and _is_phase_probe(frame_index)
                    )
                    is_residual_risk = (
                        frame_index in residual_risk_frames
                        or (
                            event_scheduler is not None
                            and "hard_textness_boundary" in event_reasons
                        )
                    ) and (is_coarse if event_scheduler is not None else True)
                    if is_coarse or is_phase or is_residual_risk:
                        _detect_selected_bgr(
                            bgr,
                            frame_index=frame_index,
                            is_coarse=is_coarse,
                            is_phase=is_phase,
                            is_residual_risk=is_residual_risk,
                        )
                    frame_index += 1
                    if frame_index % progress_interval == 0:
                        _report(scan_phase, frame_index, frame_count or frame_index)
                    if frame_index % checkpoint_interval == 0:
                        _write_checkpoint(frame_index)
        finally:
            scan_reader.release()

        if frame_count <= 0:
            frame_count = frame_index
        if frame_count <= 0:
            raise RuntimeError(f"No frames read from {source}")
        _report(scan_phase, frame_count, frame_count)
        _write_checkpoint(frame_count)

        event_candidate_payload: dict[str, Any] = {}
        if event_scheduler is not None:
            event_candidate_payload = event_scheduler.payload(
                scanned_frames=len(scanned_frames)
            )
            event_candidate_payload["audio_seed_sha256"] = str(
                self._candidate_window_payload.get("seed_sha256") or ""
            )
            event_candidate_payload["source_transcript_sha256"] = str(
                self._candidate_window_payload.get("source_transcript_sha256") or ""
            )
            event_candidate_payload["candidate_seed_mode"] = str(
                self._candidate_window_payload.get("mode") or "VISUAL_ONLY"
            )
            event_candidate_payload["candidate_seed_segments_count"] = int(
                self._candidate_window_payload.get("segments_count") or 0
            )
            event_candidate_payload["candidate_seed_audio_analysis_version"] = str(
                self._candidate_window_payload.get("audio_analysis_version") or ""
            )
            event_candidate_payload["candidate_seed_audio_analysis_fingerprint"] = str(
                self._candidate_window_payload.get("audio_analysis_fingerprint") or ""
            )
            event_candidate_payload["candidate_seed_vad_has_speech"] = (
                self._candidate_window_payload.get("vad_has_speech")
            )
            (dest / f"{CANDIDATE_WINDOW_SCHEMA_VERSION}.json").write_text(
                json.dumps(event_candidate_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        seed_hits = [*coarse_hits, *phase_hits, *residual_risk_hits]

        # Pass 2: verify provisional interval boundaries.  Opening N+/-STEP
        # around every persistent hit recreates a full-duration scan.
        dense_candidates = interval_dense_rescan_frame_indices(
            seed_hits,
            step=self._step,
            frame_count=frame_count,
            frame_w=width,
            frame_h=height,
            max_centroid_px=self._centroid_merge_px,
            max_probe_gap_frames=heavy_probe_gap_frames,
            transition_frames=sorted(temporal_transition_frames),
        )
        dense_needed, dense_rescan_budget = bound_dense_rescan_frame_indices(
            dense_candidates,
            already_scanned=sorted(scanned_frames),
            frame_count=frame_count,
            max_heavy_ratio=(
                event_dense_rescan_max_ratio(fps)
                if self._event_scan
                else PHASE1_DENSE_RESCAN_MAX_HEAVY_RATIO
            ),
        )
        hits: list[DetectionHit] = list(seed_hits)
        if dense_needed:
            want = set(dense_needed)
            dense_done = 0
            _report("phase1_dense_rescan", 0, len(dense_needed))
            if self._event_scan and event_two_pass_decode:
                for fi, analysis_bgr in _event_selected_frames(dense_needed):
                    scanned_frames.add(fi)
                    frame_cache[fi] = analysis_bgr
                    found, rejected = self._detect_frame_hits(
                        analysis_bgr,
                        frame_index=fi,
                        detector=detector,
                        frame_w=width,
                        frame_h=height,
                    )
                    geometry_rejected += rejected
                    hits.extend(found)
                    want.discard(fi)
                    dense_done += 1
                    if dense_done % progress_interval == 0:
                        _report("phase1_dense_rescan", dense_done, len(dense_needed))
            else:
                cap2 = cv2.VideoCapture(str(source))
                if not cap2.isOpened():
                    raise RuntimeError(f"Cannot reopen video for dense rescan: {source}")
                try:
                    fi = 0
                    while want:
                        ok, bgr = cap2.read()
                        if not ok or bgr is None:
                            break
                        if fi in want:
                            analysis_bgr = _analysis_frame(bgr)
                            scanned_frames.add(fi)
                            frame_cache[fi] = analysis_bgr
                            found, rejected = self._detect_frame_hits(
                                analysis_bgr,
                                frame_index=fi,
                                detector=detector,
                                frame_w=width,
                                frame_h=height,
                            )
                            geometry_rejected += rejected
                            hits.extend(found)
                            want.discard(fi)
                            dense_done += 1
                            if dense_done % progress_interval == 0:
                                _report("phase1_dense_rescan", dense_done, len(dense_needed))
                        fi += 1
                finally:
                    cap2.release()
            _report("phase1_dense_rescan", len(dense_needed) - len(want), len(dense_needed))

        # Pass 3: bounded high-resolution recovery on dense UI/app anchors.
        # This targets small phone-screen labels without paying 1920-long-edge
        # DBNet cost across the full video.
        small_text_anchors = dense_ui_recovery_anchor_frame_indices(
            hits,
            frame_count=frame_count,
            fps=fps,
            transition_frames=sorted(temporal_transition_frames),
        )
        small_text_candidates: set[int] = set()
        for anchor in small_text_anchors:
            start, end = apply_temporal_pad(anchor, frame_count=frame_count, pad=1)
            small_text_candidates.update(range(start, end + 1))
        small_text_new_frames, small_text_budget = bound_dense_rescan_frame_indices(
            sorted(small_text_candidates),
            already_scanned=sorted(scanned_frames),
            frame_count=frame_count,
            max_heavy_ratio=(
                event_dense_rescan_max_ratio(fps)
                if self._event_scan
                else PHASE1_DENSE_RESCAN_MAX_HEAVY_RATIO
            ),
        )
        small_text_frames = sorted(
            set(small_text_new_frames)
            | {int(value) for value in small_text_candidates if int(value) in scanned_frames}
        )
        small_text_frame_limit = max(
            12,
            min(
                72,
                int(
                    np.ceil(
                        max(1.0, duration_ms / 60_000.0)
                        * PHASE1_SMALL_TEXT_MAX_ANCHORS_PER_MINUTE
                    )
                ),
            ),
        )
        if self._event_scan and len(small_text_frames) > small_text_frame_limit:
            positions = np.linspace(
                0,
                len(small_text_frames) - 1,
                num=small_text_frame_limit,
                dtype=np.int64,
            )
            small_text_frames = sorted(
                {small_text_frames[int(position)] for position in positions}
            )
        small_text_hits: list[DetectionHit] = []
        small_text_geometry_rejected = 0
        if small_text_frames:
            want = set(small_text_frames)
            done = 0
            _report("phase1_small_text_recovery", 0, len(want))

            def _process_small_text_frame(fi: int, analysis_bgr: np.ndarray) -> None:
                nonlocal small_text_geometry_rejected, done
                scanned_frames.add(fi)
                frame_cache[fi] = analysis_bgr
                found, rejected = self._detect_frame_hits(
                    analysis_bgr,
                    frame_index=fi,
                    detector=detector,
                    frame_w=width,
                    frame_h=height,
                    long_edge=(
                        max(width, height)
                        if self._event_scan
                        else PHASE1_SMALL_TEXT_DET_LONG_EDGE
                    ),
                    bin_thresh=PHASE1_SMALL_TEXT_DET_BIN_THRESH,
                )
                small_text_hits.extend(found)
                small_text_geometry_rejected += rejected
                want.discard(fi)
                done += 1
                if done % progress_interval == 0:
                    _report("phase1_small_text_recovery", done, len(small_text_frames))

            if self._event_scan and event_two_pass_decode:
                for fi, analysis_bgr in _event_selected_frames(small_text_frames):
                    _process_small_text_frame(fi, analysis_bgr)
            else:
                cap3 = cv2.VideoCapture(str(source))
                if not cap3.isOpened():
                    raise RuntimeError(f"Cannot reopen video for small-text recovery: {source}")
                try:
                    fi = 0
                    while want:
                        ok, bgr = cap3.read()
                        if not ok or bgr is None:
                            break
                        if fi in want:
                            _process_small_text_frame(fi, _analysis_frame(bgr))
                        fi += 1
                finally:
                    cap3.release()
            _report(
                "phase1_small_text_recovery",
                len(small_text_frames) - len(want),
                len(small_text_frames),
            )

        if small_text_hits:
            hits_by_frame: dict[int, list[DetectionHit]] = defaultdict(list)
            for hit in [*hits, *small_text_hits]:
                hits_by_frame[int(hit.frame_index)].append(hit)
            hits = [
                hit
                for frame_index in sorted(hits_by_frame)
                for hit in merge_frame_hit_boxes(hits_by_frame[frame_index])
            ]
        geometry_rejected += small_text_geometry_rejected

        postprocess_total = 15
        postprocess_stage = 0
        postprocess_last_tick = time.perf_counter()

        def _postprocess_progress(stage: str) -> None:
            nonlocal postprocess_stage, postprocess_last_tick
            now = time.perf_counter()
            logger.info(
                "master_phase1_stage_complete stage=%s elapsed_s=%.3f total_elapsed_s=%.3f",
                stage,
                now - postprocess_last_tick,
                now - extract_started,
            )
            postprocess_last_tick = now
            postprocess_stage += 1
            _report(
                f"phase1_postprocess_{stage}",
                min(postprocess_stage, postprocess_total),
                postprocess_total,
            )

        _postprocess_progress("coverage")

        if event_scheduler is not None:
            event_candidate_payload = event_scheduler.payload(
                scanned_frames=len(scanned_frames)
            )
            event_candidate_payload["audio_seed_sha256"] = str(
                self._candidate_window_payload.get("seed_sha256") or ""
            )
            event_candidate_payload["source_transcript_sha256"] = str(
                self._candidate_window_payload.get("source_transcript_sha256") or ""
            )
            (dest / f"{CANDIDATE_WINDOW_SCHEMA_VERSION}.json").write_text(
                json.dumps(event_candidate_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        logger.info(
            "master_phase1_scan coarse_hits=%s phase_hits=%s dense_extra_frames=%s "
            "residual_risk_frames=%s residual_profile_boxes=%s "
            "geom_rejected=%s total_hits=%s cached_frames=%s cache_bytes=%s",
            len(coarse_hits),
            len(phase_hits),
            len(dense_needed),
            len(residual_risk_frames),
            residual_profile_boxes,
            geometry_rejected,
            len(hits),
            len(frame_cache),
            frame_cache.backing_bytes,
        )

        coverage = build_text_frame_coverage(
            _hits_to_source(hits),
            frame_count=frame_count,
            frame_w=source_width,
            frame_h=source_height,
            scanned_frames=sorted(scanned_frames),
        )
        coverage["temporal_scan"] = {
            "policy_version": (
                EVENT_SCAN_POLICY_VERSION
                if self._event_scan
                else TEMPORAL_SCAN_POLICY_VERSION
            ),
            "analysis_engine": self._analysis_engine,
            "analysis_policy_version": (
                EVENT_SCAN_POLICY_VERSION
                if self._event_scan
                else TEMPORAL_SCAN_POLICY_VERSION
            ),
            "logical_step": int(self._step),
            "all_frame_lightweight_probes": int(lightweight_scanned_frames),
            "heavy_probe_frames": len(scanned_frames),
            "heavy_probe_ratio": round(len(scanned_frames) / float(max(1, frame_count)), 4),
            "max_heavy_probe_gap_frames": (
                heavy_probe_gap_frames if self._step == 1 else self._step
            ),
            "probe_reasons": dict(sorted(temporal_probe_reasons.items())),
            "transition_frames": len(temporal_transition_frames),
            "dense_rescan_policy": "provisional_interval_boundaries_v1",
            "dense_rescan_budget": dense_rescan_budget,
            "small_text_recovery": {
                "anchors": len(small_text_anchors),
                "frames": len(small_text_frames),
                "hits": len(small_text_hits),
                "long_edge": PHASE1_SMALL_TEXT_DET_LONG_EDGE,
                "bin_thresh": PHASE1_SMALL_TEXT_DET_BIN_THRESH,
                "budget": small_text_budget,
            },
        }
        if event_candidate_payload:
            coverage["temporal_scan"]["event_candidates"] = event_candidate_payload
        coverage_path = dest / "text_frame_coverage.json"
        coverage_path.write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "master_phase1_text_coverage frames_with_text=%s/%s scanned=%s hits=%s path=%s",
            coverage.get("n_frames_with_text"),
            frame_count,
            coverage.get("n_scanned_frames"),
            coverage.get("n_hits"),
            coverage_path,
        )

        _postprocess_progress("merge_tracks")
        merged = merge_tracks_by_centroid(
            hits,
            frame_count=frame_count,
            pad=self._pad,
            max_centroid_px=self._centroid_merge_px,
            gap_max=(
                event_track_merge_gap_frames(fps)
                if self._event_scan
                else MERGE_GAP_FRAMES
            ),
            frame_w=width,
            frame_h=height,
        )
        provisional_single_frame_frames = (
            list(
                event_candidate_payload.get(
                    "single_frame_retention_candidate_frames"
                )
                or []
            )
            if self._event_scan and event_candidate_payload
            else []
        )
        confirmed, dropped = confirm_tracks(
            merged,
            min_hits=self._min_hits,
            strong_single_frame_indices=provisional_single_frame_frames,
        )
        _postprocess_progress("finalize_tracks")
        tracks, finalize_audit = finalize_confirmed_tracks(
            confirmed,
            frame_count=frame_count,
            frame_w=width,
            frame_h=height,
            min_hits=self._min_hits,
            split_gap_max=(
                SPLIT_GAP_FRAMES
            ),
            editor_split_gap_max=(
                event_track_merge_gap_frames(fps) if self._event_scan else None
            ),
            strong_single_frame_indices=provisional_single_frame_frames,
        )
        provisional_single_frame_set = {
            int(value) for value in provisional_single_frame_frames
        }
        for track in tracks:
            if (
                int(track.hit_count) == 1
                and any(
                    int(value) in provisional_single_frame_set
                    for value in track.hit_frames
                )
            ):
                setattr(track, "_strong_single_frame_textness", True)
                setattr(track, "_single_frame_retention_candidate", True)
        tracks, wide_ui_split_audit = split_wide_ui_tracks_by_ink_columns(
            tracks,
            frame_cache=frame_cache,
            frame_w=width,
            frame_h=height,
        )
        for track in tracks:
            if (
                int(track.hit_count) == 1
                and any(
                    int(value) in provisional_single_frame_set
                    for value in track.hit_frames
                )
            ):
                setattr(track, "_strong_single_frame_textness", True)
                setattr(track, "_single_frame_retention_candidate", True)
        # Geometry/temporal provenance is intentionally evaluated before local
        # recognition. Dense phone/app panels and scene-bound text are preserve-
        # only; spending recognizer and editor refinement work on them is both
        # slow and a source of accidental source-text removal.
        early_provenance = classify_visual_text_provenance(
            tracks,
            frame_w=width,
            frame_h=height,
            text_audit={},
            frame_cache=frame_cache,
        )
        early_protected_source: list[MergedTrack] = []
        editor_or_uncertain_tracks: list[MergedTrack] = []
        for track in tracks:
            decision = dict(early_provenance.get(id(track)) or {})
            if (
                str(decision.get("classification") or "")
                in {"SOURCE_INTRINSIC", "SOURCE_INTRINSIC_PANEL", "PLATFORM_UI"}
                and float(decision.get("confidence") or 0.0) >= 0.96
            ):
                setattr(track, "_source_intrinsic_candidate", "early_geometry_provenance")
                setattr(track, "_skip_editor_postprocess", True)
                early_protected_source.append(track)
            else:
                editor_or_uncertain_tracks.append(track)
        tracks = editor_or_uncertain_tracks
        _postprocess_progress("local_text_gate")
        recognizer = None
        try:
            from src.media_pipeline.frame_sampling.ensure_text_recognizer_model import (
                ensure_text_recognizer_assets,
            )
            from src.media_pipeline.frame_sampling.local_text_recognizer import (
                LocalTextRecognizer,
            )

            model_path, dict_path = ensure_text_recognizer_assets()
            recognizer = LocalTextRecognizer(model_path, dict_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("phase1_local_recognizer_unavailable err=%s", exc)
        tracks, text_audit = filter_tracks_by_local_text(
            tracks,
            frame_cache=frame_cache,
            frame_w=width,
            frame_h=height,
            recognizer=recognizer,
            source=source,
            preserve_source_candidates=True,
        )
        tracks.extend(early_protected_source)
        text_audit["early_source_partition"] = {
            "policy": "geometry_temporal_provenance_before_local_recognizer_v1",
            "protected_tracks": len(early_protected_source),
            "recognizer_candidate_tracks": len(editor_or_uncertain_tracks),
            "confidence_threshold": 0.96,
        }
        preliminary_provenance = classify_visual_text_provenance(
            tracks,
            frame_w=width,
            frame_h=height,
            text_audit=text_audit,
            frame_cache=frame_cache,
        )
        preliminary_counts: Counter[str] = Counter()
        for track in tracks:
            classification = str(
                dict(preliminary_provenance.get(id(track)) or {}).get(
                    "classification"
                )
                or "UNCERTAIN"
            )
            preliminary_counts[classification] += 1
            if classification in {
                "SOURCE_INTRINSIC",
                "SOURCE_INTRINSIC_PANEL",
                "PLATFORM_UI",
            }:
                if not bool(getattr(track, "_source_intrinsic_candidate", None)):
                    setattr(
                        track,
                        "_source_intrinsic_candidate",
                        "preliminary_source_provenance",
                    )
                setattr(track, "_skip_editor_postprocess", True)
            elif classification == "UNCERTAIN":
                # Fail safe: an uncertain source/editor decision must not be
                # rewritten by editor-only ink and content segmentation before
                # the operator sees it.
                setattr(track, "_skip_editor_postprocess", True)
        # Source-bound copy is already complete for its only downstream action:
        # preserve the original pixels.  Content segmentation, hardsub ink
        # recovery and editor boundary reconciliation cannot improve that
        # action and previously made dense phone/app videos spend minutes in
        # postprocess.  Keep those tracks intact while the editor branch is
        # refined independently.
        protected_source_candidates = [
            track
            for track in tracks
            if bool(getattr(track, "_skip_editor_postprocess", False))
        ]
        tracks = [
            track
            for track in tracks
            if not bool(getattr(track, "_skip_editor_postprocess", False))
        ]
        text_audit["source_candidate_partition"] = {
            "protected_tracks": len(protected_source_candidates),
            "editor_postprocess_tracks": len(tracks),
            "preliminary_provenance_counts": dict(
                sorted(preliminary_counts.items())
            ),
            "policy": "preserve_source_before_editor_postprocess_v1",
        }
        _postprocess_progress("geometry_normalize")
        tracks = complete_locked_overlay_boxes_from_hit_evidence(
            tracks,
            frame_w=width,
            frame_h=height,
        )
        before_coalesce = len(tracks)
        tracks = coalesce_near_duplicate_tracks(
            tracks, frame_w=width, frame_h=height
        )
        before_purge = len(tracks)
        tracks = purge_redundant_hardsub_fragments(
            tracks, frame_w=width, frame_h=height
        )
        _postprocess_progress("content_segmentation")
        if self._event_scan:
            tracks, content_audit = split_tracks_by_visual_content_change(
                tracks,
                frame_cache=frame_cache,
            )
            content_audit["local_ocr_skipped"] = True
        else:
            tracks, content_audit = split_tracks_by_local_text_change(
                tracks,
                frame_cache=frame_cache,
                frame_w=width,
                frame_h=height,
                recognizer=recognizer,
                source=source,
            )
        _postprocess_progress("content_reconcile")
        if self._event_scan:
            content_reconcile_pre_audit = {
                "method": "temporal_consensus_geometry_reconcile_v1",
                "before_count": len(tracks),
                "after_count": len(tracks),
                "merged_tracks": 0,
                "local_ocr_skipped": True,
            }
        else:
            tracks, content_reconcile_pre_audit = coalesce_tracks_by_local_text_content(
                tracks,
                frame_cache=frame_cache,
                frame_w=width,
                frame_h=height,
                recognizer=recognizer,
                source=source,
            )
        tracks = purge_redundant_hardsub_fragments(
            tracks, frame_w=width, frame_h=height
        )
        if self._event_scan:
            content_boundary_audit = {
                "method": "event_boundary_evidence_v1",
                "tracks": len(tracks),
                "local_ocr_skipped": True,
            }
        else:
            tracks, content_boundary_audit = expand_tracks_by_local_text_continuity(
                tracks,
                frame_cache=frame_cache,
                frame_count=frame_count,
                frame_w=width,
                frame_h=height,
                recognizer=recognizer,
                source=source,
            )
        _postprocess_progress("boundary_refinement")
        boundary_audit: list[dict[str, Any]] = []
        boundary_refined: list[MergedTrack] = []
        for track in tracks:
            if self._event_scan:
                refined = track
                audit_row = {
                    "method": "event_hit_boundary_v1",
                    "applied": False,
                    "prior_span": [track.start_frame, track.end_frame],
                    "refined_span": [track.start_frame, track.end_frame],
                    "random_frame_reads_skipped": True,
                }
            else:
                refined, audit_row = refine_track_boundaries_by_template(
                    track,
                    frame_cache=frame_cache,
                    frame_count=frame_count,
                    frame_w=width,
                    frame_h=height,
                    source=source,
                )
            boundary_refined.append(refined)
            boundary_audit.append(audit_row)
        tracks, boundary_audit = purge_hardsub_shadows_by_boundary_audit(
            boundary_refined,
            boundary_audit,
            frame_w=width,
            frame_h=height,
        )
        tracks = apply_ink_aware_keyframes(
            tracks,
            frame_cache=frame_cache,
            frame_w=width,
            frame_h=height,
        )
        tracks = extend_hardsub_tracks_to_ink(
            tracks,
            frame_cache=frame_cache,
            frame_w=width,
            frame_h=height,
            source=source,
        )
        _postprocess_progress("post_ink_reconcile")
        # A second reconciliation pass runs after ink normalization. DBNet may
        # produce wildly different pre-ink X spans for the same caption, so the
        # content-safe overlap can become visible only after glyph tightening.
        # It must run before fragment purge so a continuation is unioned into
        # the host rather than dropped with its later end-frame evidence.
        if self._event_scan:
            content_reconcile_post_audit = {
                "method": "temporal_consensus_post_ink_v1",
                "before_count": len(tracks),
                "after_count": len(tracks),
                "merged_tracks": 0,
                "local_ocr_skipped": True,
            }
        else:
            tracks, content_reconcile_post_audit = coalesce_tracks_by_local_text_content(
                tracks,
                frame_cache=frame_cache,
                frame_w=width,
                frame_h=height,
                recognizer=recognizer,
                source=source,
                geometry_normalized=True,
            )
        if int(content_reconcile_post_audit.get("merged_tracks") or 0) > 0:
            boundary_audit = []
            boundary_refined = []
            for track in tracks:
                refined, audit_row = refine_track_boundaries_by_template(
                    track,
                    frame_cache=frame_cache,
                    frame_count=frame_count,
                    frame_w=width,
                    frame_h=height,
                    source=source,
                )
                boundary_refined.append(refined)
                boundary_audit.append(audit_row)
            boundary_refined, boundary_audit = (
                purge_hardsub_shadows_by_boundary_audit(
                    boundary_refined,
                    boundary_audit,
                    frame_w=width,
                    frame_h=height,
                )
            )
            tracks = apply_ink_aware_keyframes(
                boundary_refined,
                frame_cache=frame_cache,
                frame_w=width,
                frame_h=height,
            )
            # Both inputs have already passed horizontal ink refinement. A
            # second extend would re-introduce scene texture into the selected
            # normalized geometry; only timing/boundary/keyframe changed here.
        # Re-purge only after both content reconciliation passes have preserved
        # the union lifespan of duplicate geometry fragments.
        tracks = purge_redundant_hardsub_fragments(
            tracks, frame_w=width, frame_h=height
        )
        # Content segmentation rebuilds tracks from its selected hit subset;
        # re-apply supported edge completion so repeated full-label evidence
        # (for example a leading glyph recovered on later glare-free frames)
        # cannot be replaced by the partial median again.
        tracks = complete_locked_overlay_boxes_from_hit_evidence(
            tracks,
            frame_w=width,
            frame_h=height,
        )
        _postprocess_progress("coverage_reconcile")
        tracks, dense_coverage_geometry_audit = (
            constrain_hardsubs_to_dense_detector_coverage(
                tracks,
                hits,
                frame_w=width,
                frame_h=height,
            )
        )
        tracks, final_temporal_coverage_audit = reconcile_final_tracks_with_coverage(
            tracks,
            hits,
            frame_count=frame_count,
            frame_w=width,
            frame_h=height,
        )
        _postprocess_progress("residual_recovery")
        if self._event_scan:
            residual_hardsub_recovery_audit = {
                "method": "event_candidate_residual_coverage_v1",
                "before_count": len(tracks),
                "after_count": len(tracks),
                "local_ocr_skipped": True,
            }
        else:
            tracks, residual_hardsub_recovery_audit = recover_residual_hardsub_tracks(
                tracks,
                hits,
                frame_cache=frame_cache,
                frame_count=frame_count,
                frame_w=width,
                frame_h=height,
                recognizer=recognizer,
                source=source,
            )
        tracks = purge_redundant_hardsub_fragments(
            tracks, frame_w=width, frame_h=height
        )
        if self._event_scan:
            post_refinement_sparse_compact_audit = {
                "method": "provenance_fail_closed_sparse_guard_v1",
                "before_count": len(tracks),
                "after_count": len(tracks),
                "local_ocr_skipped": True,
            }
        else:
            tracks, post_refinement_sparse_compact_audit = (
                purge_unverified_sparse_compact_tracks_after_refinement(
                    tracks,
                    frame_cache=frame_cache,
                    frame_w=width,
                    frame_h=height,
                    recognizer=recognizer,
                    source=source,
                )
            )
        tracks, nested_temporal_ui_fragment_audit = (
            purge_temporally_nested_ui_fragments(
                tracks,
                frame_w=width,
                frame_h=height,
            )
        )
        tracks.extend(protected_source_candidates)
        tracks.sort(
            key=lambda row: (
                int(row.start_frame),
                float(row.box_coords[1]),
                float(row.box_coords[0]),
            )
        )
        _postprocess_progress("audit_finalize")
        content_reconcile_audit = {
            "method": "local_text_cross_track_reconcile_two_pass_v1",
            "before_count": content_reconcile_pre_audit.get("before_count"),
            "after_count": len(tracks),
            "merged_tracks": int(
                content_reconcile_pre_audit.get("merged_tracks") or 0
            )
            + int(content_reconcile_post_audit.get("merged_tracks") or 0),
            "pre_ink": content_reconcile_pre_audit,
            "post_ink": content_reconcile_post_audit,
        }
        finalize_audit["local_text_gate"] = text_audit
        finalize_audit["wide_ui_column_split"] = wide_ui_split_audit
        finalize_audit["content_segmentation"] = content_audit
        finalize_audit["content_reconciliation"] = content_reconcile_audit
        finalize_audit["content_boundary_expansion"] = content_boundary_audit
        finalize_audit["dense_coverage_geometry"] = dense_coverage_geometry_audit
        finalize_audit["final_temporal_coverage"] = final_temporal_coverage_audit
        finalize_audit["residual_hardsub_recovery"] = (
            residual_hardsub_recovery_audit
        )
        finalize_audit["post_refinement_sparse_compact_filter"] = (
            post_refinement_sparse_compact_audit
        )
        finalize_audit["nested_temporal_ui_fragment_guard"] = (
            nested_temporal_ui_fragment_audit
        )
        finalize_audit["residual_risk_profile"] = {
            "method": "raw_dbnet_intro_outro_risk_profile_v1",
            "risk_seconds": PHASE1_RESIDUAL_RISK_SECONDS,
            "frames": len(residual_risk_frames),
            "detected_boxes": residual_profile_boxes,
            "risk_only_hits": len(residual_risk_hits),
            "long_edge": PHASE1_RESIDUAL_DET_LONG_EDGE,
            "bin_thresh": PHASE1_RESIDUAL_DET_BIN_THRESH,
        }
        finalize_audit["temporal_scan"] = dict(coverage.get("temporal_scan") or {})
        finalize_audit["coalesce"] = {
            "before": before_coalesce,
            "after": before_purge,
        }
        finalize_audit["hardsub_fragment_purge"] = {
            "before": before_purge,
            "after": len(tracks),
        }
        finalize_audit["boundary_refinement"] = {
            "attempted": len(boundary_audit),
            "applied": sum(1 for row in boundary_audit if row.get("applied")),
            "changed": sum(
                1
                for row in boundary_audit
                if row.get("applied")
                and row.get("prior_span") != row.get("refined_span")
            ),
            "rows": boundary_audit,
        }
        finalize_audit["after_count"] = len(tracks)
        if text_audit.get("dropped"):
            logger.info(
                "master_phase1_local_text_gate dropped=%s kept=%s coalesce=%s→%s "
                "hardsub_purge→%s",
                text_audit.get("dropped"),
                len(tracks),
                before_coalesce,
                before_purge,
                len(tracks),
            )

        def _coverage_rows(
            current_tracks: Sequence[MergedTrack],
        ) -> list[dict[str, Any]]:
            return [
                {
                    "text_id": f"sub_{index:02d}",
                    "start_frame": int(track.start_frame),
                    "end_frame": int(track.end_frame),
                    "hit_frames": list(track.hit_frames),
                    "box_coords": _box_to_source(track.box_coords),
                }
                for index, track in enumerate(current_tracks, start=1)
            ]

        boundary_dbnet_audit: dict[str, Any] = {
            "policy_version": "endpoint_dbnet_closure_v1",
            "candidate_frames": 0,
            "decoded_frames": 0,
            "detector_hits": 0,
            "extended_tracks": 0,
            "rows": [],
        }
        if self._event_scan and tracks:
            # Coverage proxy is deliberately cheap but can miss dark/outlined
            # labels on skin or fabric. Recheck only endpoints whose last/first
            # DBNet hit is not adjacent to the semantic span. This is bounded
            # (five frames per risky side) and never becomes an all-frame OCR
            # pass.
            endpoint_offsets = (1, 3, 6, 9)
            endpoint_candidates: dict[int, list[tuple[int, str]]] = defaultdict(list)
            for track in tracks:
                hit_frames = sorted({int(value) for value in track.hit_frames})
                if not hit_frames:
                    continue
                role = classify_ocr_box_role(
                    track.box_coords, frame_w=width, frame_h=height
                )
                width_frac = max(1.0, float(track.box_coords[2]) - float(track.box_coords[0])) / max(1.0, float(width))
                if role not in {"hardsub", "mid_label", "ui_chip", "generic"}:
                    continue
                if role != "hardsub" and width_frac < 0.10:
                    continue
                text_id = str(getattr(track, "text_id", "") or id(track))
                if int(track.end_frame) - hit_frames[-1] > 0:
                    for offset in endpoint_offsets:
                        frame = int(track.end_frame) + int(offset)
                        if frame < frame_count:
                            endpoint_candidates[frame].append((id(track), "end"))
                if hit_frames[0] - int(track.start_frame) > 0:
                    for offset in endpoint_offsets:
                        frame = int(track.start_frame) - int(offset)
                        if frame >= 0:
                            endpoint_candidates[frame].append((id(track), "start"))
            selected_boundary_frames = sorted(endpoint_candidates)
            boundary_dbnet_audit["candidate_frames"] = len(selected_boundary_frames)
            if selected_boundary_frames:
                track_by_object_id = {id(track): track for track in tracks}
                boundary_hits: dict[int, list[DetectionHit]] = defaultdict(list)
                for frame_index, boundary_bgr in _event_selected_frames(
                    selected_boundary_frames
                ):
                    frame_cache[frame_index] = boundary_bgr
                    scanned_frames.add(frame_index)
                    found, rejected = self._detect_frame_hits(
                        _analysis_frame(boundary_bgr),
                        frame_index=frame_index,
                        detector=detector,
                        frame_w=width,
                        frame_h=height,
                    )
                    geometry_rejected += rejected
                    boundary_hits[frame_index].extend(found)
                    boundary_dbnet_audit["decoded_frames"] += 1
                    boundary_dbnet_audit["detector_hits"] += len(found)

                for track in tracks:
                    hit_frames = sorted({int(value) for value in track.hit_frames})
                    if not hit_frames:
                        continue
                    matched_by_side: dict[str, list[DetectionHit]] = {"start": [], "end": []}
                    for frame_index, hits_at_frame in boundary_hits.items():
                        # The selected decode is shared for efficiency, but an
                        # endpoint hit belongs only to the track/side that
                        # scheduled that frame.  Ignoring this ownership lets
                        # every track consume every other track's endpoint hit
                        # and expands independent caption epochs across scenes.
                        scheduled_sides = {
                            str(side)
                            for object_id, side in endpoint_candidates.get(
                                frame_index, ()
                            )
                            if int(object_id) == id(track)
                        }
                        side = next(
                            (
                                value
                                for value in ("start", "end")
                                if value in scheduled_sides
                            ),
                            "",
                        )
                        if not side:
                            continue
                        for hit in hits_at_frame:
                            hx0, hy0, hx1, hy1 = (float(value) for value in hit.box_xyxy)
                            tx0, ty0, tx1, ty1 = (float(value) for value in track.box_coords)
                            overlap = max(0.0, min(hx1, tx1) - max(hx0, tx0))
                            shorter = max(1.0, min(hx1 - hx0, tx1 - tx0))
                            hcy = (hy0 + hy1) * 0.5
                            tcy = (ty0 + ty1) * 0.5
                            if (
                                overlap / shorter >= 0.35
                                and abs(hcy - tcy) <= max(48.0, 0.08 * float(height))
                            ):
                                matched_by_side[side].append(hit)
                    extension: dict[str, Any] = {}
                    for side, side_hits in matched_by_side.items():
                        by_frame = {int(hit.frame_index): hit for hit in side_hits}
                        # Two independent endpoint observations prevent a
                        # single scene edge from extending an editor track.
                        if len(by_frame) < 2:
                            continue
                        ordered = sorted(by_frame)
                        if side == "end":
                            new_end = max(ordered)
                            track.end_frame = max(int(track.end_frame), new_end)
                        else:
                            new_start = min(ordered)
                            track.start_frame = min(int(track.start_frame), new_start)
                        for hit in side_hits:
                            track.hit_frames.append(int(hit.frame_index))
                            track.hit_boxes.append(tuple(float(value) for value in hit.box_xyxy))
                            track.hit_sharpness.append(float(hit.sharpness))
                        extension[side] = [min(ordered), max(ordered)]
                    if extension:
                        track.hit_count = len(track.hit_frames)
                        track.box_coords = stable_box_xyxy(track.hit_boxes, expansive=False)
                        track.centroid = _box_centroid(track.box_coords)
                        boundary_dbnet_audit["extended_tracks"] += 1
                        boundary_dbnet_audit["rows"].append(
                            {
                                "text_id": str(getattr(track, "text_id", "") or ""),
                                "extension": extension,
                            }
                        )
            finalize_audit["endpoint_dbnet_closure"] = dict(boundary_dbnet_audit)

        coverage_rows = _coverage_rows(tracks)
        completeness_residual_audit: dict[str, Any] = {
            "policy_version": "phase1_unassigned_text_discovery_v1",
            "candidate_frames": 0,
            "dbnet_frames": 0,
            "dbnet_hits": 0,
            "new_tracks": 0,
            "second_closure": False,
            "integration": {
                "policy_version": "residual_append_preserve_authority_v1",
                "authority_tracks_before": len(tracks),
                "residual_tracks_before": 0,
                "residual_tracks_after_coalesce": 0,
                "tracks_after_append": len(tracks),
                "authority_recoalesced": False,
            },
        }
        if self._event_scan:
            coverage_scale = PHASE1_COVERAGE_PROXY_LONG_EDGE / float(
                max(1, max(source_width, source_height))
            )
            coverage_width = max(2, int(round(source_width * coverage_scale)))
            coverage_height = max(2, int(round(source_height * coverage_scale)))

            def _close_coverage(
                rows: Sequence[Mapping[str, Any]],
                *,
                phase: str,
            ) -> dict[str, Any]:
                closure = CoverageTrackClosure(
                    rows,
                    source_width=source_width,
                    source_height=source_height,
                    fps=fps,
                )
                reader = _FfmpegProxyFrameReader(
                    source,
                    width=coverage_width,
                    height=coverage_height,
                )
                coverage_index = 0
                _report(phase, 0, frame_count or 1)
                try:
                    while True:
                        ok, proxy_frame = reader.read()
                        if not ok or proxy_frame is None:
                            break
                        closure.observe(proxy_frame, frame_index=coverage_index)
                        coverage_index += 1
                        if coverage_index % progress_interval == 0:
                            _report(
                                phase,
                                coverage_index,
                                frame_count or coverage_index,
                            )
                finally:
                    reader.release()
                if coverage_index != frame_count:
                    raise RuntimeError(
                        "Coverage closure frame count mismatch "
                        f"({coverage_index} != {frame_count})"
                    )
                _report(phase, coverage_index, frame_count or 1)
                return closure.finalize(frame_count=frame_count)

            coverage_payload = _close_coverage(
                coverage_rows,
                phase="phase1_coverage_closure",
            )
            unassigned_frames = sorted(
                {
                    int(value)
                    for value in list(
                        coverage_payload.get("unassigned_candidate_frames") or []
                    )
                    if 0 <= int(value) < frame_count
                }
            )
            completeness_residual_audit["candidate_frames"] = len(
                unassigned_frames
            )
            # Allocate the bounded high-resolution pass per spatial-temporal
            # residual epoch. A global frame linspace is unsafe here: generic
            # texture can stay active all video and starve a short editor label.
            discovery_frames: list[int] = []
            discovery_schedule_audit: dict[str, Any] = {}
            if unassigned_frames:
                max_frames = max(
                    24,
                    min(180, int(np.ceil(duration_ms / 1000.0 * 2.0))),
                )
                (
                    discovery_frames,
                    discovery_schedule_audit,
                ) = schedule_unassigned_discovery_frames(
                    list(coverage_payload.get("unassigned_candidates") or []),
                    fps=fps,
                    duration_ms=duration_ms,
                    max_frames=max_frames,
                    boundary_frames=[
                        boundary
                        for raw in coverage_rows
                        for boundary in (
                            int(raw.get("start_frame") or 0),
                            int(raw.get("end_frame") or 0),
                        )
                    ],
                )
                completeness_residual_audit["schedule"] = dict(
                    discovery_schedule_audit
                )

            residual_discovery_hits: list[DetectionHit] = []
            if discovery_frames:
                edge_reserved_frame_set = {
                    int(value)
                    for value in list(
                        discovery_schedule_audit.get("edge_reserved_frames")
                        or []
                    )
                }
                candidate_regions_by_frame: dict[int, list[dict[str, Any]]] = (
                    defaultdict(list)
                )
                for raw_candidate in list(
                    coverage_payload.get("unassigned_candidates") or []
                ):
                    if not isinstance(raw_candidate, Mapping):
                        continue
                    candidate_regions_by_frame[
                        int(raw_candidate.get("frame_index") or 0)
                    ].append(dict(raw_candidate.get("geometry") or {}))

                def _matches_unassigned_region(hit: DetectionHit) -> bool:
                    hx0, hy0, hx1, hy1 = (
                        float(value) for value in hit.box_xyxy[:4]
                    )
                    hit_area = max(1.0, (hx1 - hx0) * (hy1 - hy0))
                    hit_cx = 0.5 * (hx0 + hx1)
                    hit_cy = 0.5 * (hy0 + hy1)
                    for geometry in candidate_regions_by_frame.get(
                        int(hit.frame_index), []
                    ):
                        gx0 = float(geometry.get("x") or 0.0) * width
                        gy0 = float(geometry.get("y") or 0.0) * height
                        gx1 = gx0 + float(geometry.get("width") or 0.0) * width
                        gy1 = gy0 + float(geometry.get("height") or 0.0) * height
                        intersection = max(0.0, min(hx1, gx1) - max(hx0, gx0)) * max(
                            0.0, min(hy1, gy1) - max(hy0, gy0)
                        )
                        region_area = max(1.0, (gx1 - gx0) * (gy1 - gy0))
                        if (
                            intersection / min(hit_area, region_area) >= 0.25
                            or gx0 <= hit_cx <= gx1
                            and gy0 <= hit_cy <= gy1
                        ):
                            return True
                    return False

                _report(
                    "phase1_unassigned_discovery",
                    0,
                    len(discovery_frames),
                )
                for done, (fi, analysis_bgr) in enumerate(
                    _event_selected_frames(discovery_frames), start=1
                ):
                    scanned_frames.add(fi)
                    frame_cache[fi] = analysis_bgr
                    found, rejected = self._detect_frame_hits(
                        analysis_bgr,
                        frame_index=fi,
                        detector=detector,
                        frame_w=width,
                        frame_h=height,
                        long_edge=max(width, height),
                        bin_thresh=PHASE1_SMALL_TEXT_DET_BIN_THRESH,
                    )
                    geometry_rejected += rejected
                    residual_discovery_hits.extend(
                        hit
                        for hit in found
                        if (
                            _matches_unassigned_region(hit)
                            # The proxy residual intentionally does not know
                            # OCR and can miss a saturated/outlined intro or
                            # outro title at its exact locus.  Edge frames have
                            # an independently reserved high-resolution budget;
                            # admit their DBNet boxes to the normal local-CJK
                            # and provenance gates rather than requiring a
                            # noisy proxy geometry match.  No edge hit becomes
                            # authority from this exception alone.
                            or int(hit.frame_index) in edge_reserved_frame_set
                        )
                        and not any(
                            _residual_hit_covered_by_track(
                                hit,
                                track,
                                frame_w=width,
                                frame_h=height,
                            )
                            for track in tracks
                        )
                    )
                    if done % progress_interval == 0:
                        _report(
                            "phase1_unassigned_discovery",
                            done,
                            len(discovery_frames),
                        )
                _report(
                    "phase1_unassigned_discovery",
                    len(discovery_frames),
                    len(discovery_frames),
                )

            new_tracks: list[MergedTrack] = []
            if residual_discovery_hits:
                # Every discovery frame may provisionally carry a single
                # DBNet hit into the local recognizer.  It becomes authority
                # only after CJK recognition; otherwise a single hit is
                # dropped. Multi-hit tracks remain governed by temporal
                # consensus and do not need this exception.
                provisional_residual_single_frames = list(discovery_frames)
                residual_merged = merge_tracks_by_centroid(
                    residual_discovery_hits,
                    frame_count=frame_count,
                    pad=self._pad,
                    max_centroid_px=self._centroid_merge_px,
                    gap_max=event_track_merge_gap_frames(fps),
                    frame_w=width,
                    frame_h=height,
                )
                residual_confirmed, _residual_dropped = confirm_tracks(
                    residual_merged,
                    min_hits=self._min_hits,
                    strong_single_frame_indices=(
                        provisional_residual_single_frames
                    ),
                )
                new_tracks, _residual_finalize = finalize_confirmed_tracks(
                    residual_confirmed,
                    frame_count=frame_count,
                    frame_w=width,
                    frame_h=height,
                    min_hits=self._min_hits,
                    split_gap_max=SPLIT_GAP_FRAMES,
                    editor_split_gap_max=event_track_merge_gap_frames(fps),
                    strong_single_frame_indices=(
                        provisional_residual_single_frames
                    ),
                )
                provisional_residual_single_set = set(
                    provisional_residual_single_frames
                )
                for track in new_tracks:
                    if int(track.hit_count) == 1 and any(
                        int(value) in provisional_residual_single_set
                        for value in track.hit_frames
                    ):
                        setattr(track, "_strong_single_frame_textness", True)
                        setattr(track, "_single_frame_retention_candidate", True)
                new_tracks, residual_text_audit = filter_tracks_by_local_text(
                    new_tracks,
                    frame_cache=frame_cache,
                    frame_w=width,
                    frame_h=height,
                    recognizer=recognizer,
                    source=source,
                    preserve_source_candidates=True,
                )
                completeness_residual_audit["local_text_gate"] = {
                    "dropped": int(residual_text_audit.get("dropped") or 0),
                    "kept": len(new_tracks),
                }
                new_tracks = apply_ink_aware_keyframes(
                    new_tracks,
                    frame_cache=frame_cache,
                    frame_w=width,
                    frame_h=height,
                )
                new_tracks = extend_hardsub_tracks_to_ink(
                    new_tracks,
                    frame_cache=frame_cache,
                    frame_w=width,
                    frame_h=height,
                    source=source,
                )
                tracks, residual_integration_audit = (
                    integrate_residual_tracks_without_recoalescing_authority(
                    tracks,
                    new_tracks,
                    frame_w=width,
                    frame_h=height,
                    )
                )
                completeness_residual_audit["integration"] = dict(
                    residual_integration_audit
                )
                tracks = purge_redundant_hardsub_fragments(
                    tracks,
                    frame_w=width,
                    frame_h=height,
                )
                tracks.sort(
                    key=lambda row: (
                        int(row.start_frame),
                        float(row.box_coords[1]),
                        float(row.box_coords[0]),
                    )
                )
                coverage_rows = _coverage_rows(tracks)
                coverage_payload = _close_coverage(
                    coverage_rows,
                    phase="phase1_coverage_reclosure",
                )
                completeness_residual_audit["second_closure"] = True

            completeness_residual_audit.update(
                {
                    "dbnet_frames": len(discovery_frames),
                    "dbnet_hits": len(residual_discovery_hits),
                    "new_tracks": len(new_tracks),
                    "remaining_unassigned_candidate_frames": len(
                        list(
                            coverage_payload.get("unassigned_candidate_frames")
                            or []
                        )
                    ),
                }
            )
            finalize_audit["completeness_residual_discovery"] = dict(
                completeness_residual_audit
            )
            if event_candidate_payload:
                event_candidate_payload["coverage_unassigned_candidate_frames"] = list(
                    coverage_payload.get("unassigned_candidate_frames") or []
                )
                event_candidate_payload["coverage_residual_dbnet_frames"] = list(
                    discovery_frames
                )
                event_candidate_payload["coverage_residual_discovery"] = dict(
                    completeness_residual_audit
                )
                (dest / f"{CANDIDATE_WINDOW_SCHEMA_VERSION}.json").write_text(
                    json.dumps(
                        event_candidate_payload,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
        else:
            coverage_payload = {
                "schema_version": COVERAGE_TRACK_SCHEMA_VERSION,
                "policy_version": "legacy_static_geometry_projection",
                "network_calls": 0,
                "scanned_frames": 0,
                "frame_count": int(frame_count),
                "tracks": [
                    {
                        "text_id": str(row["text_id"]),
                        "policy_version": "legacy_static_geometry_projection",
                        "presence_ranges": [
                            [int(row["start_frame"]), int(row["end_frame"])]
                        ],
                        "geometry_keyframes": [
                            {
                                "frame_index": int(row["start_frame"]),
                                "geometry": {
                                    "x": float(row["box_coords"][0])
                                    / max(1, source_width),
                                    "y": float(row["box_coords"][1])
                                    / max(1, source_height),
                                    "width": (
                                        float(row["box_coords"][2])
                                        - float(row["box_coords"][0])
                                    )
                                    / max(1, source_width),
                                    "height": (
                                        float(row["box_coords"][3])
                                        - float(row["box_coords"][1])
                                    )
                                    / max(1, source_height),
                                },
                            }
                        ],
                        "confidence": 0.5,
                        "fail_closed": False,
                    }
                    for row in coverage_rows
                ],
            }

        crops_dir = dest / "crops"
        crops_dir.mkdir(parents=True, exist_ok=True)

        timeline: list[dict[str, Any]] = []
        provenance_by_track_id = classify_visual_text_provenance(
            tracks,
            frame_w=width,
            frame_h=height,
            text_audit=text_audit,
            frame_cache=frame_cache,
        )
        protected_source_ids = {id(track) for track in protected_source_candidates}
        for track in tracks:
            if id(track) not in protected_source_ids:
                continue
            decision = dict(provenance_by_track_id.get(id(track)) or {})
            classification = str(decision.get("classification") or "")
            if classification in {
                "SOURCE_INTRINSIC",
                "SOURCE_INTRINSIC_PANEL",
                "PLATFORM_UI",
            }:
                continue
            provenance_by_track_id[id(track)] = {
                "classification": "UNCERTAIN",
                "confidence": min(0.50, float(decision.get("confidence") or 0.50)),
                "policy_version": VISUAL_TEXT_PROVENANCE_SCHEMA_VERSION,
                "reasons": list(decision.get("reasons") or [])
                + [
                    "protected_by_pre_editor_source_partition",
                    "preserve_source_pixels_until_proven_editor_overlay",
                ],
            }
        _postprocess_progress("timeline_assets")
        for i, track in enumerate(tracks, start=1):
            text_id = f"sub_{i:02d}"
            rel_path = f"frames/{text_id}.jpg"
            abs_path = frames_dir / f"{text_id}.jpg"
            crop_rel = f"crops/{text_id}.jpg"
            crop_abs = crops_dir / f"{text_id}.jpg"
            key_frame = frame_cache.get(track.best_frame_index)
            if key_frame is None:
                key_frame = _read_frame(source, track.best_frame_index)
                if key_frame is not None:
                    key_frame = _analysis_frame(key_frame)
            if key_frame is not None:
                cv2.imwrite(
                    str(abs_path), key_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95]
                )
                _write_box_crop(key_frame, track.box_coords, crop_abs)
            timeline.append(
                timeline_entry_dict(
                    text_id=text_id,
                    start_frame=track.start_frame,
                    end_frame=track.end_frame,
                    fps=fps,
                    box_coords=_box_to_source(track.box_coords),
                    best_keyframe_path=rel_path.replace("\\", "/"),
                    hit_count=track.hit_count,
                    crop_path=crop_rel.replace("\\", "/"),
                    best_frame_index=track.best_frame_index,
                    hit_frames=list(track.hit_frames),
                    boundary_evidence=track_boundary_evidence(
                        track, frame_w=width, frame_h=height
                    ),
                    semantic_role=semantic_scene_role_for_track(
                        track, text_audit
                    ),
                    visual_provenance=provenance_by_track_id.get(id(track)),
                )
            )

        timeline_path = dest / "master_timeline.json"
        timeline_path.write_text(
            json.dumps(timeline, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        timeline_sha256 = hashlib.sha256(timeline_path.read_bytes()).hexdigest()
        coverage_payload["master_timeline_ref"] = {
            "path": timeline_path.name,
            "sha256": timeline_sha256,
        }
        coverage_path = dest / "phase1_track_coverage_v2.json"
        coverage_path.write_text(
            json.dumps(coverage_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        provenance_rows = [
            {
                "text_id": str(row.get("text_id") or ""),
                **dict(row.get("visual_provenance") or {}),
            }
            for row in timeline
        ]
        protected_source_rows = [
            {
                "text_id": str(row.get("text_id") or ""),
                "start_frame": row.get("start_frame"),
                "end_frame": row.get("end_frame"),
                "box_coords": list(row.get("box_coords") or []),
                "visual_provenance": dict(row.get("visual_provenance") or {}),
                "action": "PRESERVE_SOURCE_PIXELS",
            }
            for track, row in zip(tracks, timeline)
            if id(track) in protected_source_ids
        ]
        provenance_counts = Counter(
            str(row.get("classification") or "UNCERTAIN")
            for row in provenance_rows
        )
        provenance_payload = {
            "schema_version": VISUAL_TEXT_PROVENANCE_SCHEMA_VERSION,
            "phase1_ref": {
                "path": timeline_path.name,
                "sha256": hashlib.sha256(timeline_path.read_bytes()).hexdigest(),
            },
            "policy": {
                "phase1_authority": "v58_candidate",
                "authority_v3_6_full_duration": False,
                "source_intrinsic_action": "preserve_source_pixels",
                "editor_overlay_action": "ocr_translate_remove_replace",
                "uncertain_action": "operator_provenance_review",
            },
            "counts": dict(sorted(provenance_counts.items())),
            "tracks": provenance_rows,
            "protected_source_tracks": protected_source_rows,
        }
        (dest / "visual_text_provenance_v2.json").write_text(
            json.dumps(provenance_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        analysis_metrics: dict[str, Any] = {
            "analysis_engine": self._analysis_engine,
            "analysis_policy_version": (
                EVENT_SCAN_POLICY_VERSION
                if self._event_scan
                else TEMPORAL_SCAN_POLICY_VERSION
            ),
            "network_calls": 0,
            "frame_count": frame_count,
            "source_frame_size": [source_width, source_height],
            "analysis_frame_size": [width, height],
            "analysis_scale": round(float(analysis_scale), 6),
            "analysis_decode_backend": analysis_decode_backend,
            "all_frame_proxy_size": all_frame_proxy_size,
            "all_frame_proxy_frames": int(lightweight_scanned_frames),
            "detector_frames": len(scanned_frames),
            "detector_frame_ratio": round(
                len(scanned_frames) / float(max(1, frame_count)), 6
            ),
            "detector_preprocess_calls_estimate": len(scanned_frames) * 2,
            "tracks": len(timeline),
            "provenance_counts": dict(sorted(provenance_counts.items())),
            "protected_source_tracks": len(protected_source_candidates),
            "coverage_policy_version": COVERAGE_TRACK_POLICY_VERSION,
            "coverage_scanned_frames": int(
                coverage_payload.get("scanned_frames") or 0
            ),
            "coverage_tracks": len(list(coverage_payload.get("tracks") or [])),
            "coverage_unassigned_candidate_frames": len(
                list(
                    coverage_payload.get("unassigned_candidate_frames") or []
                )
            ),
            "completeness_residual_discovery": dict(
                completeness_residual_audit
            ),
            "elapsed_s": round(time.perf_counter() - extract_started, 3),
            "fallback_used": False,
        }
        if event_candidate_payload:
            analysis_metrics.update(
                {
                    "candidate_window_count": len(
                        list(event_candidate_payload.get("windows") or [])
                    ),
                    "audio_window_count": int(
                        event_candidate_payload.get("audio_window_count") or 0
                    ),
                    "candidate_seed_mode": str(
                        event_candidate_payload.get("candidate_seed_mode")
                        or "VISUAL_ONLY"
                    ),
                    "candidate_seed_segments_count": int(
                        event_candidate_payload.get("candidate_seed_segments_count")
                        or 0
                    ),
                    "candidate_seed_audio_analysis_version": str(
                        event_candidate_payload.get(
                            "candidate_seed_audio_analysis_version"
                        )
                        or ""
                    ),
                    "candidate_seed_audio_analysis_fingerprint": str(
                        event_candidate_payload.get(
                            "candidate_seed_audio_analysis_fingerprint"
                        )
                        or ""
                    ),
                    "candidate_seed_vad_has_speech": event_candidate_payload.get(
                        "candidate_seed_vad_has_speech"
                    ),
                    "visual_trigger_count": int(
                        event_candidate_payload.get("visual_trigger_count") or 0
                    ),
                    "reason_counts": dict(
                        event_candidate_payload.get("reason_counts") or {}
                    ),
                }
            )
        if self._event_scan:
            temporal_rows: list[dict[str, Any]] = []
            coverage_by_id = {
                str(row.get("text_id") or ""): dict(row)
                for row in list(coverage_payload.get("tracks") or [])
                if isinstance(row, Mapping) and str(row.get("text_id") or "")
            }
            for row in timeline:
                hit_frames = sorted(
                    {int(value) for value in list(row.get("hit_frames") or [])}
                )
                evidence_frames = []
                if hit_frames:
                    evidence_frames = list(
                        dict.fromkeys(
                            (
                                hit_frames[0],
                                hit_frames[len(hit_frames) // 2],
                                int(row.get("best_frame_index") or hit_frames[0]),
                                hit_frames[-1],
                            )
                        )
                    )
                crop_path = dest / str(row.get("crop_path") or "")
                temporal_rows.append(
                    {
                        "text_id": str(row.get("text_id") or ""),
                        "start_frame": int(row.get("start_frame") or 0),
                        "end_frame": int(row.get("end_frame") or 0),
                        "temporal_support": len(hit_frames),
                        "evidence_frames": evidence_frames,
                        "geometry_dispersion": dict(
                            dict(row.get("boundary_evidence") or {}).get(
                                "geometry_dispersion"
                            )
                            or {}
                        ),
                        "content_signature": (
                            hashlib.sha256(crop_path.read_bytes()).hexdigest()
                            if crop_path.is_file()
                            else None
                        ),
                        "visual_provenance": dict(
                            row.get("visual_provenance") or {}
                        ),
                        "coverage_authority": coverage_by_id.get(
                            str(row.get("text_id") or ""), {}
                        ),
                    }
                )
            temporal_payload = {
                "schema_version": "phase1_temporal_consensus_v1",
                "engine_version": EVENT_SCAN_ENGINE_VERSION,
                "master_timeline_ref": {
                    "path": timeline_path.name,
                    "sha256": timeline_sha256,
                },
                "tracks": temporal_rows,
            }
            (dest / "phase1_temporal_consensus_v1.json").write_text(
                json.dumps(temporal_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            event_timeline = {
                "schema_version": "phase1_event_timeline_v25",
                "engine_version": EVENT_SCAN_ENGINE_VERSION,
                "master_timeline_ref": {
                    "path": timeline_path.name,
                    "sha256": timeline_sha256,
                },
                "tracks": timeline,
                "coverage_ref": {
                    "path": coverage_path.name,
                    "sha256": hashlib.sha256(coverage_path.read_bytes()).hexdigest(),
                    "schema_version": COVERAGE_TRACK_SCHEMA_VERSION,
                },
            }
            (dest / "phase1_event_timeline_v25.json").write_text(
                json.dumps(event_timeline, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            provenance_v3 = {
                **provenance_payload,
                "schema_version": "phase1_provenance_v3",
                "engine_version": EVENT_SCAN_ENGINE_VERSION,
                "allowed_classifications": [
                    "EDITOR_OVERLAY",
                    "SOURCE_INTRINSIC",
                    "SOURCE_INTRINSIC_PANEL",
                    "PLATFORM_UI",
                    "UNKNOWN",
                ],
                "fail_closed": True,
            }
            (dest / "phase1_provenance_v3.json").write_text(
                json.dumps(provenance_v3, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (dest / "phase1_event_metrics.json").write_text(
                json.dumps(analysis_metrics, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        _postprocess_progress("qa_artifacts")
        summary = write_phase1_qa_artifacts(
            qa_dir=qa_dir,
            timeline=timeline,
            dropped=dropped,
            frame_count=frame_count,
            frame_width=source_width,
            frame_height=source_height,
            frames_dir=frames_dir,
            frame_cache=frame_cache,
            source=source,
            geometry_rejected=geometry_rejected,
            coarse_hits=len(coarse_hits),
            phase_hits=len(phase_hits),
            dense_extra_frames=len(dense_needed),
            total_hits=len(hits),
            finalize_audit=finalize_audit,
            text_coverage=coverage,
            effective_step=self._step,
            effective_pad=self._pad,
            lightweight=self._event_scan,
        )
        _postprocess_progress("complete")
        logger.info(
            "master_phase1_done tracks=%s suspects=%s finalize=%s sampled_hits=%s "
            "frames=%s out=%s",
            len(timeline),
            len(dropped),
            {
                "before": finalize_audit.get("before_count"),
                "after": finalize_audit.get("after_count"),
                "chrome": finalize_audit.get("purged_chrome"),
                "shrunk": len(list(finalize_audit.get("shrunk") or [])),
            },
            len(hits),
            frame_count,
            timeline_path,
        )
        logger.info("master_phase1_qa %s", summary)
        result = MasterPhase1Result(
            timeline=timeline,
            fps=fps,
            frame_count=frame_count,
            frame_width=source_width,
            frame_height=source_height,
            timeline_path=timeline_path,
            frames_dir=frames_dir,
            qa_dir=qa_dir,
            analysis_engine=self._analysis_engine,
            analysis_metrics=analysis_metrics,
        )
        frame_cache.close()
        checkpoint_path.unlink(missing_ok=True)
        return result


def _read_frame(video_path: Path, frame_index: int) -> np.ndarray | None:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        return frame
    finally:
        cap.release()


def otsu_binarize_with_border(
    image_bgr: np.ndarray,
    *,
    border_px: int = 10,
    invert: bool = False,
) -> np.ndarray:
    """
    Grayscale → Otsu binary → solid border pad (Phase 2 OCR prep).

    ``invert=True`` flips ink/paper for dual-polarity OCR.
    """
    if image_bgr is None or getattr(image_bgr, "size", 0) == 0:
        raise ValueError("empty image for Otsu prep")
    if image_bgr.ndim == 2:
        gray = image_bgr
    else:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    _t, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    del _t
    if invert:
        binary = cv2.bitwise_not(binary)
    border = max(0, int(border_px))
    ink = int(np.count_nonzero(binary == 0))
    paper = int(np.count_nonzero(binary == 255))
    border_val = 255 if ink > paper else 0
    padded = cv2.copyMakeBorder(
        binary,
        border,
        border,
        border,
        border,
        cv2.BORDER_CONSTANT,
        value=int(border_val),
    )
    return cv2.cvtColor(padded, cv2.COLOR_GRAY2BGR)


def otsu_polarity_variants(
    image_bgr: np.ndarray,
    *,
    border_px: int = 10,
) -> list[tuple[str, np.ndarray]]:
    """Return ``(otsu, img)`` and ``(otsu_inv, img)`` for dual-polarity OCR."""
    return [
        ("otsu", otsu_binarize_with_border(image_bgr, border_px=border_px, invert=False)),
        (
            "otsu_inv",
            otsu_binarize_with_border(image_bgr, border_px=border_px, invert=True),
        ),
    ]


# Wide thin hardsub crops (ink-extended bottom lines) destroy Otsu and confuse
# Paddle at ~40px height / aspect ≫ 10. Upscale + vertical pad recovers OCR.
_WIDE_THIN_MIN_H = 48
_WIDE_THIN_MIN_ASPECT = 12.0
_WIDE_THIN_TARGET_H = 64
_WIDE_THIN_VPAD = 24
_WIDE_THIN_HPAD = 16


def is_wide_thin_ocr_crop(
    image_bgr: np.ndarray,
    *,
    min_h: int = _WIDE_THIN_MIN_H,
    min_aspect: float = _WIDE_THIN_MIN_ASPECT,
) -> bool:
    """True when crop is short *and* extreme aspect (ink-extended hardsub)."""
    if image_bgr is None or getattr(image_bgr, "size", 0) == 0:
        return False
    h = int(image_bgr.shape[0])
    w = int(image_bgr.shape[1])
    if h <= 0:
        return False
    aspect = float(w) / float(h)
    return h < int(min_h) and aspect >= float(min_aspect)


def upscale_pad_ocr_crop(
    image_bgr: np.ndarray,
    *,
    target_h: int = _WIDE_THIN_TARGET_H,
    vpad: int = _WIDE_THIN_VPAD,
    hpad: int = _WIDE_THIN_HPAD,
    border_bgr: tuple[int, int, int] = (0, 0, 0),
) -> np.ndarray:
    """Upscale short crops to ``target_h`` then constant-border pad."""
    if image_bgr is None or getattr(image_bgr, "size", 0) == 0:
        raise ValueError("empty image for upscale-pad OCR prep")
    out = image_bgr
    h = int(out.shape[0])
    w = int(out.shape[1])
    th = max(1, int(target_h))
    if h < th:
        scale = float(th) / float(h)
        out = cv2.resize(
            out,
            (max(1, int(round(w * scale))), th),
            interpolation=cv2.INTER_CUBIC,
        )
    vp = max(0, int(vpad))
    hp = max(0, int(hpad))
    return cv2.copyMakeBorder(
        out,
        vp,
        vp,
        hp,
        hp,
        cv2.BORDER_CONSTANT,
        value=tuple(int(v) for v in border_bgr),
    )


def normalize_pad_ocr_crop(
    image_bgr: np.ndarray,
    *,
    target_h: int = _WIDE_THIN_TARGET_H,
    vpad: int = _WIDE_THIN_VPAD,
    hpad: int = _WIDE_THIN_HPAD,
    border_bgr: tuple[int, int, int] = (0, 0, 0),
) -> np.ndarray:
    """Normalize stylized fallback text to recognizer height, then pad."""
    if image_bgr is None or getattr(image_bgr, "size", 0) == 0:
        raise ValueError("empty image for normalized OCR prep")
    h = int(image_bgr.shape[0])
    w = int(image_bgr.shape[1])
    th = max(1, int(target_h))
    scale = float(th) / max(1.0, float(h))
    interpolation = cv2.INTER_AREA if h > th else cv2.INTER_CUBIC
    resized = cv2.resize(
        image_bgr,
        (max(1, int(round(w * scale))), th),
        interpolation=interpolation,
    )
    return cv2.copyMakeBorder(
        resized,
        max(0, int(vpad)),
        max(0, int(vpad)),
        max(0, int(hpad)),
        max(0, int(hpad)),
        cv2.BORDER_CONSTANT,
        value=tuple(int(v) for v in border_bgr),
    )


def phase2_ocr_prep_variants(
    image_bgr: np.ndarray,
    *,
    border_px: int = 10,
) -> list[tuple[str, np.ndarray]]:
    """
    Phase-2 OCR input variants.

    Wide-thin hardsubs: raw upscale+pad (black and white borders) — skip Otsu.
    Otherwise: dual-polarity Otsu (existing path).
    """
    if is_wide_thin_ocr_crop(image_bgr):
        return [
            (
                "raw_up_vpad",
                upscale_pad_ocr_crop(
                    image_bgr,
                    target_h=_WIDE_THIN_TARGET_H,
                    vpad=_WIDE_THIN_VPAD,
                    hpad=_WIDE_THIN_HPAD,
                    border_bgr=(0, 0, 0),
                ),
            ),
            (
                "raw_up_wpad",
                upscale_pad_ocr_crop(
                    image_bgr,
                    target_h=_WIDE_THIN_TARGET_H,
                    vpad=_WIDE_THIN_VPAD,
                    hpad=_WIDE_THIN_HPAD,
                    border_bgr=(255, 255, 255),
                ),
            ),
        ]
    return otsu_polarity_variants(image_bgr, border_px=border_px)


def phase2_ocr_fallback_variants(
    image_bgr: np.ndarray,
    *,
    border_px: int = 10,
) -> list[tuple[str, np.ndarray]]:
    """Add raw-border variants only after the normal Phase-2 OCR pass fails."""
    primary = phase2_ocr_prep_variants(image_bgr, border_px=border_px)
    if is_wide_thin_ocr_crop(image_bgr):
        return primary
    return [
        *primary,
        (
            "raw_bpad",
            normalize_pad_ocr_crop(
                image_bgr,
                target_h=_WIDE_THIN_TARGET_H,
                vpad=_WIDE_THIN_VPAD,
                hpad=_WIDE_THIN_HPAD,
                border_bgr=(0, 0, 0),
            ),
        ),
        (
            "raw_wpad",
            normalize_pad_ocr_crop(
                image_bgr,
                target_h=_WIDE_THIN_TARGET_H,
                vpad=_WIDE_THIN_VPAD,
                hpad=_WIDE_THIN_HPAD,
                border_bgr=(255, 255, 255),
            ),
        ),
    ]


def encode_ocr_jpeg(image_bgr: np.ndarray, *, quality: int = 95) -> bytes:
    ok, buf = cv2.imencode(
        ".jpg",
        image_bgr,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
    )
    if not ok:
        raise RuntimeError("Failed to encode OCR JPEG")
    return bytes(buf)


def _cjk_count(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def classify_ocr_box_role(
    xyxy: Sequence[float],
    *,
    frame_w: int = 1920,
    frame_h: int = 1080,
) -> str:
    """Heuristic role for role-aware OCR accept rules."""
    x0, y0, x1, y1 = (float(v) for v in xyxy[:4])
    w = max(1.0, x1 - x0)
    h = max(1.0, y1 - y0)
    fh = max(1.0, float(frame_h))
    fw = max(1.0, float(frame_w))
    cy = ((y0 + y1) * 0.5) / fh
    aspect = w / h
    if cy >= HARDSUB_ROLE_CY and (
        aspect >= HARDSUB_MIN_ASPECT or w >= HARDSUB_MIN_W_FRAC * fw
    ):
        return "hardsub"
    # Compact near-square list names (虾) sit just above cy 0.55 mid cutoff —
    # treat as ui_chip so peer rescue + single-CJK gates apply.
    h_frac = h / fh
    if (
        0.45 <= cy <= 0.70
        and aspect <= 1.5
        and (w / fw) < 0.08
        and h_frac <= 0.06
    ):
        return "ui_chip"
    if cy <= 0.55 and aspect < 10.0 and w < 0.45 * fw:
        return "mid_label"
    # Endcard row chips (花生油 / 72千卡) can be aspect ~5 in the lower UI.
    if aspect < 6.0 and w < 0.30 * fw:
        return "ui_chip"
    return "generic"


def accept_ocr_text_for_role(text: str, *, role: str) -> str | None:
    """Drop polarity/OCR noise that is implausible for the box role."""
    raw = str(text or "").strip()
    if not raw:
        return None
    cjk = _cjk_count(raw)
    ascii_letters = sum(1 for ch in raw if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    digits = sum(1 for ch in raw if ch.isdigit())

    if role == "mid_label":
        if len(raw) == 1 and ascii_letters == 1:
            return None
        if len(raw) <= 2 and digits == len(raw):
            return None
        if cjk >= 1 and len(raw) <= 8:
            return raw
        if cjk >= 2:
            return raw
        return None

    if role == "hardsub":
        if len(raw) == 1 and (ascii_letters == 1 or digits == 1):
            return None
        if cjk >= 2:
            return raw
        if cjk >= 1 and len(raw) >= 3:
            return raw
        return None

    if role == "ui_chip":
        if cjk >= 1 or digits >= 1:
            if len(raw) == 1 and ascii_letters == 1:
                return None
            return raw
        return None

    # generic
    if len(raw) == 1 and ascii_letters == 1:
        return None
    if cjk >= 1 or digits >= 2 or len(raw) >= 2:
        return raw
    return None


def pick_best_ocr_text(candidates: Sequence[str]) -> str | None:
    """Prefer more CJK, then longer meaningful strings."""
    best: str | None = None
    best_key: tuple[int, int] = (-1, -1)
    for raw in candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        key = (_cjk_count(text), len(text))
        if key > best_key:
            best_key = key
            best = text
    return best


def is_ocr_suspect_mixed(text: str) -> bool:
    """Caption glued with calorie/UI digits → keep text but flag for review."""
    raw = str(text or "")
    return _cjk_count(raw) >= 4 and sum(1 for ch in raw if ch.isdigit()) >= 3


def load_phase2_crop_bgr(
    entry: Mapping[str, Any],
    *,
    root_dir: Path,
    frame_width: int | None = None,
    frame_height: int | None = None,
) -> np.ndarray | None:
    """
    Prefer Phase-1 ``crop_path``; never re-run ``prepare_recognition_crop``.

    If crop missing, fall back to a raw (unpadded) slice from the keyframe.
    """
    probe = entry.get("ocr_probe_geometry")
    key_rel = str(entry.get("best_keyframe_path") or "").strip()
    if (
        isinstance(probe, Mapping)
        and key_rel
        and frame_width is not None
        and frame_height is not None
    ):
        try:
            probe_box = [
                float(probe["x"]) * int(frame_width),
                float(probe["y"]) * int(frame_height),
                (float(probe["x"]) + float(probe["width"])) * int(frame_width),
                (float(probe["y"]) + float(probe["height"])) * int(frame_height),
            ]
        except (KeyError, TypeError, ValueError):
            probe_box = []
        key_path = root_dir / key_rel
        if len(probe_box) == 4 and key_path.is_file():
            frame = cv2.imread(str(key_path))
            if frame is not None:
                cropped = _crop_xyxy_from_frame(frame, probe_box)
                if cropped is not None and cropped.size > 0:
                    return cropped

    crop_rel = str(entry.get("crop_path") or "").strip()
    if crop_rel:
        crop_path = root_dir / crop_rel
        if crop_path.is_file():
            img = cv2.imread(str(crop_path))
            if img is not None and img.size > 0:
                return img

    coords = list(entry.get("box_coords") or [])
    if not key_rel or len(coords) < 4:
        return None
    key_path = root_dir / key_rel
    if not key_path.is_file():
        return None
    frame = cv2.imread(str(key_path))
    if frame is None:
        return None
    return _crop_xyxy_from_frame(frame, coords)


def _crop_xyxy_from_frame(
    frame_bgr: np.ndarray,
    xyxy: Sequence[float],
) -> np.ndarray | None:
    h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
    x0 = max(0, min(w - 1, int(round(float(xyxy[0])))))
    y0 = max(0, min(h - 1, int(round(float(xyxy[1])))))
    x1 = max(x0 + 1, min(w, int(round(float(xyxy[2])))))
    y1 = max(y0 + 1, min(h, int(round(float(xyxy[3])))))
    crop = frame_bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    return crop


def _dump_ocr_input(
    dump_dir: Path,
    *,
    text_id: str,
    tag: str,
    image_bgr: np.ndarray,
) -> None:
    dump_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tag)
    path = dump_dir / f"{text_id}_{safe}.jpg"
    cv2.imwrite(str(path), image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])


class OcrRecognitionCache:
    """Small namespaced cache keyed by exact prepared-JPEG SHA-256."""

    def __init__(self, path: str | Path, *, namespace: str) -> None:
        self.path = Path(path)
        self.namespace = str(namespace)
        self._dirty = False
        self._payload: dict[str, Any] = {
            "schema_version": "phase2_ocr_cache_v1",
            "namespaces": {},
        }
        if self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(
                    loaded.get("namespaces"), dict
                ):
                    self._payload = loaded
            except (OSError, ValueError, TypeError):
                logger.warning("phase2_ocr_cache_invalid path=%s", self.path.name)
        namespaces = self._payload.setdefault("namespaces", {})
        namespaces.setdefault(self.namespace, {})

    @staticmethod
    def _key(content: bytes) -> str:
        return hashlib.sha256(bytes(content)).hexdigest()

    def get(self, content: bytes) -> str | None:
        _found, text = self.lookup(content)
        return text

    def lookup(self, content: bytes) -> tuple[bool, str | None]:
        namespace = self._payload["namespaces"].get(self.namespace) or {}
        key = self._key(content)
        if key not in namespace:
            return False, None
        value = namespace.get(key)
        if value is None:
            return True, None
        text = str(value or "").strip()
        return True, text or None

    def set(self, content: bytes, text: str | None) -> None:
        value = str(text or "").strip()
        namespace = self._payload["namespaces"].setdefault(self.namespace, {})
        namespace[self._key(content)] = value or None
        self._dirty = True

    def flush(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(self._payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.path)
        self._dirty = False


def _recognize_batch_sync(
    items: Sequence[Mapping[str, Any]],
    *,
    endpoint_url: str | None = None,
    cache: OcrRecognitionCache | None = None,
) -> list[str | None]:
    """
    One CloudOCRAnalyzer session for many prepared JPEGs.

    Each item: ``prepared_jpeg``, ``original_box_coords`` (or ``box_xyxy``).
    """
    if not items:
        return []
    try:
        from src.media_pipeline.ocr_filtering.analyze_ocr import (
            CloudOCRAnalyzer,
            format_timestamp_key,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("master_phase1_ocr_import_failed err=%s", exc)
        return [None] * len(items)

    out: list[str | None] = [None] * len(items)
    pending_items: list[Mapping[str, Any]] = []
    pending_indices: list[int] = []
    for original_index, item in enumerate(items):
        content = bytes(item["prepared_jpeg"])
        found, cached = cache.lookup(content) if cache is not None else (False, None)
        if found:
            out[original_index] = cached
        else:
            pending_indices.append(original_index)
            pending_items.append(item)
    if not pending_items:
        return out

    payload: list[dict[str, Any]] = []
    for i, item in enumerate(pending_items):
        coords = list(item.get("original_box_coords") or item.get("box_xyxy") or [])
        payload.append(
            {
                "timestamp": float(i),
                "original_box_coords": [float(v) for v in coords[:4]],
                "prepared_jpeg": bytes(item["prepared_jpeg"]),
                "image_crop": np.zeros((8, 8, 3), dtype=np.uint8),
            }
        )
    try:
        analyzer = CloudOCRAnalyzer(endpoint_url=endpoint_url)
        grouped = analyzer.analyze_sync(payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("master_phase1_ocr_batch_failed err=%s", exc)
        return out

    for i, original_index in enumerate(pending_indices):
        key = format_timestamp_key(float(i))
        text: str | None = None
        for hit in grouped.get(key) or []:
            cand = str(hit.get("text") or "").strip()
            if cand:
                text = cand
                break
        out[original_index] = text
        if cache is not None:
            cache.set(bytes(items[original_index]["prepared_jpeg"]), text)
    if cache is not None:
        cache.flush()
    return out


def _ocr_crop_dual_polarity(
    crop_bgr: np.ndarray,
    *,
    box_xyxy: Sequence[float],
    role: str,
    dump_dir: Path | None,
    text_id: str,
    pass_tag: str,
    endpoint_url: str | None = None,
    cache: OcrRecognitionCache | None = None,
) -> str | None:
    """Phase-2 prep variants → batch OCR → role filter → best candidate."""
    variants = phase2_ocr_fallback_variants(crop_bgr, border_px=10)
    batch: list[dict[str, Any]] = []
    for name, img in variants:
        if dump_dir is not None:
            _dump_ocr_input(
                dump_dir, text_id=text_id, tag=f"{pass_tag}_{name}", image_bgr=img
            )
        batch.append(
            {
                "prepared_jpeg": encode_ocr_jpeg(img),
                "original_box_coords": [float(v) for v in box_xyxy[:4]],
            }
        )
    if endpoint_url is None and cache is None:
        raw_texts = _recognize_batch_sync(batch)
    else:
        raw_texts = _recognize_batch_sync(
            batch,
            endpoint_url=endpoint_url,
            cache=cache,
        )
    accepted: list[str] = []
    for raw in raw_texts:
        kept = accept_ocr_text_for_role(str(raw or ""), role=role)
        if kept:
            accepted.append(kept)
    return pick_best_ocr_text(accepted)


def _recover_failed_ocr_tracks(
    timeline: list[dict[str, Any]],
    *,
    source: Path | None,
    boxes: Sequence[Sequence[float]],
    roles: Sequence[str],
    dump_dir: Path,
    endpoint_url: str | None,
    cache: OcrRecognitionCache | None,
) -> None:
    """Run one bounded local batch over only tracks missed by primary OCR."""
    from src.media_pipeline.frame_sampling.phase2_local_recovery import (
        PHASE2_HARDSUB_GEOMETRY_POLICY_VERSION,
        PHASE2_LOCAL_RECOVERY_POLICY_VERSION,
        RecoveryObservation,
        choose_recovery_consensus,
        crop_recovery_region,
        decode_selected_frames,
        hardsub_geometry_candidates,
        recovery_frame_indices,
        recovery_sharpness,
        recovery_variants,
    )

    failed = [
        index
        for index, entry in enumerate(timeline)
        if str(entry.get("ocr_source") or "") == "failed" and boxes[index]
    ]
    if not failed:
        return
    if source is None or not source.is_file():
        for index in failed:
            timeline[index]["ocr_recovery"] = {
                "policy_version": PHASE2_LOCAL_RECOVERY_POLICY_VERSION,
                "status": "SKIPPED_SOURCE_VIDEO_MISSING",
            }
        return

    frames_by_track = {
        index: recovery_frame_indices(timeline[index]) for index in failed
    }
    decoded = decode_selected_frames(
        source,
        [
            frame_index
            for indices in frames_by_track.values()
            for frame_index in indices
        ],
    )

    def _dominant_neighbor_box(index: int) -> tuple[list[float], str] | None:
        """Return a strong overlapping caption geometry for a failed short track."""
        entry = timeline[index]
        try:
            start = int(entry.get("start_frame") or 0)
            end = int(entry.get("end_frame") or start)
        except (TypeError, ValueError):
            return None
        span = max(1, end - start + 1)
        frame_w = max(1.0, float(frame_cache_width or 1))
        frame_h = max(1.0, float(frame_cache_height or 1))
        ranked: list[tuple[tuple[Any, ...], list[float], str]] = []
        for peer_index, peer in enumerate(timeline):
            if peer_index == index:
                continue
            peer_text = str(
                peer.get("ocr_text_raw")
                or peer.get("ocr_text")
                or peer.get("text")
                or ""
            ).strip()
            if not peer_text:
                continue
            try:
                peer_start = int(peer.get("start_frame") or 0)
                peer_end = int(peer.get("end_frame") or peer_start)
            except (TypeError, ValueError):
                continue
            overlap = max(0, min(end, peer_end) - max(start, peer_start) + 1)
            if overlap / float(span) < 0.90 or peer_start > start or peer_end < end:
                continue
            peer_box = list(peer.get("box_coords") or [])
            if len(peer_box) < 4:
                continue
            peer_width = max(1.0, float(peer_box[2]) - float(peer_box[0]))
            peer_height = max(1.0, float(peer_box[3]) - float(peer_box[1]))
            if peer_width / frame_w < 0.35 or peer_height / frame_h > 0.08:
                continue
            ranked.append(
                (
                    (
                        int(peer.get("hit_count") or 0),
                        peer_end - peer_start + 1,
                        round(peer_width / frame_w, 4),
                        round(overlap / float(span), 4),
                    ),
                    [float(value) for value in peer_box[:4]],
                    str(peer.get("text_id") or ""),
                )
            )
        if not ranked:
            return None
        _, box, text_id = max(ranked, key=lambda row: row[0])
        return box, text_id

    # These values are supplied by the caller's source raster contract.  The
    # helper is kept local so recovery remains a bounded, read-only pass.
    frame_cache_width = max(
        [int(frame.shape[1]) for frame in decoded.values() if frame is not None] or [1]
    )
    frame_cache_height = max(
        [int(frame.shape[0]) for frame in decoded.values() if frame is not None] or [1]
    )
    batch: list[dict[str, Any]] = []
    meta: list[
        tuple[int, int, str, float, tuple[float, float, float, float], float]
    ] = []
    geometry_candidate_counts: dict[int, int] = {}
    for index in failed:
        text_id = str(timeline[index].get("text_id") or f"sub_{index + 1:02d}")
        for frame_index in frames_by_track[index]:
            frame = decoded.get(frame_index)
            if frame is None:
                continue
            use_geometry_recovery = str(roles[index] or "") == "hardsub"
            candidates = (
                hardsub_geometry_candidates(frame, boxes[index])
                if use_geometry_recovery
                else []
            )
            # Prefer a dominant neighbouring caption lane when Phase 1's box
            # is a short, contained shadow.  Otherwise retain the immutable
            # Phase-1 geometry and one local derived line as fallbacks.
            neighbour = _dominant_neighbor_box(index)
            if neighbour is not None:
                neighbour_box, neighbour_id = neighbour
                candidate_rows = [
                    {
                        "box_xyxy": neighbour_box,
                        "score": 1.0,
                        "source": "dominant_neighbor",
                        "neighbor_text_id": neighbour_id,
                    }
                ]
            else:
                candidate_rows = [
                    {"box_xyxy": [float(value) for value in boxes[index][:4]], "score": 0.0}
                ]
                # One derived line plus the immutable Phase-1 box keeps the
                # recovery batch within the V25.1 input budget.
                candidate_rows.extend(candidates[:1])
            geometry_candidate_counts[index] = max(
                geometry_candidate_counts.get(index, 0), len(candidate_rows)
            )
            for candidate_row in candidate_rows:
                candidate_box = tuple(
                    float(value) for value in candidate_row["box_xyxy"][:4]
                )
                crop = crop_recovery_region(frame, candidate_box)
                if crop is None:
                    continue
                sharpness = recovery_sharpness(crop)
                variants = recovery_variants(crop)
                selected_variants = variants[:1]
                if (
                    len(frames_by_track[index]) == 1
                    and frame_index == frames_by_track[index][0]
                    and len(variants) >= 3
                ):
                    selected_variants.append(variants[2])
                for variant, prepared in selected_variants:
                    _dump_ocr_input(
                        dump_dir,
                        text_id=text_id,
                        tag=(
                            f"recovery_f{frame_index}_{variant}_"
                            f"y{int(round(candidate_box[1]))}"
                        ),
                        image_bgr=prepared,
                    )
                    batch.append(
                        {
                            "prepared_jpeg": encode_ocr_jpeg(prepared),
                            "original_box_coords": list(candidate_box),
                        }
                    )
                    meta.append(
                        (
                            index,
                            frame_index,
                            variant,
                            sharpness,
                            candidate_box,
                            float(candidate_row.get("score") or 0.0),
                        )
                    )

    if endpoint_url is None and cache is None:
        raw_results = _recognize_batch_sync(batch)
    else:
        raw_results = _recognize_batch_sync(
            batch,
            endpoint_url=endpoint_url,
            cache=cache,
        )
    observations: dict[int, list[RecoveryObservation]] = {}
    for (
        index,
        frame_index,
        variant,
        sharpness,
        candidate_box,
        geometry_score,
    ), raw in zip(meta, raw_results):
        kept = accept_ocr_text_for_role(str(raw or ""), role=roles[index])
        if not kept:
            continue
        observations.setdefault(index, []).append(
            RecoveryObservation(
                track_index=index,
                frame_index=frame_index,
                variant=variant,
                text=kept,
                sharpness=sharpness,
                box_xyxy=candidate_box,
                geometry_score=geometry_score,
            )
        )

    for index in failed:
        entry = timeline[index]
        text_id = str(entry.get("text_id") or f"sub_{index + 1:02d}")
        result = choose_recovery_consensus(observations.get(index) or [])
        audit = {
            "policy_version": PHASE2_LOCAL_RECOVERY_POLICY_VERSION,
            "attempted_frames": frames_by_track[index],
            "decoded_frames": [
                value for value in frames_by_track[index] if value in decoded
            ],
            "prepared_inputs": sum(1 for row in meta if row[0] == index),
            "accepted_observations": len(observations.get(index) or []),
            "geometry_candidates": int(geometry_candidate_counts.get(index, 0)),
            "geometry_policy_version": PHASE2_HARDSUB_GEOMETRY_POLICY_VERSION,
        }
        if result is None:
            entry["ocr_recovery"] = {**audit, "status": "UNRESOLVED"}
            continue
        text = str(result["text"])
        selected_box = result.get("selected_box")
        geometry_applied = bool(
            str(roles[index] or "") == "hardsub"
            and selected_box
            and int(result.get("frame_support") or 0) >= 2
            and int(result.get("geometry_observation_count") or 0) >= 2
        )
        if geometry_applied:
            original_box = list(entry.get("box_coords") or [])[:4]
            entry["box_coords"] = [float(value) for value in selected_box[:4]]
            selected_frame_image = decoded.get(int(result.get("selected_frame") or -1))
            corrected_crop = (
                crop_recovery_region(selected_frame_image, entry["box_coords"])
                if selected_frame_image is not None
                else None
            )
            if corrected_crop is not None:
                geometry_dir = dump_dir.parent / "geometry_recovery"
                geometry_dir.mkdir(parents=True, exist_ok=True)
                corrected_path = geometry_dir / f"{text_id}.jpg"
                cv2.imwrite(
                    str(corrected_path),
                    corrected_crop,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 95],
                )
                entry["crop_path"] = corrected_path.relative_to(
                    dump_dir.parent.parent
                ).as_posix()
            entry["geometry_recovery"] = {
                "policy_version": PHASE2_HARDSUB_GEOMETRY_POLICY_VERSION,
                "status": "LOCAL_DERIVED_TEMPORAL_CONSENSUS",
                "original_box_coords": original_box,
                "derived_box_coords": list(entry["box_coords"]),
                "frame_support": int(result.get("frame_support") or 0),
                "geometry_observation_count": int(
                    result.get("geometry_observation_count") or 0
                ),
                "geometry_support": int(result.get("geometry_support") or 0),
            }
        else:
            entry["geometry_recovery"] = {
                "policy_version": PHASE2_HARDSUB_GEOMETRY_POLICY_VERSION,
                "status": "UNRESOLVED_FAIL_CLOSED",
                "candidate_count": int(geometry_candidate_counts.get(index, 0)),
            }
        entry["ocr_text"] = text
        entry["ocr_source"] = "local_temporal_recovery"
        entry["ocr_frame"] = int(result["selected_frame"])
        entry["ocr_recovery"] = {
            **audit,
            **result,
            "status": "RECOVERED_FOR_OPERATOR_REVIEW",
        }
        if is_ocr_suspect_mixed(text):
            entry["ocr_suspect"] = True
        logger.info(
            "phase2_ocr_track_recovery_ok text_id=%s method=%s support=%s",
            str(entry.get("text_id") or "?"),
            result["method"],
            result["frame_support"],
        )


def ocr_timeline_keyframes(
    timeline: list[dict[str, Any]],
    *,
    root_dir: Path,
    prefer_mock: bool = False,
    video_path: str | Path | None = None,
    frame_width: int = 1920,
    frame_height: int = 1080,
    endpoint_url: str | None = None,
    cache_path: str | Path | None = None,
    cache_namespace: str | None = None,
) -> list[dict[str, Any]]:
    """
    Phase 2: crop-ready prep (Otsu or wide-thin upscale+pad), batched OCR,
    best-frame fallback.

    Writes ``ocr_text`` / ``ocr_source`` / ``ocr_frame``; never mutates geometry.
    Dumps actual OCR inputs under ``qa/ocr_inputs/``.
    """
    dump_dir = Path(root_dir) / "qa" / "ocr_inputs"
    dump_dir.mkdir(parents=True, exist_ok=True)

    if prefer_mock:
        for entry in timeline:
            tid = str(entry.get("text_id") or "")
            mock = f"[mock]{tid}"
            entry["ocr_text"] = mock
            entry["ocr_source"] = "mock"
            logger.info("phase2_ocr_track_ok text_id=%s", tid or "?")
        return timeline

    source = Path(video_path) if video_path else None
    cache = (
        OcrRecognitionCache(cache_path, namespace=str(cache_namespace))
        if cache_path is not None and cache_namespace
        else None
    )

    # ---- Pass 1: batch all track×polarity from Phase-1 crops ----
    pass1_meta: list[tuple[int, str]] = []
    pass1_batch: list[dict[str, Any]] = []
    roles: list[str] = []
    boxes: list[list[float]] = []

    for i, entry in enumerate(timeline):
        coords = list(entry.get("box_coords") or [])
        if len(coords) < 4:
            roles.append("generic")
            boxes.append([])
            continue
        box_xyxy = [float(coords[j]) for j in range(4)]
        entry["box_coords"] = list(box_xyxy)
        ocr_box_xyxy = list(box_xyxy)
        probe = entry.get("ocr_probe_geometry")
        if isinstance(probe, Mapping):
            try:
                candidate_probe = [
                    float(probe["x"]) * frame_width,
                    float(probe["y"]) * frame_height,
                    (float(probe["x"]) + float(probe["width"])) * frame_width,
                    (float(probe["y"]) + float(probe["height"])) * frame_height,
                ]
            except (KeyError, TypeError, ValueError):
                candidate_probe = []
            if (
                len(candidate_probe) == 4
                and candidate_probe[2] > candidate_probe[0]
                and candidate_probe[3] > candidate_probe[1]
            ):
                ocr_box_xyxy = candidate_probe
        boxes.append(ocr_box_xyxy)
        role = classify_ocr_box_role(
            ocr_box_xyxy, frame_w=frame_width, frame_h=frame_height
        )
        roles.append(role)
        text_id = str(entry.get("text_id") or f"sub_{i+1:02d}")
        crop = load_phase2_crop_bgr(
            entry,
            root_dir=root_dir,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        if crop is None:
            continue
        try:
            for name, img in phase2_ocr_prep_variants(crop, border_px=10):
                _dump_ocr_input(
                    dump_dir,
                    text_id=text_id,
                    tag=f"p1_{name}",
                    image_bgr=img,
                )
                pass1_batch.append(
                    {
                        "prepared_jpeg": encode_ocr_jpeg(img),
                        "original_box_coords": ocr_box_xyxy,
                    }
                )
                pass1_meta.append((i, name))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "master_phase1_ocr_prep_failed text_id=%s err=%s", text_id, exc
            )

    if endpoint_url is None and cache is None:
        pass1_raw = _recognize_batch_sync(pass1_batch)
    else:
        pass1_raw = _recognize_batch_sync(
            pass1_batch,
            endpoint_url=endpoint_url,
            cache=cache,
        )
    by_track: dict[int, list[str]] = {}
    for (ti, _pol), raw in zip(pass1_meta, pass1_raw):
        kept = accept_ocr_text_for_role(str(raw or ""), role=roles[ti])
        if kept:
            by_track.setdefault(ti, []).append(kept)

    for i, entry in enumerate(timeline):
        text_id = str(entry.get("text_id") or "?")
        if not boxes[i]:
            entry["ocr_text"] = ""
            entry["ocr_source"] = "none"
            logger.warning("phase2_ocr_track_skip_missing_box text_id=%s", text_id)
            continue

        text = pick_best_ocr_text(by_track.get(i) or [])
        if text:
            entry["ocr_text"] = text
            entry["ocr_source"] = "crop"
            entry["ocr_frame"] = int(
                entry.get("best_frame_index")
                if entry.get("best_frame_index") is not None
                else entry.get("start_frame")
                or 0
            )
            if is_ocr_suspect_mixed(text):
                entry["ocr_suspect"] = True
            logger.info("phase2_ocr_track_ok text_id=%s", text_id)
            continue

        # ---- Fallback: best_frame_index then mid_frame ----
        start = int(entry.get("start_frame") or 0)
        end = int(entry.get("end_frame") or start)
        mid_frame = start + (end - start) // 2
        best_idx = entry.get("best_frame_index")
        try:
            best_frame = int(best_idx) if best_idx is not None else mid_frame
        except (TypeError, ValueError):
            best_frame = mid_frame

        fallback_order: list[tuple[str, int]] = [("best_frame", best_frame)]
        if mid_frame != best_frame:
            fallback_order.append(("mid_frame", mid_frame))

        recovered = False
        if source is not None and source.is_file():
            for source_name, frame_idx in fallback_order:
                frame_bgr = _read_frame(source, frame_idx)
                if frame_bgr is None:
                    continue
                crop = _crop_xyxy_from_frame(frame_bgr, boxes[i])
                if crop is None:
                    continue
                text = _ocr_crop_dual_polarity(
                    crop,
                    box_xyxy=boxes[i],
                    role=roles[i],
                    dump_dir=dump_dir,
                    text_id=text_id,
                    pass_tag=f"p2_{source_name}",
                    endpoint_url=endpoint_url,
                    cache=cache,
                )
                if text:
                    entry["ocr_text"] = text
                    entry["ocr_source"] = source_name
                    entry["ocr_frame"] = int(frame_idx)
                    if is_ocr_suspect_mixed(text):
                        entry["ocr_suspect"] = True
                    recovered = True
                    logger.info(
                        "phase2_ocr_track_fallback_ok text_id=%s source=%s",
                        text_id,
                        source_name,
                    )
                    break

        if recovered:
            continue

        entry["ocr_text"] = ""
        entry["ocr_source"] = "failed"
        logger.warning(
            "phase2_ocr_track_failed_cover_only text_id=%s",
            text_id,
        )

    _recover_failed_ocr_tracks(
        timeline,
        source=source,
        boxes=boxes,
        roles=roles,
        dump_dir=dump_dir,
        endpoint_url=endpoint_url,
        cache=cache,
    )
    return timeline


def _recognize_prepared_jpeg_sync(
    jpeg: bytes,
    *,
    box_xyxy: Sequence[float],
) -> str | None:
    """Backward-compatible single-JPEG helper (tests / scripts)."""
    texts = _recognize_batch_sync(
        [{"prepared_jpeg": jpeg, "original_box_coords": list(box_xyxy)[:4]}]
    )
    return texts[0] if texts else None
