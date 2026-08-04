"""An ASR that hears nothing is not proof that a video has no dialogue.

When measured VAD says the clip contains speech but ASR returns no beats, the video
must land in a visible "uncertain" state instead of silently skipping dubbing.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.audio_pipeline.providers import PlaceholderVietnameseTranslationProvider
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.types import AudioAnalysisRequest, ResolvedAudioInput, VadResult
from src.enums import MediaAssetType


class _SilentStt:
    provider_name = "silent_stt"

    def transcribe(self, audio_storage_key, *, source_caption=None, duration_seconds=None):
        del audio_storage_key, source_caption, duration_seconds
        return []


class _StubVad:
    provider_name = "silero_vad"

    def __init__(self, result: VadResult):
        self._result = result

    def detect(self, audio_storage_key, *, duration_seconds=None, source_caption=None):
        del audio_storage_key, duration_seconds, source_caption
        return self._result


def _measured_speech() -> VadResult:
    return VadResult(
        has_speech=True,
        speech_ratio=0.9,
        difficulty_flags=["silero_vad_executed"],
        metadata={"provider": "silero_vad", "speech_seconds": 37.3, "audio_seconds": 41.4},
    )


def _measured_silence() -> VadResult:
    return VadResult(
        has_speech=False,
        speech_ratio=0.0,
        difficulty_flags=["silero_vad_executed", "skip_dubbing", "no_speech_detected"],
        metadata={"provider": "silero_vad", "speech_seconds": 0.0, "audio_seconds": 48.6},
    )


def _guessed_speech() -> VadResult:
    return VadResult(
        has_speech=True,
        speech_ratio=None,
        difficulty_flags=["vad_heuristic_assume_speech", "silero_failed"],
        metadata={"provider": "heuristic_vad"},
    )


class DialogueUncertainStateTests(unittest.TestCase):
    def _run(self, vad: VadResult) -> SimpleNamespace:
        source_video_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            workspace_id=uuid4(),
            source_platform="DOUYIN",
            source_video_external_id="aweme-uncertain",
            caption="中式减脂餐",
            duration_seconds=41.4,
            status=None,
            metadata_json={},
            source_profile=SimpleNamespace(
                source_profile_external_id="sec-1",
                handle="demo",
                display_name="Demo",
            ),
        )
        resolved = ResolvedAudioInput(
            source_video_id=source_video_id,
            input_asset_id=uuid4(),
            input_asset_type=MediaAssetType.SOURCE_VIDEO_RAW,
            storage_key="workspace/demo/clip.mp4",
            source_video_duration_seconds=41.4,
            source_caption="中式减脂餐",
        )
        service = AudioAnalysisService(
            db=MagicMock(),
            storage=MagicMock(),
            stt_provider=_SilentStt(),
            translation_provider=PlaceholderVietnameseTranslationProvider(),
            vad_provider=_StubVad(vad),
            separation_provider=MagicMock(
                provider_name="noop",
                separate=MagicMock(
                    return_value=SimpleNamespace(
                        vocal_asset_id=None,
                        background_asset_id=None,
                        transcription_storage_key="workspace/demo/clip.mp4",
                        fallback_used=False,
                        difficulty_flags=[],
                        metadata={},
                    )
                ),
            ),
        )
        with (
            patch("src.audio_pipeline.services.audio_analysis_service.AudioAssetResolver") as resolver_cls,
            patch.object(service, "_next_analysis_version", return_value="AUDIO_ANALYSIS_V1_RUN_1"),
            patch.object(service, "_mark_previous_non_current"),
            patch.object(service, "_persist_transcripts", return_value=[]),
            patch.object(service, "_persist_translations", return_value=[]),
            patch.object(service, "_persist_json_asset", return_value=SimpleNamespace(id=uuid4())),
            patch.object(service, "get_summary", return_value={"manifest": {"assets": []}}),
        ):
            resolver_cls.return_value.resolve.return_value = (source_video, resolved)
            result = service.run_analysis(AudioAnalysisRequest(source_video_id=source_video_id))
        return SimpleNamespace(meta=source_video.metadata_json, result=result)

    def test_measured_speech_without_asr_beats_is_uncertain(self) -> None:
        run = self._run(_measured_speech())

        self.assertEqual(run.meta["dialogue_phase"], "dialogue_uncertain")
        self.assertTrue(run.meta["has_speech"], "VAD measured real speech; do not claim the clip is silent")
        self.assertIn("asr_empty_despite_vad_speech", run.result.flags_summary)
        self.assertNotIn("skip_dubbing", run.result.flags_summary)

    def test_measured_silence_stays_no_dialogue(self) -> None:
        run = self._run(_measured_silence())

        self.assertEqual(run.meta["dialogue_phase"], "no_dialogue")
        self.assertFalse(run.meta["has_speech"])
        self.assertIn("skip_dubbing", run.result.flags_summary)

    def test_unmeasured_guess_stays_no_dialogue_but_is_marked_unverified(self) -> None:
        # No Silero measurement means no positive evidence of speech: keep the auto
        # pipeline moving, but record that the verdict was never verified.
        run = self._run(_guessed_speech())

        self.assertEqual(run.meta["dialogue_phase"], "no_dialogue")
        self.assertIn("dialogue_unverified", run.result.flags_summary)

    def test_vad_evidence_is_persisted_for_every_run(self) -> None:
        run = self._run(_measured_speech())

        vad_meta = run.meta["vad"]
        self.assertEqual(vad_meta["speech_ratio"], 0.9)
        self.assertEqual(vad_meta["metadata"]["speech_seconds"], 37.3)


if __name__ == "__main__":
    unittest.main()
