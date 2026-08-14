"""Deterministic, provider-agnostic initial-rate planning for timeline TTS."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.audio_pipeline.speech_budget import assess_speech_budget


DURATION_PLANNER_VERSION = "tts_duration_planner_v1"
MAX_INITIAL_RATE_MULTIPLIER = 1.12
TARGET_MAX_RATIO = 1.02


@dataclass(frozen=True)
class DurationPlan:
    planner_version: str
    base_speaking_rate: float
    speaking_rate: float
    rate_multiplier: float
    estimated_duration_seconds: float
    estimated_ratio: float
    action: str

    def to_dict(self) -> dict:
        return asdict(self)


def plan_initial_speaking_rate(
    speech_text: str,
    *,
    slot_seconds: float,
    units_per_second: float,
    base_speaking_rate: float,
) -> DurationPlan:
    """Increase rate only for predicted overflow; never stretch short speech.

    ``units_per_second`` is calibrated at ``base_speaking_rate``.  The plan is
    deliberately conservative: provider speed is capped at +12%, after which
    measured WAV duration and the existing selective correction remain authority.
    """

    safe_slot = max(0.001, float(slot_seconds))
    safe_base = max(0.5, min(2.0, float(base_speaking_rate or 1.0)))
    assessment = assess_speech_budget(
        speech_text,
        slot_seconds=safe_slot,
        units_per_second=max(0.5, float(units_per_second)),
    )
    estimated = max(0.0, float(assessment.estimated_duration_seconds))
    estimated_ratio = estimated / safe_slot
    multiplier = 1.0
    action = "keep_base_rate"
    if estimated_ratio > TARGET_MAX_RATIO:
        multiplier = min(
            MAX_INITIAL_RATE_MULTIPLIER,
            max(1.0, estimated_ratio / TARGET_MAX_RATIO),
        )
        action = (
            "increase_rate_for_predicted_overflow"
            if multiplier > 1.0005
            else "keep_base_rate"
        )
    planned = min(2.0, safe_base * multiplier)
    actual_multiplier = planned / safe_base
    return DurationPlan(
        planner_version=DURATION_PLANNER_VERSION,
        base_speaking_rate=round(safe_base, 6),
        speaking_rate=round(planned, 6),
        rate_multiplier=round(actual_multiplier, 6),
        estimated_duration_seconds=round(estimated, 6),
        estimated_ratio=round(estimated_ratio, 6),
        action=action,
    )
