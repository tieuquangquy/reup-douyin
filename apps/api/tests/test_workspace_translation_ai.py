"""Workspace DB-backed Translation AI (LLM connection) settings."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.audio_pipeline.provider_factory import build_default_translation_provider
from src.audio_pipeline.translation_llm import DurationConstrainedTranslationProvider
from src.services.workspace_settings_service import (
    TRANSLATION_AI_KEY,
    WorkspaceSettingsService,
)


class WorkspaceTranslationAiTests(unittest.TestCase):
    def test_get_returns_disabled_when_unset(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json=None)
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        cfg = service.get_translation_ai(workspace.id)
        self.assertFalse(cfg.enabled)
        self.assertIsNone(cfg.api_key)

    def test_set_falls_back_to_default_workspace_when_jwt_workspace_missing(self) -> None:
        """Login JWT uses uuid5; Phase 1 data lives on ensure_default_workspace — Save must still work."""
        from unittest.mock import patch

        default_ws = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = None
        service = WorkspaceSettingsService(db)
        with patch(
            "src.services.workspace_settings_service.ensure_default_workspace",
            return_value=default_ws,
        ) as ensure:
            saved = service.set_translation_ai(
                uuid4(),
                {
                    "enabled": True,
                    "provider": "openai_compatible",
                    "model": "gpt-3.5",
                    "api_key": "sk-test",
                    "base_url": "https://hhtechapi.com/v1",
                    "timeout_seconds": 90,
                    "fallback_provider": "none",
                    "fallback_model": "",
                },
            )
        ensure.assert_called_once_with(db)
        self.assertTrue(saved.enabled)
        self.assertEqual(default_ws.settings_json[TRANSLATION_AI_KEY]["provider"], "openai_compatible")
        db.commit.assert_called()

    def test_set_masks_api_key_on_public_view(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        saved = service.set_translation_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "openai_compatible",
                "model": "gpt-4o-mini",
                "api_key": "sk-secret-abcdef12",
                "base_url": "https://api.example.com/v1",
                "timeout_seconds": 60,
                "fallback_provider": "none",
                "fallback_model": "",
            },
        )
        self.assertTrue(saved.enabled)
        self.assertEqual(workspace.settings_json[TRANSLATION_AI_KEY]["api_key"], "sk-secret-abcdef12")
        public = service.get_translation_ai_public(workspace.id)
        self.assertTrue(public["api_key_set"])
        self.assertNotIn("sk-secret", public["api_key_masked"])
        self.assertTrue(public["api_key_masked"].endswith("ef12"))
        self.assertNotIn("api_key", public)

    def test_put_keeps_existing_key_when_api_key_omitted(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={
                TRANSLATION_AI_KEY: {
                    "enabled": True,
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
                    "api_key": "keep-me",
                    "base_url": "",
                    "timeout_seconds": 90,
                    "fallback_provider": "none",
                    "fallback_model": "",
                }
            },
        )
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_translation_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "gemini",
                "model": "gemini-2.5-pro",
                "base_url": "",
                "timeout_seconds": 90,
                "fallback_provider": "none",
                "fallback_model": "",
            },
            keep_existing_api_key=True,
        )
        self.assertEqual(workspace.settings_json[TRANSLATION_AI_KEY]["api_key"], "keep-me")
        self.assertEqual(workspace.settings_json[TRANSLATION_AI_KEY]["model"], "gemini-2.5-pro")

    def test_factory_uses_workspace_openai_compatible_when_enabled(self) -> None:
        workspace_ai = SimpleNamespace(
            enabled=True,
            provider="openai_compatible",
            model="gpt-4o-mini",
            api_key="sk-test",
            base_url="https://api.example.com/v1",
            timeout_seconds=45.0,
            fallback_provider="none",
            fallback_model="",
        )
        env = SimpleNamespace(
            gemini_api_key="env-gemini",
            gemini_translation_model="gemini-2.5-flash",
            ollama_translation_enabled=False,
            ollama_base_url="http://127.0.0.1:11434",
            ollama_translation_model="qwen2.5:14b",
            audio_translation_provider="auto",
        )
        provider = build_default_translation_provider(settings=env, workspace_ai=workspace_ai)
        self.assertIsInstance(provider, DurationConstrainedTranslationProvider)
        self.assertEqual(provider.primary.provider_name, "openai_compatible")
        self.assertEqual(provider.primary.model, "gpt-4o-mini")
        self.assertEqual(provider.primary.base_url, "https://api.example.com/v1")

    def test_factory_falls_back_to_env_when_workspace_disabled(self) -> None:
        workspace_ai = SimpleNamespace(
            enabled=False,
            provider="openai_compatible",
            model="ignored",
            api_key="sk-ignored",
            base_url="https://api.example.com/v1",
            timeout_seconds=90.0,
            fallback_provider="none",
            fallback_model="",
        )
        env = SimpleNamespace(
            gemini_api_key="env-gemini",
            gemini_translation_model="gemini-2.5-flash",
            ollama_translation_enabled=False,
            ollama_base_url="http://127.0.0.1:11434",
            ollama_translation_model="qwen2.5:14b",
            audio_translation_provider="auto",
        )
        provider = build_default_translation_provider(settings=env, workspace_ai=workspace_ai)
        self.assertIsInstance(provider, DurationConstrainedTranslationProvider)
        self.assertEqual(provider.primary.provider_name, "gemini")

    def test_mask_helper_hides_secret(self) -> None:
        from src.services.workspace_settings_service import mask_secret

        self.assertEqual(mask_secret(""), "")
        self.assertEqual(mask_secret("ab"), "••••")
        self.assertTrue(mask_secret("sk-abcdef12").endswith("ef12"))
        self.assertNotIn("sk-abcd", mask_secret("sk-abcdef12"))


class OpenAiCompatibleClientTests(unittest.TestCase):
    def test_complete_posts_chat_completions(self) -> None:
        from src.audio_pipeline.translation_llm import OpenAiCompatibleHttpClient

        captured: dict = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "Xin chao"}}]}
                ).encode("utf-8")

        def fake_open(request, timeout=None):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["auth"] = request.headers.get("Authorization")
            return FakeResponse()

        client = OpenAiCompatibleHttpClient(
            api_key="sk-test",
            model="gpt-4o-mini",
            base_url="https://api.example.com/v1",
            opener=fake_open,
        )
        text = client.complete("translate hi")
        self.assertEqual(text, "Xin chao")
        self.assertEqual(captured["url"], "https://api.example.com/v1/chat/completions")
        self.assertEqual(captured["auth"], "Bearer sk-test")
        self.assertEqual(captured["body"]["model"], "gpt-4o-mini")
        self.assertEqual(captured["body"]["messages"][0]["content"], "translate hi")


if __name__ == "__main__":
    unittest.main()
