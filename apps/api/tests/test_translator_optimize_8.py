"""Phase 2.5 optimize: canonical, track SSOT, memory, opaque ids, rules, temp=0, fossil, near-dupe."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.media_pipeline.translator.config import (
    DEFAULT_TRANSLATION_SYSTEM_PROMPT,
    TranslatorSettings,
)
from src.media_pipeline.translator.normalize import (
    canonical_zh,
    flatten_ocr_chinese,
    merge_near_duplicate_zh,
    segment_authority_zh,
    unique_chinese_texts,
)
from src.media_pipeline.translator.rule_route import rule_translate_zh
from src.media_pipeline.translator.service import translate_subtitles


def _settings() -> TranslatorSettings:
    return TranslatorSettings(
        api_key="sk-test",
        base_url="https://example.test/v1",
        model_name="gpt-4o-mini",
        system_prompt=DEFAULT_TRANSLATION_SYSTEM_PROMPT,
        source="env",
    )


class CanonicalTests(unittest.TestCase):
    def test_canonical_collapses_space_and_fullwidth(self) -> None:
        self.assertEqual(canonical_zh("加 盐"), "加盐")
        self.assertEqual(canonical_zh("５２克"), "52克")
        self.assertEqual(canonical_zh("  西兰花\n"), "西兰花")


class SegmentAuthorityTests(unittest.TestCase):
    def test_prefers_master_timeline_text_id(self) -> None:
        payload = {
            "master_timeline": [
                {
                    "text_id": "sub_01",
                    "ocr_text": "加盐",
                    "translate_ready": True,
                },
                {
                    "text_id": "sub_02",
                    "ocr_text": "西兰花",
                    "translate_ready": True,
                },
                {
                    "text_id": "sub_03",
                    "ocr_text": "52克",
                    "translate_ready": False,
                },
            ],
            "frames": [
                {
                    "time_ms": 1600,
                    "boxes": [
                        {
                            "text": "加盐",
                            "text_id": "sub_01",
                            "translate_ready": True,
                        }
                    ],
                },
                {
                    "time_ms": 1633,
                    "boxes": [
                        {
                            "text": "加盐",
                            "text_id": "sub_01",
                            "translate_ready": True,
                        }
                    ],
                },
            ],
        }
        segs = segment_authority_zh(payload)
        self.assertEqual(segs, {"sub_01": "加盐", "sub_02": "西兰花"})
        # Flatten still expands stamps for render keys.
        flat = flatten_ocr_chinese(payload)
        self.assertEqual(flat["1600#0"], "加盐")
        self.assertEqual(flat["1633#0"], "加盐")


class NearDupeTests(unittest.TestCase):
    def test_merge_near_duplicates_to_longer(self) -> None:
        mapping = merge_near_duplicate_zh(
            ["每天都会更新好吃的减脂餐", "天都会更新好吃的减脂餐", "加盐"]
        )
        self.assertEqual(
            mapping["天都会更新好吃的减脂餐"],
            "每天都会更新好吃的减脂餐",
        )
        self.assertEqual(mapping["加盐"], "加盐")
        self.assertEqual(
            mapping["每天都会更新好吃的减脂餐"],
            "每天都会更新好吃的减脂餐",
        )


class RuleRouteTests(unittest.TestCase):
    def test_rule_translates_grams_and_kcal(self) -> None:
        self.assertEqual(rule_translate_zh("52克"), "52g")
        self.assertEqual(rule_translate_zh("614千卡"), "614 kcal")
        self.assertIsNone(rule_translate_zh("加盐"))


class OpaqueIdAndTempTests(unittest.TestCase):
    def test_llm_uses_opaque_ids_and_temperature_zero(self) -> None:
        payload = {
            "frames": [
                {"time_ms": 0, "boxes": [{"text": "加盐", "translate_ready": True}]},
                {
                    "time_ms": 1000,
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
        with patch.dict("os.environ", {"TRANSLATE_LLM_DRY": ""}, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                result = translate_subtitles(
                    payload,
                    settings=_settings(),
                    client=mock_client,
                    memory_path=Path(tmp) / "mem.json",
                )
        self.assertEqual(result["0#0"], "Thêm muối")
        self.assertEqual(result["1000#0"], "Bông cải xanh")
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["temperature"], 0)
        body = kwargs["messages"][1]["content"].split("\n\n", 1)[-1]
        sent = json.loads(body)
        self.assertEqual(set(sent.keys()), {"u0", "u1"})
        self.assertTrue(all(k.startswith("u") for k in sent))
        self.assertNotIn("加盐", sent)  # opaque ids, not ZH keys


class MemoryTests(unittest.TestCase):
    def test_second_call_skips_llm_for_cached_zh(self) -> None:
        payload = {
            "frames": [
                {"time_ms": 0, "boxes": [{"text": "加盐", "translate_ready": True}]},
            ]
        }
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({"u0": "Thêm muối"}, ensure_ascii=False)
                )
            )
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with tempfile.TemporaryDirectory() as tmp:
            mem = Path(tmp) / "mem.json"
            with patch.dict("os.environ", {"TRANSLATE_LLM_DRY": ""}, clear=False):
                first = translate_subtitles(
                    payload,
                    settings=_settings(),
                    client=mock_client,
                    memory_path=mem,
                )
                second = translate_subtitles(
                    payload,
                    settings=_settings(),
                    client=mock_client,
                    memory_path=mem,
                )
        self.assertEqual(first["0#0"], "Thêm muối")
        self.assertEqual(second["0#0"], "Thêm muối")
        self.assertEqual(mock_client.chat.completions.create.call_count, 1)


class FossilTests(unittest.TestCase):
    def test_writes_translate_fossils(self) -> None:
        payload = {
            "frames": [
                {"time_ms": 0, "boxes": [{"text": "52克", "translate_ready": True}]},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp)
            with patch.dict("os.environ", {"TRANSLATE_LLM_DRY": "1"}, clear=False):
                result = translate_subtitles(
                    payload,
                    artifact_dir=art,
                    memory_path=art / "mem.json",
                )
            self.assertEqual(result["0#0"], "52g")
            unique = json.loads((art / "translate_unique.json").read_text(encoding="utf-8"))
            vi = json.loads((art / "vi_texts.json").read_text(encoding="utf-8"))
            stats = json.loads((art / "translate_stats.json").read_text(encoding="utf-8"))
            self.assertEqual(unique.get("52克"), "52g")
            self.assertEqual(vi["0#0"], "52g")
            self.assertGreaterEqual(int(stats.get("rule_hit") or 0), 1)


class CanonicalDedupeIntegrationTests(unittest.TestCase):
    def test_spaced_zh_dedupes_to_one_llm_entry(self) -> None:
        payload = {
            "frames": [
                {"time_ms": 1600, "boxes": [{"text": "加盐", "translate_ready": True}]},
                {
                    "time_ms": 1633,
                    "boxes": [{"text": "加 盐", "translate_ready": True}],
                },
            ]
        }
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({"u0": "Thêm muối"}, ensure_ascii=False)
                )
            )
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch.dict("os.environ", {"TRANSLATE_LLM_DRY": ""}, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                result = translate_subtitles(
                    payload,
                    settings=_settings(),
                    client=mock_client,
                    memory_path=Path(tmp) / "mem.json",
                )
        self.assertEqual(result["1600#0"], "Thêm muối")
        self.assertEqual(result["1633#0"], "Thêm muối")
        body = mock_client.chat.completions.create.call_args.kwargs["messages"][1][
            "content"
        ].split("\n\n", 1)[-1]
        sent = json.loads(body)
        self.assertEqual(len(sent), 1)


class NearDupeLlmIntegrationTests(unittest.TestCase):
    def test_near_dupe_sends_one_representative(self) -> None:
        payload = {
            "frames": [
                {
                    "time_ms": 0,
                    "boxes": [
                        {
                            "text": "每天都会更新好吃的减脂餐",
                            "translate_ready": True,
                        }
                    ],
                },
                {
                    "time_ms": 1000,
                    "boxes": [
                        {
                            "text": "天都会更新好吃的减脂餐",
                            "translate_ready": True,
                        }
                    ],
                },
            ]
        }
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {"u0": "Mỗi ngày cập nhật món giảm béo ngon"},
                        ensure_ascii=False,
                    )
                )
            )
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        with patch.dict("os.environ", {"TRANSLATE_LLM_DRY": ""}, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                result = translate_subtitles(
                    payload,
                    settings=_settings(),
                    client=mock_client,
                    memory_path=Path(tmp) / "mem.json",
                )
        self.assertEqual(
            result["0#0"],
            "Mỗi ngày cập nhật món giảm béo ngon",
        )
        self.assertEqual(
            result["1000#0"],
            "Mỗi ngày cập nhật món giảm béo ngon",
        )
        body = mock_client.chat.completions.create.call_args.kwargs["messages"][1][
            "content"
        ].split("\n\n", 1)[-1]
        self.assertEqual(len(json.loads(body)), 1)


if __name__ == "__main__":
    unittest.main()
