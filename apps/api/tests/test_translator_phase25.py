"""Phase 2.5 caption translator: env-driven OpenAI-compatible LLM (mocked unit tests)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.media_pipeline.translator.config import (
    DEFAULT_TRANSLATION_SYSTEM_PROMPT,
    TranslatorSettings,
    load_translator_settings,
)
from src.media_pipeline.translator.normalize import flatten_ocr_chinese
from src.media_pipeline.translator.service import translate_subtitles


class NormalizeTests(unittest.TestCase):
    def test_flatten_phase2_payload_one_key_per_box(self) -> None:
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
        self.assertEqual(flat["0#0"], "你好")
        self.assertEqual(flat["0#1"], "世界")
        self.assertEqual(flat["1000#0"], "硬字幕")
        # Convenience alias for first box on a timestamp.
        self.assertEqual(flat["0"], "你好")
        self.assertEqual(flat["1000"], "硬字幕")

    def test_flatten_keeps_timestamp_map(self) -> None:
        flat = flatten_ocr_chinese({0: "甲", "1000": "乙"})
        self.assertEqual(flat["0"], "甲")
        self.assertEqual(flat["1000"], "乙")

    def test_unique_chinese_texts_preserves_order(self) -> None:
        from src.media_pipeline.translator.normalize import unique_chinese_texts

        tracking = {
            "1600#0": "加盐",
            "1633#0": "加盐",
            "2000#0": "西兰花",
            "2000": "西兰花",
        }
        self.assertEqual(unique_chinese_texts(tracking), ["加盐", "西兰花"])


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
        # LLM is keyed by opaque ids u0..uN over unique ZH.
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {"u0": "Xin chao", "u1": "Phu de dich"},
                        ensure_ascii=False,
                    )
                )
            )
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict("os.environ", {"TRANSLATE_LLM_DRY": ""}, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
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
                    result = translate_subtitles(
                        {0: "你好", 1000: "硬字幕"},
                        settings=settings,
                        memory_path=Path(tmp) / "mem.json",
                    )

        self.assertEqual(result, {"0": "Xin chao", "1000": "Phu de dich"})
        self.assertEqual(mock_client.chat.completions.create.call_count, 1)
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-4o-mini")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(kwargs["temperature"], 0)
        user_content = kwargs["messages"][1]["content"]
        self.assertIn("你好", user_content)
        self.assertIn("硬字幕", user_content)

    def test_dedupes_repeated_zh_before_llm_then_broadcasts(self) -> None:
        """Same ZH stamped on many frames → one LLM entry, many vi_texts keys."""
        payload = {
            "frames": [
                {"time_ms": 1600, "boxes": [{"text": "加盐", "translate_ready": True}]},
                {"time_ms": 1633, "boxes": [{"text": "加盐", "translate_ready": True}]},
                {"time_ms": 1666, "boxes": [{"text": "加盐", "translate_ready": True}]},
                {
                    "time_ms": 2000,
                    "boxes": [{"text": "西兰花", "translate_ready": True}],
                },
            ]
        }
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {"u0": "Thêm muối", "u1": "Bông cải xanh"},
                        ensure_ascii=False,
                    )
                )
            )
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        settings = TranslatorSettings(
            api_key="sk-test",
            base_url="https://example.test/v1",
            model_name="gpt-4o-mini",
            system_prompt=DEFAULT_TRANSLATION_SYSTEM_PROMPT,
            source="env",
        )
        with patch.dict("os.environ", {"TRANSLATE_LLM_DRY": ""}, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                with patch(
                    "src.media_pipeline.translator.service.build_openai_client",
                    return_value=mock_client,
                ):
                    result = translate_subtitles(
                        payload,
                        settings=settings,
                        memory_path=Path(tmp) / "mem.json",
                    )

        self.assertEqual(result["1600#0"], "Thêm muối")
        self.assertEqual(result["1633#0"], "Thêm muối")
        self.assertEqual(result["1666#0"], "Thêm muối")
        self.assertEqual(result["2000#0"], "Bông cải xanh")
        user_content = mock_client.chat.completions.create.call_args.kwargs[
            "messages"
        ][1]["content"]
        body = user_content.split("\n\n", 1)[-1]
        sent = json.loads(body)
        self.assertEqual(len(sent), 2)
        self.assertEqual(set(sent.keys()), {"u0", "u1"})
        self.assertEqual(set(sent.values()), {"加盐", "西兰花"})


if __name__ == "__main__":
    unittest.main()
