"""Lightweight audio/prosody execution QA with no model dependency."""

from __future__ import annotations

import math
import struct
import wave
from typing import Any, Mapping

from src.tts_pipeline.types import ProsodySegment


PROSODY_AUDIO_QA_VERSION = "prosody-audio-qa-v1"


def analyze_prosody_audio(
    audio_bytes: bytes,
    *,
    prosody: ProsodySegment | None,
    provider_metadata: Mapping[str, Any] | None,
) -> dict:
    metadata = dict(provider_metadata or {})
    execution = dict(metadata.get("execution_contract") or {})
    requested = set(execution.get("requested_features") or [])
    applied = set(execution.get("applied_features") or [])
    warnings: list[str] = []
    if prosody is not None and prosody.emotion != "neutral":
        if "emotion" in requested and "emotion" not in applied:
            warnings.append("prosody_emotion_not_applied")
        elif not execution:
            warnings.append("prosody_execution_contract_missing")

    rms_dbfs = None
    zero_crossing_rate = None
    duration_seconds = None
    try:
        with wave.open(__import__("io").BytesIO(audio_bytes), "rb") as handle:
            frame_count = handle.getnframes()
            sample_rate = max(1, int(handle.getframerate()))
            channels = max(1, int(handle.getnchannels()))
            width = int(handle.getsampwidth())
            raw = handle.readframes(frame_count)
        if width == 2 and raw:
            values = struct.unpack("<" + "h" * (len(raw) // 2), raw)
            mono = values[::channels]
            if mono:
                rms = math.sqrt(sum(float(value) ** 2 for value in mono) / len(mono))
                rms_dbfs = round(20.0 * math.log10(max(rms / 32768.0, 1e-9)), 4)
                crossings = sum(
                    1 for left, right in zip(mono, mono[1:]) if (left < 0 <= right) or (left >= 0 > right)
                )
                zero_crossing_rate = round(crossings / max(1e-9, len(mono) / sample_rate), 4)
                duration_seconds = round(len(mono) / sample_rate, 6)
    except (OSError, EOFError, ValueError, struct.error, wave.Error):
        warnings.append("prosody_audio_metrics_unavailable")

    return {
        "schema_version": PROSODY_AUDIO_QA_VERSION,
        "execution_verified": not any(
            warning in {"prosody_emotion_not_applied", "prosody_execution_contract_missing"}
            for warning in warnings
        ),
        "requested_features": sorted(requested),
        "applied_features": sorted(applied),
        "rms_dbfs": rms_dbfs,
        "zero_crossing_rate_per_second": zero_crossing_rate,
        "duration_seconds": duration_seconds,
        "warnings": list(dict.fromkeys(warnings)),
    }
