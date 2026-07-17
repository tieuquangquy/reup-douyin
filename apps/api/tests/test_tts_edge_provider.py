"""Edge TTS provider + factory selection."""

from __future__ import annotations

import unittest
import wave
from io import BytesIO

from src.tts_pipeline.edge_tts_provider import EdgeTtsProvider, DEFAULT_EDGE_TTS_VOICE
from src.tts_pipeline.provider_factory import build_default_tts_provider
from src.tts_pipeline.providers import PlaceholderToneTtsProvider
from src.tts_pipeline.services.timing_fit import classify_timing_fit
from src.tts_pipeline.types import TtsProviderInput, VoiceConfig


def _tiny_wav(duration_seconds: float = 0.5, sample_rate: int = 16000) -> bytes:
    frames = max(1, int(duration_seconds * sample_rate))
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


class EdgeTtsProviderTests(unittest.TestCase):
    def test_edge_provider_returns_wav_without_placeholder_flag(self) -> None:
        provider = EdgeTtsProvider(
            synthesize_audio=lambda **_: (_tiny_wav(0.8), 0.8),
        )
        result = provider.synthesize(
            TtsProviderInput(
                text="Xin chào mọi người",
                language_code="vi",
                voice_config=VoiceConfig(voice_id=DEFAULT_EDGE_TTS_VOICE),
                target_duration_seconds=1.0,
            )
        )
        self.assertTrue(result.audio_bytes.startswith(b"RIFF"))
        self.assertEqual(result.mime_type, "audio/wav")
        self.assertEqual(result.provider_metadata["provider"], "edge_tts")
        self.assertNotIn("provider_placeholder", result.warnings)
        self.assertAlmostEqual(result.duration_seconds, 0.8, places=2)
        status, _ = classify_timing_fit(result.duration_seconds, 1.0)
        self.assertEqual(status.value, "fits_well")

    def test_edge_provider_maps_legacy_placeholder_voice_to_hoaimy(self) -> None:
        seen: dict[str, str] = {}

        def _capture(*, text: str, voice_id: str, speaking_rate: float):
            seen["voice_id"] = voice_id
            return _tiny_wav(0.4), 0.4

        provider = EdgeTtsProvider(synthesize_audio=_capture)
        provider.synthesize(
            TtsProviderInput(
                text="ok",
                language_code="vi",
                voice_config=VoiceConfig(voice_id="vi_female_placeholder"),
            )
        )
        self.assertEqual(seen["voice_id"], DEFAULT_EDGE_TTS_VOICE)

    def test_factory_placeholder_setting(self) -> None:
        provider = build_default_tts_provider(provider_name="placeholder")
        self.assertIsInstance(provider, PlaceholderToneTtsProvider)

    def test_factory_edge_setting_uses_edge_provider(self) -> None:
        provider = build_default_tts_provider(
            provider_name="edge",
            edge_provider_factory=lambda: EdgeTtsProvider(synthesize_audio=lambda **_: (_tiny_wav(0.3), 0.3)),
        )
        self.assertIsInstance(provider, EdgeTtsProvider)


if __name__ == "__main__":
    unittest.main()
