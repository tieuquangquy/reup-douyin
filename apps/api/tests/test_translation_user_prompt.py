"""Operator-owned dialogue translation prompt constant (env/file + append source)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.audio_pipeline.translation_llm import (
    DurationConstrainedTranslationProvider,
    FixedLlmClient,
    _build_cjk_repair_prompt,
    _build_shorten_prompt,
    _build_translate_prompt,
    resolve_translation_user_prompt,
)
from src.audio_pipeline.types import TranslationPreset


class TranslationUserPromptTests(unittest.TestCase):
    def test_custom_user_prompt_appends_chinese_source(self) -> None:
        prompt = _build_translate_prompt(
            "你好",
            TranslationPreset.LITERAL_SAFE,
            2.0,
            user_prompt="RULES_HERE\nTranslate faithfully.",
        )
        self.assertTrue(prompt.startswith("RULES_HERE\nTranslate faithfully."))
        self.assertIn("Chinese source:\n你好", prompt)
        self.assertTrue(prompt.endswith("你好"))
        self.assertNotIn("literal_safe", prompt.lower())

    def test_builtin_prompt_when_user_prompt_empty(self) -> None:
        prompt = _build_translate_prompt(
            "今天吃什么",
            TranslationPreset.LITERAL_SAFE,
            2.0,
            user_prompt="   ",
        )
        self.assertIn("literal_safe", prompt.lower())
        self.assertIn("chinese source", prompt.lower())

    def test_shorten_prompt_leads_with_operator_translation_prompt(self) -> None:
        prompt = _build_shorten_prompt(
            "这是一段中文",
            "Đây là một bản dịch tiếng Việt rất dài",
            TranslationPreset.LITERAL_SAFE,
            1.2,
            user_prompt='End every Vietnamese line with " OK".',
        )
        self.assertTrue(prompt.startswith('End every Vietnamese line with " OK".'))
        self.assertIn("Current Vietnamese (too long):", prompt)
        self.assertNotIn("Do not add meaning that is not in the Chinese source", prompt)

    def test_cjk_repair_prompt_leads_with_operator_translation_prompt(self) -> None:
        prompt = _build_cjk_repair_prompt(
            "减脂餐很简单",
            "Bữa giảm mỡ 很简单 OK",
            user_prompt='Keep trailing " OK" on every line.',
        )
        self.assertTrue(prompt.startswith('Keep trailing " OK" on every line.'))
        self.assertIn("Dirty Vietnamese:", prompt)
        self.assertNotIn("Do not add meaning that is not in the Chinese source", prompt)

    def test_rewrite_round_sends_operator_prompt_to_llm(self) -> None:
        """Duration rewrite must re-send workspace Translation prompt (not only builtin shorten)."""

        class RecordingClient(FixedLlmClient):
            def __init__(self) -> None:
                super().__init__(
                    responses=[
                        "Đây là một bản dịch tiếng Việt rất dài khiến TTS chắc chắn vượt ngân sách thời lượng của phân đoạn gốc OK",
                        "Bản dịch ngắn OK",
                    ]
                )
                self.prompts: list[str] = []

            def complete(self, prompt: str) -> str:
                self.prompts.append(prompt)
                return super().complete(prompt)

        client = RecordingClient()
        provider = DurationConstrainedTranslationProvider(
            primary=client,
            max_rewrite_rounds=2,
            user_prompt='Append " OK" after every Vietnamese line.',
            machine_translate=lambda _src: "MT IGNORE",
        )
        result = provider.translate(
            "这是一段中文",
            preset=TranslationPreset.NATURAL_VIRAL,
            duration_budget_seconds=1.2,
            source_confidence=0.9,
        )
        self.assertEqual(result.translated_text, "Bản dịch ngắn OK")
        self.assertGreaterEqual(len(client.prompts), 2)
        shorten_prompt = client.prompts[1]
        self.assertIn('Append " OK" after every Vietnamese line.', shorten_prompt)
        self.assertIn("workspace_translation_prompt", result.quality_flags)

    def test_resolve_prefers_file_over_inline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "user.txt"
            path.write_text("FROM_FILE_PROMPT\nBe natural.\n", encoding="utf-8")
            resolved = resolve_translation_user_prompt(
                inline="FROM_INLINE",
                file_path=str(path),
            )
            self.assertEqual(resolved, "FROM_FILE_PROMPT\nBe natural.")

    def test_resolve_file_comment_only_is_unset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.txt"
            path.write_text("# Paste prompt below\n\n# still empty\n", encoding="utf-8")
            resolved = resolve_translation_user_prompt(inline=None, file_path=str(path))
            self.assertIsNone(resolved)

    def test_resolve_inline_when_no_file(self) -> None:
        resolved = resolve_translation_user_prompt(inline="  INLINE_RULES  ", file_path=None)
        self.assertEqual(resolved, "INLINE_RULES")

    def test_resolve_relative_file_from_api_prompts_dir(self) -> None:
        """Worker cwd may not be apps/api; relative path still finds apps/api/prompts/."""
        with tempfile.TemporaryDirectory() as tmp:
            resolved = resolve_translation_user_prompt(
                inline=None,
                file_path="prompts/translation_user.txt",
                base_dir=Path(tmp),  # empty cwd stand-in — must fall through to api root
            )
            # Sample file ships comment-only → treated as unset
            self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
