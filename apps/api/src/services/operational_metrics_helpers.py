from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class DurationSample:
    group_key: str
    duration_seconds: float


def safe_average(values: Iterable[float]) -> float:
    clean_values = [value for value in values if value >= 0]
    if not clean_values:
        return 0.0
    return round(sum(clean_values) / len(clean_values), 2)


def summarize_counts(rows: Iterable[tuple[str, str, int]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(dict)
    for group_key, status, count in rows:
        summary[str(group_key)][str(status)] = int(count)
    return dict(summary)


def summarize_duration_samples(samples: Iterable[DurationSample]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        if sample.duration_seconds >= 0:
            grouped[sample.group_key].append(sample.duration_seconds)
    return {
        group_key: {
            "sample_count": len(values),
            "average_seconds": safe_average(values),
            "max_seconds": round(max(values), 2) if values else 0.0,
        }
        for group_key, values in grouped.items()
    }


def calculate_failure_rate(status_counts: Mapping[str, int]) -> float:
    total = sum(status_counts.values())
    if total == 0:
        return 0.0
    failed = status_counts.get("FAILED", 0) + status_counts.get("RETRYABLE", 0)
    return round((failed / total) * 100, 2)
