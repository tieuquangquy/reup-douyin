"""Per-frame text *position* authority with sparse Cloud OCR for *content* only.

Geometry on every frame comes from local ink scan (hardsub) + DBNet mid-title
boxes. Cloud OCR runs on change ticks; text attaches when the current-frame
position overlaps the OCR box. Short same-caption hardsub gaps may hold neighbor
boxes when local evidence flickers; open-ended hold-forward is not used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from src.media_pipeline.cache_provenance import (
    position_cache_matches_video,
    video_content_fingerprint,
)
from src.media_pipeline.frame_sampling.ensure_dbnet_model import ensure_dbnet_onnx
from src.media_pipeline.frame_sampling.ensure_text_recognizer_model import (
    ensure_text_recognizer_assets,
)
from src.media_pipeline.frame_sampling.local_text_detector import LocalTextDetector, TextBox
from src.media_pipeline.frame_sampling.local_text_recognizer import LocalTextRecognizer
from src.media_pipeline.frame_sampling.local_text_verifier import (
    EventDrivenTextVerifier,
    TwoFrameConfirmationGate,
    requires_two_frame_confirmation,
)
from src.media_pipeline.frame_sampling.resolve_source import resolve_video_source
from src.media_pipeline.ocr_filtering.async_batch import process_all_frames_sync
from src.media_pipeline.ocr_filtering.box_geometry_refine import (
    refine_timed_boxes_on_frame,
)
from src.media_pipeline.ocr_filtering.box_timeline_tracker import (
    OcrObservation,
    TimedBox,
    box_iou,
    observations_from_ocr_payload,
)
from src.media_pipeline.ocr_filtering.clean_box_authority import (
    DEFAULT_MIN_CONFIDENCE,
    apply_temporal_consensus,
    collapse_nearby_observations,
    filter_authority_boxes,
    merge_horizontal_line_boxes,
)
from src.media_pipeline.ocr_filtering.hybrid_glyph_ocr import (
    DEFAULT_CACHE_BATCH_SIZE,
    GlyphSegment,
    glyph_mask_change_score,
    process_ocr_paths_with_cache,
    sample_subtitle_glyph_segments,
    subtitle_glyph_mask,
)
from src.media_pipeline.ocr_filtering.overlay_zones import is_mid_title_box
from src.media_pipeline.ocr_filtering.ocr_authority_v3 import (
    EndcardSegment,
    FrameEvidence,
    authority_boxes_for_frame,
    classify_frame_state,
    detect_endcard_segments,
    local_verified_title_boxes,
    verified_endcard_boxes,
)
from src.media_pipeline.ocr_filtering.per_frame_ink_scan import scan_hardsub_ink_box
from src.media_pipeline.ocr_filtering.providers import resolve_ocr_endpoint_url
from src.media_pipeline.ocr_filtering.script_filter import contains_cjk
from src.media_pipeline.ocr_filtering.subtitle_band import (
    BOTTOM_BAND_RATIO,
    is_in_subtitle_band,
    remap_box_from_vertical_crop,
    subtitle_band_top_normalized,
)
from src.media_pipeline.ocr_filtering.types import DetectedTextBox
from src.media_pipeline.ocr_filtering.ocr_track_prototype import (
    _all_frame_times_ms,
    _bottom_band_crop,
    _extract_stills_at_times,
    _mid_title_band_crop,
)

logger = logging.getLogger(__name__)

HARDSUB_MIN_IOU = 0.12
HARDSUB_MIN_H_OVERLAP = 0.35
TITLE_MIN_IOU = 0.20
MIN_ENDCARD_SCENE_SIMILARITY = 0.90
HIGH_RES_AUTHORITY_LONG_EDGE = 960
MAX_HIGH_RES_AUTHORITY_FRAMES = 1200
CURRENT_GEOMETRY_MAX_Y_DISTANCE = 0.055
CURRENT_GEOMETRY_MAX_X_DISTANCE = 0.18
UNMATCHED_ENDCARD_LEFT_TEXT_INSET = 0.075
MAX_CLOUD_CANDIDATES_PER_GLYPH_EVENT = 2
MAX_HARDSUB_LOCAL_GAP_MS = 2000
MAX_TITLE_LOCAL_GAP_MS = 2000


def _ocr_cache_namespace(
    endpoint: str,
    *,
    min_confidence: float,
    crop_kind: str,
) -> str:
    provider_hash = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:16]
    return (
        f"ocr_authority_v3|provider={provider_hash}|"
        f"min={float(min_confidence):.4f}|crop={crop_kind}"
    )


@dataclass(frozen=True)
class OcrTextSegment:
    start_ms: int
    end_ms: int
    boxes: tuple[TimedBox, ...]


@dataclass(frozen=True)
class FrameVisualSignature:
    scene: np.ndarray
    glyph: np.ndarray


def frame_scene_signature(frame_bgr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
    return cv2.resize(lab, (32, 18), interpolation=cv2.INTER_AREA).astype(np.float32)


def scene_signature_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    distance = float(
        np.abs(a.astype(np.float32) - b.astype(np.float32)).mean()
    )
    return max(0.0, 1.0 - distance / 255.0)


def collect_frame_visual_signatures(
    video_path: Path,
) -> dict[int, FrameVisualSignature]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    out: dict[int, FrameVisualSignature] = {}
    frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            out[frame_index] = FrameVisualSignature(
                scene=frame_scene_signature(frame),
                glyph=subtitle_glyph_mask(frame),
            )
            frame_index += 1
    finally:
        cap.release()
    return out


def horizontal_overlap_frac(a: TimedBox, b: TimedBox) -> float:
    ax0, ax1 = float(a.x), float(a.x) + float(a.w)
    bx0, bx1 = float(b.x), float(b.x) + float(b.w)
    ix0, ix1 = max(ax0, bx0), min(ax1, bx1)
    iw = max(0.0, ix1 - ix0)
    min_w = max(1e-9, min(float(a.w), float(b.w)))
    return float(iw / min_w)


def attach_text_to_current_frame_geometry(
    ocr_boxes: Sequence[TimedBox],
    local_boxes: Sequence[TimedBox],
    *,
    require_all: bool = False,
    include_unmatched: bool = False,
) -> list[TimedBox]:
    """Use OCR only as text; final xywh comes from the current decoded frame."""
    local = list(local_boxes)
    attached: list[TimedBox] = []
    matched: dict[int, list[TimedBox]] = {}
    for ocr in ocr_boxes:
        ocx = float(ocr.x) + float(ocr.w) / 2.0
        ocy = float(ocr.y) + float(ocr.h) / 2.0
        best_index: int | None = None
        best_score = float("inf")
        for index, candidate in enumerate(local):
            lcx = float(candidate.x) + float(candidate.w) / 2.0
            lcy = float(candidate.y) + float(candidate.h) / 2.0
            dx = abs(lcx - ocx)
            dy = abs(lcy - ocy)
            max_y = max(
                CURRENT_GEOMETRY_MAX_Y_DISTANCE,
                0.75 * max(float(ocr.h), float(candidate.h)),
            )
            max_x = max(
                CURRENT_GEOMETRY_MAX_X_DISTANCE,
                1.5 * max(float(ocr.w), float(candidate.w)),
            )
            if dy > max_y or dx > max_x:
                continue
            # Row identity is more reliable than Cloud OCR X on icon-heavy UI.
            score = 4.0 * dy + 2.0 * dx
            if contains_cjk(ocr.text):
                expected_h = min(0.025, max(0.012, float(ocr.h) / 2.0))
                score += 30.0 * abs(float(candidate.h) - expected_h)
            if index in matched:
                # Reuse a merged local line only when every unused alternative
                # is materially farther away (for example "27% 36.1克").
                score += 0.08
            if score < best_score:
                best_score = score
                best_index = index
        if best_index is None:
            if not require_all:
                attached.append(ocr)
            continue
        matched.setdefault(best_index, []).append(ocr)

    for index, sources in matched.items():
        geometry = local[index]
        text = " ".join(
            dict.fromkeys(
                source.text.strip()
                for source in sources
                if source.text and source.text.strip()
            )
        )
        attached.append(
            TimedBox(
                x=float(geometry.x),
                y=float(geometry.y),
                w=float(geometry.w),
                h=float(geometry.h),
                text=text,
                confidence=max(float(source.confidence) for source in sources),
            )
        )
    if include_unmatched:
        for index, geometry in enumerate(local):
            if index in matched:
                continue
            # Full-frame DBNet can classify food-thumbnail edges as text.
            # Unverified cover-only evidence must stay out of the icon gutter.
            if float(geometry.x) + float(geometry.w) < UNMATCHED_ENDCARD_LEFT_TEXT_INSET:
                continue
            attached.append(
                TimedBox(
                    x=float(geometry.x),
                    y=float(geometry.y),
                    w=float(geometry.w),
                    h=float(geometry.h),
                    cover_only=True,
                )
            )
    return attached


def with_authority_cover_bounds(
    box: TimedBox,
    *,
    pad_x: float = 0.012,
    pad_y: float = 0.010,
) -> TimedBox:
    """Add a small renderer envelope around current-frame local geometry."""
    x0 = max(0.0, float(box.x) - float(pad_x))
    y0 = max(0.0, float(box.y) - float(pad_y))
    x1 = min(1.0, float(box.x) + float(box.w) + float(pad_x))
    y1 = min(1.0, float(box.y) + float(box.h) + float(pad_y))
    return TimedBox(
        x=box.x,
        y=box.y,
        w=box.w,
        h=box.h,
        text=box.text,
        confidence=box.confidence,
        cover_only=box.cover_only,
        cover_bounds=(x0, y0, x1 - x0, y1 - y0),
    )


def _textbox_to_timed(tb: TextBox, *, text: str = "", confidence: float = 0.0) -> TimedBox:
    return TimedBox(
        x=float(tb.x),
        y=float(tb.y),
        w=float(tb.width),
        h=float(tb.height),
        text=text,
        confidence=confidence,
    )


def _to_detected(box: TimedBox) -> DetectedTextBox:
    return DetectedTextBox(
        x=box.x,
        y=box.y,
        width=max(0.001, box.w),
        height=max(0.001, box.h),
        text=box.text,
        confidence=box.confidence,
    )


def _zone_kind(box: TimedBox) -> str:
    det = _to_detected(box)
    if is_mid_title_box(det):
        return "title"
    if is_in_subtitle_band(det):
        return "hardsub"
    return "other"


def detect_position_boxes_on_frame(
    frame_bgr: np.ndarray,
    *,
    detector: LocalTextDetector | None = None,
) -> list[TimedBox]:
    """Local per-frame geometry: ink hardsub + DBNet mid-title (ink-refined)."""
    if frame_bgr is None or frame_bgr.size == 0:
        return []
    out: list[TimedBox] = []

    hardsub = scan_hardsub_ink_box(frame_bgr, hint=None)
    if hardsub is not None and float(hardsub.w) >= 0.08 and float(hardsub.h) >= 0.018:
        cy = float(hardsub.y) + float(hardsub.h) / 2.0
        if cy >= subtitle_band_top_normalized(BOTTOM_BAND_RATIO) - 0.02:
            out.append(
                TimedBox(
                    x=hardsub.x,
                    y=hardsub.y,
                    w=hardsub.w,
                    h=hardsub.h,
                    text="",
                    confidence=0.0,
                )
            )

    if detector is not None:
        for tb in detector.detect(frame_bgr):
            det = DetectedTextBox(
                x=float(tb.x),
                y=float(tb.y),
                width=float(tb.width),
                height=float(tb.height),
            )
            if not is_mid_title_box(det):
                continue
            hint = _textbox_to_timed(tb)
            refined = refine_timed_boxes_on_frame(frame_bgr, [hint], expand_hardsub=False)
            if refined:
                r = refined[0]
                if float(r.w) >= 0.12 and float(r.h) >= 0.025:
                    out.append(
                        TimedBox(
                            x=r.x,
                            y=r.y,
                            w=r.w,
                            h=r.h,
                            text="",
                            confidence=0.0,
                        )
                    )
    return out


def refresh_positions_with_ink_hardsub(
    video_path: Path,
    cached_rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize cached DBNet evidence; never invent boxes from an ink-only scan."""
    del video_path
    out: list[dict[str, Any]] = []
    for row in sorted(cached_rows, key=lambda item: int(item.get("frame_index") or 0)):
        boxes = []
        for raw in row.get("boxes") or []:
            box = TimedBox(
                x=float(raw["x"]),
                y=float(raw["y"]),
                w=float(raw.get("w") or raw.get("width") or 0.0),
                h=float(raw.get("h") or raw.get("height") or 0.0),
            )
            if box.w > 0.0 and box.h > 0.0:
                boxes.append(box)
        out.append(
            {
                "frame_index": int(row["frame_index"]),
                "time_ms": int(row["time_ms"]),
                "boxes": [box.to_dict() for box in boxes],
            }
        )
    return out


def _position_event_mask(frame_bgr: np.ndarray) -> np.ndarray:
    """Compact two-channel polarity mask used only as a cheap DBNet gate."""
    small = cv2.resize(frame_bgr, (160, 90), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    saturation = hsv[:, :, 1]
    bright = ((gray >= 180) & (saturation <= 90)).astype(np.uint8) * 255
    dark = ((gray <= 75) & (saturation <= 90)).astype(np.uint8) * 255
    return np.stack((bright, dark), axis=2)


def _position_mask_change(a: np.ndarray, b: np.ndarray) -> float:
    if a.ndim == 3 or b.ndim == 3:
        if a.shape != b.shape:
            b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_NEAREST)
        channels = min(a.shape[2], b.shape[2])
        return max(
            _position_mask_change(a[:, :, index], b[:, :, index])
            for index in range(channels)
        )
    aa = (a > 0).astype(np.uint8)
    bb = (b > 0).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    aa_d = cv2.dilate(aa, kernel, iterations=1)
    bb_d = cv2.dilate(bb, kernel, iterations=1)
    intersection = int(np.count_nonzero((aa > 0) & (bb_d > 0))) + int(
        np.count_nonzero((bb > 0) & (aa_d > 0))
    )
    total = int(np.count_nonzero(aa)) + int(np.count_nonzero(bb))
    if total == 0:
        return 0.0
    return 1.0 - min(1.0, float(intersection) / float(total))


def _position_scene_signature(frame_bgr: np.ndarray) -> np.ndarray:
    return cv2.resize(frame_bgr, (32, 18), interpolation=cv2.INTER_AREA).astype(
        np.float32
    )


def _refine_positions_from_event_mask(
    mask: np.ndarray,
    boxes: Sequence[TimedBox],
) -> list[TimedBox]:
    """Snap prior geometry to current-frame candidate pixels inside a tight bound."""
    height, width = mask.shape[:2]
    refined: list[TimedBox] = []
    for box in boxes:
        x0 = max(0, int(np.floor((box.x - 0.015) * width)))
        y0 = max(0, int(np.floor((box.y - 0.015) * height)))
        x1 = min(width, int(np.ceil((box.x + box.w + 0.015) * width)))
        y1 = min(height, int(np.ceil((box.y + box.h + 0.015) * height)))
        if x1 <= x0 or y1 <= y0:
            continue
        roi = mask[y0:y1, x0:x1]
        channel_masks = [
            roi[:, :, index] > 0
            for index in range(roi.shape[2])
            if 4 <= int(np.count_nonzero(roi[:, :, index])) < int(roi.shape[0] * roi.shape[1] * 0.8)
        ]
        if not channel_masks:
            continue
        selected = min(channel_masks, key=np.count_nonzero)
        ys, xs = np.nonzero(selected)
        if len(xs) < 4:
            continue
        rx0 = max(x0, x0 + int(xs.min()) - 1)
        ry0 = max(y0, y0 + int(ys.min()) - 1)
        rx1 = min(x1, x0 + int(xs.max()) + 2)
        ry1 = min(y1, y0 + int(ys.max()) + 2)
        if rx1 - rx0 < 2 or ry1 - ry0 < 2:
            continue
        mask_x = float(rx0 / width)
        mask_y = float(ry0 / height)
        mask_w = float((rx1 - rx0) / width)
        mask_h = float((ry1 - ry0) / height)
        previous_cx = box.x + box.w * 0.5
        previous_cy = box.y + box.h * 0.5
        mask_cx = mask_x + mask_w * 0.5
        mask_cy = mask_y + mask_h * 0.5
        center_x = min(previous_cx + 0.025, max(previous_cx - 0.025, mask_cx))
        center_y = min(previous_cy + 0.018, max(previous_cy - 0.018, mask_cy))
        refined_w = min(
            box.w * 1.20,
            max(box.w * 0.80, box.w * 0.85 + mask_w * 0.15),
        )
        refined_h = min(
            box.h * 1.20,
            max(box.h * 0.80, box.h * 0.85 + mask_h * 0.15),
        )
        refined.append(
            TimedBox(
                x=max(0.0, min(1.0 - refined_w, center_x - refined_w * 0.5)),
                y=max(0.0, min(1.0 - refined_h, center_y - refined_h * 0.5)),
                w=refined_w,
                h=refined_h,
            )
        )
    return refined


class EventDrivenPositionDetector:
    """Run cheap subtitle DBNet each frame and full DBNet only on visual events."""

    def __init__(
        self,
        detector: LocalTextDetector,
        *,
        checkpoint_frames: int = 12,
        max_mask_change: float = 0.60,
        max_scene_change: float = 0.18,
        subtitle_long_edge: int = 480,
    ):
        self._detector = detector
        self._checkpoint_frames = max(1, int(checkpoint_frames))
        self._max_mask_change = float(max_mask_change)
        self._max_scene_change = float(max_scene_change)
        self._subtitle_long_edge = max(320, int(subtitle_long_edge))
        self._previous_boxes: list[TimedBox] = []
        self._previous_mask: np.ndarray | None = None
        self._previous_scene: np.ndarray | None = None
        self._last_full_dbnet_frame = -self._checkpoint_frames
        self.dbnet_calls = 0
        self.subtitle_dbnet_calls = 0
        self.full_dbnet_calls = 0
        self.refined_frames = 0
        self.scene_resets = 0

    def detect(
        self,
        frame_bgr: np.ndarray,
        *,
        frame_index: int,
    ) -> tuple[list[TimedBox], str]:
        mask = _position_event_mask(frame_bgr)
        subtitle_top = subtitle_band_top_normalized()
        mask[int(round(mask.shape[0] * subtitle_top)) :, :, :] = 0
        scene = _position_scene_signature(frame_bgr)
        mask_change = (
            _position_mask_change(mask, self._previous_mask)
            if self._previous_mask is not None
            else 1.0
        )
        scene_change = (
            float(np.abs(scene - self._previous_scene).mean()) / 255.0
            if self._previous_scene is not None
            else 1.0
        )
        scene_reset = self._previous_scene is not None and scene_change > self._max_scene_change
        previous_top_boxes = [
            box
            for box in self._previous_boxes
            if box.y + box.h * 0.5 < subtitle_top
        ]
        dense_previous = len(self._previous_boxes) >= 5
        should_run_full = (
            self._previous_mask is None
            or scene_reset
            or mask_change > self._max_mask_change
            or dense_previous
            or int(frame_index) - self._last_full_dbnet_frame >= self._checkpoint_frames
        )

        crop_top = max(0, min(frame_bgr.shape[0] - 1, int(round(frame_bgr.shape[0] * subtitle_top))))
        subtitle_crop = frame_bgr[crop_top:, :]
        subtitle_boxes = [
            TimedBox(
                x=float(box.x),
                y=subtitle_top + float(box.y) * (1.0 - subtitle_top),
                w=float(box.width),
                h=float(box.height) * (1.0 - subtitle_top),
            )
            for box in self._detector.detect(
                subtitle_crop,
                long_edge=self._subtitle_long_edge,
            )
        ]
        self.subtitle_dbnet_calls += 1
        self.dbnet_calls += 1

        if should_run_full:
            full_boxes = [_textbox_to_timed(box) for box in self._detector.detect(frame_bgr)]
            top_boxes = [
                box for box in full_boxes if box.y + box.h * 0.5 < subtitle_top
            ]
            boxes = [*top_boxes, *subtitle_boxes]
            if len(full_boxes) >= 5:
                boxes = full_boxes
            source = "dbnet_full"
            self.dbnet_calls += 1
            self.full_dbnet_calls += 1
            self._last_full_dbnet_frame = int(frame_index)
            if scene_reset:
                self.scene_resets += 1
        else:
            refined_top = _refine_positions_from_event_mask(
                mask,
                previous_top_boxes,
            )
            boxes = [*refined_top, *subtitle_boxes]
            source = "dbnet_subtitle+current_frame_refine"
            self.refined_frames += 1
        self._previous_boxes = boxes
        self._previous_mask = mask
        self._previous_scene = scene
        return boxes, source


def detect_positions_timeline(
    video_path: Path,
    *,
    detector: LocalTextDetector | None = None,
    frame_stride: int = 1,
    event_driven: bool = False,
) -> list[dict[str, Any]]:
    """Scan every frame; gate DBNet while retaining current-frame pixel evidence."""
    stride = max(1, int(frame_stride))
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    rows: list[dict[str, Any]] = []
    event_detector = (
        EventDrivenPositionDetector(detector)
        if event_driven and detector is not None
        else None
    )
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
        frame_index = 0
        while True:
            ok, bgr = cap.read()
            if not ok or bgr is None:
                break
            if frame_index % stride == 0:
                if event_detector is not None:
                    boxes, position_source = event_detector.detect(
                        bgr,
                        frame_index=frame_index,
                    )
                else:
                    boxes = (
                        [_textbox_to_timed(box) for box in detector.detect(bgr)]
                        if detector is not None
                        else []
                    )
                    position_source = "dbnet" if detector is not None else "none"
                rows.append(
                    {
                        "frame_index": frame_index,
                        "time_ms": int(round(frame_index * 1000.0 / fps)),
                        "boxes": [b.to_dict() for b in boxes],
                        "position_detection_source": position_source,
                    }
                )
                if frame_index % 100 == 0:
                    logger.info(
                        "[PerFramePos] frame=%s boxes=%s",
                        frame_index,
                        len(boxes),
                    )
            frame_index += 1
    finally:
        cap.release()
    if event_detector is not None:
        logger.info(
            "event_position_detection dbnet_calls=%s refined_frames=%s scene_resets=%s",
            event_detector.dbnet_calls,
            event_detector.refined_frames,
            event_detector.scene_resets,
        )
    return rows


def _box_center_inside_expanded(
    local: TimedBox,
    authority: TimedBox,
    *,
    pad_x: float = 0.08,
    pad_y: float = 0.05,
) -> bool:
    cx = float(local.x) + float(local.w) / 2.0
    cy = float(local.y) + float(local.h) / 2.0
    return (
        float(authority.x) - pad_x
        <= cx
        <= float(authority.x) + float(authority.w) + pad_x
        and float(authority.y) - pad_y
        <= cy
        <= float(authority.y) + float(authority.h) + pad_y
    )


def _position_boxes_from_row(row: dict[str, Any]) -> list[TimedBox]:
    """Rebuild timed boxes from a position row, keeping local CTC text evidence."""
    out: list[TimedBox] = []
    for raw in row.get("boxes") or []:
        width = float(raw.get("w") or raw.get("width") or 0.0)
        height = float(raw.get("h") or raw.get("height") or 0.0)
        if width <= 0.0 or height <= 0.0:
            continue
        out.append(
            TimedBox(
                x=float(raw["x"]),
                y=float(raw["y"]),
                w=width,
                h=height,
                text=str(raw.get("text") or ""),
                confidence=float(raw.get("confidence") or 0.0),
            )
        )
    return out


def keep_rejected_hardsub_geometry(box: TimedBox) -> bool:
    """True when a CTC-rejected proposal is still usable as bottom-band geometry.

    Wide subtitle-band boxes prove ink is present even when recognition fails.
    Narrow crumbs must stay discarded so hold cannot unlock on noise (f79/f821).
    """
    return (
        float(box.y) + float(box.h) * 0.5 + 1e-9 >= subtitle_band_top_normalized()
        and float(box.w) >= 0.12
    )


def append_raw_hardsub_geometry_keeps(
    *,
    raw_boxes: Sequence[TimedBox],
    accepted: Sequence[TimedBox],
    uncertain: list[TimedBox],
) -> None:
    """Retain wide bottom raw proposals when ink/CTC drops them with no decision.

    ``EventDrivenTextVerifier`` may blank-skip a frame (no reject events). Hold and
    OCR attach still need that geometry on the current frame.
    """
    kept = list(accepted) + list(uncertain)
    seen = {
        (round(box.x, 4), round(box.y, 4), round(box.w, 4), round(box.h, 4))
        for box in kept
    }
    for box in raw_boxes:
        if not keep_rejected_hardsub_geometry(box):
            continue
        key = (round(box.x, 4), round(box.y, 4), round(box.w, 4), round(box.h, 4))
        if key in seen:
            continue
        if any(box_iou(box, other) >= 0.50 for other in kept):
            continue
        geometry = TimedBox(
            x=float(box.x),
            y=float(box.y),
            w=float(box.w),
            h=float(box.h),
        )
        uncertain.append(geometry)
        kept.append(geometry)
        seen.add(key)


def _local_geometry_boxes_from_row(row: dict[str, Any]) -> list[TimedBox]:
    """Verified boxes plus uncertain subtitle/title proposals for activation.

    CTC may mark a visible hardsub uncertain; keep that geometry so Cloud OCR
    can still attach on the exact frame.
    """
    out = _position_boxes_from_row(row)
    seen = {
        (round(box.x, 4), round(box.y, 4), round(box.w, 4), round(box.h, 4))
        for box in out
    }
    band_top = subtitle_band_top_normalized()
    for raw in row.get("local_uncertain_boxes") or []:
        if not isinstance(raw, dict):
            continue
        width = float(raw.get("w") or raw.get("width") or 0.0)
        height = float(raw.get("h") or raw.get("height") or 0.0)
        if width <= 0.0 or height <= 0.0:
            continue
        x = float(raw["x"])
        y = float(raw["y"])
        mapping = {"x": x, "y": y, "width": width, "height": height}
        center_y = y + height * 0.5
        if not (center_y + 1e-9 >= band_top or is_mid_title_box(mapping)):
            continue
        key = (round(x, 4), round(y, 4), round(width, 4), round(height, 4))
        if key in seen:
            continue
        out.append(
            TimedBox(
                x=x,
                y=y,
                w=width,
                h=height,
                text=str(raw.get("text") or ""),
                confidence=float(raw.get("confidence") or 0.0),
            )
        )
        seen.add(key)
    return out


def route_verified_glyph_segments(
    segments: Sequence[GlyphSegment],
    position_rows: Sequence[dict[str, Any]],
    *,
    max_candidates: int = MAX_CLOUD_CANDIDATES_PER_GLYPH_EVENT,
) -> list[GlyphSegment]:
    """Route at most main+retry Cloud candidates for locally plausible events.

    Blank and rejected local frames never escalate. Retry is kept as the second
    candidate only; `_run_cloud_ocr_segments` stops spending after the first hit.
    """
    eligible_times = [
        int(row.get("time_ms") or 0)
        for row in position_rows
        if row.get("local_verification") in {"verified", "uncertain"}
    ]
    routed: list[GlyphSegment] = []
    for segment in segments:
        if not segment.has_glyph or not any(
            int(segment.start_ms) <= time_ms < int(segment.end_ms)
            for time_ms in eligible_times
        ):
            continue
        routed.append(
            GlyphSegment(
                segment_id=int(segment.segment_id),
                start_ms=int(segment.start_ms),
                end_ms=int(segment.end_ms),
                candidate_times_ms=tuple(
                    int(value)
                    for value in segment.candidate_times_ms[: max(1, int(max_candidates))]
                ),
                has_glyph=True,
            )
        )
    return routed


def route_verified_sample_times(
    sample_times: Sequence[int],
    position_rows: Sequence[dict[str, Any]],
    *,
    tolerance_ms: int = 120,
) -> list[int]:
    """Filter fixed-grid Cloud ticks through local verified/uncertain evidence."""
    eligible = [
        int(row.get("time_ms") or 0)
        for row in position_rows
        if row.get("local_verification") in {"verified", "uncertain"}
    ]
    return [
        int(sample_time)
        for sample_time in sample_times
        if any(abs(int(sample_time) - time_ms) <= int(tolerance_ms) for time_ms in eligible)
    ]


def verify_position_rows(
    video_path: Path,
    position_rows: Sequence[dict[str, Any]],
    *,
    recognizer: LocalTextRecognizer,
    provisional_endcards: Sequence[EndcardSegment] = (),
) -> tuple[list[dict[str, Any]], dict[str, int | float]]:
    """Verify exact-frame geometry while reusing unchanged local CTC evidence."""
    rows = [dict(row) for row in position_rows]
    by_index = {int(row.get("frame_index") or 0): row for row in rows}
    endcard_ranges = [
        (int(segment.start_ms), int(segment.end_ms))
        for segment in provisional_endcards
    ]
    previous: dict[str, list[TimedBox]] = {"hardsub": [], "title": [], "endcard": []}
    event_verifier = EventDrivenTextVerifier(recognizer)
    confirmation_gates = {
        "hardsub": TwoFrameConfirmationGate(),
        "title": TwoFrameConfirmationGate(),
    }
    metrics: dict[str, int | float] = {
        "raw_proposals": 0,
        "verified_lines": 0,
        "uncertain_lines": 0,
        "rejected_lines": 0,
        "recognizer_ms": 0.0,
        "event_verifier_ms": 0.0,
        "recognizer_calls": 0,
        "recognizer_batches": 0,
        "reused_recognitions": 0,
        "recognition_reuse_ratio": 0.0,
        "blank_frame_skips": 0,
        "two_frame_backfills": 0,
    }
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video for local text verification: {video_path}")
    frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            row = by_index.get(frame_index)
            frame_index += 1
            if row is None:
                continue
            raw_boxes = _position_boxes_from_row(row)
            metrics["raw_proposals"] = int(metrics["raw_proposals"]) + len(raw_boxes)
            time_ms = int(row.get("time_ms") or 0)
            is_endcard = any(start <= time_ms < end for start, end in endcard_ranges)
            mode_boxes: list[tuple[str, list[TimedBox]]]
            if is_endcard:
                mode_boxes = [("endcard", raw_boxes)]
            else:
                mode_boxes = [
                    (
                        "hardsub",
                        [
                            box
                            for box in raw_boxes
                            if box.y + box.h * 0.5 >= subtitle_band_top_normalized()
                        ],
                    ),
                    (
                        "title",
                        [
                            box
                            for box in raw_boxes
                            if box.y + box.h * 0.5 < subtitle_band_top_normalized()
                        ],
                    ),
                ]
            accepted: list[TimedBox] = []
            uncertain: list[TimedBox] = []
            rejected_count = 0
            recognized_labels: list[str] = []
            started = time.perf_counter()
            calls_before = event_verifier.recognizer_calls
            reused_before = event_verifier.reused_recognitions
            inference_ms_before = event_verifier.recognizer_inference_ms
            blank_before = event_verifier.blank_frame_skips
            for mode, candidates in mode_boxes:
                results = event_verifier.verify(
                    frame,
                    candidates,
                    mode=mode,  # type: ignore[arg-type]
                    frame_index=frame_index - 1,
                    previous_verified=previous[mode],
                )
                verified_boxes: list[TimedBox] = []
                reused_flags: list[bool] = []
                current_verified: list[TimedBox] = []
                for result in results:
                    line_box = result.line.box
                    if result.decision == "verified":
                        verified_boxes.append(
                            TimedBox(
                                line_box.x,
                                line_box.y,
                                line_box.w,
                                line_box.h,
                                text=result.recognition.text,
                                confidence=result.text_likeness,
                            )
                        )
                        reused_flags.append(bool(result.recognition_reused))
                        recognized_labels.append(result.recognition.text)
                    elif result.decision == "uncertain":
                        uncertain.append(line_box)
                    else:
                        rejected_count += 1
                        if mode == "hardsub" and keep_rejected_hardsub_geometry(
                            line_box
                        ):
                            uncertain.append(line_box)
                if mode == "endcard":
                    accepted.extend(verified_boxes)
                    current_verified = list(verified_boxes)
                elif not requires_two_frame_confirmation(mode):
                    accepted.extend(verified_boxes)
                    current_verified = list(verified_boxes)
                else:
                    confirmation = confirmation_gates[mode].accept(
                        frame_index=frame_index - 1,
                        mode=mode,
                        verified_boxes=verified_boxes,
                        recognition_reused_flags=reused_flags,
                    )
                    accepted.extend(confirmation.accepted)
                    current_verified = list(confirmation.accepted)
                    if confirmation.pending:
                        uncertain.extend(confirmation.pending)
                    if confirmation.backfill_frame_index is not None:
                        metrics["two_frame_backfills"] = (
                            int(metrics["two_frame_backfills"]) + 1
                        )
                        previous_row = by_index.get(int(confirmation.backfill_frame_index))
                        if previous_row is not None:
                            existing = [
                                TimedBox(
                                    float(raw["x"]),
                                    float(raw["y"]),
                                    float(raw.get("w") or raw.get("width") or 0.0),
                                    float(raw.get("h") or raw.get("height") or 0.0),
                                    text=str(raw.get("text") or ""),
                                    confidence=float(raw.get("confidence") or 0.0),
                                )
                                for raw in previous_row.get("boxes") or []
                            ]
                            merged = list(existing)
                            for box in confirmation.backfill_boxes:
                                if not any(box_iou(box, old) >= 0.40 for old in merged):
                                    merged.append(box)
                            previous_row["boxes"] = [box.to_dict() for box in merged]
                            previous_row["verified_line_count"] = len(merged)
                            previous_row["local_verification"] = (
                                "verified" if merged else previous_row.get("local_verification")
                            )
                            metrics["verified_lines"] = int(metrics["verified_lines"]) + (
                                len(merged) - len(existing)
                            )
                if current_verified:
                    previous[mode] = current_verified
            append_raw_hardsub_geometry_keeps(
                raw_boxes=raw_boxes,
                accepted=accepted,
                uncertain=uncertain,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            row_recognizer_ms = (
                event_verifier.recognizer_inference_ms - inference_ms_before
            )
            row_calls = event_verifier.recognizer_calls - calls_before
            row_reused = event_verifier.reused_recognitions - reused_before
            row_blank = event_verifier.blank_frame_skips - blank_before
            metrics["recognizer_ms"] = (
                float(metrics["recognizer_ms"]) + row_recognizer_ms
            )
            metrics["event_verifier_ms"] = (
                float(metrics["event_verifier_ms"]) + elapsed_ms
            )
            metrics["verified_lines"] = int(metrics["verified_lines"]) + len(accepted)
            metrics["uncertain_lines"] = int(metrics["uncertain_lines"]) + len(uncertain)
            metrics["rejected_lines"] = int(metrics["rejected_lines"]) + rejected_count
            metrics["blank_frame_skips"] = (
                int(metrics["blank_frame_skips"]) + max(0, row_blank)
            )
            row["boxes"] = [box.to_dict() for box in accepted]
            row["local_uncertain_boxes"] = [box.to_dict() for box in uncertain]
            row["raw_proposal_count"] = len(raw_boxes)
            row["verified_line_count"] = len(accepted)
            row["uncertain_line_count"] = len(uncertain)
            row["local_recognition"] = [label for label in recognized_labels if label]
            row["local_recognizer_ms"] = round(row_recognizer_ms, 3)
            row["local_recognizer_calls"] = row_calls
            row["local_recognition_reused"] = row_reused
            if not accepted and not uncertain and row_blank:
                row["local_verification"] = "blank"
            else:
                row["local_verification"] = (
                    "verified" if accepted else "uncertain" if uncertain else "rejected"
                )
    finally:
        cap.release()
    total_decisions = event_verifier.recognizer_calls + event_verifier.reused_recognitions
    metrics["recognizer_calls"] = event_verifier.recognizer_calls
    metrics["recognizer_batches"] = event_verifier.recognizer_batches
    metrics["reused_recognitions"] = event_verifier.reused_recognitions
    metrics["blank_frame_skips"] = max(
        int(metrics["blank_frame_skips"]),
        int(event_verifier.blank_frame_skips),
    )
    metrics["recognition_reuse_ratio"] = (
        float(event_verifier.reused_recognitions / total_decisions)
        if total_decisions
        else 0.0
    )
    logger.info(
        "local_text_verification raw=%s verified=%s uncertain=%s rejected=%s "
        "calls=%s reused=%s blank_skips=%s backfills=%s inference_ms=%.1f",
        metrics["raw_proposals"],
        metrics["verified_lines"],
        metrics["uncertain_lines"],
        metrics["rejected_lines"],
        metrics["recognizer_calls"],
        metrics["reused_recognitions"],
        metrics["blank_frame_skips"],
        metrics["two_frame_backfills"],
        metrics["recognizer_ms"],
    )
    return rows, metrics


def bounded_high_res_targets(
    targets: dict[int, str],
    *,
    max_frames: int,
) -> tuple[dict[int, str], int]:
    """Keep endcards, then uniformly sample subtitle retries within the budget."""
    budget = max(0, int(max_frames))
    ordered = dict(sorted((int(index), kind) for index, kind in targets.items()))
    if len(ordered) <= budget:
        return ordered, 0
    endcards = [index for index, kind in ordered.items() if kind == "endcard"]
    hardsubs = [index for index, kind in ordered.items() if kind != "endcard"]
    kept_endcards = endcards[:budget]
    slots = max(0, budget - len(kept_endcards))
    if slots >= len(hardsubs):
        kept_hardsubs = hardsubs
    elif slots <= 0:
        kept_hardsubs = []
    elif slots == 1:
        kept_hardsubs = [hardsubs[len(hardsubs) // 2]]
    else:
        kept_hardsubs = [
            hardsubs[round(i * (len(hardsubs) - 1) / (slots - 1))]
            for i in range(slots)
        ]
    selected_indices = set(kept_endcards) | set(kept_hardsubs)
    selected = {
        index: kind
        for index, kind in ordered.items()
        if index in selected_indices
    }
    return selected, len(ordered) - len(selected)


def refine_positions_for_ocr_authority(
    video_path: Path,
    position_rows: Sequence[dict[str, Any]],
    observations: Sequence[OcrObservation],
    endcard_segments: Sequence[EndcardSegment],
    *,
    detector: LocalTextDetector,
    recognizer: LocalTextRecognizer,
    long_edge: int = HIGH_RES_AUTHORITY_LONG_EDGE,
    max_candidate_distance_ms: int = 2500,
    max_high_res_frames: int = MAX_HIGH_RES_AUTHORITY_FRAMES,
) -> list[dict[str, Any]]:
    """Escalate only OCR-relevant frames to high-resolution local geometry."""
    rows = [dict(row) for row in position_rows]
    endcard_ranges = [
        (int(segment.start_ms), int(segment.end_ms))
        for segment in endcard_segments
    ]
    hardsub_observations = [
        observation
        for observation in observations
        if any(is_in_subtitle_band(_to_detected(box)) for box in observation.boxes)
    ]
    target_kind: dict[int, str] = {}
    for row in rows:
        frame_index = int(row.get("frame_index") or 0)
        time_ms = int(row.get("time_ms") or 0)
        if any(start <= time_ms < end for start, end in endcard_ranges):
            target_kind[frame_index] = "endcard"
            continue
        low_res = [
            TimedBox(
                x=float(raw["x"]),
                y=float(raw["y"]),
                w=float(raw.get("w") or raw.get("width") or 0.0),
                h=float(raw.get("h") or raw.get("height") or 0.0),
            )
            for raw in row.get("boxes") or []
        ]
        if not low_res:
            continue
        for observation in hardsub_observations:
            if abs(int(observation.time_ms) - time_ms) > int(max_candidate_distance_ms):
                continue
            if any(
                _box_center_inside_expanded(local, ocr)
                for local in low_res
                for ocr in observation.boxes
                if is_in_subtitle_band(_to_detected(ocr))
            ):
                target_kind[frame_index] = "hardsub"
                break

    requested_targets = dict(target_kind)
    target_kind, skipped_count = bounded_high_res_targets(
        target_kind,
        max_frames=max_high_res_frames,
    )
    for frame_index in set(requested_targets) - set(target_kind):
        by_row = next(
            (
                row
                for row in rows
                if int(row.get("frame_index") or 0) == frame_index
            ),
            None,
        )
        if by_row is not None:
            by_row["high_res_skipped"] = "budget"
    if not target_kind:
        return rows
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    frames = read_frames_at_indices_sequentially(cap, set(target_kind))
    cap.release()
    by_index = {int(row.get("frame_index") or 0): row for row in rows}
    high_res_verifier = EventDrivenTextVerifier(recognizer)
    for frame_index, frame in frames.items():
        kind = target_kind[frame_index]
        if kind == "hardsub":
            y0 = 2.0 / 3.0
            top = int(round(frame.shape[0] * y0))
            crop = frame[top:, :]
            detected = detector.detect(crop, long_edge=long_edge)
            high_res = [
                TimedBox(
                    x=float(box.x),
                    y=y0 + float(box.y) * (1.0 - y0),
                    w=float(box.width),
                    h=float(box.height) * (1.0 - y0),
                )
                for box in detected
            ]
            verified_high_res = high_res_verifier.verify(
                frame,
                high_res,
                mode="hardsub",
                frame_index=frame_index,
            )
            high_res = [
                result.line.box
                for result in verified_high_res
                if result.decision in {"verified", "uncertain"}
            ]
            previous = list(by_index[frame_index].get("boxes") or [])
            boxes, geometry_source = compose_hardsub_boxes_after_high_res(
                previous,
                high_res,
                band_top=y0,
            )
            by_index[frame_index]["high_res_geometry_source"] = geometry_source
        else:
            high_res = [
                _textbox_to_timed(box)
                for box in detector.detect(frame, long_edge=long_edge)
            ]
            verified_high_res = high_res_verifier.verify(
                frame,
                high_res,
                mode="endcard",
                frame_index=frame_index,
            )
            high_res = [
                result.line.box
                for result in verified_high_res
                if result.decision in {"verified", "uncertain"}
            ]
            boxes = [box.to_dict() for box in high_res]
        by_index[frame_index]["boxes"] = boxes
        by_index[frame_index]["position_resolution"] = int(long_edge)
        by_index[frame_index]["high_res_verified_lines"] = len(high_res)
        by_index[frame_index]["high_res_recognition_reused"] = sum(
            1 for result in verified_high_res if result.recognition_reused
        )
    logger.info(
        "high_res_position_authority frames=%s long_edge=%s",
        len(frames),
        int(long_edge),
    )
    if skipped_count:
        logger.warning(
            "high_res_position_budget_exhausted skipped=%s budget=%s",
            skipped_count,
            int(max_high_res_frames),
        )
    return rows


def compose_hardsub_boxes_after_high_res(
    previous_boxes: Sequence[dict[str, Any]],
    high_res_boxes: Sequence[TimedBox],
    *,
    band_top: float = 2.0 / 3.0,
) -> tuple[list[dict[str, Any]], str]:
    """Merge high-res hardsub geometry without wiping prior OCR-matched evidence.

    High-res may refine or replace the bottom band. When ink/CTC yields nothing,
    keep the previous hardsub boxes so exact-frame activation still has local signal.
    """
    above: list[dict[str, Any]] = []
    prior_hardsub: list[dict[str, Any]] = []
    for raw in previous_boxes:
        y = float(raw.get("y") or 0.0)
        h = float(raw.get("h") or raw.get("height") or 0.0)
        if y + h / 2.0 < float(band_top):
            above.append(dict(raw))
        else:
            prior_hardsub.append(dict(raw))
    if high_res_boxes:
        return [
            *above,
            *(box.to_dict() for box in high_res_boxes),
        ], "high_res"
    return [*above, *prior_hardsub], "low_res_fallback"


def build_ocr_text_segments(
    observations: Sequence[OcrObservation],
    *,
    duration_ms: int,
) -> list[OcrTextSegment]:
    """Map sparse OCR ticks to [start, end) text segments (content only)."""
    # Empty observations are meaningful boundaries: they stop the previous
    # caption instead of incorrectly carrying its text through a blank state.
    obs = sorted(observations, key=lambda o: o.time_ms)
    if not obs:
        return []
    segments: list[OcrTextSegment] = []
    for i, o in enumerate(obs):
        # The first keyframe is deliberately sampled after a short stability
        # confirmation. It still represents the state visible from frame zero.
        start = 0 if i == 0 else int(o.time_ms)
        end = int(obs[i + 1].time_ms) if i + 1 < len(obs) else int(duration_ms) + 1
        segments.append(OcrTextSegment(start_ms=start, end_ms=end, boxes=o.boxes))
    return segments


def fallback_times_for_empty_observations(
    observations: Sequence[OcrObservation],
    *,
    duration_ms: int,
    offset_ms: int = 200,
) -> list[tuple[int, int]]:
    """Return ``(original_tick, retry_tick)`` for one bounded ambiguity retry."""
    ordered = sorted(observations, key=lambda o: o.time_ms)
    retries: list[tuple[int, int]] = []
    offset = max(50, int(offset_ms))
    for i, observation in enumerate(ordered):
        if observation.boxes:
            continue
        original = int(observation.time_ms)
        retry = original + offset
        if retry > int(duration_ms):
            continue
        if i + 1 < len(ordered) and retry >= int(ordered[i + 1].time_ms) - 50:
            continue
        retries.append((original, retry))
    return retries


def activate_frame_from_observations(
    *,
    frame_index: int,
    time_ms: int,
    local_boxes: Sequence[TimedBox],
    observations: Sequence[OcrObservation],
    duration_ms: int,
    max_candidate_distance_ms: int = 2500,
    current_glyph_mask: np.ndarray | None = None,
    candidate_glyph_masks: dict[int, np.ndarray] | None = None,
    observation_sources: dict[int, int] | None = None,
) -> dict[str, Any]:
    """Choose OCR content by current-frame evidence, never by interval membership."""
    candidates: list[
        tuple[float, OcrObservation, list[TimedBox], float | None]
    ] = []
    ratio = float(time_ms) / float(duration_ms) if duration_ms > 0 else 0.0
    for observation in observations:
        distance = abs(int(observation.time_ms) - int(time_ms))
        if distance > int(max_candidate_distance_ms) or not observation.boxes:
            continue
        evidence = FrameEvidence(
            frame_index=int(frame_index),
            time_ms=int(time_ms),
            local_boxes=tuple(local_boxes),
            ocr_boxes=tuple(observation.boxes),
            timeline_ratio=ratio,
        )
        approved = authority_boxes_for_frame(evidence)
        if not approved:
            continue
        state = classify_frame_state(
            FrameEvidence(
                frame_index=int(frame_index),
                time_ms=int(time_ms),
                local_boxes=tuple(local_boxes),
                ocr_boxes=tuple(approved),
                timeline_ratio=ratio,
            )
        )
        if state == "endcard":
            # End cards require explicit scene activation in the video-aware pass.
            continue
        glyph_similarity: float | None = None
        if state == "hardsub" and current_glyph_mask is not None:
            source_time = (
                observation_sources.get(int(observation.time_ms), int(observation.time_ms))
                if observation_sources is not None
                else int(observation.time_ms)
            )
            source_mask = (
                candidate_glyph_masks.get(source_time)
                if candidate_glyph_masks is not None
                else None
            )
            if source_mask is not None:
                glyph_similarity = 1.0 - glyph_mask_change_score(
                    current_glyph_mask,
                    source_mask,
                )
                # ``approved`` already required current-frame local hardsub
                # geometry. Keep glyph as a ranking signal only so food motion
                # cannot blank a visible caption (f132).
        confidence = sum(float(box.confidence) for box in approved) / max(
            1,
            len(approved),
        )
        score = confidence - min(0.75, float(distance) / 4000.0)
        if glyph_similarity is not None:
            score += 0.25 * glyph_similarity
        candidates.append((score, observation, approved, glyph_similarity))

    if not candidates:
        local_titles = local_verified_title_boxes(local_boxes)
        if local_titles:
            confidence = sum(float(box.confidence) for box in local_titles) / max(
                1,
                len(local_titles),
            )
            return {
                "boxes": local_titles,
                "frame_state": "title",
                "activation_source": "local_verified_title",
                "activation_score": round(float(confidence), 6),
                "candidate_time_ms": None,
                "glyph_match": None,
                "ocr_candidate_count": 0,
            }
        return {
            "boxes": [],
            "frame_state": "blank",
            "activation_source": "none",
            "activation_score": 0.0,
            "candidate_time_ms": None,
            "glyph_match": None,
            "ocr_candidate_count": 0,
        }
    score, observation, approved, glyph_similarity = max(
        candidates,
        key=lambda item: item[0],
    )
    state = classify_frame_state(
        FrameEvidence(
            frame_index=int(frame_index),
            time_ms=int(time_ms),
            local_boxes=tuple(local_boxes),
            ocr_boxes=tuple(approved),
            timeline_ratio=ratio,
        )
    )
    direction = "future" if int(observation.time_ms) > int(time_ms) else "past"
    return {
        "boxes": approved,
        "frame_state": state,
        "activation_source": f"{direction}_ocr+current_local",
        "activation_score": round(float(score), 6),
        "candidate_time_ms": int(observation.time_ms),
        "glyph_match": (
            round(float(glyph_similarity), 6)
            if glyph_similarity is not None
            else None
        ),
        "ocr_candidate_count": len(candidates),
    }


def choose_segment_observation(
    segment: GlyphSegment,
    candidates_by_time: dict[int, OcrObservation],
) -> OcrObservation:
    """Choose the first successful ranked candidate and remap to segment start."""
    for candidate_time in segment.candidate_times_ms:
        observation = candidates_by_time.get(int(candidate_time))
        if observation is not None and observation.boxes:
            return OcrObservation(
                time_ms=int(segment.start_ms),
                boxes=observation.boxes,
            )
    return OcrObservation(time_ms=int(segment.start_ms), boxes=())


def read_frames_at_indices_sequentially(
    capture: Any,
    indices: set[int],
) -> dict[int, np.ndarray]:
    """Decode in presentation order; OpenCV random seek is not frame-exact."""
    wanted = {int(index) for index in indices if int(index) >= 0}
    if not wanted:
        return {}
    last = max(wanted)
    frames: dict[int, np.ndarray] = {}
    frame_index = 0
    while frame_index <= last:
        ok, frame = capture.read()
        if not ok or frame is None:
            break
        if frame_index in wanted:
            frames[frame_index] = frame.copy()
        frame_index += 1
    return frames


def repair_adjacent_partial_text(
    observations: Sequence[OcrObservation],
    *,
    max_gap_ms: int = 1200,
) -> list[OcrObservation]:
    """Repair OCR fragments when adjacent states contain the same longer text."""
    def _tracked_from_longer(
        shorter: TimedBox,
        longer: TimedBox,
        text: str,
    ) -> TimedBox:
        return TimedBox(
            x=longer.x,
            y=longer.y,
            w=longer.w,
            h=longer.h,
            text=text,
            confidence=max(shorter.confidence, longer.confidence),
        )

    ordered = sorted(observations, key=lambda observation: observation.time_ms)
    boxes_by_index = [list(observation.boxes) for observation in ordered]
    for i in range(len(ordered) - 1):
        if int(ordered[i + 1].time_ms) - int(ordered[i].time_ms) > int(max_gap_ms):
            continue
        for left_index, left in enumerate(list(boxes_by_index[i])):
            for right_index, right in enumerate(list(boxes_by_index[i + 1])):
                if _zone_kind(left) != _zone_kind(right):
                    continue
                left_text = (left.text or "").strip()
                right_text = (right.text or "").strip()
                if len(left_text) < 2 or len(right_text) < 2:
                    continue
                if left_text in right_text and len(right_text) > len(left_text):
                    boxes_by_index[i][left_index] = _tracked_from_longer(
                        left,
                        right,
                        right_text,
                    )
                elif right_text in left_text and len(left_text) > len(right_text):
                    boxes_by_index[i + 1][right_index] = _tracked_from_longer(
                        right,
                        left,
                        left_text,
                    )
    return [
        OcrObservation(time_ms=observation.time_ms, boxes=tuple(boxes_by_index[i]))
        for i, observation in enumerate(ordered)
    ]


def _boxes_overlap_for_zone(pos: TimedBox, ocr: TimedBox) -> bool:
    pz, oz = _zone_kind(pos), _zone_kind(ocr)
    if pz != oz:
        return False
    if pz == "hardsub":
        return (
            box_iou(pos, ocr) >= HARDSUB_MIN_IOU
            or horizontal_overlap_frac(pos, ocr) >= HARDSUB_MIN_H_OVERLAP
        )
    if pz == "title":
        return box_iou(pos, ocr) >= TITLE_MIN_IOU
    return box_iou(pos, ocr) >= TITLE_MIN_IOU


def attach_text_to_position_boxes(
    position_boxes: Sequence[TimedBox],
    *,
    time_ms: int,
    segments: Sequence[OcrTextSegment],
) -> list[TimedBox]:
    """Attach OCR text to current-frame boxes when zone + overlap match."""
    active = [s for s in segments if s.start_ms <= int(time_ms) < s.end_ms]
    if not active or not position_boxes:
        return [
            TimedBox(x=b.x, y=b.y, w=b.w, h=b.h, text="", confidence=0.0)
            for b in position_boxes
        ]
    ocr_boxes = [b for s in active for b in s.boxes]
    out: list[TimedBox] = []
    used_ocr: set[int] = set()
    for pos in position_boxes:
        best: TimedBox | None = None
        best_j = -1
        best_score = -1.0
        for j, ocr in enumerate(ocr_boxes):
            if j in used_ocr:
                continue
            if not _boxes_overlap_for_zone(pos, ocr):
                continue
            score = box_iou(pos, ocr)
            if _zone_kind(pos) == "hardsub":
                score = max(score, horizontal_overlap_frac(pos, ocr))
            if score > best_score:
                best_score = score
                best = ocr
                best_j = j
        if best is not None and best_j >= 0:
            used_ocr.add(best_j)
            out.append(
                TimedBox(
                    x=pos.x,
                    y=pos.y,
                    w=pos.w,
                    h=pos.h,
                    text=best.text,
                    confidence=best.confidence,
                )
            )
        else:
            out.append(
                TimedBox(x=pos.x, y=pos.y, w=pos.w, h=pos.h, text="", confidence=0.0)
            )
    return out


def merge_position_and_ocr_timelines(
    position_rows: Sequence[dict[str, Any]],
    segments: Sequence[OcrTextSegment],
) -> list[dict[str, Any]]:
    """Apply V3 evidence gate to local per-frame geometry and OCR segments."""
    merged: list[dict[str, Any]] = []
    duration_ms = max(
        (int(row.get("time_ms") or 0) for row in position_rows),
        default=0,
    )
    for row in position_rows:
        raw = row.get("boxes") or []
        pos_boxes = [
            TimedBox(
                x=float(b["x"]),
                y=float(b["y"]),
                w=float(b.get("w") or b.get("width") or 0.0),
                h=float(b.get("h") or b.get("height") or 0.0),
            )
            for b in raw
        ]
        time_ms = int(row["time_ms"])
        active_segments = [
            segment
            for segment in segments
            if segment.start_ms <= time_ms < segment.end_ms
        ]
        ocr_boxes = tuple(box for segment in active_segments for box in segment.boxes)
        evidence = FrameEvidence(
            frame_index=int(row["frame_index"]),
            time_ms=time_ms,
            local_boxes=tuple(pos_boxes),
            ocr_boxes=ocr_boxes,
            timeline_ratio=(
                float(time_ms) / float(duration_ms)
                if duration_ms > 0
                else 0.0
            ),
        )
        approved = authority_boxes_for_frame(evidence)
        text_sources = [
            segment.start_ms
            for segment in active_segments
            if approved and segment.boxes
        ]
        merged.append(
            {
                "frame_index": int(row["frame_index"]),
                "time_ms": time_ms,
                "boxes": [b.to_dict() for b in approved],
                "position_source_frame": int(row["frame_index"]),
                "text_segment_ms": text_sources[0] if text_sources else None,
                "frame_state": classify_frame_state(evidence),
                "evidence": "ocr_cjk+local_layout" if approved else "none",
            }
        )
    return merged


def merge_position_and_observation_timelines(
    position_rows: Sequence[dict[str, Any]],
    observations: Sequence[OcrObservation],
    *,
    duration_ms: int,
    observation_sources: dict[int, int],
    visual_signatures: dict[int, FrameVisualSignature],
) -> list[dict[str, Any]]:
    """V3.1 authority: activate content from evidence on this exact frame."""
    time_to_index = {
        int(row.get("time_ms") or 0): int(row.get("frame_index") or 0)
        for row in position_rows
    }

    def _nearest_frame_index(time_ms: int) -> int | None:
        if not time_to_index:
            return None
        return time_to_index.get(int(time_ms), min(time_to_index, key=lambda t: abs(t - int(time_ms))))

    glyph_by_source_time: dict[int, np.ndarray] = {}
    for source_time in set(observation_sources.values()):
        source_index = _nearest_frame_index(source_time)
        signature = visual_signatures.get(source_index) if source_index is not None else None
        if signature is not None:
            glyph_by_source_time[int(source_time)] = signature.glyph

    endcard_observations = [
        observation
        for observation in observations
        if observation.boxes
        and classify_frame_state(
            FrameEvidence(
                frame_index=0,
                time_ms=observation.time_ms,
                ocr_boxes=observation.boxes,
                timeline_ratio=1.0,
            )
        )
        == "endcard"
    ]

    merged: list[dict[str, Any]] = []
    for row in position_rows:
        frame_index = int(row["frame_index"])
        time_ms = int(row["time_ms"])
        local_boxes = tuple(_local_geometry_boxes_from_row(row))
        band_top = subtitle_band_top_normalized()
        local_mid_title = any(
            is_mid_title_box(
                {"x": box.x, "y": box.y, "width": box.w, "height": box.h}
            )
            for box in local_boxes
        )
        local_hardsub_boxes = [
            {
                "x": float(box.x),
                "y": float(box.y),
                "w": float(box.w),
                "h": float(box.h),
            }
            for box in local_boxes
            if float(box.y) + float(box.h) * 0.5 + 1e-9 >= band_top
            and float(box.w) >= 0.12
        ]
        local_hardsub_bottom = bool(local_hardsub_boxes)
        current_visual = visual_signatures.get(frame_index)
        activation = activate_frame_from_observations(
            frame_index=frame_index,
            time_ms=time_ms,
            local_boxes=local_boxes,
            observations=observations,
            duration_ms=duration_ms,
            current_glyph_mask=(
                current_visual.glyph if current_visual is not None else None
            ),
            candidate_glyph_masks=glyph_by_source_time,
            observation_sources=observation_sources,
        )
        selected_time = activation.get("candidate_time_ms")
        if selected_time is not None:
            selected_source_time = observation_sources.get(
                int(selected_time),
                int(selected_time),
            )
            activation["candidate_frame"] = _nearest_frame_index(
                selected_source_time
            )

        best_endcard: tuple[float, OcrObservation, int] | None = None
        for observation in endcard_observations:
            source_time = observation_sources.get(
                int(observation.time_ms),
                int(observation.time_ms),
            )
            source_index = _nearest_frame_index(source_time)
            source_visual = (
                visual_signatures.get(source_index)
                if source_index is not None
                else None
            )
            if current_visual is None or source_visual is None:
                continue
            scene_match = scene_signature_similarity(
                current_visual.scene,
                source_visual.scene,
            )
            if scene_match < MIN_ENDCARD_SCENE_SIMILARITY:
                continue
            evidence = FrameEvidence(
                frame_index=frame_index,
                time_ms=time_ms,
                local_boxes=local_boxes,
                ocr_boxes=observation.boxes,
                timeline_ratio=(
                    float(time_ms) / float(duration_ms)
                    if duration_ms > 0
                    else 0.0
                ),
            )
            approved = authority_boxes_for_frame(evidence)
            if not approved or classify_frame_state(evidence) != "endcard":
                continue
            if best_endcard is None or scene_match > best_endcard[0]:
                best_endcard = (scene_match, observation, int(source_index))

        if best_endcard is not None:
            scene_match, observation, source_index = best_endcard
            evidence = FrameEvidence(
                frame_index=frame_index,
                time_ms=time_ms,
                local_boxes=local_boxes,
                ocr_boxes=observation.boxes,
                timeline_ratio=(
                    float(time_ms) / float(duration_ms)
                    if duration_ms > 0
                    else 0.0
                ),
            )
            approved = authority_boxes_for_frame(evidence)
            approved = attach_text_to_current_frame_geometry(
                approved,
                local_boxes,
                require_all=True,
                include_unmatched=True,
            )
            if approved:
                activation = {
                    "boxes": approved,
                    "frame_state": "endcard",
                    "activation_source": "scene+current_geometry+full_ocr_text",
                    "activation_score": round(float(scene_match), 6),
                    "candidate_time_ms": int(observation.time_ms),
                    "candidate_frame": source_index,
                    "glyph_match": None,
                    "scene_match": round(float(scene_match), 6),
                    "ocr_candidate_count": 1,
                }

        approved_boxes = [
            with_authority_cover_bounds(box)
            for box in activation["boxes"]
        ]
        merged.append(
            {
                "frame_index": frame_index,
                "time_ms": time_ms,
                "boxes": [box.to_dict() for box in approved_boxes],
                "position_source_frame": frame_index,
                "text_segment_ms": activation.get("candidate_time_ms"),
                "candidate_frame": activation.get("candidate_frame"),
                "frame_state": activation["frame_state"],
                "evidence": (
                    "ocr+exact_frame_activation" if approved_boxes else "none"
                ),
                "activation_source": activation["activation_source"],
                "activation_score": activation["activation_score"],
                "glyph_match": activation.get("glyph_match"),
                "scene_match": activation.get("scene_match"),
                "ocr_candidate_count": int(
                    activation.get("ocr_candidate_count") or 0
                ),
                "local_mid_title": local_mid_title,
                "local_hardsub_bottom": local_hardsub_bottom,
                "local_hardsub_boxes": local_hardsub_boxes,
            }
        )
    return fill_title_local_gaps(
        fill_hardsub_local_gaps(merged, max_gap_ms=MAX_HARDSUB_LOCAL_GAP_MS),
        max_gap_ms=MAX_TITLE_LOCAL_GAP_MS,
    )


def _hardsub_caption_key(frame: Mapping[str, Any]) -> str | None:
    if str(frame.get("frame_state") or "") != "hardsub":
        return None
    boxes = frame.get("boxes") or []
    if not boxes:
        return None
    return "|".join(str(box.get("text") or "").strip() for box in boxes)


def _normalize_hardsub_caption(text: str) -> str:
    return "".join(str(text or "").split())


def _hardsub_captions_compatible(
    left: str,
    right: str,
    *,
    min_ratio: float = 0.62,
    min_shared_chars: int = 5,
) -> bool:
    """True when two OCR readings are the same caption (including partial variants)."""
    from difflib import SequenceMatcher

    a = _normalize_hardsub_caption(left)
    b = _normalize_hardsub_caption(right)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    # Partial Cloud OCR often returns a contiguous subset of the full line.
    if len(short) >= 4 and short in long:
        return True
    matcher = SequenceMatcher(None, a, b)
    shared = sum(block.size for block in matcher.get_matching_blocks())
    return matcher.ratio() >= float(min_ratio) and shared >= int(min_shared_chars)


def _prefer_hardsub_hold_text(
    left: Mapping[str, Any],
    right: Mapping[str, Any] | None,
) -> str:
    """Choose the longer compatible caption string; geometry stays current-local."""
    left_key = _hardsub_caption_key(left) or ""
    if right is None:
        return left_key
    right_key = _hardsub_caption_key(right) or ""
    if len(_normalize_hardsub_caption(right_key)) > len(
        _normalize_hardsub_caption(left_key)
    ):
        return right_key
    return left_key


def _remap_held_hardsub_to_local_geometry(
    *,
    text: str,
    confidence: float,
    local_hardsub_boxes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not local_hardsub_boxes:
        return []
    best = max(
        local_hardsub_boxes,
        key=lambda box: float(box.get("w") or box.get("width") or 0.0)
        * float(box.get("h") or box.get("height") or 0.0),
    )
    width = float(best.get("w") or best.get("width") or 0.0)
    height = float(best.get("h") or best.get("height") or 0.0)
    if width <= 0.0 or height <= 0.0:
        return []
    return [
        {
            "x": float(best["x"]),
            "y": float(best["y"]),
            "w": width,
            "h": height,
            "text": text,
            "confidence": float(confidence),
        }
    ]


def fill_hardsub_local_gaps(
    frames: Sequence[dict[str, Any]],
    *,
    max_gap_ms: int = MAX_HARDSUB_LOCAL_GAP_MS,
) -> list[dict[str, Any]]:
    """Hold hardsub text across short gaps only with current bottom geometry.

    Exact-frame activation stays primary. Blank frames may inherit neighbor
    caption text when they still have bottom-band local boxes. Geometry always
    comes from the current frame — never from a future anchor.
    """
    out = [dict(frame) for frame in frames]
    if not out:
        return out

    for index, frame in enumerate(out):
        if str(frame.get("frame_state") or "") != "blank":
            continue
        if frame.get("boxes"):
            continue
        if not frame.get("local_hardsub_bottom"):
            continue
        local_boxes = [
            box
            for box in (frame.get("local_hardsub_boxes") or [])
            if isinstance(box, Mapping)
        ]
        if not local_boxes:
            continue
        time_ms = int(frame.get("time_ms") or 0)

        prev_index: int | None = None
        for candidate in range(index - 1, -1, -1):
            key = _hardsub_caption_key(out[candidate])
            if key is None:
                continue
            if abs(time_ms - int(out[candidate].get("time_ms") or 0)) > int(max_gap_ms):
                break
            prev_index = candidate
            break
        if prev_index is None:
            continue

        next_index: int | None = None
        for candidate in range(index + 1, len(out)):
            key = _hardsub_caption_key(out[candidate])
            if key is None:
                continue
            if abs(int(out[candidate].get("time_ms") or 0) - time_ms) > int(max_gap_ms):
                break
            next_index = candidate
            break

        prev_key = _hardsub_caption_key(out[prev_index])
        if not prev_key:
            continue
        next_frame = out[next_index] if next_index is not None else None
        next_key = _hardsub_caption_key(next_frame) if next_frame is not None else None
        if next_key is not None and not _hardsub_captions_compatible(prev_key, next_key):
            continue

        text = _prefer_hardsub_hold_text(out[prev_index], next_frame)
        text_source = (
            next_frame
            if next_frame is not None
            and _normalize_hardsub_caption(text)
            == _normalize_hardsub_caption(_hardsub_caption_key(next_frame) or "")
            else out[prev_index]
        )
        confidences = [
            float(box.get("confidence") or 0.0)
            for box in (text_source.get("boxes") or [])
        ]
        held_boxes = _remap_held_hardsub_to_local_geometry(
            text=text,
            confidence=max(confidences) if confidences else 0.0,
            local_hardsub_boxes=local_boxes,
        )
        if not held_boxes:
            continue
        frame["boxes"] = held_boxes
        frame["frame_state"] = "hardsub"
        frame["evidence"] = "ocr+neighbor_hardsub_hold"
        frame["activation_source"] = "hardsub_local_gap_hold"
        frame["activation_score"] = float(text_source.get("activation_score") or 0.0)
        frame["text_segment_ms"] = text_source.get("text_segment_ms")
        frame["candidate_frame"] = text_source.get("candidate_frame")
        frame["glyph_match"] = text_source.get("glyph_match")
        frame["position_source_frame"] = int(frame.get("frame_index") or index)
        frame["ocr_candidate_count"] = int(text_source.get("ocr_candidate_count") or 0)
    return out


def fill_title_local_gaps(
    frames: Sequence[dict[str, Any]],
    *,
    max_gap_ms: int = MAX_TITLE_LOCAL_GAP_MS,
) -> list[dict[str, Any]]:
    """Hold opening mid-title boxes across short blanks until hardsub/endcard.

    Thumbnails are brief; local CTC may only verify a few early frames. Hold the
    last title forward while blank and within ``max_gap_ms``, then stop when a
    hardsub/endcard appears or the gap budget expires.

    Hold requires current-frame mid-title local geometry (``local_mid_title``).
    Without it, pasting the previous title boxes paints food after the title
    fades.
    """
    out = [dict(frame) for frame in frames]
    if not out:
        return out

    last_title: dict[str, Any] | None = None
    last_title_ms: int | None = None
    for frame in out:
        state = str(frame.get("frame_state") or "")
        time_ms = int(frame.get("time_ms") or 0)
        if state == "title" and frame.get("boxes"):
            last_title = frame
            last_title_ms = time_ms
            continue
        if state in {"hardsub", "endcard"}:
            last_title = None
            last_title_ms = None
            continue
        if state != "blank" or frame.get("boxes"):
            continue
        if not frame.get("local_mid_title"):
            continue
        if last_title is None or last_title_ms is None:
            continue
        if time_ms - int(last_title_ms) > int(max_gap_ms):
            last_title = None
            last_title_ms = None
            continue
        held_boxes = [dict(box) for box in (last_title.get("boxes") or [])]
        if not held_boxes:
            continue
        frame["boxes"] = held_boxes
        frame["frame_state"] = "title"
        frame["evidence"] = "ocr+neighbor_title_hold"
        frame["activation_source"] = "title_local_gap_hold"
        frame["activation_score"] = float(last_title.get("activation_score") or 0.0)
        frame["text_segment_ms"] = last_title.get("text_segment_ms")
        frame["candidate_frame"] = last_title.get("candidate_frame")
        frame["glyph_match"] = last_title.get("glyph_match")
        frame["position_source_frame"] = last_title.get(
            "position_source_frame",
            last_title.get("frame_index"),
        )
        frame["ocr_candidate_count"] = int(last_title.get("ocr_candidate_count") or 0)
    return out


def _run_cloud_ocr_ticks(
    video_path: Path,
    sample_times: list[int],
    *,
    duration_ms: int,
    concurrency: int | None,
    use_mid_title_band: bool,
    cache_path: Path | None = None,
    cache_batch_size: int = DEFAULT_CACHE_BATCH_SIZE,
    use_temporal_consensus: bool = False,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    enable_offset_fallback: bool = True,
    cloud_metrics: dict[str, int] | None = None,
) -> list[OcrObservation]:
    with tempfile.TemporaryDirectory(prefix="pfa_ocr_") as tmp:
        tmp_path = Path(tmp)
        stills = _extract_stills_at_times(video_path, sample_times, tmp_path / "full")
        endpoint = resolve_ocr_endpoint_url()
        crop_jobs: list[tuple[int, Path, float, float]] = []
        for t_ms, full in stills:
            hard_path, y0, y1 = _bottom_band_crop(full, tmp_path / "crops", stem=f"t{t_ms:06d}")
            crop_jobs.append((t_ms, hard_path, y0, y1))
            if use_mid_title_band and int(t_ms) <= 2500:
                mid_path, my0, my1 = _mid_title_band_crop(
                    full, tmp_path / "crops", stem=f"t{t_ms:06d}"
                )
                crop_jobs.append((t_ms, mid_path, my0, my1))

        paths = [c[1] for c in crop_jobs]
        if cache_path is not None:
            detections = process_ocr_paths_with_cache(
                paths,
                endpoint_url=endpoint,
                cache_path=cache_path,
                concurrency=concurrency,
                batch_size=cache_batch_size,
                cache_namespace=_ocr_cache_namespace(
                    endpoint,
                    min_confidence=min_confidence,
                    crop_kind="hard+mid",
                ),
                metrics=cloud_metrics,
            )
        else:
            detections = process_all_frames_sync(
                paths,
                endpoint_url=endpoint,
                concurrency=concurrency,
            )
        by_time: dict[int, list[DetectedTextBox]] = {}
        for (t_ms, _path, y0, y1), det in zip(crop_jobs, detections, strict=True):
            remapped = [
                remap_box_from_vertical_crop(b, y0_norm=y0, y1_norm=y1)
                if (y0 > 0.0 or y1 < 1.0)
                else b
                for b in det.boxes
            ]
            by_time.setdefault(t_ms, []).extend(remapped)

        ocr_frames: list[dict[str, Any]] = []
        for t_ms in sorted(by_time.keys()):
            ocr_frames.append(
                {
                    "time_ms": t_ms,
                    "boxes": [
                        {
                            "x": b.x,
                            "y": b.y,
                            "w": b.width,
                            "h": b.height,
                            "text": b.text,
                            "confidence": b.confidence,
                        }
                        for b in by_time[t_ms]
                    ],
                }
            )
        raw = observations_from_ocr_payload(ocr_frames, min_confidence=0.0, require_text=True)
        if use_temporal_consensus:
            obs = apply_temporal_consensus(raw, min_hits=2)
            return collapse_nearby_observations(obs, gap_ms=900)

        # One stable keyframe represents one caption state. Do not require the
        # same text to appear at multiple OCR ticks; that would discard every
        # unique caption. Preserve empty ticks as segment boundaries.
        cleaned = [
            OcrObservation(
                time_ms=o.time_ms,
                boxes=tuple(
                    merge_horizontal_line_boxes(
                        filter_authority_boxes(
                            o.boxes,
                            min_confidence=min_confidence,
                        )
                    )
                ),
            )
            for o in raw
        ]

        retries = (
            fallback_times_for_empty_observations(
                cleaned,
                duration_ms=duration_ms,
            )
            if enable_offset_fallback
            else []
        )
        if not retries:
            return cleaned

        retry_stills = _extract_stills_at_times(
            video_path,
            [retry_ms for _original_ms, retry_ms in retries],
            tmp_path / "fallback_full",
        )
        still_by_time = {time_ms: path for time_ms, path in retry_stills}
        retry_jobs: list[tuple[int, int, Path, float, float]] = []
        for original_ms, retry_ms in retries:
            full = still_by_time.get(retry_ms)
            if full is None:
                continue
            hard_path, y0, y1 = _bottom_band_crop(
                full,
                tmp_path / "fallback_crops",
                stem=f"fallback_t{retry_ms:06d}",
            )
            retry_jobs.append((original_ms, retry_ms, hard_path, y0, y1))
            if use_mid_title_band and retry_ms <= 2500:
                mid_path, my0, my1 = _mid_title_band_crop(
                    full,
                    tmp_path / "fallback_crops",
                    stem=f"fallback_t{retry_ms:06d}",
                )
                retry_jobs.append((original_ms, retry_ms, mid_path, my0, my1))

        retry_paths = [job[2] for job in retry_jobs]
        if cache_path is not None:
            retry_detections = process_ocr_paths_with_cache(
                retry_paths,
                endpoint_url=endpoint,
                cache_path=cache_path,
                concurrency=concurrency,
                batch_size=cache_batch_size,
                cache_namespace=_ocr_cache_namespace(
                    endpoint,
                    min_confidence=min_confidence,
                    crop_kind="hard+mid",
                ),
                metrics=cloud_metrics,
            )
        else:
            retry_detections = process_all_frames_sync(
                retry_paths,
                endpoint_url=endpoint,
                concurrency=concurrency,
            )

        retry_by_original: dict[int, list[DetectedTextBox]] = {}
        for (original_ms, _retry_ms, _path, y0, y1), detection in zip(
            retry_jobs,
            retry_detections,
            strict=True,
        ):
            retry_by_original.setdefault(original_ms, []).extend(
                [
                    remap_box_from_vertical_crop(box, y0_norm=y0, y1_norm=y1)
                    if (y0 > 0.0 or y1 < 1.0)
                    else box
                    for box in detection.boxes
                ]
            )

        replacements: dict[int, tuple[TimedBox, ...]] = {}
        for original_ms, boxes in retry_by_original.items():
            timed = tuple(
                TimedBox(
                    x=box.x,
                    y=box.y,
                    w=box.width,
                    h=box.height,
                    text=box.text,
                    confidence=box.confidence,
                )
                for box in boxes
            )
            replacements[original_ms] = tuple(
                merge_horizontal_line_boxes(
                    filter_authority_boxes(timed, min_confidence=min_confidence)
                )
            )

        return [
            OcrObservation(
                time_ms=observation.time_ms,
                boxes=replacements.get(observation.time_ms) or observation.boxes,
            )
            for observation in cleaned
        ]


def _run_cloud_ocr_segments(
    video_path: Path,
    segments: Sequence[GlyphSegment],
    *,
    duration_ms: int,
    concurrency: int | None,
    use_mid_title_band: bool,
    cache_path: Path,
    cache_batch_size: int,
    min_confidence: float,
    cloud_metrics: dict[str, int] | None = None,
) -> tuple[list[OcrObservation], dict[int, int]]:
    """OCR ranked candidates by round; stop spending once a segment succeeds."""
    observations_by_candidate: dict[int, OcrObservation] = {}
    successful_segments: set[int] = set()
    max_rank = max((len(segment.candidate_times_ms) for segment in segments), default=0)
    for rank in range(max_rank):
        round_times: list[int] = []
        owners: dict[int, list[int]] = {}
        for segment in segments:
            if not segment.has_glyph or segment.segment_id in successful_segments:
                continue
            if rank >= len(segment.candidate_times_ms):
                continue
            candidate_time = int(segment.candidate_times_ms[rank])
            round_times.append(candidate_time)
            owners.setdefault(candidate_time, []).append(segment.segment_id)
        round_times = sorted(set(round_times))
        if not round_times:
            continue

        round_observations = _run_cloud_ocr_ticks(
            video_path,
            round_times,
            duration_ms=duration_ms,
            concurrency=concurrency,
            use_mid_title_band=use_mid_title_band,
            cache_path=cache_path,
            cache_batch_size=cache_batch_size,
            use_temporal_consensus=False,
            min_confidence=min_confidence,
            enable_offset_fallback=False,
            cloud_metrics=cloud_metrics,
        )
        for observation in round_observations:
            observations_by_candidate[int(observation.time_ms)] = observation
            if observation.boxes:
                successful_segments.update(owners.get(int(observation.time_ms), []))

    chosen = [
        choose_segment_observation(segment, observations_by_candidate)
        for segment in segments
    ]
    sources: dict[int, int] = {}
    for segment, observation in zip(segments, chosen, strict=True):
        if not observation.boxes:
            continue
        for candidate_time in segment.candidate_times_ms:
            candidate = observations_by_candidate.get(int(candidate_time))
            if candidate is not None and candidate.boxes:
                sources[int(segment.start_ms)] = int(candidate_time)
                break
    return chosen, sources


def merge_endcard_candidate_boxes(
    candidate_boxes: Sequence[Sequence[TimedBox]],
) -> list[TimedBox]:
    """Consensus end-card OCR boxes, clipped to the normalized frame."""
    merged: list[TimedBox] = []
    for boxes in candidate_boxes:
        for source in boxes:
            x = max(0.0, min(1.0, float(source.x)))
            y = max(0.0, min(1.0, float(source.y)))
            w = max(0.0, min(float(source.w), 1.0 - x))
            h = max(0.0, min(float(source.h), 1.0 - y))
            if w <= 0.0 or h <= 0.0 or not (source.text or "").strip():
                continue
            box = TimedBox(
                x=x,
                y=y,
                w=w,
                h=h,
                text=(source.text or "").strip(),
                confidence=source.confidence,
            )
            match_index: int | None = None
            for index, existing in enumerate(merged):
                center_distance = (
                    (
                        (existing.x + existing.w / 2.0)
                        - (box.x + box.w / 2.0)
                    )
                    ** 2
                    + (
                        (existing.y + existing.h / 2.0)
                        - (box.y + box.h / 2.0)
                    )
                    ** 2
                ) ** 0.5
                if box_iou(existing, box) >= 0.30 or center_distance <= 0.035:
                    match_index = index
                    break
            if match_index is None:
                merged.append(box)
                continue
            existing = merged[match_index]
            existing_quality = (
                len((existing.text or "").strip()),
                float(existing.confidence),
            )
            box_quality = (len(box.text), float(box.confidence))
            if box_quality > existing_quality:
                merged[match_index] = box
    return sorted(merged, key=lambda box: (float(box.y), float(box.x)))


def _run_full_frame_endcard_ocr(
    video_path: Path,
    segments: Sequence[EndcardSegment],
    *,
    concurrency: int | None,
    cache_path: Path,
    cache_batch_size: int,
    min_confidence: float,
    cloud_metrics: dict[str, int] | None = None,
) -> tuple[list[OcrObservation], dict[int, int]]:
    """OCR up to two strong end-card candidates and merge their text boxes."""
    if not segments:
        return [], {}
    successful: dict[int, list[tuple[int, tuple[TimedBox, ...]]]] = {}
    source_times: dict[int, int] = {}
    max_rank = max((len(segment.candidate_times_ms) for segment in segments), default=0)
    with tempfile.TemporaryDirectory(prefix="v3_endcard_") as tmp:
        tmp_path = Path(tmp)
        for rank in range(max_rank):
            pending = [
                segment
                for segment in segments
                if len(successful.get(segment.segment_id, [])) < 2
                and rank < min(2, len(segment.candidate_times_ms))
            ]
            if not pending:
                continue
            times = sorted(
                {
                    int(segment.candidate_times_ms[rank])
                    for segment in pending
                }
            )
            stills = _extract_stills_at_times(video_path, times, tmp_path / f"rank_{rank}")
            path_by_time = {time_ms: path for time_ms, path in stills}
            paths = [path_by_time[time_ms] for time_ms in times if time_ms in path_by_time]
            detections = process_ocr_paths_with_cache(
                paths,
                endpoint_url=resolve_ocr_endpoint_url(),
                cache_path=cache_path,
                concurrency=concurrency,
                batch_size=cache_batch_size,
                cache_namespace=_ocr_cache_namespace(
                    resolve_ocr_endpoint_url(),
                    min_confidence=min_confidence,
                    crop_kind="full-endcard",
                ),
                metrics=cloud_metrics,
            )
            detected_by_time = {
                time_ms: detection
                for time_ms, detection in zip(
                    [time_ms for time_ms in times if time_ms in path_by_time],
                    detections,
                    strict=True,
                )
            }
            for segment in pending:
                candidate_time = int(segment.candidate_times_ms[rank])
                detection = detected_by_time.get(candidate_time)
                if detection is None:
                    continue
                raw = [
                    TimedBox(
                        x=box.x,
                        y=box.y,
                        w=box.width,
                        h=box.height,
                        text=box.text,
                        confidence=box.confidence,
                    )
                    for box in detection.boxes
                ]
                verified = tuple(
                    verified_endcard_boxes(raw, min_confidence=min_confidence)
                )
                state = classify_frame_state(
                    FrameEvidence(
                        frame_index=0,
                        time_ms=segment.start_ms,
                        ocr_boxes=verified,
                        timeline_ratio=1.0,
                    )
                )
                if state == "endcard":
                    successful.setdefault(segment.segment_id, []).append(
                        (candidate_time, verified)
                    )
                    source_times.setdefault(int(segment.start_ms), candidate_time)

    return (
        [
            OcrObservation(
                time_ms=segment.start_ms,
                boxes=tuple(
                    merge_endcard_candidate_boxes(
                        [
                            boxes
                            for _candidate_time, boxes in successful.get(
                                segment.segment_id,
                                [],
                            )
                        ]
                    )
                ),
            )
            for segment in segments
        ],
        source_times,
    )


def run_per_frame_position_authority(
    video_source: str | Path,
    *,
    out_json: Path,
    overlay_dir: Path | None = None,
    overlay_all: bool = False,
    overlay_indices: list[int] | None = None,
    overlay_diagnostic: bool = False,
    concurrency: int | None = 2,
    use_change_ticks: bool = True,
    use_mid_title_band: bool = True,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    frame_stride: int = 1,
    positions_json: Path | None = None,
    change_authority: str = "glyph",
    ocr_cache_path: Path | None = None,
    ocr_batch_size: int = DEFAULT_CACHE_BATCH_SIZE,
) -> dict[str, Any]:
    with resolve_video_source(video_source) as video_path:
        frame_times = _all_frame_times_ms(video_path)
        duration_ms = frame_times[-1] if frame_times else 0
        video_fingerprint = video_content_fingerprint(video_path)
        position_cache_path = positions_json
        if position_cache_path is None and ocr_cache_path is not None:
            position_cache_path = Path(ocr_cache_path).with_suffix(
                ".positions.json"
            )

        cached: dict[str, Any] | None = None
        detector: LocalTextDetector | None = None
        if position_cache_path is not None and Path(position_cache_path).is_file():
            cached = json.loads(
                Path(position_cache_path).read_text(encoding="utf-8")
            )
        if cached is not None and position_cache_matches_video(cached, video_path):
            position_rows = refresh_positions_with_ink_hardsub(
                video_path, cached.get("frames") or []
            )
            logger.info("ink+dbnet cache positions frames=%s", len(position_rows))
        else:
            if cached is not None:
                logger.warning(
                    "position_cache_rejected reason=missing_or_mismatched_video_fingerprint"
                )
            model = ensure_dbnet_onnx(None)
            detector = LocalTextDetector(model)
            position_rows = detect_positions_timeline(
                video_path, detector=detector, frame_stride=frame_stride
            )
            if position_cache_path is not None:
                position_cache_path.parent.mkdir(parents=True, exist_ok=True)
                position_payload = {
                    "video": str(video_path.resolve()),
                    "video_fingerprint": video_fingerprint,
                    "detector": "dbnet_onnx",
                    "stride": int(frame_stride),
                    "frame_count": len(frame_times),
                    "evaluated_frames": len(position_rows),
                    "frames": position_rows,
                }
                temp_position_cache = position_cache_path.with_name(
                    f"{position_cache_path.name}.tmp"
                )
                temp_position_cache.write_text(
                    json.dumps(position_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                temp_position_cache.replace(position_cache_path)

        provisional_endcards = detect_endcard_segments(
            position_rows,
            duration_ms=duration_ms,
        )
        recognizer_model, recognizer_dictionary = ensure_text_recognizer_assets()
        recognizer = LocalTextRecognizer(recognizer_model, recognizer_dictionary)
        position_rows, local_verification_metrics = verify_position_rows(
            video_path,
            position_rows,
            recognizer=recognizer,
            provisional_endcards=provisional_endcards,
        )
        endcard_segments = detect_endcard_segments(
            position_rows,
            duration_ms=duration_ms,
            max_candidates=MAX_CLOUD_CANDIDATES_PER_GLYPH_EVENT,
        )

        glyph_segments: list[GlyphSegment] = []
        if use_change_ticks:
            if str(change_authority).strip().lower() == "glyph":
                glyph_segments = sample_subtitle_glyph_segments(video_path)
                glyph_segments = route_verified_glyph_segments(
                    glyph_segments,
                    position_rows,
                )
                sample_times = [
                    segment.candidate_times_ms[0]
                    for segment in glyph_segments
                    if segment.has_glyph and segment.candidate_times_ms
                ]
            else:
                from src.media_pipeline.ocr_filtering.bottom_band_change_ticks import (
                    sample_bottom_band_change_times_ms,
                )

                sample_times = sample_bottom_band_change_times_ms(video_path)
                sample_times = route_verified_sample_times(sample_times, position_rows)
        else:
            sample_times = sorted(set(frame_times[:: max(1, len(frame_times) // 30)]))
            sample_times = route_verified_sample_times(sample_times, position_rows)

        cache_path = ocr_cache_path or out_json.with_suffix(".ocr-cache.json")
        cloud_metrics: dict[str, int] = {
            "requested": 0,
            "cache_hits": 0,
            "cloud_requests": 0,
        }
        observation_sources: dict[int, int] = {}
        if glyph_segments:
            observations, observation_sources = _run_cloud_ocr_segments(
                video_path,
                glyph_segments,
                duration_ms=duration_ms,
                concurrency=concurrency,
                use_mid_title_band=use_mid_title_band,
                cache_path=cache_path,
                cache_batch_size=ocr_batch_size,
                min_confidence=min_confidence,
                cloud_metrics=cloud_metrics,
            )
        else:
            observations = _run_cloud_ocr_ticks(
                video_path,
                sample_times,
                duration_ms=duration_ms,
                concurrency=concurrency,
                use_mid_title_band=use_mid_title_band,
                cache_path=cache_path,
                cache_batch_size=ocr_batch_size,
                use_temporal_consensus=str(change_authority).strip().lower() != "glyph",
                min_confidence=min_confidence,
                cloud_metrics=cloud_metrics,
            )
            observation_sources = {
                int(observation.time_ms): int(observation.time_ms)
                for observation in observations
            }
        endcard_observations, endcard_sources = _run_full_frame_endcard_ocr(
            video_path,
            endcard_segments,
            concurrency=concurrency,
            cache_path=cache_path,
            cache_batch_size=ocr_batch_size,
            min_confidence=min_confidence,
            cloud_metrics=cloud_metrics,
        )
        if endcard_segments:
            first_endcard_ms = min(segment.start_ms for segment in endcard_segments)
            observations = [
                observation
                for observation in observations
                if observation.time_ms < first_endcard_ms
            ]
            observations.extend(endcard_observations)
            observation_sources.update(endcard_sources)
            for segment in endcard_segments:
                if segment.end_ms <= duration_ms:
                    observations.append(
                        OcrObservation(time_ms=segment.end_ms, boxes=())
                    )
            observations.sort(key=lambda observation: observation.time_ms)
        observations = repair_adjacent_partial_text(observations)
        filtered = [
            OcrObservation(
                time_ms=o.time_ms,
                boxes=tuple(
                    b
                    for b in o.boxes
                    if float(b.confidence) >= float(min_confidence) or not b.confidence
                ),
            )
            for o in observations
        ]
        if detector is None:
            detector = LocalTextDetector(ensure_dbnet_onnx(None))
        position_rows = refine_positions_for_ocr_authority(
            video_path,
            position_rows,
            filtered,
            endcard_segments,
            detector=detector,
            recognizer=recognizer,
        )
        segments = build_ocr_text_segments(filtered, duration_ms=duration_ms)
        visual_signatures = collect_frame_visual_signatures(video_path)
        frames = merge_position_and_observation_timelines(
            position_rows,
            filtered,
            duration_ms=duration_ms,
            observation_sources=observation_sources,
            visual_signatures=visual_signatures,
        )

        payload: dict[str, Any] = {
            "video": str(video_path.resolve()),
            "video_fingerprint": video_fingerprint,
            "authority": "ocr_authority_v3.6",
            "frame_count": len(frame_times),
            "ocr_ticks": len(sample_times),
            "ocr_candidate_budget": sum(
                len(segment.candidate_times_ms)
                for segment in glyph_segments
                if segment.has_glyph
            )
            if glyph_segments
            else len(sample_times),
            "endcard_mode": "text_only",
            "endcard_segments": len(endcard_segments),
            "endcard_candidate_budget": sum(
                len(segment.candidate_times_ms)
                for segment in endcard_segments
            ),
            "ocr_segments": len(segments),
            "min_confidence": min_confidence,
            "use_change_ticks": use_change_ticks,
            "change_authority": change_authority if use_change_ticks else "fixed_grid",
            "ocr_cache_path": str(cache_path),
            "position_cache_path": (
                str(position_cache_path) if position_cache_path is not None else None
            ),
            "ocr_batch_size": int(ocr_batch_size),
            "position_hold_forward": False,
            "highres_dbnet_long_edge": HIGH_RES_AUTHORITY_LONG_EDGE,
            "highres_dbnet_budget": MAX_HIGH_RES_AUTHORITY_FRAMES,
            "highres_dbnet_frames": sum(
                1 for row in position_rows if row.get("position_resolution")
            ),
            "highres_dbnet_skipped": sum(
                1 for row in position_rows if row.get("high_res_skipped")
            ),
            "local_verifier_mode": "event_track_batched_blank_exit_two_frame",
            "local_text_verification": local_verification_metrics,
            "cloud_ocr_metrics": cloud_metrics,
            "ocr_observations": [
                {
                    "time_ms": o.time_ms,
                    "candidate_time_ms": observation_sources.get(int(o.time_ms)),
                    "boxes": [b.to_dict() for b in o.boxes],
                }
                for o in filtered
            ],
            "frames": frames,
        }
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("wrote %s frames=%s", out_json, len(frames))

        if overlay_dir is not None:
            _write_overlays_pfa(
                video_path,
                frames,
                overlay_dir,
                indices=overlay_indices,
                overlay_all=overlay_all,
                diagnostic=overlay_diagnostic,
            )
        return payload


def review_overlay_layers(
    entry: dict[str, Any],
    *,
    diagnostic: bool = False,
) -> list[tuple[str, dict[str, Any]]]:
    """Default QA is final authority; uncertain local evidence is opt-in and labeled."""
    layers = [("authority", box) for box in entry.get("boxes") or []]
    if diagnostic:
        layers.extend(
            ("uncertain", box)
            for box in entry.get("local_uncertain_boxes") or []
        )
    return layers


def _write_overlays_pfa(
    video_path: Path,
    dense_frames: list[dict[str, Any]],
    overlay_dir: Path,
    *,
    indices: list[int] | None,
    overlay_all: bool = False,
    diagnostic: bool = False,
) -> None:
    """Draw authority-only QA unless explicitly placed in diagnostic mode."""
    from src.media_pipeline.ocr_filtering.ocr_track_prototype import (
        _draw_label_pil,
        _resolve_cjk_font,
    )
    from PIL import Image, ImageDraw

    overlay_dir.mkdir(parents=True, exist_ok=True)
    by_idx = {int(f["frame_index"]): f for f in dense_frames}
    if overlay_all:
        indices = sorted(by_idx.keys())
    elif indices is None:
        with_boxes = [f for f in dense_frames if f.get("boxes")]
        indices = [int(with_boxes[i]["frame_index"]) for i in range(0, len(with_boxes), max(1, len(with_boxes) // 8))][:8]

    font = _resolve_cjk_font(22)
    meta_font = _resolve_cjk_font(28)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video for overlay: {video_path}")
    try:
        targets = {int(target) for target in indices or []}
        last_target = max(targets) if targets else -1
        target = 0
        while target <= last_target:
            ok, bgr = cap.read()
            if not ok or bgr is None:
                break
            if target not in targets:
                target += 1
                continue
            entry = by_idx.get(target)
            if entry is None:
                target += 1
                continue
            h, w = bgr.shape[:2]
            rgb = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(rgb)
            for layer, b in review_overlay_layers(entry, diagnostic=diagnostic):
                bw = float(b.get("w") if "w" in b else b.get("width") or 0.01)
                bh = float(b.get("h") if "h" in b else b.get("height") or 0.01)
                x0 = int(round(float(b["x"]) * w))
                y0 = int(round(float(b["y"]) * h))
                x1 = int(round((float(b["x"]) + bw) * w))
                y1 = int(round((float(b["y"]) + bh) * h))
                color = (0, 220, 255) if layer == "authority" else (255, 165, 0)
                draw.rectangle([x0, y0, x1, y1], outline=color, width=3)
                label = (b.get("text") or "").strip()
                if label or layer != "authority":
                    display = label[:24] if label else layer.upper()
                    _draw_label_pil(rgb, display, (x0, max(4, y0 - 28)), font, fill=color)
            seg = entry.get("text_segment_ms")
            meta = (
                f"{'DIAGNOSTIC' if diagnostic else 'AUTHORITY'} v3.6 "
                f"f{target} t={entry['time_ms']}ms n={len(entry.get('boxes') or [])} "
                f"pos@f{entry.get('position_source_frame')} text@{seg}ms"
            )
            _draw_label_pil(rgb, meta, (12, 10), meta_font, fill=(180, 255, 180))
            dest = (
                overlay_dir
                / f"pfa_f{target:06d}_t{entry['time_ms']:06d}_n{len(entry.get('boxes') or [])}.jpg"
            )
            rgb.save(dest, format="JPEG", quality=90)
            logger.info("overlay %s", dest.name)
            target += 1
    finally:
        cap.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-frame position (ink+DBNet) + sparse Cloud OCR text",
    )
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overlay-dir", default=None)
    parser.add_argument("--overlay-all", action="store_true")
    parser.add_argument(
        "--overlay-diagnostic",
        action="store_true",
        help="Also draw uncertain local proposals in orange; default is authority-only",
    )
    parser.add_argument("--overlay-indices", default=None)
    parser.add_argument("--positions-json", default=None, help="Reuse cached per-frame DBNet positions")
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--fixed-fps", action="store_true")
    parser.add_argument(
        "--pixel-change-ticks",
        action="store_true",
        help="Use legacy raw-pixel MAE ticks instead of glyph-mask events",
    )
    parser.add_argument(
        "--ocr-cache",
        default=None,
        help="Resumable OCR cache path (default: <out>.ocr-cache.json)",
    )
    parser.add_argument(
        "--ocr-batch-size",
        type=int,
        default=DEFAULT_CACHE_BATCH_SIZE,
        help="Checkpoint OCR cache after this many uncached crops",
    )
    parser.add_argument("--no-mid-title", action="store_true")
    parser.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    from src.media_pipeline.ocr_filtering.async_batch import _ensure_ocr_async_env_loaded

    _ensure_ocr_async_env_loaded()

    indices = None
    if args.overlay_indices:
        indices = [int(x.strip()) for x in args.overlay_indices.split(",") if x.strip()]

    run_per_frame_position_authority(
        args.video,
        out_json=Path(args.out),
        overlay_dir=Path(args.overlay_dir) if args.overlay_dir else None,
        overlay_all=bool(args.overlay_all),
        overlay_indices=indices,
        overlay_diagnostic=bool(args.overlay_diagnostic),
        concurrency=args.concurrency,
        use_change_ticks=not bool(args.fixed_fps),
        use_mid_title_band=not bool(args.no_mid_title),
        min_confidence=args.min_confidence,
        frame_stride=args.stride,
        positions_json=Path(args.positions_json) if args.positions_json else None,
        change_authority="pixel" if args.pixel_change_ticks else "glyph",
        ocr_cache_path=Path(args.ocr_cache) if args.ocr_cache else None,
        ocr_batch_size=args.ocr_batch_size,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
