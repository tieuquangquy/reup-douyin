"""Fail-closed timing decisions and pitch-preserving WAV fitting for TTS clips."""

from __future__ import annotations

import subprocess
import tempfile
import wave
from dataclasses import dataclass
from io import BytesIO
import math
from pathlib import Path
from typing import Callable

from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode


MAX_ATEMPO_SPEED = 1.15
SOFT_ATEMPO_SPEED = 1.07


@dataclass(frozen=True)
class TimingAdjustment:
    action: str
    ratio: float
    speed_factor: float | None = None
    blocked_reason: str | None = None
    quality_band: str = "no_speed_adjustment"


def timing_quality_band(
    ratio: float,
    *,
    soft_limit: float = SOFT_ATEMPO_SPEED,
    hard_limit: float = MAX_ATEMPO_SPEED,
) -> str:
    value = float(ratio)
    if value <= 1.0:
        return "no_speed_adjustment"
    if value <= float(soft_limit):
        return "natural_speed_adjustment"
    if value <= float(hard_limit):
        return "review_speed_adjustment"
    return "blocked_speed_adjustment"


def plan_timing_adjustment(
    actual_duration_seconds: float,
    budget_seconds: float,
    *,
    max_atempo_speed: float = MAX_ATEMPO_SPEED,
) -> TimingAdjustment:
    if budget_seconds <= 0 or actual_duration_seconds <= 0:
        return TimingAdjustment(
            action="block",
            ratio=999.0,
            blocked_reason="invalid_timing_budget",
            quality_band="blocked_speed_adjustment",
        )
    ratio = float(actual_duration_seconds) / float(budget_seconds)
    if ratio <= 1.0:
        return TimingAdjustment(
            action="keep_with_tail_silence",
            ratio=ratio,
            quality_band=timing_quality_band(ratio, hard_limit=max_atempo_speed),
        )
    if ratio <= float(max_atempo_speed):
        return TimingAdjustment(
            action="atempo",
            ratio=ratio,
            speed_factor=ratio,
            quality_band=timing_quality_band(ratio, hard_limit=max_atempo_speed),
        )
    return TimingAdjustment(
        action="block",
        ratio=ratio,
        blocked_reason="tts_exceeds_safe_atempo_limit",
        quality_band="blocked_speed_adjustment",
    )


def recommended_spoken_unit_limit(
    spoken_units: int,
    actual_duration_seconds: float,
    budget_seconds: float,
    *,
    max_speed: float,
) -> int:
    """Scale the measured provider result to a rewrite limit for the same voice."""

    if spoken_units <= 0 or actual_duration_seconds <= 0 or budget_seconds <= 0:
        return 0
    fit_fraction = (float(budget_seconds) * float(max_speed)) / float(
        actual_duration_seconds
    )
    return max(1, int(math.floor(float(spoken_units) * fit_fraction)))


def wav_duration_seconds(content: bytes) -> float:
    try:
        with wave.open(BytesIO(content), "rb") as handle:
            return handle.getnframes() / float(max(1, handle.getframerate()))
    except (wave.Error, EOFError) as exc:
        raise TtsPipelineError(
            TtsPipelineErrorCode.TTS_PROVIDER_FAILED,
            "TTS provider returned an invalid PCM WAV clip",
        ) from exc


class FfmpegWavTimingFitter:
    def __init__(
        self,
        *,
        ffmpeg_binary: str = "ffmpeg",
        run: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self._run = run or subprocess.run

    def fit(self, content: bytes, adjustment: TimingAdjustment) -> tuple[bytes, dict]:
        if adjustment.action != "atempo" or adjustment.speed_factor is None:
            return content, {
                "timing_adjustment": adjustment.action,
                "timing_quality_band": adjustment.quality_band,
            }
        factor = float(adjustment.speed_factor)
        if not 1.0 < factor <= MAX_ATEMPO_SPEED + 1e-9:
            raise TtsPipelineError(
                TtsPipelineErrorCode.TIMING_FIT_BLOCKED,
                "Unsafe TTS atempo factor",
            )
        with tempfile.TemporaryDirectory(prefix="tts_fit_") as temp_dir:
            input_path = Path(temp_dir) / "input.wav"
            output_path = Path(temp_dir) / "output.wav"
            input_path.write_bytes(content)
            command = [
                self.ffmpeg_binary,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(input_path),
                "-af",
                f"atempo={factor:.8f}",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ]
            completed = self._run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            if (
                completed.returncode != 0
                or not output_path.is_file()
                or output_path.stat().st_size <= 44
            ):
                raise TtsPipelineError(
                    TtsPipelineErrorCode.TIMING_FIT_BLOCKED,
                    "ffmpeg could not fit a TTS clip into its timeline slot",
                )
            fitted = output_path.read_bytes()
        return fitted, {
            "timing_adjustment": "atempo",
            "timing_quality_band": adjustment.quality_band,
            "atempo_factor": round(factor, 6),
            "duration_seconds": round(wav_duration_seconds(fitted), 6),
        }
