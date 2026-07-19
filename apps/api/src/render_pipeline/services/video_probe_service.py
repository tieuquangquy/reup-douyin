from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from src.render_pipeline.errors import RenderPipelineError, RenderPipelineErrorCode
from src.render_pipeline.types import VideoProbe
from src.storage.base import StorageBackend

logger = logging.getLogger(__name__)


def parse_ffprobe_payload(payload: dict) -> VideoProbe:
    streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
    video = next((s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if isinstance(s, dict) and s.get("codec_type") == "audio"), None)
    fmt = payload.get("format") if isinstance(payload.get("format"), dict) else {}

    width = _as_positive_int((video or {}).get("width"))
    height = _as_positive_int((video or {}).get("height"))
    fps = _parse_frame_rate((video or {}).get("avg_frame_rate")) or _parse_frame_rate((video or {}).get("r_frame_rate"))
    duration = _as_positive_float(fmt.get("duration"))
    if duration is None and video:
        duration = _as_positive_float(video.get("duration"))

    return VideoProbe(
        width=width,
        height=height,
        fps=fps,
        duration_seconds=duration,
        video_codec=_as_codec((video or {}).get("codec_name")),
        audio_codec=_as_codec((audio or {}).get("codec_name")),
        raw={"probe_strategy": "ffprobe", "streams": len(streams)},
    )


def _as_positive_int(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _as_positive_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _as_codec(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _parse_frame_rate(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if not isinstance(value, str) or not value or value in {"0/0", "N/A"}:
        return None
    if "/" in value:
        left, right = value.split("/", 1)
        try:
            num = float(left)
            den = float(right)
        except ValueError:
            return None
        if den == 0:
            return None
        rate = num / den
        return rate if rate > 0 else None
    return _as_positive_float(value)


class VideoProbeService:
    def __init__(self, storage: StorageBackend, *, ffprobe_binary: str = "ffprobe"):
        self.storage = storage
        self.ffprobe_binary = ffprobe_binary

    def probe(self, storage_key: str) -> VideoProbe:
        metadata = self.storage.metadata(storage_key)
        if not metadata.exists or not metadata.size_bytes:
            raise RenderPipelineError(
                RenderPipelineErrorCode.PROBE_FAILED,
                f"Cannot probe missing or empty asset: {storage_key}",
            )
        absolute = Path(getattr(metadata, "absolute_path", None) or self.storage.resolve(storage_key).absolute_path)
        suffix = Path(storage_key).suffix.lower().lstrip(".")
        try:
            payload = self._run_ffprobe(absolute)
            probe = parse_ffprobe_payload(payload)
            return VideoProbe(
                width=probe.width,
                height=probe.height,
                fps=probe.fps,
                duration_seconds=probe.duration_seconds,
                video_codec=probe.video_codec or suffix or None,
                audio_codec=probe.audio_codec,
                raw={
                    **probe.raw,
                    "storage_key": storage_key,
                    "size_bytes": metadata.size_bytes,
                },
            )
        except Exception as exc:
            logger.warning(
                "video_probe_ffprobe_failed",
                extra={"storage_key": storage_key, "error": str(exc)[:240]},
            )
            return VideoProbe(
                width=None,
                height=None,
                fps=None,
                duration_seconds=None,
                video_codec=suffix or None,
                audio_codec=None,
                raw={
                    "storage_key": storage_key,
                    "size_bytes": metadata.size_bytes,
                    "probe_strategy": "storage_metadata_fallback",
                    "probe_error": str(exc)[:240],
                },
            )

    def _run_ffprobe(self, path: Path) -> dict:
        binary = shutil.which(self.ffprobe_binary) or self.ffprobe_binary
        completed = subprocess.run(
            [
                binary,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "ffprobe failed").strip()
            raise RuntimeError(detail[:400])
        payload = json.loads(completed.stdout or "{}")
        if not isinstance(payload, dict):
            raise RuntimeError("ffprobe returned non-object JSON")
        return payload
