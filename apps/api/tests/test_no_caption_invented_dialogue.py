"""Caption must not become DialogueBeats when ASR is unavailable or returns no speech."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.audio_pipeline.caption_asr_consensus import apply_caption_asr_consensus
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.stt_funasr import FunasrSttProvider
from src.audio_pipeline.types import AudioAnalysisRequest, ResolvedAudioInput, TranscriptionUnit
from src.enums import MediaAssetType


class NoCaptionInventedDialogueTests(unittest.TestCase):
    def test_funasr_unavailable_returns_empty_not_caption_beats(self) -> None:
        provider = FunasrSttProvider(force_unavailable=True)
        units = provider.transcribe(
            "workspace/a.mp4",
            source_caption="【靠吃瘦了80斤】中式减脂餐 | 午餐 | 照烧鸡排饭 670千卡。",
            duration_seconds=51.0,
        )
        self.assertEqual(units, [])

    def test_funasr_timeout_returns_empty_not_caption_beats(self) -> None:
        def boom(_path: str):
            raise TimeoutError("funasr timed out")

        provider = FunasrSttProvider(
            resolve_audio_path=lambda key: "/tmp/audio.wav",
            funasr_runner=boom,
            timeout_seconds=0.01,
        )
        # Force timeout path via explicit TimeoutError from runner wrapped path —
        # provider catches TimeoutError from run_with_timeout; inject via failed _transcribe.
        with patch.object(provider, "_transcribe_with_funasr", side_effect=TimeoutError("timeout")):
            units = provider.transcribe(
                "workspace/a.mp4",
                source_caption="标题不是台词",
                duration_seconds=10.0,
            )
        self.assertEqual(units, [])

    def test_consensus_empty_asr_does_not_invent_caption_dialogue(self) -> None:
        result = apply_caption_asr_consensus(
            [],
            caption="【靠吃瘦了80斤】中式减脂餐 | 午餐",
            duration_seconds=51.0,
        )
        self.assertEqual(result, [])

    def test_run_analysis_with_funasr_unavailable_persists_zero_beats_and_skip_dubbing(self) -> None:
        source_video_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            workspace_id=uuid4(),
            source_platform="DOUYIN",
            source_video_external_id="aweme-silent",
            caption="【靠吃瘦了80斤】中式减脂餐 | 午餐 | 照烧鸡排饭 670千卡。",
            duration_seconds=51.0,
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
            source_video_duration_seconds=51.0,
            source_caption=source_video.caption,
        )
        service = AudioAnalysisService(
            db=MagicMock(),
            storage=MagicMock(),
            stt_provider=FunasrSttProvider(force_unavailable=True),
            vad_provider=MagicMock(
                provider_name="heuristic",
                detect=MagicMock(
                    return_value=SimpleNamespace(
                        has_speech=True,
                        speech_ratio=1.0,
                        difficulty_flags=["vad_heuristic_assume_speech"],
                        metadata={},
                    )
                ),
            ),
            separation_provider=MagicMock(
                provider_name="fallback",
                separate=MagicMock(
                    return_value=SimpleNamespace(
                        vocal_asset_id=None,
                        background_asset_id=None,
                        transcription_storage_key="workspace/demo/v.mp4",
                        fallback_used=True,
                        difficulty_flags=["source_separation_unavailable"],
                        metadata={},
                    )
                ),
            ),
        )
        with (
            patch("src.audio_pipeline.services.audio_analysis_service.AudioAssetResolver") as resolver_cls,
            patch.object(service, "_next_analysis_version", return_value="AUDIO_ANALYSIS_V1_RUN_1"),
            patch.object(service, "_mark_previous_non_current"),
            patch.object(service, "_persist_transcripts", return_value=[]) as persist_t,
            patch.object(service, "_persist_translations", return_value=[]),
            patch.object(service, "_persist_json_asset", return_value=SimpleNamespace(id=uuid4())),
            patch.object(service, "get_summary", return_value={"manifest": {"assets": []}}),
        ):
            resolver_cls.return_value.resolve.return_value = (source_video, resolved)
            result = service.run_analysis(
                AudioAnalysisRequest(source_video_id=source_video_id, skip_translation=True)
            )

        self.assertEqual(result.transcript_count, 0)
        persist_t.assert_called_once()
        self.assertEqual(persist_t.call_args.args[1], [])
        self.assertEqual(source_video.metadata_json.get("dialogue_phase"), "no_dialogue")
        self.assertIn("skip_dubbing", result.flags_summary)
        self.assertIn("caption_not_dialogue", result.flags_summary)


if __name__ == "__main__":
    unittest.main()
