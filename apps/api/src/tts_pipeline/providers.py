from __future__ import annotations

import math
import struct
import wave
from io import BytesIO
from typing import Protocol

from src.tts_pipeline.types import TtsProviderInput, TtsProviderOutput


class TtsProvider(Protocol):
    provider_name: str

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        ...


class PlaceholderToneTtsProvider:
    provider_name = "placeholder_tone_tts"

    def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
        duration = _estimate_duration_seconds(request.text, request.voice_config.speaking_rate)
        audio = _build_tone_wav(duration_seconds=duration)
        warnings = ["provider_placeholder"]
        if request.target_duration_seconds and duration > request.target_duration_seconds * 1.2:
            warnings.append("tts_longer_than_slot")
        return TtsProviderOutput(
            audio_bytes=audio,
            duration_seconds=duration,
            mime_type="audio/wav",
            file_extension="wav",
            provider_metadata={
                "provider": self.provider_name,
                "voice_id": request.voice_config.voice_id,
                "speaking_rate": request.voice_config.speaking_rate,
            },
            warnings=warnings,
        )


def _estimate_duration_seconds(text: str, speaking_rate: float) -> float:
    normalized_rate = max(0.5, min(2.0, speaking_rate))
    return max(0.45, len(text.strip()) / (13.0 * normalized_rate))


def _build_tone_wav(*, duration_seconds: float, sample_rate: int = 8000) -> bytes:
    frames = max(1, int(duration_seconds * sample_rate))
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(frames):
            value = int(800 * math.sin(2 * math.pi * 220 * (index / sample_rate)))
            wav.writeframes(struct.pack("<h", value))
    return buffer.getvalue()
