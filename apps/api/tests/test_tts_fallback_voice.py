"""Fallback must not pass VieNeu voice names to edge-tts."""

from __future__ import annotations

import unittest
import wave
from io import BytesIO

from src.tts_pipeline.edge_tts_provider import DEFAULT_EDGE_TTS_VOICE, EdgeTtsProvider, resolve_edge_voice_id
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.provider_factory import FallbackTtsProvider
from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput, VoiceConfig


def _tiny_wav(duration_seconds: float = 0.4, sample_rate: int = 16000) -> bytes:
    frames = max(1, int(duration_seconds * sample_rate))
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


class _FailPrimary:
    provider_name = "vieneu"

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        raise TtsPipelineError(TtsPipelineErrorCode.TTS_PROVIDER_FAILED, "primary boom")


class FallbackVoiceAuthorityTests(unittest.TestCase):
    def test_resolve_edge_voice_remaps_vieneu_display_name(self) -> None:
        self.assertEqual(resolve_edge_voice_id("Ngọc Linh"), DEFAULT_EDGE_TTS_VOICE)
        self.assertEqual(resolve_edge_voice_id("Phạm Tuyên"), DEFAULT_EDGE_TTS_VOICE)
        self.assertEqual(resolve_edge_voice_id("vi-VN-NamMinhNeural"), "vi-VN-NamMinhNeural")

    def test_fallback_applies_fallback_voice_id_not_primary_voice(self) -> None:
        seen: dict[str, str] = {}

        def _capture(*, text: str, voice_id: str, speaking_rate: float):
            seen["voice_id"] = voice_id
            return _tiny_wav(0.4), 0.4

        wrapper = FallbackTtsProvider(
            _FailPrimary(),
            EdgeTtsProvider(synthesize_audio=_capture),
            fallback_voice_id="vi-VN-NamMinhNeural",
        )
        result = wrapper.synthesize(
            TtsProviderInput(
                text="Xin chào",
                language_code="vi",
                voice_config=VoiceConfig(voice_id="Ngọc Linh"),
            )
        )
        self.assertEqual(seen["voice_id"], "vi-VN-NamMinhNeural")
        self.assertIn("tts_used_fallback_provider", result.warnings)

    def test_fallback_without_explicit_voice_still_remaps_vieneu_name(self) -> None:
        seen: dict[str, str] = {}

        def _capture(*, text: str, voice_id: str, speaking_rate: float):
            seen["voice_id"] = voice_id
            return _tiny_wav(0.4), 0.4

        wrapper = FallbackTtsProvider(
            _FailPrimary(),
            EdgeTtsProvider(synthesize_audio=_capture),
        )
        wrapper.synthesize(
            TtsProviderInput(
                text="Xin chào",
                language_code="vi",
                voice_config=VoiceConfig(voice_id="Ngọc Linh"),
            )
        )
        self.assertEqual(seen["voice_id"], DEFAULT_EDGE_TTS_VOICE)


if __name__ == "__main__":
    unittest.main()
