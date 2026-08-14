"""Local temporal quality gate for ASR units."""

from __future__ import annotations

from dataclasses import replace

from src.audio_pipeline.types import TranscriptionUnit


def validate_transcription_timeline(
    units: list[TranscriptionUnit],
    *,
    duration_seconds: float | None,
    speech_intervals: list[list[float]] | tuple[tuple[float, float], ...] | None = None,
) -> list[TranscriptionUnit]:
    duration = max(0.0, float(duration_seconds or 0.0))
    intervals = [
        (max(0.0, float(item[0])), max(0.0, float(item[1])))
        for item in (speech_intervals or [])
        if len(item) >= 2 and float(item[1]) > float(item[0])
    ]
    ordered = sorted(units, key=lambda unit: (unit.start_seconds, unit.end_seconds))
    validated: list[TranscriptionUnit] = []
    previous_end = 0.0
    for unit in ordered:
        start = max(0.0, float(unit.start_seconds))
        end = max(start + 0.05, float(unit.end_seconds))
        flags = list(unit.flags or [])
        if duration > 0 and (start > duration or end > duration):
            start = min(start, max(0.0, duration - 0.05))
            end = min(duration, max(start + 0.05, end))
            _append_once(flags, "asr_window_clamped")
        if validated and start < previous_end - 0.12:
            _append_once(flags, "asr_temporal_overlap")
        if intervals and not _overlaps_any(start, end, intervals, tolerance=0.25):
            _append_once(flags, "asr_outside_vad_speech")
        raw = dict(unit.raw_payload or {})
        raw["temporal_validation"] = {
            "duration_seconds": duration or None,
            "vad_interval_count": len(intervals),
        }
        validated.append(
            replace(
                unit,
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                flags=flags,
                raw_payload=raw,
            )
        )
        previous_end = max(previous_end, end)
    return validated


def _overlaps_any(
    start: float,
    end: float,
    intervals: list[tuple[float, float]],
    *,
    tolerance: float,
) -> bool:
    return any(min(end, right + tolerance) > max(start, left - tolerance) for left, right in intervals)


def _append_once(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)

