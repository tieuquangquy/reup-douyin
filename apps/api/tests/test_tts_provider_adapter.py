from uuid import uuid4

from src.tts_pipeline.provider_capabilities import resolve_provider_capabilities
from src.tts_pipeline.services.provider_adapter import (
    PROVIDER_LOWERING_VERSION,
    compile_provider_instruction,
)
from src.tts_pipeline.types import ProsodySegment, ProsodySpan, ProsodyState, VoiceBible


def _prosody():
    return ProsodySegment(
        translation_segment_id=uuid4(),
        segment_index=0,
        start_ms=0,
        end_ms=2000,
        emotion="serious",
        pace=0.9,
        pause_after_ms=400,
        emphasis=("quan trọng",),
        audio_tags=("serious", "slow", "emphasis", "long pause"),
        previous_state=ProsodyState(current_emotion="engaged", energy=0.7),
    )


def test_gemini_lowering_uses_tags_direction_and_state():
    compiled = compile_provider_instruction(
        "Điều này rất quan trọng.",
        voice_bible=VoiceBible(persona="narrator"),
        prosody=_prosody(),
        capabilities=resolve_provider_capabilities(
            "google", model_id="gemini-3.1-flash-tts"
        ),
        sample_context="A calm opening sample.",
    )
    assert compiled.rendered_text.startswith("[serious, slow")
    assert compiled.voice_direction
    assert "pauses: before 0ms, after 400ms" in compiled.voice_direction
    assert "emphasize: quan trọng" in compiled.voice_direction
    assert compiled.sample_context == "A calm opening sample."
    assert compiled.prosody_state["current_emotion"] == "engaged"
    assert PROVIDER_LOWERING_VERSION == "tts-provider-lowering-v2"


def test_basic_provider_never_receives_raw_tags():
    compiled = compile_provider_instruction(
        "Điều này rất quan trọng.",
        voice_bible=VoiceBible(),
        prosody=_prosody(),
        capabilities=resolve_provider_capabilities("basic"),
    )
    assert compiled.rendered_text == "Điều này rất quan trọng."
    assert not compiled.audio_tags
    assert "audio_tags_not_supported" in compiled.degraded_features


def test_ssml_provider_receives_escaped_text_and_controls():
    compiled = compile_provider_instruction(
        "A < B là quan trọng.",
        voice_bible=VoiceBible(),
        prosody=_prosody(),
        capabilities=resolve_provider_capabilities("azure"),
    )
    assert compiled.ssml_text is not None
    assert "A &lt; B" in compiled.ssml_text
    assert '<break time="400ms"/>' in compiled.ssml_text


def test_ssml_provider_lowers_clause_level_emotion_spans_inline():
    prosody = _prosody()
    prosody = ProsodySegment(
        **{
            **prosody.__dict__,
            "spans": (
                ProsodySpan(text="Tin tốt!", emotion="excited", pace=1.08, pause_after_ms=180),
                ProsodySpan(text="Nhưng hãy cẩn thận.", emotion="serious", pace=0.94, pause_after_ms=320),
            ),
        }
    )
    compiled = compile_provider_instruction(
        "Tin tốt! Nhưng hãy cẩn thận.",
        voice_bible=VoiceBible(),
        prosody=prosody,
        capabilities=resolve_provider_capabilities("google", model_id="classic"),
        base_speaking_rate=1.05,
    )
    assert compiled.ssml_text.count("<prosody ") == 2
    assert 'pitch="+1st"' in compiled.ssml_text
    assert 'pitch="-1st"' in compiled.ssml_text
    assert compiled.ssml_text.count('<break time="') == 2
