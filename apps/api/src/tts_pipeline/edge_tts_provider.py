from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
import wave
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from src.tts_pipeline.catalog import VIENEU_CURATED_VOICES
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput

logger = logging.getLogger(__name__)

DEFAULT_EDGE_TTS_VOICE = "vi-VN-HoaiMyNeural"
LEGACY_PLACEHOLDER_VOICES = frozenset({"", "vi_female_placeholder", "vi_male_placeholder"})
VIENEU_DISPLAY_VOICES = frozenset(voice_id for _, voice_id in VIENEU_CURATED_VOICES)

SynthesizeAudioFn = Callable[..., tuple[bytes, float]]


class EdgeTtsProvider:
    """Vietnamese neural TTS via Microsoft Edge online voices (edge-tts)."""

    provider_name = "edge_tts"

    def __init__(
        self,
        *,
        synthesize_audio: SynthesizeAudioFn | None = None,
        ffmpeg_binary: str = "ffmpeg",
    ):
        self._synthesize_audio = synthesize_audio
        self.ffmpeg_binary = ffmpeg_binary

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        text = (request.text or "").strip()
        if not text:
            raise TtsPipelineError(TtsPipelineErrorCode.TTS_PROVIDER_FAILED, "TTS text is empty")

        voice_id = resolve_edge_voice_id(request.voice_config.voice_id)
        speaking_rate = max(0.5, min(2.0, float(request.voice_config.speaking_rate or 1.0)))

        try:
            if self._synthesize_audio is not None:
                audio_bytes, duration_seconds = self._synthesize_audio(
                    text=text,
                    voice_id=voice_id,
                    speaking_rate=speaking_rate,
                )
            else:
                audio_bytes, duration_seconds = self._synthesize_via_edge_tts(
                    text=text,
                    voice_id=voice_id,
                    speaking_rate=speaking_rate,
                )
        except TtsPipelineError:
            raise
        except Exception as exc:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                f"edge-tts failed: {exc}",
            ) from exc

        if not audio_bytes or not audio_bytes.startswith(b"RIFF"):
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                "edge-tts did not produce a valid WAV clip (is ffmpeg on PATH?)",
            )

        warnings: list[str] = []
        if request.target_duration_seconds and duration_seconds > request.target_duration_seconds * 1.2:
            warnings.append("tts_longer_than_slot")

        return TtsProviderOutput(
            audio_bytes=audio_bytes,
            duration_seconds=duration_seconds,
            mime_type="audio/wav",
            file_extension="wav",
            provider_metadata={
                "provider": self.provider_name,
                "voice_id": voice_id,
                "speaking_rate": speaking_rate,
            },
            warnings=warnings,
        )

    def _synthesize_via_edge_tts(self, *, text: str, voice_id: str, speaking_rate: float) -> tuple[bytes, float]:
        try:
            import edge_tts  # type: ignore
        except ImportError as exc:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                "edge-tts package is not installed. Run: pip install edge-tts",
            ) from exc

        if shutil.which(self.ffmpeg_binary) is None:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
                "ffmpeg binary not found on PATH; required to convert edge-tts MP3 to WAV",
            )

        rate = _edge_rate_string(speaking_rate)
        with tempfile.TemporaryDirectory(prefix="edge-tts-") as tmp:
            mp3_path = Path(tmp) / "clip.mp3"
            wav_path = Path(tmp) / "clip.wav"
            communicate = edge_tts.Communicate(text, voice_id, rate=rate)
            asyncio.run(communicate.save(str(mp3_path)))
            if not mp3_path.is_file() or mp3_path.stat().st_size <= 0:
                raise TtsPipelineError(TtsPipelineErrorCode.TTS_PROVIDER_FAILED, "edge-tts produced empty audio")
            _ffmpeg_mp3_to_wav(mp3_path, wav_path, ffmpeg_binary=self.ffmpeg_binary)
            audio_bytes = wav_path.read_bytes()
            duration_seconds = _wav_duration_seconds(audio_bytes)
            return audio_bytes, duration_seconds


def resolve_edge_voice_id(voice_id: str | None) -> str:
    value = (voice_id or "").strip()
    if not value or value in LEGACY_PLACEHOLDER_VOICES:
        return DEFAULT_EDGE_TTS_VOICE
    # VieNeu display names (and other non-edge ids) must not be sent to edge-tts.
    if value in VIENEU_DISPLAY_VOICES or not _looks_like_edge_voice(value):
        return DEFAULT_EDGE_TTS_VOICE
    return value


def _looks_like_edge_voice(voice_id: str) -> bool:
    # Microsoft neural ids look like vi-VN-HoaiMyNeural / en-US-JennyNeural.
    if " " in voice_id:
        return False
    return "Neural" in voice_id or voice_id.startswith("vi-VN-")


def _edge_rate_string(speaking_rate: float) -> str:
    pct = int(round((speaking_rate - 1.0) * 100))
    return f"{pct:+d}%"


def _ffmpeg_mp3_to_wav(mp3_path: Path, wav_path: Path, *, ffmpeg_binary: str) -> None:
    completed = subprocess.run(
        [
            ffmpeg_binary,
            "-y",
            "-i",
            str(mp3_path),
            "-ac",
            "1",
            "-ar",
            "24000",
            str(wav_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not wav_path.is_file():
        detail = (completed.stderr or completed.stdout or "ffmpeg convert failed").strip()
        raise TtsPipelineError(TtsPipelineErrorCode.TTS_PROVIDER_FAILED, f"ffmpeg MP3→WAV failed: {detail[:400]}")


def _wav_duration_seconds(content: bytes) -> float:
    with wave.open(BytesIO(content), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate() or 1
        return max(0.05, frames / float(rate))
