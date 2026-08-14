"""Local event-first candidate scheduling for Phase 1 text analysis.

The scheduler deliberately contains no OCR or learned text detector.  It combines
already-persisted speech windows with cheap, deterministic frame-change evidence so
the expensive detector is called only where an event may exist.  Frame pixels remain
evidence; candidate windows are the discovery authority.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import cv2
import numpy as np


EVENT_SCAN_ENGINE_VERSION = "audio_visual_temporal_v1"
EVENT_SCAN_POLICY_VERSION = (
    "audio_visual_temporal_policy_v12_epoch_complete_cover"
)
CANDIDATE_WINDOW_SCHEMA_VERSION = "phase1_candidate_windows_v1"


@dataclass(frozen=True)
class CandidateWindow:
    start_ms: int
    end_ms: int
    sources: tuple[str, ...]
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["sources"] = list(self.sources)
        return row


@dataclass(frozen=True)
class VisualTrigger:
    triggered: bool
    reason: str
    scene_score: float
    tile_edge_score: float
    max_tile_edge_delta: float
    median_tile_edge_delta: float
    textness_delta: float = 0.0
    max_tile_textness_delta: float = 0.0
    hard_textness_boundary: bool = False
    absolute_textness_score: float = 0.0
    text_component_count: int = 0
    absolute_text_candidate: bool = False
    strong_absolute_text_candidate: bool = False


def _clamp_ms(value: int | float, duration_ms: int) -> int:
    return max(0, min(max(0, int(duration_ms)), int(round(float(value)))))


def merge_candidate_windows(
    windows: Sequence[CandidateWindow],
    *,
    duration_ms: int,
    merge_gap_ms: int = 180,
) -> list[CandidateWindow]:
    """Merge overlapping/nearby windows while retaining all evidence sources."""

    normalized = sorted(
        (
            CandidateWindow(
                start_ms=_clamp_ms(row.start_ms, duration_ms),
                end_ms=_clamp_ms(row.end_ms, duration_ms),
                sources=tuple(dict.fromkeys(str(value) for value in row.sources if value)),
                confidence=max(0.0, min(1.0, float(row.confidence))),
            )
            for row in windows
            if int(row.end_ms) > int(row.start_ms)
        ),
        key=lambda row: (row.start_ms, row.end_ms),
    )
    merged: list[CandidateWindow] = []
    for row in normalized:
        if not merged or row.start_ms > merged[-1].end_ms + max(0, int(merge_gap_ms)):
            merged.append(row)
            continue
        prior = merged[-1]
        merged[-1] = CandidateWindow(
            start_ms=prior.start_ms,
            end_ms=max(prior.end_ms, row.end_ms),
            sources=tuple(dict.fromkeys((*prior.sources, *row.sources))),
            confidence=max(prior.confidence, row.confidence),
        )
    return merged


def build_audio_candidate_windows(
    segments: Sequence[Mapping[str, Any]],
    *,
    duration_ms: int,
    base_lead_ms: int = 320,
    base_tail_ms: int = 380,
) -> list[CandidateWindow]:
    """Turn persisted VAD/ASR beats into conservative visual search windows."""

    windows: list[CandidateWindow] = []
    for segment in segments:
        start = int(segment.get("start_ms") or 0)
        end = int(segment.get("end_ms") or start)
        if end <= start:
            continue
        confidence = max(0.0, min(1.0, float(segment.get("confidence") or 0.0)))
        uncertainty_pad = int(round((1.0 - confidence) * 220.0))
        windows.append(
            CandidateWindow(
                start_ms=_clamp_ms(start - base_lead_ms - uncertainty_pad, duration_ms),
                end_ms=_clamp_ms(end + base_tail_ms + uncertainty_pad, duration_ms),
                sources=("AUDIO_GUIDED",),
                confidence=max(0.45, confidence),
            )
        )
    return merge_candidate_windows(windows, duration_ms=duration_ms)


class TileVisualChangeProbe:
    """Cheap all-frame scene/local-edge trigger at a small fixed raster."""

    def __init__(
        self,
        *,
        long_edge: int = 512,
        rows: int = 4,
        columns: int = 4,
        scene_threshold: float = 0.20,
        local_edge_threshold: float = 0.032,
        max_tile_edge_threshold: float = 0.050,
        local_textness_threshold: float = 0.018,
        hard_textness_threshold: float = 0.055,
        absolute_textness_threshold: float = 0.020,
        strong_absolute_textness_threshold: float = 0.038,
    ) -> None:
        self.long_edge = max(96, int(long_edge))
        self.rows = max(2, int(rows))
        self.columns = max(2, int(columns))
        self.scene_threshold = max(0.01, float(scene_threshold))
        self.local_edge_threshold = max(0.005, float(local_edge_threshold))
        self.max_tile_edge_threshold = max(0.005, float(max_tile_edge_threshold))
        self.local_textness_threshold = max(
            0.004, float(local_textness_threshold)
        )
        self.hard_textness_threshold = max(
            self.local_textness_threshold, float(hard_textness_threshold)
        )
        self.absolute_textness_threshold = max(
            0.006, float(absolute_textness_threshold)
        )
        self.strong_absolute_textness_threshold = max(
            self.absolute_textness_threshold,
            float(strong_absolute_textness_threshold),
        )
        self._previous_gray: np.ndarray | None = None
        self._previous_edges: np.ndarray | None = None
        self._previous_textness: np.ndarray | None = None

    def _signature(
        self, frame_bgr: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        height, width = frame_bgr.shape[:2]
        scale = min(1.0, self.long_edge / float(max(1, max(height, width))))
        if scale < 1.0:
            frame_bgr = cv2.resize(
                frame_bgr,
                (max(2, int(round(width * scale))), max(2, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA,
            )
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        # A small close reconnects anti-aliased glyph strokes without making this
        # probe pretend to be a text detector.
        edges = cv2.Canny(gray, 48, 136)
        edges = cv2.morphologyEx(
            edges,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1)),
        )
        # Text-specific change evidence is independent from generic scene
        # edges.  Bright and dark glyph strokes both survive through the
        # top-hat/black-hat union while broad object motion is suppressed.
        kernel_width = max(5, int(round(gray.shape[1] * 0.035)))
        if kernel_width % 2 == 0:
            kernel_width += 1
        kernel_height = max(3, int(round(gray.shape[0] * 0.018)))
        if kernel_height % 2 == 0:
            kernel_height += 1
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (kernel_width, kernel_height)
        )
        blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
        tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
        response = cv2.max(blackhat, tophat)
        threshold = max(14.0, float(np.percentile(response, 88.0)))
        textness = np.where(response >= threshold, 255, 0).astype(np.uint8)
        textness = cv2.morphologyEx(
            textness,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1)),
        )
        return gray, edges, textness

    def inspect(self, frame_bgr: np.ndarray) -> VisualTrigger:
        gray, edges, textness = self._signature(frame_bgr)
        component_count, _labels, component_stats, _centroids = (
            cv2.connectedComponentsWithStats(textness, 8)
        )
        plausible_components = 0
        for label in range(1, component_count):
            _x, _y, component_width, component_height, area = (
                int(value) for value in component_stats[label]
            )
            if (
                area >= 5
                and component_width >= 3
                and component_height >= 2
                and component_height <= max(8, int(round(gray.shape[0] * 0.16)))
            ):
                plausible_components += 1

        absolute_tile_scores: list[float] = []
        height, width = textness.shape[:2]
        for row in range(self.rows):
            y0 = int(round(row * height / self.rows))
            y1 = int(round((row + 1) * height / self.rows))
            for column in range(self.columns):
                x0 = int(round(column * width / self.columns))
                x1 = int(round((column + 1) * width / self.columns))
                tile = textness[y0:y1, x0:x1]
                absolute_tile_scores.append(
                    float(np.count_nonzero(tile)) / float(max(1, tile.size))
                )
        absolute_textness_score = max(absolute_tile_scores, default=0.0)
        absolute_text_candidate = bool(
            plausible_components >= 3
            and absolute_textness_score >= self.absolute_textness_threshold
        )
        strong_absolute_text_candidate = bool(
            plausible_components >= 5
            and absolute_textness_score
            >= self.strong_absolute_textness_threshold
        )
        if self._previous_gray is None or self._previous_gray.shape != gray.shape:
            self._previous_gray = gray
            self._previous_edges = edges
            self._previous_textness = textness
            return VisualTrigger(
                True,
                "first_frame",
                1.0,
                1.0,
                1.0,
                0.0,
                textness_delta=1.0,
                max_tile_textness_delta=1.0,
                # The first decoded frame has no appearance/disappearance
                # boundary. Absolute textness may schedule detection, but it
                # is not independent evidence for one-frame retention.
                hard_textness_boundary=False,
                absolute_textness_score=round(absolute_textness_score, 6),
                text_component_count=plausible_components,
                absolute_text_candidate=absolute_text_candidate,
                strong_absolute_text_candidate=strong_absolute_text_candidate,
            )

        assert self._previous_edges is not None
        assert self._previous_textness is not None
        scene_score = float(np.mean(cv2.absdiff(gray, self._previous_gray))) / 255.0
        edge_delta = cv2.bitwise_xor(edges, self._previous_edges)
        textness_delta_map = cv2.bitwise_xor(
            textness, self._previous_textness
        )
        height, width = edge_delta.shape[:2]
        tile_scores: list[float] = []
        textness_scores: list[float] = []
        for row in range(self.rows):
            y0 = int(round(row * height / self.rows))
            y1 = int(round((row + 1) * height / self.rows))
            for column in range(self.columns):
                x0 = int(round(column * width / self.columns))
                x1 = int(round((column + 1) * width / self.columns))
                tile = edge_delta[y0:y1, x0:x1]
                tile_scores.append(float(np.count_nonzero(tile)) / float(max(1, tile.size)))
                text_tile = textness_delta_map[y0:y1, x0:x1]
                textness_scores.append(
                    float(np.count_nonzero(text_tile))
                    / float(max(1, text_tile.size))
                )
        max_tile = max(tile_scores, default=0.0)
        median_tile = float(np.median(np.asarray(tile_scores, dtype=np.float32))) if tile_scores else 0.0
        local_edge_score = max(0.0, max_tile - median_tile)
        max_textness = max(textness_scores, default=0.0)
        median_textness = (
            float(np.median(np.asarray(textness_scores, dtype=np.float32)))
            if textness_scores
            else 0.0
        )
        local_textness_score = max(0.0, max_textness - median_textness)
        hard_textness = bool(
            local_textness_score >= self.hard_textness_threshold
            and strong_absolute_text_candidate
            and absolute_textness_score >= 0.05
        )
        if scene_score >= self.scene_threshold:
            triggered, reason = True, "scene_change"
        elif local_textness_score >= self.local_textness_threshold:
            triggered, reason = True, "local_textness_change"
        elif (
            local_edge_score >= self.local_edge_threshold
            and max_tile >= self.max_tile_edge_threshold
        ):
            triggered, reason = True, "local_textness_change"
        else:
            triggered, reason = False, "stable"
        self._previous_gray = gray
        self._previous_edges = edges
        self._previous_textness = textness
        return VisualTrigger(
            triggered=triggered,
            reason=reason,
            scene_score=round(scene_score, 6),
            tile_edge_score=round(local_edge_score, 6),
            max_tile_edge_delta=round(max_tile, 6),
            median_tile_edge_delta=round(median_tile, 6),
            textness_delta=round(local_textness_score, 6),
            max_tile_textness_delta=round(max_textness, 6),
            hard_textness_boundary=bool(hard_textness),
            absolute_textness_score=round(absolute_textness_score, 6),
            text_component_count=plausible_components,
            absolute_text_candidate=absolute_text_candidate,
            strong_absolute_text_candidate=strong_absolute_text_candidate,
        )


class EventFrameScheduler:
    """Select expensive detector frames from audio, visual and safety evidence."""

    def __init__(
        self,
        *,
        fps: float,
        frame_count: int,
        duration_ms: int,
        audio_windows: Sequence[CandidateWindow] = (),
        audio_sample_fps: float = 4.0,
        heartbeat_fps: float = 0.5,
        completeness_sample_fps: float = 2.0,
        burst_sample_fps: float = 8.0,
        burst_duration_ms: int = 420,
        visual_trigger_cooldown_ms: int = 900,
        max_detector_fps: float = 4.5,
    ) -> None:
        self.fps = max(1.0, float(fps))
        self.frame_count = max(1, int(frame_count))
        self.duration_ms = max(1, int(duration_ms))
        self.audio_windows = merge_candidate_windows(
            list(audio_windows), duration_ms=self.duration_ms
        )
        self.audio_stride = max(1, int(round(self.fps / max(0.5, audio_sample_fps))))
        self.heartbeat_stride = max(1, int(round(self.fps / max(0.2, heartbeat_fps))))
        self.completeness_stride = max(
            1, int(round(self.fps / max(1.0, completeness_sample_fps)))
        )
        self.burst_stride = max(1, int(round(self.fps / max(1.0, burst_sample_fps))))
        self.burst_frames = max(1, int(round(self.fps * burst_duration_ms / 1000.0)))
        self.visual_trigger_cooldown_frames = max(
            1, int(round(self.fps * visual_trigger_cooldown_ms / 1000.0))
        )
        # Keep a two-second rolling budget so fractional rates such as 4.5 FPS
        # remain meaningful instead of being rounded differently by runtimes.
        self.detector_budget_window_frames = max(1, int(round(self.fps * 2.0)))
        self.max_detector_fps = max(2.0, float(max_detector_fps))
        self.max_detector_frames_per_window = max(
            2,
            int(np.ceil(self.max_detector_fps * 2.0)),
        )
        self.probe = TileVisualChangeProbe()
        self._audio_mask = np.zeros(self.frame_count, dtype=np.bool_)
        self._audio_boundaries: set[int] = set()
        for window in self.audio_windows:
            start = max(0, min(self.frame_count - 1, int(np.floor(window.start_ms * self.fps / 1000.0))))
            end = max(start, min(self.frame_count - 1, int(np.ceil(window.end_ms * self.fps / 1000.0))))
            self._audio_mask[start : end + 1] = True
            self._audio_boundaries.update({start, end})
        self._scheduled_burst_frames: set[int] = set()
        self._visual_windows: list[CandidateWindow] = []
        self._next_visual_trigger_frame = 0
        self._recent_selected: deque[int] = deque()
        self.reason_counts: Counter[str] = Counter()
        self.visual_trigger_count = 0
        self.peak_scene_score = 0.0
        self.peak_tile_edge_score = 0.0
        self.peak_textness_delta = 0.0
        self._hard_textness_frames: set[int] = set()
        self._completeness_candidate_frames: set[int] = set()
        # Detection scheduling and one-frame retention are deliberately
        # separate authorities.  A cheap textness change may justify paying
        # for DBNet, but it must never be enough to keep a DBNet hit by itself.
        self._detector_candidate_frames: set[int] = set()
        self._single_frame_retention_candidate_frames: set[int] = set()

    def inspect(self, frame_bgr: np.ndarray, *, frame_index: int) -> tuple[bool, tuple[str, ...]]:
        index = max(0, min(self.frame_count - 1, int(frame_index)))
        trigger = self.probe.inspect(frame_bgr)
        self.peak_scene_score = max(self.peak_scene_score, trigger.scene_score)
        self.peak_tile_edge_score = max(self.peak_tile_edge_score, trigger.tile_edge_score)
        self.peak_textness_delta = max(
            self.peak_textness_delta, trigger.textness_delta
        )
        reasons: list[str] = []
        # Only a hard appearance/disappearance boundary may bypass cooldown.
        # Ordinary texture motion (hair, fabric, camera movement) is useful as
        # a probe hint but must not turn local OCR into full-duration DBNet.
        bypass_cooldown = bool(trigger.hard_textness_boundary)
        if trigger.triggered and (
            index >= self._next_visual_trigger_frame or bypass_cooldown
        ):
            self.visual_trigger_count += 1
            self._next_visual_trigger_frame = (
                index + self.visual_trigger_cooldown_frames
            )
            reasons.append(trigger.reason)
            if trigger.hard_textness_boundary:
                reasons.append("hard_textness_boundary")
                self._hard_textness_frames.add(index)
                self._single_frame_retention_candidate_frames.add(index)
            end = min(self.frame_count - 1, index + self.burst_frames)
            self._scheduled_burst_frames.update(
                range(index, end + 1, self.burst_stride)
            )
            start_ms = int(round(index * 1000.0 / self.fps))
            end_ms = int(round(end * 1000.0 / self.fps))
            self._visual_windows.append(
                CandidateWindow(
                    start_ms=start_ms,
                    end_ms=max(start_ms + 1, end_ms),
                    sources=(
                        "VISUAL_SCENE_CHANGE"
                        if trigger.reason == "scene_change"
                        else "VISUAL_TEXTNESS_CHANGE"
                    ,),
                    confidence=max(trigger.scene_score, trigger.tile_edge_score),
                )
            )
        # Audio timing is the stronger cadence authority inside speech windows.
        # Running the visual completeness cadence there as well pays twice for
        # the same interval without adding temporal coverage.
        if (
            not self._audio_mask[index]
            and trigger.absolute_text_candidate
            and index % self.completeness_stride == 0
        ):
            reasons.append("completeness_text_candidate")
            self._completeness_candidate_frames.add(index)
        if self._audio_mask[index] and index % self.audio_stride == 0:
            reasons.append("audio_guided")
        if index in self._audio_boundaries:
            reasons.append("audio_boundary")
        if index in self._scheduled_burst_frames:
            reasons.append("visual_burst")
            self._scheduled_burst_frames.discard(index)
        if index % self.heartbeat_stride == 0:
            reasons.append("safety_heartbeat")
        unique = tuple(dict.fromkeys(reasons))
        if not unique:
            return False, unique
        rolling_start = index - self.detector_budget_window_frames + 1
        while self._recent_selected and self._recent_selected[0] < rolling_start:
            self._recent_selected.popleft()
        # A rolling budget prevents continuous camera motion from degenerating
        # into full-frame DBNet. Completeness candidates are an independent
        # all-frame text authority and must not be starved by a preceding
        # scene-change burst.
        if (
            not {
                "audio_boundary",
                "hard_textness_boundary",
                "completeness_text_candidate",
            }.intersection(unique)
            and len(self._recent_selected) >= self.max_detector_frames_per_window
        ):
            return False, ()
        self._recent_selected.append(index)
        self._detector_candidate_frames.add(index)
        for reason in unique:
            self.reason_counts[reason] += 1
        return bool(unique), unique

    def payload(self, *, scanned_frames: int) -> dict[str, Any]:
        windows = merge_candidate_windows(
            [*self.audio_windows, *self._visual_windows],
            duration_ms=self.duration_ms,
        )
        return {
            "schema_version": CANDIDATE_WINDOW_SCHEMA_VERSION,
            "engine_version": EVENT_SCAN_ENGINE_VERSION,
            "policy_version": EVENT_SCAN_POLICY_VERSION,
            "status": "COMPLETE",
            "duration_ms": self.duration_ms,
            "frame_count": self.frame_count,
            "fps": self.fps,
            "windows": [row.to_dict() for row in windows],
            "audio_window_count": len(self.audio_windows),
            "visual_trigger_count": self.visual_trigger_count,
            "heavy_probe_frames": int(scanned_frames),
            "heavy_probe_ratio": round(float(scanned_frames) / self.frame_count, 6),
            "reason_counts": dict(sorted(self.reason_counts.items())),
            "peak_scene_score": round(self.peak_scene_score, 6),
            "peak_tile_edge_score": round(self.peak_tile_edge_score, 6),
            "peak_textness_delta": round(self.peak_textness_delta, 6),
            "hard_textness_frames": sorted(self._hard_textness_frames),
            "completeness_candidate_frames": sorted(
                self._completeness_candidate_frames
            ),
            "detector_candidate_frames": sorted(
                self._detector_candidate_frames
            ),
            "single_frame_retention_candidate_frames": sorted(
                self._single_frame_retention_candidate_frames
            ),
            "policy": {
                "audio_sample_fps": round(self.fps / self.audio_stride, 4),
                "heartbeat_fps": round(self.fps / self.heartbeat_stride, 4),
                "completeness_sample_fps": round(
                    self.fps / self.completeness_stride, 4
                ),
                "burst_sample_fps": round(self.fps / self.burst_stride, 4),
                "burst_duration_frames": self.burst_frames,
                "visual_trigger_cooldown_frames": self.visual_trigger_cooldown_frames,
                "detector_budget_window_frames": self.detector_budget_window_frames,
                "max_detector_fps": round(self.max_detector_fps, 4),
                "max_detector_frames_per_window": self.max_detector_frames_per_window,
                "hard_textness_budget_bypass": True,
                "ordinary_textness_cooldown_bypass": False,
                "completeness_inside_audio_windows": False,
                "absolute_text_candidate_enabled": True,
                "detector_candidate_is_retention_authority": False,
                "single_frame_retention_requires_local_cjk": True,
                "proxy_long_edge": int(self.probe.long_edge),
                "single_decode": True,
                "network_calls": 0,
            },
        }
