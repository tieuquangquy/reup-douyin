from uuid import uuid4

from src.tts_pipeline.provider_capabilities import resolve_provider_capabilities
from src.tts_pipeline.types import (
    PerformanceChunk,
    ProsodySegment,
    ProsodyState,
    VoiceBible,
)


def test_voice_bible_and_prosody_contracts_are_serializable():
    source_id = uuid4()
    segment_id = uuid4()
    state = ProsodyState(current_emotion="engaged", energy=0.72)
    prosody = ProsodySegment(
        translation_segment_id=segment_id,
        segment_index=2,
        start_ms=1000,
        end_ms=3000,
        emotion="curious",
        intensity=0.65,
        audio_tags=("curious",),
        previous_state=state,
        target_state=ProsodyState(current_emotion="curious", energy=0.65),
    )
    bible = VoiceBible(
        voice_id="voice-a",
        provider="gemini",
        model_id="gemini-tts",
        accent="Hanoi Vietnamese",
        director_rules=("keep natural conversational flow",),
    )
    chunk = PerformanceChunk(
        chunk_id="chunk-1",
        source_video_id=source_id,
        start_ms=1000,
        end_ms=3000,
        translated_text="Xin chào",
        member_translation_segment_ids=(segment_id,),
        member_segment_indices=(2,),
        prosody_segments=(prosody,),
        previous_state=state,
        target_state=prosody.target_state,
    )
    assert bible.to_dict()["director_rules"] == ["keep natural conversational flow"]
    assert chunk.to_dict()["prosody_segments"][0]["audio_tags"] == ["curious"]


def test_provider_capability_resolution_is_provider_specific_and_overrideable():
    gemini = resolve_provider_capabilities("google", model_id="gemini-3.1-flash-tts")
    assert gemini.supports_audio_tags
    assert gemini.supports_sample_context

    classic = resolve_provider_capabilities("google", model_id="en-US-Neural2-A")
    assert not classic.supports_audio_tags
    assert classic.supports_ssml

    local = resolve_provider_capabilities("edge", model_id="vi-VN-HoaiMyNeural")
    assert not local.expressive

    custom = resolve_provider_capabilities(
        "http_custom",
        options={"http_connector": {"capabilities": {"supports_audio_tags": True}}},
    )
    assert custom.supports_audio_tags
