import unittest
from types import SimpleNamespace

from src.audio_pipeline.providers import (
    CaptionFallbackSttProvider,
    DemucsSourceSeparationProvider,
    FallbackSourceSeparationProvider,
    FixedVadProvider,
    HeuristicVadProvider,
    PlaceholderVietnameseTranslationProvider,
    estimate_tts_duration_seconds,
)
from src.audio_pipeline.services.asset_selection import choose_audio_input_asset
from src.audio_pipeline.services.transcript_builder import TranscriptBuilder
from src.audio_pipeline.services.translation_draft_builder import TranslationDraftBuilder
from src.audio_pipeline.types import TranslationPreset, TranscriptionUnit
from src.enums import MediaAssetStatus, MediaAssetType


class AudioPipelineTests(unittest.TestCase):
    def test_transcript_builder_assigns_flags_and_indexes(self) -> None:
        builder = TranscriptBuilder(min_duration_seconds=0.5, max_duration_seconds=4.0, low_confidence_threshold=0.7)
        segments = builder.build(
            [
                TranscriptionUnit(
                    text="  你好   今天很好 ",
                    start_seconds=0.0,
                    end_seconds=0.4,
                    confidence=0.55,
                    flags=["background_too_loud"],
                ),
                TranscriptionUnit(
                    text="第二句",
                    start_seconds=0.5,
                    end_seconds=6.0,
                    confidence=0.9,
                ),
            ]
        )
        self.assertEqual([segment.segment_index for segment in segments], [0, 1])
        self.assertEqual(segments[0].normalized_source_text, "你好 今天很好")
        self.assertIn("low_confidence", segments[0].difficulty_flags)
        self.assertIn("too_short", segments[0].difficulty_flags)
        self.assertIn("background_too_loud", segments[0].difficulty_flags)
        self.assertIn("too_long", segments[1].difficulty_flags)

    def test_caption_fallback_stt_uses_source_caption(self) -> None:
        provider = CaptionFallbackSttProvider()
        units = provider.transcribe("video/raw.mp4", source_caption="中文口播", duration_seconds=3.2)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].text, "中文口播")
        self.assertEqual(units[0].end_seconds, 3.2)
        self.assertIn("caption_fallback", units[0].flags)

    def test_asset_selection_prefers_current_audio_extract(self) -> None:
        raw = SimpleNamespace(
            asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
            status=MediaAssetStatus.AVAILABLE,
            is_current=True,
        )
        audio = SimpleNamespace(
            asset_type=MediaAssetType.SOURCE_AUDIO_EXTRACT,
            status=MediaAssetStatus.AVAILABLE,
            is_current=True,
        )
        stale_audio = SimpleNamespace(
            asset_type=MediaAssetType.SOURCE_AUDIO_EXTRACT,
            status=MediaAssetStatus.AVAILABLE,
            is_current=False,
        )
        self.assertIs(choose_audio_input_asset([raw, stale_audio, audio]), audio)

    def test_source_separation_fallback_keeps_input_key_and_flags(self) -> None:
        result = FallbackSourceSeparationProvider().separate("video/raw.mp4")
        self.assertEqual(result.transcription_storage_key, "video/raw.mp4")
        self.assertTrue(result.fallback_used)
        self.assertIn("source_separation_unavailable", result.difficulty_flags)

    def test_demucs_provider_falls_back_when_unavailable(self) -> None:
        result = DemucsSourceSeparationProvider().separate("video/raw.mp4")
        self.assertEqual(result.transcription_storage_key, "video/raw.mp4")
        self.assertTrue(result.fallback_used)

    def test_fixed_vad_no_speech_flags_skip_dubbing(self) -> None:
        result = FixedVadProvider(has_speech=False).detect("video/raw.mp4", duration_seconds=10.0)
        self.assertFalse(result.has_speech)
        self.assertIn("skip_dubbing", result.difficulty_flags)

    def test_heuristic_vad_assumes_speech_for_normal_duration(self) -> None:
        result = HeuristicVadProvider().detect("video/raw.mp4", duration_seconds=8.0)
        self.assertTrue(result.has_speech)
        self.assertIn("vad_heuristic_assume_speech", result.difficulty_flags)

    def test_translation_builder_maps_budget_and_review_flags(self) -> None:
        transcript = TranscriptBuilder().build(
            [
                TranscriptionUnit(
                    text="这是一个很短的片段",
                    start_seconds=0.0,
                    end_seconds=1.0,
                    confidence=0.5,
                )
            ]
        )
        translations = TranslationDraftBuilder(PlaceholderVietnameseTranslationProvider()).build(
            transcript,
            preset=TranslationPreset.NATURAL_VIRAL,
        )
        self.assertEqual(translations[0].segment_index, 0)
        self.assertEqual(translations[0].translation_preset, TranslationPreset.NATURAL_VIRAL)
        self.assertIn("low_confidence_source", translations[0].quality_flags)
        self.assertIn("provider_placeholder", translations[0].quality_flags)

    def test_tts_duration_estimate_is_deterministic(self) -> None:
        self.assertEqual(estimate_tts_duration_seconds(""), 0.6)
        self.assertGreater(estimate_tts_duration_seconds("mot cau tieng viet kha dai"), 1.0)


if __name__ == "__main__":
    unittest.main()
