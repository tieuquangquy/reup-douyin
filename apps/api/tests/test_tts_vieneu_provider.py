"""VieNeu TTS provider unit tests (mocked SDK)."""

from __future__ import annotations

import unittest
import wave
from io import BytesIO

from src.tts_pipeline.provider_factory import build_default_tts_provider
from src.tts_pipeline.types import TtsProviderInput, VoiceConfig
from src.tts_pipeline.vieneu_tts_provider import (
    DEFAULT_VIENEU_VOICE,
    VieNeuTtsProvider,
    build_vieneu_client_kwargs,
    resolve_vieneu_voice_id,
)


def _tiny_wav(duration_seconds: float = 0.5, sample_rate: int = 16000) -> bytes:
    frames = max(1, int(duration_seconds * sample_rate))
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


class VieNeuTtsProviderTests(unittest.TestCase):
    def test_vieneu_returns_wav_metadata(self) -> None:
        provider = VieNeuTtsProvider(synthesize_audio=lambda **_: (_tiny_wav(0.6), 0.6))
        result = provider.synthesize(
            TtsProviderInput(
                text="Xin chào",
                language_code="vi",
                voice_config=VoiceConfig(voice_id=DEFAULT_VIENEU_VOICE),
            )
        )
        self.assertTrue(result.audio_bytes.startswith(b"RIFF"))
        self.assertEqual(result.provider_metadata["provider"], "vieneu")
        self.assertAlmostEqual(result.duration_seconds, 0.6, places=2)

    def test_maps_edge_voice_to_default_vieneu(self) -> None:
        seen: dict[str, str] = {}

        def _capture(*, text: str, voice_id: str, speaking_rate: float, style: str):
            seen["voice_id"] = voice_id
            return _tiny_wav(0.3), 0.3

        provider = VieNeuTtsProvider(synthesize_audio=_capture)
        provider.synthesize(
            TtsProviderInput(
                text="ok",
                language_code="vi",
                voice_config=VoiceConfig(voice_id="vi-VN-HoaiMyNeural"),
            )
        )
        self.assertEqual(seen["voice_id"], DEFAULT_VIENEU_VOICE)

    def test_resolve_vieneu_voice_preserves_ngoc_linh(self) -> None:
        self.assertEqual(resolve_vieneu_voice_id("Ngọc Linh"), "Ngọc Linh")

    def test_auto_local_backend_prefers_onnx_for_phase1(self) -> None:
        kwargs = build_vieneu_client_kwargs(
            local_backend="auto",
            model_id="v3turbo",
            base_url="",
            device="auto",
        )
        self.assertEqual(kwargs.get("backend"), "onnx")
        self.assertEqual(kwargs.get("mode"), "v3turbo")

    def test_pytorch_backend_uses_modelscope_moss_id(self) -> None:
        kwargs = build_vieneu_client_kwargs(
            local_backend="pytorch",
            model_id="",
            base_url="",
            device="cuda",
        )
        self.assertEqual(kwargs.get("backend"), "pytorch")
        self.assertEqual(kwargs.get("moss_tokenizer"), "openmoss/MOSS-Audio-Tokenizer-Nano")
        self.assertEqual(kwargs.get("device"), "cuda")

    def test_factory_vieneu_setting(self) -> None:
        provider = build_default_tts_provider(
            provider_name="vieneu",
            vieneu_provider_factory=lambda: VieNeuTtsProvider(
                synthesize_audio=lambda **_: (_tiny_wav(0.2), 0.2)
            ),
        )
        self.assertIsInstance(provider, VieNeuTtsProvider)


if __name__ == "__main__":
    unittest.main()
