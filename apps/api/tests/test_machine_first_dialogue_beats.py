"""Machine-first DialogueBeat: Demucs vocal STT, caption↔ASR consensus, auto-approve."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.audio_pipeline.caption_asr_consensus import (
    apply_caption_asr_consensus,
    caption_asr_similarity,
    drop_punctuation_only_units,
    should_auto_approve_source,
)
from src.audio_pipeline.demucs_runner import DemucsStemPaths
from src.audio_pipeline.providers import DemucsSourceSeparationProvider
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.types import (
    AudioAnalysisRequest,
    ResolvedAudioInput,
    TranscriptionUnit,
)
from src.enums import MediaAssetType, TranscriptSegmentStatus
from src.storage.local import LocalStorageBackend


class CaptionAsrConsensusTests(unittest.TestCase):
    def test_high_similarity_keeps_asr_timing_and_flags_agreed(self) -> None:
        units = [
            TranscriptionUnit(text="今天吃什么", start_seconds=0.0, end_seconds=2.0, confidence=0.9, flags=["funasr"]),
        ]
        result = apply_caption_asr_consensus(units, caption="今天吃什么？", duration_seconds=2.0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "今天吃什么")
        self.assertEqual(result[0].end_seconds, 2.0)
        self.assertIn("caption_agreed", result[0].flags)

    def test_conflict_keeps_asr_text_never_caption_title(self) -> None:
        """Douyin title/hashtag caption must not replace spoken ASR DialogueBeats."""
        units = [
            TranscriptionUnit(text="完全不同的识别结果", start_seconds=0.0, end_seconds=3.0, confidence=0.5, flags=["funasr"]),
        ]
        caption = "【靠吃瘦了80斤】中式减脂餐 | 午餐 | #减脂餐"
        result = apply_caption_asr_consensus(units, caption=caption, duration_seconds=3.0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text, "完全不同的识别结果")
        self.assertEqual(result[0].end_seconds, 3.0)
        self.assertIn("caption_asr_conflict", result[0].flags)
        self.assertNotIn("caption_preferred", result[0].flags)
        self.assertNotIn("今天", result[0].text)
        self.assertNotIn("#", result[0].text)

    def test_drop_punctuation_only_beats(self) -> None:
        units = [
            TranscriptionUnit(text="口播一句", start_seconds=0.0, end_seconds=2.0, confidence=0.9, flags=["funasr"]),
            TranscriptionUnit(text="!", start_seconds=2.0, end_seconds=2.3, confidence=0.55, flags=["funasr"]),
            TranscriptionUnit(text="  ", start_seconds=2.3, end_seconds=2.5, confidence=0.55, flags=["funasr"]),
        ]
        cleaned = drop_punctuation_only_units(units)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0].text, "口播一句")

    def test_missing_caption_marks_source_unverified(self) -> None:
        units = [
            TranscriptionUnit(text="口播", start_seconds=0.0, end_seconds=1.0, confidence=0.8, flags=["funasr"]),
        ]
        result = apply_caption_asr_consensus(units, caption=None, duration_seconds=1.0)
        self.assertIn("source_unverified", result[0].flags)

    def test_similarity_normalizes_punctuation(self) -> None:
        self.assertGreater(caption_asr_similarity("你好！", "你好"), 0.9)

    def test_auto_approve_when_agreed(self) -> None:
        self.assertTrue(should_auto_approve_source(["caption_agreed", "funasr"], avg_confidence=0.85))

    def test_auto_approve_blocked_only_on_heavy_conflict_with_low_confidence(self) -> None:
        self.assertFalse(
            should_auto_approve_source(["caption_asr_conflict", "low_confidence"], avg_confidence=0.4)
        )
        # Machine-first: conflict with decent confidence still auto-approves so VI review can proceed.
        self.assertTrue(
            should_auto_approve_source(["caption_asr_conflict"], avg_confidence=0.8)
        )


class DemucsExecutionTests(unittest.TestCase):
    def test_demucs_provider_executes_runner_and_points_stt_at_vocals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = LocalStorageBackend(root)
            input_key = "workspace/demo/video/raw.wav"
            storage.write_bytes(input_key, b"RIFF____WAVE")

            def fake_runner(*, input_path: Path, output_dir: Path, model_name: str) -> Path:
                del model_name
                out = output_dir / "vocals.wav"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"VOCALS")
                return out

            provider = DemucsSourceSeparationProvider(
                storage=storage,
                runner=fake_runner,
                demucs_importable=True,
            )
            result = provider.separate(input_key)

        self.assertFalse(result.fallback_used)
        self.assertNotIn("demucs_not_executed", result.difficulty_flags)
        self.assertNotIn("demucs_unavailable", result.difficulty_flags)
        self.assertTrue(result.transcription_storage_key.endswith("vocals.wav") or "vocals" in result.transcription_storage_key)
        self.assertNotEqual(result.transcription_storage_key, input_key)

    def test_demucs_provider_falls_back_with_unavailable_flag_when_import_missing(self) -> None:
        provider = DemucsSourceSeparationProvider(demucs_importable=False)
        result = provider.separate("video/raw.mp4")
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.transcription_storage_key, "video/raw.mp4")
        self.assertIn("demucs_unavailable", result.difficulty_flags)
        self.assertNotIn("demucs_not_executed", result.difficulty_flags)

    def test_demucs_provider_persists_both_stems(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = LocalStorageBackend(root)
            input_key = "workspace/demo/video/raw.mp4"
            storage.write_bytes(input_key, b"source")

            def fake_runner(*, input_path: Path, output_dir: Path, model_name: str):
                del input_path, model_name
                vocals = output_dir / "vocals.wav"
                background = output_dir / "no_vocals.wav"
                vocals.write_bytes(b"VOCALS")
                background.write_bytes(b"BACKGROUND")
                return DemucsStemPaths(vocals=vocals, background=background)

            provider = DemucsSourceSeparationProvider(
                storage=storage,
                runner=fake_runner,
                demucs_importable=True,
            )
            result = provider.separate(input_key)

            self.assertFalse(result.fallback_used)
            self.assertTrue(storage.exists(result.metadata["vocal_storage_key"]))
            self.assertTrue(storage.exists(result.metadata["background_storage_key"]))


class MachineFirstAutoApproveTests(unittest.TestCase):
    def test_asr_only_auto_approves_agreed_beats(self) -> None:
        source_video_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            workspace_id=uuid4(),
            source_platform="DOUYIN",
            source_video_external_id="aweme-mf",
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
        beat_id = uuid4()
        persisted = [
            SimpleNamespace(
                id=beat_id,
                segment_index=0,
                start_ms=0,
                end_ms=2000,
                text="口播一句",
                normalized_text="口播一句",
                confidence=0.9,
                difficulty_flags_json={"flags": ["caption_agreed"]},
                status=TranscriptSegmentStatus.DRAFT,
            )
        ]
        service = AudioAnalysisService(
            db=MagicMock(),
            storage=MagicMock(),
            stt_provider=MagicMock(
                provider_name="funasr",
                transcribe=MagicMock(
                    return_value=[
                        TranscriptionUnit(
                            text="口播一句",
                            start_seconds=0.0,
                            end_seconds=2.0,
                            confidence=0.9,
                            flags=["funasr"],
                        )
                    ]
                ),
            ),
            translation_provider=MagicMock(provider_name="placeholder"),
            vad_provider=MagicMock(
                provider_name="fixed",
                detect=MagicMock(return_value=SimpleNamespace(has_speech=True, speech_ratio=1.0, difficulty_flags=[], metadata={})),
            ),
            separation_provider=MagicMock(
                provider_name="demucs_htdemucs",
                separate=MagicMock(
                    return_value=SimpleNamespace(
                        vocal_asset_id=None,
                        background_asset_id=None,
                        transcription_storage_key="workspace/demo/audio/vocals.wav",
                        fallback_used=False,
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
            patch.object(service, "_next_analysis_version", return_value="AUDIO_ANALYSIS_V1_RUN_1"),
            patch.object(service, "_mark_previous_non_current"),
            patch.object(service, "_persist_transcripts", return_value=persisted) as persist_t,
            patch.object(service, "_persist_translations", return_value=[]),
            patch.object(service, "_persist_json_asset", return_value=SimpleNamespace(id=uuid4())),
            patch.object(service, "get_summary", return_value={"manifest": {"assets": []}}),
        ):
            resolver_cls.return_value.resolve.return_value = (source_video, resolved)
            result = service.run_analysis(
                AudioAnalysisRequest(source_video_id=source_video_id, skip_translation=True)
            )

        self.assertEqual(result.translation_count, 0)
        self.assertEqual(persisted[0].status, TranscriptSegmentStatus.APPROVED)
        self.assertEqual(source_video.metadata_json.get("dialogue_phase"), "source_auto_approved")
        # Consensus applied before transcript build — persist receives drafts with flags.
        drafts = persist_t.call_args.args[1]
        self.assertTrue(any("caption_agreed" in d.difficulty_flags for d in drafts))


if __name__ == "__main__":
    unittest.main()
