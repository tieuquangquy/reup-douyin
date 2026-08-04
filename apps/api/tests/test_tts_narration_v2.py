from __future__ import annotations

import unittest
import wave
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import numpy as np

from src.tts_pipeline.services.audio_timing import (
    plan_timing_adjustment,
    recommended_spoken_unit_limit,
    timing_quality_band,
)
from src.tts_pipeline.services.narration_assembler import NarrationAssembler
from src.tts_pipeline.services.render_prep_manifest_builder import (
    build_render_prep_manifest,
)
from src.tts_pipeline.services.tts_service import (
    _tts_idempotency_key,
    _voice_rate_samples,
)
from src.tts_pipeline.types import (
    SynthesizedSegment,
    TimingFitStatus,
    TranslationInputSegment,
    VoiceConfig,
)


def _wav(*, duration: float, sample_rate: int, amplitude: int = 6000) -> bytes:
    samples = np.full(max(1, int(round(duration * sample_rate))), amplitude, dtype="<i2")
    output = BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(samples.tobytes())
    return output.getvalue()


def _segment(*, index: int, start_ms: int, end_ms: int, sample_rate: int) -> SynthesizedSegment:
    duration = (end_ms - start_ms) / 1000.0
    source_id = uuid4()
    source = TranslationInputSegment(
        translation_segment_id=uuid4(),
        transcript_segment_id=uuid4(),
        source_video_id=source_id,
        segment_index=index,
        start_ms=start_ms,
        end_ms=end_ms,
        translated_text=f"Câu {index}",
        duration_budget_ms=end_ms - start_ms,
        translation_version=1,
        translation_preset="literal_safe",
    )
    return SynthesizedSegment(
        input_segment=source,
        audio_bytes=_wav(duration=duration, sample_rate=sample_rate),
        duration_seconds=duration,
        mime_type="audio/wav",
        file_extension="wav",
        provider_metadata={"provider": "test"},
        warnings=[],
        fit_status=TimingFitStatus.FITS_WELL,
        fit_ratio=1.0,
    )


class TimingAdjustmentTests(unittest.TestCase):
    def test_small_overrun_is_fitted_and_large_overrun_is_blocked(self) -> None:
        fitted = plan_timing_adjustment(1.10, 1.0)
        blocked = plan_timing_adjustment(1.20, 1.0)
        short = plan_timing_adjustment(0.60, 1.0)
        self.assertEqual(fitted.action, "atempo")
        self.assertAlmostEqual(fitted.speed_factor or 0.0, 1.10)
        self.assertEqual(blocked.action, "block")
        self.assertEqual(short.action, "keep_with_tail_silence")

    def test_quality_band_marks_above_seven_percent_for_review(self) -> None:
        self.assertEqual(timing_quality_band(1.0), "no_speed_adjustment")
        self.assertEqual(timing_quality_band(1.06), "natural_speed_adjustment")
        self.assertEqual(timing_quality_band(1.10), "review_speed_adjustment")
        self.assertEqual(timing_quality_band(1.20), "blocked_speed_adjustment")

    def test_measured_rewrite_limit_uses_provider_duration(self) -> None:
        self.assertEqual(
            recommended_spoken_unit_limit(
                139,
                34.133,
                29.0,
                max_speed=1.15,
            ),
            135,
        )
        self.assertEqual(
            recommended_spoken_unit_limit(
                139,
                34.133,
                29.0,
                max_speed=1.07,
            ),
            126,
        )

    def test_idempotency_key_changes_with_translation_or_voice(self) -> None:
        source_id = uuid4()
        first = _tts_idempotency_key(
            source_video_id=source_id,
            translation_input_sha256="a" * 64,
            voice_config=VoiceConfig(voice_id="voice-a"),
        )
        changed_translation = _tts_idempotency_key(
            source_video_id=source_id,
            translation_input_sha256="b" * 64,
            voice_config=VoiceConfig(voice_id="voice-a"),
        )
        self.assertNotEqual(first, changed_translation)


class FullDurationNarrationTests(unittest.TestCase):
    def test_places_normalized_clips_on_source_timeline_with_silence(self) -> None:
        segments = [
            _segment(index=0, start_ms=1000, end_ms=1500, sample_rate=24_000),
            _segment(index=1, start_ms=2200, end_ms=2700, sample_rate=48_000),
        ]
        audio, metadata = NarrationAssembler().assemble(
            segments,
            timeline_duration_seconds=3.0,
        )
        with wave.open(BytesIO(audio), "rb") as handle:
            self.assertEqual(handle.getframerate(), 48_000)
            self.assertEqual(handle.getnchannels(), 1)
            self.assertEqual(handle.getsampwidth(), 2)
            self.assertAlmostEqual(handle.getnframes() / 48_000, 3.0, places=3)
            pcm = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
        self.assertEqual(int(np.max(np.abs(pcm[:48_000]))), 0)
        self.assertGreater(int(np.max(np.abs(pcm[48_000:72_000]))), 0)
        self.assertEqual(int(np.max(np.abs(pcm[72_000:105_600]))), 0)
        self.assertGreater(int(np.max(np.abs(pcm[105_600:129_600]))), 0)
        self.assertEqual(metadata["assembly_strategy"], "full_duration_timeline_mix")
        self.assertEqual(metadata["audio_format"]["sample_rate_hz"], 48_000)
        self.assertEqual(metadata["timing_map"][0]["output_start_seconds"], 1.0)


class RenderPrepManifestV2Tests(unittest.TestCase):
    def test_manifest_exposes_hash_format_timing_and_pending_audio_review(self) -> None:
        joined = SimpleNamespace(
            id=uuid4(),
            asset_type="TTS_AUDIO_JOINED",
            is_current=True,
            storage_key="audio/joined.wav",
            logical_key="audio/joined.wav",
            mime_type="audio/wav",
            version=2,
            checksum_sha256="a" * 64,
            size_bytes=1234,
            metadata_json={
                "absolute_path": "C:/private/path.wav",
                "duration_seconds": 3.0,
                "audio_format": {"sample_rate_hz": 48000, "channels": 1},
                "timing_map": [],
            },
        )
        manifest = build_render_prep_manifest(
            source_video_id=str(uuid4()),
            source_video_external_id="video-1",
            assets=[joined],
            synthesized_segments=[],
            subtitle_version="TTS_PIPELINE_V2_RUN_1",
            provider_summary={"tts_provider": "test"},
            warnings=[],
            timeline_duration_seconds=3.0,
            translation_input_sha256="b" * 64,
            duration_gate_summary={"fits_budget": 1},
        )
        item = manifest["current_outputs"]["joined_narration"][0]
        self.assertEqual(manifest["manifest_version"], "RENDER_PREP_MANIFEST_V2")
        self.assertEqual(item["sha256"], "a" * 64)
        self.assertEqual(item["duration_seconds"], 3.0)
        self.assertNotIn("absolute_path", str(item))
        self.assertEqual(manifest["audio_review"]["status"], "PENDING_AUDIO_REVIEW")
        self.assertEqual(manifest["input_authority"]["translation_input_sha256"], "b" * 64)
        self.assertEqual(manifest["duration_gate_summary"], {"fits_budget": 1})


class VoiceRateSampleTests(unittest.TestCase):
    def test_uses_only_matching_provider_voice_and_rate(self) -> None:
        matching = SimpleNamespace(
            metadata_json={
                "provider": {
                    "provider": "omnivoice",
                    "voice_id": "voice-a",
                    "speaking_rate": 1.0,
                },
                "speech_budget": {
                    "spoken_units": 20,
                    "observed_audio_duration_seconds": 5.0,
                },
            }
        )
        wrong_voice = SimpleNamespace(
            metadata_json={
                "provider": {
                    "provider": "omnivoice",
                    "voice_id": "voice-b",
                    "speaking_rate": 1.0,
                },
                "speech_budget": {
                    "spoken_units": 30,
                    "observed_audio_duration_seconds": 5.0,
                },
            }
        )
        samples = _voice_rate_samples(
            [matching, wrong_voice],
            provider_name="omnivoice",
            voice_config=VoiceConfig(voice_id="voice-a", speaking_rate=1.0),
        )
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0].spoken_units, 20)


if __name__ == "__main__":
    unittest.main()
