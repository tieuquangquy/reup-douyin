"""Workspace DB-backed dialogue translation prompt setting."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.audio_pipeline.services.translation_draft_builder import TranslationDraftBuilder
from src.audio_pipeline.translation_llm import DurationConstrainedTranslationProvider
from src.audio_pipeline.types import TranscriptDraftSegment, TranslationPreset
from src.services.workspace_settings_service import (
    TRANSLATION_USER_PROMPT_KEY,
    WorkspaceSettingsService,
)


def _active_profile(workspace: SimpleNamespace, key: str) -> dict:
    store = workspace.settings_json[key]
    active_id = store["active_profile_id"]
    return next(p for p in store["profiles"] if p["id"] == active_id)


class WorkspaceTranslationPromptTests(unittest.TestCase):
    def test_get_returns_none_when_unset(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json=None)
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        self.assertIsNone(service.get_translation_user_prompt(workspace.id))

    def test_set_and_get_round_trip(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={"other": 1})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        saved = service.set_translation_user_prompt(workspace.id, "  MY_DB_PROMPT  ")
        self.assertEqual(saved, "MY_DB_PROMPT")
        active = _active_profile(workspace, TRANSLATION_USER_PROMPT_KEY)
        self.assertEqual(active["prompt"], "MY_DB_PROMPT")
        self.assertEqual(workspace.settings_json["other"], 1)
        db.commit.assert_called()
        self.assertEqual(service.get_translation_user_prompt(workspace.id), "MY_DB_PROMPT")

    def test_clear_with_empty_string(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={TRANSLATION_USER_PROMPT_KEY: "old", "keep": True},
        )
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_translation_user_prompt(workspace.id, "  ")
        # Store is present but active profile prompt is empty; get returns None.
        self.assertIsNone(service.get_translation_user_prompt(workspace.id))
        active = _active_profile(workspace, TRANSLATION_USER_PROMPT_KEY)
        self.assertEqual(active["prompt"], "")
        self.assertTrue(workspace.settings_json["keep"])


class TranslationPromptProfileLifecycleTests(unittest.TestCase):
    def test_legacy_string_migrates_on_get_public(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={TRANSLATION_USER_PROMPT_KEY: "  LEGACY PROMPT  "},
        )
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        public = service.get_translation_prompt_public(workspace.id)
        self.assertEqual(len(public["profiles"]), 1)
        self.assertEqual(public["profiles"][0]["name"], "Default")
        self.assertEqual(public["profiles"][0]["id"], "default")
        # Migration preserves stripped legacy text.
        self.assertEqual(public["profiles"][0]["prompt"], "LEGACY PROMPT")
        self.assertEqual(public["prompt"], "LEGACY PROMPT")
        self.assertEqual(public["active_profile_id"], "default")
        # And get_translation_user_prompt still returns stripped legacy.
        self.assertEqual(service.get_translation_user_prompt(workspace.id), "LEGACY PROMPT")

    def test_empty_missing_yields_single_blank_default_profile(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json=None)
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        public = service.get_translation_prompt_public(workspace.id)
        self.assertEqual(len(public["profiles"]), 1)
        self.assertEqual(public["profiles"][0]["name"], "Default")
        self.assertEqual(public["prompt"], "")
        self.assertEqual(public["source"], "empty")

    def test_create_second_does_not_change_active(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_translation_user_prompt(workspace.id, "PRIMARY")
        first_active_id = workspace.settings_json[TRANSLATION_USER_PROMPT_KEY]["active_profile_id"]
        created = service.create_translation_prompt_profile(workspace.id, name="Alt")
        self.assertNotEqual(created["id"], first_active_id)
        self.assertEqual(
            workspace.settings_json[TRANSLATION_USER_PROMPT_KEY]["active_profile_id"],
            first_active_id,
        )
        # Active still returns primary.
        self.assertEqual(service.get_translation_user_prompt(workspace.id), "PRIMARY")

    def test_put_profile_route_returns_saved_profile_prompt_authority(self) -> None:
        """PUT/PATCH /profiles/{id} must return that profile's prompt, not the active list prompt."""
        from pathlib import Path
        import re

        source = (Path(__file__).resolve().parents[1] / "src" / "api" / "routes" / "operations.py").read_text(
            encoding="utf-8"
        )
        for fn_name, profile_getter, list_getter in (
            (
                "put_translation_prompt_profile",
                "get_translation_prompt_profile_public",
                "get_translation_prompt_public",
            ),
            (
                "patch_translation_prompt_profile",
                "get_translation_prompt_profile_public",
                "get_translation_prompt_public",
            ),
            (
                "put_caption_prompt_profile",
                "get_caption_prompt_profile_public",
                "get_caption_prompt_public",
            ),
            (
                "patch_caption_prompt_profile",
                "get_caption_prompt_profile_public",
                "get_caption_prompt_public",
            ),
        ):
            match = re.search(rf"def {fn_name}\([\s\S]*?\n\n@router\.", source)
            self.assertIsNotNone(match, f"{fn_name} must exist")
            body = match.group(0)
            self.assertIn(profile_getter, body, f"{fn_name} must return {profile_getter}")
            self.assertNotIn(
                f"public = service.{list_getter}",
                body,
                f"{fn_name} must not return active-only {list_getter} after Save",
            )

    def test_set_non_active_profile_public_returns_that_prompt_not_active(self) -> None:
        """Ops Save of a new draft must read back that setup's prompt, not the active row."""
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_translation_user_prompt(workspace.id, "PRIMARY STAYS")
        created = service.create_translation_prompt_profile(workspace.id, name="Alt")
        alt_id = str(created["id"])
        service.set_translation_prompt_profile(workspace.id, alt_id, prompt="ALT DRAFT TEXT")
        focused = service.get_translation_prompt_profile_public(workspace.id, alt_id)
        active = service.get_translation_prompt_public(workspace.id)
        self.assertEqual(focused["prompt"], "ALT DRAFT TEXT")
        self.assertEqual(focused["focus_profile_id"], alt_id)
        self.assertEqual(active["prompt"], "PRIMARY STAYS")
        self.assertNotEqual(active["active_profile_id"], alt_id)

    def test_activate_switches_get_translation_user_prompt(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_translation_user_prompt(workspace.id, "PRIMARY")
        created = service.create_translation_prompt_profile(workspace.id, name="Alt")
        service.set_translation_prompt_profile(
            workspace.id, str(created["id"]), prompt="ALT PROMPT"
        )
        service.activate_translation_prompt_profile(workspace.id, str(created["id"]))
        self.assertEqual(service.get_translation_user_prompt(workspace.id), "ALT PROMPT")

    def test_delete_last_profile_fails(self) -> None:
        workspace = SimpleNamespace(id=uuid4(), settings_json={})
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        service.set_translation_user_prompt(workspace.id, "ONLY")
        only_id = _active_profile(workspace, TRANSLATION_USER_PROMPT_KEY)["id"]
        with self.assertRaises(ValueError) as ctx:
            service.delete_translation_prompt_profile(workspace.id, only_id)
        self.assertIn("last_profile", str(ctx.exception))

    def test_caption_profile_create_does_not_touch_translation_key(self) -> None:
        workspace = SimpleNamespace(
            id=uuid4(),
            settings_json={TRANSLATION_USER_PROMPT_KEY: "DIALOGUE STAYS"},
        )
        db = MagicMock()
        db.get.return_value = workspace
        service = WorkspaceSettingsService(db)
        before = workspace.settings_json[TRANSLATION_USER_PROMPT_KEY]
        service.create_caption_prompt_profile(workspace.id, name="Caption A")
        self.assertEqual(workspace.settings_json[TRANSLATION_USER_PROMPT_KEY], before)
        self.assertEqual(service.get_translation_user_prompt(workspace.id), "DIALOGUE STAYS")

    def test_builder_uses_db_user_prompt_over_builtin(self) -> None:
        captured: list[str] = []

        class CaptureClient:
            provider_name = "fixed_llm"

            def complete(self, prompt: str) -> str:
                captured.append(prompt)
                return "Ban dich tu DB prompt"

        provider = DurationConstrainedTranslationProvider(
            primary=CaptureClient(),
            max_rewrite_rounds=0,
            machine_translate=lambda _s: "MT",
        )
        builder = TranslationDraftBuilder(provider)
        drafts = [
            TranscriptDraftSegment(
                segment_index=0,
                start_seconds=0.0,
                end_seconds=2.0,
                source_text="你好",
                normalized_source_text="你好",
                confidence=0.9,
                speaker_label=None,
                difficulty_flags=[],
            )
        ]
        rows = builder.build(
            drafts,
            preset=TranslationPreset.LITERAL_SAFE,
            user_prompt="RULES_FROM_DB",
        )
        self.assertEqual(rows[0].translated_text, "Ban dich tu DB prompt")
        self.assertEqual(len(captured), 1)
        self.assertTrue(captured[0].startswith("RULES_FROM_DB"))
        self.assertIn("Chinese source:\n你好", captured[0])
        self.assertNotIn("literal_safe", captured[0].lower())


if __name__ == "__main__":
    unittest.main()
