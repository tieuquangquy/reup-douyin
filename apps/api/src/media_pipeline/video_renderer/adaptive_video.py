"""PTS-preserving adaptive Phase 4 video renderer (PyAV + explicit audio mux)."""

from __future__ import annotations

import json
import hashlib
import math
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from src.media_pipeline.video_renderer.adaptive_render import (
    AdaptiveFrameRenderer,
    AdaptiveRenderBlocked,
)
from src.media_pipeline.video_renderer.reference_plate import (
    is_usable_reference_plate_candidate,
    reference_plate_candidate_score,
)
from src.media_pipeline.video_renderer.renderer import probe_video_duration_ms
from src.media_pipeline.video_renderer.video_encoder import (
    SOFTWARE_ENCODER,
    ffmpeg_runtime_version,
    ffmpeg_video_encode_args,
    is_video_copy_args,
    probe_ffmpeg_encoder,
    select_video_encoder,
)
from src.render_pipeline.audio_loudness import (
    LoudnessMeasurementError,
    background_mix_gain,
    loudness_filter_args,
    two_pass_loudness_filter_args,
)


class AdaptiveVideoRenderError(RuntimeError):
    pass


def resolve_background_gain(contract: Mapping[str, Any]) -> float:
    """Resolve the approved mix gain, retaining a legacy-config fallback."""

    audio = dict(dict(contract.get("authorities") or {}).get("audio") or {})
    raw_gain = audio.get("background_gain")
    if raw_gain is None:
        return float(background_mix_gain())
    try:
        gain = float(raw_gain)
    except (TypeError, ValueError) as exc:
        raise AdaptiveVideoRenderError("Approved background gain is invalid") from exc
    if not math.isfinite(gain) or not 0.0 <= gain <= 1.0:
        raise AdaptiveVideoRenderError("Approved background gain is outside 0..1")
    return gain


def resolve_narration_atempo(
    narration_duration_seconds: float,
    target_duration_seconds: float,
) -> float:
    """Fit any meaningful narration overrun without exceeding the 1.20x policy."""
    ratio = float(narration_duration_seconds) / max(
        0.001, float(target_duration_seconds)
    )
    if ratio > 1.20:
        raise AdaptiveVideoRenderError(
            "Narration exceeds the bounded atempo fit policy"
        )
    return ratio if ratio > 1.0001 else 1.0


@dataclass(frozen=True)
class AdaptiveVideoRenderResult:
    output_path: Path
    frame_count: int
    qa_path: Path
    visual_preview: bool
    encoder_metadata: dict[str, Any]
    audio_mix_metadata: dict[str, Any]


def active_tracks_for_frame(
    contract: Mapping[str, Any], frame_index: int
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
        and int(row.get("start_frame") or 0)
        <= int(frame_index)
        <= int(row.get("end_frame") or 0)
    ]


def active_dense_ui_panels_for_frame(
    contract: Mapping[str, Any], frame_index: int
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in list(contract.get("dense_ui_panels") or [])
        if isinstance(row, Mapping)
        and int(row.get("start_frame") or 0)
        <= int(frame_index)
        <= int(row.get("end_frame") or -1)
    ]


def validate_adaptive_render_contract(
    contract: Mapping[str, Any], *, visual_preview: bool
) -> None:
    if str(contract.get("status") or "") != "READY_FOR_PHASE4":
        raise AdaptiveVideoRenderError("Phase 4 input is not READY_FOR_PHASE4")
    authorities = dict(contract.get("authorities") or {})
    timebase = dict(authorities.get("timebase") or {})
    if str(timebase.get("mode") or "") == "VFR" and str(
        timebase.get("status") or ""
    ) != "READY_WITH_PTS_MAP":
        raise AdaptiveVideoRenderError("VFR input requires an approved PTS map")
    audio = dict(authorities.get("audio") or {})
    if not visual_preview and str(audio.get("status") or "") != "READY":
        raise AdaptiveVideoRenderError("Final render requires approved TTS audio authority")


def build_audio_mux_command(
    *,
    video_only: Path,
    audio_source: Path,
    background_audio_source: Path | None = None,
    output: Path,
    duration_seconds: float,
    ffmpeg_binary: str,
    audio_filter_args: Sequence[str] = (),
    background_gain: float = 1.0,
    narration_atempo: float = 1.0,
    video_codec_args: Sequence[str] = ("-c:v", "copy"),
    color_metadata: Mapping[str, Any] | None = None,
) -> list[str]:
    command = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_only),
        "-i",
        str(audio_source),
    ]
    if background_audio_source is not None:
        command.extend(["-i", str(background_audio_source)])
    resolved_video_args = [str(value) for value in video_codec_args]
    command.extend(["-map", "0:v:0", *resolved_video_args])
    if not is_video_copy_args(resolved_video_args):
        command.extend(["-fps_mode:v", "passthrough"])
    if background_audio_source is not None:
        loudnorm = next(
            (
                str(audio_filter_args[index + 1])
                for index, value in enumerate(audio_filter_args[:-1])
                if str(value) == "-af"
            ),
            "loudnorm=I=-14:TP=-1.5:LRA=11",
        )
        command.extend(
            [
                "-filter_complex",
                f"[1:a]atempo={float(narration_atempo):.6f},aresample=48000,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                "volume=1.0[narration];"
                "[2:a]aresample=48000,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"volume={max(0.0, min(1.0, float(background_gain))):.4f}[background];"
                "[narration][background]"
                "amix=inputs=2:duration=longest:dropout_transition=0,"
                f"{loudnorm},"
                "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
                "[audio_out]",
                "-map",
                "[audio_out]",
            ]
        )
    else:
        command.extend(["-map", "1:a:0?"])
        if abs(float(narration_atempo) - 1.0) > 1e-6:
            existing = next(
                (
                    str(audio_filter_args[index + 1])
                    for index, value in enumerate(audio_filter_args[:-1])
                    if str(value) == "-af"
                ),
                "",
            )
            chain = f"atempo={float(narration_atempo):.6f}"
            command.extend(["-af", f"{chain},{existing}" if existing else chain])
        else:
            command.extend([str(value) for value in audio_filter_args])
    command.extend([
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-t",
        f"{max(0.001, float(duration_seconds)):.6f}",
    ])
    color = dict(color_metadata or {})
    for key, flag in (
        ("color_range", "-color_range"),
        ("color_space", "-colorspace"),
        ("color_transfer", "-color_trc"),
        ("color_primaries", "-color_primaries"),
    ):
        value = str(color.get(key) or "").strip()
        if value:
            command.extend([flag, value])
    color_range = str(color.get("color_range") or "").strip().casefold()
    if color_range in {"tv", "limited", "mpeg"}:
        command.extend(["-bsf:v", "h264_metadata=video_full_range_flag=0"])
    elif color_range in {"pc", "full", "jpeg"}:
        command.extend(["-bsf:v", "h264_metadata=video_full_range_flag=1"])
    command.extend([
        "-movflags",
        "+faststart",
        str(output),
    ])
    return command


def execute_mux_with_fallback(
    *,
    video_only: Path,
    audio_source: Path,
    background_audio_source: Path | None,
    output: Path,
    duration_seconds: float,
    ffmpeg_binary: str,
    audio_filter_args: Sequence[str],
    background_gain: float,
    selected_encoder: str,
    selected_video_args: Sequence[str],
    selected_encoder_is_hardware: bool,
    hardware_fallback_enabled: bool,
    width: int,
    height: int,
    narration_atempo: float = 1.0,
    color_metadata: Mapping[str, Any] | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    attempts: list[dict[str, Any]] = []

    def attempt(encoder: str, video_args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        command = build_audio_mux_command(
            video_only=video_only,
            audio_source=audio_source,
            background_audio_source=background_audio_source,
            output=output,
            duration_seconds=duration_seconds,
            ffmpeg_binary=ffmpeg_binary,
            audio_filter_args=audio_filter_args,
            background_gain=background_gain,
            narration_atempo=narration_atempo,
            video_codec_args=video_args,
            color_metadata=color_metadata,
        )
        started = time.perf_counter()
        completed = run(command, capture_output=True, text=True, check=False)
        success = bool(
            completed.returncode == 0
            and output.is_file()
            and output.stat().st_size > 0
        )
        attempts.append(
            {
                "encoder": encoder,
                "return_code": int(completed.returncode),
                "elapsed_seconds": round(time.perf_counter() - started, 6),
                "success": success,
            }
        )
        return completed

    actual_encoder = str(selected_encoder)
    completed = attempt(actual_encoder, selected_video_args)
    fallback_used = False
    if (
        not attempts[-1]["success"]
        and selected_encoder_is_hardware
        and hardware_fallback_enabled
    ):
        fallback_used = True
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
        actual_encoder = SOFTWARE_ENCODER
        completed = attempt(
            actual_encoder,
            ffmpeg_video_encode_args(
                actual_encoder,
                width=width,
                height=height,
            ),
        )
    return completed, {
        "selected_encoder": actual_encoder,
        "runtime_fallback_used": fallback_used,
        "runtime_fallback_reason": (
            "hardware_final_encode_failed" if fallback_used else None
        ),
        "encode_attempts": attempts,
        "success": bool(attempts[-1]["success"]),
    }


def validate_narration_file_authority(
    narration_path: str | Path,
    contract: Mapping[str, Any],
) -> None:
    narration = Path(narration_path)
    audio = dict(dict(contract.get("authorities") or {}).get("audio") or {})
    narration_ref = dict(audio.get("narration_ref") or {})
    expected = str(narration_ref.get("sha256") or "").lower()
    if audio.get("status") != "READY" or len(expected) != 64:
        raise AdaptiveVideoRenderError("Approved narration hash authority is missing")
    if not narration.is_file():
        raise AdaptiveVideoRenderError("Approved narration file is missing")
    digest = hashlib.sha256()
    with narration.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise AdaptiveVideoRenderError("Narration file hash does not match audio authority")


def validate_background_file_authority(
    background_path: str | Path,
    contract: Mapping[str, Any],
) -> None:
    background = Path(background_path)
    audio = dict(dict(contract.get("authorities") or {}).get("audio") or {})
    background_ref = dict(audio.get("background_ref") or {})
    expected = str(background_ref.get("sha256") or "").lower()
    if len(expected) != 64 or not background.is_file():
        raise AdaptiveVideoRenderError("Approved background stem authority is missing")
    digest = hashlib.sha256()
    with background.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise AdaptiveVideoRenderError("Background stem hash does not match audio authority")


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _reference_candidate(
    capture: Any,
    track: Mapping[str, Any],
    *,
    current: np.ndarray,
    frame_count: int,
    fps: float,
) -> np.ndarray | None:
    import cv2

    start = int(track.get("start_frame") or 0)
    end = int(track.get("end_frame") or start)
    offsets = {
        1,
        max(1, int(round(fps * 0.10))),
        max(1, int(round(fps * 0.25))),
        max(1, int(round(fps * 0.50))),
    }
    policy = dict(track.get("render_policy") or {})
    roi = dict(dict(policy.get("cover") or {}).get("roi") or {})
    height, width = current.shape[:2]
    x0 = max(0, int(round(float(roi.get("x") or 0.0) * width)))
    y0 = max(0, int(round(float(roi.get("y") or 0.0) * height)))
    x1 = min(
        width,
        int(
            round(
                (float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0))
                * width
            )
        ),
    )
    y1 = min(
        height,
        int(
            round(
                (float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0))
                * height
            )
        ),
    )
    outside = np.ones((height, width), dtype=bool)
    outside[y0:y1, x0:x1] = False
    inside = ~outside
    candidates: list[tuple[float, np.ndarray]] = []
    for offset in sorted(offsets):
        for index in (start - offset, end + offset):
            if not (0 <= index < frame_count):
                continue
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, candidate = capture.read()
            if not ok or candidate is None or candidate.shape != current.shape:
                continue
            outside_mad = float(
                np.abs(
                    candidate[outside].astype(np.float32)
                    - current[outside].astype(np.float32)
                ).mean()
            )
            inside_mad = float(
                np.abs(
                    candidate[inside].astype(np.float32)
                    - current[inside].astype(np.float32)
                ).mean()
            )
            if not is_usable_reference_plate_candidate(
                outside_mad=outside_mad,
                inside_mad=inside_mad,
            ):
                continue
            score = reference_plate_candidate_score(
                outside_mad=outside_mad,
                inside_mad=inside_mad,
            )
            candidates.append((score, candidate))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def should_seed_reference_plate(track: Mapping[str, Any]) -> bool:
    """Avoid an unalignable clean plate for a very short opening overlay."""
    policy = dict(track.get("render_policy") or {})
    mask_mode = str(dict(policy.get("cover") or {}).get("mask_mode") or "")
    if mask_mode != "stylized_components":
        return False
    start = int(track.get("start_frame") or 0)
    end = int(track.get("end_frame") or start)
    span_frames = max(1, end - start + 1)
    context = dict(policy.get("context") or {})
    return not (start <= 1 and span_frames <= 6) or bool(
        context.get("short_intro_reference_plate_approved")
    )


def _seed_reference_plates(
    source: Path,
    contract: Mapping[str, Any],
    renderer: AdaptiveFrameRenderer,
) -> int:
    import cv2

    video = dict(contract.get("video") or {})
    frame_count = int(video.get("frame_count") or 0)
    fps = float(video.get("fps") or 30.0)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise AdaptiveVideoRenderError("Cannot open source for reference plate selection")
    seeded = 0
    try:
        for track in list(contract.get("render_tracks") or []):
            if not isinstance(track, Mapping):
                continue
            if not should_seed_reference_plate(track):
                continue
            start = int(track.get("start_frame") or 0)
            capture.set(cv2.CAP_PROP_POS_FRAMES, start)
            ok, current = capture.read()
            if not ok or current is None:
                continue
            reference = _reference_candidate(
                capture,
                track,
                current=current,
                frame_count=frame_count,
                fps=fps,
            )
            context = dict(dict(track.get("render_policy") or {}).get("context") or {})
            if reference is None and bool(
                context.get("short_intro_full_frame_clean_plate_approved")
            ):
                clean_index = min(
                    max(0, frame_count - 1), int(track.get("end_frame") or start) + 1
                )
                capture.set(cv2.CAP_PROP_POS_FRAMES, clean_index)
                clean_ok, clean_frame = capture.read()
                if clean_ok and clean_frame is not None and clean_frame.shape == current.shape:
                    reference = clean_frame
            if reference is not None:
                renderer.seed_reference(str(track.get("text_id") or ""), reference)
                seeded += 1
    finally:
        capture.release()
    return seeded


def _seed_representative_masks(
    source: Path,
    contract: Mapping[str, Any],
    renderer: AdaptiveFrameRenderer,
) -> int:
    """Union start/middle/end glyph evidence before the first encoded frame."""
    import cv2

    video = dict(contract.get("video") or {})
    frame_count = int(video.get("frame_count") or 0)
    tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    samples: dict[int, list[dict[str, Any]]] = {}
    for track in tracks:
        start = max(0, min(frame_count - 1, int(track.get("start_frame") or 0)))
        end = max(start, min(frame_count - 1, int(track.get("end_frame") or start)))
        for index in {start, (start + end) // 2, end}:
            samples.setdefault(index, []).append(track)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise AdaptiveVideoRenderError("Cannot open source for representative masks")
    masks: dict[str, np.ndarray] = {}
    try:
        for index, active in sorted(samples.items()):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            for track in active:
                text_id = str(track.get("text_id") or "")
                observed = renderer.mask_builder(frame, track)
                if int(np.count_nonzero(observed)) == 0:
                    continue
                previous = masks.get(text_id)
                masks[text_id] = (
                    observed.copy()
                    if previous is None
                    else cv2.bitwise_or(previous, observed)
                )
    finally:
        capture.release()
    for text_id, mask in masks.items():
        renderer.seed_mask(text_id, mask)
    return len(masks)


def _seed_dense_ui_panels(
    source: Path,
    contract: Mapping[str, Any],
    renderer: AdaptiveFrameRenderer,
) -> int:
    """Use the first approved epoch frame to derive a stable source-aware plate."""
    import cv2

    panels = [
        dict(row)
        for row in list(contract.get("dense_ui_panels") or [])
        if isinstance(row, Mapping)
    ]
    if not panels:
        return 0
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise AdaptiveVideoRenderError("Cannot open source for dense UI panel plate")
    colors: dict[str, list[int]] = {}
    try:
        for panel in panels:
            panel_id = str(panel.get("panel_id") or "")
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(panel.get("start_frame") or 0))
            ok, frame = capture.read()
            if not ok or frame is None:
                raise AdaptiveVideoRenderError(
                    f"Cannot read dense UI panel reference frame: {panel_id}"
                )
            height, width = frame.shape[:2]
            roi = dict(panel.get("panel_roi") or {})
            x0 = max(0, min(width, int(round(float(roi.get("x") or 0.0) * width))))
            y0 = max(0, min(height, int(round(float(roi.get("y") or 0.0) * height))))
            x1 = max(x0, min(width, int(round((float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0)) * width))))
            y1 = max(y0, min(height, int(round((float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0)) * height))))
            if not panel_id or x1 <= x0 or y1 <= y0:
                raise AdaptiveVideoRenderError("Dense UI panel has invalid plate ROI")
            colors[panel_id] = [
                int(value)
                for value in np.median(frame[y0:y1, x0:x1], axis=(0, 1)).round()
            ]
    finally:
        capture.release()
    renderer.seed_dense_ui_panels(
        panels,
        list(contract.get("render_tracks") or []),
        plate_colors=colors,
    )
    return len(colors)


def _copy_color_authority(input_stream: Any, output_stream: Any) -> None:
    for attribute in ("color_range", "colorspace", "color_trc", "color_primaries"):
        try:
            value = getattr(input_stream.codec_context, attribute)
            if value is not None:
                setattr(output_stream.codec_context, attribute, value)
        except (AttributeError, TypeError, ValueError):
            continue


def render_adaptive_video(
    source_video: str | Path,
    output_video: str | Path,
    *,
    contract: Mapping[str, Any],
    visual_preview: bool,
    narration_path: str | Path | None = None,
    background_path: str | Path | None = None,
    ffmpeg_binary: str = "ffmpeg",
    qa_path: str | Path | None = None,
    progress: Callable[[int, int], None] | None = None,
    video_encoder_policy: str = "auto",
    hardware_smoke_probe: bool = True,
    hardware_fallback_enabled: bool = True,
) -> AdaptiveVideoRenderResult:
    import av

    validate_adaptive_render_contract(contract, visual_preview=visual_preview)
    source = Path(source_video)
    output = Path(output_video)
    if not source.is_file():
        raise AdaptiveVideoRenderError("Source video is missing")
    audio_source = source if visual_preview else Path(str(narration_path or ""))
    if not audio_source.is_file():
        raise AdaptiveVideoRenderError("Approved audio source is missing")
    if not visual_preview:
        validate_narration_file_authority(audio_source, contract)
    background_source = Path(str(background_path or "")) if background_path else None
    if not visual_preview and background_source is not None:
        validate_background_file_authority(background_source, contract)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        encoder_selection = select_video_encoder(
            video_encoder_policy,
            probe=lambda encoder: probe_ffmpeg_encoder(
                encoder,
                ffmpeg_binary=ffmpeg_binary,
                smoke_encode=bool(hardware_smoke_probe),
            ),
        )
    except RuntimeError as exc:
        raise AdaptiveVideoRenderError(str(exc)) from exc
    use_lossless_intermediate = encoder_selection.hardware
    video_only = output.with_suffix(
        ".video-only.mkv" if use_lossless_intermediate else ".video-only.mp4"
    )
    render_started = time.perf_counter()
    renderer = AdaptiveFrameRenderer()
    seeded = _seed_reference_plates(source, contract, renderer)
    masks_seeded = _seed_representative_masks(source, contract, renderer)
    panels_seeded = _seed_dense_ui_panels(source, contract, renderer)
    expected_frames = int(dict(contract.get("video") or {}).get("frame_count") or 0)
    qa_tracks: dict[str, dict[str, Any]] = {}
    qa_panels: dict[str, dict[str, Any]] = {}
    decoded_frames = 0

    input_container = av.open(str(source))
    input_stream = input_container.streams.video[0]
    output_container = av.open(str(video_only), mode="w")
    rate = input_stream.average_rate or input_stream.base_rate or 30
    intermediate_codec = "ffv1" if use_lossless_intermediate else SOFTWARE_ENCODER
    output_stream = output_container.add_stream(
        intermediate_codec,
        rate=rate,
        options=(
            {}
            if use_lossless_intermediate
            else {"crf": "20", "preset": "veryfast"}
        ),
    )
    frame_width = int(input_stream.codec_context.width)
    frame_height = int(input_stream.codec_context.height)
    renderer.seed_dense_layout_authority(
        list(contract.get("render_tracks") or [])
    )
    output_stream.width = frame_width
    output_stream.height = frame_height
    output_stream.pix_fmt = "yuv420p"
    try:
        output_stream.time_base = input_stream.time_base
    except (AttributeError, TypeError, ValueError):
        pass
    _copy_color_authority(input_stream, output_stream)
    try:
        for frame_index, frame in enumerate(input_container.decode(input_stream)):
            source_bgr = frame.to_ndarray(format="bgr24")
            active = active_tracks_for_frame(contract, frame_index)
            active_panels = active_dense_ui_panels_for_frame(contract, frame_index)
            if active or active_panels:
                try:
                    rendered_bgr, frame_qa = renderer.render_frame(
                        source_bgr, active, frame_index=frame_index
                    )
                except AdaptiveRenderBlocked as exc:
                    raise AdaptiveVideoRenderError(
                        f"Adaptive frame blocked at index {frame_index}: {exc}"
                    ) from exc
                for item in list(frame_qa.get("tracks") or []):
                    text_id = str(item.get("text_id") or "")
                    aggregate = qa_tracks.setdefault(
                        text_id,
                        {
                            "frames": 0,
                            "temporal_modes": {},
                            "max_mask_frame_fraction": 0.0,
                            "max_changed_fraction": 0.0,
                        },
                    )
                    aggregate["frames"] += 1
                    mode = str(dict(item.get("temporal") or {}).get("mode") or "unknown")
                    aggregate["temporal_modes"][mode] = (
                        int(aggregate["temporal_modes"].get(mode, 0)) + 1
                    )
                    aggregate["max_mask_frame_fraction"] = max(
                        float(aggregate["max_mask_frame_fraction"]),
                        float(
                            dict(dict(item.get("mask") or {}).get("metrics") or {}).get(
                                "frame_fraction"
                            )
                            or 0.0
                        ),
                    )
                    aggregate["max_changed_fraction"] = max(
                        float(aggregate["max_changed_fraction"]),
                        float(
                            dict(dict(item.get("damage") or {}).get("metrics") or {}).get(
                                "changed_fraction"
                            )
                            or 0.0
                        ),
                    )
                for item in list(frame_qa.get("dense_ui_panels") or []):
                    panel_id = str(item.get("panel_id") or "")
                    aggregate = qa_panels.setdefault(
                        panel_id,
                        {
                            "frames": 0,
                            "panel_roi": item.get("panel_roi"),
                            "plate_bgr": item.get("plate_bgr"),
                            "max_changed_fraction": 0.0,
                            "max_frame_change_fraction": item.get("max_frame_change_fraction"),
                            "rendered_lines": item.get("layouts"),
                        },
                    )
                    aggregate["frames"] += 1
                    aggregate["max_changed_fraction"] = max(
                        float(aggregate["max_changed_fraction"]),
                        float(item.get("changed_fraction") or 0.0),
                    )
            else:
                rendered_bgr = source_bgr
            output_frame = av.VideoFrame.from_ndarray(rendered_bgr, format="bgr24")
            output_frame.pts = frame.pts
            output_frame.time_base = frame.time_base
            for packet in output_stream.encode(output_frame):
                output_container.mux(packet)
            decoded_frames += 1
            if progress is not None:
                progress(decoded_frames, expected_frames)
        for packet in output_stream.encode():
            output_container.mux(packet)
    finally:
        input_container.close()
        output_container.close()
    if decoded_frames != expected_frames:
        raise AdaptiveVideoRenderError(
            f"Decoded frame count mismatch ({decoded_frames} != {expected_frames})"
        )

    duration = float(
        dict(contract.get("pts_map") or {}).get("last_pts_seconds")
        or (decoded_frames / max(1.0, float(rate)))
    )
    duration += float(
        dict(contract.get("pts_map") or {}).get("fallback_last_duration_seconds")
        or 0.0
    )
    width = frame_width
    height = frame_height
    selected_encoder = encoder_selection.selected_encoder
    selected_video_args = (
        ffmpeg_video_encode_args(selected_encoder, width=width, height=height)
        if use_lossless_intermediate
        else ["-c:v", "copy"]
    )
    normalization_mode = "disabled_for_visual_preview"
    audio_filter_args: Sequence[str] = []
    if not visual_preview:
        try:
            if background_source is None:
                audio_filter_args = two_pass_loudness_filter_args(
                    audio_source,
                    ffmpeg_binary=ffmpeg_binary,
                )
                normalization_mode = (
                    "two_pass_loudnorm" if audio_filter_args else "disabled"
                )
            else:
                audio_filter_args = loudness_filter_args()
                normalization_mode = (
                    "single_pass_post_mix_loudnorm"
                    if audio_filter_args
                    else "disabled"
                )
        except LoudnessMeasurementError as exc:
            raise AdaptiveVideoRenderError(str(exc)) from exc
    authority_color = dict(
        dict(contract.get("authorities") or {}).get("color") or {}
    )
    authority_audio = dict(dict(contract.get("authorities") or {}).get("audio") or {})
    resolved_background_gain = (
        resolve_background_gain(contract) if background_source is not None else None
    )
    narration_duration_seconds: float | None = None
    narration_atempo = 1.0
    if not visual_preview:
        narration_duration_ms = probe_video_duration_ms(
            audio_source, ffmpeg_binary=ffmpeg_binary
        )
        if narration_duration_ms is None:
            raise AdaptiveVideoRenderError("Narration duration authority is unavailable")
        narration_duration_seconds = narration_duration_ms / 1000.0
        # Even a sub-1% overrun must be fitted: muxing with ``-t`` otherwise
        # truncates the final syllable while the metadata reports an incomplete
        # narration.  Keep a tiny epsilon to avoid needless atempo for probe
        # rounding noise.
        narration_atempo = resolve_narration_atempo(
            narration_duration_seconds,
            duration,
        )
    mux, mux_metadata = execute_mux_with_fallback(
        video_only=video_only,
        audio_source=audio_source,
        background_audio_source=(None if visual_preview else background_source),
        output=output,
        duration_seconds=duration,
        ffmpeg_binary=ffmpeg_binary,
        audio_filter_args=audio_filter_args,
        background_gain=(
            resolved_background_gain
            if resolved_background_gain is not None
            else float(background_mix_gain())
        ),
        selected_encoder=selected_encoder,
        selected_video_args=selected_video_args,
        selected_encoder_is_hardware=encoder_selection.hardware,
        hardware_fallback_enabled=hardware_fallback_enabled,
        width=width,
        height=height,
        narration_atempo=narration_atempo,
        color_metadata=authority_color,
    )
    if not mux_metadata["success"]:
        detail = " ".join(str(mux.stderr or mux.stdout or "").split())[-300:]
        raise AdaptiveVideoRenderError(
            f"Audio/video encode failed for adaptive render: {detail or 'ffmpeg_failed'}"
        )
    encoder_metadata = {
        **encoder_selection.to_dict(),
        "probe_selected_encoder": encoder_selection.selected_encoder,
        **mux_metadata,
        "hardware": mux_metadata["selected_encoder"] != SOFTWARE_ENCODER,
        "intermediate_codec": intermediate_codec,
        "ffmpeg_version": ffmpeg_runtime_version(ffmpeg_binary),
        "total_render_seconds": round(time.perf_counter() - render_started, 6),
    }
    audio_mix_metadata = {
        "strategy": (
            "source_audio_preview"
            if visual_preview
            else str(authority_audio.get("strategy") or "")
            if str(authority_audio.get("strategy") or "")
            else "narration_with_background_stem"
            if background_source is not None
            else "narration_only"
        ),
        "normalization_mode": normalization_mode,
        "background_present": bool(not visual_preview and background_source is not None),
        "background_gain": (
            round(float(resolved_background_gain), 6)
            if not visual_preview and background_source is not None
            else None
        ),
        "narration_duration_seconds": narration_duration_seconds,
        "narration_atempo": round(float(narration_atempo), 6),
        "narration_fitted_duration_seconds": (
            round(narration_duration_seconds / narration_atempo, 6)
            if narration_duration_seconds is not None
            else None
        ),
        "narration_complete": bool(
            visual_preview
            or narration_duration_seconds is not None
            and narration_duration_seconds / narration_atempo <= duration + 0.01
        ),
    }
    try:
        video_only.unlink(missing_ok=True)
    except OSError:
        pass
    resolved_qa_path = Path(qa_path) if qa_path is not None else output.with_suffix(".qa.json")
    _write_json_atomic(
        resolved_qa_path,
        {
            "schema_version": "phase4_adaptive_render_qa_v1",
            "status": "PASS",
            "visual_preview": bool(visual_preview),
            "frames": decoded_frames,
            "reference_plates_seeded": seeded,
            "representative_masks_seeded": masks_seeded,
            "dense_ui_panels_seeded": panels_seeded,
            "encoder": encoder_metadata,
            "audio_mix": audio_mix_metadata,
            "tracks": qa_tracks,
            "dense_ui_panels": qa_panels,
        },
    )
    return AdaptiveVideoRenderResult(
        output_path=output.resolve(),
        frame_count=decoded_frames,
        qa_path=resolved_qa_path.resolve(),
        visual_preview=bool(visual_preview),
        encoder_metadata=encoder_metadata,
        audio_mix_metadata=audio_mix_metadata,
    )
