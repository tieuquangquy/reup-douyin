"""Fast local waveform checks and click-safe clip edge conditioning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
import math
import wave

import numpy as np

from src.tts_pipeline.services.narration_assembler import (
    AUTHORITY_SAMPLE_RATE,
    normalize_wav_bytes,
)


WAVEFORM_QA_VERSION = "tts_waveform_qa_v1"


@dataclass(frozen=True)
class WaveformQaResult:
    qa_version: str
    duration_seconds: float
    peak_dbfs: float
    rms_dbfs: float
    dc_offset_ratio: float
    clipped_sample_ratio: float
    silence_ratio: float
    valid_speech_audio: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return payload


def apply_edge_fades(content: bytes, *, fade_ms: int = 6) -> tuple[bytes, dict]:
    """Apply a tiny equal-power fade to prevent clip-boundary clicks."""

    normalized, duration = normalize_wav_bytes(content)
    pcm = _read_pcm(normalized)
    frames = min(len(pcm) // 2, max(0, int(round(AUTHORITY_SAMPLE_RATE * fade_ms / 1000.0))))
    if frames <= 1:
        return normalized, {"applied": False, "fade_ms": 0, "duration_seconds": duration}
    curve = np.sin(np.linspace(0.0, math.pi / 2.0, frames, dtype=np.float64))
    output = pcm.astype(np.float64)
    output[:frames] *= curve
    output[-frames:] *= curve[::-1]
    conditioned = _write_pcm(np.rint(output).astype("<i2"))
    return conditioned, {
        "applied": True,
        "fade_ms": int(fade_ms),
        "fade_frames": frames,
        "duration_seconds": round(duration, 6),
    }


def analyze_waveform(content: bytes) -> WaveformQaResult:
    normalized, duration = normalize_wav_bytes(content)
    pcm = _read_pcm(normalized).astype(np.float64)
    absolute = np.abs(pcm)
    peak = float(np.max(absolute)) if len(pcm) else 0.0
    rms = float(np.sqrt(np.mean(np.square(pcm)))) if len(pcm) else 0.0
    peak_dbfs = _dbfs(peak)
    rms_dbfs = _dbfs(rms)
    dc_offset_ratio = abs(float(np.mean(pcm))) / 32768.0 if len(pcm) else 1.0
    clipped_ratio = float(np.mean(absolute >= 32760.0)) if len(pcm) else 1.0
    silence_ratio = float(np.mean(absolute < 180.0)) if len(pcm) else 1.0
    warnings: list[str] = []
    if rms_dbfs < -48.0 or silence_ratio > 0.985:
        warnings.append("tts_waveform_near_silent")
    if clipped_ratio > 0.001:
        warnings.append("tts_waveform_clipping_detected")
    if dc_offset_ratio > 0.02:
        warnings.append("tts_waveform_dc_offset_detected")
    if peak_dbfs < -24.0:
        warnings.append("tts_waveform_low_peak")
    valid = bool(duration > 0.05 and rms_dbfs >= -55.0 and silence_ratio <= 0.995)
    return WaveformQaResult(
        qa_version=WAVEFORM_QA_VERSION,
        duration_seconds=round(duration, 6),
        peak_dbfs=round(peak_dbfs, 4),
        rms_dbfs=round(rms_dbfs, 4),
        dc_offset_ratio=round(dc_offset_ratio, 8),
        clipped_sample_ratio=round(clipped_ratio, 8),
        silence_ratio=round(silence_ratio, 8),
        valid_speech_audio=valid,
        warnings=tuple(warnings),
    )


def _dbfs(value: float) -> float:
    if value <= 0:
        return -120.0
    return 20.0 * math.log10(value / 32768.0)


def _read_pcm(content: bytes) -> np.ndarray:
    with wave.open(BytesIO(content), "rb") as handle:
        return np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2").copy()


def _write_pcm(pcm: np.ndarray) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(AUTHORITY_SAMPLE_RATE)
        handle.writeframes(pcm.astype("<i2").tobytes())
    return output.getvalue()
