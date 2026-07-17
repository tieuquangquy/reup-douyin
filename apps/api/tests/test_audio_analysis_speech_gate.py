from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.audio_pipeline.providers import (
    CaptionFallbackSttProvider,
    FixedVadProvider,
    PlaceholderVietnameseTranslationProvider,
)
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.types import AudioAnalysisRequest, ResolvedAudioInput, TranscriptionUnit, TranslationPreset
from src.enums import MediaAssetType


class _OverrunUntimedStt:
    """Mimics FunASR blob that invents end from char length and ignores duration."""

    provider_name = "overrun_untimed"

    def transcribe(self, audio_storage_key: str, *, source_caption=None, duration_seconds=None):
        del audio_storage_key, source_caption, duration_seconds
        return [
            TranscriptionUnit(
                text="减" * 759,
                start_seconds=0.0,
                end_seconds=189.75,
                confidence=0.8,
                flags=["funasr", "funasr_untimed"],
            )
        ]


class AudioAnalysisSpeechGateTests(unittest.TestCase):
    def test_run_analysis_skips_stt_when_vad_reports_no_speech(self) -> None:
        source_video_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            workspace_id=uuid4(),
            source_platform="DOUYIN",
            source_video_external_id="aweme1",
            caption="可能有字幕",
            duration_seconds=12.0,
            status=None,
            metadata_json={},
            source_profile=SimpleNamespace(
                source_profile_external_id="sec123",
                handle="demo",
                display_name="Demo",
            ),
        )
        resolved = ResolvedAudioInput(
            source_video_id=source_video_id,
            input_asset_id=uuid4(),
            input_asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
            storage_key="workspace/demo/video.mp4",
            source_video_duration_seconds=12.0,
            source_caption="可能有字幕",
        )
        stt = CaptionFallbackSttProvider()
        service = AudioAnalysisService(
            db=MagicMock(),
            storage=MagicMock(),
            stt_provider=stt,
            translation_provider=PlaceholderVietnameseTranslationProvider(),
            vad_provider=FixedVadProvider(has_speech=False),
        )

        with (
            patch(
                "src.audio_pipeline.services.audio_analysis_service.AudioAssetResolver"
            ) as resolver_cls,
            patch.object(service, "_next_analysis_version", return_value="AUDIO_ANALYSIS_V1_RUN_1"),
            patch.object(service, "_mark_previous_non_current"),
            patch.object(service, "_persist_transcripts", return_value=[]) as persist_transcripts,
            patch.object(service, "_persist_translations", return_value=[]),
            patch.object(service, "_persist_json_asset") as persist_json,
            patch.object(service, "get_summary", return_value={"manifest": {"assets": []}}),
        ):
            resolver_cls.return_value.resolve.return_value = (source_video, resolved)
            persist_json.return_value = SimpleNamespace(id=uuid4())
            result = service.run_analysis(AudioAnalysisRequest(source_video_id=source_video_id))

        persist_transcripts.assert_called_once()
        self.assertEqual(persist_transcripts.call_args.args[1], [])
        self.assertEqual(result.transcript_count, 0)
        self.assertEqual(source_video.metadata_json.get("has_speech"), False)
        self.assertIn("skip_dubbing", result.flags_summary)
        metadata_payload = persist_json.call_args_list[0].args[3]
        self.assertEqual(metadata_payload["vad"]["has_speech"], False)
        self.assertEqual(metadata_payload["vad"]["provider"], "fixed_vad")

    def test_run_analysis_keeps_stt_when_vad_reports_speech(self) -> None:
        source_video_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            workspace_id=uuid4(),
            source_platform="DOUYIN",
            source_video_external_id="aweme2",
            caption="中文口播",
            duration_seconds=8.0,
            status=None,
            metadata_json={},
            source_profile=SimpleNamespace(
                source_profile_external_id="sec456",
                handle="demo",
                display_name="Demo",
            ),
        )
        resolved = ResolvedAudioInput(
            source_video_id=source_video_id,
            input_asset_id=uuid4(),
            input_asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
            storage_key="workspace/demo/video2.mp4",
            source_video_duration_seconds=8.0,
            source_caption="中文口播",
        )
        service = AudioAnalysisService(
            db=MagicMock(),
            storage=MagicMock(),
            stt_provider=CaptionFallbackSttProvider(),
            translation_provider=PlaceholderVietnameseTranslationProvider(),
            vad_provider=FixedVadProvider(has_speech=True),
        )

        with (
            patch(
                "src.audio_pipeline.services.audio_analysis_service.AudioAssetResolver"
            ) as resolver_cls,
            patch.object(service, "_next_analysis_version", return_value="AUDIO_ANALYSIS_V1_RUN_1"),
            patch.object(service, "_mark_previous_non_current"),
            patch.object(
                service,
                "_persist_transcripts",
                return_value=[
                    SimpleNamespace(
                        id=uuid4(),
                        segment_index=0,
                        start_ms=0,
                        end_ms=1000,
                        text="中文口播",
                        normalized_text="中文口播",
                        confidence=0.55,
                        difficulty_flags_json={"flags": []},
                    )
                ],
            ) as persist_t,
            patch.object(
                service,
                "_persist_translations",
                return_value=[
                    SimpleNamespace(
                        id=uuid4(),
                        transcript_segment_id=uuid4(),
                        segment_index=0,
                        text="vi",
                        translation_preset=TranslationPreset.NATURAL_VIRAL,
                        duration_budget_ms=1000,
                        estimated_tts_duration_ms=900,
                        quality_flags_json={"flags": []},
                    )
                ],
            ),
            patch.object(service, "_persist_json_asset", return_value=SimpleNamespace(id=uuid4())),
            patch.object(service, "get_summary", return_value={"manifest": {"assets": []}}),
        ):
            resolver_cls.return_value.resolve.return_value = (source_video, resolved)
            result = service.run_analysis(
                AudioAnalysisRequest(source_video_id=source_video_id, translation_preset=TranslationPreset.NATURAL_VIRAL)
            )

        self.assertEqual(len(persist_t.call_args.args[1]), 1)
        self.assertEqual(source_video.metadata_json.get("has_speech"), True)
        self.assertEqual(result.transcript_count, 1)

    def test_run_analysis_fits_overrun_stt_units_to_video_duration(self) -> None:
        """Service-level safety net: untimed ASR past media length must clamp before persist."""
        source_video_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            workspace_id=uuid4(),
            source_platform="DOUYIN",
            source_video_external_id="aweme3",
            caption="口播",
            duration_seconds=74.0,
            status=None,
            metadata_json={},
            source_profile=SimpleNamespace(
                source_profile_external_id="sec789",
                handle="demo",
                display_name="Demo",
            ),
        )
        resolved = ResolvedAudioInput(
            source_video_id=source_video_id,
            input_asset_id=uuid4(),
            input_asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
            storage_key="workspace/demo/video3.mp4",
            source_video_duration_seconds=74.0,
            source_caption="口播",
        )
        service = AudioAnalysisService(
            db=MagicMock(),
            storage=MagicMock(),
            stt_provider=_OverrunUntimedStt(),
            translation_provider=PlaceholderVietnameseTranslationProvider(),
            vad_provider=FixedVadProvider(has_speech=True),
            separation_provider=MagicMock(
                provider_name="noop",
                separate=MagicMock(
                    return_value=SimpleNamespace(
                        vocal_asset_id=None,
                        background_asset_id=None,
                        transcription_storage_key="workspace/demo/video3.mp4",
                        fallback_used=True,
                        difficulty_flags=[],
                        metadata={},
                    )
                ),
            ),
        )

        with (
            patch(
                "src.audio_pipeline.services.audio_analysis_service.AudioAssetResolver"
            ) as resolver_cls,
            patch.object(service, "_next_analysis_version", return_value="AUDIO_ANALYSIS_V1_RUN_5"),
            patch.object(service, "_mark_previous_non_current"),
            patch.object(service, "_persist_transcripts", return_value=[]) as persist_t,
            patch.object(service, "_persist_translations", return_value=[]),
            patch.object(service, "_persist_json_asset", return_value=SimpleNamespace(id=uuid4())),
            patch.object(service, "get_summary", return_value={"manifest": {"assets": []}}),
        ):
            resolver_cls.return_value.resolve.return_value = (source_video, resolved)
            service.run_analysis(AudioAnalysisRequest(source_video_id=source_video_id))

        drafts = persist_t.call_args.args[1]
        self.assertEqual(len(drafts), 1)
        self.assertAlmostEqual(drafts[0].end_seconds, 74.0, places=2)
        self.assertIn("duration_fit", drafts[0].difficulty_flags)


if __name__ == "__main__":
    unittest.main()
