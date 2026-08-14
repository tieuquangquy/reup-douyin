"""Measure how much real speech an audio file contains, using Silero VAD.

The dialogue lane used to rely on a single signal — "did ASR return text?" — which
cannot distinguish a music-only clip from a clip whose narration the ASR failed to
decode. This module supplies the independent measurement.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.audio_pipeline.demucs_runner import run_captured
from src.audio_pipeline.model_manager import get_silero_model

logger = logging.getLogger(__name__)

SILERO_SAMPLE_RATE = 16000
# soundfile/torchaudio read these directly; anything else (mp4, webm, m4a) needs ffmpeg.
DIRECT_READ_SUFFIXES = {".wav", ".flac", ".ogg", ".aiff", ".aif"}


def needs_audio_decode(audio_path: str) -> bool:
    return Path(audio_path).suffix.lower() not in DIRECT_READ_SUFFIXES


def _decode_to_wav(audio_path: str, work_dir: Path, *, ffmpeg_binary: str = "ffmpeg") -> Path:
    if shutil.which(ffmpeg_binary) is None:
        raise RuntimeError("ffmpeg binary not found on PATH; cannot decode audio for Silero VAD")
    wav_path = work_dir / "vad_input.wav"
    completed = run_captured(
        [
            ffmpeg_binary,
            "-y",
            "-i",
            audio_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SILERO_SAMPLE_RATE),
            str(wav_path),
        ]
    )
    if completed.returncode != 0 or not wav_path.exists():
        detail = (completed.stderr or completed.stdout or "ffmpeg decode failed").strip()
        raise RuntimeError(detail[:500])
    return wav_path


@dataclass(frozen=True)
class SpeechSummary:
    """Speech Silero actually found in the file."""

    speech_seconds: float
    audio_seconds: float
    segment_count: int
    speech_intervals: tuple[tuple[float, float], ...] = ()


def silero_is_importable() -> bool:
    try:
        import silero_vad  # noqa: F401

        return True
    except Exception:
        return False


def run_silero_speech_summary(audio_path: str) -> SpeechSummary:
    """Run Silero VAD on ``audio_path``; model weights ship with the package (no download)."""
    from silero_vad import get_speech_timestamps, read_audio

    model = get_silero_model()
    with tempfile.TemporaryDirectory(prefix="silero_vad_") as tmp:
        read_path = _decode_to_wav(audio_path, Path(tmp)) if needs_audio_decode(audio_path) else Path(audio_path)
        waveform = read_audio(str(read_path), sampling_rate=SILERO_SAMPLE_RATE)
    audio_seconds = len(waveform) / float(SILERO_SAMPLE_RATE)
    stamps = get_speech_timestamps(waveform, model, sampling_rate=SILERO_SAMPLE_RATE)
    speech_samples = sum(int(stamp["end"]) - int(stamp["start"]) for stamp in stamps)
    summary = SpeechSummary(
        speech_seconds=round(speech_samples / float(SILERO_SAMPLE_RATE), 3),
        audio_seconds=round(audio_seconds, 3),
        segment_count=len(stamps),
        speech_intervals=tuple(
            (
                round(float(stamp["start"]) / SILERO_SAMPLE_RATE, 3),
                round(float(stamp["end"]) / SILERO_SAMPLE_RATE, 3),
            )
            for stamp in stamps
        ),
    )
    logger.info(
        "silero_vad_measured",
        extra={
            "audio_path": audio_path,
            "speech_seconds": summary.speech_seconds,
            "audio_seconds": summary.audio_seconds,
            "segment_count": summary.segment_count,
        },
    )
    return summary
