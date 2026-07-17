from __future__ import annotations

from dataclasses import dataclass


OUTCOME_SCORE_VERSION = "OUTCOME_SCORE_V1"


@dataclass(frozen=True)
class ScoreComponent:
    key: str
    label: str
    raw_input: dict
    subscore: float
    weight: float
    weighted_contribution: float


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, round(value, 2)))


def weighted_component(key: str, label: str, raw_input: dict, subscore: float, weight: float) -> ScoreComponent:
    normalized = clamp_score(subscore)
    return ScoreComponent(
        key=key,
        label=label,
        raw_input=raw_input,
        subscore=normalized,
        weight=weight,
        weighted_contribution=round(normalized * weight / 100, 2),
    )


def outcome_label(total_score: float) -> str:
    if total_score >= 80:
        return "strong"
    if total_score >= 65:
        return "usable"
    if total_score >= 45:
        return "needs_work"
    return "weak"

