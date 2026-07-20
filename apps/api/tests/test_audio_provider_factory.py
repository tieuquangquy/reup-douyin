from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.audio_pipeline.provider_factory import (
    build_default_stt_provider,
    build_default_translation_provider,
    probe_translation_ai_client,
)
from src.audio_pipeline.providers import PlaceholderVietnameseTranslationProvider
from src.audio_pipeline.stt_funasr import FunasrSttProvider
from src.audio_pipeline.translation_llm import (
    DurationConstrainedTranslationProvider,
    OpenAiCompatibleHttpClient,
)


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

    def test_probe_uses_draft_credentials_when_enabled_is_false(self) -> None:
        """Ops Test Connection must probe the form draft, not env Gemini, when override is Off."""
        draft = SimpleNamespace(
            enabled=False,
            provider="openai_compatible",
            model="gpt-5.6-sol",
            api_key="sk-draft",
            base_url="https://example.com/v1",
            timeout_seconds=90.0,
            fallback_provider="none",
            fallback_model="",
        )
        env = SimpleNamespace(
            gemini_api_key="env-gemini-key",
            gemini_translation_model="gemini-2.5-flash",
            ollama_base_url="http://127.0.0.1:11434",
            ollama_translation_model="qwen2.5:14b",
            audio_translation_provider="auto",
        )
        with patch.object(OpenAiCompatibleHttpClient, "complete", return_value="OK"):
            ok, provider_name, detail = probe_translation_ai_client(draft, settings=env)
        self.assertTrue(ok)
        self.assertEqual(provider_name, "openai_compatible")
        self.assertEqual(detail, "OK")


if __name__ == "__main__":
    unittest.main()
