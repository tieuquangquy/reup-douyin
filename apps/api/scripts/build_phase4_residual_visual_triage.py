"""Build hash-bound visual evidence for blocked Phase-4 residual CJK cases.

The pack is proposal-only.  It reads the locked Phase 1-4 authority chain and
writes source/render comparisons for operator review.  It never mutates OCR,
translation, approval, remediation, render, export, or publish authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from statistics import median
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from scripts.build_phase2_residual_remediation_proposal import (
    cluster_residual_detections,
)
from src.media_pipeline.video_renderer.phase4_input_contract import (
    Phase4InputError,
    prepare_phase4_from_root,
)


SCHEMA_VERSION = "phase4_residual_visual_triage_v1"
BATCH_SCHEMA_VERSION = "phase4_residual_visual_triage_index_v1"
_FRAME_RE = re.compile(r"^frame_(\d{6})\.jpg$")
_LATIN_RE = re.compile(r"[A-Za-z\u00c0-\u024f]")


class Phase4ResidualVisualTriageError(RuntimeError):
    pass


FrameLoader = Callable[[Path, Sequence[int]], Mapping[int, np.ndarray]]


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4ResidualVisualTriageError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise Phase4ResidualVisualTriageError(
            f"{path.name} must contain an object"
        )
    return payload


def _load_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4ResidualVisualTriageError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, list):
        raise Phase4ResidualVisualTriageError(
            f"{path.name} must contain a list"
        )
    return [dict(row) for row in payload if isinstance(row, Mapping)]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_self_hash(
    payload: Mapping[str, Any], field: str, *, label: str
) -> None:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    if len(claimed) != 64 or claimed != _sha256_json(unsigned):
        raise Phase4ResidualVisualTriageError(f"{label} self-hash is invalid")


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _write_jpeg_atomic(path: Path, image: np.ndarray) -> None:
    import cv2

    ok, encoded = cv2.imencode(
        ".jpg", np.asarray(image), [int(cv2.IMWRITE_JPEG_QUALITY), 92]
    )
    if not ok:
        raise Phase4ResidualVisualTriageError(
            f"Cannot encode visual evidence: {path.name}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encoded.tobytes())
    temporary.replace(path)


def _safe_ref(root: Path, raw_path: str, *, label: str) -> Path:
    path = (root / raw_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise Phase4ResidualVisualTriageError(f"Invalid {label} path")
    return path


def _verify_ref(
    root: Path, ref: Mapping[str, Any], *, label: str
) -> Path:
    path = _safe_ref(root, str(ref.get("path") or ""), label=label)
    expected = str(ref.get("sha256") or "")
    if len(expected) != 64 or expected != _sha256_file(path):
        raise Phase4ResidualVisualTriageError(f"Stale {label} artifact")
    return path


def _rect(raw: Mapping[str, Any]) -> tuple[float, float, float, float]:
    try:
        x = float(raw.get("x") or 0.0)
        y = float(raw.get("y") or 0.0)
        width = float(raw.get("width") or 0.0)
        height = float(raw.get("height") or 0.0)
    except (TypeError, ValueError) as exc:
        raise Phase4ResidualVisualTriageError(
            "Residual geometry is invalid"
        ) from exc
    if (
        width <= 0
        or height <= 0
        or min(x, y) < 0
        or x + width > 1.001
        or y + height > 1.001
    ):
        raise Phase4ResidualVisualTriageError(
            "Residual geometry is out of bounds"
        )
    return x, y, x + width, y + height


def _intersection_over_smaller(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    smaller = min(
        max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1]),
        max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1]),
    )
    return intersection / smaller if smaller > 0 else 0.0


def _normalized_master_geometry(
    row: Mapping[str, Any], *, width: int, height: int
) -> dict[str, float] | None:
    coords = list(row.get("box_coords") or [])
    if len(coords) != 4 or width < 2 or height < 2:
        return None
    try:
        x0, y0, x1, y1 = [float(value) for value in coords]
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    geometry = {
        "x": x0 / width,
        "y": y0 / height,
        "width": (x1 - x0) / width,
        "height": (y1 - y0) / height,
    }
    try:
        _rect(geometry)
    except Phase4ResidualVisualTriageError:
        return None
    return geometry


def phase1_geometry_intersections(
    cluster: Mapping[str, Any],
    master_timeline: Sequence[Mapping[str, Any]],
    *,
    frame_width: int,
    frame_height: int,
) -> list[dict[str, Any]]:
    """Return active Phase-1 boxes that touch any detection in a cluster."""

    by_id: dict[str, dict[str, Any]] = {}
    for detection in list(cluster.get("detections") or []):
        if not isinstance(detection, Mapping):
            continue
        frame_index = int(detection.get("frame_index") or 0)
        residual_rect = _rect(dict(detection.get("geometry") or {}))
        for raw in master_timeline:
            row = dict(raw)
            start = int(row.get("start_frame") or 0)
            end = int(row.get("end_frame") or start)
            active = start <= frame_index <= end
            geometry = _normalized_master_geometry(
                row, width=frame_width, height=frame_height
            )
            if geometry is None:
                continue
            overlap = _intersection_over_smaller(residual_rect, _rect(geometry))
            if overlap < 0.05:
                continue
            text_id = str(row.get("text_id") or "unknown")
            candidate = {
                "text_id": text_id,
                "start_frame": start,
                "end_frame": end,
                "geometry": geometry,
                "intersection_over_smaller": round(overlap, 6),
                "matched_frame_indices": [frame_index],
                "active_matched_frame_indices": [frame_index] if active else [],
                "active_on_residual_frame": active,
                "source_text": str(
                    row.get("ocr_text")
                    or row.get("text")
                    or row.get("recognized_text")
                    or ""
                ),
            }
            existing = by_id.get(text_id)
            if existing is None:
                by_id[text_id] = candidate
            else:
                existing["intersection_over_smaller"] = max(
                    float(existing["intersection_over_smaller"]), overlap
                )
                existing["intersection_over_smaller"] = round(
                    float(existing["intersection_over_smaller"]), 6
                )
                existing["matched_frame_indices"] = sorted(
                    {
                        *list(existing.get("matched_frame_indices") or []),
                        frame_index,
                    }
                )
                existing["active_matched_frame_indices"] = sorted(
                    {
                        *list(existing.get("active_matched_frame_indices") or []),
                        *([frame_index] if active else []),
                    }
                )
                existing["active_on_residual_frame"] = bool(
                    existing.get("active_on_residual_frame") or active
                )
    return sorted(
        by_id.values(),
        key=lambda row: (-float(row["intersection_over_smaller"]), row["text_id"]),
    )


def _restore_temporal_evidence(
    clusters: Sequence[Mapping[str, Any]],
    raw_detections: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Restore fields intentionally omitted by the shared clustering helper."""

    remaining = [dict(row) for row in raw_detections]
    output: list[dict[str, Any]] = []
    for raw_cluster in clusters:
        cluster = dict(raw_cluster)
        enriched: list[dict[str, Any]] = []
        for raw_detection in list(cluster.get("detections") or []):
            detection = dict(raw_detection)
            match = next(
                (
                    row
                    for row in remaining
                    if int(row.get("frame_index") or 0)
                    == int(detection.get("frame_index") or 0)
                    and str(row.get("text") or "")
                    == str(detection.get("text") or "")
                    and dict(row.get("geometry") or {})
                    == dict(detection.get("geometry") or {})
                ),
                None,
            )
            if match is not None:
                for key in (
                    "temporal_confirmation",
                    "provider",
                    "raw_detection_sha256",
                ):
                    if key in match:
                        detection[key] = match[key]
            enriched.append(detection)
        cluster["detections"] = enriched
        output.append(cluster)
    return output


def recommend_cluster(
    cluster: Mapping[str, Any],
    intersections: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Produce a conservative, non-authoritative operator recommendation."""

    detections = [
        dict(row)
        for row in list(cluster.get("detections") or [])
        if isinstance(row, Mapping)
    ]
    confidences = [float(row.get("confidence") or 0.0) for row in detections]
    confirmed = sum(
        str(dict(row.get("temporal_confirmation") or {}).get("status") or "")
        .upper()
        .startswith("CONFIRMED")
        for row in detections
    )
    observed = " ".join(str(row.get("text") or "") for row in detections)
    strong_intersections = [
        row
        for row in intersections
        if float(row.get("intersection_over_smaller") or 0.0) >= 0.60
    ]
    reasons: list[str] = []
    if confirmed == 0 and (median(confidences) if confidences else 0.0) < 0.65:
        action = "FALSE_POSITIVE"
        reasons.append("low_confidence_without_adjacent_confirmation")
    elif strong_intersections:
        action = "NEEDS_OPERATOR_INPUT"
        reasons.append("overlaps_existing_phase1_geometry")
    elif _LATIN_RE.search(observed):
        action = "NEEDS_OPERATOR_INPUT"
        reasons.append("mixed_cjk_and_localized_text_requires_boundary_choice")
    elif confirmed < len(detections):
        action = "NEEDS_OPERATOR_INPUT"
        reasons.append("temporal_confirmation_is_incomplete")
    else:
        action = "REMEDIATE"
        reasons.append("temporally_confirmed_residual_without_phase1_coverage")
    return {
        "action": action,
        "recommendation_only": True,
        "operator_decision_required": True,
        "reasons": reasons,
        "signals": {
            "detections": len(detections),
            "adjacent_confirmed": confirmed,
            "median_confidence": round(
                median(confidences) if confidences else 0.0, 6
            ),
            "strong_phase1_intersections": len(strong_intersections),
        },
    }


def _default_frame_loader(
    source: Path, frame_indices: Sequence[int]
) -> Mapping[int, np.ndarray]:
    """Decode exact frame numbers sequentially for VFR-safe evidence."""

    import cv2

    targets = sorted({int(index) for index in frame_indices if int(index) >= 0})
    if not targets:
        return {}
    wanted = set(targets)
    decoded: dict[int, np.ndarray] = {}
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise Phase4ResidualVisualTriageError("Cannot open source video")
    try:
        for frame_index in range(targets[-1] + 1):
            ok, frame = capture.read()
            if not ok or frame is None:
                raise Phase4ResidualVisualTriageError(
                    f"Cannot sequentially decode source frame {frame_index}"
                )
            if frame_index in wanted:
                decoded[frame_index] = frame
    finally:
        capture.release()
    return decoded


def _rendered_frame_map(
    root: Path, meta: Mapping[str, Any]
) -> dict[int, Path]:
    raw_refs = [
        *list(dict(meta.get("artifacts") or {}).get("samples") or []),
        *list(
            dict(meta.get("residual_cjk") or {}).get(
                "temporal_confirmation_frames"
            )
            or []
        ),
    ]
    mapped: dict[int, Path] = {}
    for raw in raw_refs:
        raw_path = str(raw or "")
        match = _FRAME_RE.match(Path(raw_path).name)
        if match is None:
            continue
        path = _safe_ref(root, raw_path, label="Phase 4 rendered sample")
        frame_index = int(match.group(1))
        if frame_index not in mapped or "residual_temporal_confirmation" not in raw_path:
            mapped[frame_index] = path
    return mapped


def _target_frames(
    cluster: Mapping[str, Any], *, frame_count: int
) -> tuple[list[int], list[dict[str, Any]]]:
    targets: set[int] = set()
    coverage: list[dict[str, Any]] = []
    for raw in list(cluster.get("detections") or []):
        detection = dict(raw)
        anchor = int(detection.get("frame_index") or 0)
        expected = [
            index
            for index in (anchor - 1, anchor, anchor + 1)
            if 0 <= index < frame_count
        ]
        targets.update(expected)
        coverage.append(
            {
                "detection_frame_index": anchor,
                "expected_source_render_frames": expected,
            }
        )
    return sorted(targets), coverage


def _nearest_detection(
    cluster: Mapping[str, Any], frame_index: int
) -> dict[str, Any]:
    detections = [dict(row) for row in list(cluster.get("detections") or [])]
    if not detections:
        raise Phase4ResidualVisualTriageError("Residual cluster is empty")
    return min(
        detections,
        key=lambda row: (
            abs(int(row.get("frame_index") or 0) - frame_index),
            -float(row.get("confidence") or 0.0),
        ),
    )


def _pixel_bounds(
    geometry: Mapping[str, Any], *, width: int, height: int
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = _rect(geometry)
    margin = max(12, int(round(max((x1 - x0) * width, (y1 - y0) * height) * 0.30)))
    return (
        max(0, int(math.floor(x0 * width)) - margin),
        max(0, int(math.floor(y0 * height)) - margin),
        min(width, int(math.ceil(x1 * width)) + margin),
        min(height, int(math.ceil(y1 * height)) + margin),
    )


def _draw_geometry(
    image: np.ndarray,
    geometry: Mapping[str, Any],
    *,
    color: tuple[int, int, int],
    width: int = 3,
) -> np.ndarray:
    import cv2

    output = np.asarray(image).copy()
    height, frame_width = output.shape[:2]
    x0, y0, x1, y1 = _rect(geometry)
    cv2.rectangle(
        output,
        (int(round(x0 * frame_width)), int(round(y0 * height))),
        (int(round(x1 * frame_width)), int(round(y1 * height))),
        color,
        width,
    )
    return output


def _tile(image: np.ndarray, label: str, *, width: int = 320, height: int = 220) -> np.ndarray:
    import cv2

    canvas = np.full((height, width, 3), 28, dtype=np.uint8)
    label_height = 30
    source = np.asarray(image)
    available_height = height - label_height
    scale = min(width / source.shape[1], available_height / source.shape[0])
    resized_width = max(1, int(round(source.shape[1] * scale)))
    resized_height = max(1, int(round(source.shape[0] * scale)))
    resized = cv2.resize(source, (resized_width, resized_height))
    x = (width - resized_width) // 2
    y = label_height + (available_height - resized_height) // 2
    canvas[y : y + resized_height, x : x + resized_width] = resized
    cv2.putText(
        canvas,
        label[:42],
        (9, 21),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.50,
        (240, 240, 240),
        1,
        cv2.LINE_AA,
    )
    return canvas


def _markdown_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def render_case_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Phase 4 Residual CJK Visual Triage",
        "",
        f"- Case: `{payload.get('case_id')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Pack SHA-256: `{payload.get('triage_sha256')}`",
        "- Đây là bằng chứng/đề xuất, chưa ghi approval hoặc remediation authority.",
        "",
    ]
    for cluster in list(payload.get("clusters") or []):
        recommendation = dict(cluster.get("recommendation") or {})
        lines.extend(
            [
                f"## {_markdown_escape(cluster.get('cluster_id'))} — {_markdown_escape(cluster.get('signature'))}",
                "",
                f"- Đề xuất: `{recommendation.get('action')}` (operator phải quyết định)",
                f"- Frame đại diện: `{cluster.get('representative_frame_index')}`",
                f"- Giao cắt geometry Phase 1: `{len(list(cluster.get('phase1_geometry_intersections') or []))}`",
                "",
                f"![Visual evidence]({dict(cluster.get('contact_sheet_ref') or {}).get('path')})",
                "",
                "| Phase 1 text_id | Overlap | Active frames | OCR nguồn |",
                "|---|---:|---|---|",
            ]
        )
        intersections = list(cluster.get("phase1_geometry_intersections") or [])
        if intersections:
            for row in intersections:
                lines.append(
                    f"| `{_markdown_escape(row.get('text_id'))}` | "
                    f"{float(row.get('intersection_over_smaller') or 0.0):.3f} | "
                    f"{row.get('start_frame')}–{row.get('end_frame')} | "
                    f"{_markdown_escape(row.get('source_text'))} |"
                )
        else:
            lines.append("| - | - | - | - |")
        lines.append("")
    return "\n".join(lines)


def render_batch_markdown(payload: Mapping[str, Any]) -> str:
    counts = dict(payload.get("counts") or {})
    lines = [
        "# Phase 4 V22.1 Residual Visual Triage Index",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Review token: `{payload.get('operator_review_token')}`",
        f"- Cases: `{counts.get('cases', 0)}`",
        f"- Clusters: `{counts.get('clusters', 0)}`",
        f"- REMEDIATE: `{counts.get('remediate', 0)}`",
        f"- FALSE_POSITIVE: `{counts.get('false_positive', 0)}`",
        f"- NEEDS_OPERATOR_INPUT: `{counts.get('needs_operator_input', 0)}`",
        f"- Batch SHA-256: `{payload.get('batch_triage_sha256')}`",
        "",
        "| Case | Clusters | Recommendations | Review pack |",
        "|---|---:|---|---|",
    ]
    for row in list(payload.get("cases") or []):
        summary = dict(row.get("recommendations") or {})
        recommendation_text = ", ".join(
            f"{key}={value}" for key, value in sorted(summary.items()) if value
        )
        lines.append(
            f"| `{row.get('case_id')}` | {row.get('clusters')} | "
            f"{recommendation_text or '-'} | "
            f"[mở pack]({row.get('markdown_path')}) |"
        )
    lines.extend(
        [
            "",
            "Pack này không ghi OCR approval, remediation, visual approval, TTS, render, export hoặc publish state.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_batch_index(run: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    index_path = run / "phase4_batch_preflight_index.json"
    index = _load_object(index_path)
    _verify_self_hash(index, "batch_preflight_sha256", label="Batch preflight")
    state_path = _verify_ref(
        run, dict(index.get("batch_state_ref") or {}), label="batch state"
    )
    state = _load_object(state_path)
    state_by_case = {
        str(row.get("case_id") or ""): str(row.get("status") or "")
        for row in list(state.get("cases") or [])
        if isinstance(row, Mapping)
    }
    triage_rows: list[dict[str, Any]] = []
    for raw in list(index.get("cases") or []):
        row = dict(raw)
        if str(row.get("review_result") or "") != "OPERATOR_TRIAGE_REQUIRED":
            continue
        case_id = str(row.get("case_id") or "")
        if state_by_case.get(case_id) != "WAITING_RESIDUAL_CJK_OPERATOR_TRIAGE":
            raise Phase4ResidualVisualTriageError(
                f"Batch state drifted for {case_id or 'unknown'}"
            )
        triage_rows.append(row)
    if not triage_rows:
        raise Phase4ResidualVisualTriageError(
            "Batch preflight has no operator-triage cases"
        )
    return index, triage_rows


def _build_case_pack(
    *,
    run: Path,
    row: Mapping[str, Any],
    frame_loader: FrameLoader,
) -> dict[str, Any]:
    import cv2

    case_id = str(row.get("case_id") or "").strip()
    root = (run / case_id).resolve()
    if not case_id or not root.is_relative_to(run) or not root.is_dir():
        raise Phase4ResidualVisualTriageError("Invalid triage case root")
    meta_path = _verify_ref(
        run, dict(row.get("preflight_meta_ref") or {}), label=f"{case_id} preflight meta"
    )
    report_path = _verify_ref(
        run,
        dict(row.get("preflight_report_ref") or {}),
        label=f"{case_id} preflight report",
    )
    attempt_path = _verify_ref(
        run, dict(row.get("triage_ref") or {}), label=f"{case_id} triage attempt"
    )
    meta = _load_object(meta_path)
    report = _load_object(report_path)
    attempt = _load_object(attempt_path)
    _verify_self_hash(attempt, "attempt_sha256", label=f"{case_id} attempt")
    if bool(attempt.get("operator_approval_written")):
        raise Phase4ResidualVisualTriageError(
            f"{case_id} triage attempt unexpectedly contains approval"
        )
    if str(dict(attempt.get("phase4_preflight_meta_ref") or {}).get("sha256") or "") != _sha256_file(meta_path):
        raise Phase4ResidualVisualTriageError(f"{case_id} attempt is stale")
    if (
        str(meta.get("status") or "") != "PHASE4_PREFLIGHT_BLOCKED"
        or str(meta.get("final_render_gate") or "")
        != "BLOCKED_VISUAL_RESIDUAL_CJK"
        or str(report.get("status") or "") != "PHASE4_PREFLIGHT_BLOCKED"
    ):
        raise Phase4ResidualVisualTriageError(
            f"{case_id} is not at the residual CJK triage gate"
        )

    try:
        fresh_contract, _fresh_report, source = prepare_phase4_from_root(root)
    except Phase4InputError as exc:
        raise Phase4ResidualVisualTriageError(
            f"{case_id} authority chain is invalid: {exc}"
        ) from exc
    phase3_path = root / "phase3_render_handoff.json"
    master_path = root / "master_timeline.json"
    preview_path = root / "phase4_render_input_preview.json"
    for required in (phase3_path, master_path, preview_path):
        if not required.is_file():
            raise Phase4ResidualVisualTriageError(
                f"Missing required artifact: {required.name}"
            )
    if str(meta.get("phase3_render_handoff_sha256") or "") != _sha256_file(phase3_path):
        raise Phase4ResidualVisualTriageError(f"{case_id} Phase 4 meta is stale")
    preview = _load_object(preview_path)
    fresh_refs = dict(fresh_contract.get("refs") or {})
    preview_refs = dict(preview.get("refs") or {})
    source_hash = _sha256_file(source)
    if (
        str(dict(fresh_refs.get("source_video_ref") or {}).get("sha256") or "")
        != source_hash
        or dict(preview_refs.get("source_video_ref") or {})
        != dict(fresh_refs.get("source_video_ref") or {})
        or dict(preview_refs.get("phase3_render_handoff_ref") or {})
        != dict(fresh_refs.get("phase3_render_handoff_ref") or {})
    ):
        raise Phase4ResidualVisualTriageError(
            f"{case_id} render preview authority is stale"
        )
    video = dict(preview.get("video") or {})
    fresh_video = dict(fresh_contract.get("video") or {})
    for key in ("frame_width", "frame_height", "frame_count", "fps"):
        if video.get(key) != fresh_video.get(key):
            raise Phase4ResidualVisualTriageError(
                f"{case_id} video authority drifted"
            )
    frame_width = int(video.get("frame_width") or 0)
    frame_height = int(video.get("frame_height") or 0)
    frame_count = int(video.get("frame_count") or 0)
    if min(frame_width, frame_height, frame_count) < 1:
        raise Phase4ResidualVisualTriageError(f"{case_id} video metadata is invalid")

    residual = dict(meta.get("residual_cjk") or {})
    if not bool(residual.get("complete")) or residual.get("error"):
        raise Phase4ResidualVisualTriageError(
            f"{case_id} residual evidence is incomplete"
        )
    raw_detections = [
        dict(row)
        for row in list(residual.get("detections") or [])
        if isinstance(row, Mapping)
    ]
    clusters = _restore_temporal_evidence(
        cluster_residual_detections(raw_detections), raw_detections
    )
    if not clusters:
        raise Phase4ResidualVisualTriageError(
            f"{case_id} has no reviewable residual cluster"
        )
    master = _load_list(master_path)
    rendered_map = _rendered_frame_map(root, meta)
    all_targets = sorted(
        {
            frame
            for cluster in clusters
            for frame in _target_frames(cluster, frame_count=frame_count)[0]
        }
    )
    missing_rendered = [frame for frame in all_targets if frame not in rendered_map]
    if missing_rendered:
        raise Phase4ResidualVisualTriageError(
            f"{case_id} rendered adjacent evidence is missing: {missing_rendered}"
        )
    decoded = dict(frame_loader(source, all_targets))
    missing_source = [frame for frame in all_targets if frame not in decoded]
    if missing_source:
        raise Phase4ResidualVisualTriageError(
            f"{case_id} source adjacent evidence is missing: {missing_source}"
        )

    cluster_payloads: list[dict[str, Any]] = []
    output_root = root / "qa" / "phase4_residual_visual_triage"
    for cluster_number, cluster in enumerate(clusters, start=1):
        cluster_id = f"cluster_{cluster_number:03d}_{hashlib.sha256(str(cluster['signature']).encode('utf-8')).hexdigest()[:8]}"
        cluster_dir = output_root / cluster_id
        targets, coverage = _target_frames(cluster, frame_count=frame_count)
        intersections = phase1_geometry_intersections(
            cluster,
            master,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        evidence_rows: list[dict[str, Any]] = []
        sheet_rows: list[np.ndarray] = []
        detection_frames = {
            int(item.get("frame_index") or 0)
            for item in list(cluster.get("detections") or [])
        }
        for frame_index in targets:
            source_frame = np.asarray(decoded[frame_index])
            if source_frame.shape[:2] != (frame_height, frame_width):
                raise Phase4ResidualVisualTriageError(
                    f"{case_id} source frame shape drifted at {frame_index}"
                )
            rendered_path = rendered_map[frame_index]
            rendered_frame = cv2.imread(str(rendered_path), cv2.IMREAD_COLOR)
            if rendered_frame is None or rendered_frame.shape != source_frame.shape:
                raise Phase4ResidualVisualTriageError(
                    f"{case_id} rendered frame shape drifted at {frame_index}"
                )
            nearest = _nearest_detection(cluster, frame_index)
            geometry = dict(nearest.get("geometry") or {})
            x0, y0, x1, y1 = _pixel_bounds(
                geometry, width=frame_width, height=frame_height
            )
            source_crop = source_frame[y0:y1, x0:x1]
            rendered_crop = rendered_frame[y0:y1, x0:x1]
            if source_crop.size == 0 or rendered_crop.size == 0:
                raise Phase4ResidualVisualTriageError(
                    f"{case_id} evidence crop is empty at {frame_index}"
                )
            source_path = cluster_dir / f"source_frame_{frame_index:06d}.jpg"
            source_crop_path = cluster_dir / f"source_crop_{frame_index:06d}.jpg"
            render_crop_path = cluster_dir / f"render_crop_{frame_index:06d}.jpg"
            _write_jpeg_atomic(source_path, source_frame)
            _write_jpeg_atomic(source_crop_path, source_crop)
            _write_jpeg_atomic(render_crop_path, rendered_crop)

            source_marked = _draw_geometry(
                source_frame, geometry, color=(0, 255, 255), width=3
            )
            for intersection in intersections:
                if (
                    int(intersection.get("start_frame") or 0)
                    <= frame_index
                    <= int(intersection.get("end_frame") or 0)
                ):
                    source_marked = _draw_geometry(
                        source_marked,
                        dict(intersection.get("geometry") or {}),
                        color=(255, 128, 0),
                        width=2,
                    )
            rendered_marked = _draw_geometry(
                rendered_frame, geometry, color=(0, 0, 255), width=3
            )
            relation = "exact" if frame_index in detection_frames else "adjacent"
            sheet_rows.append(
                np.hstack(
                    [
                        _tile(source_marked, f"SOURCE f={frame_index} {relation}"),
                        _tile(rendered_marked, f"RENDER f={frame_index} {relation}"),
                        _tile(source_crop, f"SOURCE CROP f={frame_index}"),
                        _tile(rendered_crop, f"RENDER CROP f={frame_index}"),
                    ]
                )
            )
            evidence_rows.append(
                {
                    "frame_index": frame_index,
                    "relation": relation,
                    "nearest_detection_frame_index": int(
                        nearest.get("frame_index") or 0
                    ),
                    "geometry": geometry,
                    "source_frame_ref": {
                        "path": source_path.relative_to(root).as_posix(),
                        "sha256": _sha256_file(source_path),
                    },
                    "rendered_frame_ref": {
                        "path": rendered_path.relative_to(root).as_posix(),
                        "sha256": _sha256_file(rendered_path),
                    },
                    "source_crop_ref": {
                        "path": source_crop_path.relative_to(root).as_posix(),
                        "sha256": _sha256_file(source_crop_path),
                    },
                    "rendered_crop_ref": {
                        "path": render_crop_path.relative_to(root).as_posix(),
                        "sha256": _sha256_file(render_crop_path),
                    },
                }
            )
        contact_path = cluster_dir / "contact_sheet.jpg"
        _write_jpeg_atomic(contact_path, np.vstack(sheet_rows))
        evidence_indices = {int(item["frame_index"]) for item in evidence_rows}
        for coverage_row in coverage:
            expected = set(coverage_row["expected_source_render_frames"])
            coverage_row["complete"] = expected.issubset(evidence_indices)
        representative = max(
            list(cluster.get("detections") or []),
            key=lambda item: float(dict(item).get("confidence") or 0.0),
        )
        cluster_payloads.append(
            {
                "cluster_id": cluster_id,
                "signature": cluster.get("signature"),
                "observed_texts": sorted(
                    {
                        str(dict(item).get("text") or "")
                        for item in list(cluster.get("detections") or [])
                    }
                ),
                "representative_frame_index": int(
                    dict(representative).get("frame_index") or 0
                ),
                "detections": list(cluster.get("detections") or []),
                "phase1_geometry_intersections": intersections,
                "recommendation": recommend_cluster(cluster, intersections),
                "coverage_by_detection": coverage,
                "source_render_adjacent_complete": all(
                    bool(item.get("complete")) for item in coverage
                ),
                "evidence_frames": evidence_rows,
                "contact_sheet_ref": {
                    "path": contact_path.relative_to(root).as_posix(),
                    "sha256": _sha256_file(contact_path),
                },
            }
        )

    case_payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "RESIDUAL_VISUAL_TRIAGE_OPERATOR_REVIEW_REQUIRED",
        "case_id": case_id,
        "operator_approval_written": False,
        "authority_mutation_written": False,
        "authority_refs": {
            "master_timeline": {
                "path": master_path.name,
                "sha256": _sha256_file(master_path),
            },
            "phase3_render_handoff": {
                "path": phase3_path.name,
                "sha256": _sha256_file(phase3_path),
            },
            "phase4_render_input_preview": {
                "path": preview_path.name,
                "sha256": _sha256_file(preview_path),
            },
            "phase4_preflight_meta": {
                "path": meta_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(meta_path),
            },
            "phase4_preflight_report": {
                "path": report_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(report_path),
            },
            "proposal_attempt": {
                "path": attempt_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(attempt_path),
                "attempt_sha256": attempt.get("attempt_sha256"),
            },
            "source_video": {
                "path": source.name,
                "sha256": source_hash,
            },
        },
        "video": video,
        "attempt_reason": attempt.get("reason"),
        "counts": {
            "clusters": len(cluster_payloads),
            "detections": sum(
                len(list(cluster.get("detections") or []))
                for cluster in cluster_payloads
            ),
            "evidence_frames": sum(
                len(list(cluster.get("evidence_frames") or []))
                for cluster in cluster_payloads
            ),
            "phase1_geometry_intersections": sum(
                len(list(cluster.get("phase1_geometry_intersections") or []))
                for cluster in cluster_payloads
            ),
        },
        "clusters": cluster_payloads,
    }
    case_payload["triage_sha256"] = _sha256_json(case_payload)
    case_json = root / "phase4_residual_visual_triage.json"
    case_markdown = root / "PHASE4_RESIDUAL_VISUAL_TRIAGE.md"
    _write_json_atomic(case_json, case_payload)
    _write_text_atomic(case_markdown, render_case_markdown(case_payload))
    return case_payload


def build_visual_triage_pack(
    *,
    run_root: str | Path,
    frame_loader: FrameLoader | None = None,
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    if not run.is_dir():
        raise Phase4ResidualVisualTriageError("Run root does not exist")
    preflight_index, triage_rows = _validate_batch_index(run)
    load_frames = frame_loader or _default_frame_loader
    case_rows: list[dict[str, Any]] = []
    totals = {
        "cases": 0,
        "clusters": 0,
        "evidence_frames": 0,
        "remediate": 0,
        "false_positive": 0,
        "needs_operator_input": 0,
    }
    for row in sorted(triage_rows, key=lambda item: str(item.get("case_id") or "")):
        payload = _build_case_pack(
            run=run, row=row, frame_loader=load_frames
        )
        recommendations = {
            "REMEDIATE": 0,
            "FALSE_POSITIVE": 0,
            "NEEDS_OPERATOR_INPUT": 0,
        }
        for cluster in list(payload.get("clusters") or []):
            action = str(dict(cluster.get("recommendation") or {}).get("action") or "")
            if action in recommendations:
                recommendations[action] += 1
        case_id = str(payload.get("case_id") or "")
        case_json = run / case_id / "phase4_residual_visual_triage.json"
        case_rows.append(
            {
                "case_id": case_id,
                "clusters": int(dict(payload.get("counts") or {}).get("clusters") or 0),
                "evidence_frames": int(
                    dict(payload.get("counts") or {}).get("evidence_frames") or 0
                ),
                "recommendations": recommendations,
                "triage_ref": {
                    "path": case_json.relative_to(run).as_posix(),
                    "sha256": _sha256_file(case_json),
                    "triage_sha256": payload.get("triage_sha256"),
                },
                "markdown_path": f"{case_id}/PHASE4_RESIDUAL_VISUAL_TRIAGE.md",
            }
        )
        totals["cases"] += 1
        totals["clusters"] += case_rows[-1]["clusters"]
        totals["evidence_frames"] += case_rows[-1]["evidence_frames"]
        totals["remediate"] += recommendations["REMEDIATE"]
        totals["false_positive"] += recommendations["FALSE_POSITIVE"]
        totals["needs_operator_input"] += recommendations["NEEDS_OPERATOR_INPUT"]

    token_seed = _sha256_json(
        {
            "batch_preflight_sha256": preflight_index.get(
                "batch_preflight_sha256"
            ),
            "case_triage_sha256": [
                dict(row.get("triage_ref") or {}).get("triage_sha256")
                for row in case_rows
            ],
        }
    )[:12].upper()
    batch_payload: dict[str, Any] = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "status": "PHASE4_RESIDUAL_VISUAL_TRIAGE_REVIEW_REQUIRED",
        "operator_review_token": (
            f"PHASE4_RESIDUAL_VISUAL_TRIAGE_REVIEW_REQUIRED_V22_1_{token_seed}"
        ),
        "operator_approval_written": False,
        "authority_mutation_written": False,
        "batch_preflight_ref": {
            "path": "phase4_batch_preflight_index.json",
            "sha256": _sha256_file(run / "phase4_batch_preflight_index.json"),
            "batch_preflight_sha256": preflight_index.get(
                "batch_preflight_sha256"
            ),
        },
        "counts": totals,
        "cases": case_rows,
    }
    batch_payload["batch_triage_sha256"] = _sha256_json(batch_payload)
    _write_json_atomic(
        run / "phase4_residual_visual_triage_index.json", batch_payload
    )
    _write_text_atomic(
        run / "PHASE4_RESIDUAL_VISUAL_TRIAGE_INDEX.md",
        render_batch_markdown(batch_payload),
    )
    return batch_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase4_residual_visual_triage"
    )
    parser.add_argument("run_root")
    args = parser.parse_args()
    try:
        payload = build_visual_triage_pack(run_root=args.run_root)
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "operator_review_token": payload["operator_review_token"],
                    "counts": payload["counts"],
                    "batch_triage_sha256": payload["batch_triage_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, Phase4ResidualVisualTriageError) as exc:
        print(f"[PHASE4-RESIDUAL-VISUAL-TRIAGE][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
