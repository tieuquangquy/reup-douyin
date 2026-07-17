"""Adapt media_pipeline Phase 2 OCR payloads into Pilot A ocr_pipeline types."""

from __future__ import annotations

from typing import Any, Mapping

from src.ocr_pipeline.hardsub_filter import group_hard_sub_events
from src.ocr_pipeline.types import FrameOcrResult, HardSubEvent, OcrBox


def frame_results_from_ocr_payload(payload: Mapping[str, Any]) -> list[FrameOcrResult]:
    """Map ``OcrFilteringResult.to_dict()`` frames → ``FrameOcrResult`` list."""
    frames_raw = payload.get("frames")
    if not isinstance(frames_raw, list):
        return []
    results: list[FrameOcrResult] = []
    for frame in frames_raw:
        if not isinstance(frame, Mapping):
            continue
        time_ms = int(frame.get("time_ms") or 0)
        width = int(frame.get("frame_width") or 0) or 1080
        height = int(frame.get("frame_height") or 0) or 1920
        boxes: list[OcrBox] = []
        for box in frame.get("boxes") or []:
            if not isinstance(box, Mapping):
                continue
            text = str(box.get("text") or "").strip()
            boxes.append(
                OcrBox(
                    x=float(box.get("x") or 0.0),
                    y=float(box.get("y") or 0.0),
                    width=max(0.01, float(box.get("width") or 0.01)),
                    height=max(0.01, float(box.get("height") or 0.01)),
                    text=text,
                    confidence=float(box.get("confidence") or 0.0),
                )
            )
        results.append(
            FrameOcrResult(
                frame_time_ms=time_ms,
                frame_width=width,
                frame_height=height,
                boxes=boxes,
            )
        )
    return results


def hardsub_events_from_ocr_payload(
    payload: Mapping[str, Any],
    *,
    band_ratio: float,
) -> list[HardSubEvent]:
    """Build timed hard-sub events from Phase 2 JSON (boxes already band-filtered)."""
    frame_results = frame_results_from_ocr_payload(payload)
    return group_hard_sub_events(frame_results, band_ratio=band_ratio)
