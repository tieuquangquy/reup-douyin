from __future__ import annotations

import re

from src.audio_pipeline.types import TranscriptDraftSegment, TranscriptionUnit


class TranscriptBuilder:
    def __init__(
        self,
        *,
        min_duration_seconds: float = 0.35,
        max_duration_seconds: float = 12.0,
        low_confidence_threshold: float = 0.65,
    ):
        self.min_duration_seconds = min_duration_seconds
        self.max_duration_seconds = max_duration_seconds
        self.low_confidence_threshold = low_confidence_threshold

    def build(self, units: list[TranscriptionUnit]) -> list[TranscriptDraftSegment]:
        normalized_units = [unit for unit in units if unit.text.strip() and unit.end_seconds > unit.start_seconds]
        normalized_units.sort(key=lambda item: (item.start_seconds, item.end_seconds))
        segments: list[TranscriptDraftSegment] = []
        for unit in normalized_units:
            flags = self._flags_for_unit(unit)
            segments.append(
                TranscriptDraftSegment(
                    segment_index=len(segments),
                    start_seconds=round(unit.start_seconds, 3),
                    end_seconds=round(unit.end_seconds, 3),
                    source_text=unit.text.strip(),
                    normalized_source_text=normalize_source_text(unit.text),
                    confidence=unit.confidence,
                    speaker_label=unit.speaker_label,
                    difficulty_flags=flags,
                    metadata={"raw_payload": unit.raw_payload or {}},
                )
            )
        return segments

    def _flags_for_unit(self, unit: TranscriptionUnit) -> list[str]:
        flags = list(dict.fromkeys(unit.flags))
        duration = unit.end_seconds - unit.start_seconds
        if unit.confidence is not None and unit.confidence < self.low_confidence_threshold:
            flags.append("low_confidence")
        if duration < self.min_duration_seconds:
            flags.append("too_short")
        if duration > self.max_duration_seconds:
            flags.append("too_long")
        if "overlap" in flags or "overlapping_speech" in flags:
            flags.append("overlapping_speech")
        if "background_too_loud" in flags:
            flags.append("background_too_loud")
        if "likely_mistranscribed" in flags:
            flags.append("likely_mistranscribed")
        return list(dict.fromkeys(flags))


def normalize_source_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())
