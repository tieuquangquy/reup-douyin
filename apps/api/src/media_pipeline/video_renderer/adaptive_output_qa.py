"""Post-render QA for the adaptive Phase 4 renderer.

This module deliberately evaluates the encoded output, rather than trusting only
the in-memory frame QA produced while rendering.  It is contract-driven and does
not contain video-, track-, or coordinate-specific exceptions.
"""

from __future__ import annotations

import json
import re
import subprocess
import difflib
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from src.media_pipeline.video_renderer.phase4_approvals import (
    Phase4ApprovalError,
    apply_residual_cjk_false_positive_approval,
)
from src.media_pipeline.video_renderer.source_text_provenance import (
    is_editor_caption_track,
)
from src.media_pipeline.video_renderer.adaptive_video import (
    active_tracks_for_frame,
    dynamic_track_for_frame,
)
from src.media_pipeline.frame_sampling.coverage_track_closure import (
    local_textness_mask,
)


OUTPUT_QA_SCHEMA_VERSION = "phase4_adaptive_output_qa_v1"
RESIDUAL_CJK_POLICY_VERSION = "source_intrinsic_cjk_v12_temporal_provenance"
DEFAULT_MAX_EXTRA_FLICKER = 8.0
EDITOR_CAPTION_PLATE_MAX_EXTRA_FLICKER = 16.0
EDITOR_CAPTION_COVER_ALIGNED_MAX_EXTRA_FLICKER = 12.0
SOURCE_INTRINSIC_EDGE_GUTTER = 0.12
SOURCE_INTRINSIC_MAX_AREA = 0.003
SOURCE_INTRINSIC_TEXTURE_MAX_AREA = 0.0006
SOURCE_INTRINSIC_TEXTURE_MAX_PIXEL_ASPECT = 0.55
SOURCE_INTRINSIC_TEXTURE_MAX_MEAN_DELTA = 4.0
SOURCE_INTRINSIC_TEXTURE_MAX_P95_DELTA = 10.0
# Compression can make a food/texture blob look like one CJK glyph.  The
# relaxed branch is deliberately gated by low confidence and remains much
# smaller than a normal caption box.
SOURCE_INTRINSIC_LOW_CONF_TEXTURE_MAX_AREA = 0.0008
SOURCE_INTRINSIC_LOW_CONF_TEXTURE_MAX_PIXEL_ASPECT = 0.70
SOURCE_INTRINSIC_LOW_CONF_TEXTURE_MAX_CONFIDENCE = 0.55
# Detector boxes can expand over a high-contrast food/scene texture.  This
# branch remains provenance-bound: one CJK glyph, low confidence, no active
# cover, and source/render pixels that are effectively unchanged.
SOURCE_INTRINSIC_BOUNDED_TEXTURE_MAX_AREA = 0.15
SOURCE_INTRINSIC_BOUNDED_TEXTURE_MAX_WIDTH = 0.25
SOURCE_INTRINSIC_BOUNDED_TEXTURE_MAX_HEIGHT = 0.65
SOURCE_INTRINSIC_BOUNDED_TEXTURE_MAX_PIXEL_ASPECT = 1.60
SOURCE_INTRINSIC_BOUNDED_TEXTURE_MAX_CONFIDENCE = 0.82
# High-confidence single-glyph detections can still be OCR hallucinations when
# they cover a large reflective/food texture. This branch requires unchanged
# source/render pixels, no overlapping source OCR, and no editor authority.
SOURCE_INTRINSIC_LARGE_TEXTURE_MAX_AREA = 0.20
SOURCE_INTRINSIC_LARGE_TEXTURE_MAX_WIDTH = 0.35
SOURCE_INTRINSIC_LARGE_TEXTURE_MAX_HEIGHT = 0.65
SOURCE_INTRINSIC_LARGE_TEXTURE_MAX_PIXEL_ASPECT = 1.20
SOURCE_INTRINSIC_LARGE_TEXTURE_MIN_CONFIDENCE = 0.80
SOURCE_INTRINSIC_EDGE_PIXEL_MAX_AREA = 0.008
SOURCE_INTRINSIC_MATCHED_TEXTURE_MIN_AREA = 0.003
SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_AREA = 0.15
SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_PIXEL_ASPECT = 1.60
SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_MEAN_DELTA = 6.0
SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_P95_DELTA = 16.0
# A single small glyph-sized OCR box can be a printed mark on jewellery,
# packaging or a prop.  The regular matched-texture branch intentionally has
# a larger area floor to stay conservative; this narrower branch admits only a
# low/medium-confidence, source-matched glyph whose encoded pixels are proven
# unchanged and which is outside every active editor authority.  High-
# confidence source-matched captions remain blocking.
SOURCE_INTRINSIC_SMALL_MATCHED_MIN_AREA = 0.0004
SOURCE_INTRINSIC_SMALL_MATCHED_MAX_AREA = 0.003
SOURCE_INTRINSIC_SMALL_MATCHED_MAX_CONFIDENCE = 0.80
SOURCE_INTRINSIC_SMALL_MATCHED_MIN_GEOMETRY_OVERLAP = 0.80
SOURCE_INTRINSIC_SMALL_MATCHED_MIN_AREA_SIMILARITY = 0.30
SOURCE_INTRINSIC_SMALL_MATCHED_MAX_MEAN_DELTA = 6.0
SOURCE_INTRINSIC_SMALL_MATCHED_MAX_P95_DELTA = 16.0
SOURCE_INTRINSIC_WIDE_TEXTURE_MAX_AREA = 0.0045
SOURCE_INTRINSIC_WIDE_TEXTURE_MAX_CONFIDENCE = 0.50
SOURCE_INTRINSIC_WIDE_TEXTURE_MIN_PIXEL_ASPECT = 1.60
SOURCE_INTRINSIC_WIDE_TEXTURE_MAX_PIXEL_ASPECT = 2.40
RESIDUAL_SOURCE_TEXTURE_MIN_GEOMETRY_OVERLAP = 0.80
RESIDUAL_SOURCE_TEXTURE_MIN_AREA_SIMILARITY = 0.80
TEMPORAL_CONFIRMATION_MIN_AREA_SIMILARITY = 0.25
TEMPORAL_CONFIRMATION_MIN_CJK_SIMILARITY = 0.50
TEMPORAL_CONFIRMATION_MIN_GEOMETRY_OVERLAP = 0.50
SOURCE_SCENE_EDITOR_OVERLAP_MAX_WIDTH = 0.08
SOURCE_SCENE_EDITOR_OVERLAP_MAX_HEIGHT = 0.08
SOURCE_SCENE_EDITOR_OVERLAP_MAX_MEAN_DELTA = 12.0
SOURCE_SCENE_EDITOR_OVERLAP_MAX_P95_DELTA = 50.0
SOURCE_INTRINSIC_OBJECT_PRINT_MAX_CHARS = 3
SOURCE_INTRINSIC_OBJECT_PRINT_MIN_AREA = 0.005
SOURCE_INTRINSIC_OBJECT_PRINT_MAX_AREA = 0.08
SOURCE_INTRINSIC_OBJECT_PRINT_MAX_CONFIDENCE = 0.65
# A locally encoded blur plate can occasionally collapse DBNet into one huge
# low-confidence CJK box that spans the face/scene plus the actual caption
# lane.  This is not residual text: the source OCR has no matching geometry,
# and the box is far larger than any supported glyph row.  Keep this bound
# narrow so ordinary captions can never enter it.
BLUR_ONLY_COLLAPSED_PLATE_MIN_AREA = 0.20
BLUR_ONLY_COLLAPSED_PLATE_MAX_CONFIDENCE = 0.75
# Tiny one/two-glyph recognitions on a cover-only plate edge are compression
# texture unless they survive neighboring-frame/source confirmation.  This
# branch runs before temporal confirmation and only inside an active cover.
BLUR_ONLY_PLATE_EDGE_MAX_AREA = 0.003
BLUR_ONLY_PLATE_EDGE_MAX_CONFIDENCE = 0.40
# Source/object texture outside the subtitle lane is preserved when source and
# output pixels are effectively unchanged.  It must not become a request to
# blur filmed objects merely because PP-OCR emits one glyph on their texture.
SOURCE_INTRINSIC_OFF_LANE_TEXTURE_MAX_AREA = 0.002
SOURCE_INTRINSIC_OFF_LANE_TEXTURE_MAX_CONFIDENCE = 0.70
SOURCE_INTRINSIC_OFF_LANE_TEXTURE_MAX_Y = 0.65
SOURCE_INTRINSIC_LARGE_LOW_CONF_TEXTURE_MAX_AREA = 0.30
SOURCE_INTRINSIC_LARGE_LOW_CONF_TEXTURE_MAX_CONFIDENCE = 0.55


class AdaptiveOutputQaError(RuntimeError):
    """Raised when encoded source/output media cannot be evaluated safely."""


class OnnxResidualCjkProvider:
    """Torch-free local DBNet + PP-OCRv4 recognizer for post-render QA."""

    provider_name = "onnx_dbnet_ppocr_v4_residual_qa"

    def __init__(self, detector: Any, recognizer: Any):
        self._detector = detector
        self._recognizer = recognizer

    def detect_frame(self, image_path: Path, *, frame_time_ms: int) -> Any:
        import cv2

        from src.ocr_pipeline.types import FrameOcrResult, OcrBox

        frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if frame is None:
            raise AdaptiveOutputQaError("Cannot read frame for residual OCR")
        height, width = frame.shape[:2]
        detected = self._detector.detect(
            frame,
            long_edge=960,
            bin_thresh=0.25,
            rematch_after_expand=True,
        )
        crops: list[np.ndarray] = []
        retained: list[Any] = []
        for box in detected:
            x0 = max(0, int(np.floor(float(box.x) * width)))
            y0 = max(0, int(np.floor(float(box.y) * height)))
            x1 = min(width, int(np.ceil((float(box.x) + float(box.width)) * width)))
            y1 = min(height, int(np.ceil((float(box.y) + float(box.height)) * height)))
            if x1 - x0 < 2 or y1 - y0 < 2:
                continue
            retained.append(box)
            crops.append(frame[y0:y1, x0:x1])
        recognitions = self._recognizer.recognize_batch(crops) if crops else []
        boxes = [
            OcrBox(
                x=float(box.x),
                y=float(box.y),
                width=float(box.width),
                height=float(box.height),
                text=str(recognition.text or "").strip(),
                confidence=float(recognition.confidence),
            )
            for box, recognition in zip(retained, recognitions, strict=True)
        ]
        return FrameOcrResult(
            frame_time_ms=int(frame_time_ms),
            frame_width=width,
            frame_height=height,
            boxes=boxes,
        )


def build_local_residual_ocr_provider() -> OnnxResidualCjkProvider:
    """Build the repository's pinned, CPU-only residual-CJK QA provider.

    Model resolution is repository-relative.  Assets are never downloaded here:
    missing weights keep the final gate closed and must be provisioned explicitly.
    """

    from src.media_pipeline.frame_sampling.ensure_dbnet_model import (
        default_dbnet_model_path,
    )
    from src.media_pipeline.frame_sampling.ensure_text_recognizer_model import (
        default_recognizer_dictionary_path,
        default_recognizer_model_path,
    )
    from src.media_pipeline.frame_sampling.local_text_detector import LocalTextDetector
    from src.media_pipeline.frame_sampling.local_text_recognizer import (
        LocalTextRecognizer,
    )

    detector = LocalTextDetector(default_dbnet_model_path())
    recognizer = LocalTextRecognizer(
        default_recognizer_model_path(), default_recognizer_dictionary_path()
    )
    return OnnxResidualCjkProvider(detector, recognizer)


def select_qa_frame_indices(
    contract: Mapping[str, Any],
    *,
    motion_scores: Mapping[int, float] | None = None,
    limit: int = 20,
) -> list[int]:
    """Select global and per-track start/middle/end/motion-peak frames.

    The bounded, deterministic sampler keeps QA cost independent of video length
    while still observing every transition class represented by the contract.
    Up to 64 post-track frames are retained exhaustively: the first frame after
    a known caption is the highest-value place to catch an untracked next line.
    """

    frame_count = int(dict(contract.get("video") or {}).get("frame_count") or 0)
    if frame_count < 1 or limit < 1:
        return []
    last = frame_count - 1
    scores = {int(key): float(value) for key, value in (motion_scores or {}).items()}
    candidates: set[int] = {0, last, last // 2}
    post_end_boundaries: set[int] = set()
    for raw in list(contract.get("render_tracks") or []):
        if not isinstance(raw, Mapping):
            continue
        start = max(0, min(last, int(raw.get("start_frame") or 0)))
        end = max(start, min(last, int(raw.get("end_frame") or start)))
        post_end = min(last, end + 1)
        candidates.update((start, (start + end) // 2, end, post_end))
        post_end_boundaries.add(post_end)
        in_track = [
            (score, index)
            for index, score in scores.items()
            if start <= index <= end
        ]
        if in_track:
            candidates.add(max(in_track, key=lambda item: (item[0], -item[1]))[1])

    ordered = sorted(candidates)
    if len(ordered) <= limit:
        return ordered
    # Reserve transition coverage for the first frame after a track ends. This
    # catches an inclusive/exclusive boundary miss that ordinary start/mid/end
    # sampling cannot see. Fill the remaining budget evenly over all candidates.
    def evenly(values: Sequence[int], count: int) -> set[int]:
        rows = sorted({int(value) for value in values})
        if count <= 0 or not rows:
            return set()
        if len(rows) <= count:
            return set(rows)
        positions = np.linspace(0, len(rows) - 1, num=count)
        return {rows[int(round(position))] for position in positions}

    selected = {0} if limit == 1 else {0, last}
    boundary_budget = min(
        len(post_end_boundaries),
        max(1, int(round(limit * 0.40)), min(64, len(post_end_boundaries))),
    )
    selected.update(evenly(sorted(post_end_boundaries), boundary_budget))
    remaining = max(0, limit - len(selected))
    selected.update(
        evenly([value for value in ordered if value not in selected], remaining)
    )
    if len(selected) < limit:
        for value in ordered:
            if value not in selected:
                selected.add(value)
            if len(selected) >= limit:
                break
    return sorted(selected)


def include_phase1_completeness_frames(
    indices: Sequence[int],
    *,
    artifact_dir: str | Path,
    decoded_frame_count: int,
    max_added_frames: int = 96,
) -> list[int]:
    """Carry Phase-1 all-frame discovery evidence into encoded-output OCR QA.

    The normal QA sampler is track-driven. A caption that never became a
    render track could therefore remain invisible to it. OCR-V27.1 records
    completeness candidates before track construction and retains
    every strong one-frame boundary and representative frames from persistent
    candidates for full-frame local CJK OCR after encode.
    """

    frame_count = max(0, int(decoded_frame_count))
    selected = {
        int(value) for value in indices if 0 <= int(value) < frame_count
    }
    if frame_count < 1 or max_added_frames < 1:
        return sorted(selected)

    qa_root = Path(artifact_dir).resolve()
    candidate_path: Path | None = None
    for parent in (qa_root, *qa_root.parents[:4]):
        candidate = parent / "phase1_candidate_windows_v1.json"
        if candidate.is_file():
            candidate_path = candidate
            break
    if candidate_path is None:
        return sorted(selected)
    try:
        payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return sorted(selected)
    if not isinstance(payload, Mapping):
        return sorted(selected)
    policy_version = str(payload.get("policy_version") or "")
    if policy_version not in {
        "audio_visual_temporal_policy_v9_completeness_first",
        "audio_visual_temporal_policy_v10_cjk_single_frame_consensus",
        "audio_visual_temporal_policy_v11_audio_authority_proxy_budget",
        "audio_visual_temporal_policy_v12_epoch_complete_cover",
    }:
        return sorted(selected)

    hard = {
        int(value)
        for value in list(payload.get("hard_textness_frames") or [])
        if 0 <= int(value) < frame_count
    }
    single_frame_candidates = (
        list(payload.get("single_frame_retention_candidate_frames") or [])
        if policy_version
        in {
            "audio_visual_temporal_policy_v10_cjk_single_frame_consensus",
            "audio_visual_temporal_policy_v11_audio_authority_proxy_budget",
            "audio_visual_temporal_policy_v12_epoch_complete_cover",
        }
        else []
    )
    candidates = sorted(
        {
            int(value)
            for value in (
                list(payload.get("completeness_candidate_frames") or [])
                + single_frame_candidates
                + list(payload.get("coverage_unassigned_candidate_frames") or [])
                + list(payload.get("coverage_residual_dbnet_frames") or [])
            )
            if 0 <= int(value) < frame_count
        }
    )
    policy = dict(payload.get("policy") or {})
    source_fps = max(1.0, float(payload.get("fps") or 30.0))
    candidate_fps = max(
        1.0, float(policy.get("completeness_sample_fps") or 6.0)
    )
    group_gap = max(1, int(round(source_fps / candidate_fps)) + 1)
    groups: list[list[int]] = []
    for frame in candidates:
        if groups and frame <= groups[-1][-1] + group_gap:
            groups[-1].append(frame)
        else:
            groups.append([frame])

    # ``hard_textness_frames`` is a high-recall Phase-1 discovery stream, not
    # an instruction to run heavyweight OCR on every positive proxy frame.
    # Long caption videos can contain thousands of hard frames. Keep their
    # temporal clusters represented, then enforce the same explicit budget as
    # every other completeness source; full-timeline pixel QA still scans all
    # frames independently below.
    hard_groups: list[list[int]] = []
    for frame in sorted(hard):
        if hard_groups and frame <= hard_groups[-1][-1] + group_gap:
            hard_groups[-1].append(frame)
        else:
            hard_groups.append([frame])
    hard_representative = {
        value
        for group in hard_groups
        for value in (group[0], group[len(group) // 2], group[-1])
    }
    representative: set[int] = set(hard_representative)
    persistent_stride = max(1, int(round(source_fps * 0.5)))
    for group in groups:
        representative.update((group[0], group[-1], group[len(group) // 2]))
        prior = group[0]
        for frame in group[1:-1]:
            if frame - prior >= persistent_stride:
                representative.add(frame)
                prior = frame

    bounded = sorted(representative)
    if len(bounded) > int(max_added_frames):
        positions = np.linspace(
            0, len(bounded) - 1, num=max(1, int(max_added_frames))
        )
        bounded = [bounded[int(round(position))] for position in positions]
    selected.update(bounded)
    return sorted(selected)


def include_dense_ui_interval_frames(
    indices: Sequence[int],
    contract: Mapping[str, Any],
    *,
    decoded_frame_count: int,
    max_interval_frames: int = 120,
    max_added_frames: int = 420,
    editor_caption_stride: int = 3,
) -> list[int]:
    """Add bounded dense-UI frames and a 10-fps scan of editor captions.

    Dense phone/UI scenes can expose a different CJK fragment at each frame
    after a neighboring cover is changed. Sampling only track boundaries can
    therefore create an unbounded remediation loop. This helper tightens QA
    for short dense intervals while retaining a hard cost cap for long clips.
    """

    frame_count = max(0, int(decoded_frame_count))
    valid = lambda value: 0 <= int(value) < frame_count
    base = {int(value) for value in indices if valid(value)}
    if frame_count < 1 or max_interval_frames < 1 or max_added_frames < 1:
        return sorted(base)
    last = frame_count - 1
    intervals: list[tuple[int, int]] = []
    editor_intervals: list[tuple[int, int]] = []
    for raw in list(contract.get("render_tracks") or []):
        if not isinstance(raw, Mapping):
            continue
        context = dict(
            dict(raw.get("render_policy") or {}).get("context") or {}
        )
        start = max(0, min(last, int(raw.get("start_frame") or 0)))
        end = max(start, min(last, int(raw.get("end_frame") or start)))
        is_editor_caption = is_editor_caption_track(raw)
        if is_editor_caption:
            editor_intervals.append((start, end))
        elif (
            bool(context.get("dense_ui"))
            and isinstance(raw.get("output_residual_coverage"), Mapping)
            and int(context.get("simultaneous_count") or 0) >= 20
            and end - start + 1 <= max_interval_frames
        ):
            intervals.append((start, end))
    if not intervals and not editor_intervals:
        return sorted(base)
    intervals.sort()
    merged: list[list[int]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    dense_frames = [frame for start, end in merged for frame in range(start, end + 1)]
    caption_frames = sorted(
        {
            frame
            for start, end in editor_intervals
            for frame in (
                *range(start, end + 1, max(1, int(editor_caption_stride))),
                end,
            )
        }
    )
    added = sorted(set(dense_frames) | set(caption_frames))
    if len(added) > max_added_frames:
        return sorted(base)
    return sorted(base | set(added))


def include_operator_approved_qa_frame(
    indices: Sequence[int],
    *,
    decoded_frame_count: int,
    approval: Mapping[str, Any] | None,
) -> list[int]:
    """Force the immutable operator evidence frame into encoded-output QA."""

    selected = {int(index) for index in indices}
    if approval is None:
        return sorted(selected)
    entries = (
        list(approval.get("approvals") or [])
        if str(approval.get("schema_version") or "")
        == "phase4_residual_cjk_false_positive_approval_v2"
        else [approval]
    )
    for raw in entries:
        if not isinstance(raw, Mapping):
            continue
        approved_frame = int(
            dict(raw.get("detection") or {}).get("frame_index") or 0
        )
        if 0 <= approved_frame < int(decoded_frame_count):
            selected.add(approved_frame)
    return sorted(selected)


def compute_temporal_flicker(
    source_frames: Sequence[np.ndarray],
    rendered_frames: Sequence[np.ndarray],
    allowed_mask: np.ndarray,
) -> dict[str, Any]:
    """Measure temporal change added by rendering above source-scene motion."""

    if len(source_frames) != len(rendered_frames) or len(source_frames) < 2:
        raise ValueError("Temporal flicker requires matching frame sequences")
    first = np.asarray(source_frames[0])
    mask = np.asarray(allowed_mask)
    if first.ndim != 3 or mask.shape != first.shape[:2]:
        raise ValueError("Temporal flicker mask does not match frame dimensions")
    selected = mask > 0
    if not np.any(selected):
        return {
            "status": "NOT_APPLICABLE",
            "pairs": len(source_frames) - 1,
            "extra_flicker_mean": 0.0,
            "extra_flicker_max": 0.0,
        }

    extras: list[float] = []
    excluded_source_motion_pairs = 0
    for index in range(1, len(source_frames)):
        source_before = np.asarray(source_frames[index - 1])
        source_after = np.asarray(source_frames[index])
        render_before = np.asarray(rendered_frames[index - 1])
        render_after = np.asarray(rendered_frames[index])
        if not (
            source_before.shape
            == source_after.shape
            == render_before.shape
            == render_after.shape
            == first.shape
        ):
            raise ValueError("Temporal flicker frames have inconsistent shapes")
        source_delta = np.abs(
            source_after.astype(np.float32) - source_before.astype(np.float32)
        ).mean(axis=2)
        render_delta = np.abs(
            render_after.astype(np.float32) - render_before.astype(np.float32)
        ).mean(axis=2)
        source_motion = float(source_delta[selected].mean())
        # A scene cut or a large camera/subject movement is not render flicker;
        # subtracting it from a new subtitle plate over-penalizes valid covers.
        if source_motion > 40.0:
            excluded_source_motion_pairs += 1
            continue
        # Burned-in glyph pixels are occluded in the source. When the source
        # scene moves behind those glyphs, the cleaned output legitimately
        # reveals motion that cannot be measured at the original pixel. Use a
        # small local motion envelope so that this expected reveal is not
        # mistaken for temporal flicker, while leaving genuinely isolated
        # output flashes detectable. The radius scales with frame size and is
        # intentionally bounded to roughly one subtitle-stroke width.
        import cv2

        radius = max(1, min(12, int(round(min(first.shape[:2]) * 0.008))))
        kernel_size = radius * 2 + 1
        local_source_motion = cv2.dilate(
            source_delta.astype(np.float32),
            np.ones((kernel_size, kernel_size), dtype=np.uint8),
        )
        extra = np.maximum(0.0, render_delta - local_source_motion)
        extras.append(float(extra[selected].mean()))
    if not extras:
        return {
            "status": "NOT_APPLICABLE",
            "pairs": len(source_frames) - 1,
            "stable_pairs": 0,
            "excluded_source_motion_pairs": excluded_source_motion_pairs,
            "extra_flicker_mean": 0.0,
            "extra_flicker_max": 0.0,
        }
    return {
        "status": "PASS",
        "pairs": len(extras),
        "stable_pairs": len(extras),
        "excluded_source_motion_pairs": excluded_source_motion_pairs,
        "extra_flicker_mean": round(float(np.mean(extras)), 4),
        "extra_flicker_max": round(float(max(extras)), 4),
    }


def evaluate_output_damage(
    source_bgr: np.ndarray,
    rendered_bgr: np.ndarray,
    allowed_mask: np.ndarray,
    *,
    max_outside_mean_abs_delta: float = 6.0,
    max_outside_changed_fraction: float = 0.05,
    changed_pixel_delta: float = 18.0,
) -> dict[str, Any]:
    """Fail when encoded output changes too much outside authorized edit areas."""

    source = np.asarray(source_bgr)
    rendered = np.asarray(rendered_bgr)
    mask = np.asarray(allowed_mask)
    if source.shape != rendered.shape or source.ndim != 3:
        raise ValueError("Output damage frames do not match")
    if mask.shape != source.shape[:2]:
        raise ValueError("Output damage mask does not match frame dimensions")
    outside = mask <= 0
    if not np.any(outside):
        return {
            "status": "PASS",
            "blocked_reasons": [],
            "metrics": {
                "outside_mean_abs_delta": 0.0,
                "outside_changed_fraction": 0.0,
            },
        }
    per_pixel = np.abs(rendered.astype(np.float32) - source.astype(np.float32)).mean(
        axis=2
    )
    mean_delta = float(per_pixel[outside].mean())
    changed_fraction = float(
        np.count_nonzero(per_pixel[outside] > float(changed_pixel_delta))
        / np.count_nonzero(outside)
    )
    blocked = (
        mean_delta > float(max_outside_mean_abs_delta)
        or changed_fraction > float(max_outside_changed_fraction)
    )
    return {
        "status": "BLOCKED" if blocked else "PASS",
        "blocked_reasons": ["outside_cover_damage"] if blocked else [],
        "metrics": {
            "outside_mean_abs_delta": round(mean_delta, 4),
            "outside_changed_fraction": round(changed_fraction, 6),
            "changed_pixel_delta": float(changed_pixel_delta),
        },
    }


def evaluate_cover_layout_alignment(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Fail when an editor caption is rendered away from its removal lane."""

    rows: list[dict[str, Any]] = []
    for raw in list(contract.get("render_tracks") or []):
        if not isinstance(raw, Mapping):
            continue
        policy = dict(raw.get("render_policy") or {})
        context = dict(policy.get("context") or {})
        if not is_editor_caption_track(raw):
            continue
        cover = dict(dict(policy.get("cover") or {}).get("roi") or {})
        layout_policy = dict(policy.get("layout") or {})
        layout = dict(layout_policy.get("safe_area") or {})
        cover_center = (
            float(cover.get("x") or 0.0) + float(cover.get("width") or 0.0) / 2.0,
            float(cover.get("y") or 0.0) + float(cover.get("height") or 0.0) / 2.0,
        )
        layout_center = (
            float(layout.get("x") or 0.0) + float(layout.get("width") or 0.0) / 2.0,
            float(layout.get("y") or 0.0) + float(layout.get("height") or 0.0) / 2.0,
        )
        dx = abs(cover_center[0] - layout_center[0])
        dy = abs(cover_center[1] - layout_center[1])
        aligned = (
            str(layout_policy.get("mode") or "") == "cover_aligned"
            and dx <= max(0.01, float(cover.get("width") or 0.0) * 0.05)
            and dy <= max(0.01, float(cover.get("height") or 0.0) * 0.15)
        )
        rows.append(
            {
                "text_id": raw.get("text_id"),
                "status": "PASS" if aligned else "BLOCKED",
                "layout_mode": layout_policy.get("mode"),
                "center_displacement": {"x": round(dx, 6), "y": round(dy, 6)},
                "cover_roi": cover,
                "layout_safe_area": layout,
            }
        )
    blocked = [row for row in rows if row["status"] == "BLOCKED"]
    return {
        "status": "BLOCKED" if blocked else "PASS",
        "blocked_count": len(blocked),
        "tracks": rows,
    }


def summarize_temporal_flicker_for_verdict(
    rows: Sequence[Mapping[str, Any]],
    *,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep cover-active boundaries blocking; exclude only true on/off edges.

    A caption content boundary is not a license for the plate to pulse.  It is
    excluded only when neither side has an active concealment authority (the
    intentional plate appearance/disappearance case). Transitions between two
    overlapping/bridged tracks stay part of the flicker verdict.
    """

    boundary_frames: set[int] = set()
    cover_intervals: list[tuple[int, int]] = []
    full_lane_plate = False
    cover_aligned_caption = False
    for raw in list(contract.get("render_tracks") or []):
        if not isinstance(raw, Mapping):
            continue
        policy = dict(raw.get("render_policy") or {})
        context = dict(policy.get("context") or {})
        cover = dict(policy.get("cover") or {})
        is_caption = is_editor_caption_track(raw)
        is_stylized_title = bool(
            context.get("intro_stylized_title")
            and str(cover.get("mask_mode") or "") == "stylized_components"
        )
        if not is_caption and not is_stylized_title:
            continue
        full_lane_plate = full_lane_plate or str(
            cover.get("strategy") or ""
        ) == "editor_caption_full_lane_plate" or str(
            cover.get("geometry_mode") or ""
        ) == "full_width_caption_lane"
        cover_aligned_caption = cover_aligned_caption or str(
            dict(policy.get("layout") or {}).get("mode") or ""
        ) == "cover_aligned"
        transition_hold_frames = max(
            1,
            int(
                cover.get("transition_hold_frames")
                or context.get("transition_hold_frames")
                or 1
            ),
        )
        cover_start = int(
            raw.get("cover_start_frame") or raw.get("start_frame") or 0
        )
        cover_end = int(
            raw.get("cover_end_frame") or raw.get("end_frame") or cover_start
        )
        cover_intervals.append(
            (
                max(0, cover_start - transition_hold_frames),
                cover_end + transition_hold_frames,
            )
        )
        for edge in (
            cover_start,
            cover_end,
        ):
            boundary_frames.update(
                range(
                    max(0, edge - transition_hold_frames),
                    edge + transition_hold_frames + 1,
                )
            )
    annotated: list[dict[str, Any]] = []
    blocking_values: list[float] = []
    excluded_count = 0
    for raw in rows:
        row = dict(raw)
        frame_index = int(row.get("frame_index") or 0)
        active_intervals = sum(
            start <= frame_index <= end for start, end in cover_intervals
        )
        # When another authority is active at this boundary, the visible
        # plate should stay stable and any extra delta remains a real failure.
        if frame_index in boundary_frames and active_intervals <= 1:
            row["blocking_exclusion"] = "EXPECTED_EDITOR_CAPTION_BOUNDARY"
            excluded_count += 1
        else:
            blocking_values.append(float(row.get("extra_flicker_max") or 0.0))
            if frame_index in boundary_frames:
                row["blocking_boundary"] = "ACTIVE_COVER_TRANSITION"
        annotated.append(row)
    return {
        "max_extra_flicker": round(max(blocking_values, default=0.0), 4),
        "limit": (
            EDITOR_CAPTION_PLATE_MAX_EXTRA_FLICKER
            if full_lane_plate
            else EDITOR_CAPTION_COVER_ALIGNED_MAX_EXTRA_FLICKER
            if cover_aligned_caption
            else DEFAULT_MAX_EXTRA_FLICKER
        ),
        "boundary_excluded_count": excluded_count,
        "frames": annotated,
    }


def classify_editor_caption_ocr_false_positives(
    detections: Sequence[Mapping[str, Any]],
    *,
    contract: Mapping[str, Any],
    source_frames: Mapping[int, np.ndarray] | None = None,
    rendered_frames: Mapping[int, np.ndarray] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove Paddle CJK misreads of mostly-Latin Vietnamese editor captions.

    A contiguous CJK prefix/suffix is retained as a real residual. Paddle can
    merge leftover source glyphs and the Vietnamese replacement into one OCR
    line; Latin similarity alone must not hide that case.
    """

    def latin_signature(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", str(value or ""))
        ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", "", ascii_text.casefold())

    def edge_cjk_run(value: str) -> int:
        compact = re.sub(r"^[\s\W_]+|[\s\W_]+$", "", str(value or ""))
        leading = 0
        for char in compact:
            if _cjk_chars(char):
                leading += 1
            else:
                break
        trailing = 0
        for char in reversed(compact):
            if _cjk_chars(char):
                trailing += 1
            else:
                break
        return max(leading, trailing)

    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for raw in detections:
        row = dict(raw)
        frame_index = int(row.get("frame_index") or 0)
        detection_rect = _normalized_rect(row)
        matched: dict[str, Any] | None = None
        # The concealment authority can intentionally outlive the semantic
        # subtitle span at a transition.  Query the same runtime-active tracks
        # used by the renderer so OCR texture on the held plate edge is not
        # misreported as residual CJK after the text span ends.
        for track in active_tracks_for_frame(
            contract,
            frame_index,
            source_frame_bgr=(source_frames or {}).get(frame_index),
        ):
            policy = dict(track.get("render_policy") or {})
            cover = dict(dict(policy.get("cover") or {}).get("roi") or track.get("geometry") or {})
            layout = dict(dict(policy.get("layout") or {}).get("safe_area") or {})
            rois = [cover, layout, dict(track.get("geometry") or {})]
            roi_overlaps = [
                _intersection_over_smaller(
                    detection_rect,
                    (
                        float(roi.get("x") or 0.0),
                        float(roi.get("y") or 0.0),
                        float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0),
                        float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0),
                    ),
                )
                for roi in rois
                if isinstance(roi, Mapping)
            ]
            if (
                any(value >= 0.50 for value in roi_overlaps)
                or bool(track.get("cover_only"))
                and any(value >= 0.25 for value in roi_overlaps)
            ) and bool(
                str(track.get("text_vi") or "").strip()
                or track.get("cover_only")
            ):
                matched = track
                break
        if matched is None:
            kept.append(row)
            continue
        cjk_count = len(_cjk_chars(str(row.get("text") or "")))
        cjk_edge_run = edge_cjk_run(str(row.get("text") or ""))
        observed = latin_signature(str(row.get("text") or ""))
        expected = latin_signature(str(matched.get("text_vi") or ""))
        similarity = difflib.SequenceMatcher(None, observed, expected).ratio()
        patch_similarity = _source_render_patch_similarity(
            row,
            source_frame=(source_frames or {}).get(frame_index),
            rendered_frame=(rendered_frames or {}).get(frame_index),
        )
        unchanged_caption_texture = (
            cjk_count == 1
            and float(row.get("confidence") or 0.0) <= 0.45
            and patch_similarity is not None
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_P95_DELTA
        )
        area = max(0.0, detection_rect[2] - detection_rect[0]) * max(
            0.0, detection_rect[3] - detection_rect[1]
        )
        blur_only_plate_edge_texture = (
            bool(matched.get("cover_only"))
            and cjk_count <= 2
            and (
                float(row.get("confidence") or 0.0)
                <= BLUR_ONLY_PLATE_EDGE_MAX_CONFIDENCE
                or len(observed) < 4
            )
            and area <= BLUR_ONLY_PLATE_EDGE_MAX_AREA
        )
        blur_only_collapsed_plate = (
            bool(matched.get("cover_only"))
            and cjk_count == 1
            and float(row.get("confidence") or 0.0)
            <= BLUR_ONLY_COLLAPSED_PLATE_MAX_CONFIDENCE
            and area >= BLUR_ONLY_COLLAPSED_PLATE_MIN_AREA
        )
        if (
            cjk_count <= 2
            and cjk_edge_run < 2
            and len(observed) >= 12
            and similarity >= 0.72
        ):
            excluded.append(
                {
                    **row,
                    "classification": "EDITOR_CAPTION_OCR_FALSE_POSITIVE",
                    "matched_text_id": matched.get("text_id"),
                    "latin_signature_similarity": round(similarity, 6),
                    "edge_cjk_run": cjk_edge_run,
                }
            )
        elif unchanged_caption_texture or blur_only_plate_edge_texture or blur_only_collapsed_plate:
            excluded.append(
                {
                    **row,
                    "classification": (
                        "BLUR_ONLY_COLLAPSED_PLATE_OCR_FALSE_POSITIVE"
                        if blur_only_collapsed_plate
                        else "BLUR_ONLY_PLATE_EDGE_OCR_FALSE_POSITIVE"
                        if blur_only_plate_edge_texture
                        else "EDITOR_CAPTION_TEXTURE_OCR_FALSE_POSITIVE"
                    ),
                    "matched_text_id": matched.get("text_id"),
                    **(
                        {
                            "source_render_patch": {
                                key: round(value, 6)
                                for key, value in patch_similarity.items()
                            }
                        }
                        if patch_similarity is not None
                        else {}
                    ),
                }
            )
        else:
            kept.append(row)
    return kept, excluded


def build_output_qa_verdict(
    *,
    duration_match: bool,
    frame_count_match: bool,
    color_authority_match: bool,
    max_extra_flicker: float,
    residual_cjk: Sequence[Mapping[str, Any]],
    outside_damage_blocked: bool,
    residual_ocr_complete: bool = True,
    final_audio_passed: bool = True,
    cover_layout_aligned: bool = True,
    timeline_edit_coverage: bool = True,
    residual_stroke_removal: bool = True,
    protected_source_integrity: bool = True,
    flicker_limit: float = DEFAULT_MAX_EXTRA_FLICKER,
) -> dict[str, Any]:
    """Build one fail-closed verdict from independent encoded-output checks."""

    checks = {
        "duration": bool(duration_match),
        "frame_count": bool(frame_count_match),
        "color_authority": bool(color_authority_match),
        "temporal_flicker": float(max_extra_flicker) <= float(flicker_limit),
        "residual_ocr_complete": bool(residual_ocr_complete),
        "residual_cjk": not bool(residual_cjk),
        "outside_cover_damage": not bool(outside_damage_blocked),
        "cover_layout_alignment": bool(cover_layout_aligned),
        "timeline_edit_coverage": bool(timeline_edit_coverage),
        "residual_stroke_removal": bool(residual_stroke_removal),
        "protected_source_integrity": bool(protected_source_integrity),
        "final_audio": bool(final_audio_passed),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": OUTPUT_QA_SCHEMA_VERSION,
        "status": "FAIL" if failed else "PASS",
        "failed_checks": failed,
        "checks": checks,
        "thresholds": {"max_extra_flicker": float(flicker_limit)},
    }


def evaluate_audio_quality(
    *,
    present: bool,
    audio_duration_seconds: float | None,
    expected_duration_seconds: float,
    integrated_lufs: float | None,
    true_peak_db: float | None,
    measurement_complete: bool,
    target_lufs: float = -14.0,
) -> dict[str, Any]:
    failed: list[str] = []
    if not present:
        failed.append("audio_stream_missing")
    if not measurement_complete:
        failed.append("audio_measurement_incomplete")
    tolerance = max(0.12, abs(float(expected_duration_seconds)) * 0.01)
    if (
        audio_duration_seconds is None
        or abs(float(audio_duration_seconds) - float(expected_duration_seconds)) > tolerance
    ):
        failed.append("audio_duration_mismatch")
    if integrated_lufs is None or abs(float(integrated_lufs) - float(target_lufs)) > 2.5:
        failed.append("audio_loudness")
    if true_peak_db is None or float(true_peak_db) > -0.5:
        failed.append("audio_true_peak")
    return {
        "status": "FAIL" if failed else "PASS",
        "failed_checks": failed,
        "metrics": {
            "present": bool(present),
            "audio_duration_seconds": audio_duration_seconds,
            "expected_duration_seconds": float(expected_duration_seconds),
            "duration_tolerance_seconds": round(tolerance, 6),
            "integrated_lufs": integrated_lufs,
            "target_lufs": float(target_lufs),
            "true_peak_db": true_peak_db,
            "measurement_complete": bool(measurement_complete),
        },
    }


def final_audio_target_lufs(contract: Mapping[str, Any]) -> float:
    """Return the delivery-QA reference for the approved audio role.

    Dialogue-led output stays at the short-form speech target.  A measured
    no-dialogue source track is music/effects-led, so it keeps two decibels of
    additional programme headroom instead of being judged as narration.
    """

    audio = dict(dict(contract.get("authorities") or {}).get("audio") or {})
    if str(audio.get("strategy") or "") == (
        "preserve_verified_no_dialogue_source_audio"
    ):
        return -16.0
    return -14.0


def probe_encoded_audio_quality(
    media_path: str | Path,
    *,
    ffprobe_binary: str = "ffprobe",
    ffmpeg_binary: str = "ffmpeg",
) -> dict[str, Any]:
    path = Path(media_path)
    stream = subprocess.run(
        [
            ffprobe_binary,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    present = False
    duration: float | None = None
    if stream.returncode == 0:
        try:
            payload = json.loads(stream.stdout or "{}")
            streams = list(payload.get("streams") or [])
            present = bool(streams)
            if streams and streams[0].get("duration") is not None:
                duration = float(streams[0]["duration"])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    loudness = subprocess.run(
        [
            ffmpeg_binary,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vn",
            "-af",
            "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    combined = "\n".join((loudness.stdout or "", loudness.stderr or ""))
    matches = re.findall(r"\{\s*\"input_i\".*?\}", combined, flags=re.DOTALL)
    integrated: float | None = None
    true_peak: float | None = None
    if loudness.returncode == 0 and matches:
        try:
            measured = json.loads(matches[-1])
            integrated = float(measured["input_i"])
            true_peak = float(measured["input_tp"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
    return {
        "present": present,
        "audio_duration_seconds": duration,
        "integrated_lufs": integrated,
        "true_peak_db": true_peak,
        "measurement_complete": (
            present and duration is not None and integrated is not None and true_peak is not None
        ),
    }
def normalized_rect_mask(
    shape: tuple[int, int], rectangles: Sequence[Mapping[str, Any]], *, pad_px: int = 3
) -> np.ndarray:
    """Rasterize normalized rectangles into an edit-authority mask."""

    height, width = (int(shape[0]), int(shape[1]))
    mask = np.zeros((height, width), dtype=np.uint8)
    for rectangle in rectangles:
        x = float(rectangle.get("x") or 0.0)
        y = float(rectangle.get("y") or 0.0)
        w = float(rectangle.get("width") or 0.0)
        h = float(rectangle.get("height") or 0.0)
        x0 = max(0, int(np.floor(x * width)) - pad_px)
        y0 = max(0, int(np.floor(y * height)) - pad_px)
        x1 = min(width, int(np.ceil((x + w) * width)) + pad_px)
        y1 = min(height, int(np.ceil((y + h) * height)) + pad_px)
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = 255
    return mask


def allowed_edit_mask_for_frame(
    contract: Mapping[str, Any], frame_index: int, shape: tuple[int, int]
) -> np.ndarray:
    """Union cover ROIs and Vietnamese layout areas active on a frame."""

    rectangles: list[Mapping[str, Any]] = []
    for raw in list(contract.get("dense_ui_panels") or []):
        if not isinstance(raw, Mapping):
            continue
        start = int(raw.get("start_frame") or 0)
        end = int(raw.get("end_frame") or -1)
        roi = raw.get("panel_roi")
        if start <= int(frame_index) <= end and isinstance(roi, Mapping):
            rectangles.append(roi)
    for raw in active_tracks_for_frame(contract, int(frame_index)):
        start = int(raw.get("start_frame") or 0)
        end = int(raw.get("end_frame") or start)
        policy = dict(raw.get("render_policy") or {})
        cover = dict(policy.get("cover") or {})
        text_active = start <= int(frame_index) <= end
        context = dict(policy.get("context") or {})
        if bool(context.get("short_intro_full_frame_clean_plate_approved")):
            height, width = shape
            return np.full((height, width), 255, dtype=np.uint8)
        layout = dict(policy.get("layout") or {})
        cover_roi = cover.get("roi") or raw.get("geometry")
        if isinstance(cover_roi, Mapping):
            rectangles.append(cover_roi)
        if text_active and str(raw.get("text_vi") or "").strip():
            safe_area = layout.get("safe_area")
            if isinstance(safe_area, Mapping):
                rectangles.append(safe_area)
    return normalized_rect_mask(shape, rectangles)


def contains_cjk(text: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in str(text or ""))


def relative_artifact_path(path: Path, root: Path) -> str:
    """Return a portable artifact reference without leaking host-local roots."""

    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _compute_motion_scores(source_video: Path) -> dict[int, float]:
    import cv2

    capture = cv2.VideoCapture(str(source_video))
    if not capture.isOpened():
        raise AdaptiveOutputQaError("Cannot open source video for motion QA")
    scores: dict[int, float] = {}
    previous: np.ndarray | None = None
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            height, width = frame.shape[:2]
            target_width = min(320, width)
            target_height = max(1, int(round(height * target_width / max(1, width))))
            small = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            scores[index] = (
                0.0
                if previous is None
                else float(np.abs(gray.astype(np.float32) - previous.astype(np.float32)).mean())
            )
            previous = gray
            index += 1
    finally:
        capture.release()
    if not scores:
        raise AdaptiveOutputQaError("Source video has no decodable frames")
    return scores


def _read_selected_frames(path: Path, indices: set[int]) -> tuple[dict[int, np.ndarray], int]:
    import cv2

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise AdaptiveOutputQaError(f"Cannot open encoded media: {path.name}")
    frames: dict[int, np.ndarray] = {}
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            if index in indices:
                frames[index] = frame
            index += 1
    finally:
        capture.release()
    missing = sorted(indices - set(frames))
    if missing:
        raise AdaptiveOutputQaError(
            f"Encoded media is missing requested QA frames (first={missing[0]})"
        )
    return frames, index


def scan_full_timeline_visual_authority(
    source_video: str | Path,
    rendered_video: str | Path,
    *,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Lightweight every-frame check for missed edits and damaged source UI.

    Heavy OCR remains limited to selected suspicious frames. This scan compares
    the encoded result with source pixels on every active authority interval, so
    a one-frame CJK flash cannot hide between sampled QA frames.
    """

    import cv2

    source_cap = cv2.VideoCapture(str(source_video))
    rendered_cap = cv2.VideoCapture(str(rendered_video))
    if not source_cap.isOpened() or not rendered_cap.isOpened():
        source_cap.release()
        rendered_cap.release()
        raise AdaptiveOutputQaError("Cannot open media for full-timeline QA")
    render_tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    protected_tracks = [
        dict(row)
        for row in list(contract.get("protected_source_tracks") or [])
        if isinstance(row, Mapping)
        and str(
            dict(row.get("visual_provenance") or {}).get("classification") or ""
        )
        == "SOURCE_INTRINSIC"
        and float(
            dict(row.get("visual_provenance") or {}).get("confidence") or 0.0
        )
        >= 0.90
    ]
    missing_edit_frames: list[int] = []
    residual_stroke_frames: list[int] = []
    protected_damage_frames: list[int] = []
    decoded = 0

    def _visually_absent_noop(
        source_frame: np.ndarray,
        rendered_frame: np.ndarray,
        track: Mapping[str, Any],
        geometry: Mapping[str, Any],
    ) -> bool:
        """A persisted semantic epoch may span clean frames between labels.

        The renderer intentionally does not blur those frames.  Treating an
        unchanged ROI as a failure here made QA contradict the runtime
        presence gate and falsely blocked otherwise correct output.
        """
        context = dict(dict(track.get("render_policy") or {}).get("context") or {})
        if not context.get("caption_row") and not context.get("physical_presence_ranges"):
            return False
        ranges = []
        for raw in list(context.get("physical_presence_ranges") or []):
            if isinstance(raw, (list, tuple)) and len(raw) == 2:
                ranges.append((int(raw[0]), int(raw[1])))
        if ranges:
            # This helper is called from the frame loop; the caller supplies
            # the current index through a temporary field below.
            current = int(track.get("_qa_frame_index") or -1)
            if not any(start <= current <= end for start, end in ranges):
                return True
        return False

    def _roi_delta(
        source_frame: np.ndarray,
        rendered_frame: np.ndarray,
        geometry: Mapping[str, Any],
    ) -> float:
        height, width = source_frame.shape[:2]
        x0 = max(0, min(width - 1, int(float(geometry.get("x") or 0.0) * width)))
        y0 = max(0, min(height - 1, int(float(geometry.get("y") or 0.0) * height)))
        x1 = max(
            x0 + 1,
            min(width, int(round((float(geometry.get("x") or 0.0) + float(geometry.get("width") or 0.0)) * width))),
        )
        y1 = max(
            y0 + 1,
            min(height, int(round((float(geometry.get("y") or 0.0) + float(geometry.get("height") or 0.0)) * height))),
        )
        left = source_frame[y0:y1, x0:x1]
        right = rendered_frame[y0:y1, x0:x1]
        if left.size == 0 or right.size == 0:
            return 0.0
        return float(np.mean(cv2.absdiff(left, right), dtype=np.float64))

    def _unchanged_textness_fraction(
        source_frame: np.ndarray,
        rendered_frame: np.ndarray,
        track: Mapping[str, Any],
        geometry: Mapping[str, Any],
    ) -> tuple[float, int]:
        height, width = source_frame.shape[:2]
        x0 = max(0, min(width - 1, int(float(geometry.get("x") or 0.0) * width)))
        y0 = max(0, min(height - 1, int(float(geometry.get("y") or 0.0) * height)))
        x1 = max(
            x0 + 1,
            min(
                width,
                int(
                    round(
                        (
                            float(geometry.get("x") or 0.0)
                            + float(geometry.get("width") or 0.0)
                        )
                        * width
                    )
                ),
            ),
        )
        y1 = max(
            y0 + 1,
            min(
                height,
                int(
                    round(
                        (
                            float(geometry.get("y") or 0.0)
                            + float(geometry.get("height") or 0.0)
                        )
                        * height
                    )
                ),
            ),
        )
        source_roi = source_frame[y0:y1, x0:x1]
        rendered_roi = rendered_frame[y0:y1, x0:x1]
        if source_roi.size == 0 or rendered_roi.shape != source_roi.shape:
            return 0.0, 0
        gray = cv2.cvtColor(source_roi, cv2.COLOR_BGR2GRAY)
        context = dict(
            dict(track.get("render_policy") or {}).get("context") or {}
        )
        cover = dict(
            dict(track.get("render_policy") or {}).get("cover") or {}
        )
        soft_reconstruction_cover = str(cover.get("strategy") or "") == (
            "soft_reconstruction_plate_v1"
        )
        if bool(context.get("caption_row")) or soft_reconstruction_cover:
            # Generic textness treats hair, garment weave and jewellery as
            # glyph strokes, producing residual failures even when the source
            # caption is visibly gone.  Caption rows use the same physical
            # white-fill/dark-outline signature as the runtime presence gate.
            channel_spread = np.max(source_roi, axis=2).astype(np.int16) - np.min(
                source_roi, axis=2
            ).astype(np.int16)
            white_fill = (gray >= 172) & (channel_spread <= 92)
            dark_outline = gray <= 105
            outline_neighborhood = cv2.dilate(
                dark_outline.astype(np.uint8),
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
                iterations=1,
            ) > 0
            textness = white_fill & outline_neighborhood
            textness = cv2.dilate(
                textness.astype(np.uint8),
                np.ones((3, 3), dtype=np.uint8),
                iterations=1,
            ) > 0
        else:
            textness = local_textness_mask(gray) > 0
        pixels = int(np.count_nonzero(textness))
        if pixels < 12:
            return 0.0, pixels
        delta = np.max(
            cv2.absdiff(source_roi, rendered_roi), axis=2
        )
        unchanged = int(np.count_nonzero((delta <= 8) & textness))
        return unchanged / float(pixels), pixels

    def _caption_glyph_signature(
        source_frame: np.ndarray,
        track: Mapping[str, Any],
        geometry: Mapping[str, Any],
    ) -> tuple[float, int]:
        """Measure structured caption strokes, excluding generic texture.

        A global textness mask sees fabric, hair and jewellery as glyphs.  For
        a caption authority we require multiple similarly sized components on
        one baseline, with a meaningful horizontal span.  This mirrors the
        renderer's outlined-caption presence rule but uses a slightly wider
        luminance/edge fallback for dark or compressed subtitle styles.
        """
        height, width = source_frame.shape[:2]
        x0 = max(0, int((float(geometry.get("x") or 0.0) - 0.012) * width))
        y0 = max(0, int((float(geometry.get("y") or 0.0) - 0.012) * height))
        x1 = min(width, int((float(geometry.get("x") or 0.0) + float(geometry.get("width") or 0.0) + 0.012) * width))
        y1 = min(height, int((float(geometry.get("y") or 0.0) + float(geometry.get("height") or 0.0) + 0.012) * height))
        if x1 <= x0 or y1 <= y0:
            return 0.0, 0
        crop = source_frame[y0:y1, x0:x1]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        spread = np.max(crop, axis=2).astype(np.int16) - np.min(crop, axis=2).astype(np.int16)
        white = (gray >= 165) & (spread <= 105)
        dark = gray <= 110
        near_dark = cv2.dilate(
            dark.astype(np.uint8),
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
            iterations=1,
        ) > 0
        bright = white & near_dark
        # Dark/solid subtitles have no white fill. Use a local edge response,
        # but still constrain it to a single text row.
        if int(np.count_nonzero(bright)) < 12:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 4)).apply(gray)
            edge = cv2.Canny(clahe, 48, 136)
            bright = cv2.morphologyEx(
                edge,
                cv2.MORPH_CLOSE,
                cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1)),
            ) > 0
        count, _labels, stats, centroids = cv2.connectedComponentsWithStats(
            bright.astype(np.uint8), connectivity=8
        )
        glyphs: list[tuple[float, float, int, int, int]] = []
        crop_h, crop_w = crop.shape[:2]
        for index in range(1, count):
            cw = int(stats[index, cv2.CC_STAT_WIDTH])
            ch = int(stats[index, cv2.CC_STAT_HEIGHT])
            area = int(stats[index, cv2.CC_STAT_AREA])
            if (
                2 <= cw <= max(14, int(crop_w * 0.16))
                and 3 <= ch <= max(14, int(crop_h * 0.92))
                and area >= 4
            ):
                glyphs.append(
                    (
                        float(centroids[index][0]),
                        float(centroids[index][1]),
                        area,
                        cw,
                        ch,
                    )
                )
        if len(glyphs) < 3:
            return 0.0, len(glyphs)
        baseline_bin = max(4, int(round(crop_h * 0.16)))
        bins: dict[int, list[tuple[float, float, int, int, int]]] = {}
        for glyph in glyphs:
            bins.setdefault(int(round(glyph[1] / baseline_bin)), []).append(glyph)
        best_fraction = 0.0
        best_pixels = 0
        expected_center = crop_h * 0.5
        for values in bins.values():
            if len(values) < 3:
                continue
            span = max(value[0] for value in values) - min(value[0] for value in values)
            area = sum(value[2] for value in values)
            center = sum(value[1] for value in values) / len(values)
            if span < crop_w * 0.12 or area < 24 or abs(center - expected_center) > crop_h * 0.48:
                continue
            # Structured glyph density, not raw texture density.
            best_pixels = max(best_pixels, int(area))
            best_fraction = max(best_fraction, min(1.0, area / float(max(1, crop_w * max(1, crop_h)))))
        return best_fraction, best_pixels

    try:
        frame_index = 0
        while True:
            source_ok, source_frame = source_cap.read()
            rendered_ok, rendered_frame = rendered_cap.read()
            if not source_ok or not rendered_ok or source_frame is None or rendered_frame is None:
                break
            if source_frame.shape[:2] != rendered_frame.shape[:2]:
                break
            decoded += 1
            small_source = cv2.resize(source_frame, (96, 96), interpolation=cv2.INTER_AREA)
            small_rendered = cv2.resize(rendered_frame, (96, 96), interpolation=cv2.INTER_AREA)
            global_delta = float(
                np.mean(cv2.absdiff(small_source, small_rendered), dtype=np.float64)
            )
            active = active_tracks_for_frame(
                contract,
                frame_index,
                source_frame_bgr=source_frame,
            )
            if active:
                for row in active:
                    row["_qa_frame_index"] = frame_index
                active_geometries = [
                    dict(
                        dict(
                            dict(row.get("render_policy") or {}).get("cover") or {}
                        ).get("roi")
                        or row.get("geometry")
                        or {}
                    )
                    for row in active
                ]
                deltas = [
                    _roi_delta(source_frame, rendered_frame, geometry)
                    for geometry in active_geometries
                ]
                # ``active_tracks_for_frame`` has already applied observed
                # glyph-presence gating to semantic lead/tail intervals.  A
                # frame is missing an edit only when every active authority is
                # effectively unchanged; using ``min`` mislabeled one
                # unchanged semantic sibling even when another cover on the
                # same frame was correctly rendered.
                absent_noop = all(
                    _visually_absent_noop(source_frame, rendered_frame, row, geometry)
                    for row, geometry in zip(active, active_geometries)
                )
                glyph_evidence = [
                    _caption_glyph_signature(source_frame, row, geometry)
                    for row, geometry in zip(active, active_geometries)
                    if bool(dict(dict(row.get("render_policy") or {}).get("context") or {}).get("caption_row"))
                ]
                has_caption_glyph_evidence = any(
                    pixels >= 24 and fraction >= 0.002
                    for fraction, pixels in glyph_evidence
                )
                if deltas and max(deltas) <= 2.0 and not absent_noop and (
                    not glyph_evidence or has_caption_glyph_evidence
                ):
                    missing_edit_frames.append(frame_index)
                residual_entries = [
                    (
                        _unchanged_textness_fraction(
                            source_frame, rendered_frame, row, geometry
                        ),
                        row,
                        geometry,
                    )
                    for row, geometry in zip(active, active_geometries)
                    if not bool(row.get("transition_hold_cover_only"))
                    and not bool(
                        dict(
                            dict(row.get("render_policy") or {}).get("context")
                            or {}
                        ).get("stacked_caption_sibling_cover_extension")
                    )
                ]
                if any(
                    pixels >= 24 and fraction >= 0.30
                    and not _visually_absent_noop(
                        source_frame, rendered_frame, row, geometry
                    )
                    and (
                        not bool(dict(dict(row.get("render_policy") or {}).get("context") or {}).get("caption_row"))
                        or _caption_glyph_signature(source_frame, row, geometry)[1] >= 24
                    )
                    for (fraction, pixels), row, geometry in residual_entries
                ):
                    residual_stroke_frames.append(frame_index)
            active_protected = [
                dynamic_track_for_frame(row, frame_index)
                for row in protected_tracks
                if int(row.get("start_frame") or 0)
                <= frame_index
                <= int(row.get("end_frame") or -1)
            ]
            if active_protected:
                deltas = [
                    _roi_delta(source_frame, rendered_frame, dict(row.get("geometry") or {}))
                    for row in active_protected
                ]
                if deltas and max(deltas) > max(14.0, global_delta * 2.75 + 4.0):
                    protected_damage_frames.append(frame_index)
            frame_index += 1
    finally:
        source_cap.release()
        rendered_cap.release()
    return {
        "policy_version": "full_timeline_visual_authority_v1",
        "decoded_frames": decoded,
        "status": (
            "BLOCKED"
            if missing_edit_frames or protected_damage_frames
            or residual_stroke_frames
            else "PASS"
        ),
        "missing_edit_frames": missing_edit_frames,
        "residual_stroke_frames": residual_stroke_frames,
        "protected_source_damage_frames": protected_damage_frames,
    }


OUTPUT_QA_CONTACT_SHEET_MAX_ROWS = 120
OUTPUT_QA_CONTACT_SHEET_MAX_HEIGHT = 12_000


def _write_contact_sheet(
    path: Path,
    indices: Sequence[int],
    source_frames: Mapping[int, np.ndarray],
    rendered_frames: Mapping[int, np.ndarray],
) -> None:
    import cv2

    contact_indices = list(indices)
    if not contact_indices:
        raise AdaptiveOutputQaError("Cannot write an empty output QA contact sheet")
    rows: list[np.ndarray] = []
    thumb_width = 360
    first_height, first_width = source_frames[contact_indices[0]].shape[:2]
    first_thumb_height = max(
        1, int(round(first_height * thumb_width / max(1, first_width)))
    )
    # JPEG encoders reject very tall images (the common hard ceiling is 65,535
    # px). A 9:16 video makes every 360 px thumbnail 640 px tall, so the old
    # fixed 120-row sheet reached 76,800 px and failed after an otherwise valid
    # render. Bound rows by the actual portrait thumbnail height and sample the
    # complete timeline uniformly.
    max_contact_rows = min(
        OUTPUT_QA_CONTACT_SHEET_MAX_ROWS,
        max(1, OUTPUT_QA_CONTACT_SHEET_MAX_HEIGHT // first_thumb_height),
    )
    if len(contact_indices) > max_contact_rows:
        positions = np.linspace(0, len(contact_indices) - 1, num=max_contact_rows)
        contact_indices = [
            contact_indices[int(round(position))] for position in positions
        ]
    for index in contact_indices:
        source = source_frames[index]
        rendered = rendered_frames[index]
        height, width = source.shape[:2]
        thumb_height = max(1, int(round(height * thumb_width / max(1, width))))
        size = (thumb_width, thumb_height)
        source_thumb = cv2.resize(source, size, interpolation=cv2.INTER_AREA)
        render_thumb = cv2.resize(rendered, size, interpolation=cv2.INTER_AREA)
        diff = cv2.absdiff(source, rendered)
        diff_thumb = cv2.resize(diff, size, interpolation=cv2.INTER_AREA)
        row = np.concatenate((source_thumb, render_thumb, diff_thumb), axis=1)
        cv2.putText(
            row,
            f"frame {index} | SOURCE / RENDER / ABS DIFF",
            (8, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), np.concatenate(rows, axis=0)):
        raise AdaptiveOutputQaError("Cannot write output QA contact sheet")


def _duration_seconds(authority: Mapping[str, Any]) -> float:
    try:
        return float(authority.get("duration_seconds") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _frame_count(authority: Mapping[str, Any], decoded_count: int) -> int:
    timestamps = list(authority.get("frame_timestamps_seconds") or [])
    return len(timestamps) if timestamps else int(decoded_count)


def _color_authority_matches(
    source_authority: Mapping[str, Any], rendered_authority: Mapping[str, Any]
) -> tuple[bool, dict[str, Any]]:
    source = dict(source_authority.get("video") or {})
    rendered = dict(rendered_authority.get("video") or {})
    fields = ("color_range", "color_space", "color_transfer", "color_primaries")
    comparison = {
        field: {"source": source.get(field), "rendered": rendered.get(field)}
        for field in fields
    }
    matches = all(
        source.get(field) in (None, "unknown")
        or rendered.get(field) == source.get(field)
        for field in fields
    )
    return matches, comparison


def _detect_residual_cjk(
    *,
    provider: Any | None,
    rendered_paths: Mapping[int, Path],
    fps: float,
) -> tuple[bool, list[dict[str, Any]], str | None]:
    if provider is None:
        return False, [], "local_ocr_provider_missing"
    residual: list[dict[str, Any]] = []
    try:
        for frame_index, path in sorted(rendered_paths.items()):
            frame_time_ms = int(round(frame_index * 1000.0 / max(1.0, fps)))
            result = provider.detect_frame(path, frame_time_ms=frame_time_ms)
            for box in list(getattr(result, "boxes", []) or []):
                text = str(getattr(box, "text", "") or "").strip()
                confidence = float(getattr(box, "confidence", 0.0) or 0.0)
                if confidence < 0.25 or not contains_cjk(text):
                    continue
                residual.append(
                    {
                        "frame_index": frame_index,
                        "text": text,
                        "confidence": round(confidence, 4),
                        "geometry": {
                            "x": float(getattr(box, "x", 0.0) or 0.0),
                            "y": float(getattr(box, "y", 0.0) or 0.0),
                            "width": float(getattr(box, "width", 0.0) or 0.0),
                            "height": float(getattr(box, "height", 0.0) or 0.0),
                        },
                    }
                )
    except Exception as exc:  # Provider failures become a fail-closed QA result.
        return False, residual, f"local_ocr_failed:{type(exc).__name__}"
    return True, residual, None


def _normalized_rect(raw: Mapping[str, Any]) -> tuple[float, float, float, float]:
    geometry = dict(raw.get("geometry") or {})
    x = float(geometry.get("x") or 0.0)
    y = float(geometry.get("y") or 0.0)
    width = float(geometry.get("width") or 0.0)
    height = float(geometry.get("height") or 0.0)
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


def _rect_area_similarity(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    larger = max(left_area, right_area)
    return min(left_area, right_area) / larger if larger > 0.0 else 0.0


def _cjk_chars(text: str) -> set[str]:
    return {
        char
        for char in str(text or "")
        if "\u3400" <= char <= "\u4dbf"
        or "\u4e00" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
    }


def classify_source_scene_protected_cjk(
    detections: Sequence[Mapping[str, Any]],
    *,
    contract: Mapping[str, Any],
    source_detections: Sequence[Mapping[str, Any]] = (),
    source_frames: Mapping[int, np.ndarray] | None = None,
    rendered_frames: Mapping[int, np.ndarray] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exclude CJK that belongs to a hash-bound source-scene text plane.

    The exclusion is deliberately subordinate to active editor authority.  A
    detection that intersects an editor overlay cover or Vietnamese layout is
    still blocking even when the broader filmed device region is protected.
    """

    regions = [
        dict(row)
        for row in list(contract.get("source_scene_text_regions") or [])
        if isinstance(row, Mapping)
        and str(row.get("classification") or "") == "SOURCE_SCENE_TEXT"
    ]
    editor_tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
        and (
            is_editor_caption_track(row)
            or bool(
                dict(
                    dict(dict(row).get("render_policy") or {}).get("context")
                    or {}
                ).get("supplemental_cover_only")
            )
        )
    ]
    source_tracks = [
        dict(row)
        for row in list(contract.get("source_scene_text_tracks") or [])
        if isinstance(row, Mapping)
        and str(row.get("classification") or "") == "SOURCE_SCENE_TEXT"
    ]
    caption_start = min(
        (int(row.get("start_frame") or 0) for row in editor_tracks),
        default=0,
    )
    caption_end = max(
        (int(row.get("end_frame") or 0) for row in editor_tracks),
        default=-1,
    )
    blocking: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    source_by_frame: dict[int, list[dict[str, Any]]] = {}
    for raw in source_detections:
        if isinstance(raw, Mapping):
            source_by_frame.setdefault(
                int(raw.get("frame_index") or 0), []
            ).append(dict(raw))
    for raw in detections:
        row = dict(raw)
        frame_index = int(row.get("frame_index") or 0)
        detection_rect = _normalized_rect(row)
        matched_region: dict[str, Any] | None = None
        for region in regions:
            if not (
                int(region.get("start_frame") or 0)
                <= frame_index
                <= int(region.get("end_frame") or -1)
            ):
                continue
            roi = dict(region.get("region_roi") or {})
            region_rect = (
                float(roi.get("x") or 0.0),
                float(roi.get("y") or 0.0),
                float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0),
                float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0),
            )
            if _intersection_over_smaller(detection_rect, region_rect) >= 0.80:
                matched_region = region
                break
        if matched_region is None:
            blocking.append(row)
            continue

        overlapping_editor_ids: list[str] = []
        for track in editor_tracks:
            if not (
                int(track.get("start_frame") or 0)
                <= frame_index
                <= int(track.get("end_frame") or 0)
            ):
                continue
            policy = dict(track.get("render_policy") or {})
            cover = dict(policy.get("cover") or {})
            layout = dict(policy.get("layout") or {})
            authority_rois = [cover.get("roi") or track.get("geometry")]
            geometry = track.get("geometry")
            if isinstance(geometry, Mapping):
                authority_rois.append(geometry)
            if any(
                isinstance(roi, Mapping)
                and _intersection_over_smaller(
                    detection_rect,
                    (
                        float(roi.get("x") or 0.0),
                        float(roi.get("y") or 0.0),
                        float(roi.get("x") or 0.0)
                        + float(roi.get("width") or 0.0),
                        float(roi.get("y") or 0.0)
                        + float(roi.get("height") or 0.0),
                    ),
                )
                >= 0.50
                for roi in authority_rois
            ):
                overlapping_editor_ids.append(str(track.get("text_id") or ""))
        if overlapping_editor_ids:
            geometry = dict(row.get("geometry") or {})
            rendered_chars = _cjk_chars(str(row.get("text") or ""))
            matched_source: dict[str, Any] | None = None
            for candidate in source_by_frame.get(frame_index, []):
                source_chars = _cjk_chars(str(candidate.get("text") or ""))
                union = rendered_chars | source_chars
                cjk_similarity = (
                    len(rendered_chars & source_chars) / len(union)
                    if union
                    else 0.0
                )
                overlap = _intersection_over_smaller(
                    detection_rect, _normalized_rect(candidate)
                )
                # OCR text can vary across source/render downscales. Geometry
                # plus source CJK presence is sufficient here; pixel binding
                # below remains the fail-closed guard against editor leakage.
                if overlap >= 0.30 and source_chars:
                    matched_source = {
                        "text": candidate.get("text"),
                        "confidence": candidate.get("confidence"),
                        "geometry": candidate.get("geometry"),
                        "geometry_overlap": round(overlap, 6),
                        "cjk_similarity": round(cjk_similarity, 6),
                    }
                    break
            patch_similarity = _source_render_patch_similarity(
                row,
                source_frame=(source_frames or {}).get(frame_index),
                rendered_frame=(rendered_frames or {}).get(frame_index),
            )
            supplemental_overlap = any(
                bool(
                    dict(
                        dict(track.get("render_policy") or {}).get("context")
                        or {}
                    ).get("supplemental_cover_only")
                )
                for track in editor_tracks
                if str(track.get("text_id") or "") in overlapping_editor_ids
            )
            editor_geometry_overlap = any(
                int(track.get("start_frame") or 0)
                <= frame_index
                <= int(track.get("end_frame") or -1)
                and _intersection_over_smaller(
                    detection_rect,
                    _normalized_rect({"geometry": track.get("geometry")}),
                )
                >= 0.50
                for track in editor_tracks
                if str(track.get("text_id") or "") in overlapping_editor_ids
            )
            source_pixels_verified = (
                not supplemental_overlap
                and patch_similarity is not None
                and not editor_geometry_overlap
                and float(geometry.get("width") or 0.0)
                <= SOURCE_SCENE_EDITOR_OVERLAP_MAX_WIDTH
                and float(geometry.get("height") or 0.0)
                <= SOURCE_SCENE_EDITOR_OVERLAP_MAX_HEIGHT
                and patch_similarity["mean_abs_delta"]
                <= SOURCE_SCENE_EDITOR_OVERLAP_MAX_MEAN_DELTA
                and patch_similarity["p95_abs_delta"]
                <= SOURCE_SCENE_EDITOR_OVERLAP_MAX_P95_DELTA
            )
            if source_pixels_verified:
                excluded.append(
                    {
                        **row,
                        "classification": (
                            "SOURCE_SCENE_TEXT_PROTECTED_OVERLAPPING_EDITOR_VERIFIED"
                        ),
                        "source_scene_region": {
                            "region_id": matched_region.get("region_id"),
                            "start_frame": matched_region.get("start_frame"),
                            "end_frame": matched_region.get("end_frame"),
                            "region_roi": matched_region.get("region_roi"),
                        },
                        "matched_source": matched_source,
                        "source_render_patch": {
                            key: round(value, 6)
                            for key, value in patch_similarity.items()
                        },
                        "overlapping_editor_text_ids": sorted(
                            value for value in overlapping_editor_ids if value
                        ),
                    }
                )
                continue
            blocking.append(
                {
                    **row,
                    "source_scene_protection": {
                        "status": "BLOCKED_BY_ACTIVE_EDITOR_AUTHORITY",
                        "region_id": matched_region.get("region_id"),
                        "editor_text_ids": sorted(
                            value for value in overlapping_editor_ids if value
                        ),
                    },
                }
            )
            continue
        source_track_ids: list[str] = []
        for track in source_tracks:
            if not (
                int(track.get("start_frame") or 0)
                <= frame_index
                <= int(track.get("end_frame") or 0)
            ):
                continue
            geometry = dict(track.get("geometry") or {})
            source_rect = (
                float(geometry.get("x") or 0.0),
                float(geometry.get("y") or 0.0),
                float(geometry.get("x") or 0.0) + float(geometry.get("width") or 0.0),
                float(geometry.get("y") or 0.0) + float(geometry.get("height") or 0.0),
            )
            if _intersection_over_smaller(detection_rect, source_rect) >= 0.50:
                source_track_ids.append(str(track.get("text_id") or ""))
        geometry = dict(row.get("geometry") or {})
        detection_width = float(geometry.get("width") or 0.0)
        detection_y = float(geometry.get("y") or 0.0)
        detection_center_x = float(geometry.get("x") or 0.0) + detection_width / 2.0
        persistent_caption_lane = (
            caption_start <= frame_index <= caption_end
            and detection_y >= 0.90
            and detection_width >= 0.20
            and 0.20 <= detection_center_x <= 0.80
        )
        if persistent_caption_lane and not source_track_ids:
            blocking.append(
                {
                    **row,
                    "source_scene_protection": {
                        "status": "BLOCKED_BY_PERSISTENT_EDITOR_CAPTION_LANE",
                        "region_id": matched_region.get("region_id"),
                    },
                }
            )
            continue
        excluded.append(
            {
                **row,
                "classification": "SOURCE_SCENE_TEXT_PROTECTED",
                "source_scene_region": {
                    "region_id": matched_region.get("region_id"),
                    "start_frame": matched_region.get("start_frame"),
                    "end_frame": matched_region.get("end_frame"),
                    "region_roi": matched_region.get("region_roi"),
                },
                **(
                    {"source_scene_track_ids": sorted(source_track_ids)}
                    if source_track_ids
                    else {}
                ),
            }
        )
    return blocking, excluded


def _source_render_patch_similarity(
    detection: Mapping[str, Any],
    *,
    source_frame: np.ndarray | None,
    rendered_frame: np.ndarray | None,
) -> dict[str, float] | None:
    """Measure a detected patch across source/render without resizing either frame."""
    if source_frame is None or rendered_frame is None:
        return None
    source = np.asarray(source_frame)
    rendered = np.asarray(rendered_frame)
    if (
        source.ndim != 3
        or rendered.ndim != 3
        or source.shape != rendered.shape
        or source.size == 0
    ):
        return None
    height, width = source.shape[:2]
    rect = _normalized_rect(detection)
    x0 = max(0, min(width, int(np.floor(rect[0] * width))))
    y0 = max(0, min(height, int(np.floor(rect[1] * height))))
    x1 = max(0, min(width, int(np.ceil(rect[2] * width))))
    y1 = max(0, min(height, int(np.ceil(rect[3] * height))))
    if x1 <= x0 or y1 <= y0:
        return None
    delta = np.abs(
        source[y0:y1, x0:x1].astype(np.int16)
        - rendered[y0:y1, x0:x1].astype(np.int16)
    )
    pixel_height = y1 - y0
    return {
        "mean_abs_delta": float(np.mean(delta)),
        "p95_abs_delta": float(np.percentile(delta, 95)),
        "pixel_aspect": float((x1 - x0) / pixel_height),
    }


def classify_source_intrinsic_edge_cjk(
    rendered_detections: Sequence[Mapping[str, Any]],
    source_detections: Sequence[Mapping[str, Any]],
    *,
    contract: Mapping[str, Any],
    source_frames: Mapping[int, np.ndarray] | None = None,
    rendered_frames: Mapping[int, np.ndarray] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Exclude narrowly evidenced source print or tiny texture false positives.

    The texture path remains deliberately fail-closed: it requires a single CJK
    recognition in an unusually tall/narrow, sub-0.06% box, no source OCR match,
    no overlap with an active cover, and near-identical source/render pixels.
    """
    source_by_frame: dict[int, list[dict[str, Any]]] = {}
    for raw in source_detections:
        source_by_frame.setdefault(int(raw.get("frame_index") or 0), []).append(
            dict(raw)
        )
    blocking: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for raw in rendered_detections:
        row = dict(raw)
        frame_index = int(row.get("frame_index") or 0)
        rect = _normalized_rect(row)
        area = max(0.0, rect[2] - rect[0]) * max(0.0, rect[3] - rect[1])
        in_edge_gutter = (
            rect[2] <= SOURCE_INTRINSIC_EDGE_GUTTER
            or rect[0] >= 1.0 - SOURCE_INTRINSIC_EDGE_GUTTER
        )
        overlaps_authority = False
        runtime_tracks = active_tracks_for_frame(
            contract,
            frame_index,
            source_frame_bgr=(source_frames or {}).get(frame_index),
        )
        for track in runtime_tracks:
            roi = dict(
                dict(dict(track.get("render_policy") or {}).get("cover") or {}).get(
                    "roi"
                )
                or {}
            )
            if not roi:
                continue
            authority_rect = (
                float(roi.get("x") or 0.0),
                float(roi.get("y") or 0.0),
                float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0),
                float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0),
            )
            if _intersection_over_smaller(rect, authority_rect) >= 0.10:
                overlaps_authority = True
                break
        matched_source: dict[str, Any] | None = None
        rendered_chars = _cjk_chars(str(row.get("text") or ""))
        overlapping_source = False
        low_confidence_source_texture_match = False
        matched_source_texture = False
        small_matched_source: dict[str, Any] | None = None
        for candidate in source_by_frame.get(frame_index, []):
            source_rect = _normalized_rect(candidate)
            source_overlap = _intersection_over_smaller(rect, source_rect)
            if source_overlap >= 0.30:
                overlapping_source = True
            source_chars = _cjk_chars(str(candidate.get("text") or ""))
            source_area_similarity = _rect_area_similarity(rect, source_rect)
            if (
                len(rendered_chars) == 1
                and source_chars == rendered_chars
                and source_overlap
                >= SOURCE_INTRINSIC_SMALL_MATCHED_MIN_GEOMETRY_OVERLAP
                and source_area_similarity
                >= SOURCE_INTRINSIC_SMALL_MATCHED_MIN_AREA_SIMILARITY
            ):
                small_matched_source = {
                    "text": candidate.get("text"),
                    "confidence": candidate.get("confidence"),
                    "geometry": candidate.get("geometry"),
                    "geometry_overlap": round(source_overlap, 6),
                    "geometry_area_similarity": round(source_area_similarity, 6),
                }
            if (
                len(rendered_chars) == 1
                and source_chars == rendered_chars
                and source_overlap >= 0.60
                and source_area_similarity >= 0.50
            ):
                matched_source_texture = True
            if (
                len(rendered_chars) == 1
                and source_chars == rendered_chars
                and float(candidate.get("confidence") or 0.0)
                <= SOURCE_INTRINSIC_LOW_CONF_TEXTURE_MAX_CONFIDENCE
                and source_overlap >= RESIDUAL_SOURCE_TEXTURE_MIN_GEOMETRY_OVERLAP
                and source_area_similarity >= RESIDUAL_SOURCE_TEXTURE_MIN_AREA_SIMILARITY
            ):
                low_confidence_source_texture_match = True
        if in_edge_gutter and area <= SOURCE_INTRINSIC_MAX_AREA and not overlaps_authority:
            for candidate in source_by_frame.get(frame_index, []):
                source_chars = _cjk_chars(str(candidate.get("text") or ""))
                union = rendered_chars | source_chars
                similarity = len(rendered_chars & source_chars) / len(union) if union else 0.0
                overlap = _intersection_over_smaller(
                    rect, _normalized_rect(candidate)
                )
                if overlap >= 0.60 and similarity >= 0.25:
                    matched_source = {
                        "text": candidate.get("text"),
                        "confidence": candidate.get("confidence"),
                        "geometry": candidate.get("geometry"),
                        "geometry_overlap": round(overlap, 6),
                        "cjk_similarity": round(similarity, 6),
                    }
                    break
        if matched_source is not None:
            excluded.append(
                {
                    **row,
                    "classification": "SOURCE_INTRINSIC_EDGE_PRINT",
                    "matched_source": matched_source,
                }
            )
            continue

        patch_similarity = _source_render_patch_similarity(
            row,
            source_frame=(source_frames or {}).get(frame_index),
            rendered_frame=(rendered_frames or {}).get(frame_index),
        )
        is_tiny_texture_false_positive = (
            len(rendered_chars) == 1
            and area <= SOURCE_INTRINSIC_TEXTURE_MAX_AREA
            and not overlaps_authority
            and not overlapping_source
            and patch_similarity is not None
            and patch_similarity["pixel_aspect"]
            <= SOURCE_INTRINSIC_TEXTURE_MAX_PIXEL_ASPECT
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_TEXTURE_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_TEXTURE_MAX_P95_DELTA
        )
        is_low_confidence_texture_false_positive = (
            len(rendered_chars) == 1
            and area <= SOURCE_INTRINSIC_LOW_CONF_TEXTURE_MAX_AREA
            and float(row.get("confidence") or 0.0)
            <= SOURCE_INTRINSIC_LOW_CONF_TEXTURE_MAX_CONFIDENCE
            and not overlaps_authority
            and (
                not overlapping_source or low_confidence_source_texture_match
            )
            and patch_similarity is not None
            and patch_similarity["pixel_aspect"]
            <= SOURCE_INTRINSIC_LOW_CONF_TEXTURE_MAX_PIXEL_ASPECT
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_TEXTURE_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_TEXTURE_MAX_P95_DELTA
        )
        bounded_texture = (
            len(rendered_chars) == 1
            and area <= SOURCE_INTRINSIC_BOUNDED_TEXTURE_MAX_AREA
            and float(rect[2] - rect[0]) <= SOURCE_INTRINSIC_BOUNDED_TEXTURE_MAX_WIDTH
            and float(rect[3] - rect[1]) <= SOURCE_INTRINSIC_BOUNDED_TEXTURE_MAX_HEIGHT
            and float(row.get("confidence") or 0.0)
            <= SOURCE_INTRINSIC_BOUNDED_TEXTURE_MAX_CONFIDENCE
            and not overlaps_authority
            and patch_similarity is not None
            and patch_similarity["pixel_aspect"]
            <= SOURCE_INTRINSIC_BOUNDED_TEXTURE_MAX_PIXEL_ASPECT
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_TEXTURE_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_TEXTURE_MAX_P95_DELTA
        )
        large_unchanged_texture = (
            len(rendered_chars) == 1
            and area <= SOURCE_INTRINSIC_LARGE_TEXTURE_MAX_AREA
            and float(rect[2] - rect[0]) <= SOURCE_INTRINSIC_LARGE_TEXTURE_MAX_WIDTH
            and float(rect[3] - rect[1]) <= SOURCE_INTRINSIC_LARGE_TEXTURE_MAX_HEIGHT
            and float(row.get("confidence") or 0.0)
            >= SOURCE_INTRINSIC_LARGE_TEXTURE_MIN_CONFIDENCE
            and not overlaps_authority
            and not overlapping_source
            and patch_similarity is not None
            and patch_similarity["pixel_aspect"]
            <= SOURCE_INTRINSIC_LARGE_TEXTURE_MAX_PIXEL_ASPECT
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_TEXTURE_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_TEXTURE_MAX_P95_DELTA
        )
        edge_unchanged_texture = (
            in_edge_gutter
            and area <= SOURCE_INTRINSIC_EDGE_PIXEL_MAX_AREA
            and not overlaps_authority
            and patch_similarity is not None
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_TEXTURE_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_TEXTURE_MAX_P95_DELTA
        )
        matched_unchanged_texture = (
            len(rendered_chars) == 1
            and SOURCE_INTRINSIC_MATCHED_TEXTURE_MIN_AREA
            <= area
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_AREA
            and matched_source_texture
            and not overlaps_authority
            and patch_similarity is not None
            and patch_similarity["pixel_aspect"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_PIXEL_ASPECT
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_P95_DELTA
        )
        small_matched_unchanged_print = (
            len(rendered_chars) == 1
            and SOURCE_INTRINSIC_SMALL_MATCHED_MIN_AREA
            <= area
            <= SOURCE_INTRINSIC_SMALL_MATCHED_MAX_AREA
            and small_matched_source is not None
            # A render-side detector can become overconfident after codec
            # sharpening.  Use the source-side confidence for provenance: a
            # true source caption is high-confidence in the unmodified frame;
            # a low-confidence source glyph that survives byte-for-byte is
            # scene texture/printed decoration.
            and float(small_matched_source.get("confidence") or 0.0)
            <= SOURCE_INTRINSIC_SMALL_MATCHED_MAX_CONFIDENCE
            and not overlaps_authority
            and patch_similarity is not None
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_SMALL_MATCHED_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_SMALL_MATCHED_MAX_P95_DELTA
        )
        wide_low_confidence_texture = (
            len(rendered_chars) == 1
            and area <= SOURCE_INTRINSIC_WIDE_TEXTURE_MAX_AREA
            and float(row.get("confidence") or 0.0)
            <= SOURCE_INTRINSIC_WIDE_TEXTURE_MAX_CONFIDENCE
            and not overlaps_authority
            and patch_similarity is not None
            and SOURCE_INTRINSIC_WIDE_TEXTURE_MIN_PIXEL_ASPECT
            <= patch_similarity["pixel_aspect"]
            <= SOURCE_INTRINSIC_WIDE_TEXTURE_MAX_PIXEL_ASPECT
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_P95_DELTA
        )
        object_print_unchanged = (
            1
            <= len(rendered_chars)
            <= SOURCE_INTRINSIC_OBJECT_PRINT_MAX_CHARS
            and SOURCE_INTRINSIC_OBJECT_PRINT_MIN_AREA
            <= area
            <= SOURCE_INTRINSIC_OBJECT_PRINT_MAX_AREA
            and float(row.get("confidence") or 0.0)
            <= SOURCE_INTRINSIC_OBJECT_PRINT_MAX_CONFIDENCE
            and not overlaps_authority
            and patch_similarity is not None
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_P95_DELTA
        )
        off_lane_source_texture = (
            1 <= len(rendered_chars) <= 2
            and area <= SOURCE_INTRINSIC_OFF_LANE_TEXTURE_MAX_AREA
            and float(rect[1]) <= SOURCE_INTRINSIC_OFF_LANE_TEXTURE_MAX_Y
            and float(row.get("confidence") or 0.0)
            <= SOURCE_INTRINSIC_OFF_LANE_TEXTURE_MAX_CONFIDENCE
            and not overlaps_authority
            and patch_similarity is not None
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_P95_DELTA
        )
        large_low_confidence_source_texture = (
            1 <= len(rendered_chars) <= 2
            and SOURCE_INTRINSIC_MATCHED_TEXTURE_MIN_AREA
            <= area
            <= SOURCE_INTRINSIC_LARGE_LOW_CONF_TEXTURE_MAX_AREA
            and float(row.get("confidence") or 0.0)
            <= SOURCE_INTRINSIC_LARGE_LOW_CONF_TEXTURE_MAX_CONFIDENCE
            and not overlaps_authority
            and patch_similarity is not None
            and patch_similarity["mean_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_MEAN_DELTA
            and patch_similarity["p95_abs_delta"]
            <= SOURCE_INTRINSIC_MATCHED_TEXTURE_MAX_P95_DELTA
        )
        if (
            is_tiny_texture_false_positive
            or is_low_confidence_texture_false_positive
            or bounded_texture
            or large_unchanged_texture
            or edge_unchanged_texture
            or matched_unchanged_texture
            or small_matched_unchanged_print
            or wide_low_confidence_texture
            or object_print_unchanged
            or off_lane_source_texture
            or large_low_confidence_source_texture
        ):
            excluded.append(
                {
                    **row,
                    "classification": "SOURCE_INTRINSIC_TEXTURE_FALSE_POSITIVE",
                    "policy_branch": (
                        "low_confidence_texture"
                        if is_low_confidence_texture_false_positive
                        else (
                            "bounded_source_texture"
                            if bounded_texture
                            else (
                                "large_unchanged_scene_texture"
                                if large_unchanged_texture
                                else (
                                    "edge_unchanged_source_print"
                                    if edge_unchanged_texture
                                    else (
                                        "matched_unchanged_scene_texture"
                                        if matched_unchanged_texture
                                        else (
                                        "small_matched_unchanged_source_print"
                                        if small_matched_unchanged_print
                                        else (
                                        "wide_low_confidence_texture"
                                        if wide_low_confidence_texture
                                        else (
                                        "object_print_unchanged"
                                        if object_print_unchanged
                                        else "off_lane_source_texture"
                                        if off_lane_source_texture
                                        else "large_low_confidence_source_texture"
                                        if large_low_confidence_source_texture
                                        else "tiny_texture"
                                        )
                                        )
                                        )
                                    )
                                )
                            )
                        )
                    ),
                    "source_render_patch": {
                        key: round(value, 6)
                        for key, value in patch_similarity.items()
                    },
                    **(
                        {"matched_source": small_matched_source}
                        if small_matched_unchanged_print
                        else {}
                    ),
                }
            )
        else:
            blocking.append(row)
    return blocking, excluded


def propagate_source_intrinsic_cjk_exclusions(
    detections: Sequence[Mapping[str, Any]],
    source_intrinsic_exclusions: Sequence[Mapping[str, Any]],
    *,
    contract: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Propagate pixel-proven source texture evidence by one adjacent frame.

    Residual OCR is intentionally sampled at caption boundaries, where the same
    physical texture may be recognized on two consecutive frames.  If one of
    those detections has already been proven unchanged between source/render,
    the adjacent matching glyph should inherit that provenance instead of
    becoming a temporal confirmation of a false positive.

    The propagation remains fail-closed: it requires the exact CJK signature,
    near-identical geometry, an adjacent frame, and pixel-bound provenance.  It
    is never applied inside an active editor-caption cover.
    """
    proven = [
        dict(row)
        for row in source_intrinsic_exclusions
        if row.get("classification")
        == "SOURCE_INTRINSIC_TEXTURE_FALSE_POSITIVE"
        and isinstance(row.get("source_render_patch"), Mapping)
        and bool(row.get("source_render_patch"))
    ]
    tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    blocking: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for raw in detections:
        row = dict(raw)
        frame_index = int(row.get("frame_index") or 0)
        rect = _normalized_rect(row)
        chars = _cjk_chars(str(row.get("text") or ""))

        overlaps_active_authority = False
        for track in tracks:
            if not (
                int(track.get("start_frame") or 0)
                <= frame_index
                <= int(track.get("end_frame") or 0)
            ):
                continue
            roi = dict(
                dict(dict(track.get("render_policy") or {}).get("cover") or {}).get(
                    "roi"
                )
                or {}
            )
            if not roi:
                continue
            authority_rect = (
                float(roi.get("x") or 0.0),
                float(roi.get("y") or 0.0),
                float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0),
                float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0),
            )
            if _intersection_over_smaller(rect, authority_rect) >= 0.10:
                overlaps_active_authority = True
                break
        if overlaps_active_authority:
            blocking.append(row)
            continue

        provenance_match: dict[str, Any] | None = None
        for candidate in proven:
            candidate_frame = int(candidate.get("frame_index") or 0)
            if abs(frame_index - candidate_frame) != 1:
                continue
            candidate_chars = _cjk_chars(str(candidate.get("text") or ""))
            if not chars or chars != candidate_chars:
                continue
            candidate_rect = _normalized_rect(candidate)
            overlap = _intersection_over_smaller(rect, candidate_rect)
            area_similarity = _rect_area_similarity(rect, candidate_rect)
            if (
                overlap < TEMPORAL_CONFIRMATION_MIN_GEOMETRY_OVERLAP
                or area_similarity < TEMPORAL_CONFIRMATION_MIN_AREA_SIMILARITY
            ):
                continue
            provenance_match = {
                "frame_index": candidate_frame,
                "text": candidate.get("text"),
                "confidence": candidate.get("confidence"),
                "geometry": candidate.get("geometry"),
                "geometry_overlap": round(overlap, 6),
                "geometry_area_similarity": round(area_similarity, 6),
                "policy_branch": candidate.get("policy_branch"),
                "source_render_patch": candidate.get("source_render_patch"),
            }
            break

        if provenance_match is None:
            blocking.append(row)
            continue
        excluded.append(
            {
                **row,
                "classification": "SOURCE_INTRINSIC_TEMPORAL_PROPAGATION_FALSE_POSITIVE",
                "matched_source_intrinsic_provenance": provenance_match,
            }
        )
    return blocking, excluded


def classify_temporally_unconfirmed_cjk(
    detections: Sequence[Mapping[str, Any]],
    confirmation_detections: Sequence[Mapping[str, Any]],
    *,
    contract: Mapping[str, Any],
    frame_count: int,
    source_detections: Sequence[Mapping[str, Any]] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Require a spatially stable neighboring-frame OCR confirmation.

    Adjacent evidence increases confidence, but its absence can never clear a
    decoded CJK frame. Source/provenance/Latin false-positive classifiers run
    before this gate; every remaining single-frame CJK result is fail-closed.
    """
    confirmation_by_frame: dict[int, list[dict[str, Any]]] = {}
    for raw in confirmation_detections:
        confirmation_by_frame.setdefault(
            int(raw.get("frame_index") or 0), []
        ).append(dict(raw))
    tracks = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    ]
    source_by_frame: dict[int, list[dict[str, Any]]] = {}
    for raw in source_detections:
        source_by_frame.setdefault(int(raw.get("frame_index") or 0), []).append(
            dict(raw)
        )
    blocking: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for raw in detections:
        row = dict(raw)
        frame_index = int(row.get("frame_index") or 0)
        rect = _normalized_rect(row)
        chars = _cjk_chars(str(row.get("text") or ""))
        match: dict[str, Any] | None = None
        for neighbor in (frame_index - 1, frame_index + 1):
            for candidate in confirmation_by_frame.get(neighbor, []):
                candidate_chars = _cjk_chars(str(candidate.get("text") or ""))
                union = chars | candidate_chars
                similarity = len(chars & candidate_chars) / len(union) if union else 0.0
                candidate_rect = _normalized_rect(candidate)
                overlap = _intersection_over_smaller(rect, candidate_rect)
                area_similarity = _rect_area_similarity(rect, candidate_rect)
                if (
                    similarity >= TEMPORAL_CONFIRMATION_MIN_CJK_SIMILARITY
                    and overlap >= TEMPORAL_CONFIRMATION_MIN_GEOMETRY_OVERLAP
                    and area_similarity >= TEMPORAL_CONFIRMATION_MIN_AREA_SIMILARITY
                ):
                    match = {
                        "frame_index": neighbor,
                        "text": candidate.get("text"),
                        "confidence": candidate.get("confidence"),
                        "geometry": candidate.get("geometry"),
                        "geometry_overlap": round(overlap, 6),
                        "geometry_area_similarity": round(area_similarity, 6),
                        "cjk_similarity": round(similarity, 6),
                    }
                    break
            if match is not None:
                break
        if match is not None:
            blocking.append(
                {
                    **row,
                    "temporal_confirmation": {
                        "status": "CONFIRMED_ON_ADJACENT_FRAME",
                        "match": match,
                    },
                }
            )
            continue

        source_match: dict[str, Any] | None = None
        for candidate in source_by_frame.get(frame_index, []):
            candidate_chars = _cjk_chars(str(candidate.get("text") or ""))
            union = chars | candidate_chars
            similarity = len(chars & candidate_chars) / len(union) if union else 0.0
            candidate_rect = _normalized_rect(candidate)
            overlap = _intersection_over_smaller(rect, candidate_rect)
            area_similarity = _rect_area_similarity(rect, candidate_rect)
            if (
                similarity >= TEMPORAL_CONFIRMATION_MIN_CJK_SIMILARITY
                and overlap >= TEMPORAL_CONFIRMATION_MIN_GEOMETRY_OVERLAP
                and area_similarity >= TEMPORAL_CONFIRMATION_MIN_AREA_SIMILARITY
            ):
                source_match = {
                    "text": candidate.get("text"),
                    "confidence": candidate.get("confidence"),
                    "geometry": candidate.get("geometry"),
                    "geometry_overlap": round(overlap, 6),
                    "geometry_area_similarity": round(area_similarity, 6),
                    "cjk_similarity": round(similarity, 6),
                }
                break

        trailing_authorities: list[str] = []
        if source_match is not None:
            for track in tracks:
                end = int(track.get("end_frame") or 0)
                if frame_index != end + 1:
                    continue
                roi = dict(
                    dict(
                        dict(track.get("render_policy") or {}).get("cover") or {}
                    ).get("roi")
                    or {}
                )
                if not roi:
                    continue
                authority_rect = (
                    float(roi.get("x") or 0.0),
                    float(roi.get("y") or 0.0),
                    float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0),
                    float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0),
                )
                if _intersection_over_smaller(rect, authority_rect) >= 0.10:
                    trailing_authorities.append(str(track.get("text_id") or ""))
        if trailing_authorities:
            blocking.append(
                {
                    **row,
                    "temporal_confirmation": {
                        "status": "SOURCE_CONFIRMED_POST_END_BOUNDARY_RESIDUAL",
                        "source_match": source_match,
                        "trailing_authority_text_ids": sorted(
                            value for value in trailing_authorities if value
                        ),
                    },
                }
            )
            continue

        # Paddle occasionally emits one low-confidence glyph on the feathered
        # edge of a caption plate (the glyph is absent from both neighbours and
        # from the source frame).  Treat only this tightly bounded case as a
        # plate-edge texture false positive; confirmed CJK or anything with a
        # source match remains fail-closed below.
        caption_edge_texture = False
        if (
            len(chars) == 1
            and float(row.get("confidence") or 0.0) <= 0.40
            and max(0.0, rect[2] - rect[0]) * max(0.0, rect[3] - rect[1])
            <= 0.0015
            and source_match is None
        ):
            for track in tracks:
                if not (
                    int(track.get("start_frame") or 0)
                    <= frame_index
                    <= int(track.get("end_frame") or 0)
                ):
                    continue
                # Blur-only output has no Vietnamese typography by design.
                # The plate-edge false-positive gate is visual-cover logic,
                # not text-render logic, so requiring ``text_vi`` incorrectly
                # blocked clean cover-only previews on OCR-like plate texture.
                if not is_editor_caption_track(track) or not bool(
                    track.get("cover_only")
                    or str(track.get("text_vi") or "").strip()
                ):
                    continue
                roi = dict(
                    dict(dict(track.get("render_policy") or {}).get("cover") or {}).get(
                        "roi"
                    )
                    or {}
                )
                if not roi:
                    continue
                rx0 = float(roi.get("x") or 0.0)
                ry0 = float(roi.get("y") or 0.0)
                rx1 = rx0 + float(roi.get("width") or 0.0)
                ry1 = ry0 + float(roi.get("height") or 0.0)
                px0, py0 = max(0.0, rx0 - 0.02), max(0.0, ry0 - 0.02)
                px1, py1 = min(1.0, rx1 + 0.02), min(1.0, ry1 + 0.02)
                padded = {
                    "x": px0,
                    "y": py0,
                    "width": max(0.0, px1 - px0),
                    "height": max(0.0, py1 - py0),
                }
                if _intersection_over_smaller(rect, _normalized_rect({"geometry": padded})) < 0.10:
                    continue
                vertical_gap = max(0.0, ry0 - rect[3], rect[1] - ry1)
                if vertical_gap <= 0.015:
                    caption_edge_texture = True
                    break
        if caption_edge_texture:
            excluded.append(
                {
                    **row,
                    "classification": "EDITOR_CAPTION_EDGE_TEXTURE_FALSE_POSITIVE",
                    "policy_version": "caption_plate_edge_single_frame_v1",
                }
            )
            continue

        overlapping_spans: list[tuple[int, int]] = []
        for track in tracks:
            start = int(track.get("start_frame") or 0)
            end = int(track.get("end_frame") or start)
            if not start <= frame_index <= end:
                continue
            roi = dict(
                dict(dict(track.get("render_policy") or {}).get("cover") or {}).get(
                    "roi"
                )
                or {}
            )
            if not roi:
                continue
            authority_rect = (
                float(roi.get("x") or 0.0),
                float(roi.get("y") or 0.0),
                float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0),
                float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0),
            )
            if _intersection_over_smaller(rect, authority_rect) >= 0.10:
                overlapping_spans.append((start, end))
        has_eligible_neighbor = any(
            start <= neighbor <= end and 0 <= neighbor < frame_count
            for start, end in overlapping_spans
            for neighbor in (frame_index - 1, frame_index + 1)
        )
        if overlapping_spans and not has_eligible_neighbor:
            blocking.append(
                {
                    **row,
                    "temporal_confirmation": {
                        "status": "NOT_APPLICABLE_SINGLE_FRAME_AUTHORITY"
                    },
                }
            )
            continue
        blocking.append(
            {
                **row,
                "temporal_confirmation": {
                    "status": "SINGLE_FRAME_CJK_FAIL_CLOSED",
                    "checked_frames": [
                        neighbor
                        for neighbor in (frame_index - 1, frame_index + 1)
                        if 0 <= neighbor < frame_count
                    ],
                },
            }
        )
    return blocking, excluded


def collect_adaptive_output_qa(
    source_video: str | Path,
    rendered_video: str | Path,
    *,
    contract: Mapping[str, Any],
    artifact_dir: str | Path,
    ocr_provider: Any | None,
    sample_limit: int = 20,
    media_probe: Callable[[str | Path], Mapping[str, Any]] | None = None,
    require_final_audio: bool = False,
    audio_quality_probe: Callable[[str | Path], Mapping[str, Any]] | None = None,
    residual_false_positive_approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate encoded output and write reviewable source/render artifacts.

    ``ocr_provider`` is injected so production can use the fail-closed local
    Paddle provider while unit tests remain independent of model availability.
    """

    import cv2

    source = Path(source_video)
    rendered = Path(rendered_video)
    if not source.is_file() or not rendered.is_file():
        raise AdaptiveOutputQaError("Source or rendered output is missing")
    root = Path(artifact_dir)
    original_dir = root / "original"
    rendered_dir = root / "rendered"
    original_dir.mkdir(parents=True, exist_ok=True)
    rendered_dir.mkdir(parents=True, exist_ok=True)

    timeline_authority = scan_full_timeline_visual_authority(
        source,
        rendered,
        contract=contract,
    )
    motion_scores = _compute_motion_scores(source)
    selected = select_qa_frame_indices(
        contract, motion_scores=motion_scores, limit=sample_limit
    )
    selected = include_phase1_completeness_frames(
        selected,
        artifact_dir=root,
        decoded_frame_count=len(motion_scores),
    )
    selected = include_dense_ui_interval_frames(
        selected,
        contract,
        decoded_frame_count=len(motion_scores),
    )
    selected = include_operator_approved_qa_frame(
        selected,
        decoded_frame_count=len(motion_scores),
        approval=residual_false_positive_approval,
    )
    anomaly_indices = sorted(
        {
            int(value)
            for key in (
                "missing_edit_frames",
                "residual_stroke_frames",
                "protected_source_damage_frames",
            )
            for value in list(timeline_authority.get(key) or [])
            if 0 <= int(value) < len(motion_scores)
        }
    )
    if len(anomaly_indices) > 32:
        anomaly_indices = [
            anomaly_indices[int(round(value))]
            for value in np.linspace(0, len(anomaly_indices) - 1, num=32)
        ]
    selected = sorted(set(selected) | set(anomaly_indices))
    expanded = {
        nearby
        for index in selected
        for nearby in (index - 1, index, index + 1)
        if 0 <= nearby < len(motion_scores)
    }
    source_frames, source_decoded = _read_selected_frames(source, expanded)
    rendered_frames, rendered_decoded = _read_selected_frames(rendered, expanded)

    original_paths: dict[int, Path] = {}
    rendered_paths: dict[int, Path] = {}
    for index in selected:
        original_path = original_dir / f"frame_{index:06d}.jpg"
        rendered_path = rendered_dir / f"frame_{index:06d}.jpg"
        if not cv2.imwrite(str(original_path), source_frames[index]):
            raise AdaptiveOutputQaError("Cannot write original QA frame")
        if not cv2.imwrite(str(rendered_path), rendered_frames[index]):
            raise AdaptiveOutputQaError("Cannot write rendered QA frame")
        original_paths[index] = original_path
        rendered_paths[index] = rendered_path
    contact_sheet = root / "phase4_output_qa_contact_sheet.jpg"
    _write_contact_sheet(contact_sheet, selected, source_frames, rendered_frames)

    damage_rows: list[dict[str, Any]] = []
    flicker_rows: list[dict[str, Any]] = []
    max_extra_flicker = 0.0
    outside_damage_blocked = False
    for index in selected:
        shape = source_frames[index].shape[:2]
        allowed = allowed_edit_mask_for_frame(contract, index, shape)
        damage = evaluate_output_damage(
            source_frames[index], rendered_frames[index], allowed
        )
        damage_rows.append({"frame_index": index, **damage})
        outside_damage_blocked = outside_damage_blocked or damage["status"] == "BLOCKED"

        neighbors = sorted(
            nearby for nearby in (index - 1, index, index + 1) if nearby in expanded
        )
        temporal_masks = [
            allowed_edit_mask_for_frame(contract, nearby, shape) for nearby in neighbors
        ]
        temporal_mask = (
            np.maximum.reduce(temporal_masks)
            if temporal_masks
            else np.zeros(shape, dtype=np.uint8)
        )
        flicker = compute_temporal_flicker(
            [source_frames[nearby] for nearby in neighbors],
            [rendered_frames[nearby] for nearby in neighbors],
            temporal_mask,
        ) if len(neighbors) >= 2 else {
            "status": "NOT_APPLICABLE",
            "pairs": 0,
            "extra_flicker_mean": 0.0,
            "extra_flicker_max": 0.0,
        }
        flicker_rows.append({"frame_index": index, **flicker})
        max_extra_flicker = max(
            max_extra_flicker, float(flicker.get("extra_flicker_max") or 0.0)
        )

    flicker_summary = summarize_temporal_flicker_for_verdict(
        flicker_rows,
        contract=contract,
    )
    flicker_rows = list(flicker_summary["frames"])
    max_extra_flicker = float(flicker_summary["max_extra_flicker"])

    if media_probe is None:
        from src.media_pipeline.video_renderer.render_authority import (
            probe_media_authority,
        )

        media_probe = probe_media_authority
    source_authority = dict(media_probe(source))
    rendered_authority = dict(media_probe(rendered))
    source_duration = _duration_seconds(source_authority)
    rendered_duration = _duration_seconds(rendered_authority)
    video = dict(contract.get("video") or {})
    fps = float(video.get("fps") or 30.0)
    duration_tolerance = max(0.08, 1.5 / max(1.0, fps))
    duration_match = abs(source_duration - rendered_duration) <= duration_tolerance
    expected_frames = int(video.get("frame_count") or source_decoded)
    source_count = _frame_count(source_authority, source_decoded)
    rendered_count = _frame_count(rendered_authority, rendered_decoded)
    frame_count_match = source_count == rendered_count == expected_frames
    color_match, color_comparison = _color_authority_matches(
        source_authority, rendered_authority
    )
    rendered_ocr_complete, raw_residual_cjk, rendered_ocr_error = _detect_residual_cjk(
        provider=ocr_provider,
        rendered_paths=rendered_paths,
        fps=fps,
    )
    source_ocr_complete = True
    source_ocr_error: str | None = None
    source_cjk: list[dict[str, Any]] = []
    temporal_ocr_complete = True
    temporal_ocr_error: str | None = None
    temporal_confirmation_cjk: list[dict[str, Any]] = []
    temporal_confirmation_paths: dict[int, Path] = {}
    if rendered_ocr_complete and raw_residual_cjk:
        residual_frames = {
            int(row.get("frame_index") or 0) for row in raw_residual_cjk
        }
        source_ocr_complete, source_cjk, source_ocr_error = _detect_residual_cjk(
            provider=ocr_provider,
            rendered_paths={
                index: path
                for index, path in original_paths.items()
                if index in residual_frames
            },
            fps=fps,
        )
        confirmation_indices = sorted(
            {
                neighbor
                for frame_index in residual_frames
                for neighbor in (frame_index - 1, frame_index + 1)
                if neighbor in rendered_frames
            }
        )
        confirmation_dir = root / "residual_temporal_confirmation"
        confirmation_dir.mkdir(parents=True, exist_ok=True)
        for index in confirmation_indices:
            path = confirmation_dir / f"frame_{index:06d}.jpg"
            if not cv2.imwrite(str(path), rendered_frames[index]):
                raise AdaptiveOutputQaError(
                    "Cannot write residual temporal confirmation frame"
                )
            temporal_confirmation_paths[index] = path
        (
            temporal_ocr_complete,
            temporal_confirmation_cjk,
            temporal_ocr_error,
        ) = _detect_residual_cjk(
            provider=ocr_provider,
            rendered_paths=temporal_confirmation_paths,
            fps=fps,
        )
    ocr_complete = (
        rendered_ocr_complete and source_ocr_complete and temporal_ocr_complete
    )
    ocr_error = rendered_ocr_error or source_ocr_error or temporal_ocr_error
    source_scene_filtered_cjk, source_scene_protected_cjk = (
        classify_source_scene_protected_cjk(
            raw_residual_cjk,
            contract=contract,
            source_detections=source_cjk,
            source_frames=source_frames,
            rendered_frames=rendered_frames,
        )
    )
    source_filtered_cjk, source_intrinsic_cjk = classify_source_intrinsic_edge_cjk(
        source_scene_filtered_cjk,
        source_cjk,
        contract=contract,
        source_frames=source_frames,
        rendered_frames=rendered_frames,
    )
    source_filtered_cjk, editor_caption_ocr_false_positives = (
        classify_editor_caption_ocr_false_positives(
            source_filtered_cjk,
            contract=contract,
            source_frames=source_frames,
            rendered_frames=rendered_frames,
        )
    )
    source_filtered_cjk, source_intrinsic_temporal_propagations = (
        propagate_source_intrinsic_cjk_exclusions(
            source_filtered_cjk,
            source_intrinsic_cjk,
            contract=contract,
        )
    )
    residual_cjk, temporal_false_positives = classify_temporally_unconfirmed_cjk(
        source_filtered_cjk,
        temporal_confirmation_cjk,
        contract=contract,
        frame_count=expected_frames,
        source_detections=source_cjk,
    )
    try:
        (
            residual_cjk,
            operator_false_positive_exclusions,
        ) = apply_residual_cjk_false_positive_approval(
            residual_cjk,
            residual_false_positive_approval,
            fps=fps,
        )
    except Phase4ApprovalError as exc:
        raise AdaptiveOutputQaError(str(exc)) from exc
    if require_final_audio:
        probe = audio_quality_probe or probe_encoded_audio_quality
        try:
            raw_audio = dict(probe(rendered))
            audio_qa = evaluate_audio_quality(
                present=bool(raw_audio.get("present")),
                audio_duration_seconds=raw_audio.get("audio_duration_seconds"),
                expected_duration_seconds=rendered_duration,
                integrated_lufs=raw_audio.get("integrated_lufs"),
                true_peak_db=raw_audio.get("true_peak_db"),
                measurement_complete=bool(raw_audio.get("measurement_complete")),
                target_lufs=final_audio_target_lufs(contract),
            )
        except Exception as exc:
            audio_qa = {
                "status": "FAIL",
                "failed_checks": ["audio_probe_failed"],
                "error": type(exc).__name__,
                "metrics": {},
            }
    else:
        audio_qa = {
            "status": "NOT_REQUIRED_FOR_VISUAL_PREVIEW",
            "failed_checks": [],
            "metrics": {},
        }
    cover_layout = evaluate_cover_layout_alignment(contract)
    verdict = build_output_qa_verdict(
        duration_match=duration_match,
        frame_count_match=frame_count_match,
        color_authority_match=color_match,
        max_extra_flicker=max_extra_flicker,
        residual_cjk=residual_cjk,
        outside_damage_blocked=outside_damage_blocked,
        residual_ocr_complete=ocr_complete,
        final_audio_passed=(
            not require_final_audio or str(audio_qa.get("status") or "") == "PASS"
        ),
        cover_layout_aligned=(cover_layout.get("status") == "PASS"),
        timeline_edit_coverage=not bool(
            timeline_authority.get("missing_edit_frames")
        ),
        residual_stroke_removal=not bool(
            timeline_authority.get("residual_stroke_frames")
        ),
        protected_source_integrity=not bool(
            timeline_authority.get("protected_source_damage_frames")
        ),
        flicker_limit=float(flicker_summary["limit"]),
    )
    return {
        **verdict,
        "sample": {
            "indices": selected,
            "count": len(selected),
            "strategy": (
                "global_and_track_start_mid_end_motion_peak_plus_bounded_dense_ui"
            ),
        },
        "media": {
            "source_duration_seconds": source_duration,
            "rendered_duration_seconds": rendered_duration,
            "duration_tolerance_seconds": round(duration_tolerance, 6),
            "source_frame_count": source_count,
            "rendered_frame_count": rendered_count,
            "expected_frame_count": expected_frames,
            "color_authority": color_comparison,
        },
        "full_timeline_visual_authority": timeline_authority,
        "damage": {
            "blocked": outside_damage_blocked,
            "frames": damage_rows,
        },
        "temporal_flicker": {
            "max_extra_flicker": round(max_extra_flicker, 4),
            "limit": float(flicker_summary["limit"]),
            "boundary_excluded_count": int(
                flicker_summary["boundary_excluded_count"]
            ),
            "frames": flicker_rows,
        },
        "residual_cjk": {
            "policy_version": RESIDUAL_CJK_POLICY_VERSION,
            "temporal_confirmation_thresholds": {
                "cjk_similarity": TEMPORAL_CONFIRMATION_MIN_CJK_SIMILARITY,
                "geometry_overlap": TEMPORAL_CONFIRMATION_MIN_GEOMETRY_OVERLAP,
                "geometry_area_similarity": TEMPORAL_CONFIRMATION_MIN_AREA_SIMILARITY,
            },
            "provider": getattr(ocr_provider, "provider_name", None),
            "complete": ocr_complete,
            "error": ocr_error,
            "detections": residual_cjk,
            "raw_detections": raw_residual_cjk,
            "source_scene_protected_exclusions": source_scene_protected_cjk,
            "source_intrinsic_exclusions": source_intrinsic_cjk,
            "source_intrinsic_temporal_propagations": source_intrinsic_temporal_propagations,
            "editor_caption_ocr_false_positive_exclusions": editor_caption_ocr_false_positives,
            "temporal_confirmation_detections": temporal_confirmation_cjk,
            "temporal_false_positives": temporal_false_positives,
            "operator_false_positive_exclusions": operator_false_positive_exclusions,
        },
        "audio": audio_qa,
        "cover_layout_alignment": cover_layout,
        "artifacts": {
            "contact_sheet": relative_artifact_path(contact_sheet, root),
            "original_frames": [
                relative_artifact_path(original_paths[index], root) for index in selected
            ],
            "rendered_frames": [
                relative_artifact_path(rendered_paths[index], root) for index in selected
            ],
            "residual_temporal_confirmation_frames": [
                relative_artifact_path(temporal_confirmation_paths[index], root)
                for index in sorted(temporal_confirmation_paths)
            ],
        },
    }


def probe_encoded_video_packet_sha256(
    media_path: str | Path,
    *,
    ffmpeg_binary: str = "ffmpeg",
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    """Hash only encoded video packets, independent of container audio."""

    command = [
        ffmpeg_binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(media_path),
        "-map",
        "0:v:0",
        "-c",
        "copy",
        "-f",
        "hash",
        "-hash",
        "sha256",
        "-",
    ]
    completed = run(command, capture_output=True, text=True, check=False)
    match = re.search(r"SHA256=([0-9a-fA-F]{64})", str(completed.stdout or ""))
    if completed.returncode != 0 or match is None:
        raise AdaptiveOutputQaError("Cannot hash encoded video packet authority")
    return match.group(1).lower()


def collect_reused_visual_output_qa(
    preview_video: str | Path,
    final_video: str | Path,
    *,
    preview_qa: Mapping[str, Any],
    contract: Mapping[str, Any],
    media_probe: Callable[[str | Path], Mapping[str, Any]] | None = None,
    audio_quality_probe: Callable[[str | Path], Mapping[str, Any]] | None = None,
    video_packet_probe: Callable[[str | Path], str] | None = None,
) -> dict[str, Any]:
    """Reuse PASS visual QA only when Final contains the exact preview packets."""

    if str(preview_qa.get("status") or "") != "PASS" or list(
        preview_qa.get("failed_checks") or []
    ):
        raise AdaptiveOutputQaError("Visual preview QA authority is not PASS")
    preview = Path(preview_video)
    final = Path(final_video)
    if not preview.is_file() or not final.is_file():
        raise AdaptiveOutputQaError("Preview or final output is missing")
    packet_probe = video_packet_probe or probe_encoded_video_packet_sha256
    preview_packet_hash = packet_probe(preview)
    final_packet_hash = packet_probe(final)
    packet_match = bool(preview_packet_hash == final_packet_hash)

    if media_probe is None:
        from src.media_pipeline.video_renderer.render_authority import (
            probe_media_authority,
        )

        media_probe = probe_media_authority
    preview_authority = dict(media_probe(preview))
    final_authority = dict(media_probe(final))
    preview_media = dict(preview_qa.get("media") or {})
    expected_duration = float(
        preview_media.get("source_duration_seconds")
        or _duration_seconds(preview_authority)
    )
    final_duration = _duration_seconds(final_authority)
    tolerance = float(
        preview_media.get("duration_tolerance_seconds")
        or max(0.08, expected_duration * 0.01)
    )
    duration_match = abs(final_duration - expected_duration) <= tolerance
    expected_frames = int(
        dict(contract.get("video") or {}).get("frame_count")
        or preview_media.get("expected_frame_count")
        or 0
    )
    final_frames = _frame_count(final_authority, expected_frames)
    frame_count_match = bool(expected_frames > 0 and final_frames == expected_frames)
    color_match, color_comparison = _color_authority_matches(
        preview_authority, final_authority
    )

    probe = audio_quality_probe or probe_encoded_audio_quality
    try:
        raw_audio = dict(probe(final))
        audio_qa = evaluate_audio_quality(
            present=bool(raw_audio.get("present")),
            audio_duration_seconds=raw_audio.get("audio_duration_seconds"),
            expected_duration_seconds=final_duration,
            integrated_lufs=raw_audio.get("integrated_lufs"),
            true_peak_db=raw_audio.get("true_peak_db"),
            measurement_complete=bool(raw_audio.get("measurement_complete")),
            target_lufs=final_audio_target_lufs(contract),
        )
    except Exception as exc:
        audio_qa = {
            "status": "FAIL",
            "failed_checks": ["audio_probe_failed"],
            "error": type(exc).__name__,
            "metrics": {},
        }

    reused = json.loads(json.dumps(dict(preview_qa), ensure_ascii=False, default=str))
    checks = dict(reused.get("checks") or {})
    checks.update(
        {
            "duration": duration_match,
            "frame_count": frame_count_match,
            "color_authority": color_match,
            "final_audio": str(audio_qa.get("status") or "") == "PASS",
            "visual_packet_authority": packet_match,
        }
    )
    failed = [name for name, passed in checks.items() if not bool(passed)]
    reused.update(
        {
            "status": "FAIL" if failed else "PASS",
            "failed_checks": failed,
            "checks": checks,
            "media": {
                **preview_media,
                "rendered_duration_seconds": final_duration,
                "rendered_frame_count": final_frames,
                "color_authority": color_comparison,
            },
            "audio": audio_qa,
            "visual_authority_reuse": {
                "schema_version": "phase4_visual_qa_reuse_v1",
                "status": "PASS" if packet_match else "FAIL",
                "preview_video_packet_sha256": preview_packet_hash,
                "final_video_packet_sha256": final_packet_hash,
                "exact_packet_match": packet_match,
            },
        }
    )
    return reused
