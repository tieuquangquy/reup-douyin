from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from src.audio_pipeline.speech_budget import assess_speech_budget, count_spoken_units
from src.tts_pipeline.types import TranslationInputSegment


MICRO_SEGMENT_MS = 1_200
MAX_MERGE_GAP_MS = 450
MAX_GROUP_SPAN_MS = 12_000
MIN_INTER_SEGMENT_GAP_MS = 80
MAX_BORROWED_PAUSE_MS = 320


def build_temporal_dialogue_timeline(
    segments: Iterable[TranslationInputSegment],
    *,
    timeline_duration_ms: int,
    units_per_second: float,
) -> tuple[list[TranslationInputSegment], dict]:
    """Repair micro boundaries and allocate safe pause before TTS synthesis.

    ASR rows remain immutable.  Returned rows are a hashable TTS/subtitle timeline
    whose metadata records every source member and automatic repair decision.
    """

    ordered = sorted(segments, key=lambda row: (row.start_ms, row.segment_index))
    if not ordered:
        return [], _report([], [], units_per_second)

    normalized = [_normalize_members(row) for row in ordered]
    groups: list[TranslationInputSegment] = []
    decisions: list[dict] = []
    index = 0
    while index < len(normalized):
        current = normalized[index]
        is_micro = _is_micro(current)
        too_long = _budget_status(current, units_per_second) == "too_long"

        if is_micro and groups and _can_merge(groups[-1], current):
            previous = groups.pop()
            merged = _merge(previous, current, "merge_micro_left")
            groups.append(merged)
            decisions.append(_decision("MERGE_LEFT", current, merged, "micro_segment"))
            index += 1
            continue

        if (is_micro or too_long) and index + 1 < len(normalized) and _can_merge(current, normalized[index + 1]):
            next_row = normalized[index + 1]
            merged = _merge(
                current,
                next_row,
                "merge_micro_right" if is_micro else "merge_over_budget_right",
            )
            groups.append(merged)
            decisions.append(
                _decision(
                    "MERGE_RIGHT",
                    current,
                    merged,
                    "micro_segment" if is_micro else "speech_budget_overflow",
                )
            )
            index += 2
            continue

        groups.append(current)
        index += 1

    allocated: list[TranslationInputSegment] = []
    for position, row in enumerate(groups):
        next_start = groups[position + 1].start_ms if position + 1 < len(groups) else timeline_duration_ms
        available_gap = max(0, next_start - row.end_ms - MIN_INTER_SEGMENT_GAP_MS)
        borrowed = min(MAX_BORROWED_PAUSE_MS, available_gap)
        if borrowed > 0 and _budget_status(row, units_per_second) != "too_short":
            updated = replace(
                row,
                end_ms=min(timeline_duration_ms, row.end_ms + borrowed),
                duration_budget_ms=row.duration_budget_ms + borrowed,
                repair_actions=(*row.repair_actions, "borrow_following_pause"),
            )
            decisions.append(
                {
                    "decision": "BORROW_PAUSE",
                    "member_segment_indices": list(updated.member_segment_indices),
                    "borrowed_ms": borrowed,
                    "start_ms": updated.start_ms,
                    "end_ms": updated.end_ms,
                }
            )
            allocated.append(updated)
        else:
            allocated.append(row)

    return allocated, _report(normalized, allocated, units_per_second, decisions)


def merge_vietnamese_text(left: str, right: str) -> str:
    """Join adjacent translations while removing a repeated word boundary."""

    left_words = _words(left)
    right_words = _words(right)
    if not left_words:
        return " ".join(right_words)
    if not right_words:
        return " ".join(left_words)
    max_overlap = min(5, len(left_words), len(right_words))
    overlap = 0
    for size in range(max_overlap, 0, -1):
        if [word.casefold() for word in left_words[-size:]] == [
            word.casefold() for word in right_words[:size]
        ]:
            overlap = size
            break
    return " ".join([*left_words, *right_words[overlap:]]).strip()


def _normalize_members(row: TranslationInputSegment) -> TranslationInputSegment:
    return replace(
        row,
        member_translation_segment_ids=(
            row.member_translation_segment_ids or (row.translation_segment_id,)
        ),
        member_transcript_segment_ids=(
            row.member_transcript_segment_ids or (row.transcript_segment_id,)
        ),
        member_segment_indices=(row.member_segment_indices or (row.segment_index,)),
        original_start_ms=(row.original_start_ms if row.original_start_ms is not None else row.start_ms),
        original_end_ms=(row.original_end_ms if row.original_end_ms is not None else row.end_ms),
    )


def _is_micro(row: TranslationInputSegment) -> bool:
    return (row.end_ms - row.start_ms) < MICRO_SEGMENT_MS or count_spoken_units(row.translated_text) <= 2


def _same_speaker(left: TranslationInputSegment, right: TranslationInputSegment) -> bool:
    if not left.speaker_label or not right.speaker_label:
        return True
    return left.speaker_label == right.speaker_label


def _can_merge(left: TranslationInputSegment, right: TranslationInputSegment) -> bool:
    gap = right.start_ms - left.end_ms
    span = right.end_ms - left.start_ms
    return (
        0 <= gap <= MAX_MERGE_GAP_MS
        and span <= MAX_GROUP_SPAN_MS
        and _same_speaker(left, right)
    )


def _merge(left: TranslationInputSegment, right: TranslationInputSegment, action: str) -> TranslationInputSegment:
    text = merge_vietnamese_text(left.translated_text, right.translated_text)
    source_text = " ".join(part for part in (left.source_text, right.source_text) if part).strip()
    # A candidate belonging to only one ASR row is never a valid candidate for a
    # repaired group: using it would silently drop the other half of the meaning.
    # Compose bounded cross-row alternatives and keep the approved merged text first.
    left_options = (left.translated_text, *left.candidate_texts[:3])
    right_options = (right.translated_text, *right.candidate_texts[:3])
    candidates = tuple(
        dict.fromkeys(
            merge_vietnamese_text(left_text, right_text)
            for left_text in left_options
            for right_text in right_options
            if left_text.strip() and right_text.strip()
        )
    )[:8]
    return replace(
        left,
        end_ms=right.end_ms,
        translated_text=text,
        duration_budget_ms=right.end_ms - left.start_ms,
        quality_flags=list(dict.fromkeys([*left.quality_flags, *right.quality_flags, "temporal_boundary_repaired"])),
        source_text=source_text,
        member_translation_segment_ids=(
            *left.member_translation_segment_ids,
            *right.member_translation_segment_ids,
        ),
        member_transcript_segment_ids=(
            *left.member_transcript_segment_ids,
            *right.member_transcript_segment_ids,
        ),
        member_segment_indices=(*left.member_segment_indices, *right.member_segment_indices),
        candidate_texts=candidates,
        original_start_ms=left.original_start_ms,
        original_end_ms=right.original_end_ms,
        repair_actions=(*left.repair_actions, *right.repair_actions, action),
        source_prosody=_merge_source_prosody(left.source_prosody, right.source_prosody),
    )


def _merge_source_prosody(left: dict, right: dict) -> dict:
    left_row = dict(left or {})
    right_row = dict(right or {})
    articulation = float(left_row.get("articulation_ms") or 0.0) + float(
        right_row.get("articulation_ms") or 0.0
    )
    pauses = float(left_row.get("internal_pause_ms") or 0.0) + float(
        right_row.get("internal_pause_ms") or 0.0
    )
    return {
        "schema_version": "source_phrase_prosody_v1",
        "word_timestamp_count": int(left_row.get("word_timestamp_count") or 0)
        + int(right_row.get("word_timestamp_count") or 0),
        "articulation_ms": round(articulation, 3),
        "internal_pause_ms": round(pauses, 3),
        "phrase_end_punctuation": right_row.get("phrase_end_punctuation") or "",
        "speaker_label": left_row.get("speaker_label") or right_row.get("speaker_label"),
        "authority": (
            "local_asr_word_timestamps"
            if "local_asr_word_timestamps"
            in {left_row.get("authority"), right_row.get("authority")}
            else "segment_timeline_only"
        ),
    }


def _budget_status(row: TranslationInputSegment, units_per_second: float) -> str:
    return assess_speech_budget(
        row.translated_text,
        slot_seconds=max(0.001, row.duration_budget_ms / 1000.0),
        units_per_second=units_per_second,
    ).status


def _decision(decision: str, source: TranslationInputSegment, output: TranslationInputSegment, reason: str) -> dict:
    return {
        "decision": decision,
        "reason": reason,
        "source_segment_index": source.segment_index,
        "member_segment_indices": list(output.member_segment_indices),
        "start_ms": output.start_ms,
        "end_ms": output.end_ms,
    }


def _report(
    inputs: list[TranslationInputSegment],
    outputs: list[TranslationInputSegment],
    units_per_second: float,
    decisions: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": "temporal_dialogue_graph_v1",
        "strategy": "context_aware_timeline_constraint",
        "input_segment_count": len(inputs),
        "dialogue_group_count": len(outputs),
        "merged_segment_count": max(0, len(inputs) - len(outputs)),
        "units_per_second": round(float(units_per_second), 6),
        "decisions": list(decisions or []),
        "groups": [
            {
                "segment_index": row.segment_index,
                "member_segment_indices": list(row.member_segment_indices),
                "member_translation_segment_ids": [str(value) for value in row.member_translation_segment_ids],
                "start_ms": row.start_ms,
                "end_ms": row.end_ms,
                "duration_budget_ms": row.duration_budget_ms,
                "spoken_units": count_spoken_units(row.translated_text),
                "repair_actions": list(row.repair_actions),
            }
            for row in outputs
        ],
    }


def _words(text: str) -> list[str]:
    return [part for part in " ".join(str(text or "").split()).split(" ") if part]
