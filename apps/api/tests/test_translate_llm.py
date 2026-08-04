"""ContextualTranslator (Step 3): flatten + LLM batch + fail-safe remap."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from src.media_pipeline.translator.config import (
    DEFAULT_TRANSLATION_SYSTEM_PROMPT,
    TranslatorSettings,
)
from src.media_pipeline.translator.translate_llm import ContextualTranslator


def _settings() -> TranslatorSettings:
    return TranslatorSettings(
        api_key="sk-test",
        base_url="https://example.test/v1",
        model_name="gemini-1.5-flash",
        system_prompt=DEFAULT_TRANSLATION_SYSTEM_PROMPT,
        source="workspace_db",
    )


class AssignIdsTests(unittest.TestCase):
    def test_flatten_step2_grouped_assigns_box_ids(self) -> None:
        step2 = {
            "00:01.000": [
                {"text": "减脂餐", "box": [1, 2, 3, 2, 3, 4, 1, 4]},
                {"text": "加盐", "box": [10, 20, 30, 20, 30, 40, 10, 40]},
            ],
            "00:27.500": [{"text": "52克", "box": [5, 6, 7, 6, 7, 8, 5, 8]}],
        }
        items = ContextualTranslator.assign_ids(step2)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["id"], "box_0")
        self.assertEqual(items[0]["text"], "减脂餐")
        self.assertEqual(items[0]["timestamp"], "00:01.000")
        self.assertEqual(items[0]["original_box_coords"], [1, 2, 3, 2, 3, 4, 1, 4])
        self.assertEqual(items[2]["id"], "box_2")
        self.assertEqual(items[2]["text"], "52克")


class FailSafeMappingTests(unittest.TestCase):
    def test_missing_id_fills_ellipsis_and_remaps(self) -> None:
        step2 = {
            "00:01.000": [
                {"text": "减脂餐", "box": [1.0, 2.0, 3.0, 2.0, 3.0, 4.0, 1.0, 4.0]},
                {"text": "加盐", "box": [10.0, 20.0, 30.0, 20.0, 30.0, 40.0, 10.0, 40.0]},
            ]
        }
        translator = ContextualTranslator(settings=_settings(), client=MagicMock())
        # LLM only returns one of two ids.
        llm_payload = {
            "translations": [
                {"id": "box_0", "vietnamese_text": "Bữa giảm béo"},
            ]
        }
        with patch.object(
            translator,
            "_chat_json",
            return_value=llm_payload,
        ):
            nested = translator.translate_step2_sync(step2)

        self.assertEqual(len(nested["00:01.000"]), 2)
        self.assertEqual(nested["00:01.000"][0]["original_text"], "减脂餐")
        self.assertEqual(nested["00:01.000"][0]["vietnamese_text"], "Bữa giảm béo")
        self.assertEqual(nested["00:01.000"][1]["vietnamese_text"], "...")
        self.assertEqual(
            nested["00:01.000"][1]["original_box_coords"],
            [10.0, 20.0, 30.0, 20.0, 30.0, 40.0, 10.0, 40.0],
        )


class TranslateBatchUsesCaptionSettingsTests(unittest.TestCase):
    def test_one_request_uses_ops_model_and_system_prompt(self) -> None:
        step2 = {"00:02.000": [{"text": "加盐", "box": [0, 0, 1, 0, 1, 1, 0, 1]}]}
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "translations": [
                                {"id": "box_0", "vietnamese_text": "Thêm muối"}
                            ]
                        },
                        ensure_ascii=False,
                    )
                )
            )
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        settings = _settings()
        settings = TranslatorSettings(
            api_key=settings.api_key,
            base_url=settings.base_url,
            model_name="gemini-2.0-flash",
            system_prompt="PROMPT_TU_OPS_CAPTION",
            source="workspace_db",
        )
        translator = ContextualTranslator(settings=settings, client=mock_client)
        nested = translator.translate_step2_sync(step2)
        self.assertEqual(nested["00:02.000"][0]["vietnamese_text"], "Thêm muối")
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gemini-2.0-flash")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(kwargs["messages"][0]["content"], "PROMPT_TU_OPS_CAPTION")
        self.assertEqual(mock_client.chat.completions.create.call_count, 1)


class ServiceUsesContextualTranslatorTests(unittest.TestCase):
    def test_translate_subtitles_failsafe_ellipsis(self) -> None:
        import tempfile
        from pathlib import Path

        from src.media_pipeline.translator.service import translate_subtitles

        mock_response = MagicMock()
        # Opaque ids; missing u1 ("硬字幕") → fail-safe "..."
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({"u0": "Xin chao"}, ensure_ascii=False)
                )
            )
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch.dict("os.environ", {"TRANSLATE_LLM_DRY": ""}, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                result = translate_subtitles(
                    {0: "你好", 1000: "硬字幕"},
                    settings=_settings(),
                    client=mock_client,
                    memory_path=Path(tmp) / "mem.json",
                )
        self.assertEqual(result["0"], "Xin chao")
        self.assertEqual(result["1000"], "...")


if __name__ == "__main__":
    unittest.main()
