from uuid import uuid4

from src.tts_pipeline.services.director import build_local_director_plan, build_voice_bible
from src.tts_pipeline.services.emotion_planner import plan_emotions
from src.tts_pipeline.types import TranslationInputSegment, VoiceConfig


def _segment(source_id, index, text, start, end):
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
        speaker_label="narrator",
    )


def test_local_director_builds_explicit_continuity_state_and_tags():
    source_id = uuid4()
    rows = [
        _segment(source_id, 0, "Tôi nghĩ đây là một bài học quan trọng.", 0, 2500),
        _segment(source_id, 1, "Nhưng điều đáng sợ nhất không phải là AI!", 2700, 5200),
    ]
    bible = build_voice_bible(
        voice_config=VoiceConfig(voice_id="instruct:vi_female_north"),
        runtime_authority={"provider": "google", "model_id": "gemini-tts"},
    )
    plan = build_local_director_plan(
        rows,
        source_video_id=source_id,
        voice_bible=bible,
    )
    assert plan.prosody_segments[0].emotion == "reflective"
    assert plan.prosody_segments[1].emotion == "serious"
    assert plan.prosody_segments[1].transition == "contrast"
    assert "emphasis" in plan.prosody_segments[1].audio_tags
    assert (
        plan.prosody_segments[1].previous_state
        == plan.prosody_segments[0].target_state
    )
    assert len(plan.to_dict()["plan_sha256"]) == 64


def test_audio_event_evidence_increases_director_confidence():
    source_id = uuid4()
    row = _segment(source_id, 0, "Nội dung bình thường.", 0, 2000)
    bible = build_voice_bible(
        voice_config=VoiceConfig(),
        runtime_authority={"provider": "edge"},
    )
    base = build_local_director_plan([row], source_video_id=source_id, voice_bible=bible)
    informed = build_local_director_plan(
        [row],
        source_video_id=source_id,
        voice_bible=bible,
        source_context={
            "audio_event_timeline": {
                "windows": [
                    {
                        "start_seconds": 0,
                        "end_seconds": 2,
                        "label": "REACTION_OR_SFX",
                        "features": {"rms_dbfs": -12.0},
                    }
                ]
            }
        },
    )
    assert informed.prosody_segments[0].emotion == "excited"
    assert informed.prosody_segments[0].confidence > base.prosody_segments[0].confidence


def test_local_director_builds_clause_level_emotion_spans():
    source_id = uuid4()
    row = _segment(
        source_id,
        0,
        "Mình đã thành công! Nhưng hãy cẩn thận. Bạn hiểu chứ?",
        0,
        4000,
    )
    plan = build_local_director_plan(
        [row],
        source_video_id=source_id,
        voice_bible=build_voice_bible(
            voice_config=VoiceConfig(),
            runtime_authority={"provider": "google", "model_id": "classic"},
        ),
    )
    spans = plan.prosody_segments[0].spans
    assert len(spans) == 3
    assert spans[0].emotion == "positive"
    assert spans[-1].emotion == "curious"


def test_provider_scoped_gate_keeps_non_gemini_director_neutral():
    source_id = uuid4()
    row = _segment(source_id, 0, "Nhớ theo dõi và chia sẻ nhé!", 0, 2000)
    plan = build_local_director_plan(
        [row],
        source_video_id=source_id,
        voice_bible=build_voice_bible(
            voice_config=VoiceConfig(), runtime_authority={"provider": "google"}
        ),
        emotion_decisions=plan_emotions([row]),
        emotion_enabled=False,
    )
    assert plan.prosody_segments[0].emotion == "neutral"
    assert all(span.emotion == "neutral" for span in plan.prosody_segments[0].spans)


def test_gemini_planner_decision_is_used_for_segment_and_spans():
    source_id = uuid4()
    row = _segment(source_id, 0, "Nhớ theo dõi và chia sẻ nhé!", 0, 2000)
    plan = build_local_director_plan(
        [row],
        source_video_id=source_id,
        voice_bible=build_voice_bible(
            voice_config=VoiceConfig(), runtime_authority={"provider": "google_gemini"}
        ),
        emotion_decisions=plan_emotions([row]),
        emotion_enabled=True,
    )
    assert plan.prosody_segments[0].emotion == "positive"
    assert plan.prosody_segments[0].source == "text_conditioned_emotion_planner"
