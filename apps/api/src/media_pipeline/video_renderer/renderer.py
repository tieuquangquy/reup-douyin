"""Single-pass FFmpeg renderer: mask + Vietnamese burn-in + anti-detection."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from src.media_pipeline.video_renderer.errors import VideoRendererError, VideoRendererErrorCode
from src.media_pipeline.video_renderer.filter_graph import (
    build_single_render_filter,
    wrap_filter_complex,
)
from src.media_pipeline.video_renderer.fonts import resolve_drawtext_font
from src.media_pipeline.video_renderer.overlays import (
    DEFAULT_HOLD_MS,
    OverlaySegment,
    overlays_from_ocr_payload,
)

logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"time=(\d{2}):(\d{2}):(\d{2}\.\d+)")
ProgressCallback = Callable[[float | None, str], None]


def _parse_ffmpeg_time_seconds(line: str) -> float | None:
    match = _TIME_RE.search(line)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _default_progress(seconds: float | None, raw: str) -> None:
    if seconds is None:
        return
    # Simple single-line progress (no total duration required).
    msg = f"\rffmpeg render time={seconds:7.2f}s"
    print(msg, end="", file=sys.stderr, flush=True)


def _frame_size_from_ocr_payload(
    ocr_payload: Mapping[str, Any] | list[Mapping[str, Any]] | None,
) -> tuple[int, int] | None:
    if ocr_payload is None:
        return None
    frames = ocr_payload if isinstance(ocr_payload, list) else list(ocr_payload.get("frames") or [])
    for frame in frames:
        if not isinstance(frame, Mapping):
            continue
        width = int(frame.get("frame_width") or 0)
        height = int(frame.get("frame_height") or 0)
        if width >= 2 and height >= 2:
            return width, height
    return None


def probe_video_frame_size(
    source_video: Path,
    *,
    ffmpeg_binary: str = "ffmpeg",
) -> tuple[int, int]:
    """Return (width, height) via ffprobe next to ffmpeg, or raise."""
    ffprobe = "ffprobe"
    which_ffmpeg = shutil.which(ffmpeg_binary)
    if which_ffmpeg:
        sibling = Path(which_ffmpeg).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if sibling.is_file():
            ffprobe = str(sibling)
        else:
            found = shutil.which("ffprobe")
            if found:
                ffprobe = found
    else:
        found = shutil.which("ffprobe")
        if found:
            ffprobe = found

    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(source_video),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "ffprobe failed").strip()
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"Could not probe video size for delogo: {detail[:300]}",
        )
    try:
        payload = json.loads(completed.stdout or "{}")
        stream = (payload.get("streams") or [{}])[0]
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"Could not parse ffprobe size: {exc}",
        ) from exc
    if width < 2 or height < 2:
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"Invalid probed frame size {width}x{height}",
        )
    return width, height


def _resolve_ffprobe_binary(ffmpeg_binary: str = "ffmpeg") -> str:
    ffprobe = "ffprobe"
    which_ffmpeg = shutil.which(ffmpeg_binary)
    if which_ffmpeg:
        sibling = Path(which_ffmpeg).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if sibling.is_file():
            return str(sibling)
    found = shutil.which("ffprobe")
    return found or ffprobe


def probe_video_duration_ms(
    source_video: Path,
    *,
    ffmpeg_binary: str = "ffmpeg",
) -> int | None:
    """Return duration in milliseconds via ffprobe, or None if unavailable."""
    ffprobe = _resolve_ffprobe_binary(ffmpeg_binary)
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(source_video),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout or "{}")
        raw = (payload.get("format") or {}).get("duration")
        seconds = float(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if seconds <= 0:
        return None
    return max(1, int(round(seconds * 1000.0)))


def render_video_single_pass(
    source_video: Path | str,
    output_video: Path | str,
    overlays: list[OverlaySegment] | None = None,
    *,
    ocr_payload: Mapping[str, Any] | list[Mapping[str, Any]] | None = None,
    vi_texts: Mapping[Any, str] | None = None,
    fontfile: Path | str | None = None,
    anti_seed: int | None = None,
    hold_ms: int = DEFAULT_HOLD_MS,
    ffmpeg_binary: str = "ffmpeg",
    progress: bool | ProgressCallback = True,
    frame_width: int | None = None,
    frame_height: int | None = None,
    attached_pic: Path | str | None = None,
    sample_dir: Path | str | None = None,
) -> Path:
    """
    Render once: mask Chinese + burn Vietnamese + anti-detection.

    Default backend: OpenCV inpaint (OCR_RENDER_BACKEND=opencv_inpaint).
    Rollback: OCR_RENDER_BACKEND=ffmpeg_delogo.
    """
    source = Path(source_video)
    output = Path(output_video)

    if shutil.which(ffmpeg_binary) is None:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_MISSING,
            f"ffmpeg binary not found on PATH ({ffmpeg_binary})",
        )
    if not source.is_file():
        raise VideoRendererError(
            VideoRendererErrorCode.SOURCE_MISSING,
            f"Source video missing: {source}",
        )

    if overlays is None:
        if ocr_payload is None:
            raise VideoRendererError(
                VideoRendererErrorCode.INVALID_INPUT,
                "Provide overlays= or ocr_payload= (+ vi_texts=)",
            )
        duration_ms = probe_video_duration_ms(source, ffmpeg_binary=ffmpeg_binary)
        overlays = overlays_from_ocr_payload(
            ocr_payload,
            vi_texts or {},
            hold_ms=hold_ms,
            video_duration_ms=duration_ms,
        )
    if not overlays:
        raise VideoRendererError(
            VideoRendererErrorCode.EMPTY_OVERLAYS,
            "overlays is empty",
        )

    from src.media_pipeline.video_renderer.inpaint_render import (
        BACKEND_OPENCV,
        render_video_opencv_inpaint,
        resolve_render_backend,
    )

    if resolve_render_backend() == BACKEND_OPENCV:
        return render_video_opencv_inpaint(
            source,
            output,
            overlays,
            fontfile=fontfile,
            anti_seed=anti_seed,
            ffmpeg_binary=ffmpeg_binary,
            progress=progress,
            frame_width=frame_width,
            frame_height=frame_height,
            attached_pic=attached_pic,
            sample_dir=sample_dir,
        )

    return _render_video_ffmpeg_delogo(
        source,
        output,
        overlays,
        ocr_payload=ocr_payload,
        fontfile=fontfile,
        anti_seed=anti_seed,
        ffmpeg_binary=ffmpeg_binary,
        progress=progress,
        frame_width=frame_width,
        frame_height=frame_height,
        attached_pic=attached_pic,
    )


def _render_video_ffmpeg_delogo(
    source: Path,
    output: Path,
    overlays: list[OverlaySegment],
    *,
    ocr_payload: Mapping[str, Any] | list[Mapping[str, Any]] | None,
    fontfile: Path | str | None,
    anti_seed: int | None,
    ffmpeg_binary: str,
    progress: bool | ProgressCallback,
    frame_width: int | None,
    frame_height: int | None,
    attached_pic: Path | str | None,
) -> Path:
    """Legacy single-pass FFmpeg delogo + drawtext path."""
    width = int(frame_width or 0)
    height = int(frame_height or 0)
    if width < 2 or height < 2:
        from_payload = _frame_size_from_ocr_payload(ocr_payload)
        if from_payload is not None:
            width, height = from_payload
    if width < 2 or height < 2:
        width, height = probe_video_frame_size(source, ffmpeg_binary=ffmpeg_binary)

    font = resolve_drawtext_font(fontfile)
    # hold already baked into overlay end_ms from Phase 2 mapping; avoid double-extend.
    chain = build_single_render_filter(
        overlays,
        fontfile=font,
        anti_seed=anti_seed,
        hold_ms=0,
        frame_width=width,
        frame_height=height,
    )
    filter_complex = wrap_filter_complex(chain)

    output.parent.mkdir(parents=True, exist_ok=True)
    cmd: list[str] = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-i",
        str(source),
    ]
    attach = Path(attached_pic) if attached_pic is not None else None
    if attach is not None:
        if not attach.is_file():
            raise VideoRendererError(
                VideoRendererErrorCode.INVALID_INPUT,
                f"attached_pic missing: {attach}",
            )
        cmd.extend(["-i", str(attach)])

    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "0:a?",
        ]
    )
    if attach is not None:
        cmd.extend(["-map", "1:v:0"])
        cmd.extend(
            [
                "-c:v:0",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:v:1",
                "mjpeg",
                "-disposition:v:1",
                "attached_pic",
            ]
        )
    else:
        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
            ]
        )

    cmd.extend(
        [
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )

    on_progress: ProgressCallback | None
    if progress is True:
        on_progress = _default_progress
    elif progress is False:
        on_progress = None
    else:
        on_progress = progress

    logger.info(
        "video_renderer_single_pass_start",
        extra={
            "source": source.name,
            "output": str(output),
            "overlays": len(overlays),
            "anti_seed": anti_seed,
            "backend": "ffmpeg_delogo",
        },
    )

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"Failed to start ffmpeg: {exc}",
        ) from exc

    stderr_lines: list[str] = []
    assert proc.stderr is not None
    try:
        while True:
            line = proc.stderr.readline()
            if not line:
                break
            stderr_lines.append(line)
            if on_progress is not None:
                on_progress(_parse_ffmpeg_time_seconds(line), line.rstrip())
        returncode = proc.wait()
    except Exception as exc:  # noqa: BLE001
        proc.kill()
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"ffmpeg render interrupted: {exc}",
        ) from exc
    finally:
        if on_progress is _default_progress:
            print(file=sys.stderr)

    if returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        detail = "".join(stderr_lines[-40:]).strip() or "ffmpeg failed"
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"ffmpeg single-pass render failed: {detail[:600]}",
        )

    logger.info(
        "video_renderer_single_pass_done",
        extra={"output": str(output), "bytes": output.stat().st_size},
    )
    return output


def render_image_with_overlays(
    source_image: Path | str,
    output_image: Path | str,
    overlays: list[OverlaySegment],
    *,
    fontfile: Path | str | None = None,
    anti_seed: int | None = None,
    ffmpeg_binary: str = "ffmpeg",
    frame_width: int | None = None,
    frame_height: int | None = None,
) -> Path:
    """Apply cover + VI to a still (e.g. thumbnail.jpg → covered cover art)."""
    source = Path(source_image)
    output = Path(output_image)
    if not source.is_file():
        raise VideoRendererError(
            VideoRendererErrorCode.SOURCE_MISSING,
            f"Source image missing: {source}",
        )
    if not overlays:
        # No text to cover — copy JPEG bytes as-is.
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(source.read_bytes())
        return output

    from src.media_pipeline.video_renderer.inpaint_render import (
        BACKEND_OPENCV,
        render_image_opencv_inpaint,
        resolve_render_backend,
    )

    if resolve_render_backend() == BACKEND_OPENCV:
        return render_image_opencv_inpaint(
            source,
            output,
            overlays,
            fontfile=fontfile,
        )

    if shutil.which(ffmpeg_binary) is None:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_MISSING,
            f"ffmpeg binary not found on PATH ({ffmpeg_binary})",
        )

    width = int(frame_width or 0)
    height = int(frame_height or 0)
    if width < 2 or height < 2:
        from src.media_pipeline.ocr_filtering.providers import _image_size

        width, height = _image_size(source)

    font = resolve_drawtext_font(fontfile)
    chain = build_single_render_filter(
        overlays,
        fontfile=font,
        anti_seed=anti_seed,
        hold_ms=0,
        frame_width=width,
        frame_height=height,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-i",
            str(source),
            "-vf",
            chain,
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        detail = (completed.stderr or completed.stdout or "ffmpeg still failed").strip()
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"ffmpeg thumbnail cover failed: {detail[:400]}",
        )
    return output
