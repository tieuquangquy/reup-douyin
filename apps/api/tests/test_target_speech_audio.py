from __future__ import annotations

import math
import shutil
import wave
from pathlib import Path

import numpy as np
import pytest

from src.audio_pipeline.target_speech_audio import (
    materialize_compact_target_audio,
    materialize_preserved_background,
    remap_compact_transcription_units,
)
from src.audio_pipeline.target_speech_authority import TargetSpeechInterval
from src.audio_pipeline.types import TranscriptionUnit
from src.storage.local import LocalStorageBackend


def _write_tone(path: Path, *, seconds: float, amplitude: float) -> None:
    sample_rate = 16_000
    time = np.arange(int(seconds * sample_rate), dtype=np.float32) / sample_rate
    signal = amplitude * np.sin(2 * math.pi * 220 * time)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes((signal * 32767).astype("<i2").tobytes())


def _interval(start: float, end: float) -> TargetSpeechInterval:
    return TargetSpeechInterval(
        start_seconds=start,
        end_seconds=end,
        decision="ACCEPT_DIALOGUE",
        confidence=0.9,
        speech_score=0.9,
        music_score=0.2,
        singing_score=0.1,
        reasons=("test",),
    )


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required")
def test_compact_audio_remaps_asr_back_to_source_timeline(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path)
    _write_tone(storage.resolve("audio/source.wav").absolute_path, seconds=4.0, amplitude=0.2)
    result = materialize_compact_target_audio(
        storage,
        input_storage_key="audio/source.wav",
        intervals=[_interval(1.0, 2.0), _interval(3.0, 3.5)],
        source_duration_seconds=4.0,
    )
    assert result is not None
    assert storage.exists(result.storage_key)
    assert result.compact_duration_seconds == pytest.approx(1.92, abs=0.02)

    units = remap_compact_transcription_units(
        [
            TranscriptionUnit(
                text="你好",
                start_seconds=0.20,
                end_seconds=0.70,
                confidence=0.9,
                raw_payload={
                    "timestamps": [[200.0, 400.0], [400.0, 700.0]],
                    "timestamps_are_absolute": True,
                },
            ),
            TranscriptionUnit(
                text="世界",
                start_seconds=1.48,
                end_seconds=1.82,
                confidence=0.9,
            ),
        ],
        audio=result,
    )
    assert len(units) == 2
    assert units[0].start_seconds == pytest.approx(1.02, abs=0.02)
    assert units[0].end_seconds == pytest.approx(1.52, abs=0.02)
    assert units[1].start_seconds >= 3.0
    assert units[0].raw_payload["timestamps"][0][0] == pytest.approx(1_020, abs=20)


def test_cross_mapping_word_timestamps_split_text_without_losing_tokens() -> None:
    from src.audio_pipeline.target_speech_audio import (
        TargetSpeechAudioResult,
        TargetSpeechTimeMap,
    )

    audio = TargetSpeechAudioResult(
        storage_key="unused.wav",
        compact_duration_seconds=2.0,
        source_duration_seconds=6.0,
        mappings=(
            TargetSpeechTimeMap(1.0, 2.0, 0.18, 1.18),
            TargetSpeechTimeMap(4.0, 4.5, 1.42, 1.92),
        ),
        cache_hit=False,
        checksum_sha256=None,
    )
    units = remap_compact_transcription_units(
        [
            TranscriptionUnit(
                text="你好世界",
                start_seconds=0.20,
                end_seconds=1.82,
                confidence=0.9,
                raw_payload={
                    "timestamps": [
                        [200.0, 400.0],
                        [400.0, 700.0],
                        [1480.0, 1640.0],
                        [1640.0, 1820.0],
                    ]
                },
            )
        ],
        audio=audio,
    )
    assert [row.text for row in units] == ["你好", "世界"]
    assert units[0].start_seconds == pytest.approx(1.02, abs=0.02)
    assert units[1].start_seconds == pytest.approx(4.06, abs=0.02)
    assert "target_speech_cross_mapping_split" in units[0].flags


def test_cross_mapping_untimed_fallback_preserves_all_text() -> None:
    from src.audio_pipeline.target_speech_audio import (
        TargetSpeechAudioResult,
        TargetSpeechTimeMap,
    )

    audio = TargetSpeechAudioResult(
        storage_key="unused.wav",
        compact_duration_seconds=2.0,
        source_duration_seconds=6.0,
        mappings=(
            TargetSpeechTimeMap(1.0, 2.0, 0.18, 1.18),
            TargetSpeechTimeMap(4.0, 4.5, 1.42, 1.92),
        ),
        cache_hit=False,
        checksum_sha256=None,
    )
    units = remap_compact_transcription_units(
        [
            TranscriptionUnit(
                text="你好世界今天",
                start_seconds=0.20,
                end_seconds=1.82,
                confidence=0.8,
            )
        ],
        audio=audio,
    )
    assert "".join(row.text for row in units) == "你好世界今天"
    assert len(units) == 2
    assert all("needs_operator_review" in row.flags for row in units)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required")
def test_preserved_background_is_materialized_and_cached(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path)
    _write_tone(storage.resolve("audio/original.wav").absolute_path, seconds=2.0, amplitude=0.25)
    _write_tone(storage.resolve("audio/no_vocals.wav").absolute_path, seconds=2.0, amplitude=0.05)
    intervals = [_interval(0.5, 1.5)]
    key = materialize_preserved_background(
        storage,
        original_storage_key="audio/original.wav",
        demucs_background_storage_key="audio/no_vocals.wav",
        target_intervals=intervals,
    )
    assert key is not None
    assert storage.exists(key)
    assert (
        materialize_preserved_background(
            storage,
            original_storage_key="audio/original.wav",
            demucs_background_storage_key="audio/no_vocals.wav",
            target_intervals=intervals,
        )
        == key
    )
