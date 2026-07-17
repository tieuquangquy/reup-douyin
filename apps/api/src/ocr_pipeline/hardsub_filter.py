"""Hard-sub band filter and temporal event grouping."""

from __future__ import annotations

from src.ocr_pipeline.types import (
    DEFAULT_HARD_SUB_BAND_RATIO,
    DEFAULT_MIN_STABLE_SAMPLES,
    FrameOcrResult,
    HardSubEvent,
    OcrBox,
)


def is_in_hard_sub_band(box: OcrBox, *, band_ratio: float = DEFAULT_HARD_SUB_BAND_RATIO) -> bool:
    """True when box center falls in the bottom band of the frame."""
    ratio = max(0.05, min(0.6, float(band_ratio)))
    band_top = 1.0 - ratio
    center_y = box.y + (box.height / 2.0)
    return center_y >= band_top


def filter_hard_sub_boxes(
    boxes: list[OcrBox],
    *,
    band_ratio: float = DEFAULT_HARD_SUB_BAND_RATIO,
) -> list[OcrBox]:
    return [box for box in boxes if is_in_hard_sub_band(box, band_ratio=band_ratio)]


def _union_box(boxes: list[OcrBox]) -> OcrBox:
    x0 = min(b.x for b in boxes)
    y0 = min(b.y for b in boxes)
    x1 = max(b.x + b.width for b in boxes)
    y1 = max(b.y + b.height for b in boxes)
    texts = [b.text for b in boxes if b.text.strip()]
    conf = sum(b.confidence for b in boxes) / max(1, len(boxes))
    return OcrBox(x=x0, y=y0, width=max(0.01, x1 - x0), height=max(0.01, y1 - y0), text=" | ".join(texts[:8]), confidence=conf)


def group_hard_sub_events(
    frames: list[FrameOcrResult],
    *,
    band_ratio: float = DEFAULT_HARD_SUB_BAND_RATIO,
    min_stable_samples: int = DEFAULT_MIN_STABLE_SAMPLES,
    gap_ms: int = 800,
) -> list[HardSubEvent]:
    """Merge consecutive sampled frames that have bottom-band text into timed events."""
    samples: list[tuple[int, OcrBox]] = []
    for frame in sorted(frames, key=lambda f: f.frame_time_ms):
        hard = filter_hard_sub_boxes(frame.boxes, band_ratio=band_ratio)
        if not hard:
            continue
        samples.append((frame.frame_time_ms, _union_box(hard)))

    if not samples:
        return []

    events: list[HardSubEvent] = []
    cluster_times = [samples[0][0]]
    cluster_boxes = [samples[0][1]]

    def flush() -> None:
        nonlocal cluster_times, cluster_boxes
        if not cluster_times:
            return
        union = _union_box(cluster_boxes)
        unstable = len(cluster_times) < max(1, min_stable_samples)
        events.append(
            HardSubEvent(
                start_ms=cluster_times[0],
                end_ms=cluster_times[-1],
                x=union.x,
                y=union.y,
                width=union.width,
                height=union.height,
                sample_count=len(cluster_times),
                avg_confidence=union.confidence,
                texts=[t for t in union.text.split(" | ") if t] if union.text else [],
                unstable=unstable,
            )
        )
        cluster_times = []
        cluster_boxes = []

    for time_ms, box in samples[1:]:
        if time_ms - cluster_times[-1] <= gap_ms:
            cluster_times.append(time_ms)
            cluster_boxes.append(box)
        else:
            flush()
            cluster_times = [time_ms]
            cluster_boxes = [box]
    flush()
    return events


def stable_hard_sub_band(
    events: list[HardSubEvent],
    *,
    band_ratio: float = DEFAULT_HARD_SUB_BAND_RATIO,
) -> tuple[float, float, float, float]:
    """Return normalized (x, y, w, h) band to blur — prefer union of stable events, else default bottom band."""
    stable = [e for e in events if not e.unstable]
    use = stable or events
    if not use:
        return 0.0, 1.0 - band_ratio, 1.0, band_ratio
    x0 = min(e.x for e in use)
    y0 = min(e.y for e in use)
    x1 = max(e.x + e.width for e in use)
    y1 = max(e.y + e.height for e in use)
    # Expand slightly so burn edges are covered.
    pad_y = 0.02
    y0 = max(0.0, y0 - pad_y)
    y1 = min(1.0, y1 + pad_y)
    return 0.0, y0, 1.0, max(band_ratio * 0.5, y1 - y0)
