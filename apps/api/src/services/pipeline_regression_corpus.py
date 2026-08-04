"""Deterministic local regression-corpus inspection and coverage accounting."""

from __future__ import annotations

import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any


class RegressionCorpusError(RuntimeError):
    pass


SUPPORTED_REGRESSION_VIDEO_EXTENSIONS = frozenset(
    {".mkv", ".mov", ".mp4", ".ogv", ".webm"}
)


REQUIRED_REAL_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "orientation": ("landscape", "portrait"),
    "resolution": ("720p_or_lower", "1080p_or_higher"),
    "timebase": ("CFR", "VFR"),
    "frame_rate": ("30fps_or_lower", "above_30fps"),
    "duration_band": ("under_35s", "35_to_45s", "45_to_60s"),
    "lighting": ("dark", "light", "mixed"),
    "motion": ("low", "medium", "high"),
    "audio": ("present", "absent"),
    # ``unknown`` is missing classification evidence, not a representative
    # input class that a corpus should intentionally acquire.
    "text_density": ("light", "medium", "dense"),
}


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rate(value: str | None) -> float:
    try:
        return float(Fraction(str(value or "0/1")))
    except (ValueError, ZeroDivisionError):
        return 0.0


def classify_probe(probe: dict[str, Any]) -> dict[str, str]:
    width = int(probe.get("width") or 0)
    height = int(probe.get("height") or 0)
    duration = float(probe.get("duration_seconds") or 0.0)
    nominal_fps = _rate(str(probe.get("r_frame_rate") or "0/1"))
    average_fps = _rate(str(probe.get("avg_frame_rate") or "0/1"))
    return {
        "orientation": "portrait" if height > width else "landscape",
        "resolution": (
            "1080p_or_higher" if min(width, height) >= 1080 else "720p_or_lower"
        ),
        "timebase": (
            "CFR"
            if nominal_fps > 0 and abs(nominal_fps - average_fps) <= 0.02
            else "VFR"
        ),
        "frame_rate": "above_30fps" if nominal_fps > 30.1 else "30fps_or_lower",
        "duration_band": (
            "under_35s"
            if duration < 35.0
            else "35_to_45s"
            if duration < 45.0
            else "45_to_60s"
        ),
        "audio": "present" if bool(probe.get("has_audio")) else "absent",
    }


def probe_video(video_path: str | Path) -> dict[str, Any]:
    video = Path(video_path).resolve()
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,width,height,r_frame_rate,avg_frame_rate",
            "-of",
            "json",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RegressionCorpusError(f"ffprobe failed for {video.name}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RegressionCorpusError(f"Invalid ffprobe output for {video.name}") from exc
    streams = list(payload.get("streams") or [])
    video_stream = next(
        (item for item in streams if item.get("codec_type") == "video"), None
    )
    if not isinstance(video_stream, dict):
        raise RegressionCorpusError(f"Video stream missing for {video.name}")
    format_row = dict(payload.get("format") or {})
    return {
        "duration_seconds": round(float(format_row.get("duration") or 0.0), 3),
        "size_bytes": int(format_row.get("size") or video.stat().st_size),
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "r_frame_rate": str(video_stream.get("r_frame_rate") or "0/1"),
        "avg_frame_rate": str(video_stream.get("avg_frame_rate") or "0/1"),
        "has_audio": any(item.get("codec_type") == "audio" for item in streams),
    }


def sample_visual_features(video_path: str | Path, sample_count: int = 7) -> dict[str, Any]:
    import cv2
    import numpy as np

    capture = cv2.VideoCapture(str(Path(video_path).resolve()))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if not capture.isOpened() or frame_count <= 0:
        capture.release()
        raise RegressionCorpusError("Could not sample regression video")
    indices = np.linspace(0, max(frame_count - 1, 0), max(2, sample_count)).astype(int)
    grays: list[Any] = []
    for index in indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ok, frame = capture.read()
        if ok and frame is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            grays.append(cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA))
    capture.release()
    # Some short WebM/OGV sources expose frame_count but do not support random
    # seeking reliably through OpenCV. Preserve original bytes and fall back to
    # bounded sequential passes instead of rejecting or transcoding them. The
    # first pass measures the actually decodable frame count because container
    # metadata can report a bogus FPS/frame_count; the second samples it.
    if len(grays) < 2:
        capture = cv2.VideoCapture(str(Path(video_path).resolve()))
        decoded_frame_count = 0
        while capture.isOpened():
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            decoded_frame_count += 1
        capture.release()
        actual_indices = np.linspace(
            0,
            max(decoded_frame_count - 1, 0),
            max(2, sample_count),
        ).astype(int)
        targets = {int(value) for value in actual_indices}
        capture = cv2.VideoCapture(str(Path(video_path).resolve()))
        grays = []
        frame_index = 0
        last_target = max(targets, default=-1)
        while capture.isOpened() and frame_index <= last_target:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            if frame_index in targets:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                grays.append(
                    cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)
                )
            frame_index += 1
        capture.release()
    if len(grays) < 2:
        raise RegressionCorpusError("Insufficient decoded samples for regression video")
    brightness_values = [float(gray.mean()) for gray in grays]
    contrast_values = [float(gray.std()) for gray in grays]
    motion_values = [
        float(cv2.absdiff(grays[index - 1], grays[index]).mean())
        for index in range(1, len(grays))
    ]
    mean_brightness = float(np.mean(brightness_values))
    brightness_range = float(max(brightness_values) - min(brightness_values))
    mean_motion = float(np.mean(motion_values))
    lighting = (
        "mixed"
        if brightness_range >= 45.0
        else "dark"
        if mean_brightness < 80.0
        else "light"
    )
    motion = "low" if mean_motion < 5.0 else "medium" if mean_motion < 14.0 else "high"
    return {
        "sample_count": len(grays),
        "mean_brightness": round(mean_brightness, 3),
        "brightness_range": round(brightness_range, 3),
        "mean_contrast": round(float(np.mean(contrast_values)), 3),
        "mean_motion": round(mean_motion, 3),
        "lighting": lighting,
        "motion": motion,
    }


def load_phase1_metrics(video_id: str, artifact_roots: list[str | Path]) -> dict[str, Any]:
    for raw_root in artifact_roots:
        root = Path(raw_root).resolve()
        candidates = (
            [root]
            if root.name in {video_id, f"local_{video_id}"}
            else [root / video_id, root / f"local_{video_id}"]
        )
        root_meta_path = root / "phase1_meta.json"
        if root_meta_path.is_file() and root not in candidates:
            root_meta = json.loads(root_meta_path.read_text(encoding="utf-8"))
            recorded_video = Path(str(root_meta.get("video") or "")).stem
            if recorded_video == video_id:
                candidates.append(root)
        for candidate in candidates:
            timeline_path = candidate / "master_timeline.json"
            meta_path = candidate / "phase1_meta.json"
            if not timeline_path.is_file() or not meta_path.is_file():
                continue
            timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
            rows = timeline if isinstance(timeline, list) else []
            hardsub_count = sum(
                1
                for row in rows
                if isinstance(row, dict)
                and (
                    str(row.get("role") or row.get("text_role") or "").lower()
                    == "hardsub"
                    or str(row.get("text_id") or "").startswith("sub_")
                )
            )
            track_count = len(rows)
            density = "dense" if track_count >= 45 else "medium" if track_count >= 25 else "light"
            return {
                "artifact_root": candidate,
                "track_count": track_count,
                "hardsub_count": hardsub_count,
                "text_density": density,
            }
    return {
        "artifact_root": None,
        "track_count": None,
        "hardsub_count": None,
        "text_density": "unknown",
    }


def build_corpus_payload(
    *,
    cases: list[dict[str, Any]],
    workspace_root: str | Path,
    policy_version: str = "pipeline_regression_policy_v1",
) -> dict[str, Any]:
    workspace = Path(workspace_root).resolve()
    normalized_cases: list[dict[str, Any]] = []
    coverage: dict[str, set[str]] = {
        key: set() for key in REQUIRED_REAL_DIMENSIONS
    }
    for raw_case in cases:
        case = dict(raw_case)
        dimensions = dict(case.get("dimensions") or {})
        for key in coverage:
            value = str(dimensions.get(key) or "")
            if value:
                coverage[key].add(value)
        for path_key in ("video_path", "phase1_artifact_root"):
            raw_path = case.get(path_key)
            if raw_path:
                resolved = Path(raw_path).resolve()
                case[path_key] = (
                    resolved.relative_to(workspace).as_posix()
                    if resolved.is_relative_to(workspace)
                    else str(resolved)
                )
        normalized_cases.append(case)
    coverage_rows = {key: sorted(values) for key, values in coverage.items()}
    gaps = {
        key: sorted(set(required) - coverage[key])
        for key, required in REQUIRED_REAL_DIMENSIONS.items()
        if set(required) - coverage[key]
    }
    payload = {
        "schema_version": "pipeline_regression_corpus_v1",
        "policy_version": policy_version,
        "status": "CORPUS_READY_WITH_GAPS" if gaps else "CORPUS_READY",
        "case_count": len(normalized_cases),
        "cases": normalized_cases,
        "coverage": coverage_rows,
        "real_video_gaps": gaps,
        "closure_rule": (
            "Do not claim universal closure while real_video_gaps is non-empty."
        ),
    }
    payload["corpus_sha256"] = _sha256_json(payload)
    return payload
