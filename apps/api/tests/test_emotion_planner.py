from types import SimpleNamespace

from src.tts_pipeline.services.emotion_planner import (
    EmotionDecision,
    enforce_emotion_policy,
    plan_emotions,
    planner_enabled,
)


def _segment(index: int, text: str):
    return SimpleNamespace(segment_index=index, start_ms=index * 1000, end_ms=(index + 1) * 1000, translated_text=text)


def test_planner_is_scoped_to_enabled_gemini_capabilities():
    assert planner_enabled(
        provider="google_gemini",
        options={"emotion_planner": {"enabled": True}},
        capabilities={"supports_audio_tags": True, "supports_voice_direction": True},
    )
    assert not planner_enabled(
        provider="google",
        options={"emotion_planner": {"enabled": True}},
        capabilities={"supports_audio_tags": True, "supports_voice_direction": True},
    )
    assert not planner_enabled(
        provider="google_gemini",
        options={"emotion_planner": {"enabled": False}},
        capabilities={"supports_audio_tags": True, "supports_voice_direction": True},
    )


def test_exclamation_alone_does_not_create_excited_emotion():
    decision = plan_emotions([_segment(0, "Món ăn đã hoàn thành rồi!")])[0]
    assert decision.emotion == "neutral"
    assert "punctuation_only" in decision.rejected_signals


def test_instruction_is_neutral_even_when_positive_word_is_present():
    decision = plan_emotions([_segment(0, "Cho món ngon vào chảo và đảo đều!")])[0]
    assert decision.intent == "instruction"
    assert decision.emotion == "neutral"
    assert "instruction_neutrality_guard" in decision.rejected_signals


def test_cta_becomes_positive_not_excited():
    decision = plan_emotions([_segment(0, "Nhớ theo dõi và chia sẻ nhé!")])[0]
    assert decision.intent == "cta"
    assert decision.emotion == "positive"
    assert decision.confidence >= 0.70


def test_warning_and_reveal_have_distinct_emotions():
    decisions = plan_emotions(
        [
            _segment(0, "Đây là cảnh báo rất nghiêm trọng."),
            _segment(1, "Thật bất ngờ, kết quả quá tuyệt vời!"),
        ]
    )
    assert decisions[0].emotion == "serious"
    assert decisions[1].emotion == "excited"


def test_intensity_transition_is_bounded():
    decisions = plan_emotions(
        [
            _segment(0, "Mọi thứ đã ổn."),
            _segment(1, "Thật bất ngờ, không thể tin được!"),
        ],
        max_intensity_delta=0.20,
    )
    assert abs(decisions[1].intensity - decisions[0].intensity) <= 0.20


def test_policy_enforces_allow_excited_option():
    rows = [_segment(0, "Thật bất ngờ, không thể tin được!")]
    planned = plan_emotions(rows)
    final, report = enforce_emotion_policy(planned, rows, allow_excited=False)
    assert planned[0].emotion == "excited"
    assert final[0].emotion == "neutral"
    assert final[0].policy_action == "downgraded"
    assert report.downgraded_count == 1


def test_policy_caps_strong_emotion_duration():
    rows = [
        _segment(0, "Đây là cảnh báo rất nghiêm trọng."),
        _segment(1, "Đây là cảnh báo nguy hiểm."),
    ]
    planned = plan_emotions(rows)
    final, report = enforce_emotion_policy(
        planned,
        rows,
        max_strong_emotion_ratio=0.20,
    )
    assert report.strong_emotion_ratio > 0.20
    assert all(decision.emotion == "neutral" for decision in final.values())
