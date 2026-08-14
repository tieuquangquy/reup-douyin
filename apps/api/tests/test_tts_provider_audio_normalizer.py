from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.services.provider_audio_normalizer import (
    canonicalize_provider_audio,
)


def _wav_bytes(*, sample_rate: int = 24_000, frames: int = 2_400) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes((b"\x10\x00" * frames))
    return output.getvalue()


class ProviderAudioNormalizerTests(unittest.TestCase):
    def test_wav_fast_path_is_validated_without_ffmpeg(self) -> None:
        audio, duration, metadata = canonicalize_provider_audio(
            _wav_bytes(),
            mime_type="audio/wav",
            file_extension="wav",
        )

        self.assertTrue(audio.startswith(b"RIFF"))
        self.assertAlmostEqual(duration, 0.1, places=2)
        self.assertFalse(metadata["converted"])
        with wave.open(BytesIO(audio), "rb") as handle:
            self.assertEqual(handle.getframerate(), 48_000)
            self.assertEqual(handle.getnchannels(), 1)

    def test_mp3_transport_is_decoded_to_canonical_wav(self) -> None:
        decoded_wav = _wav_bytes()

        def fake_run(args, **_kwargs):
            Path(args[-1]).write_bytes(decoded_wav)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with (
            patch(
                "src.tts_pipeline.services.provider_audio_normalizer.shutil.which",
                return_value="ffmpeg",
            ),
            patch(
                "src.tts_pipeline.services.provider_audio_normalizer.subprocess.run",
                side_effect=fake_run,
            ) as run,
        ):
            audio, duration, metadata = canonicalize_provider_audio(
                b"ID3compressed-provider-audio",
                mime_type="audio/mpeg",
                file_extension="mp3",
            )

        self.assertEqual(run.call_count, 1)
        self.assertTrue(audio.startswith(b"RIFF"))
        self.assertAlmostEqual(duration, 0.1, places=2)
        self.assertTrue(metadata["converted"])
        self.assertEqual(metadata["source_format"], "mp3")

    def test_decode_failure_is_reported_as_provider_error(self) -> None:
        with (
            patch(
                "src.tts_pipeline.services.provider_audio_normalizer.shutil.which",
                return_value="ffmpeg",
            ),
            patch(
                "src.tts_pipeline.services.provider_audio_normalizer.subprocess.run",
                return_value=SimpleNamespace(
                    returncode=1,
                    stdout="",
                    stderr="invalid compressed payload",
                ),
            ),
        ):
            with self.assertRaises(TtsPipelineError) as caught:
                canonicalize_provider_audio(
                    b"ID3broken",
                    mime_type="audio/mpeg",
                    file_extension="mp3",
                )

        self.assertEqual(caught.exception.code, TtsPipelineErrorCode.TTS_PROVIDER_FAILED)
        self.assertIn("invalid compressed payload", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
