"""Layout, local-recognition, and temporal verification for DBNet proposals."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

import cv2
import numpy as np

from src.media_pipeline.frame_sampling.local_text_recognizer import LocalRecognition
from src.media_pipeline.ocr_filtering.box_timeline_tracker import TimedBox, box_iou

VerificationMode = Literal["hardsub", "title", "endcard"]
VerificationDecision = Literal["verified", "uncertain", "rejected"]


class TextRecognizer(Protocol):
    def recognize(self, crop_bgr: np.ndarray) -> LocalRecognition: ...


@dataclass(frozen=True)
class CandidateLine:
    box: TimedBox
    source_boxes: tuple[TimedBox, ...]
    geometry_score: float


@dataclass(frozen=True)
class VerifiedLine:
    line: CandidateLine
    recognition: LocalRecognition
    text_likeness: float
    temporal_iou: float
    decision: VerificationDecision
    recognition_reused: bool = False


@dataclass
class _VerificationTrack:
    box: TimedBox
    signature: np.ndarray
    last_seen_frame: int
    last_recognized_frame: int
    recognition: LocalRecognition
    reusable: bool
    checkpoint_frames: int


@dataclass(frozen=True)
class ConfirmationResult:
    accepted: list[TimedBox]
    pending: list[TimedBox]
    backfill_frame_index: int | None = None
    backfill_boxes: tuple[TimedBox, ...] = ()


class TwoFrameConfirmationGate:
    """Hold brand-new verified lines one frame, then accept and backfill."""

    def __init__(self, *, min_iou: float = 0.40):
        self._min_iou = float(min_iou)
        self._pending: dict[str, tuple[int, tuple[TimedBox, ...]]] = {}

    def accept(
        self,
        *,
        frame_index: int,
        mode: str,
        verified_boxes: Sequence[TimedBox],
        recognition_reused_flags: Sequence[bool],
    ) -> ConfirmationResult:
        pending = self._pending.get(mode)
        accepted: list[TimedBox] = []
        still_pending: list[TimedBox] = []
        backfill_frame_index: int | None = None
        backfill_boxes: list[TimedBox] = []

        for box, reused in zip(verified_boxes, recognition_reused_flags, strict=True):
            if (
                reused
                and pending is not None
                and int(frame_index) == int(pending[0]) + 1
                and any(box_iou(box, previous) >= self._min_iou for previous in pending[1])
            ):
                accepted.append(box)
                backfill_frame_index = int(pending[0])
                backfill_boxes = list(pending[1])
                pending = None
                continue
            if reused:
                accepted.append(box)
                continue
            still_pending.append(box)

        if still_pending:
            self._pending[mode] = (int(frame_index), tuple(still_pending))
        elif backfill_frame_index is not None or pending is None:
            self._pending.pop(mode, None)
        elif pending is not None and int(frame_index) > int(pending[0]) + 1:
            self._pending.pop(mode, None)

        return ConfirmationResult(
            accepted=accepted,
            pending=still_pending,
            backfill_frame_index=backfill_frame_index,
            backfill_boxes=tuple(backfill_boxes),
        )


def requires_two_frame_confirmation(mode: VerificationMode | str) -> bool:
    """Hardsubs flicker with food FP; short-lived mid-titles must not wait a frame."""
    return str(mode) == "hardsub"


def _crop_has_ink_evidence(crop_bgr: np.ndarray) -> bool:
    """Cheap polarity check: sparse bright or dark low-chroma pixels in a crop."""
    if crop_bgr is None or crop_bgr.size == 0 or crop_bgr.ndim != 3:
        return False
    height, width = crop_bgr.shape[:2]
    if height < 2 or width < 2:
        return False
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    saturation = hsv[:, :, 1]
    area = max(1, height * width)
    bright = int(np.count_nonzero((gray >= 180) & (saturation <= 90)))
    dark = int(np.count_nonzero((gray <= 75) & (saturation <= 90)))
    lower = max(8, int(round(area * 0.01)))
    upper = int(round(area * 0.45))
    return (lower <= bright <= upper) or (lower <= dark <= upper)


def _merge_boxes(boxes: Sequence[TimedBox]) -> TimedBox:
    x0 = min(box.x for box in boxes)
    y0 = min(box.y for box in boxes)
    x1 = max(box.x + box.w for box in boxes)
    y1 = max(box.y + box.h for box in boxes)
    return TimedBox(x0, y0, x1 - x0, y1 - y0)


def _vertical_compatibility(a: TimedBox, b: TimedBox) -> bool:
    a_center = a.y + a.h * 0.5
    b_center = b.y + b.h * 0.5
    tolerance = max(0.012, min(a.h, b.h) * 0.75)
    return abs(a_center - b_center) <= tolerance


def _belongs_to_title_stack(box: TimedBox, candidates: Sequence[TimedBox]) -> bool:
    """Allow short title rows only when several rows share the same column."""
    neighbours = 0
    center_y = box.y + box.h * 0.5
    for other in candidates:
        if other is box:
            continue
        other_center_y = other.y + other.h * 0.5
        if not 0.025 <= abs(center_y - other_center_y) <= 0.30:
            continue
        overlap = min(box.x + box.w, other.x + other.w) - max(box.x, other.x)
        center_distance = abs(
            (box.x + box.w * 0.5) - (other.x + other.w * 0.5)
        )
        if overlap > 0.0 or center_distance <= 0.06:
            neighbours += 1
    return neighbours >= 2


def group_text_lines(
    boxes: Sequence[TimedBox],
    *,
    mode: VerificationMode,
) -> list[CandidateLine]:
    """Group same-baseline DBNet fragments and reject non-line-like geometry."""
    usable: list[TimedBox] = []
    for box in boxes:
        center_y = box.y + box.h * 0.5
        if box.w <= 0.004 or box.h <= 0.008 or box.w * box.h > 0.24:
            continue
        if mode == "hardsub" and (center_y < 0.65 or box.h > 0.16):
            continue
        if mode == "title" and (center_y < 0.10 or center_y >= 0.65 or box.h > 0.22):
            continue
        usable.append(box)
    usable.sort(key=lambda box: (box.y + box.h * 0.5, box.x))

    groups: list[list[TimedBox]] = []
    for box in usable:
        best: list[TimedBox] | None = None
        best_gap = float("inf")
        for group in groups:
            merged = _merge_boxes(group)
            if not _vertical_compatibility(merged, box):
                continue
            gap = max(0.0, box.x - (merged.x + merged.w), merged.x - (box.x + box.w))
            max_gap = 0.08 if mode == "hardsub" else 0.045
            if gap <= max_gap and gap < best_gap:
                best, best_gap = group, gap
        if best is None:
            groups.append([box])
        else:
            best.append(box)

    lines: list[CandidateLine] = []
    merged_groups = [_merge_boxes(group) for group in groups]
    for group in groups:
        merged = _merge_boxes(group)
        aspect = merged.w / max(merged.h, 1e-6)
        fill_ratio = sum(box.w * box.h for box in group) / max(merged.w * merged.h, 1e-8)
        if mode == "hardsub":
            if aspect < 2.0 or merged.w < 0.08 or fill_ratio < 0.08:
                continue
            geometry = min(1.0, aspect / 5.0) * 0.8 + min(1.0, fill_ratio) * 0.2
        elif mode == "title":
            in_stack = _belongs_to_title_stack(merged, merged_groups)
            if not in_stack and (aspect < 1.5 or merged.w < 0.10):
                continue
            if in_stack and (aspect < 0.50 or merged.w < 0.012):
                continue
            geometry = min(1.0, aspect / 4.0) * 0.7 + min(1.0, fill_ratio) * 0.3
        else:
            if aspect < 0.55 or merged.w < 0.012:
                continue
            geometry = min(1.0, aspect / 3.0) * 0.65 + min(1.0, fill_ratio) * 0.35
        lines.append(
            CandidateLine(
                box=merged,
                source_boxes=tuple(sorted(group, key=lambda item: item.x)),
                geometry_score=float(geometry),
            )
        )
    return lines


def _crop_line(frame_bgr: np.ndarray, box: TimedBox) -> np.ndarray:
    height, width = frame_bgr.shape[:2]
    pad_x = max(2, int(round(box.w * width * 0.04)))
    pad_y = max(2, int(round(box.h * height * 0.18)))
    x0 = max(0, int(np.floor(box.x * width)) - pad_x)
    y0 = max(0, int(np.floor(box.y * height)) - pad_y)
    x1 = min(width, int(np.ceil((box.x + box.w) * width)) + pad_x)
    y1 = min(height, int(np.ceil((box.y + box.h) * height)) + pad_y)
    return frame_bgr[y0:y1, x0:x1]


def _line_visual_signature(crop_bgr: np.ndarray) -> np.ndarray:
    """Return a compact edge signature robust to color and small compression jitter."""
    if crop_bgr is None or crop_bgr.size == 0:
        return np.zeros((32, 128), dtype=np.uint8)
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    compact = cv2.resize(gray, (128, 32), interpolation=cv2.INTER_AREA)
    compact = cv2.GaussianBlur(compact, (3, 3), 0)
    edges = cv2.Canny(compact, 40, 120)
    return cv2.dilate(
        edges,
        cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)),
        iterations=1,
    )


def _signature_change_score(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_NEAREST)
    aa = a > 0
    bb = b > 0
    total = int(np.count_nonzero(aa)) + int(np.count_nonzero(bb))
    if total < 8:
        return 1.0
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    aa_d = cv2.dilate(aa.astype(np.uint8), kernel, iterations=1) > 0
    bb_d = cv2.dilate(bb.astype(np.uint8), kernel, iterations=1) > 0
    intersection = int(np.count_nonzero(aa & bb_d)) + int(np.count_nonzero(bb & aa_d))
    return 1.0 - min(1.0, float(intersection) / float(total))


def _verified_line_from_recognition(
    line: CandidateLine,
    recognition: LocalRecognition,
    *,
    mode: VerificationMode,
    previous_verified: Sequence[TimedBox],
    recognition_reused: bool = False,
) -> VerifiedLine:
    temporal_iou = max(
        (box_iou(line.box, previous) for previous in previous_verified),
        default=0.0,
    )
    text_likeness = (
        0.70 * recognition.confidence
        + 0.20 * recognition.valid_char_ratio
        + 0.10 * line.geometry_score
    )
    strong_threshold = {"hardsub": 0.64, "title": 0.58, "endcard": 0.55}[mode]
    uncertain_threshold = {"hardsub": 0.46, "title": 0.42, "endcard": 0.40}[mode]
    if text_likeness >= strong_threshold and recognition.valid_char_ratio >= 0.45:
        decision: VerificationDecision = "verified"
    elif (
        text_likeness >= uncertain_threshold
        and recognition.valid_char_ratio >= 0.25
        and temporal_iou >= 0.35
    ):
        decision = "verified"
    elif text_likeness >= uncertain_threshold and recognition.valid_char_ratio >= 0.20:
        decision = "uncertain"
    else:
        decision = "rejected"
    return VerifiedLine(
        line=line,
        recognition=recognition,
        text_likeness=float(text_likeness),
        temporal_iou=float(temporal_iou),
        decision=decision,
        recognition_reused=recognition_reused,
    )


def verify_text_lines(
    frame_bgr: np.ndarray,
    boxes: Sequence[TimedBox],
    *,
    recognizer: TextRecognizer,
    mode: VerificationMode,
    previous_verified: Sequence[TimedBox] = (),
) -> list[VerifiedLine]:
    """Score proposal lines; only borderline lines may rely on temporal evidence."""
    verified: list[VerifiedLine] = []
    for line in group_text_lines(boxes, mode=mode):
        recognition = recognizer.recognize(_crop_line(frame_bgr, line.box))
        verified.append(
            _verified_line_from_recognition(
                line,
                recognition,
                mode=mode,
                previous_verified=previous_verified,
            )
        )
    return verified


class EventDrivenTextVerifier:
    """Reuse CTC evidence only while current geometry and glyph pixels still match."""

    def __init__(
        self,
        recognizer: TextRecognizer,
        *,
        checkpoint_frames: int = 24,
        stable_checkpoint_frames: int = 48,
        max_track_gap_frames: int = 3,
        min_track_iou: float = 0.40,
        max_signature_change: float = 0.30,
    ):
        self._recognizer = recognizer
        self._checkpoint_frames = max(1, int(checkpoint_frames))
        self._stable_checkpoint_frames = max(
            self._checkpoint_frames,
            int(stable_checkpoint_frames),
        )
        self._max_track_gap_frames = max(0, int(max_track_gap_frames))
        self._min_track_iou = float(min_track_iou)
        self._max_signature_change = float(max_signature_change)
        self._tracks: dict[VerificationMode, list[_VerificationTrack]] = {
            "hardsub": [],
            "title": [],
            "endcard": [],
        }
        self.recognizer_calls = 0
        self.recognizer_batches = 0
        self.reused_recognitions = 0
        self.recognizer_inference_ms = 0.0
        self.blank_frame_skips = 0

    def verify(
        self,
        frame_bgr: np.ndarray,
        boxes: Sequence[TimedBox],
        *,
        mode: VerificationMode,
        frame_index: int,
        previous_verified: Sequence[TimedBox] = (),
    ) -> list[VerifiedLine]:
        active_tracks = [
            track
            for track in self._tracks[mode]
            if int(frame_index) - track.last_seen_frame <= self._max_track_gap_frames
        ]
        if mode == "endcard":
            inked_boxes = list(boxes)
        else:
            inked_boxes = [
                box
                for box in boxes
                if _crop_has_ink_evidence(_crop_line(frame_bgr, box))
            ]
            if not inked_boxes and not active_tracks:
                self._tracks[mode] = []
                self.blank_frame_skips += 1
                return []
            if not inked_boxes:
                self._tracks[mode] = []
                return []

        lines = group_text_lines(inked_boxes, mode=mode)
        matched_track_ids: set[int] = set()
        plans: list[
            tuple[CandidateLine, np.ndarray, np.ndarray, _VerificationTrack | None, bool]
        ] = []
        for line in lines:
            crop = _crop_line(frame_bgr, line.box)
            signature = _line_visual_signature(crop)
            best_track: _VerificationTrack | None = None
            best_track_index = -1
            best_score = float("inf")
            for track_index, track in enumerate(active_tracks):
                if track_index in matched_track_ids:
                    continue
                overlap = box_iou(line.box, track.box)
                if overlap < self._min_track_iou:
                    continue
                signature_change = _signature_change_score(signature, track.signature)
                if signature_change > self._max_signature_change:
                    continue
                score = (1.0 - overlap) + signature_change
                if score < best_score:
                    best_track = track
                    best_track_index = track_index
                    best_score = score
            if best_track is not None:
                matched_track_ids.add(best_track_index)
            should_refresh = (
                best_track is None
                or not best_track.reusable
                or int(frame_index) - best_track.last_recognized_frame
                >= best_track.checkpoint_frames
            )
            plans.append((line, crop, signature, best_track, should_refresh))

        refresh_indices = [index for index, plan in enumerate(plans) if plan[4]]
        refresh_crops = [plans[index][1] for index in refresh_indices]
        refreshed: dict[int, LocalRecognition] = {}
        if refresh_crops:
            started = time.perf_counter()
            batch_method = getattr(self._recognizer, "recognize_batch", None)
            if len(refresh_crops) > 1 and callable(batch_method):
                batch_results = list(batch_method(refresh_crops))
                self.recognizer_batches += 1
            else:
                batch_results = [
                    self._recognizer.recognize(crop) for crop in refresh_crops
                ]
            self.recognizer_inference_ms += (time.perf_counter() - started) * 1000.0
            self.recognizer_calls += len(refresh_crops)
            if len(batch_results) != len(refresh_indices):
                raise RuntimeError(
                    "Local recognizer batch result mismatch: "
                    f"expected={len(refresh_indices)} actual={len(batch_results)}"
                )
            refreshed = dict(zip(refresh_indices, batch_results, strict=True))

        next_tracks: list[_VerificationTrack] = []
        results: list[VerifiedLine] = []
        for plan_index, (line, _crop, signature, best_track, should_refresh) in enumerate(
            plans
        ):
            if should_refresh:
                recognition = refreshed[plan_index]
                last_recognized_frame = int(frame_index)
                reused = False
            else:
                if best_track is None:  # pragma: no cover - guarded by should_refresh
                    raise RuntimeError("Missing verification track for reused recognition")
                recognition = best_track.recognition
                last_recognized_frame = best_track.last_recognized_frame
                reused = True
                self.reused_recognitions += 1
            result = _verified_line_from_recognition(
                line,
                recognition,
                mode=mode,
                previous_verified=previous_verified,
                recognition_reused=reused,
            )
            results.append(result)
            next_tracks.append(
                _VerificationTrack(
                    box=line.box,
                    signature=signature,
                    last_seen_frame=int(frame_index),
                    last_recognized_frame=last_recognized_frame,
                    recognition=recognition,
                    reusable=result.decision != "uncertain",
                    checkpoint_frames=(
                        self._stable_checkpoint_frames
                        if result.decision in {"verified", "rejected"}
                        else self._checkpoint_frames
                    ),
                )
            )
        self._tracks[mode] = next_tracks
        return results


def filter_verified_text_lines(
    frame_bgr: np.ndarray,
    boxes: Sequence[TimedBox],
    *,
    recognizer: TextRecognizer,
    mode: VerificationMode,
    previous_verified: Sequence[TimedBox] = (),
    include_uncertain: bool = False,
) -> list[TimedBox]:
    """Return only verified line geometry, carrying local text as diagnostic evidence."""
    accepted: list[TimedBox] = []
    for result in verify_text_lines(
        frame_bgr,
        boxes,
        recognizer=recognizer,
        mode=mode,
        previous_verified=previous_verified,
    ):
        if result.decision != "verified" and not (
            include_uncertain and result.decision == "uncertain"
        ):
            continue
        box = result.line.box
        accepted.append(
            TimedBox(
                box.x,
                box.y,
                box.w,
                box.h,
                text=result.recognition.text,
                confidence=result.text_likeness,
            )
        )
    return accepted
