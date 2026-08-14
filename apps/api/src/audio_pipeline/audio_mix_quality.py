"""Cheap, model-free signal features for the adaptive separation gate."""

from __future__ import annotations

import math
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class AudioMixQuality:
    rms_dbfs: float
    clipping_ratio: float
    spectral_flatness: float
    voice_band_ratio: float
    sampled_seconds: float
    separation_recommended: bool

    def to_dict(self) -> dict:
        return asdict(self)


def analyze_pcm_wav_mix(
    path: str | Path,
    *,
    max_sample_seconds: float = 24.0,
) -> AudioMixQuality:
    """Measure a few evenly-spaced windows without decoding the WAV again."""
    with wave.open(str(path), "rb") as handle:
        channels = int(handle.getnchannels())
        sample_rate = int(handle.getframerate())
        sample_width = int(handle.getsampwidth())
        total_frames = int(handle.getnframes())
        if sample_width != 2 or sample_rate <= 0 or total_frames <= 0:
            raise ValueError("adaptive_mix_quality_requires_pcm16_wav")
        window_frames = max(1, min(total_frames, int(sample_rate * 4.0)))
        window_count = max(1, min(6, int(math.ceil(max_sample_seconds / 4.0))))
        last_start = max(0, total_frames - window_frames)
        starts = sorted(set(int(value) for value in np.linspace(0, last_start, num=window_count, dtype=np.int64)))
        chunks: list[np.ndarray] = []
        for start in starts:
            handle.setpos(int(start))
            raw = handle.readframes(window_frames)
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
            if channels > 1 and samples.size >= channels:
                samples = samples[: samples.size - (samples.size % channels)]
                samples = samples.reshape(-1, channels).mean(axis=1)
            if samples.size:
                chunks.append(samples / 32768.0)
    if not chunks:
        raise ValueError("adaptive_mix_quality_empty_wav")
    signal = np.concatenate(chunks)
    rms = float(np.sqrt(np.mean(np.square(signal), dtype=np.float64)))
    rms_dbfs = 20.0 * math.log10(max(rms, 1e-9))
    clipping_ratio = float(np.mean(np.abs(signal) >= 0.995))

    frame_size = 2048
    usable = signal[: signal.size - (signal.size % frame_size)]
    if usable.size < frame_size:
        usable = np.pad(signal, (0, max(0, frame_size - signal.size)))
    frames = usable.reshape(-1, frame_size)
    window = np.hanning(frame_size).astype(np.float32)
    power = np.square(np.abs(np.fft.rfft(frames * window, axis=1))) + 1e-12
    flatness = np.exp(np.mean(np.log(power), axis=1)) / np.mean(power, axis=1)
    spectral_flatness = float(np.median(flatness))
    frequencies = np.fft.rfftfreq(frame_size, d=1.0 / sample_rate)
    voice_mask = (frequencies >= 250.0) & (frequencies <= 3800.0)
    voice_band_ratio = float(np.median(power[:, voice_mask].sum(axis=1) / power.sum(axis=1)))
    recommended = bool(
        clipping_ratio > 0.01
        or spectral_flatness > 0.42
        or voice_band_ratio < 0.34
        or rms_dbfs < -42.0
    )
    return AudioMixQuality(
        rms_dbfs=round(rms_dbfs, 3),
        clipping_ratio=round(clipping_ratio, 6),
        spectral_flatness=round(spectral_flatness, 5),
        voice_band_ratio=round(voice_band_ratio, 5),
        sampled_seconds=round(signal.size / sample_rate, 3),
        separation_recommended=recommended,
    )
