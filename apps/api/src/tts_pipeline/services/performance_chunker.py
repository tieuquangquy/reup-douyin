"""Semantic/prosodic performance units over the immutable TTS timeline."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

from src.tts_pipeline.services.temporal_dialogue import merge_vietnamese_text
from src.tts_pipeline.types import (
    PerformanceChunk,
    ProsodySegment,
    TtsDirectorPlan,
    TranslationInputSegment,
)


PERFORMANCE_CHUNKER_VERSION = "prosodic-semantic-chunker-v1"
MAX_PERFORMANCE_CHUNK_SPAN_MS = 12_000
MAX_PERFORMANCE_CHUNK_GAP_MS = 450


def build_performance_chunks(
    segments: Sequence[TranslationInputSegment],
    *,
    director_plan: TtsDirectorPlan,
    scene_boundaries: Sequence[int] | None = None,
    max_span_ms: int = MAX_PERFORMANCE_CHUNK_SPAN_MS,
) -> tuple[list[PerformanceChunk], dict]:
    ordered = sorted(segments, key=lambda row: (row.start_ms, row.segment_index))
    by_id = {
        str(row.translation_segment_id): row
        for row in director_plan.prosody_segments
    }
    boundaries = sorted({int(value) for value in list(scene_boundaries or [])})
    chunks: list[PerformanceChunk] = []
    current: list[TranslationInputSegment] = []
    reasons: list[str] = []

    def flush() -> None:
        nonlocal current, reasons
        if not current:
            return
        plans = tuple(
            by_id[str(row.translation_segment_id)]
            for row in current
            if str(row.translation_segment_id) in by_id
        )
        if not plans:
            current = []
            reasons = []
            return
        previous_state = plans[0].previous_state
        target_state = plans[-1].target_state
        payload = {
            "source_video_id": str(current[0].source_video_id),
            "member_translation_segment_ids": [str(row.translation_segment_id) for row in current],
            "start_ms": current[0].start_ms,
            "end_ms": current[-1].end_ms,
            "director_version": director_plan.director_version,
        }
        chunk_id = "chunk-" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        text = ""
        for row in current:
            text = merge_vietnamese_text(text, row.translated_text)
        chunks.append(
            PerformanceChunk(
                chunk_id=chunk_id,
                source_video_id=current[0].source_video_id,
                start_ms=current[0].start_ms,
                end_ms=current[-1].end_ms,
                translated_text=text,
                member_translation_segment_ids=tuple(row.translation_segment_id for row in current),
                member_segment_indices=tuple(row.segment_index for row in current),
                speaker_label=current[0].speaker_label,
                prosody_segments=plans,
                previous_state=previous_state,
                target_state=target_state,
                boundary_reasons=tuple(dict.fromkeys(reasons)),
            )
        )
        current = []
        reasons = []

    previous: TranslationInputSegment | None = None
    for row in ordered:
        plan = by_id.get(str(row.translation_segment_id))
        if plan is None:
            continue
        boundary = _boundary_reason(
            previous,
            row,
            plan,
            scene_boundaries=boundaries,
            current_start=current[0].start_ms if current else None,
            max_span_ms=max_span_ms,
        )
        if boundary and current:
            reasons.append(boundary)
            flush()
        elif boundary:
            reasons.append(boundary)
        current.append(row)
        previous = row
    flush()
    report = {
        "schema_version": "performance-chunk-plan-v1",
        "chunker_version": PERFORMANCE_CHUNKER_VERSION,
        "input_segment_count": len(ordered),
        "chunk_count": len(chunks),
        "chunks": [chunk.to_dict() for chunk in chunks],
    }
    return chunks, report


def _boundary_reason(
    previous: TranslationInputSegment | None,
    current: TranslationInputSegment,
    plan: ProsodySegment,
    *,
    scene_boundaries: Sequence[int],
    current_start: int | None,
    max_span_ms: int,
) -> str | None:
    if previous is None:
        return "initial_chunk"
    if previous.speaker_label and current.speaker_label and previous.speaker_label != current.speaker_label:
        return "speaker_boundary"
    gap = int(current.start_ms) - int(previous.end_ms)
    if gap > MAX_PERFORMANCE_CHUNK_GAP_MS:
        return "breath_boundary"
    if current_start is not None and int(current.end_ms) - int(current_start) > max_span_ms:
        return "max_performance_span"
    if any(int(previous.end_ms) <= value <= int(current.start_ms) for value in scene_boundaries):
        return "scene_boundary"
    if plan.transition in {"contrast", "conclusion", "question"}:
        return "semantic_transition"
    return None
