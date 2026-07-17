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

        self.assertEqual(workspace.settings_json[TRANSLATION_AI_KEY]["api_key"], "sk-dialogue-keep")
        self.assertEqual(workspace.settings_json[TRANSLATION_AI_KEY]["model"], "gpt-3.5")
        self.assertEqual(workspace.settings_json[TRANSLATION_USER_PROMPT_KEY], "Dialogue prompt KEEP")
        self.assertEqual(workspace.settings_json[CAPTION_AI_KEY]["api_key"], "sk-caption-new")
        self.assertEqual(workspace.settings_json[CAPTION_AI_KEY]["model"], "gpt-4o-mini")
        self.assertEqual(workspace.settings_json[CAPTION_PROMPT_KEY], "Caption prompt NEW")

        dialogue = service.get_translation_ai(workspace.id)
        caption = service.get_caption_ai(workspace.id)
        self.assertEqual(dialogue.api_key, "sk-dialogue-keep")
        self.assertEqual(caption.api_key, "sk-caption-new")


if __name__ == "__main__":
    unittest.main()
