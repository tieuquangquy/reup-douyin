from uuid import uuid4

from src.tts_pipeline.services.director import build_local_director_plan, build_voice_bible
from src.tts_pipeline.services.performance_chunker import build_performance_chunks
from src.tts_pipeline.types import TranslationInputSegment, VoiceConfig


def _row(source_id, index, text, start, end, speaker):
    return TranslationInputSegment(
        translation_segment_id=uuid4(),
        transcript_segment_id=uuid4(),
        source_video_id=source_id,
        segment_index=index,
        start_ms=start,
        end_ms=end,
        translated_text=text,
        duration_budget_ms=end - start,
        translation_version=1,
        translation_preset="contextual",
        speaker_label=speaker,
    )


def test_chunker_preserves_members_and_cuts_on_speaker_and_semantic_boundaries():
    source_id = uuid4()
    rows = [
        _row(source_id, 0, "Tôi nghĩ chúng ta nên bắt đầu.", 0, 1800, "a"),
        _row(source_id, 1, "Nhưng điều đáng sợ nhất là sự chủ quan.", 1900, 3800, "a"),
        _row(source_id, 2, "Vì vậy chúng ta phải học.", 3900, 5600, "b"),
    ]
    bible = build_voice_bible(voice_config=VoiceConfig(), runtime_authority={})
    plan = build_local_director_plan(rows, source_video_id=source_id, voice_bible=bible)
    chunks, report = build_performance_chunks(rows, director_plan=plan)
    assert len(chunks) == 3
    assert sum(len(chunk.member_segment_indices) for chunk in chunks) == 3
    assert "speaker_boundary" in chunks[1].boundary_reasons
    assert report["chunk_count"] == 3
