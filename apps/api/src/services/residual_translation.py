"""Temporal residual-CJK normalization and resumable translation support.

The encoded-output QA detector intentionally keeps per-frame evidence.  That
evidence is useful for geometry remediation, but it is the wrong authority for
operator review and translation: a caption visible for fifty frames must not
become fifty review rows or fifty LLM inputs.  This module builds stable
temporal content objects while leaving the original QA artifact immutable.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from pathlib import Path
from statistics import median
from typing import Any


RESIDUAL_NORMALIZATION_VERSION = "residual_temporal_content_v1"
RESIDUAL_TRANSLATION_CACHE_VERSION = "residual_translation_cache_v1"
RESIDUAL_TRANSLATION_PROMPT_VERSION = "residual_ocr_translate_v2"

_SIGNATURE_RE = re.compile(r"[^0-9A-Za-z\u3400-\u4dbf\u4e00-\u9fff]+")
_PROTECTED_PROVENANCE = frozenset(
    {"SOURCE_INTRINSIC", "SOURCE_INTRINSIC_PANEL", "PLATFORM_UI"}
)


def text_signature(value: str) -> str:
    return _SIGNATURE_RE.sub("", str(value or "")).lower()


def _rect(raw: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    try:
        x = float(raw.get("x") or 0.0)
        y = float(raw.get("y") or 0.0)
        width = float(raw.get("width") or 0.0)
        height = float(raw.get("height") or 0.0)
    except (TypeError, ValueError):
        return None
    if width <= 0.0 or height <= 0.0:
        return None
    return x, y, x + width, y + height


def _intersection_over_smaller(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    intersection = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    smaller = min(left_area, right_area)
    return intersection / smaller if smaller > 0.0 else 0.0


def _text_similarity(left: str, right: str) -> float:
    a = text_signature(left)
    b = text_signature(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _can_join_temporal_cluster(
    cluster: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    max_gap_frames: int,
) -> bool:
    frame_index = int(row.get("frame_index") or 0)
    if frame_index - int(cluster.get("end_frame") or 0) > max_gap_frames:
        return False
    row_rect = _rect(dict(row.get("geometry") or {}))
    anchor_rect = cluster.get("anchor_rect")
    if row_rect is None or not isinstance(anchor_rect, tuple):
        return False
    overlap = _intersection_over_smaller(row_rect, anchor_rect)
    if overlap < 0.55:
        return False
    representative = str(cluster.get("representative_text") or "")
    similarity = _text_similarity(representative, str(row.get("text") or ""))
    if similarity >= 0.72:
        return True
    left = text_signature(representative)
    right = text_signature(str(row.get("text") or ""))
    return bool(
        min(len(left), len(right)) >= 4
        and (left in right or right in left)
        and similarity >= 0.62
    )


def _choose_consensus_text(rows: Sequence[Mapping[str, Any]]) -> str:
    texts = [str(row.get("text") or "").strip() for row in rows]
    texts = [value for value in texts if value]
    if not texts:
        return ""
    counts = Counter(texts)
    confidence_by_text: dict[str, list[float]] = {}
    for row in rows:
        text = str(row.get("text") or "").strip()
        if text:
            confidence_by_text.setdefault(text, []).append(
                float(row.get("confidence") or 0.0)
            )

    def score(candidate: str) -> tuple[float, int, float, int]:
        support = int(counts[candidate])
        mean_confidence = sum(confidence_by_text[candidate]) / max(
            1, len(confidence_by_text[candidate])
        )
        consensus = sum(
            _text_similarity(candidate, other) * count
            for other, count in counts.items()
        ) / max(1, sum(counts.values()))
        # Frequency is authority; confidence and agreement break close OCR ties.
        return (
            support * 2.0 + mean_confidence + consensus,
            support,
            mean_confidence,
            len(text_signature(candidate)),
        )

    return max(counts, key=score)


def _median_geometry(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    geometries = [
        dict(row.get("geometry") or {})
        for row in rows
        if _rect(dict(row.get("geometry") or {})) is not None
    ]
    if not geometries:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    return {
        key: float(median(float(row.get(key) or 0.0) for row in geometries))
        for key in ("x", "y", "width", "height")
    }


def _protected_track_rows(
    protected_tracks: Sequence[Mapping[str, Any]],
    *,
    frame_width: int,
    frame_height: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in protected_tracks:
        row = dict(raw)
        provenance = dict(row.get("visual_provenance") or {})
        classification = str(provenance.get("classification") or "").upper()
        action = str(row.get("action") or "").upper()
        if classification not in _PROTECTED_PROVENANCE and action != "PRESERVE_SOURCE_PIXELS":
            continue
        coords = list(row.get("box_coords") or [])
        if len(coords) != 4 or frame_width <= 0 or frame_height <= 0:
            continue
        try:
            geometry = {
                "x": float(coords[0]) / frame_width,
                "y": float(coords[1]) / frame_height,
                "width": (float(coords[2]) - float(coords[0])) / frame_width,
                "height": (float(coords[3]) - float(coords[1])) / frame_height,
            }
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if _rect(geometry) is None:
            continue
        rows.append(
            {
                "text_id": str(row.get("text_id") or ""),
                "start_frame": int(row.get("start_frame") or 0),
                "end_frame": int(row.get("end_frame") or row.get("start_frame") or 0),
                "geometry": geometry,
                "classification": classification or "SOURCE_INTRINSIC",
            }
        )
    return rows


def _protected_match(
    content: Mapping[str, Any], protected_rows: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    content_rect = _rect(dict(content.get("geometry") or {}))
    if content_rect is None:
        return None
    start = int(content.get("start_frame") or 0)
    end = int(content.get("end_frame") or start)
    for protected in protected_rows:
        p_start = int(protected.get("start_frame") or 0)
        p_end = int(protected.get("end_frame") or p_start)
        if end + 2 < p_start or p_end + 2 < start:
            continue
        protected_rect = _rect(dict(protected.get("geometry") or {}))
        if protected_rect is None:
            continue
        if _intersection_over_smaller(content_rect, protected_rect) >= 0.70:
            return protected
    return None


def normalize_residual_detections(
    detections: Sequence[Mapping[str, Any]],
    *,
    protected_tracks: Sequence[Mapping[str, Any]] = (),
    frame_width: int = 0,
    frame_height: int = 0,
    image_paths: Sequence[str] = (),
    max_gap_frames: int = 6,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return review-sized temporal objects plus a normalization audit.

    Raw detections remain untouched in the Phase-4 QA artifact.  Source-intrinsic
    overlaps are omitted from localization review, but recorded in the audit.
    """

    ordered = sorted(
        [dict(row) for row in detections if isinstance(row, Mapping)],
        key=lambda row: int(row.get("frame_index") or 0),
    )
    # Backward-compatible authority for old/preflight fixtures that predate
    # geometry emission. Real encoded-output QA rows carry normalized boxes;
    # without them there is no safe temporal/provenance join to perform.
    if ordered and all(
        _rect(dict(row.get("geometry") or {})) is None for row in ordered
    ):
        legacy_rows: list[dict[str, Any]] = []
        for index, row in enumerate(ordered):
            if not text_signature(str(row.get("text") or "")):
                continue
            legacy = dict(row)
            legacy["content_id"] = f"residual_{index + 1:03d}"
            legacy["image_path"] = (
                str(image_paths[min(index, len(image_paths) - 1)])
                if image_paths
                else None
            )
            legacy_rows.append(legacy)
        return legacy_rows, {
            "version": RESIDUAL_NORMALIZATION_VERSION,
            "raw_detection_count": len(ordered),
            "temporal_content_count": len(legacy_rows),
            "review_content_count": len(legacy_rows),
            "protected_source_content_count": 0,
            "deduplicated_frame_rows": 0,
            "geometry_authority_missing": True,
        }
    clusters: list[dict[str, Any]] = []
    for row in ordered:
        text = str(row.get("text") or "").strip()
        geometry = dict(row.get("geometry") or {})
        if not text_signature(text) or _rect(geometry) is None:
            continue
        matched: dict[str, Any] | None = None
        # Only recent clusters can accept a frame, keeping repeated captions in
        # separate temporal occurrences while tolerating brief detector gaps.
        for cluster in reversed(clusters[-12:]):
            if _can_join_temporal_cluster(
                cluster, row, max_gap_frames=max(1, int(max_gap_frames))
            ):
                matched = cluster
                break
        if matched is None:
            clusters.append(
                {
                    "start_frame": int(row.get("frame_index") or 0),
                    "end_frame": int(row.get("frame_index") or 0),
                    "anchor_rect": _rect(geometry),
                    "representative_text": text,
                    "rows": [row],
                }
            )
        else:
            matched["rows"].append(row)
            matched["end_frame"] = int(row.get("frame_index") or 0)
            matched["representative_text"] = _choose_consensus_text(matched["rows"])
            median_geometry = _median_geometry(matched["rows"])
            matched["anchor_rect"] = _rect(median_geometry)

    protected_rows = _protected_track_rows(
        protected_tracks, frame_width=frame_width, frame_height=frame_height
    )
    review: list[dict[str, Any]] = []
    protected_count = 0
    for cluster in clusters:
        rows = list(cluster["rows"])
        text = _choose_consensus_text(rows)
        geometry = _median_geometry(rows)
        start_frame = int(cluster["start_frame"])
        end_frame = int(cluster["end_frame"])
        representative = max(
            (row for row in rows if str(row.get("text") or "").strip() == text),
            key=lambda row: float(row.get("confidence") or 0.0),
            default=max(rows, key=lambda row: float(row.get("confidence") or 0.0)),
        )
        # A lone, low-confidence glyph with no adjacent-frame confirmation is
        # OCR noise, not a temporal text object. Output QA keeps it as raw
        # fail-closed evidence, but translation/proposal review must not turn
        # it into a real subtitle. A high-confidence one-frame flash remains
        # reviewable and therefore is not removed by this guard.
        temporal_confirmed = any(
            str(dict(row.get("temporal_confirmation") or {}).get("status") or "")
            == "CONFIRMED_ON_ADJACENT_FRAME"
            for row in rows
        )
        mean_confidence = sum(
            float(row.get("confidence") or 0.0) for row in rows
        ) / max(1, len(rows))
        if len(rows) == 1 and not temporal_confirmed and mean_confidence < 0.50:
            continue
        identity = hashlib.sha256(
            json.dumps(
                {
                    "version": RESIDUAL_NORMALIZATION_VERSION,
                    "text": text_signature(text),
                    "start": start_frame,
                    "end": end_frame,
                    "geometry": {key: round(value, 4) for key, value in geometry.items()},
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        content: dict[str, Any] = {
            "content_id": f"residual_content_{identity}",
            "frame_index": int(representative.get("frame_index") or start_frame),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "text": text,
            "confidence": round(
                mean_confidence,
                6,
            ),
            "geometry": geometry,
            "detection_count": len(rows),
            "text_variants": [
                {"text": value, "count": count}
                for value, count in Counter(
                    str(row.get("text") or "").strip() for row in rows
                ).most_common(8)
                if value
            ],
            "temporal_confirmation": dict(
                representative.get("temporal_confirmation") or {}
            ),
            "normalization_version": RESIDUAL_NORMALIZATION_VERSION,
            "image_path": None,
        }
        if image_paths:
            # QA currently supplies a bounded evidence list rather than a
            # frame→path map.  Use the nearest stable ordinal only as a preview;
            # it is never an authority input.
            ordinal = min(len(image_paths) - 1, len(review))
            content["image_path"] = str(image_paths[ordinal])
        protected = _protected_match(content, protected_rows)
        if protected is not None:
            protected_count += 1
            continue
        review.append(content)

    audit = {
        "version": RESIDUAL_NORMALIZATION_VERSION,
        "raw_detection_count": len(ordered),
        "temporal_content_count": len(clusters),
        "review_content_count": len(review),
        "protected_source_content_count": protected_count,
        "deduplicated_frame_rows": max(0, len(ordered) - len(review)),
    }
    return review, audit


def translation_authority_suggestions(
    residual_objects: Sequence[Mapping[str, Any]],
    phase3_objects: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Reuse only strong, approved Phase-3 text authority matches."""

    approved: list[tuple[str, str]] = []
    for raw in phase3_objects:
        row = dict(raw)
        zh = str(row.get("zh_approved") or row.get("translation_input") or "").strip()
        vi = str(row.get("vi_text_approved") or row.get("vi_text_candidate") or "").strip()
        status = str(row.get("review_status") or "").upper()
        if zh and vi and (not status or "APPROVED" in status or "DETERMINISTIC" in status):
            approved.append((zh, vi))

    suggestions: list[dict[str, str]] = []
    for raw in residual_objects:
        row = dict(raw)
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        ranked = sorted(
            ((_text_similarity(text, zh), zh, vi) for zh, vi in approved),
            reverse=True,
        )
        if not ranked:
            continue
        similarity, zh, vi = ranked[0]
        left = text_signature(text)
        right = text_signature(zh)
        strong_containment = (
            min(len(left), len(right)) >= 5
            and (left in right or right in left)
            and similarity >= 0.84
        )
        if similarity < 0.92 and not strong_containment:
            continue
        suggestions.append(
            {
                "content_id": str(row.get("content_id") or ""),
                "ocr_text": text,
                "ocr_text_corrected": zh,
                "vi_text_suggested": vi,
                "suggestion_source": "phase3_approved_authority",
            }
        )
    return suggestions


def translation_cache_key(
    *,
    text: str,
    model_name: str,
    base_url: str,
    system_prompt: str,
) -> str:
    payload = {
        "version": RESIDUAL_TRANSLATION_PROMPT_VERSION,
        "text": str(text or "").strip(),
        "target": "vi",
        "model": str(model_name or ""),
        "base_url": str(base_url or "").rstrip("/"),
        "system_prompt_sha256": hashlib.sha256(
            str(system_prompt or "").encode("utf-8")
        ).hexdigest(),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def load_translation_cache(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {"schema_version": RESIDUAL_TRANSLATION_CACHE_VERSION, "entries": {}}
    candidate = Path(path)
    if not candidate.is_file():
        return {"schema_version": RESIDUAL_TRANSLATION_CACHE_VERSION, "entries": {}}
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": RESIDUAL_TRANSLATION_CACHE_VERSION, "entries": {}}
    if not isinstance(payload, dict) or payload.get("schema_version") != RESIDUAL_TRANSLATION_CACHE_VERSION:
        return {"schema_version": RESIDUAL_TRANSLATION_CACHE_VERSION, "entries": {}}
    payload["entries"] = dict(payload.get("entries") or {})
    return payload


def write_translation_cache(path: str | Path | None, payload: Mapping[str, Any]) -> None:
    if path is None:
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(destination)


def partition_translation_batches(
    items: Sequence[tuple[str, str]],
    *,
    max_items: int = 12,
    max_utf8_bytes: int = 6_000,
) -> list[list[tuple[str, str]]]:
    batches: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_bytes = 2
    for item in items:
        estimated = len(
            json.dumps(
                {item[0]: {"ocr_text": item[1], "context": "short-video overlay"}},
                ensure_ascii=False,
            ).encode("utf-8")
        )
        if current and (
            len(current) >= max(1, int(max_items))
            or current_bytes + estimated > max(256, int(max_utf8_bytes))
        ):
            batches.append(current)
            current = []
            current_bytes = 2
        current.append(item)
        current_bytes += estimated
    if current:
        batches.append(current)
    return batches
