from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from src.audio_pipeline.speech_budget import (
    SpeechRateSample,
    assess_speech_budget,
    calibrate_units_per_second,
    count_spoken_units,
    extract_protected_tokens,
    validate_protected_tokens,
)
from src.audio_pipeline.translation_llm import (
    DurationConstrainedTranslationProvider,
    FixedLlmClient,
)
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.enums import TranscriptSegmentStatus
from src.audio_pipeline.types import TranslationPreset


class SpeechBudgetTests(unittest.TestCase):
    def test_counts_vietnamese_spoken_units_and_expands_common_numbers(self) -> None:
        self.assertEqual(count_spoken_units("Cho 200 g cơm vào chảo"), 7)
        self.assertEqual(count_spoken_units("510 kcal"), 7)

    def test_pause_budget_is_capped_and_short_slot_is_fail_closed(self) -> None:
        assessment = assess_speech_budget(
            "Một, hai, ba, bốn, năm",
            slot_seconds=1.0,
            units_per_second=4.5,
        )
        self.assertEqual(assessment.pause_budget_ms, 400)
        self.assertEqual(assessment.speech_time_ms, 600)
        self.assertEqual(assessment.status, "too_long")

        short = assess_speech_budget(
            "Xin chào",
            slot_seconds=0.3,
            units_per_second=4.5,
        )
        self.assertTrue(short.requires_operator_review)
        self.assertIn("slot_below_minimum_speech_time", short.flags)

    def test_fit_status_uses_total_estimated_duration_including_pauses(self) -> None:
        over = assess_speech_budget(
            "môi trường sạch, không khí cũng rất trong lành",
            slot_seconds=2.0,
            units_per_second=4.5,
            fit_tolerance=0.12,
        )
        fitted = assess_speech_budget(
            "môi trường sạch, không khí trong lành",
            slot_seconds=2.0,
            units_per_second=4.5,
            fit_tolerance=0.12,
        )

        self.assertEqual(over.status, "too_long")
        self.assertEqual(fitted.status, "fits_budget")

    def test_voice_rate_calibration_uses_median_only_after_enough_samples(self) -> None:
        samples = [
            SpeechRateSample(spoken_units=20, duration_seconds=5.0),
            SpeechRateSample(spoken_units=24, duration_seconds=5.0),
            SpeechRateSample(spoken_units=22, duration_seconds=5.0),
            SpeechRateSample(spoken_units=100, duration_seconds=1.0),
        ]
        calibrated = calibrate_units_per_second(samples, default_units_per_second=4.5)
        self.assertAlmostEqual(calibrated.units_per_second, 4.4)
        self.assertEqual(calibrated.source, "calibrated_robust_median")

        fallback = calibrate_units_per_second(samples[:2], default_units_per_second=5.0)
        self.assertEqual(fallback.units_per_second, 5.0)
        self.assertEqual(fallback.source, "default_insufficient_samples")


class ProtectedTokenTests(unittest.TestCase):
    def test_preserves_numbers_urls_acronyms_and_common_units(self) -> None:
        tokens = extract_protected_tokens(
            "Dùng 200 g cơm, 10 ml sốt và xem https://example.com/FAQ"
        )
        self.assertTrue(validate_protected_tokens(
            tokens,
            "Dùng 200 g cơm với 10 ml sốt, xem https://example.com/FAQ",
        ).valid)
        missing = validate_protected_tokens(tokens, "Dùng cơm với sốt")
        self.assertFalse(missing.valid)
        self.assertIn("200", missing.missing_tokens)
        self.assertIn("10", missing.missing_tokens)


class ControlledDurationRewriteTests(unittest.TestCase):
    def test_rewrite_prompt_reserves_punctuation_headroom(self) -> None:
        class CapturingClient:
            provider_name = "capturing"

            def __init__(self) -> None:
                self.prompts: list[str] = []
                self.responses = [
                    "Còn hộp quà cú đêm có hai món quà tặng là quạt mini với máy thổi bong bóng, mở ra xem nào.",
                    "Hộp quà cú đêm tặng quạt mini và máy thổi bong bóng. Mở xem nhé.",
                ]

            def complete(self, prompt: str) -> str:
                self.prompts.append(prompt)
                return self.responses[min(len(self.prompts) - 1, len(self.responses) - 1)]

        client = CapturingClient()
        provider = DurationConstrainedTranslationProvider(primary=client, max_rewrite_rounds=2)
        result = provider.translate(
            "夜猫礼包有两个赠品",
            preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=4.18,
        )

        self.assertEqual(
            result.translated_text,
            "Hộp quà cú đêm tặng quạt mini và máy thổi bong bóng. Mở xem nhé.",
        )
        self.assertIn("Target spoken-unit range: 14-16", client.prompts[1])
        self.assertEqual(result.metadata["speech_budget"]["status"], "fits_budget")

    def test_rewrite_rejects_dropped_protected_tokens_then_keeps_safe_candidate(self) -> None:
        original = "Cho 200 g cơm vào chảo rồi đảo thật đều để cơm nóng hoàn toàn"
        client = FixedLlmClient(
            responses=[
                original,
                "Cho cơm vào chảo đảo đều",
                "Cho 200 g cơm vào chảo đảo đều",
            ]
        )
        provider = DurationConstrainedTranslationProvider(
            primary=client,
            max_rewrite_rounds=4,
        )
        result = provider.translate(
            "加入200克米饭翻炒",
            preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=2.0,
            source_confidence=0.95,
        )
        self.assertEqual(result.translated_text, "Cho 200 g cơm vào chảo đảo đều")
        self.assertIn("duration_rewrite_applied", result.quality_flags)
        self.assertIn("needs_operator_review", result.quality_flags)
        adaptation = result.metadata["duration_adaptation"]
        self.assertEqual(adaptation["schema_version"], "duration_adaptation_v1")
        self.assertEqual(len(adaptation["candidates"]), 2)
        self.assertFalse(adaptation["candidates"][0]["protected_tokens_ok"])
        self.assertTrue(adaptation["candidates"][1]["protected_tokens_ok"])

    def test_no_safe_candidate_preserves_original_and_requests_review(self) -> None:
        original = "Cho 200 g cơm vào chảo rồi đảo thật đều để cơm nóng hoàn toàn"
        client = FixedLlmClient(
            responses=[original, "Cho cơm vào chảo", "Đảo cơm đều"],
        )
        provider = DurationConstrainedTranslationProvider(
            primary=client,
            max_rewrite_rounds=2,
        )
        result = provider.translate(
            "加入200克米饭翻炒",
            preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=1.0,
        )
        self.assertEqual(result.translated_text, original)
        self.assertIn("duration_adaptation_required", result.quality_flags)
        self.assertIn("needs_operator_review", result.quality_flags)
        self.assertEqual(
            result.metadata["duration_adaptation"]["decision"],
            "keep_original_no_safe_candidate",
        )

    def test_translation_draft_artifact_keeps_reviewable_candidate_metadata(self) -> None:
        row = SimpleNamespace(
            id=uuid4(),
            transcript_segment_id=uuid4(),
            segment_index=0,
            text="Bản viết lại",
            status=TranscriptSegmentStatus.NEEDS_REVIEW,
            translation_preset="literal_safe",
            duration_budget_ms=2000,
            estimated_tts_duration_ms=1800,
            quality_flags_json={"flags": ["duration_rewrite_applied"]},
            metadata_json={
                "duration_adaptation": {
                    "schema_version": "duration_adaptation_v1",
                    "decision": "review_candidate_selected",
                }
            },
        )
        payload = AudioAnalysisService.__new__(AudioAnalysisService)._translation_payload(row)
        self.assertEqual(payload["status"], "NEEDS_REVIEW")
        self.assertEqual(
            payload["metadata"]["duration_adaptation"]["decision"],
            "review_candidate_selected",
        )


if __name__ == "__main__":
    unittest.main()
