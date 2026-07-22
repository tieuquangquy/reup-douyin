"""Glyph-change sampling and resumable cache for production OCR.

The local mask decides *when* text changed. Cloud OCR is only used for one
stable keyframe per caption state. OCR results are persisted after small
batches so interrupted jobs can resume without paying for completed crops.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from src.media_pipeline.ocr_filtering.async_batch import process_all_frames_sync
from src.media_pipeline.ocr_filtering.types import (
    DetectedTextBox,
    FrameOcrDetection,
    Vertex,
)

logger = logging.getLogger(__name__)

DEFAULT_GLYPH_BAND_TOP = 0.82
DEFAULT_GLYPH_FRAME_STRIDE = 2
DEFAULT_GLYPH_CHANGE_THRESHOLD = 0.42
DEFAULT_STABLE_CONFIRMATIONS = 2
DEFAULT_GLYPH_MIN_GAP_MS = 250
DEFAULT_CACHE_BATCH_SIZE = 8
_CACHE_VERSION = 1


@dataclass(frozen=True)
class GlyphKeyframe:
    frame_index: int
    time_ms: int


@dataclass(frozen=True)
class GlyphSample:
    frame_index: int
    time_ms: int
    mask: np.ndarray
    quality: float


@dataclass(frozen=True)
class GlyphSegment:
    segment_id: int
    start_ms: int
    end_ms: int
    candidate_times_ms: tuple[int, ...]
    has_glyph: bool = True


def subtitle_glyph_mask(
    frame_bgr: np.ndarray,
    *,
    y0_norm: float = DEFAULT_GLYPH_BAND_TOP,
    output_size: tuple[int, int] = (160, 48),
) -> np.ndarray:
    """Return a compact mask of low-chroma bright subtitle glyph components."""
    if frame_bgr is None or frame_bgr.size == 0:
        return np.zeros((output_size[1], output_size[0]), dtype=np.uint8)
    h, w = frame_bgr.shape[:2]
    top = max(0, min(h - 1, int(round(h * max(0.0, min(0.95, y0_norm))))))
    roi = frame_bgr[top:h, :]
    if roi.size == 0:
        return np.zeros((output_size[1], output_size[0]), dtype=np.uint8)

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    # Douyin hardsubs are predominantly white/near-white with dark outlines.
    candidate = ((value >= 185) & (saturation <= 75) & (gray >= 180)).astype(np.uint8) * 255
    candidate = cv2.morphologyEx(
        candidate,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)),
    )

    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(candidate, 8)
    kept = np.zeros_like(candidate)
    roi_area = max(1, roi.shape[0] * roi.shape[1])
    min_area = max(3, int(round(roi_area * 0.00005)))
    max_area = max(min_area, int(round(roi_area * 0.08)))
    min_h = max(2, int(round(roi.shape[0] * 0.05)))
    for label in range(1, count):
        x, y, bw, bh, area = (int(v) for v in stats[label])
        del x, y
        if area < min_area or area > max_area or bh < min_h:
            continue
        aspect = float(bw) / float(max(1, bh))
        if aspect > 12.0 and bh < int(round(roi.shape[0] * 0.35)):
            continue
        kept[labels == label] = 255

    return cv2.resize(kept, output_size, interpolation=cv2.INTER_NEAREST)


def glyph_mask_change_score(a: np.ndarray, b: np.ndarray) -> float:
    """Return 0 for equivalent masks and approach 1 for different glyph layouts."""
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_NEAREST)
    aa = (a > 0).astype(np.uint8)
    bb = (b > 0).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    # A one-pixel tolerance prevents compression jitter from creating OCR ticks.
    aa_d = cv2.dilate(aa, kernel, iterations=1)
    bb_d = cv2.dilate(bb, kernel, iterations=1)
    intersection = int(np.count_nonzero((aa > 0) & (bb_d > 0))) + int(
        np.count_nonzero((bb > 0) & (aa_d > 0))
    )
    total = int(np.count_nonzero(aa)) + int(np.count_nonzero(bb))
    if total == 0:
        return 0.0
    similarity = min(1.0, float(intersection) / float(total))
    return 1.0 - similarity


def select_stable_glyph_keyframes(
    samples: Sequence[tuple[int, int, np.ndarray]],
    *,
    change_threshold: float = DEFAULT_GLYPH_CHANGE_THRESHOLD,
    stable_confirmations: int = DEFAULT_STABLE_CONFIRMATIONS,
    min_gap_ms: int = DEFAULT_GLYPH_MIN_GAP_MS,
) -> list[GlyphKeyframe]:
    """Choose one confirmed stable sample for each distinct glyph-mask state."""
    if not samples:
        return []
    confirmations = max(1, int(stable_confirmations))
    gap_ms = max(0, int(min_gap_ms))
    threshold = max(0.01, min(1.0, float(change_threshold)))

    accepted_mask: np.ndarray | None = None
    pending_mask: np.ndarray | None = None
    pending_count = 0
    keys: list[GlyphKeyframe] = []

    for frame_index, time_ms, mask in samples:
        if accepted_mask is not None and glyph_mask_change_score(accepted_mask, mask) < threshold:
            pending_mask = None
            pending_count = 0
            continue

        if pending_mask is None or glyph_mask_change_score(pending_mask, mask) >= threshold:
            pending_mask = mask.copy()
            pending_count = 1
        else:
            pending_count += 1

        if pending_count < confirmations:
            continue
        if keys and int(time_ms) - keys[-1].time_ms < gap_ms:
            continue

        accepted_mask = mask.copy()
        keys.append(GlyphKeyframe(frame_index=int(frame_index), time_ms=int(time_ms)))
        pending_mask = None
        pending_count = 0

    if not keys:
        frame_index, time_ms, _mask = samples[0]
        keys.append(GlyphKeyframe(frame_index=int(frame_index), time_ms=int(time_ms)))
    return keys


def build_glyph_segments(
    samples: Sequence[GlyphSample],
    *,
    duration_ms: int,
    change_threshold: float = DEFAULT_GLYPH_CHANGE_THRESHOLD,
    stable_confirmations: int = DEFAULT_STABLE_CONFIRMATIONS,
    min_gap_ms: int = DEFAULT_GLYPH_MIN_GAP_MS,
    max_candidates: int = 3,
) -> list[GlyphSegment]:
    """Convert confirmed glyph states into segments with ranked OCR candidates."""
    if not samples:
        return []
    tuples = [(sample.frame_index, sample.time_ms, sample.mask) for sample in samples]
    keys = select_stable_glyph_keyframes(
        tuples,
        change_threshold=change_threshold,
        stable_confirmations=stable_confirmations,
        min_gap_ms=min_gap_ms,
    )
    by_frame = {sample.frame_index: sample for sample in samples}
    count = max(1, int(max_candidates))
    segments: list[GlyphSegment] = []
    for i, key in enumerate(keys):
        start_ms = 0
        if i > 0:
            start_ms = (int(keys[i - 1].time_ms) + int(key.time_ms)) // 2
        end_ms = int(duration_ms) + 1
        if i + 1 < len(keys):
            end_ms = (int(key.time_ms) + int(keys[i + 1].time_ms)) // 2

        reference = by_frame.get(key.frame_index)
        candidates = [
            sample
            for sample in samples
            if start_ms <= int(sample.time_ms) < end_ms
            and (
                reference is None
                or glyph_mask_change_score(reference.mask, sample.mask) < change_threshold
            )
        ]
        if not candidates and reference is not None:
            candidates = [reference]
        ranked = sorted(
            candidates,
            key=lambda sample: (
                float(sample.quality),
                -abs(int(sample.time_ms) - int(key.time_ms)),
            ),
            reverse=True,
        )
        segments.append(
            GlyphSegment(
                segment_id=i,
                start_ms=start_ms,
                end_ms=end_ms,
                candidate_times_ms=tuple(
                    int(sample.time_ms) for sample in ranked[:count]
                ),
                has_glyph=bool(
                    reference is not None
                    and int(np.count_nonzero(reference.mask)) >= 3
                ),
            )
        )
    return segments


def _glyph_sample_quality(
    frame_bgr: np.ndarray,
    mask: np.ndarray,
    *,
    y0_norm: float,
) -> float:
    h = int(frame_bgr.shape[0])
    top = max(0, min(h - 1, int(round(h * y0_norm))))
    gray = cv2.cvtColor(frame_bgr[top:h, :], cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var()) if gray.size else 0.0
    occupancy = float(np.count_nonzero(mask)) / float(max(1, mask.size))
    occupancy_score = min(1.0, occupancy / 0.03)
    if occupancy > 0.35:
        occupancy_score *= max(0.0, 1.0 - (occupancy - 0.35) * 2.0)
    return occupancy_score + min(1.0, sharpness / 600.0)


def sample_subtitle_glyph_segments(
    video_path: str | Path,
    *,
    y0_norm: float = DEFAULT_GLYPH_BAND_TOP,
    frame_stride: int = DEFAULT_GLYPH_FRAME_STRIDE,
    change_threshold: float = DEFAULT_GLYPH_CHANGE_THRESHOLD,
    stable_confirmations: int = DEFAULT_STABLE_CONFIRMATIONS,
    min_gap_ms: int = DEFAULT_GLYPH_MIN_GAP_MS,
    max_candidates: int = 3,
) -> list[GlyphSegment]:
    """Build caption states first, then rank up to N Cloud OCR candidates/state."""
    path = Path(video_path)
    stride = max(1, int(frame_stride))
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    samples: list[GlyphSample] = []
    duration_ms = 0
    frame_index = 0
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
        while True:
            ok, bgr = cap.read()
            if not ok or bgr is None:
                break
            time_ms = int(round(frame_index * 1000.0 / fps))
            duration_ms = time_ms
            if frame_index % stride == 0:
                mask = subtitle_glyph_mask(bgr, y0_norm=y0_norm)
                samples.append(
                    GlyphSample(
                        frame_index=frame_index,
                        time_ms=time_ms,
                        mask=mask,
                        quality=_glyph_sample_quality(
                            bgr,
                            mask,
                            y0_norm=y0_norm,
                        ),
                    )
                )
            frame_index += 1
    finally:
        cap.release()

    segments = build_glyph_segments(
        samples,
        duration_ms=duration_ms,
        change_threshold=change_threshold,
        stable_confirmations=stable_confirmations,
        min_gap_ms=min_gap_ms,
        max_candidates=max_candidates,
    )
    logger.info(
        "glyph_segments video=%s frames=%s samples=%s segments=%s candidates=%s",
        path.name,
        frame_index,
        len(samples),
        len(segments),
        sum(len(segment.candidate_times_ms) for segment in segments),
    )
    return segments


def sample_subtitle_glyph_change_times_ms(
    video_path: str | Path,
    *,
    y0_norm: float = DEFAULT_GLYPH_BAND_TOP,
    frame_stride: int = DEFAULT_GLYPH_FRAME_STRIDE,
    change_threshold: float = DEFAULT_GLYPH_CHANGE_THRESHOLD,
    stable_confirmations: int = DEFAULT_STABLE_CONFIRMATIONS,
    min_gap_ms: int = DEFAULT_GLYPH_MIN_GAP_MS,
) -> list[int]:
    """Scan locally and return stable caption-state keyframe timestamps."""
    segments = sample_subtitle_glyph_segments(
        video_path,
        y0_norm=y0_norm,
        frame_stride=frame_stride,
        change_threshold=change_threshold,
        stable_confirmations=stable_confirmations,
        min_gap_ms=min_gap_ms,
        max_candidates=1,
    )
    return [
        segment.candidate_times_ms[0]
        for segment in segments
        if segment.candidate_times_ms
    ]


def _box_to_payload(box: DetectedTextBox) -> dict[str, Any]:
    return {
        "x": float(box.x),
        "y": float(box.y),
        "width": float(box.width),
        "height": float(box.height),
        "text": str(box.text or ""),
        "confidence": float(box.confidence or 0.0),
        "vertices": [{"x": float(v.x), "y": float(v.y)} for v in box.vertices],
    }


def _detection_to_payload(detection: FrameOcrDetection) -> dict[str, Any]:
    return {
        "frame_width": int(detection.frame_width),
        "frame_height": int(detection.frame_height),
        "boxes": [_box_to_payload(box) for box in detection.boxes],
    }


def _detection_from_payload(payload: dict[str, Any]) -> FrameOcrDetection:
    boxes = []
    for raw in payload.get("boxes") or []:
        vertices = tuple(
            Vertex(x=float(v.get("x") or 0.0), y=float(v.get("y") or 0.0))
            for v in raw.get("vertices") or []
        )
        boxes.append(
            DetectedTextBox(
                x=float(raw.get("x") or 0.0),
                y=float(raw.get("y") or 0.0),
                width=float(raw.get("width") or 0.0),
                height=float(raw.get("height") or 0.0),
                text=str(raw.get("text") or ""),
                confidence=float(raw.get("confidence") or 0.0),
                vertices=vertices,
            )
        )
    return FrameOcrDetection(
        frame_width=int(payload.get("frame_width") or 0),
        frame_height=int(payload.get("frame_height") or 0),
        boxes=boxes,
    )


class OcrResultCache:
    """Small JSON cache with atomic writes after each completed OCR batch."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._entries: dict[str, dict[str, Any]] = {}
        if self.path.is_file():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if int(raw.get("version") or 0) == _CACHE_VERSION:
                    self._entries = dict(raw.get("entries") or {})
            except (OSError, ValueError, TypeError):
                logger.warning("ocr_cache_load_failed path=%s", self.path)

    def get(self, key: str) -> FrameOcrDetection | None:
        payload = self._entries.get(str(key))
        return _detection_from_payload(payload) if payload is not None else None

    def put(self, key: str, detection: FrameOcrDetection) -> None:
        self._entries[str(key)] = _detection_to_payload(detection)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f"{self.path.name}.tmp")
        temp.write_text(
            json.dumps(
                {"version": _CACHE_VERSION, "entries": self._entries},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temp.replace(self.path)

    @property
    def entry_count(self) -> int:
        return len(self._entries)


def ocr_crop_cache_key(
    path: str | Path,
    *,
    namespace: str = "hybrid-v1",
) -> str:
    digest = hashlib.sha256()
    digest.update(str(namespace).encode("utf-8"))
    digest.update(b"\0")
    digest.update(Path(path).read_bytes())
    return digest.hexdigest()


def process_ocr_paths_with_cache(
    paths: Sequence[Path],
    *,
    endpoint_url: str,
    cache_path: str | Path,
    concurrency: int | None = 2,
    batch_size: int = DEFAULT_CACHE_BATCH_SIZE,
    cache_namespace: str = "hybrid-v1",
    metrics: dict[str, int] | None = None,
) -> list[FrameOcrDetection]:
    """OCR uncached unique crops in small batches, checkpointing each batch."""
    cache = OcrResultCache(cache_path)
    keys = [
        ocr_crop_cache_key(path, namespace=cache_namespace)
        for path in paths
    ]
    resolved: dict[str, FrameOcrDetection] = {}
    missing: list[tuple[str, Path]] = []
    seen_missing: set[str] = set()

    for key, path in zip(keys, paths, strict=True):
        hit = cache.get(key)
        if hit is not None:
            resolved[key] = hit
        elif key not in seen_missing:
            seen_missing.add(key)
            missing.append((key, Path(path)))

    logger.info(
        "hybrid_ocr_cache paths=%s hits=%s misses=%s entries=%s",
        len(paths),
        len(paths) - len(missing),
        len(missing),
        cache.entry_count,
    )
    if metrics is not None:
        metrics["requested"] = int(metrics.get("requested", 0)) + len(paths)
        metrics["cache_hits"] = int(metrics.get("cache_hits", 0)) + len(paths) - len(missing)
        metrics["cloud_requests"] = int(metrics.get("cloud_requests", 0)) + len(missing)
    size = max(1, int(batch_size))
    for offset in range(0, len(missing), size):
        chunk = missing[offset : offset + size]
        detections = process_all_frames_sync(
            [path for _key, path in chunk],
            endpoint_url=endpoint_url,
            concurrency=concurrency,
        )
        for (key, _path), detection in zip(chunk, detections, strict=True):
            cache.put(key, detection)
            resolved[key] = detection
        cache.save()
        logger.info(
            "hybrid_ocr_checkpoint completed=%s/%s",
            min(offset + len(chunk), len(missing)),
            len(missing),
        )

    return [resolved[key] if key in resolved else cache.get(key) for key in keys]  # type: ignore[list-item]
