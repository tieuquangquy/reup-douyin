"""Loudness normalisation for the delivered render.

Dub volume varies with the voice and the line, background music varies with the source, and
nothing downstream evens them out. Viewers scrolling a feed notice the jumps immediately
even though a single clip sounds fine, so the fix belongs at the one place where the
deliverable's audio is encoded rather than in each producing stage.

This is single-pass `loudnorm`: less exact than the two-pass measurement, but it costs
nothing extra in render time and removes the large differences that actually get noticed.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.core.settings import get_settings

# Common target for short-form social video; quiet enough to leave headroom for music.
DEFAULT_TARGET_LUFS = -14.0
# Keep a margin below 0 dBTP so lossy encoding cannot clip.
DEFAULT_TRUE_PEAK_DB = -1.5
# AAC may add inter-sample overshoot after the PCM loudnorm pass.  Reserve an
# extra 1.2 dB during measured final normalization so the encoded deliverable,
# rather than only the intermediate waveform, keeps the -1.5 dBTP intent.
TWO_PASS_ENCODE_TRUE_PEAK_DB = DEFAULT_TRUE_PEAK_DB - 1.2
DEFAULT_LOUDNESS_RANGE = 11.0
DEFAULT_BACKGROUND_MIX_GAIN = 1.0
TWO_PASS_LOUDNESS_POLICY_VERSION = "two_pass_loudnorm_aac_headroom_v1"


class LoudnessMeasurementError(RuntimeError):
    """Raised when an approved audio source cannot produce two-pass authority."""


def loudness_normalization_enabled(settings: object | None = None) -> bool:
    cfg = settings if settings is not None else get_settings()
    return bool(getattr(cfg, "render_loudness_normalization_enabled", True))


def loudness_target_lufs(settings: object | None = None) -> float:
    cfg = settings if settings is not None else get_settings()
    try:
        target = float(getattr(cfg, "render_loudness_target_lufs", DEFAULT_TARGET_LUFS))
    except (TypeError, ValueError):
        return DEFAULT_TARGET_LUFS
    # LUFS targets are negative; a positive value is a typo that would blow out every render.
    if not (-40.0 <= target < 0.0):
        return DEFAULT_TARGET_LUFS
    return target


def build_loudnorm_filter(
    *,
    target_lufs: float,
    true_peak_db: float = DEFAULT_TRUE_PEAK_DB,
    loudness_range: float = DEFAULT_LOUDNESS_RANGE,
) -> str:
    return f"loudnorm=I={target_lufs:g}:TP={true_peak_db:g}:LRA={loudness_range:g}"


def loudness_filter_args(settings: object | None = None) -> list[str]:
    """ffmpeg arguments that normalise the audio track, or nothing when disabled."""
    cfg = settings if settings is not None else get_settings()
    if not loudness_normalization_enabled(cfg):
        return []
    return ["-af", build_loudnorm_filter(target_lufs=loudness_target_lufs(cfg))]


def measure_loudnorm_first_pass(
    audio_path: str | Path,
    *,
    target_lufs: float,
    true_peak_db: float = DEFAULT_TRUE_PEAK_DB,
    loudness_range: float = DEFAULT_LOUDNESS_RANGE,
    ffmpeg_binary: str = "ffmpeg",
    run: Callable[..., Any] = subprocess.run,
) -> dict[str, float]:
    """Measure the exact input values required by FFmpeg loudnorm pass two."""

    path = Path(audio_path)
    if not path.is_file():
        raise LoudnessMeasurementError("Approved audio source is missing")
    command = [
        ffmpeg_binary,
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-vn",
        "-af",
        (
            f"loudnorm=I={float(target_lufs):g}:TP={float(true_peak_db):g}:"
            f"LRA={float(loudness_range):g}:print_format=json"
        ),
        "-f",
        "null",
        "-",
    ]
    completed = run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    combined = "\n".join((completed.stdout or "", completed.stderr or ""))
    matches = re.findall(r'\{\s*"input_i".*?\}', combined, flags=re.DOTALL)
    if completed.returncode != 0 or not matches:
        raise LoudnessMeasurementError("FFmpeg loudness measurement failed")
    try:
        raw = json.loads(matches[-1])
        measured = {
            "input_i": float(raw["input_i"]),
            "input_tp": float(raw["input_tp"]),
            "input_lra": float(raw["input_lra"]),
            "input_thresh": float(raw["input_thresh"]),
            "target_offset": float(raw["target_offset"]),
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise LoudnessMeasurementError("FFmpeg loudness measurement is invalid") from exc
    if not all(math.isfinite(value) for value in measured.values()):
        raise LoudnessMeasurementError("FFmpeg loudness measurement is non-finite")
    return measured


def build_two_pass_loudnorm_filter(
    measured: dict[str, float],
    *,
    target_lufs: float,
    true_peak_db: float = DEFAULT_TRUE_PEAK_DB,
    loudness_range: float = DEFAULT_LOUDNESS_RANGE,
) -> str:
    """Build deterministic pass-two parameters from a completed first pass."""

    return (
        f"loudnorm=I={float(target_lufs):g}:TP={float(true_peak_db):g}:"
        f"LRA={float(loudness_range):g}:"
        f"measured_I={float(measured['input_i']):g}:"
        f"measured_TP={float(measured['input_tp']):g}:"
        f"measured_LRA={float(measured['input_lra']):g}:"
        f"measured_thresh={float(measured['input_thresh']):g}:"
        f"offset={float(measured['target_offset']):g}:linear=true"
    )


def two_pass_loudness_filter_args(
    audio_path: str | Path,
    *,
    settings: object | None = None,
    ffmpeg_binary: str = "ffmpeg",
    run: Callable[..., Any] = subprocess.run,
) -> list[str]:
    """Return a measured pass-two filter, or no filter when normalization is off."""

    cfg = settings if settings is not None else get_settings()
    if not loudness_normalization_enabled(cfg):
        return []
    target = loudness_target_lufs(cfg)
    measured = measure_loudnorm_first_pass(
        audio_path,
        target_lufs=target,
        true_peak_db=TWO_PASS_ENCODE_TRUE_PEAK_DB,
        ffmpeg_binary=ffmpeg_binary,
        run=run,
    )
    return [
        "-af",
        build_two_pass_loudnorm_filter(
            measured,
            target_lufs=target,
            true_peak_db=TWO_PASS_ENCODE_TRUE_PEAK_DB,
        ),
    ]


def background_mix_gain(settings: object | None = None) -> float:
    cfg = settings if settings is not None else get_settings()
    try:
        value = float(
            getattr(cfg, "render_background_mix_gain", DEFAULT_BACKGROUND_MIX_GAIN)
        )
    except (TypeError, ValueError):
        return DEFAULT_BACKGROUND_MIX_GAIN
    return max(0.0, min(1.0, value))
