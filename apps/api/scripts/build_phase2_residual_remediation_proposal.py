"""Build an operator-reviewed Phase-2 proposal from Phase-4 residual CJK.

The proposal is suggestion-only.  It never mutates ``master_timeline.json``
or any Phase-2/3 approval artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence

from src.media_pipeline.frame_sampling.phase2_ocr_contract import (
    parse_localization_policy,
)
from src.media_pipeline.ocr_filtering.script_filter import contains_cjk
from src.media_pipeline.video_renderer.adaptive_output_qa import (
    build_local_residual_ocr_provider,
)
from src.media_pipeline.video_renderer.phase4_input_contract import (
    prepare_phase4_from_root,
)


SCHEMA_VERSION = "phase2_residual_remediation_proposal_v3"
_SIGNATURE_RE = re.compile(r"[0-9\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_BOUNDARY_SCAN_MARGIN_FRAMES = 30
_MAX_BOUNDARY_SCAN_SAMPLES = 120


class ResidualRemediationProposalError(RuntimeError):
    pass


def has_approved_translation_authority(track: Mapping[str, Any]) -> bool:
    """Accept reviewed translations and deterministic number/unit localization."""

    return str(track.get("translation_status") or "") in {
        "TRANSLATION_APPROVED",
        "TRANSLATION_DETERMINISTIC",
    }


def select_residual_authority(
    phase4_meta: Mapping[str, Any],
    *,
    output_qa: Mapping[str, Any] | None = None,
    render_meta: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Select fail-closed preflight or encoded-output residual evidence."""

    if (
        str(phase4_meta.get("status") or "") == "PHASE4_PREFLIGHT_BLOCKED"
        and str(phase4_meta.get("final_render_gate") or "")
        == "BLOCKED_VISUAL_RESIDUAL_CJK"
    ):
        return "phase4_preflight", dict(phase4_meta.get("residual_cjk") or {})
    qa = dict(output_qa or {})
    rendered = dict(render_meta or {})
    if (
        str(qa.get("status") or "") == "FAIL"
        and "residual_cjk" in list(qa.get("failed_checks") or [])
        and str(rendered.get("status") or "") == "VISUAL_PREVIEW_QA_FAILED"
        and rendered.get("visual_preview") is True
        and str(rendered.get("output_qa_status") or "") == "FAIL"
        and "residual_cjk" in list(
            rendered.get("output_qa_failed_checks") or []
        )
    ):
        return "encoded_visual_preview_output_qa", dict(
            qa.get("residual_cjk") or {}
        )
    raise ResidualRemediationProposalError(
        "Phase 4 has no fail-closed residual CJK authority"
    )


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResidualRemediationProposalError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise ResidualRemediationProposalError(f"{path.name} must be an object")
    return payload


def _load_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResidualRemediationProposalError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, list):
        raise ResidualRemediationProposalError(f"{path.name} must be a list")
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


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _signature(text: str) -> str:
    return "".join(_SIGNATURE_RE.findall(str(text or "")))


def _rect(raw: Mapping[str, Any]) -> tuple[float, float, float, float]:
    try:
        x = float(raw.get("x") or 0.0)
        y = float(raw.get("y") or 0.0)
        width = float(raw.get("width") or 0.0)
        height = float(raw.get("height") or 0.0)
    except (TypeError, ValueError) as exc:
        raise ResidualRemediationProposalError("Residual geometry is invalid") from exc
    if width <= 0 or height <= 0 or min(x, y) < 0 or x + width > 1.001 or y + height > 1.001:
        raise ResidualRemediationProposalError("Residual geometry is out of bounds")
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


def cluster_residual_detections(
    detections: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Group the same residual sampled at multiple nearby frames."""
    clusters: list[dict[str, Any]] = []
    ordered = sorted(detections, key=lambda row: int(row.get("frame_index") or 0))
    for raw in ordered:
        text = str(raw.get("text") or "").strip()
        signature = _signature(text)
        if not signature or not contains_cjk(signature):
            continue
        geometry = dict(raw.get("geometry") or {})
        rect = _rect(geometry)
        match: dict[str, Any] | None = None
        for cluster in clusters:
            if cluster["signature"] != signature:
                continue
            if _intersection_over_smaller(rect, cluster["anchor_rect"]) >= 0.60:
                match = cluster
                break
        row = {
            "frame_index": int(raw.get("frame_index") or 0),
            "text": text,
            "confidence": float(raw.get("confidence") or 0.0),
            "geometry": geometry,
        }
        if match is None:
            clusters.append(
                {
                    "signature": signature,
                    "anchor_rect": rect,
                    "detections": [row],
                }
            )
        else:
            match["detections"].append(row)
    for cluster in clusters:
        cluster["detections"].sort(key=lambda row: row["frame_index"])
    return clusters


def source_match_cluster(
    cluster: Mapping[str, Any],
    corrections: Mapping[str, str],
) -> dict[str, Any]:
    """Use an explicit suggestion-only OCR correction for source confirmation.

    Encoded-output OCR can be garbled even when the source crop is clear.  The
    correction changes only the signature used to re-OCR the source; the
    original residual detections remain immutable evidence and still require
    operator approval before materialization.
    """

    output = dict(cluster)
    detections = [
        dict(row)
        for row in list(cluster.get("detections") or [])
        if isinstance(row, Mapping)
    ]
    if not detections:
        return output
    representative = max(
        detections,
        key=lambda row: float(row.get("confidence") or 0.0),
    )
    observed = str(representative.get("text") or "").strip()
    corrected = str(corrections.get(observed) or "").strip()
    signature = _signature(corrected)
    if not corrected:
        return output
    if not signature or not contains_cjk(signature):
        raise ResidualRemediationProposalError(
            f"Residual source correction for {observed} is invalid"
        )
    output["signature"] = signature
    output["source_text_correction"] = {
        "encoded_ocr_text": observed,
        "source_ocr_text_suggested": corrected,
        "operator_approval_written": False,
    }
    return output


def match_source_box(
    residual: Mapping[str, Any], boxes: Sequence[Any]
) -> dict[str, Any] | None:
    """Require an exact number+CJK signature and spatial source agreement."""
    expected = str(residual.get("signature") or "")
    anchor = tuple(residual.get("anchor_rect") or ())
    if len(anchor) != 4:
        return None
    candidates: list[tuple[float, dict[str, Any]]] = []
    for box in boxes:
        text = str(getattr(box, "text", "") or "").strip()
        if _signature(text) != expected or not contains_cjk(text):
            continue
        geometry = {
            "x": float(getattr(box, "x", 0.0) or 0.0),
            "y": float(getattr(box, "y", 0.0) or 0.0),
            "width": float(getattr(box, "width", 0.0) or 0.0),
            "height": float(getattr(box, "height", 0.0) or 0.0),
        }
        try:
            overlap = _intersection_over_smaller(anchor, _rect(geometry))
        except ResidualRemediationProposalError:
            continue
        confidence = float(getattr(box, "confidence", 0.0) or 0.0)
        if overlap < 0.50 or confidence < 0.25:
            continue
        candidates.append(
            (
                overlap + confidence,
                {
                    "text": text,
                    "confidence": confidence,
                    "geometry": geometry,
                    "overlap": overlap,
                },
            )
        )
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def match_source_cluster_crop(
    frame: Any,
    residual: Mapping[str, Any],
    *,
    provider: Any,
    frame_time_ms: int,
) -> dict[str, Any] | None:
    """OCR a bounded residual crop and project exact boxes to full-frame space."""

    import cv2
    import numpy as np

    image = np.asarray(frame)
    if image.ndim != 3 or image.shape[2] != 3:
        return None
    height, width = image.shape[:2]
    anchor = tuple(residual.get("anchor_rect") or ())
    if len(anchor) != 4:
        return None
    pad_x = max(0.015, (float(anchor[2]) - float(anchor[0])) * 0.18)
    pad_y = max(0.015, (float(anchor[3]) - float(anchor[1])) * 0.35)
    x0 = max(0, int(math.floor((float(anchor[0]) - pad_x) * width)))
    y0 = max(0, int(math.floor((float(anchor[1]) - pad_y) * height)))
    x1 = min(width, int(math.ceil((float(anchor[2]) + pad_x) * width)))
    y1 = min(height, int(math.ceil((float(anchor[3]) + pad_y) * height)))
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    with tempfile.TemporaryDirectory(prefix="phase2_residual_crop_") as temp_dir:
        temp_path = Path(temp_dir) / "source_crop.jpg"
        if not cv2.imwrite(str(temp_path), crop):
            raise ResidualRemediationProposalError(
                "Cannot stage residual source crop"
            )
        result = provider.detect_frame(temp_path, frame_time_ms=frame_time_ms)
    crop_width = max(1, x1 - x0)
    crop_height = max(1, y1 - y0)
    projected = []
    for box in list(getattr(result, "boxes", []) or []):
        projected.append(
            SimpleNamespace(
                text=str(getattr(box, "text", "") or ""),
                confidence=float(getattr(box, "confidence", 0.0) or 0.0),
                x=(x0 + float(getattr(box, "x", 0.0) or 0.0) * crop_width)
                / width,
                y=(y0 + float(getattr(box, "y", 0.0) or 0.0) * crop_height)
                / height,
                width=float(getattr(box, "width", 0.0) or 0.0)
                * crop_width
                / width,
                height=float(getattr(box, "height", 0.0) or 0.0)
                * crop_height
                / height,
            )
        )
    return match_source_box(residual, projected)


def match_source_box_for_geometry_expansion(
    *,
    expected_text: str,
    residual: Mapping[str, Any],
    existing_geometry: Mapping[str, Any],
    boxes: Sequence[Any],
) -> dict[str, Any] | None:
    """Match a full approved source line that contains a rendered residual."""
    expected = _signature(expected_text)
    residual_signature = str(residual.get("signature") or "")
    if not expected or not contains_cjk(expected):
        return None
    existing_rect = _rect(existing_geometry)
    anchor = tuple(residual.get("anchor_rect") or ())
    if len(anchor) != 4:
        return None
    candidates: list[tuple[float, dict[str, Any]]] = []
    for box in boxes:
        text = str(getattr(box, "text", "") or "").strip()
        signature = _signature(text)
        confidence = float(getattr(box, "confidence", 0.0) or 0.0)
        similarity = SequenceMatcher(None, expected, signature).ratio()
        if not contains_cjk(signature) or confidence < 0.50 or similarity < 0.80:
            continue
        if residual_signature and not set(residual_signature).intersection(signature):
            continue
        geometry = {
            "x": float(getattr(box, "x", 0.0) or 0.0),
            "y": float(getattr(box, "y", 0.0) or 0.0),
            "width": float(getattr(box, "width", 0.0) or 0.0),
            "height": float(getattr(box, "height", 0.0) or 0.0),
        }
        try:
            source_rect = _rect(geometry)
        except ResidualRemediationProposalError:
            continue
        existing_overlap = _intersection_over_smaller(source_rect, existing_rect)
        residual_overlap = _intersection_over_smaller(source_rect, anchor)
        source_area = (source_rect[2] - source_rect[0]) * (
            source_rect[3] - source_rect[1]
        )
        existing_area = (existing_rect[2] - existing_rect[0]) * (
            existing_rect[3] - existing_rect[1]
        )
        if (
            existing_overlap < 0.50
            or residual_overlap < 0.50
            or source_area <= existing_area * 1.05
        ):
            continue
        candidates.append(
            (
                similarity + existing_overlap + residual_overlap + confidence,
                {
                    "text": text,
                    "signature": signature,
                    "confidence": confidence,
                    "similarity": similarity,
                    "geometry": geometry,
                    "existing_overlap": existing_overlap,
                    "residual_overlap": residual_overlap,
                },
            )
        )
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _active_expansion_target(
    cluster: Mapping[str, Any],
    render_tracks: Sequence[Mapping[str, Any]],
    content_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    representative = max(
        list(cluster.get("detections") or []),
        key=lambda row: float(dict(row).get("confidence") or 0.0),
    )
    frame_index = int(dict(representative).get("frame_index") or 0)
    residual_rect = tuple(cluster.get("anchor_rect") or ())
    residual_signature = str(cluster.get("signature") or "")
    if len(residual_rect) != 4:
        return None
    candidates: list[tuple[float, dict[str, Any]]] = []
    for raw in render_tracks:
        track = dict(raw)
        if not (
            int(track.get("start_frame") or 0)
            <= frame_index
            <= int(track.get("end_frame") or -1)
        ):
            continue
        content = dict(content_by_id.get(str(track.get("content_id") or "")) or {})
        expected_signature = _signature(
            str(content.get("ocr_text_approved") or "")
        )
        if (
            not residual_signature
            or not expected_signature
            or (
                residual_signature not in expected_signature
                and expected_signature not in residual_signature
                and SequenceMatcher(
                    None, residual_signature, expected_signature
                ).ratio()
                < 0.50
            )
        ):
            continue
        cover = dict(dict(track.get("render_policy") or {}).get("cover") or {})
        roi = dict(cover.get("roi") or {})
        if not roi:
            continue
        cover_rect = _rect(roi)
        overlap = _intersection_over_smaller(residual_rect, cover_rect)
        vertical_overlap = max(
            0.0,
            min(residual_rect[3], cover_rect[3])
            - max(residual_rect[1], cover_rect[1]),
        ) / max(1e-9, residual_rect[3] - residual_rect[1])
        horizontal_gap = max(
            0.0,
            max(cover_rect[0], residual_rect[0])
            - min(cover_rect[2], residual_rect[2]),
        )
        if overlap < 0.10 and (vertical_overlap < 0.50 or horizontal_gap > 0.08):
            continue
        candidates.append((overlap + vertical_overlap - horizontal_gap, track))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _same_content_translation(
    text_ids: Sequence[str],
    render_tracks: Sequence[Mapping[str, Any]],
) -> tuple[str, str] | None:
    """Reuse one exact approved translation across duplicate geometries."""
    requested = {str(value) for value in text_ids if str(value)}
    candidates = {
        (
            str(row.get("content_id") or ""),
            str(row.get("text_vi") or "").strip(),
        )
        for raw in render_tracks
        if isinstance(raw, Mapping)
        for row in (dict(raw),)
        if str(row.get("text_id") or "") in requested
        and has_approved_translation_authority(row)
        and str(row.get("content_id") or "")
        and str(row.get("text_vi") or "").strip()
    }
    if len(candidates) != 1:
        return None
    return next(iter(candidates))


def dominant_active_window(
    timeline: Sequence[Mapping[str, Any]], frame_index: int
) -> tuple[int, int, int, int]:
    windows = [
        (int(row.get("start_frame") or 0), int(row.get("end_frame") or 0))
        for row in timeline
        if int(row.get("start_frame") or 0)
        <= frame_index
        <= int(row.get("end_frame") or -1)
    ]
    if not windows:
        raise ResidualRemediationProposalError(
            f"No active Phase-1 window at frame {frame_index}"
        )
    counts = Counter(windows)
    (start_frame, end_frame), support = counts.most_common(1)[0]
    if support / len(windows) < 0.50:
        raise ResidualRemediationProposalError(
            f"Ambiguous temporal window at frame {frame_index}"
        )
    return start_frame, end_frame, support, len(windows)


def _timecode(frame_index: int, fps: float) -> str:
    milliseconds = int(round(frame_index * 1000.0 / max(fps, 0.001)))
    seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f"{hours:02d}:{minute:02d}:{sec:02d}.{ms:03d}"


def _median(values: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _max_gap(frames: Sequence[int]) -> int:
    return max((right - left - 1 for left, right in zip(frames, frames[1:])), default=0)


def infer_contiguous_hit_window(
    hit_frames: Sequence[int],
    *,
    anchor_frame: int,
    max_internal_gap: int = 1,
) -> tuple[int, int, list[int]]:
    """Infer an untracked OCR span only from the run containing the residual."""

    ordered = sorted({int(value) for value in hit_frames})
    if not ordered or int(anchor_frame) not in ordered:
        raise ResidualRemediationProposalError(
            "Residual anchor is not confirmed in source OCR"
        )
    runs: list[list[int]] = [[ordered[0]]]
    for frame_index in ordered[1:]:
        if frame_index - runs[-1][-1] - 1 <= int(max_internal_gap):
            runs[-1].append(frame_index)
        else:
            runs.append([frame_index])
    selected = next(
        (run for run in runs if run[0] <= int(anchor_frame) <= run[-1]),
        None,
    )
    if not selected:
        raise ResidualRemediationProposalError(
            "Residual source OCR window is ambiguous"
        )
    return selected[0], selected[-1], selected


def build_boundary_scan_frames(
    *,
    start_frame: int,
    end_frame: int,
    residual_frames: Sequence[int],
    frame_count: int,
    required_frames: Sequence[int] = (),
    margin_frames: int = _BOUNDARY_SCAN_MARGIN_FRAMES,
    max_samples: int = _MAX_BOUNDARY_SCAN_SAMPLES,
) -> tuple[list[int], int, int]:
    """Build a bounded coarse scan covering stale Phase-1 and residual evidence.

    Phase-4 samples can prove that a caption survives beyond the Phase-1
    temporal window.  The scan therefore covers the union of both authorities,
    plus a small margin for negative boundary evidence.  Required frames are
    retained even when the union is subsampled.
    """

    if frame_count < 1:
        raise ResidualRemediationProposalError(
            "Cannot build a boundary scan without frame authority"
        )
    observed = [
        max(0, min(frame_count - 1, int(value))) for value in residual_frames
    ]
    scan_start = max(
        0,
        min([int(start_frame)] + observed) - max(0, int(margin_frames)),
    )
    scan_end = min(
        frame_count - 1,
        max([int(end_frame)] + observed) + max(0, int(margin_frames)),
    )
    full_scan = list(range(scan_start, scan_end + 1))
    if max_samples < 2:
        raise ResidualRemediationProposalError(
            "Boundary scan max_samples must be at least 2"
        )
    if len(full_scan) <= max_samples:
        return full_scan, scan_start, scan_end
    step = max(1, math.ceil(len(full_scan) / max_samples))
    required = {
        max(scan_start, min(scan_end, int(value)))
        for value in (
            list(required_frames)
            + observed
            + [scan_start, int(start_frame), int(end_frame), scan_end]
        )
    }
    sampled = sorted(set(full_scan[::step]) | required)
    return sampled, scan_start, scan_end


def refine_hit_boundaries(
    *,
    start_frame: int,
    end_frame: int,
    frame_count: int,
    is_hit: Callable[[int], bool],
) -> tuple[int, int, bool, bool, list[int]]:
    """Refine coarse OCR boundaries and require immediate outside negatives."""

    refined_start = int(start_frame)
    refined_end = int(end_frame)
    probed: list[int] = []

    cursor = refined_start - 1
    while cursor >= 0:
        probed.append(cursor)
        if not is_hit(cursor):
            break
        refined_start = cursor
        cursor -= 1
    before_confirmed = refined_start == 0 or (
        cursor == refined_start - 1 and cursor >= 0
    )

    cursor = refined_end + 1
    while cursor < frame_count:
        probed.append(cursor)
        if not is_hit(cursor):
            break
        refined_end = cursor
        cursor += 1
    after_confirmed = refined_end == frame_count - 1 or (
        cursor == refined_end + 1 and cursor < frame_count
    )
    return (
        refined_start,
        refined_end,
        before_confirmed,
        after_confirmed,
        probed,
    )


def _proposal_markdown(proposal: Mapping[str, Any]) -> str:
    lines = [
        "# Phase 2 Residual OCR Remediation Proposal",
        "",
        f"- Status: `{proposal.get('status')}`",
        f"- Proposal SHA-256: `{proposal.get('proposal_sha256')}`",
        f"- Residual clusters: {dict(proposal.get('counts') or {}).get('residual_clusters', 0)}",
        "- Proposed occurrences: "
        f"{dict(proposal.get('counts') or {}).get('proposed_occurrences', 0)}",
        "- Proposed geometry overrides: "
        f"{dict(proposal.get('counts') or {}).get('proposed_geometry_overrides', 0)}",
        "",
        "Proposal này chưa thay đổi authority OCR và cần operator duyệt rõ ràng.",
        "",
        "| ID | Action | Target | OCR nguồn đề xuất | Render đề xuất | Frame | Geometry | Evidence |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in list(proposal.get("proposals") or []):
        change = dict(
            row.get("proposed_occurrence")
            or row.get("proposed_geometry_override")
            or {}
        )
        box = list(change.get("box_coords") or [])
        geometry = ", ".join(f"{float(value):.1f}" for value in box)
        evidence = dict(row.get("evidence") or {})
        crop = str(dict(evidence.get("crop_ref") or {}).get("path") or "")
        lines.append(
            f"| {row.get('remediation_id')} | {row.get('proposed_action')} | "
            f"{change.get('target_text_id') or change.get('text_id')} | "
            f"{row.get('ocr_text_suggested')} | "
            f"{row.get('render_text_suggested')} | "
            f"{change.get('start_frame')}–{change.get('end_frame')} | "
            f"{geometry} | `{crop}` |"
        )
    lines.append("")
    return "\n".join(lines)


def build_proposal(
    root_dir: str | Path,
    *,
    generated_at: str | None = None,
    provider: Any | None = None,
    frame_loader: Callable[[Path, Sequence[int]], Mapping[int, Any]] | None = None,
) -> dict[str, Any]:
    """Build a hash-bound suggestion artifact without applying it."""
    import cv2
    import numpy as np

    root = Path(root_dir).resolve()
    phase4_meta_path = root / "phase4_preflight_meta.json"
    if not phase4_meta_path.is_file():
        raise ResidualRemediationProposalError(
            "Missing required artifact: phase4_preflight_meta.json"
        )
    phase4_meta = _load_object(phase4_meta_path)
    output_qa_path = (
        root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
    )
    render_meta_path = root / "phase4_adaptive_render_meta.json"
    output_qa = _load_object(output_qa_path) if output_qa_path.is_file() else None
    render_meta = _load_object(render_meta_path) if render_meta_path.is_file() else None
    residual_source, residual = select_residual_authority(
        phase4_meta,
        output_qa=output_qa,
        render_meta=render_meta,
    )
    paths = {
        "master": root / "master_timeline.json",
        "phase2_timeline": root / "phase2_ocr_timeline.json",
        "phase2_handoff": root / "phase2_handoff.json",
        "phase3_timeline": root / "phase3_translation_timeline.json",
        "phase3_handoff": root / "phase3_render_handoff.json",
        "phase4_meta": phase4_meta_path,
        "phase4_input": root
        / (
            "phase4_render_input.json"
            if residual_source == "encoded_visual_preview_output_qa"
            else "phase4_render_input_preview.json"
        ),
    }
    for path in paths.values():
        if not path.is_file():
            raise ResidualRemediationProposalError(
                f"Missing required artifact: {path.name}"
            )
    phase2_timeline = _load_object(paths["phase2_timeline"])
    phase2_handoff = _load_object(paths["phase2_handoff"])
    phase3_timeline = _load_object(paths["phase3_timeline"])
    phase3_handoff = _load_object(paths["phase3_handoff"])
    phase4_input = _load_object(paths["phase4_input"])
    timeline = _load_list(paths["master"])
    suggestion_path = root / "phase2_residual_translation_suggestions.json"
    translation_suggestions: dict[str, str] = {}
    source_text_corrections: dict[str, str] = {}
    if suggestion_path.is_file():
        suggestion_payload = _load_object(suggestion_path)
        if (
            str(suggestion_payload.get("status") or "") != "SUGGESTION_ONLY"
            or bool(suggestion_payload.get("operator_approval_written"))
        ):
            raise ResidualRemediationProposalError(
                "Residual translation suggestions must remain non-authoritative"
            )
        for raw in list(suggestion_payload.get("suggestions") or []):
            if not isinstance(raw, Mapping):
                continue
            source_text = str(raw.get("ocr_text") or "").strip()
            corrected_text = str(raw.get("ocr_text_corrected") or "").strip()
            vi_text = str(raw.get("vi_text_suggested") or "").strip()
            if source_text and vi_text:
                translation_suggestions[source_text] = vi_text
            if source_text and corrected_text:
                source_text_corrections[source_text] = corrected_text
                if vi_text:
                    translation_suggestions[corrected_text] = vi_text
    if not bool(residual.get("complete")) or residual.get("error"):
        raise ResidualRemediationProposalError("Residual OCR evidence is incomplete")
    clusters = cluster_residual_detections(list(residual.get("detections") or []))
    if not clusters:
        raise ResidualRemediationProposalError("No reviewable residual CJK cluster")

    master_hash = _sha256_file(paths["master"])
    phase2_hash = _sha256_file(paths["phase2_handoff"])
    phase3_hash = _sha256_file(paths["phase3_handoff"])
    if str(dict(phase2_handoff.get("phase1_ref") or {}).get("sha256") or "") != master_hash:
        raise ResidualRemediationProposalError("Phase 2 master authority is stale")
    if (
        str(
            dict(phase3_timeline.get("phase2_handoff_ref") or {}).get("sha256")
            or ""
        )
        != phase2_hash
    ):
        raise ResidualRemediationProposalError("Phase 3 timeline authority is stale")
    if str(dict(phase3_handoff.get("phase2_handoff_ref") or {}).get("sha256") or "") != phase2_hash:
        raise ResidualRemediationProposalError("Phase 3 handoff authority is stale")
    if str(phase4_meta.get("phase3_render_handoff_sha256") or "") != phase3_hash:
        raise ResidualRemediationProposalError("Phase 4 evidence is stale")

    residual_authority_refs: dict[str, Any] = {}
    if residual_source == "encoded_visual_preview_output_qa":
        if output_qa is None or render_meta is None:
            raise ResidualRemediationProposalError(
                "Encoded residual authority artifacts are missing"
            )
        preview_path = root / "phase4_adaptive_visual_preview.mp4"
        if (
            str(render_meta.get("phase4_input_sha256") or "")
            != _sha256_file(paths["phase4_input"])
            or not preview_path.is_file()
            or str(render_meta.get("output_video_sha256") or "")
            != _sha256_file(preview_path)
        ):
            raise ResidualRemediationProposalError(
                "Encoded visual preview residual authority is stale"
            )
        residual_authority_refs = {
            "phase4_render_meta": {
                "path": render_meta_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(render_meta_path),
            },
            "phase4_output_qa": {
                "path": output_qa_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(output_qa_path),
            },
            "phase4_visual_preview": {
                "path": preview_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(preview_path),
            },
        }

    _, _, source = prepare_phase4_from_root(root)
    source_ref = dict(dict(phase4_input.get("refs") or {}).get("source_video_ref") or {})
    if str(source_ref.get("sha256") or "") != _sha256_file(source):
        raise ResidualRemediationProposalError("Source video authority is stale")
    video = dict(phase4_input.get("video") or {})
    frame_width = int(video.get("frame_width") or 0)
    frame_height = int(video.get("frame_height") or 0)
    fps = float(video.get("fps") or 0.0)
    if frame_width < 2 or frame_height < 2 or fps <= 0:
        raise ResidualRemediationProposalError("Invalid video metadata")

    runtime_provider = provider or build_local_residual_ocr_provider()

    def default_frame_loader(video_path: Path, indices: Sequence[int]) -> Mapping[int, Any]:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise ResidualRemediationProposalError("Cannot open source video")
        targets = sorted(set(int(index) for index in indices))
        wanted = set(targets)
        loaded: dict[int, Any] = {}
        try:
            for frame_index in range((targets[-1] + 1) if targets else 0):
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise ResidualRemediationProposalError(
                        f"Cannot decode source frame {frame_index}"
                    )
                if frame_index in wanted:
                    loaded[frame_index] = frame
        finally:
            capture.release()
        return loaded

    load_frames = frame_loader or default_frame_loader
    proposals: list[dict[str, Any]] = []
    content_by_id = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(phase2_timeline.get("content_objects") or [])
        if isinstance(row, Mapping) and str(row.get("content_id") or "")
    }
    content_id_by_text_id = {
        str(row.get("text_id") or ""): str(row.get("content_id") or "")
        for row in list(phase2_timeline.get("track_enrichments") or [])
        if isinstance(row, Mapping) and str(row.get("text_id") or "")
    }
    master_by_id = {
        str(row.get("text_id") or ""): dict(row)
        for row in timeline
        if str(row.get("text_id") or "")
    }
    render_tracks = [
        dict(row)
        for row in list(phase4_input.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    evidence_root = root / "qa" / "phase2_residual_remediation"
    evidence_root.mkdir(parents=True, exist_ok=True)
    for cluster in clusters:
        representative = max(
            cluster["detections"], key=lambda row: float(row["confidence"])
        )
        source_cluster = source_match_cluster(cluster, source_text_corrections)
        expansion_target = _active_expansion_target(
            cluster, render_tracks, content_by_id
        )
        if expansion_target is not None:
            target_text_id = str(expansion_target.get("text_id") or "")
            content_id = str(expansion_target.get("content_id") or "")
            master_row = master_by_id.get(target_text_id)
            content_row = content_by_id.get(content_id)
            expected_text = str(
                dict(content_row or {}).get("ocr_text_approved") or ""
            ).strip()
            render_text = str(expansion_target.get("text_vi") or "").strip()
            if (
                master_row is None
                or content_row is None
                or not expected_text
                or not render_text
                or not has_approved_translation_authority(expansion_target)
            ):
                raise ResidualRemediationProposalError(
                    "Residual geometry expansion lacks approved content authority"
                )
            coords = list(master_row.get("box_coords") or [])
            if len(coords) != 4:
                raise ResidualRemediationProposalError(
                    "Residual geometry expansion target is invalid"
                )
            existing_geometry = {
                "x": float(coords[0]) / frame_width,
                "y": float(coords[1]) / frame_height,
                "width": (float(coords[2]) - float(coords[0])) / frame_width,
                "height": (float(coords[3]) - float(coords[1])) / frame_height,
            }
            start_frame = int(master_row.get("start_frame") or 0)
            end_frame = int(master_row.get("end_frame") or start_frame)
            scan_frames = list(range(start_frame, end_frame + 1))
            if len(scan_frames) > 120:
                step = max(1, math.ceil(len(scan_frames) / 120))
                scan_frames = scan_frames[::step]
                if scan_frames[-1] != end_frame:
                    scan_frames.append(end_frame)
            frames = load_frames(source, scan_frames)
            matches: list[dict[str, Any]] = []
            for frame_index in scan_frames:
                frame = frames.get(frame_index)
                if frame is None:
                    continue
                with tempfile.TemporaryDirectory(
                    prefix="phase2_residual_expand_"
                ) as temp_dir:
                    temp_path = Path(temp_dir) / "source.jpg"
                    if not cv2.imwrite(str(temp_path), frame):
                        raise ResidualRemediationProposalError(
                            "Cannot stage OCR frame"
                        )
                    result = runtime_provider.detect_frame(
                        temp_path,
                        frame_time_ms=int(round(frame_index * 1000.0 / fps)),
                    )
                matched = match_source_box_for_geometry_expansion(
                    expected_text=expected_text,
                    residual=cluster,
                    existing_geometry=existing_geometry,
                    boxes=list(getattr(result, "boxes", []) or []),
                )
                if matched is not None:
                    matched["frame_index"] = frame_index
                    matches.append(matched)
            hit_frames = [int(row["frame_index"]) for row in matches]
            hit_density = len(hit_frames) / max(1, len(scan_frames))
            if (
                not matches
                or hit_density < 0.80
                or hit_frames[0] != start_frame
                or hit_frames[-1] != end_frame
            ):
                raise ResidualRemediationProposalError(
                    f"Geometry expansion for {target_text_id} lacks stable source evidence"
                )
            source_geometry = {
                key: _median(
                    [float(dict(row["geometry"])[key]) for row in matches]
                )
                for key in ("x", "y", "width", "height")
            }
            existing_rect = _rect(existing_geometry)
            source_rect = _rect(source_geometry)
            expanded_rect = (
                min(existing_rect[0], source_rect[0]),
                min(existing_rect[1], source_rect[1]),
                max(existing_rect[2], source_rect[2]),
                max(existing_rect[3], source_rect[3]),
            )
            box_coords = [
                expanded_rect[0] * frame_width,
                expanded_rect[1] * frame_height,
                expanded_rect[2] * frame_width,
                expanded_rect[3] * frame_height,
            ]
            identity = hashlib.sha256(
                json.dumps(
                    {
                        "action": "EXPAND_EXISTING_PHASE2_GEOMETRY",
                        "target_text_id": target_text_id,
                        "box_coords": box_coords,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:12]
            remediation_id = f"p2r_{identity}"
            evidence_dir = evidence_root / remediation_id
            evidence_dir.mkdir(parents=True, exist_ok=True)
            representative_index = int(representative["frame_index"])
            representative_frame = frames[representative_index]
            source_path = evidence_dir / (
                f"source_frame_{representative_index:06d}.jpg"
            )
            if not cv2.imwrite(str(source_path), representative_frame):
                raise ResidualRemediationProposalError(
                    "Cannot write source evidence"
                )
            x0 = max(0, int(math.floor(expanded_rect[0] * frame_width)) - 12)
            y0 = max(0, int(math.floor(expanded_rect[1] * frame_height)) - 12)
            x1 = min(frame_width, int(math.ceil(expanded_rect[2] * frame_width)) + 12)
            y1 = min(frame_height, int(math.ceil(expanded_rect[3] * frame_height)) + 12)
            crop = np.asarray(representative_frame)[y0:y1, x0:x1]
            crop_path = evidence_dir / "source_crop.jpg"
            if crop.size == 0 or not cv2.imwrite(str(crop_path), crop):
                raise ResidualRemediationProposalError("Cannot write crop evidence")
            observed_texts = Counter(str(row["text"]) for row in matches)
            accepted_signatures = sorted(
                {_signature(expected_text)}
                | {str(row["signature"]) for row in matches}
            )
            proposals.append(
                {
                    "remediation_id": remediation_id,
                    "proposal_status": "OPERATOR_REVIEW_REQUIRED",
                    "proposed_action": "EXPAND_EXISTING_PHASE2_GEOMETRY",
                    "target_content_id": content_id,
                    "ocr_text_suggested": expected_text,
                    "render_text_suggested": render_text,
                    "accepted_candidate_signatures": accepted_signatures,
                    "localization": {
                        "mode": "translation_carry_forward_exact",
                        "content_id": content_id,
                    },
                    "proposed_geometry_override": {
                        "target_text_id": target_text_id,
                        "start_frame": start_frame,
                        "end_frame": end_frame,
                        "start_time": _timecode(start_frame, fps),
                        "end_time": _timecode(end_frame + 1, fps),
                        "original_box_coords": [
                            round(float(value), 4) for value in coords
                        ],
                        "box_coords": [round(value, 4) for value in box_coords],
                        "best_keyframe_path": source_path.relative_to(root).as_posix(),
                        "crop_path": crop_path.relative_to(root).as_posix(),
                        "best_frame_index": representative_index,
                        "hit_frames": hit_frames,
                        "boundary_evidence": {
                            "status": "sampled_window_confirmed",
                            "method": "phase4_residual_geometry_expansion_ocr",
                            "observed_first_frame": hit_frames[0],
                            "observed_last_frame": hit_frames[-1],
                            "sampled_frames": len(scan_frames),
                            "hit_count": len(hit_frames),
                            "hit_density": round(hit_density, 6),
                            "max_internal_gap": _max_gap(hit_frames),
                        },
                    },
                    "evidence": {
                        "phase4_detections": cluster["detections"],
                        "source_ocr": {
                            "expected_approved_text": expected_text,
                            "observed_text_counts": dict(observed_texts),
                            "observations": len(matches),
                            "median_confidence": round(
                                _median(
                                    [float(row["confidence"]) for row in matches]
                                ),
                                6,
                            ),
                            "median_geometry": source_geometry,
                        },
                        "source_frame_ref": {
                            "path": source_path.relative_to(root).as_posix(),
                            "sha256": _sha256_file(source_path),
                        },
                        "crop_ref": {
                            "path": crop_path.relative_to(root).as_posix(),
                            "sha256": _sha256_file(crop_path),
                        },
                    },
                }
            )
            continue
        representative_index = int(representative["frame_index"])
        frame_count = int(video.get("frame_count") or 0)
        if frame_count < 1:
            raise ResidualRemediationProposalError(
                "Cannot infer a residual without frame authority"
            )
        inferred_untracked_window = False
        inferred_nested_window = False
        try:
            start_frame, end_frame, support, active = dominant_active_window(
                timeline, representative_index
            )
        except ResidualRemediationProposalError as exc:
            if not str(exc).startswith("No active Phase-1 window"):
                raise
            start_frame = max(0, representative_index - 30)
            end_frame = min(frame_count - 1, representative_index + 120)
            support = 0
            active = 0
            inferred_untracked_window = True
        residual_frames = [
            int(row.get("frame_index") or 0)
            for row in list(cluster.get("detections") or [])
            if isinstance(row, Mapping)
        ]
        scan_frames, scan_start, scan_end = build_boundary_scan_frames(
            start_frame=start_frame,
            end_frame=end_frame,
            residual_frames=residual_frames,
            frame_count=frame_count,
            required_frames=[representative_index],
        )
        frames: dict[int, Any] = {}
        match_cache: dict[int, dict[str, Any] | None] = {}

        def scan_source_frames(frame_indices: Sequence[int]) -> None:
            requested = sorted(
                {
                    int(frame_index)
                    for frame_index in frame_indices
                    if 0 <= int(frame_index) < frame_count
                    and int(frame_index) not in match_cache
                }
            )
            if not requested:
                return
            loaded = load_frames(source, requested)
            frames.update(loaded)
            for frame_index in requested:
                frame = frames.get(frame_index)
                if frame is None:
                    match_cache[frame_index] = None
                    continue
                matched = match_source_cluster_crop(
                    frame,
                    source_cluster,
                    provider=runtime_provider,
                    frame_time_ms=int(round(frame_index * 1000.0 / fps)),
                )
                if matched is not None:
                    matched["frame_index"] = frame_index
                match_cache[frame_index] = matched

        scan_source_frames(scan_frames)

        def source_hit(frame_index: int) -> bool:
            scan_source_frames([frame_index])
            return match_cache.get(frame_index) is not None

        matches = [
            dict(match_cache[frame_index])
            for frame_index in sorted(match_cache)
            if match_cache[frame_index] is not None
        ]
        hit_frames = [int(row["frame_index"]) for row in matches]
        boundary_differs = bool(hit_frames) and (
            hit_frames[0] != start_frame or hit_frames[-1] != end_frame
        )
        if inferred_untracked_window or boundary_differs:
            max_sample_gap = max(
                (
                    right - left
                    for left, right in zip(scan_frames, scan_frames[1:])
                ),
                default=1,
            )
            try:
                inferred_start, inferred_end, inferred_hits = (
                    infer_contiguous_hit_window(
                        hit_frames,
                        anchor_frame=representative_index,
                        max_internal_gap=max(1, max_sample_gap - 1),
                    )
                )
            except ResidualRemediationProposalError as exc:
                raise ResidualRemediationProposalError(
                    f"Residual {cluster['signature']} source confirmation failed: {exc}"
                ) from exc
            (
                inferred_start,
                inferred_end,
                before_confirmed,
                after_confirmed,
                _boundary_probes,
            ) = refine_hit_boundaries(
                start_frame=inferred_start,
                end_frame=inferred_end,
                frame_count=frame_count,
                is_hit=source_hit,
            )
            inferred_hits = [
                frame_index
                for frame_index in sorted(match_cache)
                if inferred_start <= frame_index <= inferred_end
                and match_cache[frame_index] is not None
            ]
            sampled_in_window = sum(
                inferred_start <= frame_index <= inferred_end
                for frame_index in match_cache
            )
            hit_density = len(inferred_hits) / max(1, sampled_in_window)
            if hit_density < 0.80 or not before_confirmed or not after_confirmed:
                raise ResidualRemediationProposalError(
                    f"Residual {cluster['signature']} lacks stable inferred boundary evidence"
                )
            start_frame = inferred_start
            end_frame = inferred_end
            inferred_nested_window = not inferred_untracked_window
            matches = [
                dict(match_cache[frame_index])
                for frame_index in sorted(match_cache)
                if start_frame <= frame_index <= end_frame
                and match_cache[frame_index] is not None
            ]
            hit_frames = [int(row["frame_index"]) for row in matches]
            support = len(hit_frames)
        else:
            sampled_in_window = sum(
                start_frame <= frame_index <= end_frame
                for frame_index in scan_frames
            )
            hit_density = len(hit_frames) / max(1, sampled_in_window)
            if (
                not matches
                or hit_density < 0.80
                or hit_frames[0] != start_frame
                or hit_frames[-1] != end_frame
            ):
                raise ResidualRemediationProposalError(
                    f"Residual {cluster['signature']} lacks stable source boundary evidence"
                )
        texts = Counter(str(row["text"]) for row in matches)
        source_text, text_support = texts.most_common(1)[0]
        if text_support / len(matches) < 0.80:
            raise ResidualRemediationProposalError(
                f"Residual {cluster['signature']} has ambiguous source OCR"
            )
        geometry = {
            key: _median([float(dict(row["geometry"])[key]) for row in matches])
            for key in ("x", "y", "width", "height")
        }
        source_rect = _rect(geometry)
        duplicate_refs: list[str] = []
        same_content_refs: list[str] = []
        for row in timeline:
            row_start = int(row.get("start_frame") or 0)
            row_end = int(row.get("end_frame") or row_start)
            if row_start > end_frame or start_frame > row_end:
                continue
            coords = list(row.get("box_coords") or [])
            if len(coords) < 4:
                continue
            existing = (
                float(coords[0]) / frame_width,
                float(coords[1]) / frame_height,
                float(coords[2]) / frame_width,
                float(coords[3]) / frame_height,
            )
            if _intersection_over_smaller(source_rect, existing) >= 0.70:
                existing_text_id = str(row.get("text_id") or "")
                existing_content = content_by_id.get(
                    content_id_by_text_id.get(existing_text_id, ""), {}
                )
                if _signature(
                    str(dict(existing_content).get("ocr_text_approved") or "")
                ) == _signature(source_text):
                    same_content_refs.append(existing_text_id)
                else:
                    duplicate_refs.append(existing_text_id)
        if duplicate_refs:
            raise ResidualRemediationProposalError(
                "Residual matches existing Phase-1 geometry: " + ",".join(duplicate_refs)
            )

        identity = hashlib.sha256(
            json.dumps(
                {
                    "signature": cluster["signature"],
                    "geometry": geometry,
                    "window": [start_frame, end_frame],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:12]
        remediation_id = f"p2r_{identity}"
        evidence_dir = evidence_root / remediation_id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        representative_frame = frames[int(representative["frame_index"])]
        source_path = evidence_dir / f"source_frame_{int(representative['frame_index']):06d}.jpg"
        if not cv2.imwrite(str(source_path), representative_frame):
            raise ResidualRemediationProposalError("Cannot write source evidence")
        x0 = max(0, int(math.floor(geometry["x"] * frame_width)) - 12)
        y0 = max(0, int(math.floor(geometry["y"] * frame_height)) - 12)
        x1 = min(
            frame_width,
            int(math.ceil((geometry["x"] + geometry["width"]) * frame_width)) + 12,
        )
        y1 = min(
            frame_height,
            int(math.ceil((geometry["y"] + geometry["height"]) * frame_height)) + 12,
        )
        crop = np.asarray(representative_frame)[y0:y1, x0:x1]
        crop_path = evidence_dir / "source_crop.jpg"
        if crop.size == 0 or not cv2.imwrite(str(crop_path), crop):
            raise ResidualRemediationProposalError("Cannot write crop evidence")

        carry_forward = _same_content_translation(
            same_content_refs,
            render_tracks,
        )
        localization = parse_localization_policy(source_text)
        if carry_forward is not None:
            carry_content_id, render_text = carry_forward
            localization = {
                "mode": "translation_carry_forward_exact",
                "content_id": carry_content_id,
                "geometry_refs": sorted(set(same_content_refs)),
            }
        elif str(localization.get("mode") or "") == "deterministic":
            render_text = str(
                localization.get("render_text_suggested") or ""
            ).strip()
        else:
            render_text = str(translation_suggestions.get(source_text) or "").strip()
            if render_text:
                localization = {
                    **localization,
                    "mode": "translation_review_required",
                    "render_text_suggested": render_text,
                    "suggestion_source": suggestion_path.name,
                    "operator_approval_written": False,
                }
        if not render_text:
            raise ResidualRemediationProposalError(
                f"Residual {source_text} requires a translation suggestion"
            )
        box_coords = [
            geometry["x"] * frame_width,
            geometry["y"] * frame_height,
            (geometry["x"] + geometry["width"]) * frame_width,
            (geometry["y"] + geometry["height"]) * frame_height,
        ]
        proposals.append(
            {
                "remediation_id": remediation_id,
                "proposal_status": "OPERATOR_REVIEW_REQUIRED",
                "proposed_action": "ADD_PHASE2_OCCURRENCE",
                "ocr_text_suggested": source_text,
                "render_text_suggested": render_text,
                "localization": localization,
                "source_text_correction": source_cluster.get(
                    "source_text_correction"
                ),
                "existing_same_content_geometry_refs": same_content_refs,
                "proposed_occurrence": {
                    "text_id": remediation_id,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "start_time": _timecode(start_frame, fps),
                    "end_time": _timecode(end_frame + 1, fps),
                    "box_coords": [round(value, 4) for value in box_coords],
                    "best_keyframe_path": source_path.relative_to(root).as_posix(),
                    "crop_path": crop_path.relative_to(root).as_posix(),
                    "best_frame_index": int(representative["frame_index"]),
                    "hit_frames": hit_frames,
                    "boundary_evidence": {
                        "status": (
                            "inferred_untracked_window_confirmed"
                            if inferred_untracked_window
                            else "inferred_nested_window_confirmed"
                            if inferred_nested_window
                            else "sampled_window_confirmed"
                        ),
                        "method": "phase4_residual_source_ocr",
                        "observed_first_frame": hit_frames[0],
                        "observed_last_frame": hit_frames[-1],
                        "sampled_frames": len(scan_frames),
                        "hit_count": len(hit_frames),
                        "hit_density": round(hit_density, 6),
                        "max_internal_gap": _max_gap(hit_frames),
                        "temporal_window_support": support,
                        "temporal_window_active_tracks": active,
                    },
                },
                "evidence": {
                    "phase4_detections": cluster["detections"],
                    "source_ocr": {
                        "text": source_text,
                        "text_support": text_support,
                        "observations": len(matches),
                        "median_confidence": round(
                            _median([float(row["confidence"]) for row in matches]), 6
                        ),
                        "median_geometry": geometry,
                    },
                    "source_frame_ref": {
                        "path": source_path.relative_to(root).as_posix(),
                        "sha256": _sha256_file(source_path),
                    },
                    "crop_ref": {
                        "path": crop_path.relative_to(root).as_posix(),
                        "sha256": _sha256_file(crop_path),
                    },
                },
            }
        )

    proposal: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PROPOSAL_READY_FOR_OPERATOR_REVIEW",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "operator_approval_written": False,
        "residual_authority": residual_source,
        "authority_refs": {
            "master_timeline": {"path": paths["master"].name, "sha256": master_hash},
            "phase2_timeline": {
                "path": paths["phase2_timeline"].name,
                "sha256": _sha256_file(paths["phase2_timeline"]),
            },
            "phase2_handoff": {"path": paths["phase2_handoff"].name, "sha256": phase2_hash},
            "phase3_timeline": {
                "path": paths["phase3_timeline"].name,
                "sha256": _sha256_file(paths["phase3_timeline"]),
            },
            "phase3_handoff": {"path": paths["phase3_handoff"].name, "sha256": phase3_hash},
            "phase4_preflight_meta": {
                "path": paths["phase4_meta"].name,
                "sha256": _sha256_file(paths["phase4_meta"]),
            },
            "phase4_render_input": {
                "path": paths["phase4_input"].name,
                "sha256": _sha256_file(paths["phase4_input"]),
            },
            "source_video": {"path": source.name, "sha256": _sha256_file(source)},
            **residual_authority_refs,
            **(
                {
                    "residual_translation_suggestions": {
                        "path": suggestion_path.name,
                        "sha256": _sha256_file(suggestion_path),
                    }
                }
                if suggestion_path.is_file()
                else {}
            ),
        },
        "counts": {
            "residual_clusters": len(clusters),
            "proposed_occurrences": sum(
                str(row.get("proposed_action") or "") == "ADD_PHASE2_OCCURRENCE"
                for row in proposals
            ),
            "proposed_geometry_overrides": sum(
                str(row.get("proposed_action") or "")
                == "EXPAND_EXISTING_PHASE2_GEOMETRY"
                for row in proposals
            ),
        },
        "proposals": proposals,
        "non_goals": [
            "do_not_overwrite_master_timeline",
            "do_not_write_phase2_operator_approval",
            "do_not_reuse_previous_translation_approval_without_hash_match",
            "do_not_write_visual_approval",
        ],
    }
    proposal["proposal_sha256"] = _sha256_json(proposal)
    return proposal


def validate_proposal(root_dir: str | Path, proposal: Mapping[str, Any]) -> None:
    root = Path(root_dir).resolve()
    unsigned = dict(proposal)
    claimed = str(unsigned.pop("proposal_sha256", "") or "")
    if len(claimed) != 64 or claimed != _sha256_json(unsigned):
        raise ResidualRemediationProposalError("Proposal self-hash is invalid")
    if str(proposal.get("status") or "") != "PROPOSAL_READY_FOR_OPERATOR_REVIEW":
        raise ResidualRemediationProposalError("Proposal is not reviewable")
    if bool(proposal.get("operator_approval_written")):
        raise ResidualRemediationProposalError(
            "Proposal must not claim operator approval"
        )
    authority_refs = dict(proposal.get("authority_refs") or {})
    for name, ref in authority_refs.items():
        item = dict(ref) if isinstance(ref, Mapping) else {}
        if name == "source_video":
            continue
        path = root / str(item.get("path") or "")
        if not path.is_file() or _sha256_file(path) != str(item.get("sha256") or ""):
            raise ResidualRemediationProposalError("Proposal authority is stale")
    _, _, source = prepare_phase4_from_root(root)
    source_ref = dict(authority_refs.get("source_video") or {})
    if (
        source.name != str(source_ref.get("path") or "")
        or _sha256_file(source) != str(source_ref.get("sha256") or "")
    ):
        raise ResidualRemediationProposalError("Proposal source authority is stale")
    rows = list(proposal.get("proposals") or [])
    if not rows:
        raise ResidualRemediationProposalError("Proposal has no occurrences")
    for raw in rows:
        row = dict(raw) if isinstance(raw, Mapping) else {}
        action = str(row.get("proposed_action") or "")
        if action not in {
            "ADD_PHASE2_OCCURRENCE",
            "EXPAND_EXISTING_PHASE2_GEOMETRY",
        } or not str(row.get("ocr_text_suggested") or "").strip() or not str(
            row.get("render_text_suggested") or ""
        ).strip():
            raise ResidualRemediationProposalError("Proposal row is invalid")
        if action == "ADD_PHASE2_OCCURRENCE":
            change = dict(row.get("proposed_occurrence") or {})
            if not str(change.get("text_id") or "").strip():
                raise ResidualRemediationProposalError(
                    "Proposal occurrence is invalid"
                )
        else:
            change = dict(row.get("proposed_geometry_override") or {})
            target_text_id = str(change.get("target_text_id") or "").strip()
            coords = list(change.get("box_coords") or [])
            original = list(change.get("original_box_coords") or [])
            if not target_text_id or len(coords) != 4 or len(original) != 4:
                raise ResidualRemediationProposalError(
                    "Proposal geometry override is invalid"
                )
        evidence = dict(row.get("evidence") or {})
        for key in ("source_frame_ref", "crop_ref"):
            ref = dict(evidence.get(key) or {})
            path = (root / str(ref.get("path") or "")).resolve()
            if (
                not path.is_relative_to(root)
                or not path.is_file()
                or _sha256_file(path) != str(ref.get("sha256") or "")
            ):
                raise ResidualRemediationProposalError(
                    f"Proposal evidence is stale: {key}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase2_residual_remediation_proposal"
    )
    parser.add_argument("artifact_root")
    parser.add_argument(
        "--output-stem",
        default="phase2_residual_remediation_proposal",
        help="Artifact stem for a new immutable proposal generation.",
    )
    args = parser.parse_args()
    root = Path(args.artifact_root).resolve()
    output_stem = str(args.output_stem or "").strip()
    if (
        not output_stem
        or Path(output_stem).name != output_stem
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", output_stem)
    ):
        print("[P2-RESIDUAL-PROPOSAL][FAIL] Invalid output stem", flush=True)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        proposal = build_proposal(root)
        validate_proposal(root, proposal)
        json_path = root / f"{output_stem}.json"
        markdown_path = root / f"{output_stem}.md"
        _write_json_atomic(json_path, proposal)
        _write_text_atomic(markdown_path, _proposal_markdown(proposal))
        print(
            json.dumps(
                {
                    "status": proposal["status"],
                    "proposed_occurrences": proposal["counts"]["proposed_occurrences"],
                    "proposed_geometry_overrides": proposal["counts"][
                        "proposed_geometry_overrides"
                    ],
                    "proposal_sha256": proposal["proposal_sha256"],
                    "json": str(json_path),
                    "markdown": str(markdown_path),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, ResidualRemediationProposalError) as exc:
        attempt: dict[str, Any] = {
            "schema_version": "phase2_residual_remediation_proposal_attempt_v1",
            "status": "PROPOSAL_BLOCKED_OPERATOR_TRIAGE_REQUIRED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reason": str(exc),
            "operator_approval_written": False,
        }
        meta_path = root / "phase4_preflight_meta.json"
        if meta_path.is_file():
            attempt["phase4_preflight_meta_ref"] = {
                "path": meta_path.name,
                "sha256": _sha256_file(meta_path),
            }
        attempt["attempt_sha256"] = _sha256_json(attempt)
        try:
            _write_json_atomic(
                root / f"{output_stem}_attempt.json",
                attempt,
            )
        except OSError:
            pass
        print(f"[P2-RESIDUAL-PROPOSAL][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
