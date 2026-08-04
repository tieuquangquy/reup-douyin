"""Silero VAD must produce a real speech measurement, not an assumption.

Without it the pipeline has a single signal ("did ASR return text?") and cannot tell
a music-only clip from a clip whose narration the ASR failed to decode.
"""

from __future__ import annotations

import unittest

from src.audio_pipeline.providers import SileroVadProvider
from src.audio_pipeline.silero_vad_runner import SpeechSummary, needs_audio_decode


class FakeStorage:
    def resolve(self, key: str):
        return type("Resolved", (), {"absolute_path": f"C:/fake/{key}"})()


def _provider(runner, *, importable: bool = True) -> SileroVadProvider:
    return SileroVadProvider(storage=FakeStorage(), runner=runner, silero_importable=importable)


class AudioDecodeGateTests(unittest.TestCase):
    def test_container_video_must_be_decoded_before_vad(self) -> None:
        # SOURCE_VIDEO_RAW is the analyze input; soundfile cannot open mp4/webm, and a
        # silent decode failure would drop us back to "assume speech" for every video.
        self.assertTrue(needs_audio_decode("C:/media/clip.mp4"))
        self.assertTrue(needs_audio_decode("C:/media/clip.MP4"))
        self.assertTrue(needs_audio_decode("C:/media/clip.webm"))
        self.assertTrue(needs_audio_decode("C:/media/clip.m4a"))

    def test_plain_wav_is_read_directly(self) -> None:
        self.assertFalse(needs_audio_decode("C:/media/clip.wav"))
        self.assertFalse(needs_audio_decode("C:/media/clip.flac"))


class SileroVadProviderTests(unittest.TestCase):
    def test_narrated_clip_reports_measured_speech_ratio(self) -> None:
        runner = lambda _path: SpeechSummary(speech_seconds=37.3, audio_seconds=41.4, segment_count=12)

        result = _provider(runner).detect("audio/key.wav", duration_seconds=41.4)

        self.assertTrue(result.has_speech)
        self.assertAlmostEqual(result.speech_ratio or 0.0, 0.901, places=2)
        self.assertIn("silero_vad_executed", result.difficulty_flags)
        self.assertNotIn("vad_heuristic_assume_speech", result.difficulty_flags)
        self.assertEqual(result.metadata["speech_seconds"], 37.3)
        self.assertEqual(result.metadata["speech_segment_count"], 12)

    def test_music_only_clip_reports_no_speech(self) -> None:
        runner = lambda _path: SpeechSummary(speech_seconds=0.0, audio_seconds=48.6, segment_count=0)

        result = _provider(runner).detect("audio/key.wav", duration_seconds=48.6)

        self.assertFalse(result.has_speech)
        self.assertEqual(result.speech_ratio, 0.0)
        self.assertIn("no_speech_detected", result.difficulty_flags)
        self.assertIn("skip_dubbing", result.difficulty_flags)

    def test_speech_shorter_than_floor_is_not_dialogue(self) -> None:
        # A single cough/word does not justify a dubbing lane.
        runner = lambda _path: SpeechSummary(speech_seconds=0.3, audio_seconds=50.0, segment_count=1)

        result = _provider(runner).detect("audio/key.wav", duration_seconds=50.0)

        self.assertFalse(result.has_speech)
        self.assertIn("speech_below_threshold", result.difficulty_flags)

    def test_runner_failure_falls_back_without_claiming_measurement(self) -> None:
        def boom(_path):
            raise RuntimeError("model load failed")

        result = _provider(boom).detect("audio/key.wav", duration_seconds=50.0)

        self.assertTrue(result.has_speech, "Fallback must stay conservative and keep dubbing possible")
        self.assertIn("silero_failed", result.difficulty_flags)
        self.assertIn("vad_heuristic_assume_speech", result.difficulty_flags)
        self.assertNotIn("silero_vad_executed", result.difficulty_flags)

    def test_missing_dependency_falls_back(self) -> None:
        result = _provider(lambda _path: None, importable=False).detect("audio/key.wav", duration_seconds=50.0)

        self.assertTrue(result.has_speech)
        self.assertIn("silero_unavailable", result.difficulty_flags)
        self.assertNotIn("silero_vad_executed", result.difficulty_flags)


if __name__ == "__main__":
    unittest.main()
