"""Caption AI workspace settings must not overwrite dialogue Translation settings."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.services.workspace_settings_service import (
    CAPTION_AI_KEY,
    CAPTION_PROMPT_KEY,
    TRANSLATION_AI_KEY,
    TRANSLATION_USER_PROMPT_KEY,
    WorkspaceSettingsService,
)


def _active_profile(workspace: SimpleNamespace, key: str) -> dict:
    store = workspace.settings_json[key]
    active_id = store["active_profile_id"]
    return next(p for p in store["profiles"] if p["id"] == active_id)


class WorkspaceCaptionAiIsolationTests(unittest.TestCase):
    def test_set_caption_ai_does_not_touch_translation_ai(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={
                TRANSLATION_AI_KEY: {
                    "enabled": True,
                    "provider": "openai_compatible",
                    "model": "gpt-3.5",
                    "api_key": "sk-dialogue-keep",
                    "base_url": "https://hhtechapi.com/v1",
                    "timeout_seconds": 90,
                    "fallback_provider": "none",
                    "fallback_model": "",
                },
                TRANSLATION_USER_PROMPT_KEY: "Dialogue prompt KEEP",
            },
        )
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)

        service.set_caption_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "openai_compatible",
                "model": "gpt-4o-mini",
                "api_key": "sk-caption-new",
                "base_url": "https://caption.example/v1",
                "timeout_seconds": 60,
                "fallback_provider": "none",
                "fallback_model": "",
            },
        )
        service.set_caption_prompt(workspace.id, "Caption prompt NEW")

        # Flat translation blob is untouched until read/migrate; caption is multi-profile.
        self.assertEqual(workspace.settings_json[TRANSLATION_AI_KEY]["api_key"], "sk-dialogue-keep")
        self.assertEqual(workspace.settings_json[TRANSLATION_AI_KEY]["model"], "gpt-3.5")
        self.assertEqual(workspace.settings_json[TRANSLATION_USER_PROMPT_KEY], "Dialogue prompt KEEP")
        caption_active = _active_profile(workspace, CAPTION_AI_KEY)
        self.assertEqual(caption_active["api_key"], "sk-caption-new")
        self.assertEqual(caption_active["model"], "gpt-4o-mini")
        caption_prompt_active = _active_profile(workspace, CAPTION_PROMPT_KEY)
        self.assertEqual(caption_prompt_active["prompt"], "Caption prompt NEW")
        self.assertEqual(service.get_caption_prompt(workspace.id), "Caption prompt NEW")

        dialogue = service.get_translation_ai(workspace.id)
        caption = service.get_caption_ai(workspace.id)
        self.assertEqual(dialogue.api_key, "sk-dialogue-keep")
        self.assertEqual(caption.api_key, "sk-caption-new")


class CaptionAiProfileLifecycleTests(unittest.TestCase):
    def test_legacy_flat_migrates_on_get_public(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={
                CAPTION_AI_KEY: {
                    "enabled": True,
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
                    "api_key": "sk-cap",
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
        public = service.get_caption_ai_public(workspace.id)
        self.assertEqual(len(public["profiles"]), 1)
        self.assertEqual(public["profiles"][0]["name"], "Default")
        self.assertEqual(public["provider"], "gemini")
        self.assertEqual(public["api_key"], "sk-cap")
        self.assertEqual(public["profiles"][0]["api_key"], "sk-cap")

    def test_create_caption_does_not_touch_translation_store(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={
                TRANSLATION_AI_KEY: {
                    "enabled": True,
                    "provider": "ollama",
                    "model": "qwen",
                    "api_key": "",
                    "base_url": "http://127.0.0.1:11434",
                    "timeout_seconds": 90,
                    "fallback_provider": "none",
                    "fallback_model": "",
                }
            },
        )
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        before = dict(workspace.settings_json[TRANSLATION_AI_KEY])
        service.create_caption_ai_profile(workspace.id, name="Caption A")
        self.assertEqual(workspace.settings_json[TRANSLATION_AI_KEY], before)
        self.assertIn(CAPTION_AI_KEY, workspace.settings_json)
        self.assertEqual(len(workspace.settings_json[CAPTION_AI_KEY]["profiles"]), 2)

    def test_delete_last_caption_profile_fails(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_caption_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "gemini",
                "model": "flash",
                "api_key": "sk-x",
                "base_url": "",
                "timeout_seconds": 90,
                "fallback_provider": "none",
                "fallback_model": "",
            },
        )
        only_id = _active_profile(workspace, CAPTION_AI_KEY)["id"]
        with self.assertRaises(ValueError) as ctx:
            service.delete_caption_ai_profile(workspace.id, only_id)
        self.assertIn("last_profile", str(ctx.exception))

    def test_activate_switches_get_caption_ai(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_caption_ai(
            workspace.id,
            {
                "enabled": True,
                "provider": "gemini",
                "model": "flash",
                "api_key": "sk-a",
                "base_url": "",
                "timeout_seconds": 90,
                "fallback_provider": "none",
                "fallback_model": "",
            },
        )
        created = service.create_caption_ai_profile(workspace.id, name="B")
        service.set_caption_ai_profile(
            workspace.id,
            str(created["id"]),
            {
                "enabled": True,
                "provider": "openai_compatible",
                "model": "gpt",
                "api_key": "sk-b",
                "base_url": "https://x/v1",
                "timeout_seconds": 60,
                "fallback_provider": "none",
                "fallback_model": "",
            },
        )
        service.activate_caption_ai_profile(workspace.id, str(created["id"]))
        cfg = service.get_caption_ai(workspace.id)
        self.assertEqual(cfg.provider, "openai_compatible")
        self.assertEqual(cfg.api_key, "sk-b")


if __name__ == "__main__":
    unittest.main()
