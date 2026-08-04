"""Hash-bound finalization for operator-approved NO_TEXT regression controls."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from src.media_pipeline.video_renderer.adaptive_output_qa import (
    build_local_residual_ocr_provider,
    collect_adaptive_output_qa,
)
from src.media_pipeline.video_renderer.render_policy import RENDER_POLICY_VERSION


class NoTextPassthroughError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NoTextPassthroughError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise NoTextPassthroughError(f"{path.name} must contain an object")
    return payload


def _verify_self_hash(payload: Mapping[str, Any], field: str, label: str) -> str:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    if len(claimed) != 64 or _sha256_json(unsigned) != claimed:
        raise NoTextPassthroughError(f"{label} self-hash is invalid")
    return claimed


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def load_no_text_authority(root_dir: str | Path) -> dict[str, Any]:
    """Load the exact source approved by the Phase-1 full-video NO_TEXT gate."""

    root = Path(root_dir).resolve()
    approval_path = root / "phase1_no_text_approval.json"
    review_path = root / "phase1_no_text_review.json"
    approval = _load(approval_path)
    review = _load(review_path)
    approval_sha = _verify_self_hash(
        approval, "approval_sha256", "NO_TEXT approval"
    )
    review_sha = _verify_self_hash(review, "review_sha256", "NO_TEXT review")
    review_ref = dict(approval.get("review_ref") or {})
    if (
        str(approval.get("status") or "") != "NO_TEXT_OPERATOR_APPROVED"
        or str(approval.get("decision") or "") != "NO_TEXT_CONFIRMED"
        or str(review_ref.get("path") or "") != review_path.name
        or str(review_ref.get("sha256") or "") != review_sha
    ):
        raise NoTextPassthroughError("NO_TEXT authority is incomplete or stale")
    source_ref = dict(review.get("source_video") or {})
    source = Path(str(source_ref.get("path") or "")).resolve()
    if (
        not source.is_file()
        or source.stat().st_size != int(source_ref.get("size_bytes") or -1)
        or _sha256_file(source) != str(source_ref.get("sha256") or "")
    ):
        raise NoTextPassthroughError("NO_TEXT source video authority drifted")
    return {
        "source": source,
        "source_sha256": str(source_ref["sha256"]),
        "approval_sha256": approval_sha,
        "review_sha256": review_sha,
        "approval_file_sha256": _sha256_file(approval_path),
        "review_file_sha256": _sha256_file(review_path),
    }


def _probe_media(path: Path, ffprobe_binary: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            ffprobe_binary,
            "-v",
            "error",
            "-count_frames",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise NoTextPassthroughError("ffprobe failed for NO_TEXT source")
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise NoTextPassthroughError("ffprobe returned invalid JSON") from exc
    streams = list(payload.get("streams") or [])
    video = next(
        (dict(row) for row in streams if row.get("codec_type") == "video"), None
    )
    if not video:
        raise NoTextPassthroughError("NO_TEXT source has no video stream")
    audio = next(
        (dict(row) for row in streams if row.get("codec_type") == "audio"), None
    )
    duration = float(dict(payload.get("format") or {}).get("duration") or 0.0)
    frame_count = int(video.get("nb_read_frames") or video.get("nb_frames") or 0)
    rate = str(video.get("r_frame_rate") or "0/1")
    numerator, denominator = (rate.split("/", 1) + ["1"])[:2]
    fps = float(numerator) / max(1.0, float(denominator))
    if duration <= 0 or frame_count <= 0 or fps <= 0:
        raise NoTextPassthroughError("NO_TEXT source probe is incomplete")
    return {
        "duration_seconds": duration,
        "frame_count": frame_count,
        "fps": fps,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "audio_present": audio is not None,
        "video": video,
    }


def _verify_silent_or_absent_audio(
    path: Path, probe: Mapping[str, Any], ffmpeg_binary: str
) -> dict[str, Any]:
    if not bool(probe.get("audio_present")):
        return {
            "status": "VERIFIED_SOURCE_HAS_NO_AUDIO",
            "source_audio_present": False,
            "max_volume_db": None,
            "policy_version": "no_text_silent_or_absent_audio_v1",
        }
    completed = subprocess.run(
        [
            ffmpeg_binary,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vn",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "NUL",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    combined = "\n".join((completed.stdout or "", completed.stderr or ""))
    match = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", combined)
    if completed.returncode != 0 or not match:
        raise NoTextPassthroughError("Source audio silence measurement failed")
    raw = match.group(1).lower()
    max_volume = float("-inf") if raw == "-inf" else float(raw)
    if max_volume > -60.0:
        raise NoTextPassthroughError(
            "Audible NO_TEXT source requires separate dialogue/background authority"
        )
    return {
        "status": "VERIFIED_SOURCE_AUDIO_SILENT",
        "source_audio_present": True,
        "max_volume_db": max_volume,
        "silence_threshold_db": -60.0,
        "policy_version": "no_text_silent_or_absent_audio_v1",
    }


def _render_video_only(
    source: Path,
    output: Path,
    *,
    ffmpeg_binary: str,
) -> dict[str, Any]:
    attempts = [
        (
            "h264_nvenc",
            ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "19", "-b:v", "0"],
        ),
        ("libx264", ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]),
    ]
    errors: list[str] = []
    for encoder, encoder_args in attempts:
        temporary = output.with_suffix(".tmp.mp4")
        temporary.unlink(missing_ok=True)
        command = [
            ffmpeg_binary,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-an",
            *encoder_args,
            "-pix_fmt",
            "yuv420p",
            "-color_range",
            "tv",
            "-colorspace",
            "bt709",
            "-color_trc",
            "bt709",
            "-color_primaries",
            "bt709",
            "-fps_mode",
            "passthrough",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode == 0 and temporary.is_file() and temporary.stat().st_size:
            temporary.replace(output)
            return {
                "selected_encoder": encoder,
                "runtime_fallback_used": encoder != "h264_nvenc",
                "attempted_encoders": [row[0] for row in attempts[: attempts.index((encoder, encoder_args)) + 1]],
            }
        errors.append((completed.stderr or completed.stdout or encoder)[-500:])
        temporary.unlink(missing_ok=True)
    raise NoTextPassthroughError("NO_TEXT render failed: " + " | ".join(errors))


def build_no_text_contract(
    *, authority: Mapping[str, Any], probe: Mapping[str, Any]
) -> dict[str, Any]:
    video = dict(probe.get("video") or {})
    return {
        "schema_version": "phase4_render_input_v1",
        "status": "READY_FOR_PHASE4",
        "refs": {
            "phase1_no_text_approval_ref": {
                "path": "phase1_no_text_approval.json",
                "sha256": authority["approval_file_sha256"],
                "approval_sha256": authority["approval_sha256"],
            },
            "source_video_ref": {
                "path": Path(authority["source"]).name,
                "sha256": authority["source_sha256"],
            },
        },
        "video": {
            "frame_width": int(probe["width"]),
            "frame_height": int(probe["height"]),
            "frame_count": int(probe["frame_count"]),
            "fps": float(probe["fps"]),
        },
        "counts": {
            "render_tracks": 0,
            "localized_tracks": 0,
            "cover_only_tracks": 0,
            "content_objects": 0,
        },
        "timing_normalization": {
            "policy_version": "no_text_passthrough_v1",
            "adjusted_shared_caption_boundaries": 0,
        },
        "render_tracks": [],
        "render_policy_version": RENDER_POLICY_VERSION,
        "timebase_mode": "SOURCE_PASSTHROUGH",
        "authorities": {
            "visual": {
                "status": "NO_TEXT_SOURCE_PIXELS_PRESERVED",
                "source_video_sha256": authority["source_sha256"],
            },
            "audio": {
                "status": "READY",
                "strategy": "drop_verified_silent_or_absent_source_audio",
            },
            "color": {
                field: video.get(field)
                for field in (
                    "color_range",
                    "color_space",
                    "color_transfer",
                    "color_primaries",
                )
            },
        },
        "final_render_gate": "READY_FOR_FINAL_RENDER",
    }


def finalize_no_text_passthrough(
    *,
    root_dir: str | Path,
    operator_id: str,
    ffmpeg_binary: str = "ffmpeg",
    ffprobe_binary: str = "ffprobe",
    qa_collector: Callable[..., dict[str, Any]] = collect_adaptive_output_qa,
    ocr_provider: Any | None = None,
) -> dict[str, Any]:
    """Create a delivery MP4 and complete QA authority without inventing text/audio."""

    root = Path(root_dir).resolve()
    operator = str(operator_id or "").strip()
    if not root.is_dir() or not operator:
        raise NoTextPassthroughError("Artifact root and operator are required")
    authority = load_no_text_authority(root)
    source = Path(authority["source"])
    probe = _probe_media(source, ffprobe_binary)
    audio_authority = _verify_silent_or_absent_audio(source, probe, ffmpeg_binary)
    contract = build_no_text_contract(authority=authority, probe=probe)
    contract_path = root / "phase4_render_input.json"
    _write_json_atomic(contract_path, contract)

    phase2_timeline = {
        "schema_version": "phase2_ocr_timeline_v1",
        "status": "NO_TEXT_BYPASS",
        "source_video_sha256": authority["source_sha256"],
        "objects": [],
        "master_timeline_overwritten": False,
    }
    _write_json_atomic(root / "phase2_ocr_timeline.json", phase2_timeline)
    phase2_meta = {
        "schema_version": "phase2_meta_v1",
        "status": "OCR_BYPASSED_NO_TEXT",
        "ready_for_phase3": True,
        "review_required": 0,
        "ocr_ok": 0,
        "tracks": 0,
        "no_text_approval_sha256": authority["approval_sha256"],
    }
    _write_json_atomic(root / "phase2_meta.json", phase2_meta)
    _write_json_atomic(
        root / "phase2_handoff.json",
        {
            "schema_version": "phase2_handoff_v1",
            "status": "READY_FOR_PHASE3",
            "mode": "NO_TEXT_BYPASS",
            "items": [],
        },
    )
    _write_json_atomic(
        root / "phase3_translation_timeline.json",
        {
            "schema_version": "phase3_translation_timeline_v1",
            "status": "NO_TEXT_BYPASS",
            "translations": [],
        },
    )
    _write_json_atomic(
        root / "phase3_render_handoff.json",
        {
            "schema_version": "phase3_render_handoff_v1",
            "status": "READY_FOR_RENDER",
            "mode": "NO_TEXT_SOURCE_PASSTHROUGH",
            "render_tracks": [],
        },
    )
    _write_json_atomic(
        root / "phase3_closeout.json",
        {
            "schema_version": "phase3_closeout_v1",
            "status": "PHASE3_CLOSED",
            "mode": "NO_TEXT_BYPASS",
            "translation_count": 0,
            "source_video_sha256": authority["source_sha256"],
        },
    )

    output = root / "phase4_adaptive_final.mp4"
    encoder = _render_video_only(source, output, ffmpeg_binary=ffmpeg_binary)
    rendered_probe = _probe_media(output, ffprobe_binary)
    if int(rendered_probe["frame_count"]) != int(probe["frame_count"]):
        raise NoTextPassthroughError("NO_TEXT output frame count drifted")
    preview = root / "phase4_adaptive_visual_preview.mp4"
    shutil.copyfile(output, preview)

    provider = ocr_provider or build_local_residual_ocr_provider()
    qa_dir = root / "qa" / "phase4_adaptive_final_output_qa"
    qa = qa_collector(
        source,
        output,
        contract=contract,
        artifact_dir=qa_dir,
        ocr_provider=provider,
        require_final_audio=False,
    )
    qa_path = root / "qa" / "phase4_adaptive_final_output_qa.json"
    _write_json_atomic(qa_path, qa)
    if str(qa.get("status") or "") != "PASS" or list(qa.get("failed_checks") or []):
        raise NoTextPassthroughError(
            "NO_TEXT encoded-output QA failed: "
            + ",".join(str(row) for row in list(qa.get("failed_checks") or []))
        )

    visual_approval = {
        "schema_version": "phase4_visual_approval_v1",
        "status": "VISUAL_APPROVED",
        "approved_at": _now(),
        "operator_id": operator,
        "verification_method": "HASH_BOUND_NO_TEXT_SOURCE_PASSTHROUGH",
        "source_video_sha256": authority["source_sha256"],
        "no_text_approval_sha256": authority["approval_sha256"],
        "output_video_sha256": _sha256_file(output),
    }
    visual_approval["approval_sha256"] = _sha256_json(visual_approval)
    _write_json_atomic(root / "phase4_visual_approval.json", visual_approval)
    audio_approval = {
        "schema_version": "phase4_audio_approval_v1",
        "status": "AUDIO_APPROVED",
        "approved_at": _now(),
        "operator_id": operator,
        "audio_role": "verified_silent_or_absent_source_audio",
        "delivery_audio_present": False,
        "source_video_sha256": authority["source_sha256"],
        "authority": audio_authority,
    }
    audio_approval["approval_sha256"] = _sha256_json(audio_approval)
    _write_json_atomic(root / "phase4_audio_approval.json", audio_approval)
    recipe = {
        "schema_version": "phase4_render_recipe_v1",
        "status": "READY",
        "policy_version": RENDER_POLICY_VERSION,
        "mode": "NO_TEXT_SOURCE_PASSTHROUGH",
        "phase4_input_sha256": _sha256_file(contract_path),
        "source_video_sha256": authority["source_sha256"],
        "audio_strategy": "drop_verified_silent_or_absent_source_audio",
        "external_publish": False,
    }
    recipe["recipe_sha256"] = _sha256_json(recipe)
    _write_json_atomic(root / "phase4_render_recipe.json", recipe)
    render_meta = {
        "schema_version": "phase4_adaptive_render_meta_v1",
        "status": "FINAL_RENDERED",
        "visual_preview": False,
        "phase4_input_sha256": _sha256_file(contract_path),
        "source_video_sha256": authority["source_sha256"],
        "output_video_sha256": _sha256_file(output),
        "output_qa_status": "PASS",
        "output_qa_failed_checks": [],
        "frames": int(rendered_probe["frame_count"]),
        "encoder": encoder,
        "audio_mix": {
            "strategy": "drop_verified_silent_or_absent_source_audio",
            "background_present": False,
            "narration_complete": True,
            "source_audio_authority": audio_authority,
        },
        "artifacts": {"video": output.name, "visual_preview": preview.name},
    }
    _write_json_atomic(root / "phase4_adaptive_render_meta.json", render_meta)
    _write_json_atomic(
        root / "qa" / "phase4_adaptive_final_qa.json",
        {
            "schema_version": "phase4_adaptive_qa_v1",
            "status": "PASS",
            "failed_checks": [],
            "mode": "NO_TEXT_SOURCE_PASSTHROUGH",
        },
    )
    return {
        "status": "FINAL_RENDERED",
        "source_video_sha256": authority["source_sha256"],
        "output_video_sha256": render_meta["output_video_sha256"],
        "output_qa_status": "PASS",
        "encoder": encoder,
        "audio_authority": audio_authority,
    }
