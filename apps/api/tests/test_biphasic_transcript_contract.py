"""DialogueBeat biphasic contract: ASR-only analyze → approve source → literal translate (no FunASR)."""

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
from src.audio_pipeline.translation_llm import _build_translate_prompt
from src.audio_pipeline.types import (
    AudioAnalysisRequest,
    ResolvedAudioInput,
    TranscriptDraftSegment,
    TranslationDraftSegment,
    TranslationPreset,
)
from src.enums import MediaAssetType, TranscriptSegmentStatus


class BiphasicTranscriptContractTests(unittest.TestCase):
    def test_asr_only_analyze_skips_translation_build(self) -> None:
        source_video_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            workspace_id=uuid4(),
            source_platform="DOUYIN",
            source_video_external_id="aweme-bi",
            caption="口播一句",
            duration_seconds=8.0,
            status=None,
            metadata_json={},
            source_profile=SimpleNamespace(
                source_profile_external_id="sec",
                handle="demo",
                display_name="Demo",
            ),
        )
        resolved = ResolvedAudioInput(
            source_video_id=source_video_id,
            input_asset_id=uuid4(),
            input_asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
            storage_key="workspace/demo/v.mp4",
            source_video_duration_seconds=8.0,
            source_caption="口播一句",
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
                        end_ms=2000,
                        text="口播一句",
                        normalized_text="口播一句",
                        confidence=0.9,
                        difficulty_flags_json={"flags": []},
                    )
                ],
            ) as persist_t,
            patch.object(service, "_persist_translations", return_value=[]) as persist_tr,
            patch.object(service, "_persist_json_asset", return_value=SimpleNamespace(id=uuid4())),
            patch.object(service, "get_summary", return_value={"manifest": {"assets": []}}),
            patch.object(service.translation_builder, "build") as translation_build,
        ):
            resolver_cls.return_value.resolve.return_value = (source_video, resolved)
            result = service.run_analysis(
                AudioAnalysisRequest(
                    source_video_id=source_video_id,
                    skip_translation=True,
                )
            )

        translation_build.assert_not_called()
        persist_t.assert_called_once()
        persist_tr.assert_called_once()
        self.assertEqual(persist_tr.call_args.args[2], [])
        self.assertEqual(result.translation_count, 0)
        self.assertEqual(result.transcript_count, 1)

    def test_literal_safe_prompt_forbids_additions(self) -> None:
        prompt = _build_translate_prompt("今天吃什么", TranslationPreset.LITERAL_SAFE, 2.0)
        lowered = prompt.lower()
        self.assertIn("literal", lowered)
        self.assertIn("do not add", lowered)
        self.assertIn("chinese source", lowered)
        self.assertIn("cooking", lowered)
        self.assertIn("subscribe", lowered)

    def test_natural_viral_prompt_asks_for_spoken_hooks(self) -> None:
        prompt = _build_translate_prompt("今天吃什么", TranslationPreset.NATURAL_VIRAL, 2.0)
        lowered = prompt.lower()
        self.assertIn("natural_viral", lowered)
        self.assertIn("spoken", lowered)
        self.assertIn("chinese source", lowered)

    def test_translation_only_builds_from_approved_source_beats(self) -> None:
        source_video_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            workspace_id=uuid4(),
            source_platform="DOUYIN",
            source_video_external_id="aweme-tr",
            caption=None,
            duration_seconds=8.0,
            status=None,
            metadata_json={},
            source_profile=SimpleNamespace(
                source_profile_external_id="sec",
                handle="demo",
                display_name="Demo",
            ),
        )
        beat = SimpleNamespace(
            id=uuid4(),
            segment_index=0,
            start_ms=0,
            end_ms=2000,
            text="口播一句",
            normalized_text="口播一句",
            confidence=0.9,
            speaker_label=None,
            difficulty_flags_json={"flags": []},
            analysis_version="AUDIO_ANALYSIS_V1_RUN_1",
            status=TranscriptSegmentStatus.APPROVED,
        )
        service = AudioAnalysisService(
            db=MagicMock(),
            storage=MagicMock(),
            stt_provider=MagicMock(transcribe=MagicMock(side_effect=AssertionError("ASR must not run"))),
            translation_provider=PlaceholderVietnameseTranslationProvider(),
            vad_provider=FixedVadProvider(has_speech=True),
        )
        with (
            patch.object(service, "_load_source_video", return_value=source_video),
            patch.object(service, "get_transcript_segments", return_value=[beat]),
            patch.object(service, "_mark_previous_translations_non_current"),
            patch.object(
                service,
                "_persist_translations",
                return_value=[
                    SimpleNamespace(
                        id=uuid4(),
                        transcript_segment_id=beat.id,
                        segment_index=0,
                        text="một câu mouthcast",
                        translation_preset=TranslationPreset.LITERAL_SAFE,
                        duration_budget_ms=2000,
                        estimated_tts_duration_ms=1800,
                        quality_flags_json={"flags": []},
                    )
                ],
            ) as persist_tr,
            patch.object(service, "_persist_json_asset", return_value=SimpleNamespace(id=uuid4())),
            patch.object(service, "get_summary", return_value={"manifest": {"assets": []}}),
        ):
            result = service.run_translation_only(
                source_video_id,
                translation_preset=TranslationPreset.LITERAL_SAFE,
                require_source_approved=True,
                job_id=uuid4(),
            )

        service.stt_provider.transcribe.assert_not_called()
        self.assertEqual(result.translation_count, 1)
        drafts = persist_tr.call_args.args[2]
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].translation_preset, TranslationPreset.LITERAL_SAFE)

    def test_translation_only_persists_clean_beats_when_some_gate_fail(self) -> None:
        """Minority CJK-gate failures must not discard successful Vietnamese beats."""
        source_video_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            workspace_id=uuid4(),
            source_platform="DOUYIN",
            source_video_external_id="aweme-partial-tr",
            caption=None,
            duration_seconds=8.0,
            status=None,
            metadata_json={},
            source_profile=SimpleNamespace(
                source_profile_external_id="sec",
                handle="demo",
                display_name="Demo",
            ),
        )
        beats = [
            SimpleNamespace(
                id=uuid4(),
                segment_index=0,
                start_ms=0,
                end_ms=2000,
                text="口播一句",
                normalized_text="口播一句",
                confidence=0.9,
                speaker_label=None,
                difficulty_flags_json={"flags": []},
                analysis_version="AUDIO_ANALYSIS_V1_RUN_1",
                status=TranscriptSegmentStatus.APPROVED,
            ),
            SimpleNamespace(
                id=uuid4(),
                segment_index=1,
                start_ms=2000,
                end_ms=4000,
                text="还有中文",
                normalized_text="还有中文",
                confidence=0.9,
                speaker_label=None,
                difficulty_flags_json={"flags": []},
                analysis_version="AUDIO_ANALYSIS_V1_RUN_1",
                status=TranscriptSegmentStatus.APPROVED,
            ),
        ]
        service = AudioAnalysisService(db=MagicMock(), storage=MagicMock())
        drafts = [
            TranslationDraftSegment(
                segment_index=0,
                translated_text="Một câu miệng",
                translation_preset=TranslationPreset.LITERAL_SAFE,
                duration_budget_seconds=2.0,
                estimated_tts_duration_seconds=1.5,
                quality_flags=[],
            ),
            TranslationDraftSegment(
                segment_index=1,
                translated_text="",
                translation_preset=TranslationPreset.LITERAL_SAFE,
                duration_budget_seconds=2.0,
                estimated_tts_duration_seconds=0.0,
                quality_flags=["translation_gate_failed", "vi_contains_source_script"],
            ),
        ]
        with (
            patch.object(service, "_load_source_video", return_value=source_video),
            patch.object(service, "get_transcript_segments", return_value=beats),
            patch.object(service.translation_builder, "build", return_value=drafts),
            patch.object(service, "_mark_previous_translations_non_current"),
            patch.object(
                service,
                "_persist_translations",
                return_value=[
                    SimpleNamespace(
                        id=uuid4(),
                        transcript_segment_id=beats[0].id,
                        segment_index=0,
                        text="Một câu miệng",
                        translation_preset=TranslationPreset.LITERAL_SAFE,
                        duration_budget_ms=2000,
                        estimated_tts_duration_ms=1500,
                        quality_flags_json={"flags": []},
                    ),
                    SimpleNamespace(
                        id=uuid4(),
                        transcript_segment_id=beats[1].id,
                        segment_index=1,
                        text="",
                        translation_preset=TranslationPreset.LITERAL_SAFE,
                        duration_budget_ms=2000,
                        estimated_tts_duration_ms=0,
                        quality_flags_json={"flags": ["translation_gate_failed"]},
                    ),
                ],
            ) as persist_tr,
            patch.object(service, "_persist_json_asset", return_value=SimpleNamespace(id=uuid4())),
            patch.object(service, "get_summary", return_value={"manifest": {"assets": []}}),
        ):
            result = service.run_translation_only(source_video_id, require_source_approved=True)

        # Job authority: filled Vietnamese beats only (empty gated rows must not count as success).
        self.assertEqual(result.translation_count, 1)
        self.assertEqual(persist_tr.call_args.args[2][0].translated_text, "Một câu miệng")
        self.assertIn("translation_gate_failed", result.flags_summary)
        self.assertEqual(source_video.metadata_json.get("dialogue_phase"), "translated_literal_partial")
        self.assertEqual(source_video.metadata_json.get("translation_filled_count"), 1)

    def test_translation_only_fails_when_provider_returns_empty(self) -> None:
        source_video_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            workspace_id=uuid4(),
            source_platform="DOUYIN",
            source_video_external_id="aweme-empty-tr",
            caption=None,
            duration_seconds=8.0,
            status=None,
            metadata_json={},
            source_profile=SimpleNamespace(
                source_profile_external_id="sec",
                handle="demo",
                display_name="Demo",
            ),
        )
        beat = SimpleNamespace(
            id=uuid4(),
            segment_index=0,
            start_ms=0,
            end_ms=2000,
            text="口播一句",
            normalized_text="口播一句",
            confidence=0.9,
            speaker_label=None,
            difficulty_flags_json={"flags": []},
            analysis_version="AUDIO_ANALYSIS_V1_RUN_1",
            status=TranscriptSegmentStatus.APPROVED,
        )
        empty_provider = MagicMock()
        empty_provider.provider_name = "empty"
        empty_provider.translate = MagicMock(
            side_effect=AssertionError("builder mocked; translate unused")
        )
        service = AudioAnalysisService(
            db=MagicMock(),
            storage=MagicMock(),
            translation_provider=empty_provider,
        )
        from src.audio_pipeline.errors import AudioAnalysisError
        from src.audio_pipeline.types import TranslationDraftSegment, TranslationPreset

        with (
            patch.object(service, "_load_source_video", return_value=source_video),
            patch.object(service, "get_transcript_segments", return_value=[beat]),
            patch.object(
                service.translation_builder,
                "build",
                return_value=[
                    TranslationDraftSegment(
                        segment_index=0,
                        translated_text="   ",
                        translation_preset=TranslationPreset.LITERAL_SAFE,
                        duration_budget_seconds=2.0,
                        estimated_tts_duration_seconds=1.0,
                        quality_flags=[],
                    )
                ],
            ),
        ):
            with self.assertRaises(AudioAnalysisError) as ctx:
                service.run_translation_only(source_video_id, require_source_approved=True)
            self.assertEqual(ctx.exception.code, "translation_failed")
            self.assertIn("0 non-empty", ctx.exception.message.lower())

    def test_translation_only_rejects_unapproved_source(self) -> None:
        source_video_id = uuid4()
        beat = SimpleNamespace(
            id=uuid4(),
            segment_index=0,
            start_ms=0,
            end_ms=2000,
            text="x",
            normalized_text="x",
            confidence=0.9,
            speaker_label=None,
            difficulty_flags_json={"flags": []},
            analysis_version="AUDIO_ANALYSIS_V1_RUN_1",
            status=TranscriptSegmentStatus.DRAFT,
        )
        service = AudioAnalysisService(db=MagicMock(), storage=MagicMock())
        with (
            patch.object(service, "_load_source_video", return_value=SimpleNamespace(id=source_video_id, workspace_id=uuid4(), source_platform="DOUYIN", source_video_external_id="e", source_profile=SimpleNamespace(source_profile_external_id="p", handle="h", display_name="d"), metadata_json={})),
            patch.object(service, "get_transcript_segments", return_value=[beat]),
        ):
            from src.audio_pipeline.errors import AudioAnalysisError

            with self.assertRaises(AudioAnalysisError) as ctx:
                service.run_translation_only(source_video_id, require_source_approved=True)
            self.assertIn("approve", ctx.exception.message.lower())


if __name__ == "__main__":
    unittest.main()
