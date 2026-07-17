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
        self.assertEqual(workspace.settings_json[TRANSLATION_USER_PROMPT_KEY], "MY_DB_PROMPT")
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
        self.assertNotIn(TRANSLATION_USER_PROMPT_KEY, workspace.settings_json)
        self.assertTrue(workspace.settings_json["keep"])

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
