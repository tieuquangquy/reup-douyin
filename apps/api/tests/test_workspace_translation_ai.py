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


def _active_profile(workspace, key=TRANSLATION_AI_KEY):
    store = workspace.settings_json[key]
    active_id = store["active_profile_id"]
    return next(p for p in store["profiles"] if p["id"] == active_id)


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
        active = _active_profile(default_ws)
        self.assertEqual(active["provider"], "openai_compatible")
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
        active = _active_profile(workspace)
        self.assertEqual(active["api_key"], "sk-secret-abcdef12")
        public = service.get_translation_ai_public(workspace.id)
        self.assertTrue(public["api_key_set"])
        self.assertNotIn("sk-secret", public["api_key_masked"])
        self.assertTrue(public["api_key_masked"].endswith("ef12"))
        self.assertEqual(public["api_key"], "sk-secret-abcdef12")
        self.assertEqual(public["profiles"][0]["api_key"], "sk-secret-abcdef12")

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
        active = _active_profile(workspace)
        self.assertEqual(active["api_key"], "keep-me")
        self.assertEqual(active["model"], "gemini-2.5-pro")

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


class TranslationAiProfileLifecycleTests(unittest.TestCase):
    def _service(self, workspace):
        db = MagicMock()
        db.get.return_value = workspace
        return WorkspaceSettingsService(db)

    def test_legacy_flat_migrates_on_get_public(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={
                TRANSLATION_AI_KEY: {
                    "enabled": True,
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
                    "api_key": "legacy-key-1234",
                    "base_url": "",
                    "timeout_seconds": 90,
                    "fallback_provider": "none",
                    "fallback_model": "",
                }
            },
        )
        service = self._service(workspace)
        public = service.get_translation_ai_public(workspace.id)
        self.assertEqual(len(public["profiles"]), 1)
        self.assertEqual(public["profiles"][0]["name"], "Default")
        self.assertEqual(public["active_profile_id"], public["profiles"][0]["id"])
        self.assertEqual(public["active_profile_name"], "Default")
        cfg = service.get_translation_ai(workspace.id)
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.provider, "gemini")
        self.assertEqual(cfg.api_key, "legacy-key-1234")

    def test_create_second_profile_does_not_change_active(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        service = self._service(workspace)
        service.set_translation_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "openai_compatible",
                "model": "gpt-4o-mini",
                "api_key": "sk-first",
                "base_url": "https://a.example/v1",
                "timeout_seconds": 60,
                "fallback_provider": "none",
                "fallback_model": "",
            },
        )
        first_id = _active_profile(workspace)["id"]
        created = service.create_translation_ai_profile(workspace.id, name="Second")
        self.assertEqual(created["name"], "Second")
        self.assertEqual(created["provider"], "auto")
        self.assertFalse(created["enabled"])
        store = workspace.settings_json[TRANSLATION_AI_KEY]
        self.assertEqual(len(store["profiles"]), 2)
        self.assertEqual(store["active_profile_id"], first_id)
        self.assertEqual(service.get_translation_ai(workspace.id).provider, "openai_compatible")

    def test_reorder_profiles_persists_list_order_without_changing_active(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        service = self._service(workspace)
        service.set_translation_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "openai_compatible",
                "model": "gpt-4o-mini",
                "api_key": "sk-first",
                "base_url": "https://a.example/v1",
                "timeout_seconds": 60,
                "fallback_provider": "none",
                "fallback_model": "",
            },
        )
        first_id = _active_profile(workspace)["id"]
        second = service.create_translation_ai_profile(workspace.id, name="Second")
        third = service.create_translation_ai_profile(workspace.id, name="Third")
        before_ids = [p["id"] for p in workspace.settings_json[TRANSLATION_AI_KEY]["profiles"]]
        self.assertEqual(before_ids[0], first_id)
        reordered = [third["id"], first_id, second["id"]]
        public = service.reorder_translation_ai_profiles(workspace.id, reordered)
        store_ids = [p["id"] for p in workspace.settings_json[TRANSLATION_AI_KEY]["profiles"]]
        self.assertEqual(store_ids, reordered)
        self.assertEqual(public["active_profile_id"], first_id)
        self.assertEqual([p["id"] for p in public["profiles"]], reordered)
        with self.assertRaises(ValueError) as ctx:
            service.reorder_translation_ai_profiles(workspace.id, [first_id, second["id"]])
        self.assertIn("invalid_profile_order", str(ctx.exception))

    def test_activate_switches_get_translation_ai(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        service = self._service(workspace)
        service.set_translation_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "api_key": "sk-a",
                "base_url": "",
                "timeout_seconds": 90,
                "fallback_provider": "none",
                "fallback_model": "",
            },
        )
        first_id = _active_profile(workspace)["id"]
        created = service.create_translation_ai_profile(workspace.id, name="Cloud")
        service.set_translation_ai_profile(
            workspace.id,
            created["id"],
            {
                "enabled": True,
                "provider": "openai_compatible",
                "model": "gpt-4o-mini",
                "api_key": "sk-cloud",
                "base_url": "https://cloud.example/v1",
                "timeout_seconds": 60,
                "fallback_provider": "none",
                "fallback_model": "",
            },
        )
        self.assertEqual(service.get_translation_ai(workspace.id).provider, "gemini")
        service.activate_translation_ai_profile(workspace.id, created["id"])
        self.assertEqual(service.get_translation_ai(workspace.id).provider, "openai_compatible")
        self.assertEqual(service.get_translation_ai(workspace.id).api_key, "sk-cloud")
        service.activate_translation_ai_profile(workspace.id, first_id)
        self.assertEqual(service.get_translation_ai(workspace.id).provider, "gemini")

    def test_delete_last_profile_fails(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        service = self._service(workspace)
        created = service.create_translation_ai_profile(workspace.id, name="Only")
        # Normalize: only "Only" and any auto-created default from set path
        store = workspace.settings_json[TRANSLATION_AI_KEY]
        # Delete extras down to one
        while len(store["profiles"]) > 1:
            leftover = next(p for p in store["profiles"] if p["id"] != created["id"])
            service.delete_translation_ai_profile(workspace.id, leftover["id"])
            store = workspace.settings_json[TRANSLATION_AI_KEY]
        with self.assertRaises(ValueError) as ctx:
            service.delete_translation_ai_profile(workspace.id, created["id"])
        self.assertIn("last_profile", str(ctx.exception))

    def test_rename_and_duplicate_name_rejected(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        service = self._service(workspace)
        a = service.create_translation_ai_profile(workspace.id, name="Alpha")
        service.create_translation_ai_profile(workspace.id, name="Beta")
        service.rename_translation_ai_profile(workspace.id, a["id"], name="Alpha2")
        renamed = next(
            p for p in workspace.settings_json[TRANSLATION_AI_KEY]["profiles"] if p["id"] == a["id"]
        )
        self.assertEqual(renamed["name"], "Alpha2")
        with self.assertRaises(ValueError) as ctx:
            service.create_translation_ai_profile(workspace.id, name=" beta ")
        self.assertIn("duplicate_name", str(ctx.exception))


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


class TranslationAiModelsProfileResolveTests(unittest.TestCase):
    def test_resolve_saved_uses_editing_profile_not_active(self) -> None:
        """List-models must read the editing setup's stored key when api_key is omitted."""
        from src.api.routes.operations import _resolve_translation_ai_saved

        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_translation_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "api_key": "active-key-aaaa",
                "base_url": "",
                "timeout_seconds": 30,
                "fallback_provider": "none",
                "fallback_model": "",
            },
        )
        created = service.create_translation_ai_profile(workspace.id, name="Draft")
        draft_id = str(created.get("id") or "")
        service.set_translation_ai_profile(
            workspace.id,
            draft_id,
            {
                "enabled": False,
                "provider": "openai_compatible",
                "model": "gpt-4o-mini",
                "api_key": "draft-key-bbbb",
                "base_url": "https://api.example.com/v1",
                "timeout_seconds": 45,
                "fallback_provider": "none",
                "fallback_model": "",
            },
        )

        active = _resolve_translation_ai_saved(service, workspace.id, None, "translation_ai")
        draft = _resolve_translation_ai_saved(service, workspace.id, draft_id, "translation_ai")
        self.assertEqual(active.api_key, "active-key-aaaa")
        self.assertEqual(draft.api_key, "draft-key-bbbb")
        self.assertEqual(draft.provider, "openai_compatible")
        self.assertEqual(draft.base_url, "https://api.example.com/v1")


if __name__ == "__main__":
    unittest.main()
