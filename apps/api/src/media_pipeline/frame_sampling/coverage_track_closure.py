"""Coverage-first temporal closure for local on-screen text tracks.

DBNet remains the seed detector.  This module consumes a cheap all-frame proxy
stream and turns sparse detector evidence into frame-exact presence ranges and
geometry keyframes.  It deliberately performs no OCR and no network calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import cv2
import numpy as np


COVERAGE_TRACK_SCHEMA_VERSION = "phase1_track_coverage_v2"
COVERAGE_TRACK_POLICY_VERSION = "coverage_first_track_closure_v3_epoch_budget"


def _candidate_geometry(raw: Mapping[str, Any]) -> tuple[float, float, float, float]:
    geometry = dict(raw.get("geometry") or {})
    x0 = float(geometry.get("x") or 0.0)
    y0 = float(geometry.get("y") or 0.0)
    return (
        x0,
        y0,
        x0 + float(geometry.get("width") or 0.0),
        y0 + float(geometry.get("height") or 0.0),
    )


def _candidate_geometry_match(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    ax0, ay0, ax1, ay1 = _candidate_geometry(left)
    bx0, by0, bx1, by1 = _candidate_geometry(right)
    intersection = max(0.0, min(ax1, bx1) - max(ax0, bx0)) * max(
        0.0, min(ay1, by1) - max(ay0, by0)
    )
    smaller = min(
        max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0),
        max(0.0, bx1 - bx0) * max(0.0, by1 - by0),
    )
    if smaller > 0.0 and intersection / smaller >= 0.28:
        return True
    aw, ah = max(0.001, ax1 - ax0), max(0.001, ay1 - ay0)
    bw, bh = max(0.001, bx1 - bx0), max(0.001, by1 - by0)
    center_delta = max(
        abs((ax0 + ax1 - bx0 - bx1) * 0.5) / max(aw, bw),
        abs((ay0 + ay1 - by0 - by1) * 0.5) / max(ah, bh),
    )
    return center_delta <= 0.55


def schedule_unassigned_discovery_frames(
    candidates: Sequence[Mapping[str, Any]],
    *,
    fps: float,
    duration_ms: int,
    max_frames: int,
    boundary_frames: Sequence[int] = (),
) -> tuple[list[int], dict[str, Any]]:
    """Allocate high-resolution DBNet budget per spatial-temporal epoch.

    A frame-only global linspace loses short overlays whenever generic scene
    texture keeps the proxy residual active for most of the video.  This
    scheduler first tracks each residual locus, then round-robins the budget
    across epochs.  Brief appearance/disappearance epochs are ranked ahead of
    full-duration texture, while persistent candidates still retain periodic
    validation samples.
    """

    rate = max(1.0, float(fps))
    budget = max(1, int(max_frames))
    max_gap = max(2, int(round(rate * 0.16)))
    ordered = sorted(
        (dict(row) for row in candidates if isinstance(row, Mapping)),
        key=lambda row: int(row.get("frame_index") or 0),
    )
    epochs: list[dict[str, Any]] = []
    active: list[int] = []
    for row in ordered:
        frame = max(0, int(row.get("frame_index") or 0))
        active = [
            index
            for index in active
            if frame - int(epochs[index]["last_frame"]) <= max_gap
        ]
        matches = [
            index
            for index in active
            if _candidate_geometry_match(epochs[index]["last_row"], row)
        ]
        if matches:
            epoch_index = min(
                matches,
                key=lambda index: frame - int(epochs[index]["last_frame"]),
            )
            epoch = epochs[epoch_index]
            epoch["frames"].append(frame)
            epoch["rows"].append(row)
            epoch["last_frame"] = frame
            epoch["last_row"] = row
        else:
            epoch_index = len(epochs)
            epochs.append(
                {
                    "frames": [frame],
                    "rows": [row],
                    "last_frame": frame,
                    "last_row": row,
                }
            )
        if epoch_index not in active:
            active.append(epoch_index)

    sample_stride = max(1, int(round(rate / 4.0)))
    duration_frames = max(1, int(round(duration_ms * rate / 1000.0)))
    boundary_set = {max(0, int(value)) for value in boundary_frames}
    boundary_radius = max(2, int(round(rate * 0.35)))
    ranked: list[tuple[float, int, list[int]]] = []
    for index, epoch in enumerate(epochs):
        frames = sorted({int(value) for value in epoch["frames"]})
        first, last = frames[0], frames[-1]
        span = max(1, last - first + 1)
        wanted = {first, last, frames[len(frames) // 2]}
        prior = first
        for frame in frames[1:-1]:
            if frame - prior >= sample_stride:
                wanted.add(frame)
                prior = frame
        geometries = [_candidate_geometry(row) for row in epoch["rows"]]
        aspects = [
            max(0.0, x1 - x0) / max(0.001, y1 - y0)
            for x0, y0, x1, y1 in geometries
        ]
        line_score = min(2.0, float(np.median(aspects)) / 4.0)
        brief_score = 2.5 if span <= rate * 2.0 else 1.0
        persistence_penalty = max(0.15, 1.0 - span / float(duration_frames))
        support_score = min(1.0, len(frames) / 4.0)
        boundary_distance = min(
            (abs(frame - boundary) for frame in frames for boundary in boundary_set),
            default=10**9,
        )
        boundary_score = 6.0 if boundary_distance <= boundary_radius else 0.0
        score = (
            brief_score
            + line_score
            + support_score
            + persistence_penalty
            + boundary_score
        )
        # Bound one noisy locus before global allocation; long epochs retain
        # enough cadence to validate changes without consuming all 180 slots.
        epoch_cap = max(3, min(18, int(np.ceil(span / sample_stride)) + 2))
        wanted.update(
            frame
            for frame in frames
            if any(abs(frame - boundary) <= boundary_radius for boundary in boundary_set)
        )
        wanted_ordered = sorted(wanted)
        if len(wanted_ordered) > epoch_cap:
            positions = np.linspace(0, len(wanted_ordered) - 1, epoch_cap)
            wanted_ordered = sorted(
                {wanted_ordered[int(round(position))] for position in positions}
            )
        ranked.append((score, index, wanted_ordered))

    ranked.sort(key=lambda item: (-item[0], item[2][0], item[1]))
    selected: list[int] = []
    selected_set: set[int] = set()
    # Opening/closing editor titles often exist before the first temporal
    # boundary can be observed. Reserve a tiny intro/outro discovery budget so
    # a large title at frame 0 cannot be starved by thousands of later texture
    # epochs. These are still only detector candidates; normal local-CJK and
    # provenance gates decide whether they become authority.
    edge_radius = max(2, int(round(rate * 0.35)))
    edge_candidates = sorted(
        {
            int(row.get("frame_index") or 0)
            for row in ordered
            if int(row.get("frame_index") or 0) <= edge_radius
            or int(row.get("frame_index") or 0)
            >= max(0, duration_frames - 1 - edge_radius)
        }
    )
    for edge_values in (
        [value for value in edge_candidates if value <= edge_radius],
        [
            value
            for value in edge_candidates
            if value >= max(0, duration_frames - 1 - edge_radius)
        ],
    ):
        if not edge_values or len(selected) >= budget:
            continue
        # Consecutive edge frames establish temporal consensus for a title
        # that exists from frame zero; a linspace across the whole edge window
        # can sample only one of its three visible frames.
        reserved = (
            edge_values[: min(3, len(edge_values))]
            if edge_values[0] <= edge_radius
            else edge_values[-min(3, len(edge_values)) :]
        )
        for frame in reserved:
            if frame not in selected_set:
                selected.append(frame)
                selected_set.add(frame)
    depth = 0
    while len(selected) < budget:
        added = False
        for _score, _index, frames in ranked:
            if depth >= len(frames):
                continue
            frame = frames[depth]
            if frame not in selected_set:
                selected.append(frame)
                selected_set.add(frame)
                added = True
                if len(selected) >= budget:
                    break
        if not added:
            break
        depth += 1
    selected.sort()
    persistent_epochs = sum(
        1
        for _score, _index, frames in ranked
        if frames and frames[-1] - frames[0] + 1 >= duration_frames * 0.50
    )
    return selected, {
        "policy": "spatial_temporal_epoch_budget_v1",
        "candidate_rows": len(ordered),
        "candidate_epochs": len(epochs),
        "persistent_epochs": persistent_epochs,
        "boundary_frames": sorted(boundary_set),
        "boundary_epochs": sum(
            1
            for _score, _index, frames in ranked
            if any(
                abs(frame - boundary) <= boundary_radius
                for frame in frames
                for boundary in boundary_set
            )
        ),
        "selected_frames": len(selected),
        "edge_reserved_frames": sorted(
            frame
            for frame in selected_set
            if frame <= edge_radius
            or frame >= max(0, duration_frames - 1 - edge_radius)
        ),
        "max_frames": budget,
        "network_calls": 0,
        "model_calls": 0,
    }


def _odd(value: int) -> int:
    result = max(3, int(value))
    return result if result % 2 else result + 1


def local_textness_mask(gray: np.ndarray) -> np.ndarray:
    """Return a deterministic stroke map that supports dark and bright text."""

    if gray.ndim != 2 or gray.size == 0:
        return np.zeros(gray.shape[:2], dtype=np.uint8)
    height, width = gray.shape[:2]
    normalized = cv2.createCLAHE(
        clipLimit=1.8,
        tileGridSize=(max(2, min(8, width // 24)), max(2, min(8, height // 12))),
    ).apply(gray)
    horizontal = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (_odd(max(5, width // 18)), _odd(max(3, height // 5))),
    )
    blackhat = cv2.morphologyEx(normalized, cv2.MORPH_BLACKHAT, horizontal)
    tophat = cv2.morphologyEx(normalized, cv2.MORPH_TOPHAT, horizontal)
    stroke = cv2.max(blackhat, tophat)
    gradient = cv2.convertScaleAbs(cv2.Scharr(normalized, cv2.CV_16S, 1, 0))
    response = cv2.max(stroke, gradient)
    percentile = float(np.percentile(response, 86.0))
    threshold = max(14.0, percentile)
    binary = np.where(response >= threshold, 255, 0).astype(np.uint8)
    binary = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1)),
    )

    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    kept = np.zeros_like(binary)
    min_area = max(2, int(round(binary.size * 0.0008)))
    for label in range(1, count):
        x, y, component_width, component_height, area = (
            int(value) for value in stats[label]
        )
        if area < min_area or component_width < 2 or component_height < 2:
            continue
        if component_height > max(6, int(round(height * 0.92))):
            continue
        kept[labels == label] = 255
    return kept


def stylized_outline_text_mask(frame_bgr: np.ndarray) -> np.ndarray:
    """Return a conservative mask for coloured/outlined title glyphs.

    The normal proxy textness map is intentionally grayscale and excels at
    thin subtitle strokes.  Intro cards frequently use a saturated (yellow,
    red, etc.) fill with a dark outline; those glyphs can therefore disappear
    from the proxy residual even though DBNet sees them at full resolution.
    This helper only supplies discovery evidence and never promotes a track on
    its own.  Requiring a bright chromatic fill adjacent to a dark outline and
    connected row-shaped components keeps skin, hair and garment texture out.
    """

    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3 or frame_bgr.size == 0:
        return np.zeros(frame_bgr.shape[:2], dtype=np.uint8)
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    # Bright chromatic fills cover the common yellow/white title styles while
    # remaining independent of a fixed hue.  Neutral white is accepted only
    # when a dark outline is immediately adjacent.
    chromatic = (saturation >= 75) & (value >= 125)
    neutral_bright = (saturation <= 72) & (gray >= 168)
    bright = chromatic | neutral_bright
    dark = gray <= 105
    outline = cv2.dilate(
        dark.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        iterations=1,
    ) > 0
    mask = (bright & outline).astype(np.uint8) * 255
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)),
    )
    return mask


def _ranges(values: Sequence[int], *, bridge_gap: int = 1) -> list[list[int]]:
    ordered = sorted({int(value) for value in values})
    if not ordered:
        return []
    output: list[list[int]] = [[ordered[0], ordered[0]]]
    for value in ordered[1:]:
        if value <= output[-1][1] + max(1, int(bridge_gap)) + 1:
            output[-1][1] = value
        else:
            output.append([value, value])
    return output


def _normalized_geometry(
    box: Sequence[float], *, frame_width: int, frame_height: int
) -> dict[str, float]:
    x0, y0, x1, y1 = (float(value) for value in box[:4])
    width = max(1.0, float(frame_width))
    height = max(1.0, float(frame_height))
    return {
        "x": round(max(0.0, min(1.0, x0 / width)), 8),
        "y": round(max(0.0, min(1.0, y0 / height)), 8),
        "width": round(max(0.0, min(1.0, (x1 - x0) / width)), 8),
        "height": round(max(0.0, min(1.0, (y1 - y0) / height)), 8),
    }


def _geometry_delta(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    return max(
        abs(float(left.get(key) or 0.0) - float(right.get(key) or 0.0))
        for key in ("x", "y", "width", "height")
    )


@dataclass
class _Observation:
    score: float
    geometry: dict[str, float]


@dataclass
class _TrackState:
    text_id: str
    start_frame: int
    end_frame: int
    hit_frames: set[int]
    source_box: tuple[float, float, float, float]
    observations: dict[int, _Observation] = field(default_factory=dict)


class CoverageTrackClosure:
    """Accumulate light proxy evidence and close sparse tracks frame-by-frame."""

    def __init__(
        self,
        tracks: Sequence[Mapping[str, Any]],
        *,
        source_width: int,
        source_height: int,
        fps: float,
        search_pad_seconds: float = 0.75,
    ) -> None:
        self.source_width = max(2, int(source_width))
        self.source_height = max(2, int(source_height))
        self.fps = max(1.0, float(fps))
        self.search_pad_frames = max(
            2, int(round(self.fps * max(0.1, float(search_pad_seconds))))
        )
        self._tracks: list[_TrackState] = []
        for index, raw in enumerate(tracks):
            box = list(raw.get("box_coords") or [])
            if len(box) != 4:
                continue
            self._tracks.append(
                _TrackState(
                    text_id=str(raw.get("text_id") or f"sub_{index + 1:02d}"),
                    start_frame=max(0, int(raw.get("start_frame") or 0)),
                    end_frame=max(
                        int(raw.get("start_frame") or 0),
                        int(raw.get("end_frame") or 0),
                    ),
                    hit_frames={int(value) for value in list(raw.get("hit_frames") or [])},
                    source_box=tuple(float(value) for value in box),
                )
            )
        self.scanned_frames = 0
        self._unassigned_candidates: list[dict[str, Any]] = []

    def _observe_unassigned_textness(
        self,
        gray: np.ndarray,
        *,
        frame_index: int,
        frame_bgr: np.ndarray | None = None,
    ) -> None:
        """Record line-like stroke regions outside every known active track.

        This is discovery evidence, not provenance and not OCR. It closes the
        seed-only blind spot: a later high-resolution DBNet pass can inspect
        these exact frames/ROIs, while post-render QA can still fail closed if
        no trustworthy track is produced.
        """

        proxy_height, proxy_width = gray.shape[:2]
        mask = local_textness_mask(gray)
        owned = np.zeros_like(mask)
        sx = proxy_width / float(self.source_width)
        sy = proxy_height / float(self.source_height)
        index = int(frame_index)
        for track in self._tracks:
            if not (
                track.start_frame - self.search_pad_frames
                <= index
                <= track.end_frame + self.search_pad_frames
            ):
                continue
            x0, y0, x1, y1 = track.source_box
            glyph_height = max(3.0, (y1 - y0) * sy)
            pad_x = max(3, int(round(glyph_height * 0.65)))
            pad_y = max(2, int(round(glyph_height * 0.40)))
            px0 = max(0, min(proxy_width - 1, int(np.floor(x0 * sx)) - pad_x))
            py0 = max(0, min(proxy_height - 1, int(np.floor(y0 * sy)) - pad_y))
            px1 = max(px0 + 1, min(proxy_width, int(np.ceil(x1 * sx)) + pad_x))
            py1 = max(py0 + 1, min(proxy_height, int(np.ceil(y1 * sy)) + pad_y))
            owned[py0:py1, px0:px1] = 255
        residual = cv2.bitwise_and(mask, cv2.bitwise_not(owned))
        # Merge a second, colour-aware discovery stream.  It is deliberately
        # bounded to plausible row components below; this prevents a large
        # coloured object from consuming the residual detector budget while
        # rescuing short stylized opening/endcard titles.
        if frame_bgr is not None:
            chromatic = stylized_outline_text_mask(frame_bgr)
            chromatic = cv2.resize(
                chromatic,
                (proxy_width, proxy_height),
                interpolation=cv2.INTER_AREA,
            )
            chromatic = np.where(chromatic >= 96, 255, 0).astype(np.uint8)
            chromatic = cv2.bitwise_and(chromatic, cv2.bitwise_not(owned))
            residual = cv2.max(residual, chromatic)
        join_width = _odd(max(5, int(round(proxy_width * 0.018))))
        grouped = cv2.dilate(
            residual,
            cv2.getStructuringElement(cv2.MORPH_RECT, (join_width, 3)),
            iterations=1,
        )
        count, labels, stats, _ = cv2.connectedComponentsWithStats(grouped, 8)
        candidates: list[dict[str, Any]] = []
        for label in range(1, count):
            x, y, width, height, area = (int(value) for value in stats[label])
            width_frac = width / float(max(1, proxy_width))
            height_frac = height / float(max(1, proxy_height))
            if (
                area < 12
                or width_frac < 0.035
                or height_frac < 0.006
                or height_frac > 0.24
                or width / float(max(1, height)) < 1.05
            ):
                continue
            component = labels == label
            ink_pixels = int(np.count_nonzero(residual[component]))
            ink_density = ink_pixels / float(max(1, width * height))
            # Proxy interpolation can connect bright outlined glyphs into a
            # nearly solid line candidate. DBNet is the downstream validator,
            # so discovery must retain that high-density case for recall.
            if ink_pixels < 8 or not 0.012 <= ink_density <= 0.97:
                continue
            candidates.append(
                {
                    "frame_index": index,
                    "geometry": _normalized_geometry(
                        (
                            x / sx,
                            y / sy,
                            (x + width) / sx,
                            (y + height) / sy,
                        ),
                        frame_width=self.source_width,
                        frame_height=self.source_height,
                    ),
                    "ink_density": round(ink_density, 6),
                    "ink_pixels": ink_pixels,
                }
            )
        if candidates:
            candidates.sort(
                key=lambda row: (
                    float(row["geometry"]["width"])
                    * float(row["geometry"]["height"]),
                    float(row["ink_density"]),
                ),
                reverse=True,
            )
            self._unassigned_candidates.extend(candidates[:4])

    def observe(self, frame_bgr: np.ndarray, *, frame_index: int) -> None:
        if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
            raise ValueError("Coverage proxy frame must be HxWx3 BGR")
        proxy_height, proxy_width = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        index = int(frame_index)
        self._observe_unassigned_textness(
            gray,
            frame_index=index,
            frame_bgr=frame_bgr,
        )
        for track in self._tracks:
            if not (
                track.start_frame - self.search_pad_frames
                <= index
                <= track.end_frame + self.search_pad_frames
            ):
                continue
            sx = proxy_width / float(self.source_width)
            sy = proxy_height / float(self.source_height)
            x0, y0, x1, y1 = track.source_box
            px0, py0, px1, py1 = x0 * sx, y0 * sy, x1 * sx, y1 * sy
            glyph_height = max(3.0, py1 - py0)
            pad_x = max(4, int(round(glyph_height * 0.85)))
            pad_y = max(3, int(round(glyph_height * 0.55)))
            rx0 = max(0, min(proxy_width - 1, int(np.floor(px0)) - pad_x))
            ry0 = max(0, min(proxy_height - 1, int(np.floor(py0)) - pad_y))
            rx1 = max(rx0 + 1, min(proxy_width, int(np.ceil(px1)) + pad_x))
            ry1 = max(ry0 + 1, min(proxy_height, int(np.ceil(py1)) + pad_y))
            crop = gray[ry0:ry1, rx0:rx1]
            mask = local_textness_mask(crop)
            score = float(np.count_nonzero(mask)) / float(max(1, mask.size))
            ys, xs = np.where(mask > 0)
            geometry = _normalized_geometry(
                track.source_box,
                frame_width=self.source_width,
                frame_height=self.source_height,
            )
            if len(xs) >= 4:
                observed = (
                    (rx0 + int(xs.min())) / sx,
                    (ry0 + int(ys.min())) / sy,
                    (rx0 + int(xs.max()) + 1) / sx,
                    (ry0 + int(ys.max()) + 1) / sy,
                )
                ox0 = min(track.source_box[0], observed[0])
                oy0 = min(track.source_box[1], observed[1])
                ox1 = max(track.source_box[2], observed[2])
                oy1 = max(track.source_box[3], observed[3])
                search_area = max(1.0, (rx1 - rx0) * (ry1 - ry0))
                observed_area = max(1.0, (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
                if observed_area / search_area <= 0.82:
                    geometry = _normalized_geometry(
                        (ox0, oy0, ox1, oy1),
                        frame_width=self.source_width,
                        frame_height=self.source_height,
                    )
            track.observations[index] = _Observation(score=score, geometry=geometry)
        self.scanned_frames += 1

    def finalize(self, *, frame_count: int) -> dict[str, Any]:
        last = max(0, int(frame_count) - 1)
        output: list[dict[str, Any]] = []
        for track in self._tracks:
            scores = {index: row.score for index, row in track.observations.items()}
            positive = [scores[index] for index in track.hit_frames if index in scores]
            if not positive:
                positive = [
                    scores[index]
                    for index in scores
                    if track.start_frame <= index <= track.end_frame
                ]
            positive_level = float(np.median(positive)) if positive else 0.0
            outside = [
                score
                for index, score in scores.items()
                if index < track.start_frame or index > track.end_frame
            ]
            background_level = float(np.median(outside)) if outside else 0.0
            separation = max(0.0, positive_level - background_level)
            high = max(0.006, background_level + separation * 0.35)
            low = max(0.004, background_level + separation * 0.20)
            present: set[int] = {
                index for index, score in scores.items() if score >= high
            }
            present.update(index for index in track.hit_frames if index in scores)
            for index, score in scores.items():
                if score < low or index in present:
                    continue
                if index - 1 in present or index + 1 in present:
                    present.add(index)
            ranges = _ranges(sorted(present), bridge_gap=1)
            overlapping = [
                row
                for row in ranges
                if not (row[1] < track.start_frame or row[0] > track.end_frame)
            ]
            if overlapping:
                ranges = overlapping
            elif track.start_frame <= last:
                ranges = [[track.start_frame, min(last, track.end_frame)]]

            selected_frames = {
                index
                for start, end in ranges
                for index in range(max(0, start), min(last, end) + 1)
            }
            keyframes: list[dict[str, Any]] = []
            previous: Mapping[str, Any] | None = None
            for index in sorted(selected_frames):
                observation = track.observations.get(index)
                if observation is None:
                    continue
                geometry = observation.geometry
                if previous is None or _geometry_delta(previous, geometry) >= 0.0015:
                    keyframes.append({"frame_index": index, "geometry": geometry})
                    previous = geometry
            if selected_frames:
                final_index = max(selected_frames)
                final_observation = track.observations.get(final_index)
                if final_observation is not None and (
                    not keyframes or keyframes[-1]["frame_index"] != final_index
                ):
                    keyframes.append(
                        {"frame_index": final_index, "geometry": final_observation.geometry}
                    )
            confidence = 0.50
            if positive_level > 0.0:
                confidence = min(
                    0.99,
                    0.60 + max(0.0, positive_level - background_level) * 3.0,
                )
            output.append(
                {
                    "text_id": track.text_id,
                    "policy_version": COVERAGE_TRACK_POLICY_VERSION,
                    "presence_ranges": ranges,
                    "geometry_keyframes": keyframes,
                    "thresholds": {
                        "high": round(high, 6),
                        "low": round(low, 6),
                        "positive_level": round(positive_level, 6),
                        "background_level": round(background_level, 6),
                    },
                    "confidence": round(confidence, 6),
                    "fail_closed": True,
                }
            )
        return {
            "schema_version": COVERAGE_TRACK_SCHEMA_VERSION,
            "policy_version": COVERAGE_TRACK_POLICY_VERSION,
            "network_calls": 0,
            "scanned_frames": int(self.scanned_frames),
            "frame_count": int(frame_count),
            "tracks": output,
            "unassigned_candidate_frames": sorted(
                {
                    int(row["frame_index"])
                    for row in self._unassigned_candidates
                }
            ),
            "unassigned_candidates": list(self._unassigned_candidates),
        }
