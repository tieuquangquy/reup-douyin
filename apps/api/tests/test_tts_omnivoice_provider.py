"""OmniVoice (k2-fsa) TTS provider — Preview / job synthesize path."""

from __future__ import annotations

import unittest
import wave
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from src.tts_pipeline.omnivoice_tts_provider import (
    DEFAULT_OMNIVOICE_MODEL,
    OmniVoiceTtsProvider,
    resolve_omnivoice_instruct,
    resolve_omnivoice_model_id,
)
from src.tts_pipeline.provider_factory import (
    ConfiguredButUnavailableTtsProvider,
    build_default_tts_provider,
    probe_tts_ai_client,
)
from src.tts_pipeline.types import TtsProviderInput, VoiceConfig


def _tiny_wav(duration_seconds: float = 0.5, sample_rate: int = 24000) -> bytes:
    frames = max(1, int(duration_seconds * sample_rate))
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


class OmniVoiceResolveTests(unittest.TestCase):
    def test_model_id_defaults_to_k2_checkpoint(self) -> None:
        self.assertEqual(resolve_omnivoice_model_id(""), DEFAULT_OMNIVOICE_MODEL)
        self.assertEqual(resolve_omnivoice_model_id("omnivoice"), DEFAULT_OMNIVOICE_MODEL)
        self.assertEqual(resolve_omnivoice_model_id("k2-fsa/OmniVoice"), "k2-fsa/OmniVoice")

    def test_instruct_presets_use_omnivoice_allowlist(self) -> None:
        self.assertIsNone(resolve_omnivoice_instruct("auto"))
        # OmniVoice rejects free-form prose; presets must be allowlisted tokens only.
        north = resolve_omnivoice_instruct("instruct:vi_female_north")
        self.assertEqual(north, "female, young adult")
        self.assertEqual(resolve_omnivoice_instruct("alloy"), "female, young adult")
        self.assertEqual(resolve_omnivoice_instruct("instruct:en_british"), "female, british accent")
        # Free-form prose is dropped (would fail OmniVoice.generate).
        self.assertIsNone(
            resolve_omnivoice_instruct(
                "Vietnamese female speaker from Northern Vietnam, clear natural tone"
            )
        )


class OmniVoiceProviderTests(unittest.TestCase):
    def test_preferred_batch_size_is_vram_aware(self) -> None:
        provider = OmniVoiceTtsProvider(model_id="k2-fsa/OmniVoice")
        fake_torch = SimpleNamespace(
            cuda=SimpleNamespace(
                is_available=lambda: True,
                get_device_properties=lambda _index: SimpleNamespace(total_memory=4 * 1024**3),
            )
        )
        with (
            patch("src.tts_pipeline.omnivoice_tts_provider._resolve_device", return_value="cuda"),
            patch.dict("sys.modules", {"torch": fake_torch}),
        ):
            self.assertEqual(provider.preferred_batch_size, 1)
        fake_torch.cuda.get_device_properties = lambda _index: SimpleNamespace(
            total_memory=12 * 1024**3
        )
        with (
            patch("src.tts_pipeline.omnivoice_tts_provider._resolve_device", return_value="cuda"),
            patch.dict("sys.modules", {"torch": fake_torch}),
        ):
            self.assertEqual(provider.preferred_batch_size, 4)

    def test_synthesize_returns_wav(self) -> None:
        seen: dict[str, object] = {}

        def _capture(**kwargs):  # noqa: ANN003
            seen.update(kwargs)
            return _tiny_wav(0.4), 0.4

        provider = OmniVoiceTtsProvider(
            synthesize_audio=_capture,
            model_id="k2-fsa/OmniVoice",
        )
        result = provider.synthesize(
            TtsProviderInput(
                text="Xin chào",
                language_code="vi",
                voice_config=VoiceConfig(
                    voice_id="instruct:vi_female_north",
                    language_code="vi",
                    speaking_rate=1.0,
                ),
            )
        )
        self.assertTrue(result.audio_bytes.startswith(b"RIFF"))
        self.assertEqual(result.provider_metadata["provider"], "omnivoice")
        self.assertEqual(seen.get("instruct"), "female, young adult")

    def test_rejects_unsupported_studio_engine(self) -> None:
        provider = OmniVoiceTtsProvider(
            synthesize_audio=lambda **_: (_tiny_wav(0.1), 0.1),
            model_id="cosyvoice2",
        )
        with self.assertRaises(Exception) as ctx:
            provider.synthesize(
                TtsProviderInput(
                    text="hi",
                    language_code="vi",
                    voice_config=VoiceConfig(voice_id="auto"),
                )
            )
        self.assertIn("only the default OmniVoice", str(ctx.exception))

    def test_synthesize_batch_uses_one_model_generate_call(self) -> None:
        class _FakeModel:
            sampling_rate = 24_000

            def __init__(self) -> None:
                self.calls = 0
                self.last_text = None

            def generate(self, **kwargs):  # noqa: ANN003
                self.calls += 1
                self.last_text = kwargs["text"]
                return [np.zeros(2_400, dtype=np.float32), np.zeros(3_600, dtype=np.float32)]

        model = _FakeModel()
        provider = OmniVoiceTtsProvider(model_id="k2-fsa/OmniVoice")
        requests = [
            TtsProviderInput(
                text="Một",
                language_code="vi",
                voice_config=VoiceConfig(voice_id="instruct:vi_female_north"),
            ),
            TtsProviderInput(
                text="Hai",
                language_code="vi",
                voice_config=VoiceConfig(voice_id="instruct:vi_female_north"),
            ),
        ]
        with (
            patch("src.tts_pipeline.omnivoice_tts_provider._resolve_device", return_value="cpu"),
            patch(
                "src.tts_pipeline.omnivoice_tts_provider._get_or_load_model",
                return_value=model,
            ),
        ):
            outputs = provider.synthesize_batch(requests)

        self.assertEqual(model.calls, 1)
        self.assertEqual(model.last_text, ["Một", "Hai"])
        self.assertEqual(len(outputs), 2)
        self.assertTrue(all(output.audio_bytes.startswith(b"RIFF") for output in outputs))
        self.assertEqual(outputs[0].provider_metadata["batch_size"], 2)


class OmniVoiceFactoryPreviewTests(unittest.TestCase):
    def test_factory_builds_omnivoice_not_unavailable(self) -> None:
        """Regression: Ops Preview must not hit ConfiguredButUnavailable for omnivoice."""
        provider = build_default_tts_provider(
            provider_name="omnivoice",
            omnivoice_provider_factory=lambda: OmniVoiceTtsProvider(
                synthesize_audio=lambda **_: (_tiny_wav(0.2), 0.2),
                model_id="k2-fsa/OmniVoice",
            ),
        )
        self.assertNotIsInstance(provider, ConfiguredButUnavailableTtsProvider)
        self.assertEqual(getattr(provider, "provider_name", ""), "omnivoice")
        out = provider.synthesize(
            TtsProviderInput(
                text="Xin chào",
                language_code="vi",
                voice_config=VoiceConfig(voice_id="auto"),
            )
        )
        self.assertTrue(out.audio_bytes.startswith(b"RIFF"))

    def test_factory_workspace_omnivoice_uses_adapter(self) -> None:
        """Mirrors Ops saved settings (provider=omnivoice, model=k2-fsa/OmniVoice)."""
        workspace = SimpleNamespace(
            enabled=True,
            provider="omnivoice",
            voice_id="instruct:vi_female_north",
            speaking_rate=1.0,
            language_code="vi",
            model_id="k2-fsa/OmniVoice",
            api_key=None,
            base_url="",
            timeout_seconds=60.0,
            fallback_provider="none",
            fallback_voice_id="",
            local_backend="auto",
            device="auto",
            cli_binary="",
            options_json={},
        )
        provider = build_default_tts_provider(
            workspace_tts=workspace,
            omnivoice_provider_factory=lambda: OmniVoiceTtsProvider(
                synthesize_audio=lambda **_: (_tiny_wav(0.3), 0.3),
                model_id="k2-fsa/OmniVoice",
            ),
        )
        self.assertNotIsInstance(provider, ConfiguredButUnavailableTtsProvider)
        out = provider.synthesize(
            TtsProviderInput(
                text="Xin chào",
                language_code="vi",
                voice_config=VoiceConfig(voice_id="instruct:vi_female_north"),
            )
        )
        self.assertTrue(out.audio_bytes.startswith(b"RIFF"))

    def test_probe_omnivoice_when_importable(self) -> None:
        workspace = SimpleNamespace(
            enabled=True,
            provider="omnivoice",
            language_code="vi",
            api_key=None,
            base_url="",
        )
        with patch(
            "src.tts_pipeline.provider_factory._module_importable",
            return_value=True,
        ):
            result = probe_tts_ai_client(workspace)
        self.assertTrue(result.ok)
        self.assertEqual(result.provider, "omnivoice")
        self.assertIsNotNone(result.catalog)
        self.assertNotIn("until a dedicated synthesize adapter", result.detail)


if __name__ == "__main__":
    unittest.main()
