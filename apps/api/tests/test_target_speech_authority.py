from __future__ import annotations

import math
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from src.audio_pipeline.target_speech_asr_consensus import (
    choose_target_speech_asr,
)
from src.audio_pipeline.target_speech_authority import (
    AcousticFeatures,
    AudioEventLabel,
    TargetSpeechInterval,
    TargetSpeechStatus,
    _classify,
    _strong_singing_interval,
    analyze_target_speech,
    resolve_after_separation,
)
from src.audio_pipeline.types import TranscriptionUnit, VadResult


def _features(**overrides: float) -> AcousticFeatures:
    values = {
        "rms_dbfs": -18.0,
        "spectral_flatness": 0.35,
        "voice_band_ratio": 0.72,
        "harmonicity": 0.45,
        "voiced_ratio": 0.60,
        "pitch_stability": 0.25,
        "chroma_concentration": 0.20,
        "rhythmicity": 0.15,
        "stereo_side_ratio": 0.10,
    }
    values.update(overrides)
    return AcousticFeatures(**values)


def _write_wav(path: Path, *, music: bool) -> None:
    sample_rate = 16_000
    seconds = 2.0
    time = np.arange(int(sample_rate * seconds), dtype=np.float32) / sample_rate
    if music:
        signal = 0.45 * np.sin(2 * math.pi * 220 * time)
        signal += 0.25 * np.sin(2 * math.pi * 330 * time)
    else:
        carrier = 180 + 50 * np.sin(2 * math.pi * 2.0 * time)
        signal = 0.16 * np.sin(2 * math.pi * carrier * time)
        signal += 0.035 * np.sin(2 * math.pi * 1_800 * time)
    samples = np.clip(signal, -1.0, 1.0)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes((samples * 32767).astype("<i2").tobytes())


def test_acoustic_gate_distinguishes_primary_speech_from_singing() -> None:
    speech = _classify(_features(), vad_overlap=1.0)
    singing = _classify(
        _features(
            spectral_flatness=0.08,
            harmonicity=0.92,
            voiced_ratio=0.96,
            pitch_stability=0.92,
            chroma_concentration=0.88,
            rhythmicity=0.72,
        ),
        vad_overlap=1.0,
    )
    assert speech[0] == AudioEventLabel.PRIMARY_DIALOGUE
    assert singing[0] == AudioEventLabel.SINGING_OR_RAP
    assert singing[4] > speech[4]


def test_isolated_singing_windows_cannot_veto_a_speech_interval() -> None:
    assert not _strong_singing_interval(
        {
            "speech_score": 0.78,
            "singing_score": 0.49,
            "singing_label_ratio": 0.18,
        }
    )


def test_sustained_strong_singing_still_rejects_non_dialogue_vocals() -> None:
    assert _strong_singing_interval(
        {
            "speech_score": 0.72,
            "singing_score": 0.74,
            "singing_label_ratio": 0.76,
        }
    )


def test_music_only_vad_false_never_opens_dialogue_lane() -> None:
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "music.wav"
        _write_wav(path, music=True)
        authority = analyze_target_speech(
            path,
            vad=VadResult(
                has_speech=False,
                speech_ratio=0.0,
                difficulty_flags=["silero_vad_executed"],
                metadata={"speech_intervals": []},
            ),
            duration_seconds=2.0,
        )
    assert authority.status == TargetSpeechStatus.NO_TARGET_SPEECH
    assert authority.target_intervals == ()


def test_singing_vad_is_rejected_as_non_dialogue_when_acoustically_tonal() -> None:
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "singing.wav"
        _write_wav(path, music=True)
        authority = analyze_target_speech(
            path,
            vad=VadResult(
                has_speech=True,
                speech_ratio=0.95,
                difficulty_flags=["silero_vad_executed"],
                metadata={"speech_intervals": [[0.0, 2.0]]},
            ),
            duration_seconds=2.0,
        )
    assert authority.status in {
        TargetSpeechStatus.NO_TARGET_SPEECH,
        TargetSpeechStatus.UNCERTAIN,
    }
    assert not authority.target_intervals or authority.rejected_intervals


def test_original_singing_veto_survives_separation() -> None:
    singing = TargetSpeechInterval(
        start_seconds=0.0,
        end_seconds=2.0,
        decision="REJECT_NON_DIALOGUE",
        confidence=0.9,
        speech_score=0.8,
        music_score=0.9,
        singing_score=0.9,
        reasons=("singing",),
    )
    original = type("Authority", (), {})()
    from src.audio_pipeline.target_speech_authority import (
        TargetSpeechAuthority,
    )

    original = TargetSpeechAuthority(
        status=TargetSpeechStatus.UNCERTAIN,
        provider="test",
        duration_seconds=2.0,
        target_intervals=(),
        ambiguous_intervals=(singing,),
        rejected_intervals=(singing,),
        event_windows=(),
        requires_separation=True,
        diagnostics={},
    )
    separated = TargetSpeechAuthority(
        status=TargetSpeechStatus.READY,
        provider="test",
        duration_seconds=2.0,
        target_intervals=(
            TargetSpeechInterval(
                start_seconds=0.0,
                end_seconds=2.0,
                decision="ACCEPT_DIALOGUE",
                confidence=0.95,
                speech_score=0.95,
                music_score=0.1,
                singing_score=0.1,
                reasons=("vocal_speech",),
            ),
        ),
        ambiguous_intervals=(),
        rejected_intervals=(),
        event_windows=(),
        requires_separation=False,
        diagnostics={},
    )
    resolved = resolve_after_separation(original, separated)
    assert resolved.target_intervals == ()
    assert resolved.rejected_intervals


def test_asr_consensus_blocks_disagreement_and_keeps_selected_units() -> None:
    original = [
        TranscriptionUnit(
            text="你好",
            start_seconds=0.0,
            end_seconds=1.0,
            confidence=0.85,
        )
    ]
    separated = [
        TranscriptionUnit(
            text="完全不同",
            start_seconds=0.0,
            end_seconds=1.0,
            confidence=0.90,
        )
    ]
    result = choose_target_speech_asr(
        original_units=original,
        separated_units=separated,
        target_seconds=1.0,
        prefer_separated=True,
    )
    assert result.units
    assert "asr_stem_disagreement" in result.diagnostics["flags"]
    assert "needs_operator_review" in result.units[0].flags
