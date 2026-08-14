"""Fail-closed bridge from approved Phase 2+3 artifacts to Phase 4 render tracks."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.media_pipeline.video_renderer.fonts import resolve_drawtext_font
from src.media_pipeline.video_renderer.overlays import OverlaySegment, gate_vi_for_burn
from src.media_pipeline.video_renderer.render_policy import enrich_phase4_render_policies
from src.media_pipeline.video_renderer.render_policy import select_text_render_tracks
from src.media_pipeline.video_renderer.render_runtime import (
    ViGlyphCache,
    plan_vi_placements,
    resolve_vi_font_size_for_kind,
)

PHASE4_INPUT_SCHEMA_VERSION = "phase4_render_input_v1"
PHASE4_PREFLIGHT_SCHEMA_VERSION = "phase4_render_preflight_v1"
PHASE4_TIMING_NORMALIZATION_POLICY_VERSION = "transition_boundary_v2"


class Phase4InputError(RuntimeError):
    """Approved artifacts cannot be mapped safely into render tracks."""


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


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4InputError(f"Cannot read valid {path.name}") from exc


def _pixel_bound_residual_suppressions(
    root: Path, remediation: Mapping[str, Any]
) -> tuple[list[str], list[dict[str, Any]]]:
    """Reject residual OCR that has no text-like pixels in its bound crop.

    Output OCR may hallucinate a CJK glyph on skin, cloth, or compression
    texture while the full-frame recognizer is highly confident.  A crop hash
    supplied by the remediation authority is the narrowest local evidence we
    have; a low-contrast crop with no dark text strokes is therefore a
    deterministic source-bound false positive, not a translation object.
    """

    try:
        import cv2
        import numpy as np
    except Exception:
        return [], []
    suppressed: list[str] = []
    audit: list[dict[str, Any]] = []
    rows = [
        dict(row)
        for row in [
            *list(remediation.get("approved_occurrences") or []),
            *list(remediation.get("approved_geometry_overrides") or []),
        ]
        if isinstance(row, Mapping)
    ]
    for row in rows:
        occurrence = dict(row.get("occurrence") or {})
        text_id = str(occurrence.get("text_id") or row.get("remediation_id") or "")
        crop_ref = dict(dict(row.get("visual_override") or {}).get("crop_ref") or {})
        crop_path = (root / str(crop_ref.get("path") or "")).resolve()
        if (
            not text_id
            or not crop_path.is_file()
            or not crop_path.is_relative_to(root)
            or len(str(crop_ref.get("sha256") or "")) != 64
            or _sha256_file(crop_path) != str(crop_ref.get("sha256") or "")
        ):
            continue
        image = cv2.imread(str(crop_path), cv2.IMREAD_GRAYSCALE)
        if image is None or image.size == 0:
            continue
        dark_fraction = float(np.mean(image < 60))
        contrast = float(np.std(image))
        if contrast >= 24.0 or dark_fraction >= 0.015:
            continue
        suppressed.append(text_id)
        audit.append(
            {
                "text_id": text_id,
                "classification": "SOURCE_BOUND_PIXEL_FALSE_POSITIVE",
                "contrast_std": round(contrast, 4),
                "dark_pixel_fraction": round(dark_fraction, 6),
                "crop_ref": {
                    "path": crop_path.relative_to(root).as_posix(),
                    "sha256": crop_ref.get("sha256"),
                },
            }
        )
    return sorted(set(suppressed)), audit


def _source_bound_empty_transition_suppressions(
    root: Path,
    master: Mapping[str, Mapping[str, Any]],
    enrichments: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Suppress OCR-empty transition boxes that are demonstrably filmed texture.

    High-recall Phase 1 is allowed to over-detect, but a ``TRANSITION_NOISE``
    row must not become an automatic blur authority merely because its box is
    screen locked.  Hat eyelets, eyes, hair and skin are particularly common
    DBNet false positives.  The Phase 2 recovery result and the hash-bound crop
    provide a local, deterministic veto: no decoded text, no accepted recovery
    observation, and a crop without caption-like edge energy means there is no
    editor glyph to conceal.

    The thresholds intentionally preserve dark/bright text: even compact CJK
    has either substantial Laplacian energy or meaningful high-pass response.
    Smooth material and facial regions remain far below both bounds.
    """

    try:
        import cv2
        import numpy as np
    except Exception:
        return [], []

    suppressed: list[str] = []
    audit: list[dict[str, Any]] = []
    for text_id, enrichment in enrichments.items():
        semantic = dict(enrichment.get("semantic_hardsub") or {})
        recovery = dict(enrichment.get("ocr_recovery") or {})
        if (
            str(semantic.get("classification") or "") != "TRANSITION_NOISE"
            or str(enrichment.get("ocr_text_raw") or "").strip()
            or str(recovery.get("status") or "").upper() != "UNRESOLVED"
            or int(recovery.get("accepted_observations") or 0) > 0
        ):
            continue
        master_row = master.get(text_id)
        if master_row is None:
            continue
        crop_path = (root / str(master_row.get("crop_path") or "")).resolve()
        if not crop_path.is_file() or not crop_path.is_relative_to(root):
            continue
        image = cv2.imread(str(crop_path), cv2.IMREAD_GRAYSCALE)
        if image is None or image.size < 16:
            continue
        laplacian_variance = float(cv2.Laplacian(image, cv2.CV_64F).var())
        short_side = max(3, min(image.shape[:2]))
        kernel_size = max(3, min(15, (short_side // 4) | 1))
        background = cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)
        highpass_mean = float(cv2.absdiff(image, background).mean())
        edge_fraction = float(np.mean(cv2.Canny(image, 50, 150) > 0))
        provenance = dict(enrichment.get("visual_provenance") or {})
        reasons = {
            str(value or "") for value in list(provenance.get("reasons") or [])
        }
        master_evidence = dict(master_row.get("boundary_evidence") or {})
        sparse_unanchored_micro = bool(
            int(master_evidence.get("hit_count") or master_row.get("hit_count") or 0)
            <= 2
            and str(master_evidence.get("status") or "").lower() == "uncertain"
            and reasons == {
                "screen_locked_localization_track",
                "explicit_editor_provenance_without_dialogue_alignment",
            }
        )
        if (
            not sparse_unanchored_micro
            and (
                laplacian_variance >= 1000.0
                or highpass_mean >= 8.0
                or edge_fraction >= 0.16
            )
        ):
            continue
        suppressed.append(text_id)
        audit.append(
            {
                "text_id": text_id,
                "classification": "SOURCE_INTRINSIC_EMPTY_TRANSITION_FALSE_POSITIVE",
                "reason": "ocr_empty_recovery_unresolved_non_glyph_crop",
                "laplacian_variance": round(laplacian_variance, 4),
                "highpass_mean": round(highpass_mean, 4),
                "edge_fraction": round(edge_fraction, 6),
                "crop_path": crop_path.relative_to(root).as_posix(),
            }
        )
    return sorted(set(suppressed)), audit


def _mapping_by_id(
    rows: Sequence[Any], *, key: str, label: str
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise Phase4InputError(f"{label} contains an invalid row")
        row = dict(raw)
        item_id = str(row.get(key) or "").strip()
        if not item_id or item_id in output:
            raise Phase4InputError(f"{label} contains a missing or duplicate {key}")
        output[item_id] = row
    return output


def _kind_for_roles(roles: Sequence[Any]) -> str:
    normalized = {str(role or "").strip().lower() for role in roles}
    # OCR can add a hardsub role to a compact app label near the lower edge.
    # Keep explicit UI chips anchored to their source widget instead of moving
    # them into the shared bottom-subtitle band.
    if "ui_chip" in normalized:
        return "ui"
    if "hardsub" in normalized:
        return "hardsub"
    if "title" in normalized:
        return "title"
    return "ui"


def _normalized_ocr_text(value: Any) -> str:
    return "".join(
        char
        for char in str(value or "").strip().casefold()
        if char.isalnum() or "\u3400" <= char <= "\u9fff"
    )


def _recovered_duplicate_shadow_ids(
    master: Mapping[str, Mapping[str, Any]],
    enrichments: Mapping[str, Mapping[str, Any]],
    *,
    frame_width: int,
    frame_height: int,
    fps: float,
) -> set[str]:
    """Suppress a short OCR recovery that snapped onto an existing caption.

    Phase 2 keeps the immutable projection row for audit, but a recovery crop
    can discover the same sentence again in a neighboring detector box. The
    duplicate must not shift content ids or render a second Vietnamese label.
    This gate requires exact source-text agreement, temporal containment and
    hash-bound local geometry consensus.
    """

    short_frames = max(2, int(round(max(0.1, float(fps)) * 0.75)))
    suppressed: set[str] = set()
    for text_id, enrichment in enrichments.items():
        recovery = dict(enrichment.get("geometry_recovery") or {})
        if (
            str(recovery.get("status") or "")
            != "LOCAL_DERIVED_TEMPORAL_CONSENSUS"
            or int(recovery.get("frame_support") or 0) < 2
            or int(recovery.get("geometry_observation_count") or 0) < 2
        ):
            continue
        candidate_master = master.get(text_id)
        if candidate_master is None:
            continue
        candidate_text = _normalized_ocr_text(enrichment.get("ocr_text_raw"))
        if not candidate_text:
            continue
        candidate_start = int(candidate_master.get("start_frame") or 0)
        candidate_end = int(candidate_master.get("end_frame") or candidate_start)
        if candidate_end - candidate_start + 1 > short_frames:
            continue
        derived = list(recovery.get("derived_box_coords") or [])
        if len(derived) != 4:
            continue
        try:
            cx0, cy0, cx1, cy1 = (float(value) for value in derived)
        except (TypeError, ValueError):
            continue
        candidate_area = max(1.0, (cx1 - cx0) * (cy1 - cy0))
        if cx1 <= cx0 or cy1 <= cy0:
            continue
        for host_id, host in master.items():
            if host_id == text_id:
                continue
            host_enrichment = enrichments.get(host_id)
            if host_enrichment is None:
                continue
            if candidate_text != _normalized_ocr_text(
                host_enrichment.get("ocr_text_raw")
            ):
                continue
            host_start = int(host.get("start_frame") or 0)
            host_end = int(host.get("end_frame") or host_start)
            overlap_frames = max(
                0,
                min(candidate_end, host_end)
                - max(candidate_start, host_start)
                + 1,
            )
            candidate_span = max(1, candidate_end - candidate_start + 1)
            if (
                host_start > candidate_start
                or host_end < candidate_end
                or overlap_frames / float(candidate_span) < 0.90
            ):
                continue
            host_coords = list(host.get("box_coords") or [])
            if len(host_coords) != 4:
                continue
            try:
                hx0, hy0, hx1, hy1 = (float(value) for value in host_coords)
            except (TypeError, ValueError):
                continue
            host_width = hx1 - hx0
            host_height = hy1 - hy0
            if (
                host_width / max(1.0, float(frame_width)) < 0.35
                or host_height / max(1.0, float(frame_height)) > 0.08
            ):
                continue
            intersection = max(0.0, min(cx1, hx1) - max(cx0, hx0)) * max(
                0.0, min(cy1, hy1) - max(cy0, hy0)
            )
            host_area = max(1.0, host_width * host_height)
            if intersection / min(candidate_area, host_area) >= 0.65:
                suppressed.add(text_id)
                break
    return suppressed


def _frame_ms(frame_index: int, fps: float) -> int:
    return int(round(float(frame_index) * 1000.0 / float(fps)))


def _geometry_overlap_over_smaller(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> float:
    left_x0 = float(left.get("x") or 0.0)
    left_y0 = float(left.get("y") or 0.0)
    left_x1 = left_x0 + float(left.get("width") or 0.0)
    left_y1 = left_y0 + float(left.get("height") or 0.0)
    right_x0 = float(right.get("x") or 0.0)
    right_y0 = float(right.get("y") or 0.0)
    right_x1 = right_x0 + float(right.get("width") or 0.0)
    right_y1 = right_y0 + float(right.get("height") or 0.0)
    intersection = max(0.0, min(left_x1, right_x1) - max(left_x0, right_x0)) * max(
        0.0, min(left_y1, right_y1) - max(left_y0, right_y0)
    )
    smaller = min(
        max(0.0, left_x1 - left_x0) * max(0.0, left_y1 - left_y0),
        max(0.0, right_x1 - right_x0) * max(0.0, right_y1 - right_y0),
    )
    return intersection / smaller if smaller > 0.0 else 0.0


def _resolve_protected_caption_shadow_ids(
    master: Mapping[str, Mapping[str, Any]],
    enrichments: Mapping[str, Mapping[str, Any]],
    geometry_ids: Sequence[str],
    protected_ids: set[str],
    *,
    frame_width: int,
    frame_height: int,
) -> set[str]:
    """Demote persisted source rows that are actually a second editor-caption line.

    Phase 1 provenance is intentionally conservative and may propagate a dense
    phone-panel decision into a wide, two-line editor caption.  If that row is
    left in ``protected_source_tracks``, the renderer carves it out of the
    caption plate and the original CJK remains visible.  This narrow conflict
    resolver only demotes a protected row when an approved editor row covers at
    least 75% of the same time span, overlaps its horizontal extent by 80%, and
    is immediately adjacent vertically.  The row becomes cover-only (never a
    translated object), so source text is not guessed or duplicated.
    """
    editor_rows: list[dict[str, Any]] = []
    for text_id in geometry_ids:
        enrichment = enrichments.get(str(text_id))
        master_row = master.get(str(text_id))
        if enrichment is None or master_row is None:
            continue
        provenance = dict(enrichment.get("visual_provenance") or {})
        classification = str(provenance.get("classification") or "").upper()
        confidence = float(provenance.get("confidence") or 0.0)
        if classification not in {"EDITOR_LABEL", "EDITOR_OVERLAY"} or confidence < 0.90:
            continue
        editor_rows.append(dict(master_row, text_id=str(text_id)))

    if not editor_rows:
        return set()
    fw = max(1.0, float(frame_width))
    fh = max(1.0, float(frame_height))
    demoted: set[str] = set()
    for text_id in sorted(protected_ids):
        candidate = master.get(str(text_id))
        if candidate is None:
            continue
        candidate_provenance = dict(candidate.get("visual_provenance") or {})
        if (
            str(candidate_provenance.get("classification") or "").upper()
            not in {"SOURCE_INTRINSIC", "SOURCE_INTRINSIC_PANEL"}
            or float(candidate_provenance.get("confidence") or 0.0) < 0.90
        ):
            continue
        coords = list(candidate.get("box_coords") or [])
        if len(coords) != 4:
            continue
        x0, y0, x1, y1 = (float(value) for value in coords)
        candidate_width = max(1.0, x1 - x0)
        candidate_height = max(1.0, y1 - y0)
        candidate_start = int(candidate.get("start_frame") or 0)
        candidate_end = int(candidate.get("end_frame") or candidate_start)
        candidate_span = max(1, candidate_end - candidate_start + 1)
        # A compact OCR child may be a duplicate fragment fully enclosed by a
        # wider approved editor row (for example the last two glyphs of a
        # comment-card line).  Preserving that child punches a Chinese-text
        # hole through the parent cover.  Exact spatial containment plus
        # strong temporal overlap is materially stronger than mere proximity
        # and remains safe for unrelated phone/source labels.
        compact_nested_shadow = False
        if candidate_width / fw < 0.14 and candidate_height / fh <= 0.045:
            for editor in editor_rows:
                editor_start = int(editor.get("start_frame") or 0)
                editor_end = int(editor.get("end_frame") or editor_start)
                overlap_frames = max(
                    0,
                    min(candidate_end, editor_end)
                    - max(candidate_start, editor_start)
                    + 1,
                )
                editor_span = max(1, editor_end - editor_start + 1)
                if overlap_frames / float(min(editor_span, candidate_span)) < 0.90:
                    continue
                editor_coords = list(editor.get("box_coords") or [])
                if len(editor_coords) != 4:
                    continue
                ex0, ey0, ex1, ey1 = (float(value) for value in editor_coords)
                intersection = max(0.0, min(x1, ex1) - max(x0, ex0)) * max(
                    0.0, min(y1, ey1) - max(y0, ey0)
                )
                candidate_area = candidate_width * candidate_height
                if intersection / candidate_area >= 0.90:
                    compact_nested_shadow = True
                    break
            if compact_nested_shadow:
                demoted.add(str(text_id))
                continue
        # A genuinely small phone label that is not an enclosed detector child
        # is not demoted merely because a caption happens to be nearby.
        if candidate_width / fw < 0.14 or candidate_height / fh > 0.045:
            continue
        for editor in editor_rows:
            if str(editor.get("text_id") or "") == str(text_id):
                continue
            editor_start = int(editor.get("start_frame") or 0)
            editor_end = int(editor.get("end_frame") or editor_start)
            editor_span = max(1, editor_end - editor_start + 1)
            overlap_frames = max(
                0,
                min(candidate_end, editor_end)
                - max(candidate_start, editor_start)
                + 1,
            )
            if overlap_frames / float(min(editor_span, candidate_span)) < 0.75:
                continue
            editor_coords = list(editor.get("box_coords") or [])
            if len(editor_coords) != 4:
                continue
            ex0, ey0, ex1, ey1 = (float(value) for value in editor_coords)
            horizontal_intersection = max(0.0, min(x1, ex1) - max(x0, ex0))
            if horizontal_intersection / min(candidate_width, max(1.0, ex1 - ex0)) < 0.80:
                continue
            vertical_gap = max(0.0, ey0 - y1, y0 - ey1)
            if vertical_gap > max(0.018 * fh, 1.5 * max(y1 - y0, ey1 - ey0)):
                continue
            demoted.add(str(text_id))
            break
    # Caption OCR often alternates between a combined two-line box and
    # individual line boxes.  Propagate the decision through that tightly
    # connected component so a later duplicate cannot reintroduce a protected
    # carve-out after the editor anchor itself ends.
    changed = True
    while changed:
        changed = False
        seed_rows = [master[text_id] for text_id in demoted if text_id in master]
        for text_id in sorted(protected_ids - demoted):
            candidate = master.get(str(text_id))
            if candidate is None:
                continue
            provenance = dict(candidate.get("visual_provenance") or {})
            if (
                str(provenance.get("classification") or "").upper()
                not in {"SOURCE_INTRINSIC", "SOURCE_INTRINSIC_PANEL"}
                or float(provenance.get("confidence") or 0.0) < 0.90
            ):
                continue
            coords = list(candidate.get("box_coords") or [])
            if len(coords) != 4:
                continue
            x0, y0, x1, y1 = (float(value) for value in coords)
            candidate_width = max(1.0, x1 - x0)
            candidate_height = max(1.0, y1 - y0)
            if candidate_width / fw < 0.14 or candidate_height / fh > 0.045:
                continue
            candidate_start = int(candidate.get("start_frame") or 0)
            candidate_end = int(candidate.get("end_frame") or candidate_start)
            candidate_span = max(1, candidate_end - candidate_start + 1)
            for seed in seed_rows:
                seed_start = int(seed.get("start_frame") or 0)
                seed_end = int(seed.get("end_frame") or seed_start)
                seed_span = max(1, seed_end - seed_start + 1)
                overlap_frames = max(
                    0,
                    min(candidate_end, seed_end)
                    - max(candidate_start, seed_start)
                    + 1,
                )
                if overlap_frames / float(min(candidate_span, seed_span)) < 0.60:
                    continue
                seed_coords = list(seed.get("box_coords") or [])
                if len(seed_coords) != 4:
                    continue
                sx0, sy0, sx1, sy1 = (float(value) for value in seed_coords)
                horizontal_intersection = max(0.0, min(x1, sx1) - max(x0, sx0))
                if horizontal_intersection / min(
                    candidate_width, max(1.0, sx1 - sx0)
                ) < 0.80:
                    continue
                vertical_gap = max(0.0, sy0 - y1, y0 - sy1)
                if vertical_gap > max(
                    0.018 * fh, 1.5 * max(y1 - y0, sy1 - sy0)
                ):
                    continue
                demoted.add(str(text_id))
                changed = True
                break
    return demoted


def _redundant_nested_editor_shadow_parents(
    master: Mapping[str, Mapping[str, Any]],
    enrichments: Mapping[str, Mapping[str, Any]],
    geometry_ids: Sequence[str],
    shadow_ids: set[str],
) -> dict[str, str]:
    """Return protected fragments already fully covered by an editor parent.

    Demoting a compact duplicate out of ``protected_source_tracks`` prevents a
    carve-out, but retaining it as another cover track is redundant and can
    trigger a second residual-stroke pass on pixels the parent already
    concealed.  Suppression is safe only for near-complete spatial containment
    and near-complete temporal overlap with an approved editor row.
    """

    editors = [
        master[text_id]
        for text_id in geometry_ids
        if text_id in master
        and str(
            dict(enrichments.get(text_id, {}).get("visual_provenance") or {}).get(
                "classification"
            )
            or ""
        ).upper()
        in {"EDITOR_LABEL", "EDITOR_OVERLAY"}
        and float(
            dict(enrichments.get(text_id, {}).get("visual_provenance") or {}).get(
                "confidence"
            )
            or 0.0
        )
        >= 0.90
    ]
    redundant: dict[str, str] = {}
    for text_id in shadow_ids:
        candidate = master.get(text_id)
        if candidate is None:
            continue
        coords = list(candidate.get("box_coords") or [])
        if len(coords) != 4:
            continue
        x0, y0, x1, y1 = (float(value) for value in coords)
        area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        start = int(candidate.get("start_frame") or 0)
        end = int(candidate.get("end_frame") or start)
        span = max(1, end - start + 1)
        if area <= 0.0:
            continue
        for editor in editors:
            editor_start = int(editor.get("start_frame") or 0)
            editor_end = int(editor.get("end_frame") or editor_start)
            overlap = max(
                0,
                min(end, editor_end) - max(start, editor_start) + 1,
            )
            if overlap / float(min(span, max(1, editor_end - editor_start + 1))) < 0.90:
                continue
            editor_coords = list(editor.get("box_coords") or [])
            if len(editor_coords) != 4:
                continue
            ex0, ey0, ex1, ey1 = (float(value) for value in editor_coords)
            intersection = max(0.0, min(x1, ex1) - max(x0, ex0)) * max(
                0.0, min(y1, ey1) - max(y0, ey0)
            )
            if intersection / area >= 0.90:
                redundant[text_id] = str(editor.get("text_id") or "")
                break
    return redundant


def _normalize_shared_caption_boundaries(
    tracks: list[dict[str, Any]], *, fps: float
) -> int:
    """Make one burn authority per temporal caption lane.

    Phase 1 deliberately keeps a conservative (cover-safe) interval around a
    detection.  Sparse OCR can therefore produce two different content
    objects with the same nominal start, even though their observed glyph
    frames are sequential.  Using the conservative interval for burn would
    stamp both Vietnamese strings during the transition.  We retain that
    interval as ``cover_*`` and partition only the text authority using the
    observed hit frames (or the representative frame as a fallback).

    The legacy boundary trim is retained for callers that do not carry Phase
    1 evidence (old artifacts and unit fixtures).
    """
    adjusted = 0
    max_ui_transition_frames = max(6, int(round(float(fps) * 1.75)))
    for track in tracks:
        start = int(track.get("start_frame") or 0)
        end = int(track.get("end_frame") or start)
        track.setdefault("cover_start_frame", start)
        track.setdefault("cover_end_frame", end)

    def evidence_anchor(track: Mapping[str, Any]) -> float:
        hits = [
            int(value)
            for value in list(track.get("hit_frames") or [])
            if isinstance(value, (int, float))
        ]
        if hits:
            values = sorted(hits)
            middle = len(values) // 2
            return float(values[middle]) if len(values) % 2 else (values[middle - 1] + values[middle]) / 2.0
        best = track.get("best_frame_index")
        if isinstance(best, (int, float)):
            return float(best)
        return (int(track.get("start_frame") or 0) + int(track.get("end_frame") or 0)) / 2.0

    def has_evidence(track: Mapping[str, Any]) -> bool:
        if bool(list(track.get("hit_frames") or [])):
            return True
        evidence = dict(track.get("boundary_evidence") or {})
        return evidence.get("observed_first_frame") is not None or evidence.get(
            "observed_last_frame"
        ) is not None

    def same_caption_lane(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        if str(left.get("kind") or "") != str(right.get("kind") or ""):
            return False
        if str(left.get("kind") or "") not in {"ui", "hardsub"}:
            return False
        return _geometry_overlap_over_smaller(
            dict(left.get("geometry") or {}), dict(right.get("geometry") or {})
        ) >= 0.65

    # Compare neighboring evidence in the same lane rather than trusting the
    # order of conservative OCR intervals (which is undefined when starts
    # are equal).
    ordered = sorted(
        [
            row
            for row in tracks
            if not bool(row.get("cover_only"))
        ],
        key=lambda row: (evidence_anchor(row), str(row.get("text_id") or "")),
    )
    for index, current in enumerate(ordered):
        for following in ordered[index + 1 :]:
            current_kind = str(current.get("kind") or "")
            following_kind = str(following.get("kind") or "")
            current_start = int(current.get("start_frame") or 0)
            current_end = int(current.get("end_frame") or current_start)
            following_start = int(following.get("start_frame") or 0)
            following_end = int(following.get("end_frame") or following_start)
            current_cover_start = int(current.get("cover_start_frame") or 0)
            current_cover_end = int(
                current.get("cover_end_frame") or current_cover_start
            )
            following_cover_start = int(following.get("cover_start_frame") or 0)
            following_cover_end = int(
                following.get("cover_end_frame") or following_cover_start
            )
            overlap_frames = (
                min(current_cover_end, following_cover_end)
                - max(current_cover_start, following_cover_start)
                + 1
            )
            shared_hardsub_boundary = (
                current_kind == "hardsub"
                and following_kind == "hardsub"
                and overlap_frames == 1
            )
            short_ui_transition = (
                current_kind == "ui"
                and following_kind == "ui"
                and 1 <= overlap_frames <= max_ui_transition_frames
            )
            if (
                not (shared_hardsub_boundary or short_ui_transition)
                or str(current.get("content_id") or "")
                == str(following.get("content_id") or "")
                or not same_caption_lane(current, following)
            ):
                continue

            # When Phase 1 carries evidence for both rows, split at the midpoint
            # between the observed glyph clusters.  This handles equal starts and
            # prevents a later short track from being trimmed before its own hit
            # frames.  The original conservative interval remains available for
            # source-text covering through cover_start/end_frame.
            if has_evidence(current) and has_evidence(following):
                left_anchor = evidence_anchor(current)
                right_anchor = evidence_anchor(following)
                if right_anchor > left_anchor:
                    shared_frame = int(round((left_anchor + right_anchor) / 2.0))
                    left_end = min(current_end, shared_frame)
                    right_start = max(following_start, shared_frame + 1)
                    if left_end >= current_start and right_start <= following_end:
                        current["end_frame"] = left_end
                        current["end_ms"] = _frame_ms(left_end + 1, fps)
                        following["start_frame"] = right_start
                        following["start_ms"] = _frame_ms(right_start, fps)
                        for row in (current, following):
                            row["timing_adjustment"] = {
                                "policy_version": PHASE4_TIMING_NORMALIZATION_POLICY_VERSION,
                                "reason": "temporal_evidence_partitioned_shared_caption_lane",
                                "boundary_frame": shared_frame,
                            }
                        adjusted += 1
                        continue

            # Legacy path for artifacts without hit evidence.
            shared_frame = following_start
            if shared_frame <= current_start:
                continue
            current["nominal_end_frame"] = int(current["end_frame"])
            current["end_frame"] = shared_frame - 1
            current["end_ms"] = _frame_ms(shared_frame, fps)
            current["timing_adjustment"] = {
                "policy_version": PHASE4_TIMING_NORMALIZATION_POLICY_VERSION,
                "reason": (
                    "short_ui_transition_assigned_to_incoming_track"
                    if short_ui_transition
                    else "shared_transition_frame_assigned_to_incoming_caption"
                ),
                "frames_trimmed": overlap_frames,
            }
            adjusted += 1
    return adjusted


def _collapse_residual_caption_cover_groups(
    tracks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Union same-lane residual fragments into one cover-only authority.

    Encoded OCR commonly reports only the left and right glyph islands of a
    full caption. Keeping each island as an independent cover leaves the
    middle Chinese glyphs visible. Connected fragments that overlap in time
    and share the same caption lane are therefore collapsed into one union ROI
    with the widest temporal interval. No Vietnamese text is burned here; the
    canonical Phase 3 content object remains the sole translation authority.
    """

    candidates = [
        row
        for row in tracks
        if bool(row.get("residual_caption_fragment_cover_only"))
        and bool(row.get("cover_only"))
    ]
    if len(candidates) < 2:
        return tracks, 0

    def connected(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        if max(
            int(left.get("start_frame") or 0),
            int(right.get("start_frame") or 0),
        ) > min(
            int(left.get("end_frame") or 0),
            int(right.get("end_frame") or 0),
        ):
            return False
        a = dict(left.get("geometry") or {})
        b = dict(right.get("geometry") or {})
        a_height = float(a.get("height") or 0.0)
        b_height = float(b.get("height") or 0.0)
        a_center = float(a.get("y") or 0.0) + a_height * 0.5
        b_center = float(b.get("y") or 0.0) + b_height * 0.5
        return abs(a_center - b_center) <= max(
            0.04, 1.25 * max(a_height, b_height)
        )

    remaining = {str(row.get("text_id") or ""): row for row in candidates}
    remove_ids: set[str] = set()
    collapsed = 0
    while remaining:
        seed_id, seed = remaining.popitem()
        group = [seed]
        changed = True
        while changed:
            changed = False
            for text_id, row in list(remaining.items()):
                if any(connected(row, member) for member in group):
                    group.append(row)
                    remaining.pop(text_id)
                    changed = True
        if len(group) < 2:
            continue
        canonical = max(
            group,
            key=lambda row: (
                int(row.get("end_frame") or 0)
                - int(row.get("start_frame") or 0),
                float(dict(row.get("geometry") or {}).get("width") or 0.0),
                str(row.get("text_id") or ""),
            ),
        )
        geometries = [dict(row.get("geometry") or {}) for row in group]
        x0 = min(float(row.get("x") or 0.0) for row in geometries)
        y0 = min(float(row.get("y") or 0.0) for row in geometries)
        x1 = max(
            float(row.get("x") or 0.0) + float(row.get("width") or 0.0)
            for row in geometries
        )
        y1 = max(
            float(row.get("y") or 0.0) + float(row.get("height") or 0.0)
            for row in geometries
        )
        canonical["geometry"] = {
            "x": x0,
            "y": y0,
            "width": x1 - x0,
            "height": y1 - y0,
        }
        canonical["start_frame"] = min(
            int(row.get("start_frame") or 0) for row in group
        )
        canonical["end_frame"] = max(
            int(row.get("end_frame") or 0) for row in group
        )
        canonical["best_frame_index"] = max(
            canonical["start_frame"],
            min(
                canonical["end_frame"],
                int(canonical.get("best_frame_index") or canonical["start_frame"]),
            ),
        )
        canonical["hit_frames"] = sorted(
            {
                int(frame)
                for row in group
                for frame in list(row.get("hit_frames") or [])
                if isinstance(frame, (int, float))
            }
        )
        canonical["residual_caption_cover_group"] = {
            "policy_version": "phase4_residual_caption_union_v1",
            "members": sorted(str(row.get("text_id") or "") for row in group),
            "reason": "same_lane_temporal_residual_fragments",
        }
        for row in group:
            text_id = str(row.get("text_id") or "")
            if row is not canonical:
                remove_ids.add(text_id)
        collapsed += len(group) - 1

    return [
        row
        for row in tracks
        if str(row.get("text_id") or "") not in remove_ids
    ], collapsed


def _suppress_weak_caption_fragments(tracks: list[dict[str, Any]]) -> int:
    """Keep OCR-empty transition fragments as cover-only geometry.

    The guard is deliberately narrow: the fragment must be a tiny, short
    hardsub with an operator EDIT but no OCR candidate, and it must sit beside
    a larger hardsub in the same temporal/lane neighborhood. This prevents a
    guessed sentence from being burned over a partial transition crop while
    preserving the geometry needed to remove the source glyph fragment.
    """

    suppressed = 0
    for track in tracks:
        if (
            not bool(track.pop("weak_ocr_fragment_candidate", False))
            or str(track.get("kind") or "") != "hardsub"
            or bool(track.get("cover_only"))
        ):
            continue
        start = int(track.get("start_frame") or 0)
        end = int(track.get("end_frame") or start)
        geometry = dict(track.get("geometry") or {})
        area = float(geometry.get("width") or 0.0) * float(
            geometry.get("height") or 0.0
        )
        if end - start + 1 > 6 or area > 0.003:
            continue
        x0 = float(geometry.get("x") or 0.0)
        y0 = float(geometry.get("y") or 0.0)
        x1 = x0 + float(geometry.get("width") or 0.0)
        y1 = y0 + float(geometry.get("height") or 0.0)
        parent: dict[str, Any] | None = None
        for candidate in tracks:
            if candidate is track or str(candidate.get("kind") or "") != "hardsub":
                continue
            candidate_start = int(candidate.get("start_frame") or 0)
            candidate_end = int(candidate.get("end_frame") or candidate_start)
            overlap_frames = max(
                0, min(end, candidate_end) - max(start, candidate_start) + 1
            )
            if overlap_frames < max(1, (end - start + 1) // 2):
                continue
            other = dict(candidate.get("geometry") or {})
            other_area = float(other.get("width") or 0.0) * float(
                other.get("height") or 0.0
            )
            if other_area < area * 1.5:
                continue
            ox0 = float(other.get("x") or 0.0)
            oy0 = float(other.get("y") or 0.0)
            ox1 = ox0 + float(other.get("width") or 0.0)
            oy1 = oy0 + float(other.get("height") or 0.0)
            vertical_intersection = max(0.0, min(y1, oy1) - max(y0, oy0))
            vertical_smaller = min(max(0.0, y1 - y0), max(0.0, oy1 - oy0))
            vertical_gap = max(0.0, oy0 - y1, y0 - oy1)
            horizontal_gap = max(0.0, ox0 - x1, x0 - ox1)
            if (
                vertical_smaller > 0.0
                and (
                    vertical_intersection / vertical_smaller >= 0.10
                    or vertical_gap <= 0.04
                )
                and horizontal_gap <= 0.05
            ):
                parent = candidate
                break
        if parent is None:
            continue
        track["text_vi"] = ""
        track["cover_only"] = True
        track["translation_status"] = "COVER_ONLY_WEAK_OCR_FRAGMENT"
        track["weak_fragment_suppression"] = {
            "policy_version": "weak_hardsub_fragment_guard_v1",
            "parent_text_id": parent.get("text_id"),
            "reason": "ocr_empty_short_adjacent_caption_fragment",
        }
        suppressed += 1
    return suppressed


def build_phase4_render_input(
    master_timeline: Sequence[Mapping[str, Any]],
    phase2_timeline: Mapping[str, Any],
    phase3_render_handoff: Mapping[str, Any],
    *,
    video_metadata: Mapping[str, Any],
    refs: Mapping[str, Any],
    cover_only_refs: Sequence[str] = (),
    protected_source_refs: Sequence[str] = (),
    suppressed_shadow_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Join by exact ``text_id``; timestamp/fuzzy lookup is intentionally forbidden."""
    if str(phase3_render_handoff.get("status") or "") != "READY_FOR_RENDER":
        raise Phase4InputError("Phase 3 render handoff is not READY_FOR_RENDER")

    frame_width = int(video_metadata.get("frame_width") or 0)
    frame_height = int(video_metadata.get("frame_height") or 0)
    frame_count = int(video_metadata.get("frame_count") or 0)
    fps = float(video_metadata.get("fps") or 0.0)
    if frame_width < 2 or frame_height < 2 or frame_count < 1 or fps <= 0:
        raise Phase4InputError("Invalid video metadata for Phase 4")

    master = _mapping_by_id(
        list(master_timeline), key="text_id", label="master_timeline"
    )
    enrichments = _mapping_by_id(
        list(phase2_timeline.get("track_enrichments") or []),
        key="text_id",
        label="phase2 track_enrichments",
    )
    coverage_by_id: dict[str, dict[str, Any]] = {
        text_id: dict(row.get("coverage_authority") or {})
        for text_id, row in enrichments.items()
        if isinstance(row.get("coverage_authority"), Mapping)
    }
    for raw in list(phase2_timeline.get("protected_source_tracks") or []):
        if not isinstance(raw, Mapping):
            continue
        text_id = str(raw.get("text_id") or "")
        coverage = raw.get("coverage_authority")
        if text_id and isinstance(coverage, Mapping):
            coverage_by_id[text_id] = dict(coverage)
    content = _mapping_by_id(
        list(phase2_timeline.get("content_objects") or []),
        key="content_id",
        label="phase2 content_objects",
    )
    raw_geometry = phase3_render_handoff.get("geometry_map")
    if not isinstance(raw_geometry, Mapping):
        raise Phase4InputError("Phase 3 handoff geometry_map must be an object")
    geometry = {
        str(text_id): dict(value)
        for text_id, value in raw_geometry.items()
        if isinstance(value, Mapping)
    }
    if len(geometry) != len(raw_geometry):
        raise Phase4InputError("Phase 3 handoff contains invalid geometry rows")

    suppressed_ids = {str(value) for value in suppressed_shadow_refs if str(value)}
    suppressed_ids.update(
        _recovered_duplicate_shadow_ids(
            master,
            enrichments,
            frame_width=frame_width,
            frame_height=frame_height,
            fps=fps,
        )
    )
    # An explicit, evidence-bound suppression is allowed to retire a stale
    # projection row (for example a residual OCR hallucination on skin).  The
    # immutable master id stays in the partition audit but is not rendered.
    geometry = {
        text_id: row
        for text_id, row in geometry.items()
        if text_id not in suppressed_ids
    }
    cover_ids = {str(value) for value in cover_only_refs if str(value)}
    protected_ids = {str(value) for value in protected_source_refs if str(value)}
    protected_caption_shadow_ids = _resolve_protected_caption_shadow_ids(
        master,
        enrichments,
        list(geometry),
        protected_ids,
        frame_width=frame_width,
        frame_height=frame_height,
    )
    redundant_nested_shadow_parents = _redundant_nested_editor_shadow_parents(
        master,
        enrichments,
        list(geometry),
        protected_caption_shadow_ids,
    )
    redundant_nested_shadow_ids = set(redundant_nested_shadow_parents)
    protected_ids.difference_update(protected_caption_shadow_ids)
    suppressed_ids.update(redundant_nested_shadow_ids)
    cover_ids.update(protected_caption_shadow_ids - redundant_nested_shadow_ids)
    if (cover_ids & protected_ids) or (cover_ids & suppressed_ids) or (
        protected_ids & suppressed_ids
    ):
        raise Phase4InputError("Phase 4 track partitions overlap")
    expected_ids = set(geometry) | cover_ids | protected_ids | suppressed_ids
    if set(master) != expected_ids:
        raise Phase4InputError(
            "Render geometry set mismatch "
            f"(master={len(master)}, translated={len(geometry)}, "
            f"cover_only={len(cover_ids)}, protected_source={len(protected_ids)}, "
            f"suppressed={len(suppressed_ids)})"
        )
    if not set(geometry).issubset(enrichments):
        raise Phase4InputError("Phase 2 enrichment is missing translated text_id rows")

    render_tracks: list[dict[str, Any]] = []
    protected_source_tracks: list[dict[str, Any]] = []
    for text_id, master_row in master.items():
        if text_id in suppressed_ids:
            continue
        start_frame = int(master_row.get("start_frame") or 0)
        end_frame = int(master_row.get("end_frame") or start_frame)
        provisional_content_id = str(
            dict(geometry.get(text_id) or {}).get("content_id")
            or dict(enrichments.get(text_id) or {}).get("content_id")
            or ""
        )
        provisional_semantic = dict(
            dict(enrichments.get(text_id, {}).get("semantic_hardsub") or {})
            or dict(
                dict(content.get(provisional_content_id) or {}).get(
                    "semantic_hardsub"
                )
                or {}
            )
        )
        provisional_alignment = dict(provisional_semantic.get("alignment") or {})
        semantic_dialogue_residual_expanded = False
        if (
            text_id.startswith("p2r_")
            and str(provisional_semantic.get("classification") or "")
            == "DIALOGUE_HARDSUB"
            and str(
                dict(provisional_semantic.get("translation_authority") or {}).get(
                    "translation_status"
                )
                or provisional_alignment.get("translation_status")
                or ""
            ).upper()
            == "APPROVED"
        ):
            try:
                transcript_start_ms = int(
                    provisional_alignment.get("transcript_start_ms")
                )
                transcript_end_ms = int(
                    provisional_alignment.get("transcript_end_ms")
                )
            except (TypeError, ValueError):
                transcript_start_ms = transcript_end_ms = 0
            if transcript_end_ms > transcript_start_ms >= 0:
                transcript_start_frame = max(
                    0,
                    min(
                        frame_count - 1,
                        int(math.floor(transcript_start_ms * fps / 1000.0)),
                    ),
                )
                transcript_end_frame = max(
                    transcript_start_frame,
                    min(
                        frame_count - 1,
                        int(math.ceil(transcript_end_ms * fps / 1000.0)) - 1,
                    ),
                )
                # Audio alignment supplies semantic timing, while the residual
                # OCR track supplies physical ink timing. Concealment must cover
                # their union so visual lead/tail frames cannot expose CJK.
                start_frame = min(start_frame, transcript_start_frame)
                end_frame = max(end_frame, transcript_end_frame)
                semantic_dialogue_residual_expanded = True
        raw_best_frame = master_row.get("best_frame_index")
        best_frame_index = (
            int(raw_best_frame)
            if raw_best_frame is not None
            else (start_frame + end_frame) // 2
        )
        if not start_frame <= best_frame_index <= end_frame:
            best_frame_index = (start_frame + end_frame) // 2
        coords = list(master_row.get("box_coords") or [])
        if (
            len(coords) != 4
            or start_frame < 0
            or end_frame < start_frame
            or end_frame >= frame_count
        ):
            raise Phase4InputError(f"Invalid timing/geometry for {text_id}")
        x0, y0, x1, y1 = (float(coords[index]) for index in range(4))
        if (
            x0 < 0
            or y0 < 0
            or x1 <= x0
            or y1 <= y0
            or x1 > frame_width
            or y1 > frame_height
        ):
            raise Phase4InputError(f"Out-of-frame geometry for {text_id}")

        if text_id in protected_ids:
            protected_source_tracks.append(
                {
                    "text_id": text_id,
                    "start_frame": start_frame,
                    "end_frame": end_frame,
                    "geometry": {
                        "x": x0 / frame_width,
                        "y": y0 / frame_height,
                        "width": (x1 - x0) / frame_width,
                        "height": (y1 - y0) / frame_height,
                    },
                    "classification": "SOURCE_INTRINSIC",
                    "action": "PRESERVE_SOURCE_PIXELS",
                    "visual_provenance": dict(
                        master_row.get("visual_provenance") or {}
                    ),
                    "coverage_authority": dict(
                        coverage_by_id.get(text_id) or {}
                    ),
                }
            )
            continue

        boundary_evidence = dict(master_row.get("boundary_evidence") or {})
        residual_caption_fragment = bool(
            text_id.startswith("p2r_")
            and str(boundary_evidence.get("method") or "")
            == "phase4_residual_source_ocr"
        )
        semantic_classification = str(
            dict(enrichments.get(text_id, {}).get("semantic_hardsub") or {}).get(
                "classification"
            )
            or dict(
                dict(content.get(provisional_content_id) or {}).get(
                    "semantic_hardsub"
                )
                or {}
            ).get("classification")
            or ""
        )
        # A residual that falls inside an approved dialogue cue is physical
        # concealment evidence, not a second subtitle placement authority.
        # Rendering a full Vietnamese dialogue segment into a 2-3 frame OCR
        # fragment creates unreadable flashes and typography failures. The
        # approved dialogue/TTS timeline remains the semantic authority.
        semantic_dialogue_residual_cover = bool(
            text_id.startswith("p2r_")
            and semantic_classification == "DIALOGUE_HARDSUB"
            and not semantic_dialogue_residual_expanded
        )
        # Output residual OCR often captures only the left/right glyphs of a
        # caption whose main temporal content object is already translated.
        # These rows extend source cover authority only; burning each fragment
        # as a separate Vietnamese label creates duplicate, scattered text.
        is_cover_only = (
            text_id in cover_ids
            or residual_caption_fragment
            or semantic_dialogue_residual_cover
        )
        text_vi = ""
        content_id: str | None = None
        roles: list[str] = []
        semantic_dialogue_hardsub = False
        translation_status = "COVER_ONLY"
        if not is_cover_only:
            phase3_row = geometry[text_id]
            enrichment = enrichments[text_id]
            content_id = str(phase3_row.get("content_id") or "").strip()
            if content_id != str(enrichment.get("content_id") or "").strip():
                raise Phase4InputError(f"Content mapping mismatch for {text_id}")
            content_row = content.get(content_id)
            if content_row is None:
                raise Phase4InputError(f"Missing Phase 2 content object for {text_id}")
            roles = [str(role) for role in list(content_row.get("roles") or [])]
            semantic_dialogue_hardsub = (
                str(
                    dict(content_row.get("semantic_hardsub") or {}).get(
                        "classification"
                    )
                    or ""
                )
                == "DIALOGUE_HARDSUB"
            )
            duplicate_transition_canonical = bool(
                content_row.get("duplicate_transition_canonicalization")
            )
            translation_status = str(phase3_row.get("translation_status") or "")
            if translation_status not in {
                "TRANSLATION_APPROVED",
                "TRANSLATION_DETERMINISTIC",
            }:
                raise Phase4InputError(f"Unapproved translation for {text_id}")
            raw_text = str(phase3_row.get("text_vi") or "").strip()
            text_vi = gate_vi_for_burn(raw_text)
            if not text_vi or text_vi != raw_text:
                raise Phase4InputError(f"Unsafe or empty Vietnamese text for {text_id}")

        render_tracks.append(
            {
                "text_id": text_id,
                "content_id": content_id,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "best_frame_index": best_frame_index,
                "start_ms": _frame_ms(start_frame, fps),
                "end_ms": _frame_ms(end_frame + 1, fps),
                "geometry": {
                    "x": x0 / frame_width,
                    "y": y0 / frame_height,
                    "width": (x1 - x0) / frame_width,
                    "height": (y1 - y0) / frame_height,
                },
                # Keep Phase 1 temporal evidence in the Phase 4 contract. It
                # is used only to partition competing burn authorities; the
                # conservative source interval remains the cover interval.
                "hit_frames": [
                    int(value)
                    for value in list(master_row.get("hit_frames") or [])
                    if isinstance(value, (int, float))
                ],
                "boundary_evidence": boundary_evidence,
                "coverage_authority": dict(
                    coverage_by_id.get(text_id) or {}
                ),
                "visual_provenance": dict(
                    master_row.get("visual_provenance") or {}
                ),
                "editor_card_panel_box": list(
                    dict(master_row.get("visual_provenance") or {}).get(
                        "editor_card_panel_box"
                    )
                    or []
                ),
                "editor_card_panel_geometry": (
                    {
                        "x": float(
                            dict(master_row.get("visual_provenance") or {})[
                                "editor_card_panel_box"
                            ][0]
                        )
                        / frame_width,
                        "y": float(
                            dict(master_row.get("visual_provenance") or {})[
                                "editor_card_panel_box"
                            ][1]
                        )
                        / frame_height,
                        "width": (
                            float(
                                dict(master_row.get("visual_provenance") or {})[
                                    "editor_card_panel_box"
                                ][2]
                            )
                            - float(
                                dict(master_row.get("visual_provenance") or {})[
                                    "editor_card_panel_box"
                                ][0]
                            )
                        )
                        / frame_width,
                        "height": (
                            float(
                                dict(master_row.get("visual_provenance") or {})[
                                    "editor_card_panel_box"
                                ][3]
                            )
                            - float(
                                dict(master_row.get("visual_provenance") or {})[
                                    "editor_card_panel_box"
                                ][1]
                            )
                        )
                        / frame_height,
                    }
                    if len(
                        list(
                            dict(master_row.get("visual_provenance") or {}).get(
                                "editor_card_panel_box"
                            )
                            or []
                        )
                    )
                    == 4
                    else {}
                ),
                "roles": roles,
                "kind": (
                    "hardsub"
                    if (
                        residual_caption_fragment
                        or semantic_dialogue_hardsub
                        or semantic_dialogue_residual_cover
                    )
                    else "ui"
                    if is_cover_only
                    else _kind_for_roles(roles)
                ),
                "text_vi": text_vi,
                "translation_status": translation_status,
                "cover_only": is_cover_only,
                "editor_caption_shadow_cover_only": (
                    text_id in protected_caption_shadow_ids
                ),
                "residual_caption_fragment_cover_only": residual_caption_fragment,
                "semantic_dialogue_residual_cover_only": (
                    semantic_dialogue_residual_cover
                ),
                "semantic_dialogue_residual_expanded": (
                    semantic_dialogue_residual_expanded
                ),
                "semantic_dialogue_hardsub": semantic_dialogue_hardsub,
                "duplicate_transition_canonical": (
                    duplicate_transition_canonical if not is_cover_only else False
                ),
                "weak_ocr_fragment_candidate": bool(
                    not list(content_row.get("ocr_text_raw_candidates") or [])
                    and str(
                        dict(content_row.get("operator_review") or {}).get(
                            "decision"
                        )
                        or ""
                    ).upper()
                    == "EDIT"
                )
                if not is_cover_only
                else False,
            }
        )

    render_tracks.sort(key=lambda row: (row["start_frame"], row["text_id"]))
    render_tracks_by_id = {
        str(row.get("text_id") or ""): row for row in render_tracks
    }
    for shadow_id, parent_id in redundant_nested_shadow_parents.items():
        shadow = master.get(shadow_id)
        parent = render_tracks_by_id.get(parent_id)
        if shadow is None or parent is None:
            continue
        shadow_presence_ranges = [
            (int(raw[0]), int(raw[1]))
            for raw in list(
                dict(coverage_by_id.get(shadow_id) or {}).get("presence_ranges")
                or []
            )
            if isinstance(raw, (list, tuple))
            and len(raw) == 2
            and int(raw[1]) >= int(raw[0])
        ]
        shadow_start = min(
            [int(shadow.get("start_frame") or 0)]
            + [start for start, _end in shadow_presence_ranges]
        )
        shadow_end = max(
            [
                int(
                    shadow.get("end_frame")
                    or shadow.get("start_frame")
                    or 0
                )
            ]
            + [end for _start, end in shadow_presence_ranges]
        )
        # The parent owns the shared geometry.  Extend only its physical cover
        # timing through the duplicate child's fail-closed presence tail so the
        # final CJK glyph cannot reappear after the parent OCR row ends.  The
        # extension is persisted because render-policy enrichment recalculates
        # normal OCR boundaries later in the pipeline.
        parent["cover_start_frame"] = min(
            int(parent.get("cover_start_frame") or parent.get("start_frame") or 0),
            shadow_start,
        )
        parent["cover_end_frame"] = max(
            int(parent.get("cover_end_frame") or parent.get("end_frame") or 0),
            shadow_end,
        )
        parent["nested_shadow_timing_extension"] = {
            "shadow_text_id": shadow_id,
            "start_frame": shadow_start,
            "end_frame": shadow_end,
            "policy_version": "nested_editor_shadow_timing_v1",
        }
    render_tracks, residual_fragments_collapsed = (
        _collapse_residual_caption_cover_groups(render_tracks)
    )
    for row in render_tracks:
        row["start_ms"] = _frame_ms(int(row.get("start_frame") or 0), fps)
        row["end_ms"] = _frame_ms(int(row.get("end_frame") or 0) + 1, fps)
    suppressed_weak_fragments = _suppress_weak_caption_fragments(render_tracks)
    adjusted_boundaries = _normalize_shared_caption_boundaries(
        render_tracks, fps=fps
    )
    return enrich_phase4_render_policies({
        "schema_version": PHASE4_INPUT_SCHEMA_VERSION,
        "status": "READY_FOR_PHASE4_PREFLIGHT",
        "refs": dict(refs),
        "video": {
            "frame_width": frame_width,
            "frame_height": frame_height,
            "frame_count": frame_count,
            "fps": fps,
        },
        "counts": {
            "render_tracks": len(render_tracks),
            "localized_tracks": sum(1 for row in render_tracks if row["text_vi"]),
            "cover_only_tracks": sum(1 for row in render_tracks if row["cover_only"]),
            "weak_caption_fragments_suppressed": suppressed_weak_fragments,
            "content_objects": len({row["content_id"] for row in render_tracks if row["content_id"]}),
            "protected_source_tracks": len(protected_source_tracks),
            "protected_caption_shadows_demoted": len(
                protected_caption_shadow_ids
            ),
            "redundant_nested_editor_shadows_suppressed": len(
                redundant_nested_shadow_ids
            ),
            "suppressed_shadow_tracks": len(suppressed_ids),
            "residual_caption_fragments_collapsed": residual_fragments_collapsed,
        },
        "timing_normalization": {
            "policy_version": PHASE4_TIMING_NORMALIZATION_POLICY_VERSION,
            "adjusted_shared_caption_boundaries": adjusted_boundaries,
            "weak_caption_fragments_suppressed": suppressed_weak_fragments,
        },
        "render_tracks": render_tracks,
        "protected_source_tracks": protected_source_tracks,
        "protected_caption_shadow_resolutions": [
            {
                "text_id": text_id,
                "resolution": "COVER_ONLY_EDITOR_CAPTION_SHADOW",
                "policy_version": "protected_caption_shadow_conflict_v1",
            }
            for text_id in sorted(protected_caption_shadow_ids)
        ],
        "suppressed_shadow_refs": sorted(suppressed_ids),
    })


def _segments_from_contract(contract: Mapping[str, Any]) -> list[OverlaySegment]:
    output: list[OverlaySegment] = []
    for row in list(contract.get("render_tracks") or []):
        geometry = dict(row.get("geometry") or {})
        output.append(
            OverlaySegment(
                start_ms=int(row.get("start_ms") or 0),
                end_ms=int(row.get("end_ms") or 0),
                x=float(geometry.get("x") or 0.0),
                y=float(geometry.get("y") or 0.0),
                width=float(geometry.get("width") or 0.0),
                height=float(geometry.get("height") or 0.0),
                text_vi=str(row.get("text_vi") or ""),
                kind=str(row.get("kind") or "ui"),
            )
        )
    return output


def _rects_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    smaller = min(
        max(0, a[2] - a[0]) * max(0, a[3] - a[1]),
        max(0, b[2] - b[0]) * max(0, b[3] - b[1]),
    )
    # A few anti-aliased edge pixels and stacked subtitle baselines can share a
    # thin strip even when glyph ink remains readable.  Measure material
    # overlap against the smaller label; the 0.30 threshold matches the
    # renderer's glyph boxes and avoids blocking intentionally stacked source
    # labels (which are still covered by visual preview QA).
    return smaller > 0 and intersection / smaller >= 0.30


def analyze_phase4_typography(
    contract: Mapping[str, Any], *, fontfile: str | Path | None = None
) -> dict[str, Any]:
    """Measure responsive layouts using the same safe-area engine as Phase 4."""
    import numpy as np

    from src.media_pipeline.video_renderer.adaptive_typography import (
        TypographyLayoutError,
        plan_dense_grid_layouts,
        plan_text_layout,
    )

    video = dict(contract.get("video") or {})
    frame_width = int(video.get("frame_width") or 0)
    frame_height = int(video.get("frame_height") or 0)
    if frame_width < 2 or frame_height < 2:
        raise Phase4InputError("Cannot analyze typography without frame dimensions")
    resolved_font = resolve_drawtext_font(fontfile)
    background = np.full((frame_height, frame_width, 3), 96, dtype=np.uint8)
    tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    rows: list[dict[str, Any]] = []
    text_overflow = 0
    clamp_required = 0
    rect_by_id: dict[str, tuple[int, int, int, int]] = {}
    dense_tracks: list[dict[str, Any]] = []
    for track in tracks:
        text = str(track.get("text_vi") or "").strip()
        if not text:
            continue
        policy = dict(track.get("render_policy") or {})
        context = dict(policy.get("context") or {})
        layout_policy = dict(policy.get("layout") or {})
        if bool(context.get("dense_ui")) and str(
            layout_policy.get("mode") or ""
        ) != "cover_aligned":
            dense_tracks.append(track)
            continue
        effective_kind = str(context.get("effective_kind") or track.get("kind") or "ui")
        typography_kind = str(context.get("typography_kind") or effective_kind)
        try:
            layout = plan_text_layout(
                text,
                kind=typography_kind,
                safe_area=dict(layout_policy.get("safe_area") or {}),
                frame_width=frame_width,
                frame_height=frame_height,
                fontfile=resolved_font,
                background_bgr=background,
                max_lines=int(layout_policy.get("max_lines") or 1),
            )
        except TypographyLayoutError:
            text_overflow += 1
            rows.append(
                {
                    "text_id": track.get("text_id"),
                    "content_id": track.get("content_id"),
                    "kind": typography_kind,
                    "font_size_px": None,
                    "glyph_width_px": None,
                    "glyph_height_px": None,
                    "frame_width_fraction": None,
                    "line_count": None,
                    "text_overflow": True,
                    "clamp_required": False,
                }
            )
            continue
        text_id = str(track.get("text_id") or "")
        rect_by_id[text_id] = (
            layout.x0,
            layout.y0,
            layout.x0 + layout.width,
            layout.y0 + layout.height,
        )
        rows.append(
            {
                "text_id": text_id,
                "content_id": track.get("content_id"),
                "kind": typography_kind,
                "font_size_px": layout.font_size_px,
                "glyph_width_px": layout.width,
                "glyph_height_px": layout.height,
                "frame_width_fraction": round(layout.width / frame_width, 4),
                "line_count": len(layout.lines),
                "text_overflow": False,
                "clamp_required": False,
                "layout_rect_px": {
                    "x0": layout.x0,
                    "y0": layout.y0,
                    "x1": layout.x0 + layout.width,
                    "y1": layout.y0 + layout.height,
                },
            }
        )

    event_times = sorted(
        {
            int(value)
            for track in tracks
            if track.get("text_vi")
            for value in (
                track.get("start_ms") or 0,
                track.get("end_ms") or 0,
            )
        }
    )
    dense_rects_by_time: dict[int, dict[str, tuple[int, int, int, int]]] = {}
    dense_metrics_written: set[str] = set()
    dense_overflow_ids: set[str] = set()
    dense_layout_cache: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    if dense_tracks:
        for time_ms in event_times:
            active_dense = [
                track
                for track in dense_tracks
                if int(track.get("start_ms") or 0)
                <= time_ms
                < int(track.get("end_ms") or 0)
            ]
            active_dense = select_text_render_tracks(active_dense)
            if not active_dense:
                continue
            key = tuple(str(track.get("text_id") or "") for track in active_dense)
            layouts = dense_layout_cache.get(key)
            if layouts is None:
                first_policy = dict(active_dense[0].get("render_policy") or {})
                safe_area = dict(
                    dict(first_policy.get("layout") or {}).get("safe_area") or {}
                )
                dense_items = []
                for track in active_dense:
                    geometry = dict(track.get("geometry") or {})
                    center = float(geometry.get("x") or 0.0) + float(
                        geometry.get("width") or 0.0
                    ) * 0.5
                    dense_items.append(
                        {
                            "text_id": track.get("text_id"),
                            "content_id": track.get("content_id"),
                            "text": track.get("text_vi"),
                            "side": "left" if center < 0.5 else "right",
                        }
                    )
                try:
                    layouts = plan_dense_grid_layouts(
                        dense_items,
                        safe_area=safe_area,
                        frame_width=frame_width,
                        frame_height=frame_height,
                        fontfile=resolved_font,
                        background_bgr=background,
                    )
                except TypographyLayoutError:
                    dense_overflow_ids.update(key)
                    layouts = []
                dense_layout_cache[key] = layouts
            time_rects: dict[str, tuple[int, int, int, int]] = {}
            for item in layouts:
                layout = item["layout"]
                text_id = str(item.get("text_id") or "")
                rect = (
                    layout.x0,
                    layout.y0,
                    layout.x0 + layout.width,
                    layout.y0 + layout.height,
                )
                time_rects[text_id] = rect
                if text_id in dense_metrics_written:
                    continue
                dense_metrics_written.add(text_id)
                rows.append(
                    {
                        "text_id": text_id,
                        "content_id": item.get("content_id"),
                        "kind": "ui",
                        "font_size_px": layout.font_size_px,
                        "glyph_width_px": layout.width,
                        "glyph_height_px": layout.height,
                        "frame_width_fraction": round(layout.width / frame_width, 4),
                        "line_count": len(layout.lines),
                        "text_overflow": False,
                        "clamp_required": False,
                        "layout_rect_px": {
                            "x0": layout.x0,
                            "y0": layout.y0,
                            "x1": layout.x0 + layout.width,
                            "y1": layout.y0 + layout.height,
                        },
                    }
                )
            dense_rects_by_time[time_ms] = time_rects
        text_overflow += len(dense_overflow_ids)

    collision_events: list[dict[str, Any]] = []
    non_blocking_collision_events: list[dict[str, Any]] = []
    track_by_id = {
        str(track.get("text_id") or ""): track
        for track in tracks
        if str(track.get("text_id") or "")
    }

    def source_geometry_overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
        a = dict(left.get("geometry") or {})
        b = dict(right.get("geometry") or {})
        ax0, ay0 = float(a.get("x") or 0.0), float(a.get("y") or 0.0)
        ax1, ay1 = ax0 + float(a.get("width") or 0.0), ay0 + float(a.get("height") or 0.0)
        bx0, by0 = float(b.get("x") or 0.0), float(b.get("y") or 0.0)
        bx1, by1 = bx0 + float(b.get("width") or 0.0), by0 + float(b.get("height") or 0.0)
        intersection = max(0.0, min(ax1, bx1) - max(ax0, bx0)) * max(
            0.0, min(ay1, by1) - max(ay0, by0)
        )
        smaller = min(
            max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0),
            max(0.0, bx1 - bx0) * max(0.0, by1 - by0),
        )
        return intersection / smaller if smaller > 0.0 else 0.0
    for time_ms in event_times:
        active_tracks = [
            track
            for track in tracks
            if track.get("text_vi")
            and int(track.get("start_ms") or 0) <= time_ms < int(track.get("end_ms") or 0)
        ]
        active_tracks = select_text_render_tracks(active_tracks)
        active_ids: list[str] = []
        rects: list[tuple[int, int, int, int]] = []
        dense_time_rects = dense_rects_by_time.get(time_ms, {})
        for track in active_tracks:
            text_id = str(track.get("text_id") or "")
            context = dict(
                dict(track.get("render_policy") or {}).get("context") or {}
            )
            rect = (
                dense_time_rects.get(text_id)
                if bool(context.get("dense_ui"))
                else rect_by_id.get(text_id)
            )
            if rect is None:
                continue
            active_ids.append(text_id)
            rects.append(rect)
        if len(active_ids) < 2:
            continue
        overlap_pairs = [
            [active_ids[index], active_ids[other_index]]
            for index, rect in enumerate(rects)
            for other_index, other in enumerate(
                rects[index + 1 :], start=index + 1
            )
            if _rects_overlap(rect, other)
        ]
        if overlap_pairs:
            event = {
                "time_ms": time_ms,
                "active": len(active_ids),
                "overlaps": len(overlap_pairs),
                "overlap_pairs": overlap_pairs,
            }
            # Source-separated editor UI labels are intentionally allowed to
            # use the renderer's stable vertical packing.  Their expanded
            # Vietnamese glyph boxes may touch even though the source boxes do
            # not; visual preview still records the event for operator QA.
            source_separated = all(
                source_geometry_overlap(
                    track_by_id.get(left, {}), track_by_id.get(right, {})
                ) < 0.10
                and str(track_by_id.get(left, {}).get("kind") or "ui") != "hardsub"
                and str(track_by_id.get(right, {}).get("kind") or "ui") != "hardsub"
                for left, right in overlap_pairs
            )
            bounded_residual_transition = all(
                (
                    str(track_by_id.get(text_id, {}).get("text_id") or "").startswith(
                        "p2r_"
                    )
                    and int(track_by_id.get(text_id, {}).get("end_frame") or 0)
                    - int(track_by_id.get(text_id, {}).get("start_frame") or 0)
                    <= 12
                )
                for pair in overlap_pairs
                for text_id in pair
                if str(track_by_id.get(text_id, {}).get("text_id") or "").startswith(
                    "p2r_"
                )
            ) and any(
                str(text_id).startswith("p2r_") for pair in overlap_pairs for text_id in pair
            )
            if source_separated or bounded_residual_transition:
                non_blocking_collision_events.append(
                    {
                        **event,
                        "classification": (
                            "ENCODED_RESIDUAL_TRANSITION_CONTACT"
                            if bounded_residual_transition
                            else "SOURCE_SEPARATED_LAYOUT_CONTACT"
                        ),
                    }
                )
            else:
                collision_events.append(event)

    blocking_reasons: list[str] = []
    if text_overflow:
        blocking_reasons.append(f"text_overflow:{text_overflow}")
    if collision_events:
        blocking_reasons.append(f"unresolved_collisions:{len(collision_events)}")
    return {
        "schema_version": PHASE4_PREFLIGHT_SCHEMA_VERSION,
        "status": (
            "PHASE4_PREFLIGHT_BLOCKED" if blocking_reasons else "READY_FOR_PHASE4"
        ),
        "blocked_reasons": blocking_reasons,
        "font": {"name": resolved_font.name},
        "counts": {
            "measured_tracks": len(rows),
            "text_overflow": text_overflow,
            "clamp_required": clamp_required,
            "collision_events": len(collision_events),
            "non_blocking_collision_events": len(non_blocking_collision_events),
        },
        "track_metrics": rows,
        "collision_events": collision_events,
        "non_blocking_collision_events": non_blocking_collision_events,
    }


def _verify_hash_ref(payload: Mapping[str, Any], key: str, path: Path) -> None:
    ref = payload.get(key)
    expected = str(ref.get("sha256") or "") if isinstance(ref, Mapping) else ""
    if not expected or expected != _sha256_file(path):
        raise Phase4InputError(f"Stale or missing {key} hash")


def _apply_geometry_overrides(
    master: Sequence[Mapping[str, Any]],
    overrides: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for raw in overrides:
        override = dict(raw)
        text_id = str(override.get("target_text_id") or "").strip()
        if not text_id or text_id in by_id:
            raise Phase4InputError("Residual geometry override target is invalid")
        by_id[text_id] = override
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in master:
        row = dict(raw)
        text_id = str(row.get("text_id") or "")
        override = by_id.get(text_id)
        if override is None:
            output.append(row)
            continue
        original = list(override.get("original_box_coords") or [])
        replacement = list(override.get("box_coords") or [])
        if (
            len(original) != 4
            or len(replacement) != 4
            or original != list(row.get("box_coords") or [])
            or int(override.get("start_frame")) != int(row.get("start_frame"))
            or int(override.get("end_frame")) != int(row.get("end_frame"))
        ):
            raise Phase4InputError("Residual geometry override authority drifted")
        row.update(
            {
                "box_coords": replacement,
                "best_keyframe_path": override.get("best_keyframe_path"),
                "crop_path": override.get("crop_path"),
                "best_frame_index": override.get("best_frame_index"),
                "geometry_remediation": {
                    "status": "OPERATOR_APPROVED_OVERRIDE",
                    "original_box_coords": original,
                },
            }
        )
        seen.add(text_id)
        output.append(row)
    if seen != set(by_id):
        raise Phase4InputError("Residual geometry override target is missing")
    return output


def _resolve_phase1_source_path(
    root: Path,
    source_raw: str,
    *,
    api_root: Path | None = None,
) -> Path:
    """Resolve Phase-1 source paths across artifact and API working bases."""
    source_candidate = Path(source_raw)
    if source_candidate.is_absolute():
        candidates = [source_candidate]
    else:
        runtime_api_root = (
            api_root.resolve()
            if api_root is not None
            else Path(__file__).resolve().parents[3]
        )
        candidates = [
            root / source_candidate,
            runtime_api_root / source_candidate,
            root.parent / source_candidate,
        ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    raise Phase4InputError("Source video referenced by Phase 1 is missing")


def prepare_phase4_from_root(
    root_dir: str | Path,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Load and verify the immutable artifact chain, then build preflight data."""
    root = Path(root_dir).resolve()
    paths = {
        "master": root / "master_timeline.json",
        "phase2_timeline": root / "phase2_ocr_timeline.json",
        "phase2_handoff": root / "phase2_handoff.json",
        "phase3_timeline": root / "phase3_translation_timeline.json",
        "phase3_handoff": root / "phase3_render_handoff.json",
        "ocr_payload": root / "ocr_payload.json",
        "phase1_meta": root / "phase1_meta.json",
    }
    for path in paths.values():
        if not path.is_file():
            raise Phase4InputError(f"Missing required artifact: {path.name}")
    master = _load_json(paths["master"])
    phase2_timeline = _load_json(paths["phase2_timeline"])
    phase2_handoff = _load_json(paths["phase2_handoff"])
    phase3_timeline = _load_json(paths["phase3_timeline"])
    phase3_handoff = _load_json(paths["phase3_handoff"])
    ocr_payload = _load_json(paths["ocr_payload"])
    phase1_meta = _load_json(paths["phase1_meta"])
    for label, payload in (
        ("phase2_handoff", phase2_handoff),
        ("phase3_timeline", phase3_timeline),
        ("phase3_handoff", phase3_handoff),
        ("ocr_payload", ocr_payload),
        ("phase1_meta", phase1_meta),
    ):
        if not isinstance(payload, Mapping):
            raise Phase4InputError(f"{label} must be a JSON object")
    if not isinstance(master, list) or not isinstance(phase2_timeline, Mapping):
        raise Phase4InputError("Invalid Phase 1/2 timeline shape")

    _verify_hash_ref(phase2_handoff, "phase1_ref", paths["master"])
    _verify_hash_ref(phase2_handoff, "phase2_ref", paths["phase2_timeline"])
    _verify_hash_ref(phase3_timeline, "phase2_handoff_ref", paths["phase2_handoff"])
    _verify_hash_ref(phase3_handoff, "phase2_handoff_ref", paths["phase2_handoff"])
    if (
        str(dict(phase3_timeline.get("review_summary") or {}).get("status") or "")
        != "TRANSLATION_APPROVED"
    ):
        raise Phase4InputError("Phase 3 translation timeline is not approved")

    supplemental = [
        dict(row)
        for row in list(phase2_timeline.get("supplemental_occurrences") or [])
        if isinstance(row, Mapping)
    ]
    geometry_overrides = [
        dict(row)
        for row in list(phase2_timeline.get("geometry_overrides") or [])
        if isinstance(row, Mapping)
    ]
    remediation_ref = dict(
        phase2_timeline.get("residual_remediation_ref") or {}
    )
    handoff_remediation_ref = dict(
        phase2_handoff.get("residual_remediation_ref") or {}
    )
    pixel_suppressed_refs: list[str] = []
    pixel_suppression_audit: list[dict[str, Any]] = []
    if supplemental or geometry_overrides:
        if not remediation_ref or remediation_ref != handoff_remediation_ref:
            raise Phase4InputError("Residual remediation authority mismatch")
        remediation_path = root / str(remediation_ref.get("path") or "")
        if (
            not remediation_path.is_file()
            or _sha256_file(remediation_path)
            != str(remediation_ref.get("sha256") or "")
        ):
            raise Phase4InputError("Residual remediation authority is stale")
        remediation = _load_json(remediation_path)
        if not isinstance(remediation, Mapping):
            raise Phase4InputError("Residual remediation must be a JSON object")
        unsigned = dict(remediation)
        claimed = str(unsigned.pop("remediation_sha256", "") or "")
        if (
            str(remediation.get("status") or "")
            != "OCR_RESIDUAL_REMEDIATION_APPROVED"
            or claimed != str(remediation_ref.get("remediation_sha256") or "")
            or claimed != _sha256_json(unsigned)
        ):
            raise Phase4InputError("Residual remediation self-hash is invalid")
        pixel_suppressed_refs, pixel_suppression_audit = (
            _pixel_bound_residual_suppressions(root, remediation)
        )
        approved_overrides = [
            dict(dict(row).get("geometry_override") or {})
            for row in list(remediation.get("approved_geometry_overrides") or [])
            if isinstance(row, Mapping)
        ]
        approved_by_id = {
            str(row.get("target_text_id") or ""): row
            for row in approved_overrides
            if str(row.get("target_text_id") or "")
        }
        timeline_by_id = {
            str(row.get("target_text_id") or ""): row
            for row in geometry_overrides
            if str(row.get("target_text_id") or "")
        }
        if approved_by_id != timeline_by_id:
            raise Phase4InputError("Residual geometry override authority mismatch")
    elif remediation_ref or handoff_remediation_ref:
        raise Phase4InputError("Residual remediation has no approved change")

    empty_transition_refs, empty_transition_audit = (
        _source_bound_empty_transition_suppressions(
            root,
            _mapping_by_id(master, key="text_id", label="master_timeline"),
            _mapping_by_id(
                list(phase2_timeline.get("track_enrichments") or []),
                key="text_id",
                label="phase2 track_enrichments",
            ),
        )
    )

    source_raw = str(phase1_meta.get("video") or "").strip()
    if not source_raw:
        raise Phase4InputError("phase1_meta.json has no source video reference")
    source_path = _resolve_phase1_source_path(root, source_raw)

    cover_only_refs: list[str] = []
    for item in list(phase2_handoff.get("cover_only_items") or []):
        if isinstance(item, Mapping):
            cover_only_refs.extend(str(value) for value in list(item.get("geometry_refs") or []))
    # Source-bound suppression is a stronger, later authority than the
    # conservative Phase 2 cover-only partition.  Keep the historical row in
    # the handoff for audit but do not ask Phase 4 to both suppress and cover it.
    empty_transition_set = set(empty_transition_refs)
    cover_only_refs = [
        text_id for text_id in cover_only_refs if text_id not in empty_transition_set
    ]
    protected_source_refs: list[str] = []
    for item in list(phase2_handoff.get("preserved_source_items") or []):
        if not isinstance(item, Mapping):
            continue
        protected_source_refs.extend(
            str(value) for value in list(item.get("geometry_refs") or [])
        )
        if str(item.get("text_id") or ""):
            protected_source_refs.append(str(item.get("text_id")))
    suppressed_shadow_refs: list[str] = []
    for item in list(phase2_handoff.get("suppressed_shadow_items") or []):
        if not isinstance(item, Mapping):
            continue
        shadow_id = str(item.get("shadow_text_id") or item.get("text_id") or "")
        if shadow_id:
            suppressed_shadow_refs.append(shadow_id)
    suppressed_shadow_refs.extend(pixel_suppressed_refs)
    suppressed_shadow_refs.extend(empty_transition_refs)
    refs = {
        "phase1_ref": phase2_handoff.get("phase1_ref"),
        "phase2_ref": phase2_handoff.get("phase2_ref"),
        "phase2_handoff_ref": {
            "path": paths["phase2_handoff"].name,
            "sha256": _sha256_file(paths["phase2_handoff"]),
        },
        "phase3_timeline_ref": {
            "path": paths["phase3_timeline"].name,
            "sha256": _sha256_file(paths["phase3_timeline"]),
        },
        "phase3_render_handoff_ref": {
            "path": paths["phase3_handoff"].name,
            "sha256": _sha256_file(paths["phase3_handoff"]),
        },
        "source_video_ref": {
            "path": source_path.name,
            "sha256": _sha256_file(source_path),
        },
    }
    if remediation_ref:
        refs["residual_remediation_ref"] = remediation_ref
    coverage_ref = dict(phase2_timeline.get("phase1_coverage_ref") or {})
    if coverage_ref:
        coverage_path = root / str(coverage_ref.get("path") or "")
        if (
            not coverage_path.is_file()
            or _sha256_file(coverage_path)
            != str(coverage_ref.get("sha256") or "")
        ):
            raise Phase4InputError("Phase 1 coverage authority is stale")
        coverage_payload = _load_json(coverage_path)
        if not isinstance(coverage_payload, Mapping):
            raise Phase4InputError("Phase 1 coverage authority must be an object")
        master_ref = dict(coverage_payload.get("master_timeline_ref") or {})
        if str(master_ref.get("sha256") or "") != _sha256_file(paths["master"]):
            raise Phase4InputError("Phase 1 coverage/master authority mismatch")
        refs["phase1_coverage_ref"] = coverage_ref
    video_metadata = {
        key: ocr_payload.get(key)
        for key in ("frame_width", "frame_height", "frame_count", "fps")
    }
    master_with_overrides = _apply_geometry_overrides(master, geometry_overrides)
    master_with_supplemental = master_with_overrides + supplemental
    contract = build_phase4_render_input(
        master_with_supplemental,
        phase2_timeline,
        phase3_handoff,
        video_metadata=video_metadata,
        refs=refs,
        cover_only_refs=cover_only_refs,
        protected_source_refs=protected_source_refs,
        suppressed_shadow_refs=suppressed_shadow_refs,
    )
    contract["pixel_bound_residual_suppressions"] = pixel_suppression_audit
    contract["source_bound_empty_transition_suppressions"] = (
        empty_transition_audit
    )
    report = analyze_phase4_typography(contract)
    contract["status"] = (
        "READY_FOR_PHASE4"
        if report["status"] == "READY_FOR_PHASE4"
        else "PHASE4_PREFLIGHT_BLOCKED"
    )
    return contract, report, source_path


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _preflight_markdown(
    contract: Mapping[str, Any], report: Mapping[str, Any]
) -> str:
    counts = dict(contract.get("counts") or {})
    qa_counts = dict(report.get("counts") or {})
    lines = [
        "# Phase 4 Render Preflight",
        "",
        f"- Trạng thái: `{report.get('status') or 'UNKNOWN'}`",
        f"- Render tracks: {counts.get('render_tracks', 0)}",
        f"- Localized tracks: {counts.get('localized_tracks', 0)}",
        f"- Cover-only tracks: {counts.get('cover_only_tracks', 0)}",
        f"- Text overflow: {qa_counts.get('text_overflow', 0)}",
        f"- Clamp required: {qa_counts.get('clamp_required', 0)}",
        f"- Collision events: {qa_counts.get('collision_events', 0)}",
        "",
        "| text_id | content_id | kind | font px | glyph px | width/frame | overflow | clamp |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    for row in list(report.get("track_metrics") or []):
        lines.append(
            "| {text_id} | {content_id} | {kind} | {font} | {width}×{height} | {ratio:.1%} | {overflow} | {clamp} |".format(
                text_id=row.get("text_id") or "",
                content_id=row.get("content_id") or "",
                kind=row.get("kind") or "",
                font=int(row.get("font_size_px") or 0),
                width=int(row.get("glyph_width_px") or 0),
                height=int(row.get("glyph_height_px") or 0),
                ratio=float(row.get("frame_width_fraction") or 0.0),
                overflow="YES" if row.get("text_overflow") else "no",
                clamp="YES" if row.get("clamp_required") else "no",
            )
        )
    lines.extend(
        [
            "",
            "Preflight chỉ xác nhận contract, typography và placement; chưa render video hoàn chỉnh.",
            "",
        ]
    )
    return "\n".join(lines)


def write_phase4_preflight_artifacts(
    *,
    root_dir: str | Path,
    contract: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, Path]:
    root = Path(root_dir)
    preview_path = root / "phase4_render_input_preview.json"
    final_path = root / "phase4_render_input.json"
    report_json_path = root / "qa" / "phase4_preflight_report.json"
    report_md_path = root / "PHASE4_PREFLIGHT_REPORT.md"
    _write_json_atomic(preview_path, dict(contract))
    _write_json_atomic(report_json_path, dict(report))
    _write_text_atomic(report_md_path, _preflight_markdown(contract, report))
    if (
        str(contract.get("status") or "") == "READY_FOR_PHASE4"
        and str(report.get("status") or "") == "READY_FOR_PHASE4"
    ):
        _write_json_atomic(final_path, dict(contract))
    elif final_path.is_file():
        stale_dir = root / "qa" / "stale"
        stale_dir.mkdir(parents=True, exist_ok=True)
        final_path.replace(
            stale_dir
            / f"{final_path.stem}_{_sha256_file(final_path)[:12]}{final_path.suffix}"
        )
    return {
        "preview": preview_path,
        "final": final_path,
        "report_json": report_json_path,
        "report_md": report_md_path,
    }
