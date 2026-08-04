"""PTS, audio, color, and reproducibility authority for final rendering."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

RENDER_RECIPE_SCHEMA_VERSION = "phase4_render_recipe_v1"


class RenderAuthorityError(RuntimeError):
    pass


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def analyze_frame_timestamps(timestamps: Sequence[float]) -> dict[str, Any]:
    values = [float(value) for value in timestamps]
    deltas = [
        values[index] - values[index - 1]
        for index in range(1, len(values))
        if values[index] > values[index - 1]
    ]
    if len(deltas) < 2:
        return {
            "status": "INSUFFICIENT_PTS",
            "mode": "UNKNOWN",
            "frame_timestamps": len(values),
        }
    nominal = float(median(deltas))
    deviations = [abs(delta - nominal) / max(1e-9, nominal) for delta in deltas]
    max_deviation = max(deviations)
    p95_index = min(len(deviations) - 1, int(round((len(deviations) - 1) * 0.95)))
    p95_deviation = sorted(deviations)[p95_index]
    vfr = max_deviation > 0.08 or p95_deviation > 0.04
    return {
        "status": "PTS_RENDER_REQUIRED" if vfr else "READY",
        "mode": "VFR" if vfr else "CFR",
        "frame_timestamps": len(values),
        "nominal_frame_duration_seconds": round(nominal, 9),
        "nominal_fps": round(1.0 / nominal, 6),
        "max_delta_deviation_fraction": round(max_deviation, 6),
        "p95_delta_deviation_fraction": round(p95_deviation, 6),
    }


def apply_pts_map_to_contract(
    contract: Mapping[str, Any], timestamps: Sequence[float]
) -> dict[str, Any]:
    values = [float(value) for value in timestamps]
    video = dict(contract.get("video") or {})
    frame_count = int(video.get("frame_count") or 0)
    if frame_count < 1 or len(values) < frame_count:
        raise RenderAuthorityError("PTS map does not cover every source frame")
    deltas = [
        values[index] - values[index - 1]
        for index in range(1, frame_count)
        if values[index] > values[index - 1]
    ]
    fallback_delta = float(median(deltas)) if deltas else 1.0 / max(
        1.0, float(video.get("fps") or 30.0)
    )
    tracks: list[dict[str, Any]] = []
    for raw in list(contract.get("render_tracks") or []):
        if not isinstance(raw, Mapping):
            raise RenderAuthorityError("Render track is invalid during PTS mapping")
        row = dict(raw)
        start_frame = int(row.get("start_frame") or 0)
        end_frame = int(row.get("end_frame") or start_frame)
        if start_frame < 0 or end_frame < start_frame or end_frame >= frame_count:
            raise RenderAuthorityError("Render track frame range is outside PTS map")
        nominal_start = row.get("start_ms")
        nominal_end = row.get("end_ms")
        start_seconds = values[start_frame]
        end_seconds = (
            values[end_frame + 1]
            if end_frame + 1 < frame_count
            else values[end_frame] + fallback_delta
        )
        row["nominal_start_ms"] = nominal_start
        row["nominal_end_ms"] = nominal_end
        row["start_ms"] = int(round(start_seconds * 1000.0))
        row["end_ms"] = max(
            row["start_ms"] + 1, int(round(end_seconds * 1000.0))
        )
        tracks.append(row)
    output = dict(contract)
    output["render_tracks"] = tracks
    output["timebase_mode"] = "PTS"
    output["pts_map"] = {
        "frame_count": frame_count,
        "first_pts_seconds": values[0],
        "last_pts_seconds": values[frame_count - 1],
        "fallback_last_duration_seconds": fallback_delta,
    }
    return output


def resolve_audio_authority(
    render_prep_manifest: Mapping[str, Any] | None,
    *,
    allow_source_passthrough: bool,
) -> dict[str, Any]:
    outputs = (
        dict(render_prep_manifest.get("current_outputs") or {})
        if isinstance(render_prep_manifest, Mapping)
        else {}
    )
    joined = [
        dict(item)
        for item in list(outputs.get("joined_narration") or [])
        if isinstance(item, Mapping) and str(item.get("storage_key") or "").strip()
    ]
    manifest_version = (
        str(render_prep_manifest.get("manifest_version") or "")
        if isinstance(render_prep_manifest, Mapping)
        else ""
    )
    review = (
        dict(render_prep_manifest.get("audio_review") or {})
        if isinstance(render_prep_manifest, Mapping)
        else {}
    )
    render_contract = (
        dict(render_prep_manifest.get("render_contract") or {})
        if isinstance(render_prep_manifest, Mapping)
        else {}
    )
    approved = str(review.get("status") or "") == "AUDIO_APPROVED"
    valid_joined = [
        item
        for item in joined
        if len(str(item.get("sha256") or "")) == 64
        and str(item.get("mime_type") or "audio/wav").startswith("audio/")
    ]
    backgrounds = [
        dict(item)
        for item in list(outputs.get("background_audio") or [])
        if isinstance(item, Mapping)
        and str(item.get("storage_key") or "").strip()
        and len(str(item.get("sha256") or "")) == 64
    ]
    background_gain: float | None = None
    raw_background_gain = render_contract.get("background_gain")
    if backgrounds and raw_background_gain is not None:
        try:
            background_gain = float(raw_background_gain)
        except (TypeError, ValueError):
            background_gain = None
        if (
            background_gain is None
            or not math.isfinite(background_gain)
            or not 0.0 <= background_gain <= 1.0
        ):
            return {
                "status": "BLOCKED",
                "strategy": None,
                "narration_ref": None,
                "background_ref": None,
                "background_gain": None,
                "warnings": ["background_mix_gain_invalid"],
            }
    if manifest_version == "RENDER_PREP_MANIFEST_V2" and approved and valid_joined:
        chosen = valid_joined[-1]
        audio_role = str(chosen.get("role") or "")
        return {
            "status": "READY",
            "strategy": (
                "preserve_verified_no_dialogue_source_audio"
                if audio_role == "verified_no_dialogue_source_audio"
                else
                "mix_vietnamese_narration_with_background_stem"
                if backgrounds
                else "replace_with_vietnamese_narration"
            ),
            "narration_ref": {
                "storage_key": chosen.get("storage_key"),
                "sha256": chosen.get("sha256"),
                "mime_type": chosen.get("mime_type"),
                "duration_seconds": chosen.get("duration_seconds"),
                "audio_format": chosen.get("audio_format"),
                "role": chosen.get("role"),
            },
            "background_ref": (
                {
                    "storage_key": backgrounds[-1].get("storage_key"),
                    "sha256": backgrounds[-1].get("sha256"),
                    "mime_type": backgrounds[-1].get("mime_type"),
                    "role": backgrounds[-1].get("role"),
                }
                if backgrounds
                else None
            ),
            "background_gain": background_gain if backgrounds else None,
            "warnings": [],
        }
    if allow_source_passthrough:
        return {
            "status": "VISUAL_PREVIEW_ONLY",
            "strategy": "source_passthrough",
            "narration_ref": None,
            "warnings": ["tts_joined_narration_missing"],
        }
    return {
        "status": "BLOCKED",
        "strategy": None,
        "narration_ref": None,
        "warnings": [
            "tts_joined_narration_required"
            if not joined
            else "tts_manifest_v2_required"
            if manifest_version != "RENDER_PREP_MANIFEST_V2"
            else "tts_audio_operator_approval_required"
            if not approved
            else "tts_joined_narration_hash_required"
        ],
    }


def build_reproducible_render_recipe(
    *,
    phase4_input_sha256: str,
    source_video_sha256: str,
    font_sha256: str,
    policy_version: str,
    runtime_versions: Mapping[str, Any],
    audio_authority: Mapping[str, Any],
    color_authority: Mapping[str, Any],
    timebase_authority: Mapping[str, Any],
    anti_transform_enabled: bool,
    anti_seed: int | None,
    encoding_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if anti_transform_enabled and anti_seed is None:
        raise RenderAuthorityError(
            "A deterministic anti-transform seed is required when enabled"
        )
    payload = {
        "schema_version": RENDER_RECIPE_SCHEMA_VERSION,
        "inputs": {
            "phase4_input_sha256": str(phase4_input_sha256),
            "source_video_sha256": str(source_video_sha256),
            "font_sha256": str(font_sha256),
        },
        "policy_version": str(policy_version),
        "runtime_versions": dict(runtime_versions),
        "audio_authority": dict(audio_authority),
        "color_authority": dict(color_authority),
        "timebase_authority": dict(timebase_authority),
        "encoding_policy": dict(encoding_policy or {}),
        "localization": {
            "anti_transform_enabled": bool(anti_transform_enabled),
            "anti_seed": int(anti_seed) if anti_seed is not None else None,
        },
    }
    payload["recipe_sha256"] = _sha256_json(payload)
    return payload


def probe_media_authority(
    source_video: str | Path,
    *,
    ffprobe_binary: str = "ffprobe",
) -> dict[str, Any]:
    source = Path(source_video)
    if not source.is_file():
        raise RenderAuthorityError("Source video is missing")
    stream_probe = subprocess.run(
        [
            ffprobe_binary,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if stream_probe.returncode != 0:
        raise RenderAuthorityError("ffprobe cannot read source stream metadata")
    try:
        payload = json.loads(stream_probe.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RenderAuthorityError("ffprobe returned invalid stream JSON") from exc
    streams = [item for item in list(payload.get("streams") or []) if isinstance(item, Mapping)]
    video = next((dict(item) for item in streams if item.get("codec_type") == "video"), {})
    audio = next((dict(item) for item in streams if item.get("codec_type") == "audio"), {})

    timestamps = probe_frame_timestamps(source, ffprobe_binary=ffprobe_binary)
    timebase = analyze_frame_timestamps(timestamps)
    return {
        "video": {
            "codec": video.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
            "pixel_format": video.get("pix_fmt"),
            "sample_aspect_ratio": video.get("sample_aspect_ratio"),
            "display_aspect_ratio": video.get("display_aspect_ratio"),
            "color_range": video.get("color_range"),
            "color_space": video.get("color_space"),
            "color_transfer": video.get("color_transfer"),
            "color_primaries": video.get("color_primaries"),
            "field_order": video.get("field_order"),
        },
        "audio": {
            "present": bool(audio),
            "codec": audio.get("codec_name"),
            "sample_rate": audio.get("sample_rate"),
            "channels": audio.get("channels"),
            "channel_layout": audio.get("channel_layout"),
        },
        "timebase": timebase,
        "frame_timestamps_seconds": timestamps,
        "duration_seconds": dict(payload.get("format") or {}).get("duration"),
    }


def probe_frame_timestamps(
    source_video: str | Path,
    *,
    ffprobe_binary: str = "ffprobe",
) -> list[float]:
    source = Path(source_video)
    frames_probe = subprocess.run(
        [
            ffprobe_binary,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "frame=best_effort_timestamp_time",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    timestamps: list[float] = []
    if frames_probe.returncode == 0:
        try:
            frame_payload = json.loads(frames_probe.stdout or "{}")
            timestamps = [
                float(item["best_effort_timestamp_time"])
                for item in list(frame_payload.get("frames") or [])
                if isinstance(item, Mapping)
                and item.get("best_effort_timestamp_time") is not None
            ]
        except (json.JSONDecodeError, TypeError, ValueError):
            timestamps = []
    return timestamps
