"""Cheap post-transfer QA for authoritative source media."""

from __future__ import annotations

from typing import Any


POST_DOWNLOAD_QA_VERSION = "post-download-qa-v1"


def evaluate_post_download_qa(
    probe: object,
    *,
    advertised_width: int | None = None,
    advertised_height: int | None = None,
    advertised_codec: str | None = None,
    advertised_fps: float | None = None,
    expected_duration_seconds: float | None = None,
    expect_audio: bool | None = None,
) -> dict[str, Any]:
    """Compare the selected candidate's claims with measured ffprobe output.

    The gate is intentionally cheap: it reuses the mandatory ffprobe result and
    does not decode extra frames on the critical path. Measured media validity
    remains enforced by DownloadService before this summary is produced.
    """

    measured_width = _positive_int(getattr(probe, "width", None))
    measured_height = _positive_int(getattr(probe, "height", None))
    measured_fps = _positive_float(getattr(probe, "fps", None))
    measured_codec = _codec(getattr(probe, "video_codec", None))
    warnings: list[str] = []

    advertised_pixels = _positive_int(advertised_width) * _positive_int(advertised_height)
    measured_pixels = measured_width * measured_height
    if advertised_pixels > 0 and measured_pixels > 0 and measured_pixels < advertised_pixels * 0.9:
        warnings.append("measured_resolution_below_advertised")
    normalized_advertised_codec = _codec(advertised_codec)
    if normalized_advertised_codec and measured_codec and normalized_advertised_codec != measured_codec:
        warnings.append("measured_codec_differs_from_advertised")
    advertised_fps_value = _positive_float(advertised_fps)
    if advertised_fps_value and measured_fps and abs(measured_fps - advertised_fps_value) > 1.0:
        warnings.append("measured_fps_differs_from_advertised")
    measured_duration = _positive_float(getattr(probe, "duration_seconds", None))
    expected_duration = _positive_float(expected_duration_seconds)
    if expected_duration and measured_duration:
        tolerance = max(0.25, expected_duration * 0.02)
        if abs(measured_duration - expected_duration) > tolerance:
            warnings.append("measured_duration_differs_from_expected")
    audio_codec = _codec(getattr(probe, "audio_codec", None))
    if expect_audio is True and not audio_codec:
        warnings.append("expected_audio_stream_missing")

    return {
        "schema_version": POST_DOWNLOAD_QA_VERSION,
        "status": "WARN" if warnings else "PASS",
        "warnings": warnings,
        "measured": {
            "width": measured_width or None,
            "height": measured_height or None,
            "fps": measured_fps or None,
            "video_codec": measured_codec or None,
            "audio_codec": _codec(getattr(probe, "audio_codec", None)) or None,
            "duration_seconds": measured_duration or None,
            "audio_present": bool(audio_codec),
        },
        "advertised": {
            "width": _positive_int(advertised_width) or None,
            "height": _positive_int(advertised_height) or None,
            "fps": advertised_fps_value or None,
            "video_codec": normalized_advertised_codec or None,
            "duration_seconds": expected_duration or None,
            "expect_audio": expect_audio,
        },
    }


def _positive_int(value: object) -> int:
    try:
        parsed = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _positive_float(value: object) -> float:
    try:
        parsed = float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed > 0 else 0.0


def _codec(value: object) -> str:
    raw = str(value or "").strip().lower()
    if any(token in raw for token in ("h264", "avc")):
        return "h264"
    if any(token in raw for token in ("h265", "hevc", "bytevc")):
        return "hevc"
    if "av1" in raw or "av01" in raw:
        return "av1"
    return raw
