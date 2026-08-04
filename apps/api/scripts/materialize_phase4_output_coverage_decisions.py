"""Rescan source boundaries and materialize approved V22.8.1 coverage tracks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from scripts.build_phase2_residual_remediation_proposal import (
    _signature,
    build_boundary_scan_frames,
    infer_contiguous_hit_window,
    match_source_cluster_crop,
    refine_hit_boundaries,
)
from scripts.run_phase4_adaptive import _source_path
from src.media_pipeline.video_renderer.adaptive_output_qa import (
    build_local_residual_ocr_provider,
)
from src.media_pipeline.video_renderer.overlays import gate_vi_for_burn
from src.media_pipeline.video_renderer.render_policy import (
    RenderPolicyError,
    normalize_render_text,
    plan_render_track,
)
from src.media_pipeline.video_renderer.visual_remediation import (
    ACTIVE_POINTER_NAME,
    VisualRemediationError,
    _sha256_json,
    apply_visual_remediation,
)


FALSE_POSITIVE_ACTION = "APPROVE_RESIDUAL_FALSE_POSITIVE"
OPERATOR_SOURCE_TEMPLATE_STRATEGY = "OPERATOR_CONFIRMED_SOURCE_TEMPLATE_V1"
SOURCE_BOUNDARY_VERIFIED = "SOURCE_BOUNDARY_VERIFIED"
SOURCE_TEMPLATE_OPERATOR_VERIFIED = "SOURCE_TEMPLATE_OPERATOR_VERIFIED"
VERIFIED_SOURCE_STATUSES = frozenset(
    {SOURCE_BOUNDARY_VERIFIED, SOURCE_TEMPLATE_OPERATOR_VERIFIED}
)
BOUNDARY_MARGIN_FRAMES = 45
BOUNDARY_MAX_SAMPLES = 180
CONTACT_SHEET_DIVIDER_PX = 8
TEMPLATE_BINDING_MAX_MAD = 5.0
TEMPLATE_BINDING_MIN_SSIM = 0.95
TEMPLATE_BINDING_MIN_NCC = 0.97
TEMPLATE_MIN_STDDEV = 8.0
TEMPLATE_MATCH_MIN_NCC = 0.72
TEMPLATE_MATCH_MIN_SSIM = 0.68
TEMPLATE_MATCH_MAX_MAD = 36.0
TEMPLATE_TRACK_MAX_RADIUS_FRAMES = 120


class OutputCoverageMaterializationError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OutputCoverageMaterializationError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise OutputCoverageMaterializationError(
            f"{path.name} must contain an object"
        )
    return payload


def _verify_self(payload: Mapping[str, Any], field: str) -> None:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    if len(claimed) != 64 or claimed != _sha256_json(unsigned):
        raise OutputCoverageMaterializationError(f"Invalid self-hash: {field}")


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _rect(raw: Mapping[str, Any]) -> tuple[float, float, float, float]:
    geometry = dict(raw.get("geometry") or raw)
    x = float(geometry.get("x") or 0.0)
    y = float(geometry.get("y") or 0.0)
    width = float(geometry.get("width") or 0.0)
    height = float(geometry.get("height") or 0.0)
    if (
        width <= 0
        or height <= 0
        or x < 0
        or y < 0
        or x + width > 1.001
        or y + height > 1.001
    ):
        raise OutputCoverageMaterializationError("Residual geometry is invalid")
    return x, y, x + width, y + height


def _overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    a = _rect(left)
    b = _rect(right)
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1])
    )
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return intersection / smaller if smaller > 0 else 0.0


def _anchor(cluster: Mapping[str, Any]) -> dict[str, Any]:
    detections = [
        dict(row)
        for row in list(cluster.get("detections") or [])
        if isinstance(row, Mapping)
    ]
    if not detections:
        raise OutputCoverageMaterializationError("Residual cluster is empty")
    return max(detections, key=lambda row: float(row.get("confidence") or 0.0))


def _load_selected_frames(path: Path, indices: Sequence[int]) -> dict[int, Any]:
    import cv2

    wanted = sorted({int(value) for value in indices if int(value) >= 0})
    if not wanted:
        return {}
    targets = set(wanted)
    frames: dict[int, Any] = {}
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise OutputCoverageMaterializationError("Cannot open source video")
    try:
        for frame_index in range(wanted[-1] + 1):
            ok, frame = capture.read()
            if not ok or frame is None:
                raise OutputCoverageMaterializationError(
                    f"Cannot decode source frame {frame_index}"
                )
            if frame_index in targets:
                frames[frame_index] = frame
    finally:
        capture.release()
    return frames


class _FrameCache:
    def __init__(self, path: Path, frames: Mapping[int, Any]):
        self.path = path
        self.frames = {int(key): value for key, value in frames.items()}

    def get(self, frame_index: int) -> Any:
        import cv2

        index = int(frame_index)
        if index in self.frames:
            return self.frames[index]
        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened():
            raise OutputCoverageMaterializationError("Cannot reopen source video")
        try:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
        finally:
            capture.release()
        if not ok or frame is None:
            raise OutputCoverageMaterializationError(
                f"Cannot decode source frame {index}"
            )
        self.frames[index] = frame
        return frame

    def iter_range(self, start_frame: int, end_frame: int):
        """Decode a bounded range sequentially without retaining every frame."""

        import cv2

        start = int(start_frame)
        end = int(end_frame)
        if start < 0 or end < start:
            raise OutputCoverageMaterializationError(
                "Sequential source-frame range is invalid"
            )
        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened():
            raise OutputCoverageMaterializationError("Cannot reopen source video")
        try:
            capture.set(cv2.CAP_PROP_POS_FRAMES, start)
            for frame_index in range(start, end + 1):
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise OutputCoverageMaterializationError(
                        f"Cannot decode source frame {frame_index}"
                    )
                yield frame_index, frame
        finally:
            capture.release()


def _is_verified_source_status(value: Any) -> bool:
    return str(value or "") in VERIFIED_SOURCE_STATUSES


def _pixel_rect(
    geometry: Mapping[str, Any], image: Any
) -> tuple[int, int, int, int]:
    import numpy as np

    array = np.asarray(image)
    if array.ndim < 2:
        raise OutputCoverageMaterializationError("Source frame is invalid")
    height, width = array.shape[:2]
    x0, y0, x1, y1 = _rect(geometry)
    px0 = max(0, int(math.floor(x0 * width)))
    py0 = max(0, int(math.floor(y0 * height)))
    px1 = min(width, int(math.ceil(x1 * width)))
    py1 = min(height, int(math.ceil(y1 * height)))
    if px1 - px0 < 2 or py1 - py0 < 2:
        raise OutputCoverageMaterializationError("Source template is too small")
    return px0, py0, px1, py1


def _normalized_geometry(
    rect: Sequence[int], image: Any
) -> dict[str, float]:
    import numpy as np

    array = np.asarray(image)
    height, width = array.shape[:2]
    if len(rect) != 4 or height < 1 or width < 1:
        raise OutputCoverageMaterializationError("Template geometry is invalid")
    x0, y0, x1, y1 = (int(value) for value in rect)
    geometry = {
        "x": x0 / width,
        "y": y0 / height,
        "width": (x1 - x0) / width,
        "height": (y1 - y0) / height,
    }
    _rect(geometry)
    return geometry


def _review_source_crop(frame: Any, geometry: Mapping[str, Any]) -> Any:
    """Rebuild the source half written by the residual-review contact sheet."""

    import numpy as np

    image = np.asarray(frame)
    if image.ndim != 3 or image.shape[2] != 3:
        raise OutputCoverageMaterializationError("Source frame is invalid")
    height, width = image.shape[:2]
    x0, y0, x1, y1 = _rect(geometry)
    pad_x = max(12, int(round((x1 - x0) * width * 0.25)))
    pad_y = max(12, int(round((y1 - y0) * height * 0.35)))
    px0 = max(0, int(math.floor(x0 * width)) - pad_x)
    py0 = max(0, int(math.floor(y0 * height)) - pad_y)
    px1 = min(width, int(math.ceil(x1 * width)) + pad_x)
    py1 = min(height, int(math.ceil(y1 * height)) + pad_y)
    crop = image[py0:py1, px0:px1].copy()
    if crop.size == 0:
        raise OutputCoverageMaterializationError("Source review crop is empty")
    return crop


def _global_ssim(left: Any, right: Any) -> float:
    import cv2
    import numpy as np

    a = np.asarray(left)
    b = np.asarray(right)
    if a.shape != b.shape or a.size == 0:
        raise OutputCoverageMaterializationError(
            "Template binding images are incompatible"
        )
    if a.ndim == 3:
        a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    mean_a = float(a.mean())
    mean_b = float(b.mean())
    centered_a = a - mean_a
    centered_b = b - mean_b
    variance_a = float(np.mean(centered_a * centered_a))
    variance_b = float(np.mean(centered_b * centered_b))
    covariance = float(np.mean(centered_a * centered_b))
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    denominator = (mean_a**2 + mean_b**2 + c1) * (
        variance_a + variance_b + c2
    )
    if denominator <= 0:
        return 1.0 if np.array_equal(a, b) else 0.0
    return float(
        ((2.0 * mean_a * mean_b + c1) * (2.0 * covariance + c2))
        / denominator
    )


def _image_similarity_metrics(left: Any, right: Any) -> dict[str, float]:
    import cv2
    import numpy as np

    a = np.asarray(left)
    b = np.asarray(right)
    if a.shape != b.shape or a.size == 0:
        raise OutputCoverageMaterializationError(
            "Template binding images are incompatible"
        )
    gray_a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY) if a.ndim == 3 else a
    gray_b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY) if b.ndim == 3 else b
    correlation = cv2.matchTemplate(
        gray_a, gray_b, cv2.TM_CCOEFF_NORMED
    )
    ncc = float(correlation[0, 0])
    if not math.isfinite(ncc):
        ncc = 0.0
    return {
        "mad": float(
            np.abs(a.astype(np.float32) - b.astype(np.float32)).mean()
        ),
        "ssim": _global_ssim(a, b),
        "ncc": ncc,
    }


def _contact_sheet_source_half(
    contact_sheet: Any, *, expected_shape: Sequence[int]
) -> Any:
    import numpy as np

    contact = np.asarray(contact_sheet)
    if contact.ndim != 3 or contact.shape[2] != 3 or len(expected_shape) < 2:
        raise OutputCoverageMaterializationError(
            "Operator contact sheet is invalid"
        )
    expected_height = int(expected_shape[0])
    expected_width = int(expected_shape[1])
    if (
        contact.shape[0] != expected_height
        or contact.shape[1]
        != expected_width * 2 + CONTACT_SHEET_DIVIDER_PX
    ):
        raise OutputCoverageMaterializationError(
            "Operator contact sheet layout changed"
        )
    divider = contact[
        :, expected_width : expected_width + CONTACT_SHEET_DIVIDER_PX
    ]
    divider_core = divider[:, 1:-1]
    if float(divider_core.mean()) < 250.0 or float(divider_core.std()) > 3.0:
        raise OutputCoverageMaterializationError(
            "Operator contact sheet divider is invalid"
        )
    return contact[:, :expected_width].copy()


def _bind_operator_source_template(
    *,
    case_root: Path,
    candidate: Mapping[str, Any],
    frame_cache: _FrameCache,
) -> dict[str, Any]:
    """Hash-bind an approved contact sheet to its source frame and template."""

    import cv2
    import numpy as np

    decision = dict(candidate.get("decision") or {})
    cluster = dict(candidate.get("cluster") or {})
    representative = dict(candidate.get("representative") or {})
    if (
        str(decision.get("geometry_strategy") or "")
        != OPERATOR_SOURCE_TEMPLATE_STRATEGY
        or not bool(decision.get("operator_confirmed_source_template_required"))
        or int(decision.get("source_boundary_failure_count") or 0) < 2
        or len(list(decision.get("source_boundary_failure_history") or [])) < 2
    ):
        raise OutputCoverageMaterializationError(
            "Operator source-template authority is incomplete"
        )
    anchor_frame = int(representative.get("frame_index") or 0)
    if anchor_frame != int(decision.get("representative_frame_index") or -1):
        raise OutputCoverageMaterializationError(
            "Source-template representative frame changed"
        )
    geometry = dict(representative.get("geometry") or {})
    _rect(geometry)
    decision_ref = dict(decision.get("evidence_ref") or {})
    cluster_ref = dict(
        dict(cluster.get("evidence") or {}).get(
            "source_render_contact_sheet"
        )
        or {}
    )
    if (
        not str(decision_ref.get("path") or "")
        or decision_ref != cluster_ref
        or len(str(decision_ref.get("sha256") or "")) != 64
    ):
        raise OutputCoverageMaterializationError(
            "Source-template contact-sheet authority changed"
        )
    evidence_path = (case_root / str(decision_ref["path"])).resolve()
    if (
        not evidence_path.is_relative_to(case_root)
        or not evidence_path.is_file()
        or _sha256_file(evidence_path) != str(decision_ref["sha256"])
    ):
        raise OutputCoverageMaterializationError(
            "Source-template contact-sheet hash changed"
        )
    frame = frame_cache.get(anchor_frame)
    reconstructed = _review_source_crop(frame, geometry)
    contact = cv2.imread(str(evidence_path), cv2.IMREAD_COLOR)
    if contact is None:
        raise OutputCoverageMaterializationError(
            "Cannot decode source-template contact sheet"
        )
    approved_source = _contact_sheet_source_half(
        contact, expected_shape=reconstructed.shape
    )
    metrics = _image_similarity_metrics(reconstructed, approved_source)
    if (
        metrics["mad"] > TEMPLATE_BINDING_MAX_MAD
        or metrics["ssim"] < TEMPLATE_BINDING_MIN_SSIM
        or metrics["ncc"] < TEMPLATE_BINDING_MIN_NCC
    ):
        raise OutputCoverageMaterializationError(
            "Source crop does not match operator-approved contact sheet"
        )
    anchor_rect = _pixel_rect(geometry, frame)
    x0, y0, x1, y1 = anchor_rect
    template_bgr = np.asarray(frame)[y0:y1, x0:x1].copy()
    template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
    template_stddev = float(template_gray.std())
    if (
        template_gray.shape[0] < 8
        or template_gray.shape[1] < 8
        or template_stddev < TEMPLATE_MIN_STDDEV
    ):
        raise OutputCoverageMaterializationError(
            "Source template has insufficient visual variance"
        )
    return {
        "anchor_frame": anchor_frame,
        "anchor_rect": anchor_rect,
        "template_gray": template_gray,
        "geometry": geometry,
        "template_stddev": template_stddev,
        "contact_sheet_ref": {
            "path": evidence_path.relative_to(case_root).as_posix(),
            "sha256": _sha256_file(evidence_path),
        },
        "binding_metrics": metrics,
    }


def _match_source_template_frame(
    frame: Any,
    *,
    template_gray: Any,
    predicted_rect: Sequence[int],
) -> dict[str, Any]:
    """Run one bounded template match and return both positive/negative evidence."""

    import cv2
    import numpy as np

    image = np.asarray(frame)
    template = np.asarray(template_gray)
    if image.ndim != 3 or template.ndim != 2 or len(predicted_rect) != 4:
        raise OutputCoverageMaterializationError("Template tracking input is invalid")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    template_height, template_width = template.shape[:2]
    x0, y0, x1, y1 = (int(value) for value in predicted_rect)
    if x1 - x0 != template_width or y1 - y0 != template_height:
        raise OutputCoverageMaterializationError(
            "Predicted template geometry changed"
        )
    radius_x = max(12, int(round(template_width * 0.30)))
    radius_y = max(12, int(round(template_height * 0.40)))
    sx0 = max(0, x0 - radius_x)
    sy0 = max(0, y0 - radius_y)
    sx1 = min(gray.shape[1], x1 + radius_x)
    sy1 = min(gray.shape[0], y1 + radius_y)
    search = gray[sy0:sy1, sx0:sx1]
    if search.shape[0] < template_height or search.shape[1] < template_width:
        raise OutputCoverageMaterializationError(
            "Template search window is too small"
        )
    response = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, ncc, _, location = cv2.minMaxLoc(response)
    match_x0 = sx0 + int(location[0])
    match_y0 = sy0 + int(location[1])
    match_rect = (
        match_x0,
        match_y0,
        match_x0 + template_width,
        match_y0 + template_height,
    )
    patch = gray[match_rect[1] : match_rect[3], match_rect[0] : match_rect[2]]
    mad = float(
        np.abs(template.astype(np.float32) - patch.astype(np.float32)).mean()
    )
    ssim = _global_ssim(template, patch)
    ncc_value = float(ncc) if math.isfinite(float(ncc)) else 0.0
    hit = (
        ncc_value >= TEMPLATE_MATCH_MIN_NCC
        and ssim >= TEMPLATE_MATCH_MIN_SSIM
        and mad <= TEMPLATE_MATCH_MAX_MAD
    )
    return {
        "hit": hit,
        "rect": match_rect,
        "ncc": ncc_value,
        "ssim": ssim,
        "mad": mad,
    }


def _template_hit_window(
    hit_frames: Sequence[int],
    *,
    anchor_frame: int,
    scan_start: int,
    scan_end: int,
) -> tuple[int, int, list[int], int, int]:
    """Select the anchor-contiguous run and require immediate negatives."""

    start, end, contiguous = infer_contiguous_hit_window(
        hit_frames, anchor_frame=anchor_frame, max_internal_gap=0
    )
    if start <= int(scan_start) or end >= int(scan_end):
        raise OutputCoverageMaterializationError(
            "Immediate template negative evidence is incomplete"
        )
    before_frame = start - 1
    after_frame = end + 1
    hit_set = {int(value) for value in hit_frames}
    if before_frame in hit_set or after_frame in hit_set:
        raise OutputCoverageMaterializationError(
            "Template boundary negative evidence is positive"
        )
    if contiguous != list(range(start, end + 1)):
        raise OutputCoverageMaterializationError(
            "Source-template span contains an internal gap"
        )
    return start, end, contiguous, before_frame, after_frame


def _track_operator_source_template(
    *,
    frame_cache: _FrameCache,
    binding: Mapping[str, Any],
    scan_start: int,
    scan_end: int,
) -> dict[str, Any]:
    anchor_frame = int(binding.get("anchor_frame") or 0)
    anchor_rect = tuple(int(value) for value in binding.get("anchor_rect") or ())
    template_gray = binding.get("template_gray")
    if (
        len(anchor_rect) != 4
        or not (int(scan_start) <= anchor_frame <= int(scan_end))
    ):
        raise OutputCoverageMaterializationError(
            "Source-template anchor is outside scan window"
        )
    results: dict[int, dict[str, Any]] = {}
    iterator = getattr(frame_cache, "iter_range", None)
    frames = (
        iterator(int(scan_start), int(scan_end))
        if callable(iterator)
        else (
            (frame_index, frame_cache.get(frame_index))
            for frame_index in range(int(scan_start), int(scan_end) + 1)
        )
    )
    for frame_index, frame in frames:
        results[int(frame_index)] = _match_source_template_frame(
            frame,
            template_gray=template_gray,
            predicted_rect=anchor_rect,
        )
    anchor_result = results.get(anchor_frame)
    if anchor_result is None:
        raise OutputCoverageMaterializationError(
            "Source-template anchor frame was not decoded"
        )
    if not bool(anchor_result.get("hit")):
        raise OutputCoverageMaterializationError(
            "Source-template anchor did not match itself"
        )
    hit_frames = sorted(
        frame_index
        for frame_index, row in results.items()
        if bool(row.get("hit"))
    )
    start, end, contiguous, before_frame, after_frame = _template_hit_window(
        hit_frames,
        anchor_frame=anchor_frame,
        scan_start=int(scan_start),
        scan_end=int(scan_end),
    )
    return {
        "start_frame": start,
        "end_frame": end,
        "hit_frames": contiguous,
        "all_hit_frames": hit_frames,
        "before_frame": before_frame,
        "after_frame": after_frame,
        "results": results,
    }


def _coverage_candidates(
    proposal_case: Mapping[str, Any], review_case: Mapping[str, Any]
) -> list[dict[str, Any]]:
    clusters = {
        str(row.get("cluster_id") or ""): dict(row)
        for raw in list(review_case.get("clusters") or [])
        if isinstance(raw, Mapping)
        for row in (dict(raw),)
    }
    approved_signatures_by_vi: dict[str, set[str]] = {}
    for raw in list(proposal_case.get("decisions") or []):
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        if str(row.get("proposed_action") or "") == FALSE_POSITIVE_ACTION:
            continue
        vi_text = str(row.get("vi_text_suggested") or "").strip()
        signature = _signature(str(row.get("source_text_suggested") or ""))
        if vi_text and signature:
            approved_signatures_by_vi.setdefault(vi_text, set()).add(signature)
    output: list[dict[str, Any]] = []
    for raw in list(proposal_case.get("decisions") or []):
        if not isinstance(raw, Mapping):
            continue
        decision = dict(raw)
        if str(decision.get("proposed_action") or "") == FALSE_POSITIVE_ACTION:
            continue
        cluster_id = str(decision.get("cluster_id") or "")
        cluster = clusters.get(cluster_id)
        source_text = str(decision.get("source_text_suggested") or "").strip()
        vi_text = str(decision.get("vi_text_suggested") or "").strip()
        if cluster is None or not source_text or not vi_text:
            raise OutputCoverageMaterializationError(
                f"Coverage decision is incomplete: {cluster_id}"
            )
        signature = _signature(source_text)
        if not signature:
            raise OutputCoverageMaterializationError(
                f"Coverage source signature is empty: {cluster_id}"
            )
        representative = _anchor(cluster)
        geometry = dict(representative.get("geometry") or {})
        anchor_rect = _rect(geometry)
        residual = {
            "signature": signature,
            "approved_signatures": sorted(
                approved_signatures_by_vi.get(vi_text) or {signature}
            ),
            "anchor_rect": anchor_rect,
            "detections": list(cluster.get("detections") or []),
        }
        output.append(
            {
                "cluster_id": cluster_id,
                "decision": decision,
                "cluster": cluster,
                "representative": representative,
                "residual": residual,
            }
        )
    return output


def _match_source_cluster_full_frame(
    frame: Any,
    residual: Mapping[str, Any],
    *,
    provider: Any,
    frame_time_ms: int,
    ocr_result_cache: dict[int, Any] | None = None,
) -> dict[str, Any] | None:
    """Rescue exact OCR when the crop detector needs full-frame context.

    A candidate remains exact: its normalized OCR signature must equal or
    contain an operator-approved signature.  For a merged OCR row, geometry
    stays at the approved residual anchor so unrelated neighboring labels are
    not covered.
    """

    import cv2
    import numpy as np

    image = np.asarray(frame)
    if image.ndim != 3 or image.shape[2] != 3:
        return None
    approved = {
        str(value)
        for value in list(residual.get("approved_signatures") or [])
        if str(value)
    }
    if not approved:
        approved = {str(residual.get("signature") or "")}
    anchor = tuple(residual.get("anchor_rect") or ())
    if len(anchor) != 4:
        return None
    cache_key = int(frame_time_ms)
    if ocr_result_cache is not None and cache_key in ocr_result_cache:
        result = ocr_result_cache[cache_key]
    else:
        with tempfile.TemporaryDirectory(
            prefix="phase4_output_boundary_full_"
        ) as temp_dir:
            path = Path(temp_dir) / "source_frame.jpg"
            if not cv2.imwrite(str(path), image):
                raise OutputCoverageMaterializationError(
                    "Cannot stage full-frame source OCR"
                )
            result = provider.detect_frame(path, frame_time_ms=frame_time_ms)
        if ocr_result_cache is not None:
            ocr_result_cache[cache_key] = result
    candidates: list[tuple[float, dict[str, Any]]] = []
    anchor_geometry = {
        "x": anchor[0],
        "y": anchor[1],
        "width": anchor[2] - anchor[0],
        "height": anchor[3] - anchor[1],
    }
    anchor_center = (
        (anchor[0] + anchor[2]) * 0.5,
        (anchor[1] + anchor[3]) * 0.5,
    )
    recognized: list[dict[str, Any]] = []
    for box in list(getattr(result, "boxes", []) or []):
        text = str(getattr(box, "text", "") or "").strip()
        signature = _signature(text)
        geometry = {
            "x": float(getattr(box, "x", 0.0) or 0.0),
            "y": float(getattr(box, "y", 0.0) or 0.0),
            "width": float(getattr(box, "width", 0.0) or 0.0),
            "height": float(getattr(box, "height", 0.0) or 0.0),
        }
        confidence = float(getattr(box, "confidence", 0.0) or 0.0)
        if signature and confidence >= 0.25:
            recognized.append(
                {
                    "text": text,
                    "signature": signature,
                    "confidence": confidence,
                    "geometry": geometry,
                }
            )
        exact_signature = next(
            (
                value
                for value in approved
                if signature == value or value in signature
            ),
            None,
        )
        if exact_signature is None or confidence < 0.25:
            continue
        try:
            overlap = _overlap(geometry, anchor_geometry)
        except OutputCoverageMaterializationError:
            continue
        center = (
            float(geometry["x"]) + float(geometry["width"]) * 0.5,
            float(geometry["y"]) + float(geometry["height"]) * 0.5,
        )
        center_distance = math.dist(center, anchor_center)
        merged = signature != exact_signature
        if overlap < 0.50 and (merged or center_distance > 0.18):
            continue
        candidates.append(
            (
                overlap + confidence + (1.0 if not merged else 0.0),
                {
                    "text": text,
                    "signature": signature,
                    "matched_approved_signature": exact_signature,
                    "confidence": confidence,
                    "geometry": (
                        {
                            **anchor_geometry,
                        }
                        if merged
                        else geometry
                    ),
                    "full_frame_ocr_geometry": geometry,
                    "overlap": overlap,
                    "match_mode": (
                        "APPROVED_SIGNATURE_IN_MERGED_OCR_ROW"
                        if merged
                        else "EXACT_FULL_FRAME_SIGNATURE"
                    ),
                },
            )
        )
    for size in (2, 3):
        for rows in combinations(recognized, size):
            combined = "".join(str(row["signature"]) for row in rows)
            exact_signature = next(
                (value for value in approved if combined == value),
                None,
            )
            if exact_signature is None:
                continue
            rects = [_rect(dict(row["geometry"])) for row in rows]
            union = {
                "x": min(rect[0] for rect in rects),
                "y": min(rect[1] for rect in rects),
                "width": max(rect[2] for rect in rects)
                - min(rect[0] for rect in rects),
                "height": max(rect[3] for rect in rects)
                - min(rect[1] for rect in rects),
            }
            overlap = _overlap(union, anchor_geometry)
            center = (
                float(union["x"]) + float(union["width"]) * 0.5,
                float(union["y"]) + float(union["height"]) * 0.5,
            )
            center_distance = math.dist(center, anchor_center)
            if overlap < 0.50 and center_distance > 0.18:
                continue
            confidence = min(float(row["confidence"]) for row in rows)
            candidates.append(
                (
                    overlap + confidence + 1.5,
                    {
                        "text": " | ".join(str(row["text"]) for row in rows),
                        "signature": combined,
                        "matched_approved_signature": exact_signature,
                        "confidence": confidence,
                        "geometry": union,
                        "full_frame_ocr_geometry": union,
                        "overlap": overlap,
                        "match_mode": "EXACT_COMPOUND_FULL_FRAME_SIGNATURE",
                        "compound_box_count": size,
                    },
                )
            )
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _match_source_cluster_deskew_crop(
    frame: Any,
    residual: Mapping[str, Any],
    *,
    provider: Any,
    frame_time_ms: int,
) -> dict[str, Any] | None:
    """Deskew a bounded phone-screen crop, then require an exact signature."""

    import cv2
    import numpy as np

    image = np.asarray(frame)
    if image.ndim != 3 or image.shape[2] != 3:
        return None
    height, width = image.shape[:2]
    anchor = tuple(residual.get("anchor_rect") or ())
    approved = {
        str(value)
        for value in list(residual.get("approved_signatures") or [])
        if str(value)
    } or {str(residual.get("signature") or "")}
    if len(anchor) != 4 or not any(approved):
        return None
    pad_x = max(0.03, (float(anchor[2]) - float(anchor[0])) * 0.35)
    pad_y = max(0.03, (float(anchor[3]) - float(anchor[1])) * 0.80)
    x0 = max(0, int(math.floor((float(anchor[0]) - pad_x) * width)))
    y0 = max(0, int(math.floor((float(anchor[1]) - pad_y) * height)))
    x1 = min(width, int(math.ceil((float(anchor[2]) + pad_x) * width)))
    y1 = min(height, int(math.ceil((float(anchor[3]) + pad_y) * height)))
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    crop_height, crop_width = crop.shape[:2]
    candidates: list[tuple[float, dict[str, Any]]] = []
    for angle in (-15.0, -10.0, -5.0):
        matrix = cv2.getRotationMatrix2D(
            (crop_width * 0.5, crop_height * 0.5), angle, 1.0
        )
        inverse = cv2.invertAffineTransform(matrix)
        rotated = cv2.warpAffine(
            crop,
            matrix,
            (crop_width, crop_height),
            borderMode=cv2.BORDER_REPLICATE,
        )
        staged = cv2.resize(
            rotated, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC
        )
        with tempfile.TemporaryDirectory(
            prefix="phase4_output_boundary_deskew_"
        ) as temp_dir:
            path = Path(temp_dir) / "source_crop.jpg"
            if not cv2.imwrite(str(path), staged):
                raise OutputCoverageMaterializationError(
                    "Cannot stage deskewed source OCR crop"
                )
            result = provider.detect_frame(path, frame_time_ms=frame_time_ms)
        recognized: list[dict[str, Any]] = []
        for box in list(getattr(result, "boxes", []) or []):
            text = str(getattr(box, "text", "") or "").strip()
            signature = _signature(text)
            confidence = float(getattr(box, "confidence", 0.0) or 0.0)
            if not signature or confidence < 0.25:
                continue
            rx0 = float(getattr(box, "x", 0.0) or 0.0) * crop_width
            ry0 = float(getattr(box, "y", 0.0) or 0.0) * crop_height
            rx1 = rx0 + float(getattr(box, "width", 0.0) or 0.0) * crop_width
            ry1 = ry0 + float(getattr(box, "height", 0.0) or 0.0) * crop_height
            corners = np.array(
                [[rx0, ry0, 1.0], [rx1, ry0, 1.0], [rx1, ry1, 1.0], [rx0, ry1, 1.0]],
                dtype=np.float64,
            )
            restored = corners @ inverse.T
            px0 = max(0.0, min(crop_width, float(restored[:, 0].min())))
            py0 = max(0.0, min(crop_height, float(restored[:, 1].min())))
            px1 = max(0.0, min(crop_width, float(restored[:, 0].max())))
            py1 = max(0.0, min(crop_height, float(restored[:, 1].max())))
            geometry = {
                "x": (x0 + px0) / width,
                "y": (y0 + py0) / height,
                "width": max(1.0, px1 - px0) / width,
                "height": max(1.0, py1 - py0) / height,
            }
            recognized.append(
                {
                    "text": text,
                    "signature": signature,
                    "confidence": confidence,
                    "geometry": geometry,
                }
            )
        for size in (1, 2, 3):
            for rows in combinations(recognized, size):
                combined = "".join(str(row["signature"]) for row in rows)
                exact = next((value for value in approved if combined == value), None)
                if exact is None:
                    continue
                rects = [_rect(dict(row["geometry"])) for row in rows]
                union = {
                    "x": min(rect[0] for rect in rects),
                    "y": min(rect[1] for rect in rects),
                    "width": max(rect[2] for rect in rects)
                    - min(rect[0] for rect in rects),
                    "height": max(rect[3] for rect in rects)
                    - min(rect[1] for rect in rects),
                }
                confidence = min(float(row["confidence"]) for row in rows)
                candidates.append(
                    (
                        confidence + (0.5 if size == 1 else 0.0),
                        {
                            "text": " | ".join(str(row["text"]) for row in rows),
                            "signature": combined,
                            "matched_approved_signature": exact,
                            "confidence": confidence,
                            "geometry": union,
                            "match_mode": "EXACT_DESKEWED_CROP_SIGNATURE",
                            "deskew_angle_degrees": angle,
                            "compound_box_count": size,
                        },
                    )
                )
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _candidate_scan(
    candidate: Mapping[str, Any],
    *,
    tracks: Sequence[Mapping[str, Any]],
    frame_count: int,
) -> dict[str, Any]:
    decision = dict(candidate.get("decision") or {})
    content_ids = {str(value) for value in list(decision.get("content_ids") or []) if str(value)}
    intersection_ids = {
        str(dict(value).get("text_id") or "")
        for value in list(decision.get("active_intersections") or [])
        if isinstance(value, Mapping)
    }
    authorities = [
        dict(row)
        for row in tracks
        if isinstance(row, Mapping)
        and (
            str(dict(row).get("content_id") or "") in content_ids
            or str(dict(row).get("text_id") or "") in intersection_ids
        )
    ]
    detections = [
        dict(row)
        for row in list(dict(candidate.get("cluster") or {}).get("detections") or [])
        if isinstance(row, Mapping)
    ]
    residual_frames = [int(row.get("frame_index") or 0) for row in detections]
    representative = int(dict(candidate.get("representative") or {}).get("frame_index") or 0)
    start_frame = min(
        [int(row.get("start_frame") or representative) for row in authorities]
        or residual_frames
        or [representative]
    )
    end_frame = max(
        [int(row.get("end_frame") or representative) for row in authorities]
        or residual_frames
        or [representative]
    )
    scan_frames, scan_start, scan_end = build_boundary_scan_frames(
        start_frame=start_frame,
        end_frame=end_frame,
        residual_frames=residual_frames,
        frame_count=frame_count,
        required_frames=[representative, *residual_frames],
        margin_frames=BOUNDARY_MARGIN_FRAMES,
        max_samples=BOUNDARY_MAX_SAMPLES,
    )
    return {
        "frames": scan_frames,
        "scan_start": scan_start,
        "scan_end": scan_end,
        "authority_track_ids": [str(row.get("text_id") or "") for row in authorities],
    }


def _boundary_evidence_image(
    *,
    path: Path,
    frame_cache: _FrameCache,
    frames: Sequence[int],
    geometry: Mapping[str, Any],
) -> None:
    import cv2
    import numpy as np

    x0, y0, x1, y1 = _rect(geometry)
    tiles = []
    for frame_index in frames:
        image = frame_cache.get(int(frame_index))
        height, width = image.shape[:2]
        pad_x = max(10, int(round((x1 - x0) * width * 0.25)))
        pad_y = max(10, int(round((y1 - y0) * height * 0.35)))
        px0 = max(0, int(math.floor(x0 * width)) - pad_x)
        py0 = max(0, int(math.floor(y0 * height)) - pad_y)
        px1 = min(width, int(math.ceil(x1 * width)) + pad_x)
        py1 = min(height, int(math.ceil(y1 * height)) + pad_y)
        crop = image[py0:py1, px0:px1].copy()
        cv2.putText(
            crop,
            f"f={int(frame_index)}",
            (5, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )
        tiles.append(crop)
    if not tiles:
        raise OutputCoverageMaterializationError("Boundary evidence has no frames")
    target_height = max(tile.shape[0] for tile in tiles)
    normalized = []
    for tile in tiles:
        if tile.shape[0] != target_height:
            tile = cv2.copyMakeBorder(
                tile,
                0,
                target_height - tile.shape[0],
                0,
                0,
                cv2.BORDER_CONSTANT,
                value=(255, 255, 255),
            )
        normalized.append(tile)
    contact = np.hstack(normalized)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), contact):
        raise OutputCoverageMaterializationError("Cannot write boundary evidence")


def _kind_for_geometry(geometry: Mapping[str, Any]) -> tuple[str, list[str]]:
    width = float(geometry.get("width") or 0.0)
    height = float(geometry.get("height") or 0.0)
    y = float(geometry.get("y") or 0.0)
    if width >= 0.42 and height <= 0.12 and y >= 0.35:
        return "hardsub", ["hardsub"]
    if width >= 0.20 and height >= 0.05 and y < 0.48:
        return "title", ["mid_label"]
    return "ui", ["ui_chip"]


def _simultaneous_count(track: Mapping[str, Any], tracks: Sequence[Mapping[str, Any]]) -> int:
    start = int(track.get("start_frame") or 0)
    end = int(track.get("end_frame") or start)
    events = {start}
    for row in tracks:
        row_start = int(dict(row).get("start_frame") or 0)
        if start <= row_start <= end:
            events.add(row_start)
    return max(
        1,
        max(
            sum(
                int(dict(row).get("start_frame") or 0) <= event
                <= int(dict(row).get("end_frame") or -1)
                for row in tracks
            )
            for event in events
        ),
    )


def _merge_candidates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for raw in sorted(rows, key=lambda row: (int(row.get("start_frame") or 0), str(row.get("cluster_id") or ""))):
        row = dict(raw)
        match = next(
            (
                existing
                for existing in merged
                if str(existing.get("vi_text") or "") == str(row.get("vi_text") or "")
                and str(existing.get("content_id") or "") == str(row.get("content_id") or "")
                and int(row.get("start_frame") or 0) <= int(existing.get("end_frame") or -1) + 1
                and int(existing.get("start_frame") or 0) <= int(row.get("end_frame") or -1) + 1
                and _overlap(dict(existing.get("geometry") or {}), dict(row.get("geometry") or {})) >= 0.70
            ),
            None,
        )
        if match is None:
            row["cluster_ids"] = [str(row.get("cluster_id") or "")]
            row["verification_statuses"] = [
                str(row.get("verification_status") or SOURCE_BOUNDARY_VERIFIED)
            ]
            merged.append(row)
            continue
        match["start_frame"] = min(int(match["start_frame"]), int(row["start_frame"]))
        match["end_frame"] = max(int(match["end_frame"]), int(row["end_frame"]))
        match["cluster_ids"].append(str(row.get("cluster_id") or ""))
        match["hit_frames"] = sorted(set(match.get("hit_frames") or []) | set(row.get("hit_frames") or []))
        match["verification_statuses"] = sorted(
            set(match.get("verification_statuses") or [])
            | {
                str(
                    row.get("verification_status")
                    or SOURCE_BOUNDARY_VERIFIED
                )
            }
        )
    return merged


def _scan_case(
    *,
    case_root: Path,
    candidates: Sequence[Mapping[str, Any]],
    effective_contract: Mapping[str, Any],
    provider: Any,
    artifact_version: str = "v22_8_1",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    video = dict(effective_contract.get("video") or {})
    frame_count = int(video.get("frame_count") or 0)
    fps = float(video.get("fps") or 0.0)
    if frame_count < 1 or fps <= 0:
        raise OutputCoverageMaterializationError("Video frame authority is invalid")
    tracks = [
        dict(row)
        for row in list(effective_contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    source = _source_path(case_root)
    plans: dict[str, dict[str, Any]] = {}
    all_scan_frames: set[int] = set()
    for candidate in candidates:
        cluster_id = str(candidate.get("cluster_id") or "")
        plans[cluster_id] = _candidate_scan(
            candidate, tracks=tracks, frame_count=frame_count
        )
        all_scan_frames.update(plans[cluster_id]["frames"])
    frames = _load_selected_frames(source, sorted(all_scan_frames))
    frame_cache = _FrameCache(source, frames)
    matches: dict[tuple[str, int], dict[str, Any] | None] = {}
    tracking_rects: dict[str, tuple[float, float, float, float]] = {}
    full_frame_ocr_cache: dict[int, Any] = {}
    deskew_attempted: set[tuple[str, int]] = set()
    evidence_frames = {
        str(candidate.get("cluster_id") or ""): {
            int(dict(row).get("frame_index") or 0)
            for row in list(dict(candidate.get("cluster") or {}).get("detections") or [])
            if isinstance(row, Mapping)
        }
        for candidate in candidates
    }

    def match(candidate: Mapping[str, Any], frame_index: int) -> dict[str, Any] | None:
        cluster_id = str(candidate.get("cluster_id") or "")
        key = (cluster_id, int(frame_index))
        if key not in matches:
            residual = dict(candidate.get("residual") or {})
            if cluster_id in tracking_rects:
                residual["anchor_rect"] = tracking_rects[cluster_id]
            matches[key] = _match_source_cluster_full_frame(
                frame_cache.get(frame_index),
                residual,
                provider=provider,
                frame_time_ms=int(round(frame_index * 1000.0 / fps)),
                ocr_result_cache=full_frame_ocr_cache,
            )
            if matches[key] is None:
                matches[key] = match_source_cluster_crop(
                    frame_cache.get(frame_index),
                    residual,
                    provider=provider,
                    frame_time_ms=int(round(frame_index * 1000.0 / fps)),
                )
        if (
            matches.get(key) is None
            and key not in deskew_attempted
            and (
                int(frame_index) in evidence_frames.get(cluster_id, set())
                or cluster_id in tracking_rects
            )
        ):
            deskew_attempted.add(key)
            residual = dict(candidate.get("residual") or {})
            if cluster_id in tracking_rects:
                residual["anchor_rect"] = tracking_rects[cluster_id]
            matches[key] = _match_source_cluster_deskew_crop(
                frame_cache.get(frame_index),
                residual,
                provider=provider,
                frame_time_ms=int(round(frame_index * 1000.0 / fps)),
            )
        if matches.get(key) is not None:
            rect = _rect(dict(matches[key].get("geometry") or {}))
            tracking_rects[cluster_id] = rect
        return matches[key]

    attempts: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    evidence_dir = (
        case_root / "qa" / f"phase4_output_boundary_rescan_{artifact_version}"
    )
    for candidate in candidates:
        cluster_id = str(candidate.get("cluster_id") or "")
        decision = dict(candidate.get("decision") or {})
        plan = plans[cluster_id]
        attempt: dict[str, Any] = {
            "cluster_id": cluster_id,
            "proposed_action": decision.get("proposed_action"),
            "source_text": decision.get("source_text_suggested"),
            "vi_text": decision.get("vi_text_suggested"),
            "geometry_strategy": decision.get("geometry_strategy")
            or "CLUSTER_GEOMETRY",
            "scan_window": [plan["scan_start"], plan["scan_end"]],
            "coarse_scan_frames": list(plan["frames"]),
            "authority_track_ids": plan["authority_track_ids"],
            "status": "SOURCE_BOUNDARY_VALIDATION_FAILED",
        }
        try:
            if (
                str(decision.get("geometry_strategy") or "")
                == OPERATOR_SOURCE_TEMPLATE_STRATEGY
            ):
                binding = _bind_operator_source_template(
                    case_root=case_root,
                    candidate=candidate,
                    frame_cache=frame_cache,
                )
                anchor_frame = int(binding["anchor_frame"])
                template_scan_start = max(
                    0,
                    anchor_frame - TEMPLATE_TRACK_MAX_RADIUS_FRAMES,
                )
                template_scan_end = min(
                    frame_count - 1,
                    anchor_frame + TEMPLATE_TRACK_MAX_RADIUS_FRAMES,
                )
                attempt["scan_window"] = [
                    template_scan_start,
                    template_scan_end,
                ]
                tracking = _track_operator_source_template(
                    frame_cache=frame_cache,
                    binding=binding,
                    scan_start=template_scan_start,
                    scan_end=template_scan_end,
                )
                contiguous_hits = [
                    int(value) for value in tracking["hit_frames"]
                ]
                geometries = [
                    _normalized_geometry(
                        dict(tracking["results"])[frame_index]["rect"],
                        frame_cache.get(frame_index),
                    )
                    for frame_index in contiguous_hits
                ]
                geometry = {
                    key: float(
                        median(float(row[key]) for row in geometries)
                    )
                    for key in ("x", "y", "width", "height")
                }
                _rect(geometry)
                content_ids = [
                    str(value)
                    for value in list(decision.get("content_ids") or [])
                    if str(value)
                ]
                content_id = (
                    content_ids[0]
                    if len(set(content_ids)) == 1
                    else f"p4out_content_{cluster_id.removeprefix('outres_')}"
                )
                before_frame = int(tracking["before_frame"])
                after_frame = int(tracking["after_frame"])
                evidence_sequence = [
                    before_frame,
                    int(tracking["start_frame"]),
                    anchor_frame,
                    int(tracking["end_frame"]),
                    after_frame,
                ]
                evidence_path = evidence_dir / f"{cluster_id}.jpg"
                _boundary_evidence_image(
                    path=evidence_path,
                    frame_cache=frame_cache,
                    frames=evidence_sequence,
                    geometry=geometry,
                )

                def compact_result(frame_index: int) -> dict[str, Any]:
                    result = dict(dict(tracking["results"])[frame_index])
                    return {
                        "frame_index": int(frame_index),
                        "hit": bool(result.get("hit")),
                        "ncc": round(float(result.get("ncc") or 0.0), 6),
                        "ssim": round(float(result.get("ssim") or 0.0), 6),
                        "mad": round(float(result.get("mad") or 0.0), 6),
                        "geometry": _normalized_geometry(
                            result.get("rect") or (), frame_cache.get(frame_index)
                        ),
                    }

                attempt.update(
                    {
                        "status": SOURCE_TEMPLATE_OPERATOR_VERIFIED,
                        "source_span": [
                            int(tracking["start_frame"]),
                            int(tracking["end_frame"]),
                        ],
                        "negative_evidence": {
                            "before": compact_result(before_frame),
                            "after": compact_result(after_frame),
                        },
                        "source_geometry": geometry,
                        "source_hit_frames": contiguous_hits,
                        "all_template_hit_frames": list(
                            tracking["all_hit_frames"]
                        ),
                        "template_tracking_metrics": [
                            compact_result(frame_index)
                            for frame_index in contiguous_hits
                        ],
                        "source_template_binding": {
                            "representative_frame_index": anchor_frame,
                            "contact_sheet_ref": binding[
                                "contact_sheet_ref"
                            ],
                            "binding_metrics": {
                                key: round(float(value), 6)
                                for key, value in dict(
                                    binding["binding_metrics"]
                                ).items()
                            },
                            "template_stddev": round(
                                float(binding["template_stddev"]), 6
                            ),
                            "thresholds": {
                                "binding_max_mad": TEMPLATE_BINDING_MAX_MAD,
                                "binding_min_ssim": TEMPLATE_BINDING_MIN_SSIM,
                                "binding_min_ncc": TEMPLATE_BINDING_MIN_NCC,
                                "tracking_min_ncc": TEMPLATE_MATCH_MIN_NCC,
                                "tracking_min_ssim": TEMPLATE_MATCH_MIN_SSIM,
                                "tracking_max_mad": TEMPLATE_MATCH_MAX_MAD,
                            },
                        },
                        "evidence_ref": {
                            "path": evidence_path.relative_to(
                                case_root
                            ).as_posix(),
                            "sha256": _sha256_file(evidence_path),
                        },
                        "provider": "opencv-match-template",
                    }
                )
                verified.append(
                    {
                        "cluster_id": cluster_id,
                        "content_id": content_id,
                        "source_text": str(
                            decision.get("source_text_suggested") or ""
                        ),
                        "vi_text": str(decision.get("vi_text_suggested") or ""),
                        "start_frame": int(tracking["start_frame"]),
                        "end_frame": int(tracking["end_frame"]),
                        "best_frame_index": anchor_frame,
                        "geometry": geometry,
                        "output_residual_geometry": dict(
                            dict(candidate.get("representative") or {}).get(
                                "geometry"
                            )
                            or {}
                        ),
                        "residual_signature": str(
                            dict(candidate.get("residual") or {}).get(
                                "signature"
                            )
                            or ""
                        ),
                        "hit_frames": contiguous_hits,
                        "verification_status": SOURCE_TEMPLATE_OPERATOR_VERIFIED,
                        "attempt_evidence_ref": attempt["evidence_ref"],
                        "source_template_contact_sheet_ref": binding[
                            "contact_sheet_ref"
                        ],
                    }
                )
                attempts.append(attempt)
                continue
            coarse_hits = [
                frame_index
                for frame_index in plan["frames"]
                if match(candidate, frame_index) is not None
            ]
            approved_evidence_frames = sorted(
                {
                    int(dict(row).get("frame_index") or 0)
                    for row in list(dict(candidate.get("cluster") or {}).get("detections") or [])
                    if isinstance(row, Mapping)
                }
            )
            anchor_frame = next(
                (frame for frame in approved_evidence_frames if frame in coarse_hits),
                None,
            )
            if anchor_frame is None:
                raise OutputCoverageMaterializationError(
                    "No approved residual frame matched exact source OCR"
                )
            ordered_scan = sorted(plan["frames"])
            max_gap = max(
                (right - left - 1 for left, right in zip(ordered_scan, ordered_scan[1:])),
                default=0,
            )
            coarse_start, coarse_end, coarse_run = infer_contiguous_hit_window(
                coarse_hits,
                anchor_frame=anchor_frame,
                max_internal_gap=max_gap,
            )
            exact_frames = list(range(coarse_start, coarse_end + 1))
            exact_hits = [
                frame_index
                for frame_index in exact_frames
                if match(candidate, frame_index) is not None
            ]
            exact_start, exact_end, exact_run = infer_contiguous_hit_window(
                exact_hits,
                anchor_frame=anchor_frame,
                max_internal_gap=0,
            )
            (
                refined_start,
                refined_end,
                before_confirmed,
                after_confirmed,
                probed,
            ) = refine_hit_boundaries(
                start_frame=exact_start,
                end_frame=exact_end,
                frame_count=frame_count,
                is_hit=lambda index: match(candidate, index) is not None,
            )
            if not before_confirmed or not after_confirmed:
                raise OutputCoverageMaterializationError(
                    "Immediate outside negative evidence is incomplete"
                )
            before_frame = refined_start - 1 if refined_start > 0 else None
            after_frame = refined_end + 1 if refined_end + 1 < frame_count else None
            if before_frame is not None and match(candidate, before_frame) is not None:
                raise OutputCoverageMaterializationError(
                    "Source OCR remains positive before refined boundary"
                )
            if after_frame is not None and match(candidate, after_frame) is not None:
                raise OutputCoverageMaterializationError(
                    "Source OCR remains positive after refined boundary"
                )
            hit_frames = [
                frame_index
                for frame_index in range(refined_start, refined_end + 1)
                if match(candidate, frame_index) is not None
            ]
            contiguous_start, contiguous_end, contiguous_hits = infer_contiguous_hit_window(
                hit_frames,
                anchor_frame=anchor_frame,
                max_internal_gap=0,
            )
            if contiguous_start != refined_start or contiguous_end != refined_end:
                raise OutputCoverageMaterializationError(
                    "Exact source OCR span contains an internal negative"
                )
            source_boxes = [
                dict(match(candidate, frame_index) or {})
                for frame_index in contiguous_hits
            ]
            geometry = {
                key: float(median(float(dict(row.get("geometry") or {}).get(key) or 0.0) for row in source_boxes))
                for key in ("x", "y", "width", "height")
            }
            _rect(geometry)
            content_ids = [str(value) for value in list(decision.get("content_ids") or []) if str(value)]
            content_id = content_ids[0] if len(set(content_ids)) == 1 else f"p4out_content_{cluster_id.removeprefix('outres_')}"
            evidence_sequence = [
                frame
                for frame in (before_frame, refined_start, anchor_frame, refined_end, after_frame)
                if frame is not None
            ]
            evidence_path = evidence_dir / f"{cluster_id}.jpg"
            _boundary_evidence_image(
                path=evidence_path,
                frame_cache=frame_cache,
                frames=evidence_sequence,
                geometry=geometry,
            )
            attempt.update(
                {
                    "status": SOURCE_BOUNDARY_VERIFIED,
                    "coarse_hit_frames": coarse_hits,
                    "coarse_run": coarse_run,
                    "exact_initial_run": exact_run,
                    "refinement_probed_frames": probed,
                    "source_span": [refined_start, refined_end],
                    "negative_evidence": {
                        "before_frame": before_frame,
                        "before_hit": False,
                        "after_frame": after_frame,
                        "after_hit": False,
                    },
                    "source_geometry": geometry,
                    "source_hit_frames": contiguous_hits,
                    "source_ocr_confidences": [
                        round(float(row.get("confidence") or 0.0), 4)
                        for row in source_boxes
                    ],
                    "evidence_ref": {
                        "path": evidence_path.relative_to(case_root).as_posix(),
                        "sha256": _sha256_file(evidence_path),
                    },
                    "provider": getattr(provider, "provider_name", "unknown"),
                }
            )
            verified.append(
                {
                    "cluster_id": cluster_id,
                    "content_id": content_id,
                    "source_text": str(decision.get("source_text_suggested") or ""),
                    "vi_text": str(decision.get("vi_text_suggested") or ""),
                    "start_frame": refined_start,
                    "end_frame": refined_end,
                    "best_frame_index": anchor_frame,
                    "geometry": geometry,
                    "output_residual_geometry": dict(
                        dict(candidate.get("representative") or {}).get(
                            "geometry"
                        )
                        or {}
                    ),
                    "residual_signature": str(
                        dict(candidate.get("residual") or {}).get("signature")
                        or ""
                    ),
                    "hit_frames": contiguous_hits,
                    "verification_status": SOURCE_BOUNDARY_VERIFIED,
                    "attempt_evidence_ref": attempt["evidence_ref"],
                }
            )
        except (OutputCoverageMaterializationError, ValueError) as exc:
            attempt["failure_reason"] = str(exc)
        attempts.append(attempt)
    return attempts, verified


def _tracks_from_verified(
    *,
    verified: Sequence[Mapping[str, Any]],
    existing_tracks: Sequence[Mapping[str, Any]],
    fps: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    merged = _merge_candidates(verified)
    preliminary: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    for row in merged:
        vi_text = gate_vi_for_burn(str(row.get("vi_text") or ""))
        if not vi_text:
            continue
        geometry = dict(row.get("geometry") or {})
        kind, roles = _kind_for_geometry(geometry)
        identity = hashlib.sha256(
            json.dumps(
                {
                    "clusters": sorted(row.get("cluster_ids") or []),
                    "span": [row.get("start_frame"), row.get("end_frame")],
                    "geometry": geometry,
                    "vi_text": vi_text,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:12]
        start_frame = int(row.get("start_frame") or 0)
        end_frame = int(row.get("end_frame") or 0)
        candidate = {
                "text_id": f"p4out_{identity}",
                "content_id": row.get("content_id"),
                "start_frame": start_frame,
                "end_frame": end_frame,
                "best_frame_index": int(row.get("best_frame_index") or start_frame),
                "start_ms": int(round(start_frame * 1000.0 / fps)),
                "end_ms": int(round((end_frame + 1) * 1000.0 / fps)),
                "geometry": geometry,
                "roles": roles,
                "kind": kind,
                "text_vi": vi_text,
                "translation_status": "TRANSLATION_APPROVED",
                "cover_only": False,
                "duplicate_transition_canonical": False,
                "output_residual_coverage": {
                    "status": (
                        "OPERATOR_APPROVED_SOURCE_TEMPLATE_VERIFIED"
                        if SOURCE_TEMPLATE_OPERATOR_VERIFIED
                        in set(row.get("verification_statuses") or [])
                        else "OPERATOR_APPROVED_SOURCE_BOUNDARY_VERIFIED"
                    ),
                    "verification_statuses": sorted(
                        row.get("verification_statuses") or []
                    ),
                    "cluster_ids": sorted(row.get("cluster_ids") or []),
                    "source_text": row.get("source_text"),
                    "attempt_evidence_ref": row.get("attempt_evidence_ref"),
                },
            }
        equivalent = next(
            (
                existing
                for raw in [*existing_tracks, *preliminary]
                if isinstance(raw, Mapping)
                for existing in (dict(raw),)
                if normalize_render_text(existing.get("text_vi"))
                == normalize_render_text(vi_text)
                and _overlap(existing, candidate) >= 0.90
                and (
                    max(
                        0,
                        min(
                            int(existing.get("end_frame") or -1),
                            end_frame,
                        )
                        - max(
                            int(existing.get("start_frame") or 0),
                            start_frame,
                        )
                        + 1,
                    )
                    / max(
                        1,
                        max(
                            int(existing.get("end_frame") or -1),
                            end_frame,
                        )
                        - min(
                            int(existing.get("start_frame") or 0),
                            start_frame,
                        )
                        + 1,
                    )
                )
                >= 0.90
            ),
            None,
        )
        if equivalent is not None:
            equivalent_id = str(equivalent.get("text_id") or "")
            reused.append(
                {
                    "candidate_text_id": candidate["text_id"],
                    "equivalent_text_id": equivalent_id,
                    "equivalent_is_same_attempt": any(
                        str(item.get("text_id") or "") == equivalent_id
                        for item in preliminary
                    ),
                    "source_text": row.get("source_text"),
                    "text_vi": vi_text,
                    "geometry_overlap_over_smaller": round(
                        _overlap(equivalent, candidate), 6
                    ),
                    "output_residual_geometry": dict(
                        row.get("output_residual_geometry") or {}
                    ),
                    "residual_signature": str(row.get("residual_signature") or ""),
                    "cluster_ids": sorted(row.get("cluster_ids") or []),
                }
            )
            continue
        preliminary.append(candidate)
    all_tracks: list[dict[str, Any]] = [dict(row) for row in existing_tracks] + preliminary
    output: list[dict[str, Any]] = []
    for track in preliminary:
        track["render_policy"] = plan_render_track(
            track,
            simultaneous_count=_simultaneous_count(track, all_tracks),
        )
        output.append(track)
    return output, reused


def _output_residual_alignment_overrides(
    reused: Sequence[Mapping[str, Any]],
    existing_tracks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Align an existing cover ROI to operator-reviewed encoded residual geometry."""

    by_id = {
        str(row.get("text_id") or ""): dict(row)
        for raw in existing_tracks
        if isinstance(raw, Mapping)
        for row in (dict(raw),)
        if str(row.get("text_id") or "")
    }
    operations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in reused:
        row = dict(raw)
        target_id = str(row.get("equivalent_text_id") or "")
        if not target_id or target_id in seen:
            continue
        target = by_id.get(target_id)
        if target is None:
            raise OutputCoverageMaterializationError(
                f"Equivalent output-coverage target is missing: {target_id}"
            )
        residual = dict(row.get("output_residual_geometry") or {})
        policy = dict(target.get("render_policy") or {})
        cover = dict(policy.get("cover") or {})
        current_roi = dict(cover.get("roi") or {})
        _rect(residual)
        _rect(current_roi)
        width = float(current_roi.get("width") or 0.0)
        height = float(current_roi.get("height") or 0.0)
        if bool(row.get("equivalent_is_same_attempt")):
            x0 = max(
                0.0,
                min(
                    float(current_roi.get("x") or 0.0),
                    float(residual.get("x") or 0.0) - 0.006,
                ),
            )
            y0 = max(
                0.0,
                min(
                    float(current_roi.get("y") or 0.0),
                    float(residual.get("y") or 0.0) - 0.008,
                ),
            )
            x1 = min(
                1.0,
                max(
                    float(current_roi.get("x") or 0.0) + width,
                    float(residual.get("x") or 0.0)
                    + float(residual.get("width") or 0.0)
                    + 0.006,
                ),
            )
            y1 = min(
                1.0,
                max(
                    float(current_roi.get("y") or 0.0) + height,
                    float(residual.get("y") or 0.0)
                    + float(residual.get("height") or 0.0)
                    + 0.008,
                ),
            )
            aligned_roi = {
                "x": x0,
                "y": y0,
                "width": x1 - x0,
                "height": y1 - y0,
            }
        else:
            aligned_roi = {
                "x": max(
                    0.0,
                    min(1.0 - width, float(residual.get("x") or 0.0) - 0.006),
                ),
                "y": max(
                    0.0,
                    min(1.0 - height, float(residual.get("y") or 0.0) - 0.008),
                ),
                "width": width,
                "height": height,
            }
        residual_signature = str(row.get("residual_signature") or "")
        source_signature = _signature(str(row.get("source_text") or ""))
        exact_residual_signature = bool(
            residual_signature
            and source_signature
            and residual_signature == source_signature
        )
        required_residual_width = (
            min(0.18, float(residual.get("width") or width) + 0.012)
            if exact_residual_signature
            else width
        )
        if (
            exact_residual_signature
            and float(residual.get("width") or 0.0) > width * 1.8
        ):
            aligned_roi["width"] = required_residual_width
            aligned_roi["x"] = max(
                0.0,
                min(
                    1.0 - aligned_roi["width"],
                    float(residual.get("x") or 0.0) - 0.006,
                ),
            )
        _rect(aligned_roi)
        previous_width_expanded = bool(
            dict(dict(target.get("render_policy") or {}).get("context") or {}).get(
                "output_residual_width_expanded"
            )
        )
        already_expanded_for_residual = bool(
            exact_residual_signature
            and width + 1e-9 >= required_residual_width
        )
        operations.append(
            {
                "operation": "POLICY_OVERRIDE",
                "target_text_id": target_id,
                "expected_track_sha256": _sha256_json(target),
                "context_updates": {
                    "output_residual_geometry_aligned": True,
                    "output_residual_width_expanded": (
                        previous_width_expanded
                        or already_expanded_for_residual
                        or aligned_roi["width"] > width
                    ),
                    "output_residual_alignment_cluster_ids": sorted(
                        row.get("cluster_ids") or []
                    ),
                },
                "cover_updates": {"roi": aligned_roi},
                "damage_budget_changed": False,
            }
        )
        seen.add(target_id)
    return operations


def _micro_ui_reference_overrides(
    tracks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Use a bounded clean reference for long, tiny OCR-confirmed UI labels."""

    operations: list[dict[str, Any]] = []
    for raw in tracks:
        track = dict(raw)
        text_id = str(track.get("text_id") or "")
        geometry = dict(track.get("geometry") or {})
        policy = dict(track.get("render_policy") or {})
        context = dict(policy.get("context") or {})
        cover = dict(policy.get("cover") or {})
        area = float(geometry.get("width") or 0.0) * float(
            geometry.get("height") or 0.0
        )
        span = int(track.get("end_frame") or 0) - int(
            track.get("start_frame") or 0
        ) + 1
        if (
            not text_id.startswith("p4out_")
            or not bool(context.get("micro_ui"))
            or span <= 6
            or bool(context.get("output_residual_bounded_dense_mask"))
        ):
            continue
        tiny_reference = area < 0.001 and str(
            cover.get("mask_mode") or ""
        ) != "stylized_components"
        operations.append(
            {
                "operation": "POLICY_OVERRIDE",
                "target_text_id": text_id,
                "expected_track_sha256": _sha256_json(track),
                "context_updates": {
                    "output_residual_bounded_dense_mask": True,
                    **(
                        {
                            "reference_plate_operator_approved": True,
                            "output_residual_micro_ui_reference": True,
                        }
                        if tiny_reference
                        else {}
                    ),
                },
                "cover_updates": (
                    {
                        "mask_mode": "stylized_components",
                        "fallback": "reference_plate_operator_approved",
                    }
                    if tiny_reference
                    else {}
                ),
                "damage_budget_changed": False,
            }
        )
    return operations


def _merge_added_track_operations(
    parent_operations: Sequence[Mapping[str, Any]],
    added_operations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Replace an existing ADD_TRACK and discard its superseded auto-policy."""

    replacements = {
        str(dict(row.get("track") or {}).get("text_id") or ""): dict(row)
        for raw in added_operations
        if isinstance(raw, Mapping)
        for row in (dict(raw),)
        if str(row.get("operation") or "") == "ADD_TRACK"
        and str(dict(row.get("track") or {}).get("text_id") or "")
    }
    merged: list[dict[str, Any]] = []
    replaced: set[str] = set()
    for raw in parent_operations:
        if not isinstance(raw, Mapping):
            continue
        operation = dict(raw)
        target_id = str(operation.get("target_text_id") or "")
        context_updates = dict(operation.get("context_updates") or {})
        cover_updates = dict(operation.get("cover_updates") or {})
        is_generated_micro_ui_override = (
            str(operation.get("operation") or "") == "POLICY_OVERRIDE"
            and target_id in replacements
            and context_updates.get("output_residual_bounded_dense_mask") is True
            and set(context_updates).issubset(
                {
                    "output_residual_bounded_dense_mask",
                    "reference_plate_operator_approved",
                    "output_residual_micro_ui_reference",
                }
            )
            and set(cover_updates).issubset({"mask_mode", "fallback"})
            and operation.get("damage_budget_changed") is False
        )
        if is_generated_micro_ui_override:
            continue
        track_id = (
            str(dict(operation.get("track") or {}).get("text_id") or "")
            if str(operation.get("operation") or "") == "ADD_TRACK"
            else ""
        )
        replacement = replacements.get(track_id)
        if replacement is None:
            merged.append(operation)
            continue
        if track_id not in replaced:
            merged.append(replacement)
            replaced.add(track_id)
    merged.extend(
        operation
        for track_id, operation in replacements.items()
        if track_id not in replaced
    )
    return merged


def materialize(
    *,
    run_root: str | Path,
    operator_id: str,
    materialized_at: str,
    provider: Any | None = None,
    retry_failed: bool = True,
    proposal_name: str = "phase4_output_residual_decision_proposal_v22_8_1.json",
    approval_name: str = "phase4_output_residual_decision_approval_v22_8_1.json",
    review_name: str = "phase4_output_residual_review_v22_8.json",
    false_positive_name: str = (
        "phase4_output_false_positive_materialization_v22_8_1.json"
    ),
    output_name: str = "phase4_output_coverage_materialization_v22_8_1.json",
    artifact_version: str = "v22_8_1",
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    names = (
        proposal_name,
        approval_name,
        review_name,
        false_positive_name,
        output_name,
    )
    if any(
        not str(value).strip()
        or Path(str(value)).name != str(value)
        or not str(value).endswith(".json")
        for value in names
    ):
        raise OutputCoverageMaterializationError("Invalid materialization filename")
    version = str(artifact_version or "").strip().lower()
    if not version or not version.replace("_", "").isalnum():
        raise OutputCoverageMaterializationError("Invalid artifact version")
    proposal_path = run / proposal_name
    approval_path = run / approval_name
    review_path = run / review_name
    false_positive_path = run / false_positive_name
    proposal = _load(proposal_path)
    approval = _load(approval_path)
    review = _load(review_path)
    false_positive = _load(false_positive_path)
    _verify_self(proposal, "proposal_sha256")
    _verify_self(approval, "approval_sha256")
    _verify_self(review, "review_sha256")
    _verify_self(false_positive, "materialization_sha256")
    if (
        str(approval.get("status") or "")
        != "PHASE4_OUTPUT_RESIDUAL_DECISIONS_APPROVED"
        or str(dict(approval.get("proposal_ref") or {}).get("sha256") or "")
        != _sha256_file(proposal_path)
        or int(dict(false_positive.get("counts") or {}).get("new_false_positive_decisions") or 0)
        != int(dict(dict(proposal.get("counts") or {}).get("actions") or {}).get(FALSE_POSITIVE_ACTION) or 0)
    ):
        raise OutputCoverageMaterializationError(
            "Approved decision or false-positive authority is incomplete"
        )
    operator = str(operator_id or "").strip()
    timestamp = str(materialized_at or "").strip()
    if not operator or not timestamp:
        raise OutputCoverageMaterializationError(
            "operator_id and materialized_at are required"
        )
    review_cases = {
        str(row.get("case_id") or ""): dict(row)
        for raw in list(review.get("cases") or [])
        if isinstance(raw, Mapping)
        for row in (dict(raw),)
    }
    runtime_provider = provider or build_local_residual_ocr_provider()
    case_results: list[dict[str, Any]] = []
    total_attempts = 0
    total_verified = 0
    total_materialized = 0
    status_counts: Counter[str] = Counter()
    for raw_case in list(proposal.get("cases") or []):
        case = dict(raw_case)
        case_id = str(case.get("case_id") or "")
        review_case = review_cases.get(case_id)
        if review_case is None:
            raise OutputCoverageMaterializationError(f"Review case is missing: {case_id}")
        candidates = _coverage_candidates(case, review_case)
        if not candidates:
            continue
        case_root = (run / case_id).resolve()
        input_path = case_root / "phase4_render_input.json"
        raw_contract = _load(input_path)
        try:
            effective_contract, parent_ref = apply_visual_remediation(
                case_root, raw_contract, contract_path=input_path
            )
        except VisualRemediationError as exc:
            raise OutputCoverageMaterializationError(str(exc)) from exc
        source_ref = dict(dict(case.get("authority_refs") or {}).get("source_video") or {})
        source = _source_path(case_root)
        if (
            source.name != str(source_ref.get("path") or "")
            or _sha256_file(source) != str(source_ref.get("sha256") or "")
        ):
            raise OutputCoverageMaterializationError(f"Source authority changed: {case_id}")
        scan_path = case_root / f"phase4_output_source_boundary_rescan_{version}.json"
        prior_attempts: dict[str, dict[str, Any]] = {}
        if scan_path.is_file():
            prior_scan = _load(scan_path)
            _verify_self(prior_scan, "rescan_sha256")
            prior_approval_ref = dict(
                dict(prior_scan.get("authority_refs") or {}).get(
                    "decision_approval"
                )
                or {}
            )
            if str(prior_approval_ref.get("sha256") or "") != _sha256_file(
                approval_path
            ):
                raise OutputCoverageMaterializationError(
                    f"Prior boundary rescan approval changed: {case_id}"
                )
            prior_attempts = {
                str(row.get("cluster_id") or ""): dict(row)
                for raw in list(prior_scan.get("attempts") or [])
                if isinstance(raw, Mapping)
                for row in (dict(raw),)
            }
        retry_candidates = [
            row
            for row in candidates
            if not _is_verified_source_status(
                dict(
                    prior_attempts.get(str(row.get("cluster_id") or ""))
                    or {}
                ).get("status")
            )
        ] if retry_failed else []
        if retry_candidates:
            refreshed_attempts, verified = _scan_case(
                case_root=case_root,
                candidates=retry_candidates,
                effective_contract=effective_contract,
                provider=runtime_provider,
                artifact_version=version,
            )
        else:
            refreshed_attempts, verified = [], []
        attempt_by_id = dict(prior_attempts)
        attempt_by_id.update(
            {
                str(row.get("cluster_id") or ""): dict(row)
                for row in refreshed_attempts
            }
        )
        attempts = [
            attempt_by_id[str(row.get("cluster_id") or "")]
            for row in candidates
            if str(row.get("cluster_id") or "") in attempt_by_id
        ]
        verified_count = sum(
            _is_verified_source_status(row.get("status")) for row in attempts
        )
        for attempt in attempts:
            status_counts[str(attempt.get("status") or "UNKNOWN")] += 1
        total_attempts += len(attempts)
        total_verified += verified_count
        scan_artifact: dict[str, Any] = {
            "schema_version": "phase4_output_source_boundary_rescan_v1",
            "status": (
                "SOURCE_BOUNDARY_RESCAN_VERIFIED"
                if verified_count == len(candidates)
                else "SOURCE_BOUNDARY_RESCAN_PARTIAL"
            ),
            "created_at": timestamp,
            "case_id": case_id,
            "operator_id": operator,
            "provider": getattr(runtime_provider, "provider_name", "unknown"),
            "authority_refs": {
                "decision_approval": {
                    "path": f"../{approval_path.name}",
                    "sha256": _sha256_file(approval_path),
                    "approval_sha256": approval.get("approval_sha256"),
                },
                "source_video": {
                    "path": source.name,
                    "sha256": _sha256_file(source),
                },
                "phase4_input": {
                    "path": input_path.name,
                    "sha256": _sha256_file(input_path),
                },
            },
            "counts": {
                "decisions": len(candidates),
                "verified": verified_count,
                "failed_closed": len(candidates) - verified_count,
            },
            "attempts": attempts,
        }
        scan_artifact["rescan_sha256"] = _sha256_json(scan_artifact)
        _write(scan_path, scan_artifact)
        try:
            added_tracks, reused_tracks = _tracks_from_verified(
                verified=verified,
                existing_tracks=list(effective_contract.get("render_tracks") or []),
                fps=float(dict(effective_contract.get("video") or {}).get("fps") or 30.0),
            )
        except RenderPolicyError as exc:
            added_tracks = []
            reused_tracks = []
            scan_artifact["status"] = "SOURCE_BOUNDARY_RESCAN_POLICY_BLOCKED"
            scan_artifact["policy_failure"] = str(exc)
            scan_artifact["rescan_sha256"] = _sha256_json(
                {key: value for key, value in scan_artifact.items() if key != "rescan_sha256"}
            )
            _write(scan_path, scan_artifact)
        active_path = case_root / ACTIVE_POINTER_NAME
        parent_payload: dict[str, Any] = {}
        parent_path: Path | None = None
        if active_path.is_file():
            pointer = _load(active_path)
            ref = dict(pointer.get("active_ref") or {})
            parent_path = (case_root / str(ref.get("path") or "")).resolve()
            if (
                not parent_path.is_relative_to(case_root)
                or not parent_path.is_file()
                or _sha256_file(parent_path) != str(ref.get("sha256") or "")
            ):
                raise OutputCoverageMaterializationError(
                    f"Active visual remediation changed: {case_id}"
                )
            parent_payload = _load(parent_path)
        parent_operations = [
            dict(row)
            for row in list(parent_payload.get("operations") or [])
            if isinstance(row, Mapping)
        ]
        added_operations = [
            {
                "operation": "ADD_TRACK",
                "track": track,
                "expected_added_track_sha256": _sha256_json(track),
                "source_boundary_rescan_ref": {
                    "path": scan_path.name,
                    "rescan_sha256": scan_artifact.get("rescan_sha256"),
                },
            }
            for track in added_tracks
        ]
        operations = _merge_added_track_operations(
            parent_operations,
            added_operations,
        )
        policy_overrides = _micro_ui_reference_overrides(
            [
                *list(effective_contract.get("render_tracks") or []),
                *added_tracks,
            ]
        )
        policy_overrides.extend(
            _output_residual_alignment_overrides(
                reused_tracks,
                [
                    *list(effective_contract.get("render_tracks") or []),
                    *added_tracks,
                ],
            )
        )
        operations.extend(policy_overrides)
        cumulative_added_tracks = sum(
            str(row.get("operation") or "") == "ADD_TRACK" for row in operations
        )
        material_ref = parent_ref
        if added_tracks or policy_overrides:
            material: dict[str, Any] = {
                "schema_version": "phase4_visual_remediation_v1",
                "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
                "created_at": timestamp,
                "case_id": case_id,
                "operator_id": operator,
                "authority_refs": {
                    "phase4_input": {
                        "path": input_path.name,
                        "sha256": _sha256_file(input_path),
                    },
                    "output_residual_decision_approval": {
                        "path": f"../{approval_path.name}",
                        "sha256": _sha256_file(approval_path),
                        "approval_sha256": approval.get("approval_sha256"),
                    },
                    "source_boundary_rescan": {
                        "path": scan_path.name,
                        "sha256": _sha256_file(scan_path),
                        "rescan_sha256": scan_artifact.get("rescan_sha256"),
                    },
                    **(
                        {
                            "parent_visual_remediation": {
                                "path": parent_path.name,
                                "sha256": _sha256_file(parent_path),
                                "materialization_sha256": parent_payload.get("materialization_sha256"),
                            }
                        }
                        if parent_path is not None
                        else {}
                    ),
                },
                "operations": operations,
                "non_goals": [
                    "do_not_overwrite_master_timeline",
                    "do_not_relax_qa_thresholds",
                    "do_not_materialize_failed_source_boundaries",
                ],
            }
            material["materialization_sha256"] = _sha256_json(material)
            material_version = str(approval.get("approval_sha256") or "")[:12]
            rescan_version = str(scan_artifact.get("rescan_sha256") or "")[:12]
            material_path = case_root / (
                f"phase4_visual_remediation_{material_version}_{rescan_version}_output_coverage.json"
            )
            _write(material_path, material)
            pointer = {
                "schema_version": "phase4_visual_remediation_pointer_v1",
                "status": "ACTIVE",
                "active_ref": {
                    "path": material_path.name,
                    "sha256": _sha256_file(material_path),
                    "materialization_sha256": material["materialization_sha256"],
                },
            }
            pointer["pointer_sha256"] = _sha256_json(pointer)
            _write(active_path, pointer)
            material_ref = pointer["active_ref"]
        total_materialized += cumulative_added_tracks
        case_results.append(
            {
                "case_id": case_id,
                "counts": {
                    "decisions": len(candidates),
                    "verified": verified_count,
                    "added_tracks": cumulative_added_tracks,
                    "new_tracks_this_attempt": len(added_tracks),
                    "policy_overrides_this_attempt": len(policy_overrides),
                    "equivalent_existing_tracks_reused": len(reused_tracks),
                    "failed_closed": len(candidates) - verified_count,
                },
                "equivalent_existing_tracks": reused_tracks,
                "rescan_ref": {
                    "path": scan_path.relative_to(run).as_posix(),
                    "sha256": _sha256_file(scan_path),
                    "rescan_sha256": scan_artifact.get("rescan_sha256"),
                },
                "visual_remediation_ref": material_ref,
            }
        )
    expected = int(dict(proposal.get("counts") or {}).get("decisions") or 0) - int(
        dict(dict(proposal.get("counts") or {}).get("actions") or {}).get(FALSE_POSITIVE_ACTION) or 0
    )
    if total_attempts != expected:
        raise OutputCoverageMaterializationError(
            f"Coverage attempt count {total_attempts} does not match approved {expected}"
        )
    index: dict[str, Any] = {
        "schema_version": "phase4_output_coverage_materialization_v1",
        "status": (
            "PHASE4_OUTPUT_COVERAGE_MATERIALIZED"
            if total_verified == expected
            else "PHASE4_OUTPUT_COVERAGE_PARTIAL_FAIL_CLOSED"
        ),
        "created_at": timestamp,
        "operator_id": operator,
        "decision_approval_ref": {
            "path": approval_path.name,
            "sha256": _sha256_file(approval_path),
            "approval_sha256": approval.get("approval_sha256"),
        },
        "provider": getattr(runtime_provider, "provider_name", "unknown"),
        "counts": {
            "cases": len(case_results),
            "approved_coverage_decisions": expected,
            "source_boundary_verified": total_verified,
            "failed_closed": expected - total_verified,
            "added_tracks": total_materialized,
            "attempt_statuses": dict(sorted(status_counts.items())),
        },
        "cases": case_results,
    }
    index["materialization_sha256"] = _sha256_json(index)
    _write(run / output_name, index)
    return index


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.materialize_phase4_output_coverage_decisions"
    )
    parser.add_argument("run_root")
    parser.add_argument("--operator-id", default="operator-user-approved")
    parser.add_argument("--materialized-at")
    parser.add_argument("--no-retry-failed", action="store_true")
    parser.add_argument(
        "--proposal-name",
        default="phase4_output_residual_decision_proposal_v22_8_1.json",
    )
    parser.add_argument(
        "--approval-name",
        default="phase4_output_residual_decision_approval_v22_8_1.json",
    )
    parser.add_argument(
        "--review-name", default="phase4_output_residual_review_v22_8.json"
    )
    parser.add_argument(
        "--false-positive-name",
        default="phase4_output_false_positive_materialization_v22_8_1.json",
    )
    parser.add_argument(
        "--output-name",
        default="phase4_output_coverage_materialization_v22_8_1.json",
    )
    parser.add_argument("--artifact-version", default="v22_8_1")
    args = parser.parse_args()
    try:
        result = materialize(
            run_root=args.run_root,
            operator_id=args.operator_id,
            materialized_at=args.materialized_at
            or datetime.now(timezone.utc).isoformat(),
            retry_failed=not args.no_retry_failed,
            proposal_name=args.proposal_name,
            approval_name=args.approval_name,
            review_name=args.review_name,
            false_positive_name=args.false_positive_name,
            output_name=args.output_name,
            artifact_version=args.artifact_version,
        )
    except (OSError, ValueError, OutputCoverageMaterializationError) as exc:
        print(f"[PHASE4-OUTPUT-COVERAGE][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {"status": result["status"], "counts": result["counts"]},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
