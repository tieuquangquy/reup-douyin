"""Bounded local OCR recovery for editor tracks missed by the primary pass."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np


PHASE2_LOCAL_RECOVERY_POLICY_VERSION = "phase2_local_temporal_recovery_v1"
PHASE2_HARDSUB_GEOMETRY_POLICY_VERSION = "phase2_hardsub_geometry_recovery_v1"
PHASE2_TEMPORAL_SHADOW_POLICY_VERSION = "phase2_temporal_shadow_reconcile_v1"
PHASE2_LOCAL_RECOVERY_MAX_FRAMES = 2
PHASE2_LOCAL_RECOVERY_TARGET_HEIGHT = 112
_SIGNATURE_RE = re.compile(r"[0-9A-Za-z%+.\-\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


@dataclass(frozen=True)
class RecoveryObservation:
    track_index: int
    frame_index: int
    variant: str
    text: str
    sharpness: float
    box_xyxy: tuple[float, float, float, float] | None = None
    geometry_score: float = 0.0


def _track_text(row: Mapping[str, Any]) -> str:
    return str(
        row.get("ocr_text_raw")
        or row.get("ocr_text")
        or row.get("text")
        or ""
    ).strip()


def _frame_span(row: Mapping[str, Any]) -> tuple[int, int]:
    try:
        start = int(row.get("start_frame") or 0)
        end = int(row.get("end_frame") or start)
    except (TypeError, ValueError):
        return (0, 0)
    return (min(start, end), max(start, end))


def reconcile_temporal_shadow_tracks(
    timeline: Sequence[Mapping[str, Any]],
    *,
    frame_width: int,
    frame_height: int,
    fps: float,
    max_duration_seconds: float = 0.75,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop empty, short detector shadows already covered by a strong caption.

    Phase 1 can produce a short second box during a caption transition.  If the
    candidate has no OCR text, is fully contained by a longer caption, and its
    geometry is materially outside that caption lane, it cannot safely become a
    new editor object.  The longer caption remains the only authority and the
    dropped row is retained in an audit list.  This is deliberately limited to
    empty tracks so a real, independently recognized line is never discarded.
    """
    rows = [dict(row) for row in timeline]
    if not rows:
        return rows, []
    width = max(1.0, float(frame_width))
    height = max(1.0, float(frame_height))
    short_frames = max(2, int(round(max(0.1, float(max_duration_seconds)) * max(1.0, float(fps)))))
    audit: list[dict[str, Any]] = []
    drop_ids: set[str] = set()

    for index, candidate in enumerate(rows):
        candidate_id = str(candidate.get("text_id") or f"sub_{index + 1:02d}")
        if _track_text(candidate):
            continue
        start, end = _frame_span(candidate)
        span = end - start + 1
        if span > short_frames:
            continue
        candidate_box = list(candidate.get("box_coords") or [])
        if len(candidate_box) < 4:
            continue
        cx = (float(candidate_box[0]) + float(candidate_box[2])) * 0.5
        cy = (float(candidate_box[1]) + float(candidate_box[3])) * 0.5
        candidate_height = max(1.0, float(candidate_box[3]) - float(candidate_box[1]))

        hosts: list[tuple[tuple[Any, ...], Mapping[str, Any]]] = []
        for host_index, host in enumerate(rows):
            if host_index == index:
                continue
            host_text = _track_text(host)
            if not host_text:
                continue
            host_start, host_end = _frame_span(host)
            overlap = max(0, min(end, host_end) - max(start, host_start) + 1)
            if overlap / float(span) < 0.90 or host_start > start or host_end < end:
                continue
            host_box = list(host.get("box_coords") or [])
            if len(host_box) < 4:
                continue
            host_width = max(1.0, float(host_box[2]) - float(host_box[0]))
            host_height = max(1.0, float(host_box[3]) - float(host_box[1]))
            if host_width / width < 0.35 or host_height / height > 0.08:
                continue
            hx = (float(host_box[0]) + float(host_box[2])) * 0.5
            hy = (float(host_box[1]) + float(host_box[3])) * 0.5
            centre_distance = ((cx - hx) ** 2 + (cy - hy) ** 2) ** 0.5
            if centre_distance <= max(3.0 * host_height, 0.035 * height):
                continue
            host_span = host_end - host_start + 1
            hosts.append(
                (
                    (
                        int(host.get("hit_count") or 0),
                        host_span,
                        round(host_width / width, 4),
                        round(overlap / float(span), 4),
                    ),
                    host,
                )
            )
        if not hosts:
            continue
        _, host = max(hosts, key=lambda item: item[0])
        host_id = str(host.get("text_id") or "")
        host_text = _track_text(host)
        candidate["temporal_shadow_reconcile"] = {
            "policy_version": PHASE2_TEMPORAL_SHADOW_POLICY_VERSION,
            "status": "PURGED_REDUNDANT_TEMPORAL_SHADOW",
            "shadow_text_id": candidate_id,
            "host_text_id": host_id,
            "host_text": host_text,
            "reason": "empty_short_track_temporally_contained_outside_dominant_caption_lane",
        }
        drop_ids.add(candidate_id)
        audit.append(dict(candidate["temporal_shadow_reconcile"]))

    return [row for row in rows if str(row.get("text_id") or "") not in drop_ids], audit


def recovery_signature(text: str) -> str:
    """Normalize presentation punctuation without attempting language correction."""
    return "".join(_SIGNATURE_RE.findall(str(text or ""))).lower()


def recovery_frame_indices(
    entry: Mapping[str, Any],
    *,
    max_frames: int = PHASE2_LOCAL_RECOVERY_MAX_FRAMES,
) -> list[int]:
    """Choose a sharpness-friendly, temporally diverse bounded frame set."""
    start = int(entry.get("start_frame") or 0)
    end = max(start, int(entry.get("end_frame") or start))
    mid = start + (end - start) // 2
    raw_best = entry.get("best_frame_index")
    try:
        best = int(raw_best) if raw_best is not None else mid
    except (TypeError, ValueError):
        best = mid
    hits = sorted(
        {
            max(start, min(end, int(value)))
            for value in list(entry.get("hit_frames") or [])
            if str(value).strip()
        }
    )
    ordered = [best]
    if hits:
        ordered.extend((hits[0], hits[len(hits) // 2], hits[-1]))
    ordered.extend((mid, start, end))
    unique = list(dict.fromkeys(max(start, min(end, value)) for value in ordered))
    return unique[: max(1, int(max_frames))]


def decode_selected_frames(
    video_path: str | Path,
    frame_indices: Sequence[int],
) -> dict[int, np.ndarray]:
    """Decode all requested frames with one VideoCapture lifecycle."""
    wanted = sorted({max(0, int(value)) for value in frame_indices})
    if not wanted:
        return {}
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {}
    decoded: dict[int, np.ndarray] = {}
    try:
        for frame_index in wanted:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = cap.read()
            if ok and frame is not None and frame.size > 0:
                decoded[frame_index] = frame
    finally:
        cap.release()
    return decoded


def expanded_recovery_box(
    box_xyxy: Sequence[float],
    *,
    frame_width: int,
    frame_height: int,
) -> list[int]:
    """Expand only the recognition crop; downstream geometry remains untouched."""
    x0, y0, x1, y1 = (float(value) for value in box_xyxy[:4])
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    pad_x = max(4.0, min(32.0, width * 0.025))
    pad_y = max(6.0, min(48.0, height * 0.30))
    return [
        max(0, int(round(x0 - pad_x))),
        max(0, int(round(y0 - pad_y))),
        min(int(frame_width), int(round(x1 + pad_x))),
        min(int(frame_height), int(round(y1 + pad_y))),
    ]


def crop_recovery_region(
    frame_bgr: np.ndarray,
    box_xyxy: Sequence[float],
) -> np.ndarray | None:
    height, width = frame_bgr.shape[:2]
    x0, y0, x1, y1 = expanded_recovery_box(
        box_xyxy,
        frame_width=int(width),
        frame_height=int(height),
    )
    if x1 <= x0 or y1 <= y0:
        return None
    crop = frame_bgr[y0:y1, x0:x1]
    return crop if crop.size > 0 else None


def hardsub_geometry_candidates(
    frame_bgr: np.ndarray,
    box_xyxy: Sequence[float],
    *,
    max_candidates: int = 4,
    vertical_search_frac: float = 0.14,
) -> list[dict[str, Any]]:
    """Find a few deterministic text-line boxes near a failed hardsub box.

    Phase 1 event scanning may retain the wrong horizontal line when a source UI
    panel sits immediately above/below a burn-in subtitle.  This pass searches
    only a bounded vertical neighbourhood and a bounded horizontal corridor;
    it never changes the Phase 1 artifact.  The score is intentionally based on
    local stroke/edge projections rather than a recognizer, so geometry recovery
    remains local and cheap and can fail closed when the scene is ambiguous.
    """
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return []
    height, width = frame_bgr.shape[:2]
    if len(box_xyxy) < 4 or width < 8 or height < 8:
        return []
    x0, y0, x1, y1 = (float(value) for value in box_xyxy[:4])
    if x1 <= x0 or y1 <= y0:
        return []
    prior_w = max(16.0, x1 - x0)
    prior_h = max(12.0, y1 - y0)
    # Keep the search local to the suspected line; the wider X corridor handles
    # partial detector boxes without turning this into a full-frame OCR pass.
    sx0 = max(0, int(round(x0 - 0.85 * prior_w)))
    sx1 = min(width, int(round(x1 + 0.85 * prior_w)))
    if sx1 - sx0 < max(80, int(1.4 * prior_w)):
        sx0, sx1 = 0, width
    half = max(72.0, min(720.0, float(height) * float(vertical_search_frac)))
    sy0 = max(0, int(round((y0 + y1) * 0.5 - half)))
    sy1 = min(height, int(round((y0 + y1) * 0.5 + half)))
    if sy1 - sy0 < 24:
        return []

    gray = cv2.cvtColor(frame_bgr[sy0:sy1, sx0:sx1], cv2.COLOR_BGR2GRAY)
    # CJK subtitles are generally outlined/fill text.  Combining gradients and
    # a blackhat/tophat response is more stable than a single global threshold
    # on skin, hair, or bright UI backgrounds.
    blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
    gx = np.abs(cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3))
    gy = np.abs(cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3))
    edge = np.clip((gx + gy) / 255.0, 0.0, 8.0)
    local = cv2.morphologyEx(
        blur,
        cv2.MORPH_BLACKHAT,
        cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (max(9, int(prior_h)), max(5, int(prior_h // 2))),
        ),
    )
    ink = np.clip(local.astype(np.float32) / 64.0, 0.0, 8.0)
    signal = 0.72 * edge + 0.28 * ink
    row_score = signal.mean(axis=1).astype(np.float32)
    smooth_k = max(5, int(round(prior_h * 0.42)) | 1)
    row_score = cv2.GaussianBlur(row_score.reshape(-1, 1), (1, smooth_k), 0).ravel()
    if not np.isfinite(row_score).any() or float(np.max(row_score)) <= 0.0:
        return []
    # Local maxima with a conservative percentile gate.  The prior centre gets a
    # small bonus only as a tie-breaker; it must not force the old wrong box.
    threshold = max(float(np.percentile(row_score, 66.0)), float(np.max(row_score)) * 0.36)
    maxima: list[tuple[float, int]] = []
    for index in range(1, len(row_score) - 1):
        value = float(row_score[index])
        if value < threshold or value < float(row_score[index - 1]) or value < float(row_score[index + 1]):
            continue
        maxima.append((value, index))
    maxima.sort(key=lambda item: (-item[0], abs((sy0 + item[1]) - (y0 + y1) * 0.5)))
    selected: list[dict[str, Any]] = []
    min_sep = max(10.0, prior_h * 0.70)
    target_h = max(48.0, min(220.0, prior_h * 1.85))
    for score, local_y in maxima:
        center_y = float(sy0 + local_y)
        if any(abs(center_y - float(row["box_xyxy"][1] + row["box_xyxy"][3]) * 0.5) < min_sep for row in selected):
            continue
        cy0 = max(0.0, center_y - target_h * 0.5)
        cy1 = min(float(height), center_y + target_h * 0.5)
        # Tighten X to the connected stroke run around this line.  This is what
        # prevents a successful OCR recovery from later blurring an entire
        # phone panel or the full bottom band.
        band_y0 = max(0, int(round(center_y - target_h * 0.62)) - sy0)
        band_y1 = min(signal.shape[0], int(round(center_y + target_h * 0.62)) - sy0)
        column_score = signal[band_y0:band_y1].mean(axis=0)
        x_threshold = max(
            float(np.percentile(column_score, 68.0)),
            float(np.max(column_score)) * 0.24,
        )
        column_mask = (column_score >= x_threshold).astype(np.uint8)[None, :]
        close_width = max(9, int(round(prior_h * 0.60)))
        column_mask = cv2.morphologyEx(
            column_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (close_width, 1)),
        ).ravel()
        runs: list[tuple[int, int, float]] = []
        run_start: int | None = None
        for column, active in enumerate(np.r_[column_mask, 0]):
            if active and run_start is None:
                run_start = column
            elif not active and run_start is not None:
                if column - run_start >= max(24, int(prior_w * 0.30)):
                    runs.append(
                        (
                            run_start,
                            column - 1,
                            float(column_score[run_start:column].sum()),
                        )
                    )
                run_start = None
        if runs:
            run_x0, run_x1, _run_score = max(
                runs,
                key=lambda row: (
                    row[2],
                    -abs((sx0 + row[0] + row[1]) * 0.5 - (x0 + x1) * 0.5),
                ),
            )
            x_pad = max(8.0, min(30.0, prior_h * 0.16))
            candidate_x0 = max(float(sx0), float(sx0 + run_x0) - x_pad)
            candidate_x1 = min(float(sx1), float(sx0 + run_x1) + x_pad)
        else:
            candidate_x0, candidate_x1 = float(sx0), float(sx1)
        candidate = {
            "box_xyxy": [candidate_x0, cy0, candidate_x1, cy1],
            "score": round(float(score), 6),
            "search_box": [int(sx0), int(sy0), int(sx1), int(sy1)],
        }
        selected.append(candidate)
        if len(selected) >= max(1, int(max_candidates)):
            break
    return selected


def recovery_sharpness(image_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _resize_to_target(image_bgr: np.ndarray, target_height: int) -> np.ndarray:
    height, width = image_bgr.shape[:2]
    target = max(int(target_height), int(height))
    scale = target / max(1.0, float(height))
    if abs(scale - 1.0) < 0.01:
        return image_bgr.copy()
    return cv2.resize(
        image_bgr,
        (max(1, int(round(width * scale))), target),
        interpolation=cv2.INTER_CUBIC,
    )


def _pad(image_bgr: np.ndarray, value: int) -> np.ndarray:
    vertical = max(12, int(round(image_bgr.shape[0] * 0.16)))
    horizontal = max(12, int(round(image_bgr.shape[0] * 0.10)))
    return cv2.copyMakeBorder(
        image_bgr,
        vertical,
        vertical,
        horizontal,
        horizontal,
        cv2.BORDER_CONSTANT,
        value=(value, value, value),
    )


def recovery_variants(
    crop_bgr: np.ndarray,
    *,
    target_height: int = PHASE2_LOCAL_RECOVERY_TARGET_HEIGHT,
) -> list[tuple[str, np.ndarray]]:
    """Three complementary, deterministic variants for stylized editor text."""
    raw = _resize_to_target(crop_bgr, target_height)
    lab = cv2.cvtColor(raw, cv2.COLOR_BGR2LAB)
    light, channel_a, channel_b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(light)
    contrast = cv2.cvtColor(
        cv2.merge((clahe, channel_a, channel_b)),
        cv2.COLOR_LAB2BGR,
    )
    blurred = cv2.GaussianBlur(raw, (0, 0), 1.1)
    sharpened = cv2.addWeighted(raw, 1.8, blurred, -0.8, 0)
    return [
        ("expanded_raw_bpad", _pad(raw, 0)),
        ("expanded_clahe_wpad", _pad(contrast, 255)),
        ("expanded_unsharp_bpad", _pad(sharpened, 0)),
    ]


def choose_recovery_consensus(
    observations: Sequence[RecoveryObservation],
) -> dict[str, Any] | None:
    """Vote by normalized text, distinct frames, variants, and source sharpness."""
    usable = [row for row in observations if recovery_signature(row.text)]
    if not usable:
        return None
    grouped: dict[str, list[RecoveryObservation]] = defaultdict(list)
    for row in usable:
        grouped[recovery_signature(row.text)].append(row)

    def _group_key(item: tuple[str, list[RecoveryObservation]]) -> tuple:
        signature, rows = item
        frames = {row.frame_index for row in rows}
        variants = {row.variant for row in rows}
        cjk = sum(1 for char in signature if "\u3400" <= char <= "\u9fff")
        return (
            len(frames),
            len(rows),
            len(variants),
            cjk,
            len(signature),
            round(float(np.mean([row.geometry_score for row in rows])), 6),
            max(row.sharpness for row in rows),
        )

    signature, winners = max(grouped.items(), key=_group_key)
    representative = max(
        winners,
        key=lambda row: (
            len(recovery_signature(row.text)),
            row.sharpness,
            row.text,
        ),
    )
    frame_support = len({row.frame_index for row in winners})
    variant_support = len({row.variant for row in winners})
    boxes = [row.box_xyxy for row in winners if row.box_xyxy and len(row.box_xyxy) >= 4]
    selected_box: list[float] | None = None
    if boxes:
        selected_box = [
            round(float(np.median([box[index] for box in boxes])), 2)
            for index in range(4)
        ]
    geometry_support = len(
        {
            tuple(round(float(value), 1) for value in box[:4])
            for box in boxes
        }
    )
    if frame_support >= 2:
        method = "temporal_consensus"
        confidence = min(0.99, 0.78 + 0.06 * frame_support + 0.02 * variant_support)
    elif variant_support >= 2:
        method = "variant_consensus"
        confidence = min(0.88, 0.70 + 0.05 * variant_support)
    else:
        method = "best_effort_operator_review"
        confidence = 0.58
    return {
        "text": representative.text,
        "signature": signature,
        "method": method,
        "confidence": round(float(confidence), 3),
        "frame_support": frame_support,
        "variant_support": variant_support,
        "observation_count": len(winners),
        "selected_frame": representative.frame_index,
        "selected_variant": representative.variant,
        "selected_box": selected_box,
        "geometry_observation_count": len(boxes),
        "geometry_support": geometry_support,
    }


def repeated_recovered_source_ui_indices(
    timeline: Sequence[Mapping[str, Any]],
    *,
    frame_width: int,
    frame_height: int,
) -> set[int]:
    """Fail closed on a short, stable UI label repeated across separate scenes."""
    width = max(1.0, float(frame_width))
    height = max(1.0, float(frame_height))
    groups: dict[str, list[int]] = defaultdict(list)
    for index, raw in enumerate(timeline):
        recovery = dict(raw.get("ocr_recovery") or {})
        if recovery.get("status") != "RECOVERED_FOR_OPERATOR_REVIEW":
            continue
        signature = recovery_signature(str(raw.get("ocr_text") or ""))
        cjk = sum(1 for char in signature if "\u3400" <= char <= "\u9fff")
        box = list(raw.get("box_coords") or [])
        if len(box) < 4 or cjk < 1 or cjk > 4 or len(signature) > 6:
            continue
        box_width = max(1.0, float(box[2]) - float(box[0])) / width
        box_height = max(1.0, float(box[3]) - float(box[1])) / height
        center_y = (float(box[1]) + float(box[3])) * 0.5 / height
        if box_width > 0.26 or box_height > 0.065 or center_y < 0.45:
            continue
        groups[signature].append(index)

    protected: set[int] = set()
    for indices in groups.values():
        if len(indices) < 2:
            continue
        starts = [int(timeline[index].get("start_frame") or 0) for index in indices]
        ends = [int(timeline[index].get("end_frame") or 0) for index in indices]
        if max(ends) - min(starts) < 30:
            continue
        for left_pos, left_index in enumerate(indices):
            left_box = list(timeline[left_index].get("box_coords") or [])
            for right_index in indices[left_pos + 1 :]:
                right_box = list(timeline[right_index].get("box_coords") or [])
                intersection_x = max(
                    0.0,
                    min(float(left_box[2]), float(right_box[2]))
                    - max(float(left_box[0]), float(right_box[0])),
                )
                intersection_y = max(
                    0.0,
                    min(float(left_box[3]), float(right_box[3]))
                    - max(float(left_box[1]), float(right_box[1])),
                )
                intersection = intersection_x * intersection_y
                left_area = max(1.0, float(left_box[2]) - float(left_box[0])) * max(
                    1.0, float(left_box[3]) - float(left_box[1])
                )
                right_area = max(
                    1.0, float(right_box[2]) - float(right_box[0])
                ) * max(1.0, float(right_box[3]) - float(right_box[1]))
                iou = intersection / max(1.0, left_area + right_area - intersection)
                if iou >= 0.72:
                    protected.update((left_index, right_index))
    return protected
