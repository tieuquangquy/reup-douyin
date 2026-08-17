"""Planning helpers for the low-call Gemini expressive synthesis lane.

The provider still returns ordinary WAV audio.  This module only decides which
approved translation candidate is spoken and whether a narration fits in one
provider request or needs a small number of timeline blocks.  It deliberately
does not know about HTTP, storage, jobs, or SQLAlchemy.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from src.audio_pipeline.speech_budget import count_spoken_units
from src.tts_pipeline.services.input_preflight import rank_preflight_candidates
from src.tts_pipeline.services.speech_text import build_vietnamese_speech_text
from src.tts_pipeline.types import TranslationInputSegment


GEMINI_WHOLE_VIDEO_VERSION = "gemini-whole-video-v1"


@dataclass(frozen=True)
class GeminiNarrationBlock:
    block_index: int
    segments: tuple[TranslationInputSegment, ...]
    start_ms: int
    end_ms: int

    @property
    def duration_seconds(self) -> float:
        return max(0.001, (self.end_ms - self.start_ms) / 1000.0)


def resolve_gemini_synthesis_strategy(
    *,
    provider: str,
    expressive_options: Mapping[str, object] | None,
) -> str:
    """Return ``whole_video`` only for an explicitly compatible Gemini lane."""

    if str(provider or "").strip().lower() not in {"google_gemini", "google_cloud_tts"}:
        return "segment"
    options = dict(expressive_options or {})
    requested = str(options.get("synthesis_strategy") or "whole_video").strip().lower()
    if requested not in {"whole_video", "auto_blocks", "segment"}:
        requested = "whole_video"
    if str(options.get("single_voice_mode") or "off").strip().lower() != "required":
        return "segment"
    return requested


def select_whole_video_candidates(
    segments: Sequence[TranslationInputSegment],
    *,
    units_per_second: float,
    pronunciation_glossary: Mapping[str, str] | None = None,
    compact_trigger_ratio: float = 0.88,
) -> list[TranslationInputSegment]:
    """Choose a safe, already-approved candidate before any paid request.

    Whole-video synthesis is fitted once at block level.  We still remove
    obvious per-row timing risks up front so one unusually dense sentence does
    not force the whole performance to run unnaturally fast.
    """

    safe_units_per_second = max(0.5, float(units_per_second))
    trigger = max(0.65, min(1.0, float(compact_trigger_ratio)))
    selected: list[TranslationInputSegment] = []
    for segment in segments:
        budget_seconds = max(0.1, segment.duration_budget_ms / 1000.0)
        ranked = rank_preflight_candidates(
            segment,
            slot_seconds=budget_seconds,
            units_per_second=safe_units_per_second,
            pronunciation_glossary=dict(pronunciation_glossary or {}),
        ) or [str(segment.translated_text or "").strip()]
        ranked = list(dict.fromkeys(text.strip() for text in ranked if text.strip()))
        primary = str(segment.translated_text or "").strip() or ranked[0]
        primary_speech = build_vietnamese_speech_text(
            primary,
            pronunciation_glossary=dict(pronunciation_glossary or {}),
        ).speech_text
        predicted_ratio = count_spoken_units(primary_speech) / (
            budget_seconds * safe_units_per_second
        )
        chosen = primary
        repair_actions = list(segment.repair_actions)
        compact_candidates = [text for text in ranked if text != primary]
        if predicted_ratio > trigger and compact_candidates:
            chosen = min(
                compact_candidates,
                key=lambda text: (count_spoken_units(text), ranked.index(text)),
            )
            if chosen != primary:
                repair_actions.append("gemini_whole_video_compact_preflight")
        selected.append(
            replace(
                segment,
                translated_text=chosen,
                repair_actions=tuple(dict.fromkeys(repair_actions)),
            )
        )
    return selected


def build_gemini_narration_blocks(
    segments: Sequence[TranslationInputSegment],
    *,
    strategy: str,
    max_whole_video_seconds: float = 180.0,
    max_block_seconds: float = 45.0,
    max_request_chars: int = 6_000,
) -> list[GeminiNarrationBlock]:
    """Keep normal short-form narration in one request, otherwise bound blocks."""

    rows = sorted(segments, key=lambda row: (row.start_ms, row.segment_index))
    if not rows:
        return []
    normalized_strategy = str(strategy or "segment").strip().lower()
    whole_span = max(0.001, (rows[-1].end_ms - rows[0].start_ms) / 1000.0)
    char_count = sum(len(str(row.translated_text or "")) for row in rows)
    if (
        normalized_strategy == "whole_video"
        and whole_span <= max(30.0, float(max_whole_video_seconds))
        and char_count <= max(500, int(max_request_chars))
    ):
        return [
            GeminiNarrationBlock(
                block_index=0,
                segments=tuple(rows),
                start_ms=rows[0].start_ms,
                end_ms=rows[-1].end_ms,
            )
        ]

    block_limit_ms = int(round(max(15.0, min(120.0, float(max_block_seconds))) * 1000.0))
    char_limit = max(500, int(max_request_chars))
    blocks: list[GeminiNarrationBlock] = []
    current: list[TranslationInputSegment] = []
    current_chars = 0
    for row in rows:
        proposed_start = current[0].start_ms if current else row.start_ms
        proposed_span = row.end_ms - proposed_start
        proposed_chars = current_chars + len(str(row.translated_text or ""))
        if current and (proposed_span > block_limit_ms or proposed_chars > char_limit):
            blocks.append(
                GeminiNarrationBlock(
                    block_index=len(blocks),
                    segments=tuple(current),
                    start_ms=current[0].start_ms,
                    end_ms=current[-1].end_ms,
                )
            )
            current = []
            current_chars = 0
        current.append(row)
        current_chars += len(str(row.translated_text or ""))
    if current:
        blocks.append(
            GeminiNarrationBlock(
                block_index=len(blocks),
                segments=tuple(current),
                start_ms=current[0].start_ms,
                end_ms=current[-1].end_ms,
            )
        )
    return blocks


def boundary_pause_tag(gap_ms: int) -> str:
    if int(gap_ms) >= 650:
        return "[long pause]"
    if int(gap_ms) >= 120:
        return "[short pause]"
    return ""
