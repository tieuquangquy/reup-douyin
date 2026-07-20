"""Workspace DB-backed caption prompt multi-profile store."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.services.workspace_settings_service import (
    CAPTION_PROMPT_KEY,
    TRANSLATION_USER_PROMPT_KEY,
    WorkspaceSettingsService,
)


def _active_profile(workspace: SimpleNamespace, key: str) -> dict:
    store = workspace.settings_json[key]
    active_id = store["active_profile_id"]
    return next(p for p in store["profiles"] if p["id"] == active_id)


class WorkspaceCaptionPromptTests(unittest.TestCase):
    def test_get_returns_none_when_unset(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json=None)
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        self.assertIsNone(service.get_caption_prompt(workspace.id))

    def test_set_and_get_round_trip(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={"other": 1})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        saved = service.set_caption_prompt(workspace.id, "  CAPTION_PROMPT  ")
        self.assertEqual(saved, "CAPTION_PROMPT")
        active = _active_profile(workspace, CAPTION_PROMPT_KEY)
        self.assertEqual(active["prompt"], "CAPTION_PROMPT")
        self.assertEqual(service.get_caption_prompt(workspace.id), "CAPTION_PROMPT")

    def test_clear_empty_returns_none(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={CAPTION_PROMPT_KEY: "OLD"})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_caption_prompt(workspace.id, "   ")
        self.assertIsNone(service.get_caption_prompt(workspace.id))


class CaptionPromptProfileLifecycleTests(unittest.TestCase):
    def test_legacy_string_migrates_on_get_public(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(), settings_json={CAPTION_PROMPT_KEY: "  LEGACY  "}
        )
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        public = service.get_caption_prompt_public(workspace.id)
        self.assertEqual(len(public["profiles"]), 1)
        self.assertEqual(public["profiles"][0]["name"], "Default")
        self.assertEqual(public["prompt"], "LEGACY")

    def test_create_second_does_not_change_active(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_caption_prompt(workspace.id, "PRIMARY")
        first_active_id = workspace.settings_json[CAPTION_PROMPT_KEY]["active_profile_id"]
        service.create_caption_prompt_profile(workspace.id, name="Alt")
        self.assertEqual(
            workspace.settings_json[CAPTION_PROMPT_KEY]["active_profile_id"], first_active_id
        )
        self.assertEqual(service.get_caption_prompt(workspace.id), "PRIMARY")

    def test_activate_switches_get_caption_prompt(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_caption_prompt(workspace.id, "PRIMARY")
        created = service.create_caption_prompt_profile(workspace.id, name="Alt")
        service.set_caption_prompt_profile(
            workspace.id, str(created["id"]), prompt="ALT_CAPTION"
        )
        service.activate_caption_prompt_profile(workspace.id, str(created["id"]))
        self.assertEqual(service.get_caption_prompt(workspace.id), "ALT_CAPTION")

    def test_delete_last_profile_fails(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_caption_prompt(workspace.id, "ONLY")
        only_id = _active_profile(workspace, CAPTION_PROMPT_KEY)["id"]
        with self.assertRaises(ValueError) as ctx:
            service.delete_caption_prompt_profile(workspace.id, only_id)
        self.assertIn("last_profile", str(ctx.exception))

    def test_translation_prompt_create_does_not_touch_caption_key(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(), settings_json={CAPTION_PROMPT_KEY: "CAPTION STAYS"}
        )
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        before = workspace.settings_json[CAPTION_PROMPT_KEY]
        service.create_translation_prompt_profile(workspace.id, name="Dialogue A")
        self.assertEqual(workspace.settings_json[CAPTION_PROMPT_KEY], before)
        self.assertNotIn(TRANSLATION_USER_PROMPT_KEY, before if isinstance(before, dict) else {})
        self.assertEqual(service.get_caption_prompt(workspace.id), "CAPTION STAYS")


if __name__ == "__main__":
    unittest.main()
