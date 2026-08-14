import wave
from io import BytesIO
from uuid import uuid4

import numpy as np

from src.tts_pipeline.services.whole_video_alignment import split_whole_video_wav
from src.tts_pipeline.types import TranslationInputSegment


def _wav_with_pause() -> bytes:
    sample_rate = 48_000
    first = np.full(sample_rate, 5_000, dtype="<i2")
    pause = np.zeros(int(sample_rate * 0.25), dtype="<i2")
    second = np.full(sample_rate, -5_000, dtype="<i2")
    pcm = np.concatenate((first, pause, second))
    output = BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return output.getvalue()


def _segment(
    index: int,
    start_ms: int,
    end_ms: int,
    text: str | None = None,
) -> TranslationInputSegment:
    return TranslationInputSegment(
        translation_segment_id=uuid4(),
        transcript_segment_id=uuid4(),
        source_video_id=uuid4(),
        segment_index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        translated_text=text or f"Câu {index}",
        duration_budget_ms=end_ms - start_ms,
        translation_version=1,
        translation_preset="literal_safe",
    )


def test_silence_alignment_finds_natural_sentence_boundary() -> None:
    slices = split_whole_video_wav(
        _wav_with_pause(),
        [_segment(0, 0, 1_000), _segment(1, 1_250, 2_250)],
        search_window_ms=400,
    )
    assert len(slices) == 2
    assert 1.0 <= slices[0].duration_seconds <= 1.25
    assert 1.0 <= slices[1].duration_seconds <= 1.25
    assert slices[0].boundary_confidence > 0.5


def test_single_segment_preserves_entire_wav() -> None:
    slices = split_whole_video_wav(
        _wav_with_pause(),
        [_segment(0, 0, 2_250)],
    )
    assert len(slices) == 1
    assert abs(slices[0].duration_seconds - 2.25) < 0.001
    assert slices[0].boundary_confidence == 1.0


def test_global_sequence_alignment_rejects_short_intra_word_valleys() -> None:
    sample_rate = 48_000

    def tone(seconds: float, value: int) -> np.ndarray:
        return np.full(int(sample_rate * seconds), value, dtype="<i2")

    stable_pause = np.zeros(int(sample_rate * 0.25), dtype="<i2")
    micro_pause = np.zeros(int(sample_rate * 0.025), dtype="<i2")
    pcm = np.concatenate(
        (
            tone(0.9, 4_000),
            stable_pause,
            tone(0.9, -4_000),
            micro_pause,
            tone(0.9, -4_000),
            stable_pause,
            tone(0.9, 5_000),
            stable_pause,
            tone(0.9, -5_000),
        )
    )
    output = BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())

    slices = split_whole_video_wav(
        output.getvalue(),
        [
            _segment(0, 0, 1_250, "một câu"),
            _segment(1, 1_250, 2_500, "một câu dài hơn nhiều"),
            _segment(2, 2_500, 3_750, "một câu"),
            _segment(3, 3_750, 5_000, "một câu"),
        ],
    )

    assert len(slices) == 4
    cuts_seconds = [row.end_frame / sample_rate for row in slices[:-1]]
    assert 0.9 <= cuts_seconds[0] <= 1.15
    assert 2.8 <= cuts_seconds[1] <= 3.1
    assert 3.9 <= cuts_seconds[2] <= 4.3
    assert min(row.boundary_confidence for row in slices) > 0.75
