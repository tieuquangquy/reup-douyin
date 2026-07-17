from __future__ import annotations

import time
import unittest
from dataclasses import dataclass

from src.audio_pipeline.providers import (
    CaptionFallbackSttProvider,
    PlaceholderVietnameseTranslationProvider,
    estimate_tts_duration_seconds,
)
from src.audio_pipeline.stt_funasr import (
    FunasrSttProvider,
    fit_funasr_units_to_duration,
    parse_funasr_generate_result,
    split_caption_into_timed_units,
)
from src.audio_pipeline.translation_llm import DurationConstrainedTranslationProvider, FixedLlmClient
from src.audio_pipeline.types import TranslationPreset


class FunasrSttProviderTests(unittest.TestCase):
    def test_untimed_funasr_blob_fits_video_duration_not_char_heuristic(self) -> None:
        """Regression: len(text)/4 invented ~3min for a ~74s Douyin video."""
        long_zh = "减" * 760  # char heuristic would claim ~190s
        raw = [{"text": long_zh}]
        units = parse_funasr_generate_result(raw)
        self.assertEqual(len(units), 1)
        self.assertIn("funasr_untimed", units[0].flags)
        self.assertGreater(units[0].end_seconds, 150.0)

        fitted = fit_funasr_units_to_duration(units, duration_seconds=74.0)
        # Keep untimed blob as one DialogueBeat; only clamp timing onto the media window.
        self.assertEqual(len(fitted), 1)
        self.assertEqual(fitted[0].start_seconds, 0.0)
        self.assertAlmostEqual(fitted[0].end_seconds, 74.0, places=2)
        self.assertIn("duration_fit", fitted[0].flags or [])
        self.assertNotIn("sentence_split", fitted[0].flags or [])
        self.assertEqual(fitted[0].text, long_zh)

        def runner(path: str):
            del path
            return raw

        provider = FunasrSttProvider(
            resolve_audio_path=lambda key: "/tmp/audio.wav",
            funasr_runner=runner,
        )
        via_provider = provider.transcribe("workspace/a.mp4", duration_seconds=74.0)
        self.assertEqual(len(via_provider), 1)
        self.assertAlmostEqual(via_provider[0].end_seconds, 74.0, places=2)

    def test_untimed_funasr_blob_stays_one_beat_even_with_sentence_punctuation(self) -> None:
        raw = [{"text": "当你减脂时不要吃这些硬菜了！薯片蛋糕可乐热量爆炸。坚持清淡饮食。"}]
        units = parse_funasr_generate_result(raw)
        self.assertEqual(len(units), 1)
        fitted = fit_funasr_units_to_duration(units, duration_seconds=28.0)
        self.assertEqual(len(fitted), 1)
        self.assertNotIn("sentence_split", fitted[0].flags or [])
        self.assertIn("funasr_untimed", fitted[0].flags or [])
        self.assertEqual(fitted[0].start_seconds, 0.0)
        self.assertAlmostEqual(fitted[0].end_seconds, 28.0, places=2)
        self.assertIn("减脂", fitted[0].text)
        self.assertIn("清淡", fitted[0].text)

    def test_parse_funasr_sentence_timestamps(self) -> None:
        raw = [
            {
                "text": "今天吃什么 减脂餐很简单",
                "sentence_info": [
                    {"text": "今天吃什么", "start": 0, "end": 1200},
                    {"text": "减脂餐很简单", "start": 1300, "end": 2800},
                ],
            }
        ]
        units = parse_funasr_generate_result(raw)
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0].text, "今天吃什么")
        self.assertEqual(units[0].start_seconds, 0.0)
        self.assertAlmostEqual(units[0].end_seconds, 1.2)
        self.assertEqual(units[1].text, "减脂餐很简单")
        self.assertAlmostEqual(units[1].start_seconds, 1.3)

    def test_split_caption_distributes_timing_by_length(self) -> None:
        units = split_caption_into_timed_units("你好。世界！测试", duration_seconds=6.0)
        self.assertEqual(len(units), 3)
        self.assertEqual(units[0].start_seconds, 0.0)
        self.assertAlmostEqual(units[-1].end_seconds, 6.0, places=2)
        self.assertTrue(all(u.end_seconds > u.start_seconds for u in units))

    def test_funasr_uses_injected_runner_when_available(self) -> None:
        def runner(path: str):
            self.assertEqual(path, "/tmp/audio.wav")
            return [
                {
                    "text": "口播一句",
                    "sentence_info": [{"text": "口播一句", "start": 100, "end": 2100}],
                }
            ]

        provider = FunasrSttProvider(
            resolve_audio_path=lambda key: "/tmp/audio.wav",
            funasr_runner=runner,
        )
        units = provider.transcribe("workspace/a.mp4", source_caption="caption ignored when asr works", duration_seconds=3.0)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].text, "口播一句")
        self.assertNotIn("caption_fallback", units[0].flags)

    def test_funasr_unavailable_returns_empty_not_caption(self) -> None:
        provider = FunasrSttProvider(
            resolve_audio_path=lambda key: None,
            funasr_runner=None,
            force_unavailable=True,
        )
        units = provider.transcribe("workspace/a.mp4", source_caption="第一句。第二句。", duration_seconds=4.0)
        self.assertEqual(units, [])

    def test_funasr_timeout_returns_empty_not_caption(self) -> None:
        """Slow model download/load must not block ANALYZE_AUDIO forever."""

        def slow_runner(path: str):
            del path
            time.sleep(2.0)
            return [
                {
                    "text": "should_not_win",
                    "sentence_info": [{"text": "should_not_win", "start": 0, "end": 1000}],
                }
            ]

        events: list[str] = []
        provider = FunasrSttProvider(
            resolve_audio_path=lambda key: "/tmp/audio.wav",
            funasr_runner=slow_runner,
            timeout_seconds=0.35,
            heartbeat_seconds=0.1,
            on_lifecycle=events.append,
        )
        started = time.monotonic()
        units = provider.transcribe(
            "workspace/a.mp4",
            source_caption="第一句。第二句。",
            duration_seconds=4.0,
        )
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 1.5, msg="timeout should abort before slow_runner finishes")
        self.assertEqual(units, [])
        self.assertIn("funasr_started", events)
        self.assertIn("funasr_waiting", events)
        self.assertIn("funasr_timed_out", events)


class DurationConstrainedTranslationTests(unittest.TestCase):
    def test_literal_safe_prefers_llm_over_machine_translate(self) -> None:
        client = FixedLlmClient(responses=["Ban dich Gemini sat nghia"])
        provider = DurationConstrainedTranslationProvider(
            primary=client,
            max_rewrite_rounds=0,
            machine_translate=lambda _src: "Ban dich MyMemory",
        )
        result = provider.translate(
            "减脂餐很简单",
            preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=3.0,
        )
        self.assertEqual(result.translated_text, "Ban dich Gemini sat nghia")
        self.assertEqual(client.call_count, 1)
        self.assertNotIn("machine_translate_primary", result.quality_flags)
        self.assertEqual(result.metadata.get("provider"), "fixed_llm")

    def test_literal_safe_uses_mt_when_llm_unavailable(self) -> None:
        @dataclass
        class BoomClient:
            provider_name: str = "gemini"

            def complete(self, prompt: str) -> str:
                raise RuntimeError("quota")

        provider = DurationConstrainedTranslationProvider(
            primary=BoomClient(),
            max_rewrite_rounds=0,
            machine_translate=lambda _src: "Ban dich MT recovery",
        )
        result = provider.translate(
            "减脂餐很简单",
            preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=3.0,
        )
        self.assertEqual(result.translated_text, "Ban dich MT recovery")
        self.assertIn("machine_translate_recovery", result.quality_flags)
        self.assertEqual(result.metadata.get("provider"), "mymemory")

    def test_rewrite_loop_shortens_oversized_translation(self) -> None:
        client = FixedLlmClient(
            responses=[
                "Đây là một bản dịch tiếng Việt rất dài khiến TTS chắc chắn vượt ngân sách thời lượng của phân đoạn gốc",
                "Bản dịch ngắn gọn",
            ]
        )
        provider = DurationConstrainedTranslationProvider(primary=client, max_rewrite_rounds=2)
        result = provider.translate(
            "这是一段中文",
            preset=TranslationPreset.NATURAL_VIRAL,
            duration_budget_seconds=1.2,
            source_confidence=0.9,
        )
        self.assertEqual(result.translated_text, "Bản dịch ngắn gọn")
        self.assertEqual(client.call_count, 2)
        self.assertNotIn("provider_placeholder", result.quality_flags)
        self.assertIn("duration_rewrite_applied", result.quality_flags)

    def test_gemini_then_qwen_fallback_on_primary_error(self) -> None:
        @dataclass
        class BoomClient:
            provider_name: str = "gemini"

            def complete(self, prompt: str) -> str:
                raise RuntimeError("quota")

        qwen = FixedLlmClient(responses=["Bản dịch từ Qwen"], provider_name="qwen_ollama")

        def boom_mt(_src: str) -> str:
            raise RuntimeError("mt_skip")

        provider = DurationConstrainedTranslationProvider(
            primary=BoomClient(),
            fallback=qwen,
            max_rewrite_rounds=0,
            machine_translate=boom_mt,
        )
        result = provider.translate(
            "你好",
            preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=2.0,
        )
        self.assertEqual(result.translated_text, "Bản dịch từ Qwen")
        self.assertEqual(result.metadata.get("provider"), "qwen_ollama")
        self.assertIn("translation_fallback_used", result.quality_flags)

    def test_cjk_in_vietnamese_triggers_repair_then_clean(self) -> None:
        client = FixedLlmClient(
            responses=[
                "Khi bạn giảm mỡ 一定不要再吃这些硬菜",
                "Khi bạn đang giảm mỡ thì đừng ăn những món nặng calo này nữa",
            ]
        )

        def boom_mt(_src: str) -> str:
            raise RuntimeError("mt_skip_for_repair_path")

        provider = DurationConstrainedTranslationProvider(
            primary=client,
            max_rewrite_rounds=0,
            machine_translate=boom_mt,
        )
        result = provider.translate(
            "当你正在减脂时一定不要再吃这些硬菜了",
            preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=6.0,
        )
        self.assertEqual(
            result.translated_text,
            "Khi bạn đang giảm mỡ thì đừng ăn những món nặng calo này nữa",
        )
        self.assertEqual(client.call_count, 2)
        self.assertNotIn("translation_gate_failed", result.quality_flags)
        self.assertFalse(any("\u4e00" <= ch <= "\u9fff" for ch in result.translated_text))

    def test_cjk_gate_fails_closed_when_repair_still_dirty(self) -> None:
        client = FixedLlmClient(
            responses=[
                "Bản dịch lẫn 中文 còn sót",
                "Vẫn còn 汉字 trong câu",
                "Cuối cùng vẫn 有中文",
            ]
        )

        def boom_mt(_src: str) -> str:
            raise RuntimeError("mt_down")

        provider = DurationConstrainedTranslationProvider(
            primary=client,
            max_rewrite_rounds=0,
            max_cjk_repair_rounds=2,
            machine_translate=boom_mt,
        )
        result = provider.translate(
            "还有中文",
            preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=3.0,
        )
        self.assertEqual(result.translated_text, "")
        self.assertIn("vi_contains_source_script", result.quality_flags)
        self.assertIn("translation_gate_failed", result.quality_flags)

    def test_cjk_dirty_recovers_via_machine_translate(self) -> None:
        """When chat LLM leaves Chinese, recovery MT on source cleans the beat."""
        client = FixedLlmClient(responses=["Khi giảm mỡ 不要吃这些"])
        provider = DurationConstrainedTranslationProvider(
            primary=client,
            max_rewrite_rounds=0,
            max_cjk_repair_rounds=2,
            machine_translate=lambda _src: "Khi giam mo dung an mon nay",
        )
        result = provider.translate(
            "减脂时不要吃这些。薯片蛋糕。",
            preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=6.0,
        )
        self.assertEqual(result.translated_text, "Khi giam mo dung an mon nay")
        self.assertEqual(client.call_count, 1)
        self.assertIn("machine_translate_applied", result.quality_flags)
        self.assertNotIn("translation_gate_failed", result.quality_flags)

    def test_cjk_dirty_recovers_via_micro_chunk_when_mt_unavailable(self) -> None:
        """Long dirty VI: after repair+MT fail, re-translate smaller Chinese chunks."""
        client = FixedLlmClient(
            responses=[
                "Khi giảm mỡ 不要吃这些",
                "Vẫn lẫn 硬菜",
                "Khi giảm mỡ đừng ăn món này",
                "khoai tây chiên và bánh ngọt",
            ]
        )

        def boom_mt(_src: str) -> str:
            raise RuntimeError("mt_down")

        provider = DurationConstrainedTranslationProvider(
            primary=client,
            max_rewrite_rounds=0,
            max_cjk_repair_rounds=1,
            machine_translate=boom_mt,
        )
        result = provider.translate(
            "减脂时不要吃这些。薯片蛋糕。",
            preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=6.0,
        )
        self.assertEqual(
            result.translated_text,
            "Khi giảm mỡ đừng ăn món này khoai tây chiên và bánh ngọt",
        )
        self.assertIn("cjk_chunk_retranslate_applied", result.quality_flags)
        self.assertNotIn("translation_gate_failed", result.quality_flags)

    def test_placeholder_still_available(self) -> None:
        text = PlaceholderVietnameseTranslationProvider().translate(
            "中文",
            preset=TranslationPreset.NATURAL_VIRAL,
            duration_budget_seconds=2.0,
        ).translated_text
        self.assertIn("中文", text)
        self.assertGreater(estimate_tts_duration_seconds("mot cau dai"), 0.6)


class CaptionFallbackStillWorks(unittest.TestCase):
    def test_caption_fallback_single_unit(self) -> None:
        units = CaptionFallbackSttProvider().transcribe("k", source_caption="口播", duration_seconds=2.5)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].end_seconds, 2.5)


if __name__ == "__main__":
    unittest.main()
