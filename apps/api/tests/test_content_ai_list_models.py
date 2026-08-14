"""List models for Content AI (draft credentials, no live network)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.content_intelligence.services.content_ai_classifier import ContentAiClassifier
from src.content_intelligence.services.content_ai_settings_service import (
    ContentAiConfig,
    merge_content_ai_list_models_draft,
)


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class ContentAiListModelsTests(unittest.TestCase):
    def test_openai_compatible_parses_ids_without_live_network(self) -> None:
        captured: dict = {}

        def fake_open(request, timeout=None):
            captured["url"] = request.full_url
            captured["auth"] = request.headers.get("Authorization")
            captured["timeout"] = timeout
            return _FakeResponse({"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}, {"id": ""}]})

        ok, models, detail = ContentAiClassifier().list_models(
            ContentAiConfig(
                provider="openai_compatible",
                api_key="sk-test",
                base_url="https://api.example.com/v1",
                timeout_seconds=90.0,
            ),
            opener=fake_open,
        )
        self.assertTrue(ok)
        self.assertEqual(models, ["gpt-4o", "gpt-4o-mini"])
        self.assertEqual(captured["url"], "https://api.example.com/v1/models")
        self.assertEqual(captured["auth"], "Bearer sk-test")
        self.assertLessEqual(captured["timeout"], 12.0)
        self.assertEqual(detail, "")

    def test_auto_provider_resolves_to_gemini_before_listing(self) -> None:
        captured: dict = {}

        def fake_open(request, timeout=None):
            captured["url"] = request.full_url
            return _FakeResponse(
                {
                    "models": [
                        {"name": "models/gemini-2.5-flash"},
                        {"name": "models/gemini-2.0-flash"},
                    ]
                }
            )

        ok, models, detail = ContentAiClassifier().list_models(
            ContentAiConfig(provider="auto", api_key="gk", base_url="", model=""),
            opener=fake_open,
        )
        self.assertTrue(ok)
        self.assertEqual(models, ["gemini-2.0-flash", "gemini-2.5-flash"])
        self.assertIn("generativelanguage.googleapis.com", captured["url"])
        self.assertIn("key=gk", captured["url"])
        self.assertEqual(detail, "")

    def test_missing_credentials_fail_closed_without_opener(self) -> None:
        opened = {"called": False}

        def fake_open(request, timeout=None):
            opened["called"] = True
            raise AssertionError("must not contact a provider without credentials")

        ok, models, detail = ContentAiClassifier().list_models(
            ContentAiConfig(provider="gemini", api_key=None, base_url=""),
            opener=fake_open,
        )
        self.assertFalse(ok)
        self.assertEqual(models, [])
        self.assertFalse(opened["called"])
        self.assertIn("credential", detail.lower())

    def test_draft_blank_key_keeps_stored_secret(self) -> None:
        saved = ContentAiConfig(
            provider="gemini",
            api_key="stored-key",
            base_url="",
            timeout_seconds=90.0,
        )
        merged = merge_content_ai_list_models_draft(
            saved,
            {"provider": "auto", "api_key": None, "base_url": None, "timeout_seconds": 12.0},
        )
        self.assertEqual(merged.api_key, "stored-key")
        self.assertEqual(merged.provider, "auto")
        self.assertEqual(merged.timeout_seconds, 12.0)

    def test_clear_api_key_drops_stored_secret(self) -> None:
        saved = ContentAiConfig(provider="gemini", api_key="stored-key")
        merged = merge_content_ai_list_models_draft(
            saved,
            {"clear_api_key": True, "api_key": "typed"},
        )
        self.assertIsNone(merged.api_key)

    def test_route_exposes_models_without_test_confirmation(self) -> None:
        route = Path(__file__).resolve().parents[1] / "src" / "api" / "routes" / "content_intelligence.py"
        text = route.read_text(encoding="utf-8")
        self.assertIn('/content-intelligence/ai-config/models', text)
        models_start = text.index('/content-intelligence/ai-config/models')
        models_block = text[models_start : models_start + 1800]
        self.assertIn("list_models", models_block)
        self.assertIn("merge_content_ai_list_models_draft", models_block)
        self.assertNotIn("CONTENT_CLASSIFICATION_AI_APPROVED", models_block)


if __name__ == "__main__":
    unittest.main()
