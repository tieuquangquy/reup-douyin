from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.audio_pipeline.provider_factory import build_default_stt_provider, build_default_translation_provider
from src.audio_pipeline.providers import PlaceholderVietnameseTranslationProvider
from src.audio_pipeline.stt_funasr import FunasrSttProvider
from src.audio_pipeline.translation_llm import DurationConstrainedTranslationProvider


class AudioProviderFactoryTests(unittest.TestCase):
    def test_default_stt_is_funasr_wrapper(self) -> None:
        provider = build_default_stt_provider(settings=SimpleNamespace(local_storage_root="./data/storage"))
        self.assertIsInstance(provider, FunasrSttProvider)

    def test_default_translation_uses_llm_when_gemini_key_present(self) -> None:
        settings = SimpleNamespace(
            gemini_api_key="test-key",
            ollama_base_url="http://127.0.0.1:11434",
            ollama_translation_model="qwen2.5:14b",
            audio_translation_provider="auto",
        )
        provider = build_default_translation_provider(settings=settings)
        self.assertIsInstance(provider, DurationConstrainedTranslationProvider)
        self.assertEqual(provider.primary.provider_name, "gemini")

    def test_default_translation_placeholder_when_no_llm_configured(self) -> None:
        settings = SimpleNamespace(
            gemini_api_key=None,
            ollama_base_url="http://127.0.0.1:11434",
            ollama_translation_model="qwen2.5:14b",
            audio_translation_provider="placeholder",
        )
        provider = build_default_translation_provider(settings=settings)
        self.assertIsInstance(provider, PlaceholderVietnameseTranslationProvider)

    def test_auto_uses_qwen_when_gemini_missing_but_ollama_enabled(self) -> None:
        settings = SimpleNamespace(
            gemini_api_key="",
            ollama_base_url="http://127.0.0.1:11434",
            ollama_translation_model="qwen2.5:14b",
            audio_translation_provider="auto",
            ollama_translation_enabled=True,
        )
        provider = build_default_translation_provider(settings=settings)
        self.assertIsInstance(provider, DurationConstrainedTranslationProvider)
        self.assertEqual(provider.primary.provider_name, "qwen_ollama")


if __name__ == "__main__":
    unittest.main()
