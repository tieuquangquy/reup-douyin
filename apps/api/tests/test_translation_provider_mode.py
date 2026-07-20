"""Resolve Translation AI provider ids to runtime modes + list-models aliases."""

from __future__ import annotations

import json
import unittest

from src.audio_pipeline.translation_ai_models import list_translation_ai_models, model_list_ready
from src.audio_pipeline.translation_provider_mode import resolve_translation_provider_mode


class TranslationProviderModeTests(unittest.TestCase):
    def test_native_and_aliases(self) -> None:
        self.assertEqual(resolve_translation_provider_mode("gemini"), "gemini")
        self.assertEqual(resolve_translation_provider_mode("ollama"), "ollama")
        self.assertEqual(resolve_translation_provider_mode("qwen"), "ollama")
        self.assertEqual(resolve_translation_provider_mode("openai_compatible"), "openai_compatible")
        self.assertEqual(resolve_translation_provider_mode("openrouter"), "openai_compatible")
        self.assertEqual(resolve_translation_provider_mode("deepseek"), "openai_compatible")
        self.assertEqual(resolve_translation_provider_mode("custom_proxy"), "openai_compatible")
        self.assertEqual(resolve_translation_provider_mode("auto"), "unsupported")
        self.assertEqual(resolve_translation_provider_mode(""), "unsupported")

    def test_model_list_ready_for_aliases(self) -> None:
        self.assertTrue(
            model_list_ready(
                "openrouter",
                api_key="sk",
                base_url="https://openrouter.ai/api/v1",
            )
        )
        self.assertFalse(model_list_ready("openrouter", api_key="sk", base_url=""))
        self.assertTrue(model_list_ready("gemini", api_key="gk", base_url=""))

    def test_list_openrouter_uses_openai_compatible_endpoint(self) -> None:
        captured: dict = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"data": [{"id": "openai/gpt-4o-mini"}]}).encode("utf-8")

        def fake_open(request, timeout=None):
            captured["url"] = request.full_url
            captured["auth"] = request.headers.get("Authorization")
            return FakeResponse()

        ok, models, detail = list_translation_ai_models(
            provider="openrouter",
            api_key="sk-or",
            base_url="https://openrouter.ai/api/v1",
            opener=fake_open,
        )
        self.assertTrue(ok)
        self.assertEqual(models, ["openai/gpt-4o-mini"])
        self.assertEqual(captured["url"], "https://openrouter.ai/api/v1/models")
        self.assertEqual(captured["auth"], "Bearer sk-or")
        self.assertEqual(detail, "")


if __name__ == "__main__":
    unittest.main()
