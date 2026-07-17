"""List models for Translation AI providers (draft credentials, no live network)."""

from __future__ import annotations

import json
import unittest

from src.audio_pipeline.translation_ai_models import (
    list_translation_ai_models,
    model_list_ready,
)


class TranslationAiListModelsTests(unittest.TestCase):
    def test_ready_matrix(self) -> None:
        self.assertFalse(model_list_ready("openai_compatible", api_key="", base_url="https://x/v1"))
        self.assertFalse(model_list_ready("openai_compatible", api_key="sk", base_url=""))
        self.assertTrue(model_list_ready("openai_compatible", api_key="sk", base_url="https://x/v1"))
        self.assertTrue(model_list_ready("gemini", api_key="gk", base_url=""))
        self.assertFalse(model_list_ready("gemini", api_key="", base_url=""))
        self.assertTrue(model_list_ready("ollama", api_key="", base_url="http://127.0.0.1:11434"))
        self.assertFalse(model_list_ready("ollama", api_key="", base_url=""))
        self.assertFalse(model_list_ready("auto", api_key="x", base_url="https://x"))

    def test_list_openai_compatible_parses_ids(self) -> None:
        captured: dict = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}, {"id": ""}]}
                ).encode("utf-8")

        def fake_open(request, timeout=None):
            captured["url"] = request.full_url
            captured["auth"] = request.headers.get("Authorization")
            return FakeResponse()

        ok, models, detail = list_translation_ai_models(
            provider="openai_compatible",
            api_key="sk-test",
            base_url="https://api.example.com/v1",
            opener=fake_open,
        )
        self.assertTrue(ok)
        self.assertEqual(models, ["gpt-4o", "gpt-4o-mini"])
        self.assertEqual(captured["url"], "https://api.example.com/v1/models")
        self.assertEqual(captured["auth"], "Bearer sk-test")
        self.assertEqual(detail, "")

    def test_list_gemini_strips_models_prefix(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "models": [
                            {"name": "models/gemini-2.5-flash"},
                            {"name": "models/gemini-2.0-flash"},
                        ]
                    }
                ).encode("utf-8")

        def fake_open(request, timeout=None):
            self.assertIn("generativelanguage.googleapis.com", request.full_url)
            self.assertIn("key=gk", request.full_url)
            return FakeResponse()

        ok, models, detail = list_translation_ai_models(
            provider="gemini",
            api_key="gk",
            base_url="",
            opener=fake_open,
        )
        self.assertTrue(ok)
        self.assertEqual(models, ["gemini-2.0-flash", "gemini-2.5-flash"])
        self.assertEqual(detail, "")

    def test_list_ollama_uses_tags(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"models": [{"name": "qwen2.5:14b"}, {"name": "llama3.2:3b"}]}).encode(
                    "utf-8"
                )

        def fake_open(request, timeout=None):
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/tags")
            return FakeResponse()

        ok, models, detail = list_translation_ai_models(
            provider="ollama",
            api_key="",
            base_url="http://127.0.0.1:11434",
            opener=fake_open,
        )
        self.assertTrue(ok)
        self.assertEqual(models, ["llama3.2:3b", "qwen2.5:14b"])

    def test_not_ready_returns_empty_without_network(self) -> None:
        called = False

        def boom(*_a, **_k):
            nonlocal called
            called = True
            raise AssertionError("must not call network")

        ok, models, detail = list_translation_ai_models(
            provider="openai_compatible",
            api_key="",
            base_url="https://api.example.com/v1",
            opener=boom,
        )
        self.assertFalse(ok)
        self.assertEqual(models, [])
        self.assertIn("credentials", detail.lower())
        self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
