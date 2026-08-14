from __future__ import annotations

import wave
from io import BytesIO
from uuid import uuid4

import numpy as np

from src.tts_pipeline.services.narration_assembler import trim_wav_silence
from src.tts_pipeline.services.temporal_dialogue import (
    build_temporal_dialogue_timeline,
    merge_vietnamese_text,
)
from src.tts_pipeline.services.tts_service import _rank_tts_candidates
from src.tts_pipeline.types import TranslationInputSegment


def _segment(
    index: int,
    start_ms: int,
    end_ms: int,
    text: str,
    *,
    source: str = "",
    speaker: str | None = "speaker_0",
    candidates: tuple[str, ...] = (),
) -> TranslationInputSegment:
    translation_id = uuid4()
    transcript_id = uuid4()
    return TranslationInputSegment(
        translation_segment_id=translation_id,
        transcript_segment_id=transcript_id,
        source_video_id=uuid4(),
        segment_index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        translated_text=text,
        duration_budget_ms=end_ms - start_ms,
        translation_version=1,
        translation_preset="literal_safe",
        source_text=source,
        speaker_label=speaker,
        member_translation_segment_ids=(translation_id,),
        member_transcript_segment_ids=(transcript_id,),
        member_segment_indices=(index,),
        candidate_texts=candidates,
        original_start_ms=start_ms,
        original_end_ms=end_ms,
    )


def test_repairs_demonstrated_micro_boundary_and_keeps_both_meanings() -> None:
    left = _segment(7, 5_000, 6_600, "Kẻ phần", source="画卧")
    right = _segment(8, 6_700, 7_640, "bọng mắt", source="蚕")

    groups, report = build_temporal_dialogue_timeline(
        [left, right], timeline_duration_ms=8_000, units_per_second=4.5
    )

    assert len(groups) == 1
    assert groups[0].translated_text == "Kẻ phần bọng mắt"
    assert groups[0].member_segment_indices == (7, 8)
    assert report["merged_segment_count"] == 1


def test_does_not_merge_micro_segments_from_different_known_speakers() -> None:
    left = _segment(0, 0, 900, "Xin chào", speaker="speaker_0")
    right = _segment(1, 1_000, 1_800, "Chào bạn", speaker="speaker_1")

    groups, _ = build_temporal_dialogue_timeline(
        [left, right], timeline_duration_ms=2_000, units_per_second=4.5
    )

    assert len(groups) == 2


def test_borrows_only_bounded_following_pause() -> None:
    row = _segment(0, 0, 2_000, "Đây là câu vừa đủ để đọc")
    groups, report = build_temporal_dialogue_timeline(
        [row], timeline_duration_ms=3_000, units_per_second=4.5
    )

    assert groups[0].end_ms == 2_320
    assert "borrow_following_pause" in groups[0].repair_actions
    assert any(item["decision"] == "BORROW_PAUSE" for item in report["decisions"])


def test_merge_removes_repeated_boundary_words() -> None:
    assert merge_vietnamese_text("Rốt cuộc anh muốn", "anh muốn làm gì") == "Rốt cuộc anh muốn làm gì"


def test_candidate_ranking_rejects_lost_protected_number_and_prefers_fit() -> None:
    row = _segment(
        0,
        0,
        1_600,
        "Dùng 15 ml dầu đậu phộng nhé",
        source="花生油15ml",
        candidates=("Dùng dầu nhé", "Dùng 15 ml dầu"),
    )

    ranked = _rank_tts_candidates(row, 1.6, 4.5)

    assert "Dùng dầu nhé" not in ranked
    assert ranked[0] == "Dùng 15 ml dầu"


def test_trim_wav_silence_removes_only_outer_padding() -> None:
    sample_rate = 48_000
    lead = np.zeros(int(sample_rate * 0.2), dtype=np.int16)
    voice = np.full(int(sample_rate * 0.4), 2_000, dtype=np.int16)
    tail = np.zeros(int(sample_rate * 0.2), dtype=np.int16)
    stream = BytesIO()
    with wave.open(stream, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(np.concatenate([lead, voice, tail]).astype("<i2").tobytes())

    _, duration, metadata = trim_wav_silence(stream.getvalue())

    assert metadata["trimmed"] is True
    assert 0.48 <= duration <= 0.50
    assert metadata["trimmed_ms"] >= 300
