"""Translator settings resolve from Ops Caption AI settings (not Translation settings)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.media_pipeline.translator.config import (
    DEFAULT_TRANSLATION_SYSTEM_PROMPT,
    TranslatorSettings,
)
from src.media_pipeline.translator.resolve import resolve_translator_settings
from src.services.workspace_settings_service import TranslationAiConfig


class ResolveFromCaptionAiTests(unittest.TestCase):
    def test_uses_caption_ai_and_prompt_when_enabled(self) -> None:
        db = MagicMock()
        workspace_id = uuid4()
        ai = TranslationAiConfig(
            enabled=True,
            provider="openai_compatible",
            model="gpt-3.5",
            api_key="sk-caption",
            base_url="https://hhtechapi.com/v1",
            timeout_seconds=90.0,
        )
        with patch(
            "src.media_pipeline.translator.resolve.WorkspaceSettingsService"
        ) as svc_cls:
            svc = svc_cls.return_value
            svc.get_caption_ai.return_value = ai
            svc.get_caption_prompt.return_value = "Prompt Caption AI"
            settings = resolve_translator_settings(db=db, workspace_id=workspace_id)
            svc.get_translation_ai.assert_not_called()
            svc.get_translation_user_prompt.assert_not_called()

        self.assertEqual(settings.api_key, "sk-caption")
        self.assertEqual(settings.base_url, "https://hhtechapi.com/v1")
        self.assertEqual(settings.model_name, "gpt-3.5")
        self.assertEqual(settings.system_prompt, "Prompt Caption AI")
        self.assertEqual(settings.source, "workspace_db")

    def test_falls_back_to_default_prompt_when_caption_prompt_empty(self) -> None:
        db = MagicMock()
        ai = TranslationAiConfig(
            enabled=True,
            provider="openai_compatible",
            model="m",
            api_key="k",
            base_url="https://example.com/v1",
        )
        with patch(
            "src.media_pipeline.translator.resolve.WorkspaceSettingsService"
        ) as svc_cls:
            svc = svc_cls.return_value
            svc.get_caption_ai.return_value = ai
            svc.get_caption_prompt.return_value = None
            settings = resolve_translator_settings(db=db, workspace_id=None)

        self.assertEqual(settings.system_prompt, DEFAULT_TRANSLATION_SYSTEM_PROMPT)

    def test_env_fallback_when_caption_override_disabled(self) -> None:
        db = MagicMock()
        ai = TranslationAiConfig(enabled=False, provider="openai_compatible")
        with patch(
            "src.media_pipeline.translator.resolve.WorkspaceSettingsService"
        ) as svc_cls:
            svc = svc_cls.return_value
            svc.get_caption_ai.return_value = ai
            svc.get_caption_prompt.return_value = None
            with patch(
                "src.media_pipeline.translator.resolve.load_translator_settings",
                return_value=TranslatorSettings(
                    api_key="sk-env",
                    base_url="https://api.openai.com/v1",
                    model_name="gpt-4o-mini",
                    system_prompt="env prompt",
                    source="env",
                ),
            ) as load_env:
                settings = resolve_translator_settings(db=db, workspace_id=None)
                load_env.assert_called_once()
        self.assertEqual(settings.source, "env")
        self.assertEqual(settings.api_key, "sk-env")


if __name__ == "__main__":
    unittest.main()
