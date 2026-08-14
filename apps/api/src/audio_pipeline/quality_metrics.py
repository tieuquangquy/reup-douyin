"""Offline quality metrics for Analyze Audio corpus benchmarks.

The service has no ground truth at runtime.  This module keeps benchmark
scoring separate from production authority and accepts a small hand-labelled
reference manifest (text + dialogue intervals).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class AudioQualityMetrics:
    cer: float
    wer: float
    timing_iou: float
    false_dialogue_rate: float
    missed_dialogue_rate: float
    predicted_interval_count: int
    reference_interval_count: int

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "schema_version": "audio-quality-metrics-v1",
            "cer": self.cer,
            "wer": self.wer,
            "timing_iou": self.timing_iou,
            "false_dialogue_rate": self.false_dialogue_rate,
            "missed_dialogue_rate": self.missed_dialogue_rate,
            "predicted_interval_count": self.predicted_interval_count,
            "reference_interval_count": self.reference_interval_count,
        }


def evaluate_audio_quality(
    *,
    reference_text: str,
    predicted_text: str,
    reference_intervals: Sequence[Sequence[float]],
    predicted_intervals: Sequence[Sequence[float]],
) -> AudioQualityMetrics:
    reference = _valid_intervals(reference_intervals)
    predicted = _valid_intervals(predicted_intervals)
    return AudioQualityMetrics(
        cer=round(_error_rate(_characters(reference_text), _characters(predicted_text)), 6),
        wer=round(
            _error_rate(reference_text.split(), predicted_text.split()),
            6,
        ),
        timing_iou=round(_mean_best_iou(predicted, reference), 6),
        false_dialogue_rate=round(_unmatched_rate(predicted, reference), 6),
        missed_dialogue_rate=round(_unmatched_rate(reference, predicted), 6),
        predicted_interval_count=len(predicted),
        reference_interval_count=len(reference),
    )


def _error_rate(reference: Sequence[str], predicted: Sequence[str]) -> float:
    if not reference:
        return 0.0 if not predicted else 1.0
    previous = list(range(len(predicted) + 1))
    for row_index, expected in enumerate(reference, start=1):
        current = [row_index]
        for column_index, actual in enumerate(predicted, start=1):
            substitution = previous[column_index - 1] + (expected != actual)
            insertion = current[column_index - 1] + 1
            deletion = previous[column_index] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return min(1.0, previous[-1] / max(1, len(reference)))


def _characters(value: str) -> list[str]:
    return [character for character in value if not character.isspace()]


def _valid_intervals(values: Sequence[Sequence[float]]) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for value in values:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            continue
        try:
            start, end = max(0.0, float(value[0])), max(0.0, float(value[1]))
        except (TypeError, ValueError):
            continue
        if end > start:
            result.append((start, end))
    return result


def _iou(left: tuple[float, float], right: tuple[float, float]) -> float:
    intersection = max(0.0, min(left[1], right[1]) - max(left[0], right[0]))
    union = max(left[1], right[1]) - min(left[0], right[0])
    return intersection / union if union > 0 else 0.0


def _mean_best_iou(
    predicted: Sequence[tuple[float, float]],
    reference: Sequence[tuple[float, float]],
) -> float:
    if not predicted:
        return 1.0 if not reference else 0.0
    return sum(max((_iou(row, expected) for expected in reference), default=0.0) for row in predicted) / len(predicted)


def _unmatched_rate(
    measured: Sequence[tuple[float, float]],
    authority: Sequence[tuple[float, float]],
) -> float:
    if not measured:
        return 0.0
    return sum(
        1
        for row in measured
        if max((_iou(row, expected) for expected in authority), default=0.0) < 0.25
    ) / len(measured)
