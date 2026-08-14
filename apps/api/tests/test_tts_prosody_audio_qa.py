import io
import math
import struct
import wave
from uuid import uuid4

from src.tts_pipeline.services.prosody_audio_qa import analyze_prosody_audio
from src.tts_pipeline.types import ProsodySegment


def _wav() -> bytes:
    sample_rate = 16000
    samples = [
        int(5000 * math.sin(2 * math.pi * 220 * index / sample_rate))
        for index in range(sample_rate // 4)
    ]
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    return output.getvalue()


def test_prosody_audio_qa_requires_provider_execution_evidence():
    prosody = ProsodySegment(
        translation_segment_id=uuid4(),
        segment_index=0,
        start_ms=0,
        end_ms=250,
        emotion="excited",
    )
    report = analyze_prosody_audio(
        _wav(),
        prosody=prosody,
        provider_metadata={
            "execution_contract": {
                "requested_features": ["emotion"],
                "applied_features": ["emotion", "ssml"],
            }
        },
    )
    assert report["execution_verified"]
    assert report["rms_dbfs"] is not None
    assert report["zero_crossing_rate_per_second"] > 0


def test_prosody_audio_qa_flags_metadata_only_emotion():
    prosody = ProsodySegment(
        translation_segment_id=uuid4(),
        segment_index=0,
        start_ms=0,
        end_ms=250,
        emotion="serious",
    )
    report = analyze_prosody_audio(
        _wav(),
        prosody=prosody,
        provider_metadata={
            "execution_contract": {
                "requested_features": ["emotion"],
                "applied_features": [],
            }
        },
    )
    assert not report["execution_verified"]
    assert "prosody_emotion_not_applied" in report["warnings"]
