"""Deterministic QA for planned prosody continuity.

This is deliberately provider/audio independent.  It catches a broken state
handoff before a paid call; waveform and duration QA remain the authority for
the generated audio itself.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.tts_pipeline.types import ProsodySegment


PROSODY_QA_VERSION = "prosody-continuity-qa-v1"
MAX_PACE_STATE_DELTA = 0.35
MAX_ENERGY_STATE_DELTA = 0.55


def assess_prosody_continuity(
    segments: Sequence[ProsodySegment],
    *,
    max_pace_delta: float = MAX_PACE_STATE_DELTA,
    max_energy_delta: float = MAX_ENERGY_STATE_DELTA,
) -> dict:
    ordered = sorted(segments, key=lambda row: (row.start_ms, row.segment_index))
    issues: list[dict] = []
    for previous, current in zip(ordered, ordered[1:]):
        # The next segment must start from the state the previous segment ended
        # with. This detects accidental reinitialization in future directors.
        prev_target = previous.target_state
        current_start = current.previous_state
        pace_delta = abs(float(current_start.pace) - float(prev_target.pace))
        energy_delta = abs(float(current_start.energy) - float(prev_target.energy))
        if pace_delta > max_pace_delta or energy_delta > max_energy_delta:
            issues.append(
                {
                    "segment_index": current.segment_index,
                    "previous_segment_index": previous.segment_index,
                    "pace_delta": round(pace_delta, 6),
                    "energy_delta": round(energy_delta, 6),
                    "reason": "prosody_state_jump",
                }
            )
    return {
        "schema_version": PROSODY_QA_VERSION,
        "segment_count": len(ordered),
        "passed": not issues,
        "issue_count": len(issues),
        "issues": issues,
    }
