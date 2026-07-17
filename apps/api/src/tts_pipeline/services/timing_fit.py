from __future__ import annotations

from src.tts_pipeline.types import TimingFitStatus


def classify_timing_fit(actual_duration_seconds: float, budget_seconds: float) -> tuple[TimingFitStatus, float]:
    if budget_seconds <= 0:
        return TimingFitStatus.TOO_LONG, 999.0
    ratio = actual_duration_seconds / budget_seconds
    if ratio <= 0.55:
        return TimingFitStatus.TOO_SHORT, ratio
    if ratio <= 1.05:
        return TimingFitStatus.FITS_WELL, ratio
    if ratio <= 1.25:
        return TimingFitStatus.SLIGHTLY_LONG, ratio
    return TimingFitStatus.TOO_LONG, ratio


def timing_fit_flags(status: TimingFitStatus) -> list[str]:
    if status == TimingFitStatus.FITS_WELL:
        return []
    return [status.value]
