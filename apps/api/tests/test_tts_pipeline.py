import unittest
from types import SimpleNamespace
from uuid import uuid4

from src.enums import MediaAssetType
from src.tts_pipeline.providers import PlaceholderToneTtsProvider
from src.tts_pipeline.services.subtitle_builder import SubtitleBuilder, build_srt
from src.tts_pipeline.services.timing_fit import classify_timing_fit
from src.tts_pipeline.types import TimingFitStatus, TranslationInputSegment, TtsProviderInput, VoiceConfig


class TtsPipelineTests(unittest.TestCase):
    def test_timing_fit_classification(self) -> None:
        self.assertEqual(classify_timing_fit(1.0, 2.0)[0], TimingFitStatus.TOO_SHORT)
        self.assertEqual(classify_timing_fit(1.0, 1.0)[0], TimingFitStatus.FITS_WELL)
        self.assertEqual(classify_timing_fit(1.12, 1.0)[0], TimingFitStatus.SLIGHTLY_LONG)
        self.assertEqual(classify_timing_fit(1.4, 1.0)[0], TimingFitStatus.TOO_LONG)

    def test_placeholder_tts_provider_returns_wav(self) -> None:
        provider = PlaceholderToneTtsProvider()
        result = provider.synthesize(
            TtsProviderInput(
                text="Day la mot cau tieng Viet",
                language_code="vi",
                voice_config=VoiceConfig(),
                target_duration_seconds=2.0,
            )
        )
        self.assertEqual(result.mime_type, "audio/wav")
        self.assertTrue(result.audio_bytes.startswith(b"RIFF"))
        self.assertIn("provider_placeholder", result.warnings)

    def test_subtitle_builder_and_srt(self) -> None:
        translation_id = uuid4()
        segment = TranslationInputSegment(
            translation_segment_id=translation_id,
            transcript_segment_id=uuid4(),
            source_video_id=uuid4(),
            segment_index=0,
            start_ms=1200,
            end_ms=3400,
            translated_text="Xin chao moi nguoi",
            duration_budget_ms=2200,
            translation_version=1,
            translation_preset="natural_viral",
            quality_flags=["low_confidence_source"],
        )
        subtitles = SubtitleBuilder().build([segment], [])
        self.assertEqual(subtitles[0].text, "Xin chao moi nguoi")
        self.assertEqual(subtitles[0].layout_mode, "bottom_safe_area")
        self.assertIn("low_confidence_source", subtitles[0].review_flags)
        srt = build_srt(subtitles)
        self.assertIn("00:00:01,200 --> 00:00:03,400", srt)
        self.assertIn("Xin chao moi nguoi", srt)

    def test_render_prep_manifest_asset_type_values(self) -> None:
        asset = SimpleNamespace(
            id=uuid4(),
            asset_type=MediaAssetType.TTS_AUDIO_JOINED,
            is_current=True,
            storage_key="workspace/video/audio/joined.wav",
            logical_key="workspace/video/audio/joined.wav",
            mime_type="audio/wav",
            version=1,
            metadata_json={},
        )
        self.assertEqual(str(asset.asset_type), "TTS_AUDIO_JOINED")


if __name__ == "__main__":
    unittest.main()
