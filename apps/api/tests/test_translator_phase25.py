"""Phase 2.5 caption translator: env-driven OpenAI-compatible LLM (mocked unit tests)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from src.media_pipeline.translator.config import (
    DEFAULT_TRANSLATION_SYSTEM_PROMPT,
    TranslatorSettings,
    load_translator_settings,
)
from src.media_pipeline.translator.normalize import flatten_ocr_chinese
from src.media_pipeline.translator.service import translate_subtitles


class NormalizeTests(unittest.TestCase):
    def test_flatten_phase2_payload_joins_boxes(self) -> None:
        payload = {
            "frames": [
                {
                    "time_ms": 0,
                    "boxes": [{"text": "你好"}, {"text": "世界"}],
                },
                {"time_ms": 1000, "boxes": [{"text": "硬字幕"}]},
            ]
        }
        flat = flatten_ocr_chinese(payload)
        self.assertEqual(flat["0"], "你好 世界")
        self.assertEqual(flat["1000"], "硬字幕")

    def test_flatten_keeps_timestamp_map(self) -> None:
        flat = flatten_ocr_chinese({0: "甲", "1000": "乙"})
        self.assertEqual(flat["0"], "甲")
        self.assertEqual(flat["1000"], "乙")


class ConfigTests(unittest.TestCase):
    def test_default_system_prompt_when_env_empty(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "LLM_API_KEY": "sk-test",
                "LLM_BASE_URL": "https://example.test/v1",
                "LLM_MODEL_NAME": "gpt-4o-mini",
                "TRANSLATION_SYSTEM_PROMPT": "",
            },
            clear=False,
        ):
            settings = load_translator_settings()
        self.assertEqual(settings.system_prompt, DEFAULT_TRANSLATION_SYSTEM_PROMPT)
        self.assertIn("JSON", settings.system_prompt)


class TranslateSubtitlesTests(unittest.TestCase):
    def test_batches_one_request_and_maps_vietnamese_json(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {"0": "Xin chao", "1000": "Phu de dich"},
                        ensure_ascii=False,
                    )
                )
            )
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch(
            "src.media_pipeline.translator.service.build_openai_client",
            return_value=mock_client,
        ):
            settings = TranslatorSettings(
                api_key="sk-test",
                base_url="https://example.test/v1",
                model_name="gpt-4o-mini",
                system_prompt=DEFAULT_TRANSLATION_SYSTEM_PROMPT,
                source="workspace_db",
            )
            result = translate_subtitles({0: "你好", 1000: "硬字幕"}, settings=settings)

        self.assertEqual(result, {"0": "Xin chao", "1000": "Phu de dich"})
        self.assertEqual(mock_client.chat.completions.create.call_count, 1)
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-4o-mini")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        user_content = kwargs["messages"][1]["content"]
        self.assertIn("你好", user_content)
        self.assertIn("硬字幕", user_content)


if __name__ == "__main__":
    unittest.main()
