"""Capability-driven H.264 encoder selection for the Phase 4 renderer.

The selected hardware encoder is verified by an actual FFmpeg smoke encode. A codec
listed by ``ffmpeg -encoders`` is not sufficient because the driver or hardware device
may still be unavailable at runtime.
"""

from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Callable, Sequence


SOFTWARE_ENCODER = "libx264"
HARDWARE_ENCODERS = frozenset(
    {"h264_nvenc", "h264_qsv", "h264_videotoolbox"}
)
SUPPORTED_ENCODERS = frozenset({SOFTWARE_ENCODER, *HARDWARE_ENCODERS})


@dataclass(frozen=True)
class EncoderProbeResult:
    encoder: str
    available: bool
    probe_kind: str
    elapsed_ms: int
    diagnostic: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class VideoEncoderSelection:
    requested_policy: str
    selected_encoder: str
    hardware: bool
    fallback_used: bool
    fallback_reason: str | None
    probes: tuple[EncoderProbeResult, ...]

    def to_dict(self) -> dict:
        return {
            "requested_policy": self.requested_policy,
            "selected_encoder": self.selected_encoder,
            "hardware": self.hardware,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "probes": [probe.to_dict() for probe in self.probes],
        }


EncoderProbe = Callable[[str], EncoderProbeResult]


def preferred_hardware_encoders(platform_name: str | None = None) -> tuple[str, ...]:
    system = str(platform_name or platform.system()).strip().casefold()
    if system == "darwin":
        return ("h264_videotoolbox",)
    if system == "windows":
        return ("h264_nvenc", "h264_qsv")
    return ("h264_nvenc", "h264_qsv")


def probe_ffmpeg_encoder(
    encoder: str,
    *,
    ffmpeg_binary: str = "ffmpeg",
    smoke_encode: bool = True,
    timeout_seconds: float = 15.0,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> EncoderProbeResult:
    started = time.perf_counter()
    if smoke_encode:
        command = [
            ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:r=8:d=0.5",
            "-frames:v",
            "4",
            "-an",
            "-c:v",
            str(encoder),
            "-pix_fmt",
            "yuv420p",
            "-f",
            "null",
            "-",
        ]
        probe_kind = "smoke_encode"
    else:
        command = [ffmpeg_binary, "-hide_banner", "-encoders"]
        probe_kind = "encoder_catalog"
    try:
        completed = run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(1.0, float(timeout_seconds)),
        )
        output = "\n".join(
            value for value in (completed.stderr, completed.stdout) if value
        )
        available = completed.returncode == 0 and (
            smoke_encode or str(encoder) in output
        )
        diagnostic = None if available else _safe_diagnostic(output)
    except subprocess.TimeoutExpired:
        available = False
        diagnostic = "probe_timeout"
    except OSError as exc:
        available = False
        diagnostic = f"probe_start_failed:{type(exc).__name__}"
    elapsed_ms = int(round((time.perf_counter() - started) * 1000.0))
    return EncoderProbeResult(
        encoder=str(encoder),
        available=available,
        probe_kind=probe_kind,
        elapsed_ms=max(0, elapsed_ms),
        diagnostic=diagnostic,
    )


def ffmpeg_runtime_version(
    ffmpeg_binary: str = "ffmpeg",
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    try:
        completed = run(
            [ffmpeg_binary, "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    first_line = str(completed.stdout or completed.stderr or "").splitlines()
    return first_line[0][:200] if completed.returncode == 0 and first_line else "unknown"


def select_video_encoder(
    policy: str = "auto",
    *,
    platform_name: str | None = None,
    probe: EncoderProbe | None = None,
) -> VideoEncoderSelection:
    requested = str(policy or "auto").strip().casefold()
    if requested in {"cpu", "software", "x264"}:
        requested = SOFTWARE_ENCODER
    if requested not in {"auto", *SUPPORTED_ENCODERS}:
        requested = "auto"
    probe_encoder = probe or (lambda name: probe_ffmpeg_encoder(name))
    candidates = (
        (*preferred_hardware_encoders(platform_name), SOFTWARE_ENCODER)
        if requested == "auto"
        else (requested, SOFTWARE_ENCODER)
        if requested != SOFTWARE_ENCODER
        else (SOFTWARE_ENCODER,)
    )
    results: list[EncoderProbeResult] = []
    for encoder in dict.fromkeys(candidates):
        result = probe_encoder(encoder)
        results.append(result)
        if result.available:
            fallback_used = encoder != requested and requested != "auto"
            fallback_reason = (
                f"requested_encoder_unavailable:{requested}"
                if fallback_used
                else "hardware_encoder_unavailable"
                if requested == "auto" and encoder == SOFTWARE_ENCODER
                else None
            )
            return VideoEncoderSelection(
                requested_policy=requested,
                selected_encoder=encoder,
                hardware=encoder in HARDWARE_ENCODERS,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                probes=tuple(results),
            )
    raise RuntimeError("No usable H.264 encoder passed the runtime probe")


def ffmpeg_video_encode_args(
    encoder: str,
    *,
    width: int,
    height: int,
) -> list[str]:
    name = str(encoder).strip().casefold()
    if name not in SUPPORTED_ENCODERS:
        raise ValueError(f"Unsupported video encoder: {encoder}")
    bitrate = max(4_000_000, min(20_000_000, int(width) * int(height) * 4))
    if name == "libx264":
        return [
            "-c:v",
            name,
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
        ]
    if name == "h264_nvenc":
        return [
            "-c:v",
            name,
            "-preset",
            "p5",
            "-rc",
            "vbr",
            "-cq",
            "20",
            "-b:v",
            "0",
            "-pix_fmt",
            "yuv420p",
        ]
    if name == "h264_qsv":
        return [
            "-c:v",
            name,
            "-preset",
            "medium",
            "-global_quality",
            "21",
            "-pix_fmt",
            "yuv420p",
        ]
    return [
        "-c:v",
        name,
        "-b:v",
        str(bitrate),
        "-pix_fmt",
        "yuv420p",
    ]


def _safe_diagnostic(output: str, *, limit: int = 240) -> str:
    compact = " ".join(str(output or "").split())
    return compact[-limit:] if compact else "encoder_probe_failed"


def is_video_copy_args(values: Sequence[str]) -> bool:
    normalized = [str(value).strip().casefold() for value in values]
    return normalized in (["-c:v", "copy"], ["-codec:v", "copy"])
