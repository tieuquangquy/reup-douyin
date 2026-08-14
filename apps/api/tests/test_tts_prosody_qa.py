from dataclasses import replace
from uuid import uuid4

from src.tts_pipeline.services.prosody_qa import assess_prosody_continuity
from src.tts_pipeline.types import ProsodySegment, ProsodyState


def _segment(index: int, previous: ProsodyState, target: ProsodyState):
    return ProsodySegment(
        translation_segment_id=uuid4(),
        segment_index=index,
        start_ms=index * 1000,
        end_ms=(index + 1) * 1000,
        previous_state=previous,
        target_state=target,
    )


def test_prosody_continuity_passes_for_planned_state_handoff():
    initial = ProsodyState(energy=0.5, pace=1.0)
    next_state = ProsodyState(energy=0.7, pace=1.08)
    report = assess_prosody_continuity(
        [_segment(0, initial, next_state), _segment(1, next_state, next_state)]
    )
    assert report["passed"]
    assert report["issue_count"] == 0


def test_prosody_continuity_flags_large_reinitialized_jump():
    initial = ProsodyState(energy=0.5, pace=1.0)
    target = ProsodyState(energy=0.9, pace=1.15)
    second = _segment(1, target, target)
    second = replace(
        second,
        previous_state=ProsodyState(energy=0.1, pace=0.7),
    )
    report = assess_prosody_continuity([_segment(0, initial, target), second])
    assert not report["passed"]
    assert report["issues"][0]["reason"] == "prosody_state_jump"
