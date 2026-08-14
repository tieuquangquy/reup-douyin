from __future__ import annotations

from src.audio_pipeline.dialogue_validation import (
    DialogueDecision,
    high_recall_candidate_authority,
    validate_dialogue_units,
)
from src.audio_pipeline.target_speech_authority import (
    AcousticFeatures,
    AudioEventLabel,
    AudioEventWindow,
    TargetSpeechAuthority,
    TargetSpeechInterval,
    TargetSpeechStatus,
)
from src.audio_pipeline.types import TranscriptionUnit, VadResult


def _features() -> AcousticFeatures:
    return AcousticFeatures(
        rms_dbfs=-18.0,
        spectral_flatness=0.25,
        voice_band_ratio=0.7,
        harmonicity=0.5,
        voiced_ratio=0.7,
        pitch_stability=0.3,
        chroma_concentration=0.3,
        rhythmicity=0.2,
        stereo_side_ratio=0.1,
    )


def _window(
    start: float,
    end: float,
    *,
    speech: float,
    music: float,
    singing: float = 0.2,
) -> AudioEventWindow:
    return AudioEventWindow(
        start_seconds=start,
        end_seconds=end,
        label=(
            AudioEventLabel.SPEECH_MUSIC_AMBIGUOUS
            if music >= 0.6
            else AudioEventLabel.PRIMARY_DIALOGUE
        ),
        confidence=max(speech, music, singing),
        vad_overlap=1.0,
        speech_score=speech,
        music_score=music,
        singing_score=singing,
        features=_features(),
    )


def _authority(*windows: AudioEventWindow) -> TargetSpeechAuthority:
    return TargetSpeechAuthority(
        status=TargetSpeechStatus.READY,
        provider="test",
        duration_seconds=12.0,
        target_intervals=(
            TargetSpeechInterval(
                0.0,
                12.0,
                "ACCEPT_DIALOGUE",
                0.8,
                0.8,
                0.4,
                0.2,
                ("test",),
            ),
        ),
        ambiguous_intervals=(),
        rejected_intervals=(),
        event_windows=tuple(windows),
        requires_separation=False,
        diagnostics={},
    )


def test_isolated_single_character_in_music_is_not_persisted() -> None:
    authority = _authority(
        _window(0.0, 1.2, speech=0.9, music=0.1),
        _window(9.0, 9.5, speech=0.82, music=0.94, singing=0.4),
    )
    result = validate_dialogue_units(
        [
            TranscriptionUnit("今天化妆", 0.1, 1.0, 0.9),
            TranscriptionUnit("吧", 9.10, 9.34, 0.8),
        ],
        authority=authority,
    )
    assert [row.text for row in result.units] == ["今天化妆"]
    assert [row.text for row in result.dropped_units] == ["吧"]
    assert result.assessments[-1].decision == DialogueDecision.DROP_NON_DIALOGUE
    assert result.diagnostics["isolated_orphan_drop_count"] == 1


def test_real_short_reply_with_clean_speech_is_preserved() -> None:
    authority = _authority(
        _window(4.0, 4.5, speech=0.94, music=0.12),
    )
    result = validate_dialogue_units(
        [TranscriptionUnit("好", 4.10, 4.35, 0.92)],
        authority=authority,
    )
    assert [row.text for row in result.units] == ["好"]
    assert result.dropped_units == ()
    assert result.assessments[0].decision == DialogueDecision.KEEP


def test_selective_verifier_compares_only_overlapping_word_timestamps() -> None:
    authority = _authority(
        _window(0.0, 4.5, speech=0.8, music=0.55),
    )
    primary = TranscriptionUnit(
        "甲乙丙丁",
        0.0,
        4.0,
        0.8,
        raw_payload={
            "timestamps": [
                [0.0, 900.0],
                [1000.0, 1900.0],
                [2000.0, 2900.0],
                [3000.0, 3900.0],
            ],
            "timestamps_are_absolute": True,
        },
    )
    verifier = TranscriptionUnit("丙", 2.0, 2.9, 0.9)
    result = validate_dialogue_units(
        [primary],
        authority=authority,
        secondary_units=[verifier],
    )
    assert result.assessments[0].secondary_agreement == 1.0
    assert result.assessments[0].decision == DialogueDecision.KEEP


def test_high_recall_candidates_include_vad_span_rejected_by_event_gate() -> None:
    rejected = TargetSpeechInterval(
        2.0,
        5.0,
        "REJECT_NON_DIALOGUE",
        0.9,
        0.7,
        0.9,
        0.85,
        ("singing",),
    )
    authority = TargetSpeechAuthority(
        status=TargetSpeechStatus.NO_TARGET_SPEECH,
        provider="test",
        duration_seconds=8.0,
        target_intervals=(),
        ambiguous_intervals=(),
        rejected_intervals=(rejected,),
        event_windows=(),
        requires_separation=False,
        diagnostics={},
    )
    candidates = high_recall_candidate_authority(
        authority,
        vad=VadResult(
            has_speech=True,
            speech_ratio=0.4,
            metadata={"speech_intervals": [[2.0, 5.0]]},
        ),
    )
    assert len(candidates.target_intervals) == 1
    assert candidates.target_intervals[0].decision == "ASR_CANDIDATE_HIGH_RECALL"

    validation = validate_dialogue_units(
        [TranscriptionUnit("虚假歌词", 2.1, 4.9, 0.9)],
        authority=authority,
    )
    assert validation.units == ()
    assert validation.dropped_units
