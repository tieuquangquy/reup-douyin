"""OpenCV inpaint Phase 3+4: text mask → inpaint → Pillow VI → FFmpeg pipes."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

import numpy as np

from src.media_pipeline.video_renderer.errors import VideoRendererError, VideoRendererErrorCode
from src.media_pipeline.video_renderer.filter_graph import build_anti_detection_filters
from src.media_pipeline.video_renderer.fonts import resolve_drawtext_font
from src.media_pipeline.video_renderer.overlays import (
    DEFAULT_MIN_COVER_WIDTH,
    DEFAULT_PAD_X,
    DEFAULT_PAD_Y,
    DENSE_UI_KIND,
    OverlaySegment,
    expand_cover_rect,
    is_artifact_vi_text,
)

logger = logging.getLogger(__name__)

OCR_RENDER_BACKEND_ENV = "OCR_RENDER_BACKEND"
BACKEND_OPENCV = "opencv_inpaint"
BACKEND_FFMPEG = "ffmpeg_delogo"

ProgressCallback = Callable[[float | None, str], None]

_MIN_MASK_FRACTION = 0.005


def resolve_render_backend() -> str:
    """Default opencv_inpaint; set OCR_RENDER_BACKEND=ffmpeg_delogo to rollback."""
    raw = os.environ.get(OCR_RENDER_BACKEND_ENV, "").strip().lower()
    if raw in {BACKEND_FFMPEG, "delogo", "ffmpeg"}:
        return BACKEND_FFMPEG
    return BACKEND_OPENCV


def _norm_box_to_pixels(
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    frame_w: int,
    frame_h: int,
) -> tuple[int, int, int, int]:
    x0 = int(max(0, min(frame_w - 1, round(float(x) * frame_w))))
    y0 = int(max(0, min(frame_h - 1, round(float(y) * frame_h))))
    x1 = int(max(x0 + 1, min(frame_w, round((float(x) + float(w)) * frame_w))))
    y1 = int(max(y0 + 1, min(frame_h, round((float(y) + float(h)) * frame_h))))
    return x0, y0, x1, y1


def _roi_text_mask(gray_roi: np.ndarray) -> np.ndarray:
    """Otsu (+ invert if needed) → binary text mask for one ROI."""
    import cv2

    if gray_roi.size < 4:
        return np.zeros(gray_roi.shape, dtype=np.uint8)
    blur = cv2.GaussianBlur(gray_roi, (3, 3), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Prefer the darker class as "ink" for typical dark-on-light subs.
    mean_on = float(gray_roi[binary == 255].mean()) if np.any(binary == 255) else 255.0
    mean_off = float(gray_roi[binary == 0].mean()) if np.any(binary == 0) else 0.0
    if mean_on <= mean_off:
        ink = binary
    else:
        ink = cv2.bitwise_not(binary)
    frac = float(np.count_nonzero(ink)) / float(ink.size)
    # White text on dark UI: if ink fraction extreme, try inverted.
    if frac < _MIN_MASK_FRACTION or frac > 0.85:
        alt = cv2.bitwise_not(ink)
        alt_frac = float(np.count_nonzero(alt)) / float(alt.size)
        if _MIN_MASK_FRACTION <= alt_frac <= 0.85:
            ink = alt
            frac = alt_frac
    if frac < _MIN_MASK_FRACTION:
        # Soft fallback: filled ellipse inside ROI so thin glyphs still get inpainted.
        h, w = ink.shape[:2]
        ink = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(
            ink,
            (w // 2, h // 2),
            (max(1, w // 2 - 1), max(1, h // 2 - 1)),
            0,
            0,
            360,
            255,
            -1,
        )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    return cv2.dilate(ink, kernel, iterations=1)


def build_text_mask(
    frame_bgr: np.ndarray,
    boxes_xywh_norm: Sequence[tuple[float, float, float, float]],
) -> np.ndarray:
    """
    Full-frame uint8 mask (0/255): text pixels from per-box Otsu + dilate.
    ``boxes_xywh_norm`` are normalized xywh already padded/expanded by caller.
    """
    import cv2

    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"frame must be HxWx3 BGR, got {getattr(frame_bgr, 'shape', None)}",
        )
    h, w = frame_bgr.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    for x, y, bw, bh in boxes_xywh_norm:
        x0, y0, x1, y1 = _norm_box_to_pixels(x, y, bw, bh, frame_w=w, frame_h=h)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        roi = gray[y0:y1, x0:x1]
        local = _roi_text_mask(roi)
        mask[y0:y1, x0:x1] = cv2.bitwise_or(mask[y0:y1, x0:x1], local)
    return mask


_MIN_WIDTH_KINDS = frozenset({"hardsub"})
# UI / title labels: tight pad so adjacent boxes stay distinct.
_UI_PAD_X = 0.03
_UI_PAD_Y = 0.025


def _expand_segment_cover(seg: OverlaySegment) -> tuple[float, float, float, float]:
    """Local cover geometry per kind."""
    if seg.kind == DENSE_UI_KIND:
        return (
            float(seg.x),
            float(seg.y),
            float(seg.width),
            float(seg.height),
        )
    if seg.kind == "hardsub":
        return expand_cover_rect(
            float(seg.x),
            float(seg.y),
            float(seg.width),
            float(seg.height),
            pad_x=DEFAULT_PAD_X,
            pad_y=DEFAULT_PAD_Y,
            min_width=DEFAULT_MIN_COVER_WIDTH,
        )
    pad_x = _UI_PAD_X if seg.kind == "ui" else DEFAULT_PAD_X
    pad_y = _UI_PAD_Y if seg.kind == "ui" else DEFAULT_PAD_Y
    return expand_cover_rect(
        float(seg.x),
        float(seg.y),
        float(seg.width),
        float(seg.height),
        pad_x=pad_x,
        pad_y=pad_y,
        min_width=0.0,
    )


def build_cover_mask(
    frame_bgr: np.ndarray,
    segments: Sequence[OverlaySegment],
) -> np.ndarray:
    """
    Cover mask for active overlays.

    Dense UI: only ``dense_ui`` panel (+ bottom ``hardsub``) is masked so the
    slate wipe does not depend on OCR recalling every crumb. Sparse: per-box.
    """
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"frame must be HxWx3 BGR, got {getattr(frame_bgr, 'shape', None)}",
        )
    h, w = frame_bgr.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    if not segments:
        return mask

    has_dense = any(seg.kind == DENSE_UI_KIND for seg in segments)
    for seg in segments:
        if has_dense and seg.kind not in {DENSE_UI_KIND, "hardsub"}:
            continue
        x, y, bw, bh = _expand_segment_cover(seg)
        x0, y0, x1, y1 = _norm_box_to_pixels(x, y, bw, bh, frame_w=w, frame_h=h)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        mask[y0:y1, x0:x1] = 255
    return mask


def apply_solid_cover(
    frame_bgr: np.ndarray,
    mask: np.ndarray,
    *,
    radius: int = 14,
    opaque_panel: bool = False,
) -> np.ndarray:
    """
    Fast solid-region cover: dilate → fill from surrounding ring (or opaque panel).

    ``opaque_panel=True`` (dense UI end-card): fill with a neutral slate so every
    Chinese UI label is wiped, then lightly soften edges only.
    """
    import cv2

    del radius  # API compat; kernel sizes below are fixed for speed/quality.
    if mask is None or int(mask.max()) == 0:
        return frame_bgr
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    dilated = cv2.dilate(mask, kernel, iterations=2)
    cleaned = frame_bgr.copy()
    if opaque_panel:
        # Neutral slate — readable Chinese on white cards cannot survive.
        fill = np.array([52, 48, 46], dtype=np.float64)
        cleaned[dilated > 0] = fill
    else:
        outer = cv2.dilate(dilated, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)), iterations=1)
        ring = (outer > 0) & (dilated == 0)
        if np.any(ring):
            fill = frame_bgr[ring].mean(axis=0)
        else:
            fill = frame_bgr.reshape(-1, 3).mean(axis=0)
        cleaned[dilated > 0] = fill
    soft = cv2.GaussianBlur(cleaned, (9, 9), 0)
    edge = cv2.dilate(dilated, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)
    edge_only = (edge > 0) & (dilated == 0)
    if np.any(edge_only):
        cleaned[edge_only] = soft[edge_only]
    return cleaned


def inpaint_frame(
    frame_bgr: np.ndarray,
    mask: np.ndarray,
    *,
    large_region: bool = False,
    radius: int = 3,
) -> np.ndarray:
    """Restore background under mask; NS for large/endcard regions, else TELEA."""
    import cv2

    if mask is None or int(mask.max()) == 0:
        return frame_bgr
    flags = cv2.INPAINT_NS if large_region else cv2.INPAINT_TELEA
    return cv2.inpaint(frame_bgr, mask, max(1, int(radius)), flags)


def _active_segments(overlays: Sequence[OverlaySegment], time_ms: int) -> list[OverlaySegment]:
    return [seg for seg in overlays if int(seg.start_ms) <= time_ms < int(seg.end_ms)]


def _expanded_boxes_for_segments(segments: Sequence[OverlaySegment]) -> list[tuple[float, float, float, float]]:
    return [_expand_segment_cover(seg) for seg in segments]


def draw_vi_overlays(
    frame_bgr: np.ndarray,
    segments: Sequence[OverlaySegment],
    *,
    fontfile: Path | str,
) -> np.ndarray:
    """Burn Vietnamese text with Pillow (Unicode + stroke) centered in each box."""
    from PIL import Image, ImageDraw, ImageFont

    if not segments:
        return frame_bgr
    h, w = frame_bgr.shape[:2]
    rgb = frame_bgr[:, :, ::-1].copy()
    img = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(img)
    font_path = Path(fontfile)
    for seg in segments:
        if seg.kind == DENSE_UI_KIND:
            continue
        text = (seg.text_vi or "").strip()
        if not text or is_artifact_vi_text(text):
            continue
        x0, y0, bw, bh = _expand_segment_cover(seg)
        # Fit font to local box height (UI labels are small).
        size = max(10, min(72, int(max(8, int(bh * h)) * 0.55)))
        box_w = max(8, int(bw * w))
        box_h = max(8, int(bh * h))
        px = int(x0 * w)
        py = int(y0 * h)
        try:
            font = ImageFont.truetype(str(font_path), size=size)
        except OSError:
            font = ImageFont.load_default()
        # Shrink until text fits width.
        for _ in range(8):
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=2)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            if tw <= box_w * 0.95 and th <= box_h * 0.9:
                break
            size = max(8, int(size * 0.85))
            try:
                font = ImageFont.truetype(str(font_path), size=size)
            except OSError:
                break
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=2)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = px + max(0, (box_w - tw) // 2) - bbox[0]
        ty = py + max(0, (box_h - th) // 2) - bbox[1]
        # Dark stroke then light fill for contrast on any background.
        draw.text((tx, ty), text, font=font, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    out = np.asarray(img)[:, :, ::-1].copy()
    return out


def process_frame_bgr(
    frame_bgr: np.ndarray,
    segments: Sequence[OverlaySegment],
    *,
    fontfile: Path | str,
) -> np.ndarray:
    """Cover active overlays then burn VI (passthrough if no segments)."""
    if not segments:
        return frame_bgr
    mask = build_cover_mask(frame_bgr, segments)
    opaque = any(seg.kind == DENSE_UI_KIND for seg in segments)
    radius = 12
    cleaned = apply_solid_cover(frame_bgr, mask, radius=radius, opaque_panel=opaque)
    return draw_vi_overlays(cleaned, segments, fontfile=fontfile)


def render_image_opencv_inpaint(
    source_image: Path | str,
    output_image: Path | str,
    overlays: Sequence[OverlaySegment],
    *,
    fontfile: Path | str | None = None,
) -> Path:
    """Still-image path (thumbnail): mask + inpaint + VI."""
    import cv2

    source = Path(source_image)
    output = Path(output_image)
    if not source.is_file():
        raise VideoRendererError(
            VideoRendererErrorCode.SOURCE_MISSING,
            f"Source image missing: {source}",
        )
    frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if frame is None:
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"Cannot read image: {source}",
        )
    font = resolve_drawtext_font(fontfile)
    # Treat as t=0 for thumbnail overlays (caller already filtered).
    active = list(overlays) if overlays else []
    out = process_frame_bgr(frame, active, fontfile=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), out):
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"Failed to write inpainted image: {output}",
        )
    return output.resolve()


def _even_dimension(value: int) -> int:
    """libx264 requires even width/height."""
    v = max(2, int(value))
    return v if v % 2 == 0 else v - 1


def read_exact_bytes(stream, size: int) -> bytes:
    """
    Read exactly ``size`` bytes (or short on EOF).

    Windows pipes often return partial reads; treating that as EOF yields 0-frame
    encodes that still produce a tiny 0s MP4 and a false COMPLETED job.
    """
    need = max(0, int(size))
    if need == 0:
        return b""
    chunks: list[bytes] = []
    got = 0
    while got < need:
        chunk = stream.read(need - got)
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode("latin1")
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def _drain_pipe(pipe) -> bytearray:
    """Read subprocess pipe to completion (avoids stderr deadlock)."""
    buf = bytearray()
    if pipe is None:
        return buf
    try:
        while True:
            chunk = pipe.read(65536)
            if not chunk:
                break
            if isinstance(chunk, str):
                buf.extend(chunk.encode("utf-8", errors="replace"))
            else:
                buf.extend(chunk)
            # Guard against mock/infinite non-empty reads.
            if len(buf) > 2_000_000:
                break
    except Exception:
        pass
    return buf


def _parse_fractional_fps(raw: str) -> float | None:
    text = str(raw or "").strip()
    if "/" not in text:
        return None
    num_s, den_s = text.split("/", 1)
    try:
        num, den = float(num_s), float(den_s)
    except ValueError:
        return None
    if den <= 0 or num <= 0:
        return None
    return max(1.0, min(60.0, num / den))


def _parse_stream_fps(stream: Mapping[str, Any] | dict[str, Any]) -> float | None:
    """Prefer nominal ``r_frame_rate`` over ``avg_frame_rate`` (avoids 29s→33s stretch)."""
    for key in ("r_frame_rate", "avg_frame_rate"):
        parsed = _parse_fractional_fps(str(stream.get(key) or ""))
        if parsed is not None:
            return parsed
    return None


def mux_output_trim_args(duration_ms: int | None) -> list[str]:
    """Cap muxed output to source duration so long audio cannot inflate container length."""
    ms = int(duration_ms or 0)
    if ms <= 0:
        return []
    return ["-t", f"{ms / 1000.0:.3f}"]


def _probe_fps(source: Path, *, ffmpeg_binary: str) -> float:
    from src.media_pipeline.video_renderer.renderer import _resolve_ffprobe_binary

    ffprobe = _resolve_ffprobe_binary(ffmpeg_binary)
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate,avg_frame_rate",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return 25.0
    import json

    try:
        payload = json.loads(completed.stdout or "{}")
        stream = (payload.get("streams") or [{}])[0]
        parsed = _parse_stream_fps(stream)
        if parsed is not None:
            return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return 25.0


def render_video_opencv_inpaint(
    source_video: Path | str,
    output_video: Path | str,
    overlays: Sequence[OverlaySegment],
    *,
    fontfile: Path | str | None = None,
    anti_seed: int | None = None,
    ffmpeg_binary: str = "ffmpeg",
    progress: bool | ProgressCallback = True,
    frame_width: int | None = None,
    frame_height: int | None = None,
    attached_pic: Path | str | None = None,
) -> Path:
    """
    Decode → per-frame inpaint+VI (passthrough when idle) → encode with anti-hash.

    Audio is remuxed from source; optional attached_pic mapped as MJPEG cover.
    """
    from src.media_pipeline.video_renderer.renderer import (
        probe_video_duration_ms,
        probe_video_frame_size,
    )

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
    if not overlays:
        raise VideoRendererError(
            VideoRendererErrorCode.EMPTY_OVERLAYS,
            "overlays is empty",
        )

    width = int(frame_width or 0)
    height = int(frame_height or 0)
    if width < 2 or height < 2:
        width, height = probe_video_frame_size(source, ffmpeg_binary=ffmpeg_binary)
    width = _even_dimension(width)
    height = _even_dimension(height)
    fps = _probe_fps(source, ffmpeg_binary=ffmpeg_binary)
    duration_ms = probe_video_duration_ms(source, ffmpeg_binary=ffmpeg_binary) or 0
    total_frames = max(1, int(round((duration_ms / 1000.0) * fps))) if duration_ms else 0

    font = resolve_drawtext_font(fontfile)
    anti = ",".join(build_anti_detection_filters(seed=anti_seed)) or "null"
    output.parent.mkdir(parents=True, exist_ok=True)

    # Two-phase: encode video-only from pipe (no -shortest race with audio), then mux.
    video_only = output.with_suffix(".inpaint.mp4")
    frame_bytes = width * height * 3
    # Force CFR on decode to match encode -r (prevents VFR/avg mismatch stretching duration).
    fps_s = f"{fps:.4f}".rstrip("0").rstrip(".")
    decode_cmd = [
        ffmpeg_binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-an",
        "-vf",
        f"fps={fps_s},scale={width}:{height}:flags=bicubic,format=bgr24",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-",
    ]
    encode_cmd = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps:.4f}",
        "-i",
        "-",
        "-vf",
        anti,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(video_only),
    ]

    on_progress: ProgressCallback | None
    if progress is True:

        def _default(seconds: float | None, raw: str) -> None:
            if seconds is None:
                return
            print(f"\rinpaint render time={seconds:7.2f}s", end="", file=sys.stderr, flush=True)

        on_progress = _default
    elif progress is False:
        on_progress = None
    else:
        on_progress = progress

    try:
        import tqdm  # type: ignore

        use_tqdm = progress is True
    except ImportError:
        use_tqdm = False

    decoder = subprocess.Popen(
        decode_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=10**7,
    )
    encoder = subprocess.Popen(
        encode_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=10**7,
    )
    assert decoder.stdout is not None
    assert encoder.stdin is not None

    import threading

    enc_err_buf = bytearray()
    dec_err_buf = bytearray()

    def _drain_enc() -> None:
        enc_err_buf.extend(_drain_pipe(encoder.stderr))

    def _drain_dec() -> None:
        dec_err_buf.extend(_drain_pipe(decoder.stderr))

    enc_drain = threading.Thread(target=_drain_enc, daemon=True)
    dec_drain = threading.Thread(target=_drain_dec, daemon=True)
    enc_drain.start()
    dec_drain.start()

    frame_index = 0
    bar = None
    if use_tqdm and total_frames > 0:
        bar = tqdm.tqdm(total=total_frames, desc="inpaint", unit="frame", leave=False)
    pipe_error: BaseException | None = None

    try:
        while True:
            raw = read_exact_bytes(decoder.stdout, frame_bytes)
            if len(raw) < frame_bytes:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3)).copy()
            time_ms = int(round(frame_index * 1000.0 / fps))
            active = _active_segments(overlays, time_ms)
            out_frame = process_frame_bgr(frame, active, fontfile=font)
            try:
                encoder.stdin.write(out_frame.tobytes())
            except BrokenPipeError as exc:
                pipe_error = exc
                break
            frame_index += 1
            if bar is not None:
                bar.update(1)
            elif on_progress is not None and frame_index % max(1, int(fps)) == 0:
                on_progress(time_ms / 1000.0, f"frame={frame_index}")
    except Exception as exc:
        pipe_error = exc
    finally:
        if bar is not None:
            bar.close()
        try:
            if encoder.stdin:
                encoder.stdin.flush()
        except Exception:
            pass
        try:
            if encoder.stdin:
                encoder.stdin.close()
        except Exception:
            pass
        try:
            if decoder.stdout:
                decoder.stdout.close()
        except Exception:
            pass

    dec_code = decoder.wait(timeout=120)
    enc_code = encoder.wait(timeout=600)
    enc_drain.join(timeout=5)
    dec_drain.join(timeout=5)
    enc_err = enc_err_buf.decode("utf-8", errors="replace").strip()
    dec_err = dec_err_buf.decode("utf-8", errors="replace").strip()

    if pipe_error is not None or enc_code != 0:
        detail = enc_err or dec_err or str(pipe_error or "encode failed")
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"OpenCV inpaint render failed: {pipe_error or f'exit={enc_code}'}; ffmpeg: {detail[:500]}",
        )
    if frame_index < 1:
        detail = dec_err or enc_err or f"decode_exit={dec_code}"
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"OpenCV inpaint produced 0 frames (would be 0s video). {detail[:400]}",
        )
    if not video_only.is_file() or video_only.stat().st_size <= 0:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"OpenCV inpaint encode wrote empty file; ffmpeg: {(enc_err or dec_err)[:400]}",
        )

    encoded_ms = probe_video_duration_ms(video_only, ffmpeg_binary=ffmpeg_binary) or 0
    if encoded_ms < 200:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"OpenCV inpaint output too short ({encoded_ms}ms, frames={frame_index}); "
            f"ffmpeg: {(enc_err or dec_err)[:300]}",
        )

    attach = Path(attached_pic) if attached_pic is not None else None
    if attach is not None and not attach.is_file():
        raise VideoRendererError(
            VideoRendererErrorCode.INVALID_INPUT,
            f"attached_pic missing: {attach}",
        )

    mux_cmd: list[str] = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_only),
        "-i",
        str(source),
    ]
    if attach is not None:
        mux_cmd.extend(["-i", str(attach)])
        mux_cmd.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "1:a?",
                "-map",
                "2:v:0",
                "-c:v:0",
                "copy",
                "-c:v:1",
                "mjpeg",
                "-disposition:v:1",
                "attached_pic",
                "-c:a",
                "copy",
                *mux_output_trim_args(duration_ms),
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
    else:
        mux_cmd.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "1:a?",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                *mux_output_trim_args(duration_ms),
                "-movflags",
                "+faststart",
                str(output),
            ]
        )

    mux = subprocess.run(mux_cmd, capture_output=True, text=True, check=False)
    try:
        video_only.unlink(missing_ok=True)
    except OSError:
        pass
    if mux.returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"inpaint mux failed: {(mux.stderr or mux.stdout or '')[:400]}",
        )

    final_ms = probe_video_duration_ms(output, ffmpeg_binary=ffmpeg_binary) or 0
    if final_ms < 200:
        raise VideoRendererError(
            VideoRendererErrorCode.FFMPEG_FAILED,
            f"Cleaned video is {final_ms}ms after mux (expected ~{encoded_ms}ms). "
            f"mux: {(mux.stderr or '')[:300]}",
        )

    if on_progress is not None:
        print(file=sys.stderr)
    logger.info(
        "opencv_inpaint_render_done",
        extra={"frames": frame_index, "output": str(output), "fps": fps, "duration_ms": final_ms},
    )
    return output.resolve()
