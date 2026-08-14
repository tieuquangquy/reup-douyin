import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from src.enums import MediaAssetType
from src.storage.local import LocalStorageBackend
from src.tts_pipeline.providers import PlaceholderToneTtsProvider
from src.tts_pipeline.services.tts_service import TtsPipelineService, _select_tts_probe_candidates
from src.tts_pipeline.services.subtitle_builder import SubtitleBuilder, build_srt
from src.tts_pipeline.services.timing_fit import classify_timing_fit
from src.tts_pipeline.types import (
    SynthesizedSegment,
    TimingFitStatus,
    TranslationInputSegment,
    TtsProviderInput,
    TtsProviderOutput,
    VoiceConfig,
)


class TtsPipelineTests(unittest.TestCase):
    def test_expressive_probe_keeps_primary_and_compact_approved_fallback(self) -> None:
        ranked = [
            "Chỗ gốc mũi này không vẽ hai đường chữ C nữa, mình sẽ làm đậm vùng tam giác giữa hai đầu mày và cả hốc mắt.",
            "Ở phần gốc mũi này mình không vẽ hai đường chữ C nữa, mà sẽ nhấn vào vùng tam giác giữa hai đầu mày và hốc mắt.",
            "Gốc mũi không vẽ hai đường chữ C nữa, chỉ nhấn vùng tam giác giữa mày và hốc mắt.",
        ]

        selected = _select_tts_probe_candidates(ranked, expressive_required=True)

        self.assertEqual(selected, [ranked[0], ranked[2]])

    def test_raw_acoustic_cache_reuses_voice_audio_across_timeline_budgets(self) -> None:
        with TemporaryDirectory() as tmp:
            provider = SimpleNamespace(
                provider_name="omnivoice",
                model_id="k2-fsa/OmniVoice",
                options={},
            )
            service = TtsPipelineService(
                SimpleNamespace(),
                storage=LocalStorageBackend(Path(tmp)),
                tts_provider=provider,
            )
            source = SimpleNamespace(id=uuid4(), workspace_id=uuid4())
            voice = VoiceConfig(
                voice_id="instruct:vi_female_north",
                language_code="vi",
                speaking_rate=1.0,
            )
            cache_key = service._acoustic_cache_key(
                "Xin chào",
                voice_config=voice,
                runtime_authority={"provider": "omnivoice"},
            )
            raw = TtsProviderOutput(
                audio_bytes=b"RIFFraw-acoustic-wave",
                duration_seconds=1.4,
                mime_type="audio/wav",
                file_extension="wav",
                provider_metadata={"provider": "omnivoice"},
                warnings=[],
            )

            service._write_acoustic_cache(source, raw, cache_key=cache_key)
            cached = service._load_acoustic_cache(source, cache_key=cache_key)

            self.assertIsNotNone(cached)
            assert cached is not None
            self.assertEqual(cached.audio_bytes, raw.audio_bytes)
            self.assertEqual(cached.duration_seconds, 1.4)
            self.assertEqual(cached.provider_metadata["acoustic_cache"]["status"], "hit")

    def test_segment_cache_round_trip_reuses_exact_fitted_wav(self) -> None:
        with TemporaryDirectory() as tmp:
            provider = SimpleNamespace(
                provider_name="omnivoice",
                model_id="k2-fsa/OmniVoice",
                options={},
            )
            service = TtsPipelineService(
                SimpleNamespace(),
                storage=LocalStorageBackend(Path(tmp)),
                tts_provider=provider,
            )
            source = SimpleNamespace(id=uuid4(), workspace_id=uuid4())
            segment = TranslationInputSegment(
                translation_segment_id=uuid4(),
                transcript_segment_id=uuid4(),
                source_video_id=source.id,
                segment_index=2,
                start_ms=1000,
                end_ms=2200,
                translated_text="Xin chào",
                duration_budget_ms=1200,
                translation_version=1,
                translation_preset="literal_safe",
            )
            voice = VoiceConfig(
                voice_id="instruct:vi_female_north",
                language_code="vi",
                speaking_rate=1.0,
            )
            cache_key = service._segment_cache_key(
                segment,
                voice_config=voice,
                runtime_authority={"provider": "omnivoice"},
            )
            fitted = SynthesizedSegment(
                input_segment=segment,
                audio_bytes=b"RIFFexact-fitted-wave",
                duration_seconds=1.2,
                mime_type="audio/wav",
                file_extension="wav",
                provider_metadata={"provider": "omnivoice", "speech_budget": {"spoken_units": 2}},
                warnings=[],
                fit_status=TimingFitStatus.FITS_WELL,
                fit_ratio=1.0,
            )

            service._write_segment_cache(source, fitted, cache_key=cache_key)
            cached = service._load_segment_cache(source, segment, cache_key=cache_key)

            self.assertIsNotNone(cached)
            assert cached is not None
            self.assertEqual(cached.audio_bytes, fitted.audio_bytes)
            self.assertEqual(cached.fit_status, TimingFitStatus.FITS_WELL)
            self.assertEqual(cached.provider_metadata["segment_cache"]["status"], "hit")

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
