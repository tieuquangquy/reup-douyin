"""Materialize an operator-approved consolidated Phase-4 remediation proposal."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from src.media_pipeline.video_renderer.phase4_input_contract import (
    Phase4InputError,
    _resolve_phase1_source_path,
)
from src.media_pipeline.video_renderer.visual_remediation import (
    VisualRemediationError,
    apply_visual_remediation,
)


DEFAULT_APPROVAL_NAME = "phase4_remediation_approval_v22_4.json"
ACTIVE_POINTER_NAME = "phase4_visual_remediation_active.json"
_COLLISION_TARGET_RE = re.compile(r"geometry:\s*([A-Za-z0-9_.-]+)")


class Phase4RemediationMaterializationError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4RemediationMaterializationError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise Phase4RemediationMaterializationError(
            f"{path.name} must contain an object"
        )
    return payload


def _load_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4RemediationMaterializationError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, list):
        raise Phase4RemediationMaterializationError(
            f"{path.name} must contain a list"
        )
    return [dict(row) for row in payload if isinstance(row, Mapping)]


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _verify_proposal(proposal: Mapping[str, Any]) -> None:
    unsigned = dict(proposal)
    claimed = str(unsigned.pop("proposal_sha256", "") or "")
    if (
        len(claimed) != 64
        or claimed != _sha256_json(unsigned)
        or str(proposal.get("status") or "")
        != "PROPOSAL_READY_FOR_OPERATOR_REVIEW"
        or bool(proposal.get("operator_approval_written"))
    ):
        raise Phase4RemediationMaterializationError(
            "Phase-4 remediation proposal authority is invalid"
        )


def visible_intervals_for_split(
    track: Mapping[str, Any],
    *,
    failure_frame: int,
    minimum_blank_frames: int = 2,
) -> list[list[int]]:
    """Split one stale span at OCR-confirmed internal blank intervals."""

    start = int(track.get("start_frame") or 0)
    end = int(track.get("end_frame") or start)
    hits = sorted(
        {
            int(value)
            for value in list(track.get("hit_frames") or [])
            if start <= int(value) <= end
        }
    )
    if not hits:
        raise Phase4RemediationMaterializationError(
            "Track split lacks Phase-1 hit-frame evidence"
        )
    boundaries = [
        (left, right)
        for left, right in zip(hits, hits[1:])
        if right - left - 1 >= max(1, int(minimum_blank_frames))
    ]
    if len(boundaries) != 1:
        raise Phase4RemediationMaterializationError(
            "Track split requires one unambiguous internal blank interval"
        )
    left, right = boundaries[0]
    if not left < int(failure_frame) < right:
        raise Phase4RemediationMaterializationError(
            "Track split blank interval does not contain the failed frame"
        )
    return [[start, left], [right, end]]


def _source_path(case_root: Path) -> Path:
    meta = _load_object(case_root / "phase1_meta.json")
    try:
        return _resolve_phase1_source_path(case_root, str(meta.get("video") or ""))
    except Phase4InputError as exc:
        raise Phase4RemediationMaterializationError(
            "Phase-1 source video is unavailable"
        ) from exc


def _detect_hard_cut(
    case_root: Path,
    *,
    start_frame: int,
    end_frame: int,
) -> dict[str, Any]:
    import cv2
    import numpy as np

    source = _source_path(case_root)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise Phase4RemediationMaterializationError("Cannot open source for cut scan")
    samples: list[tuple[int, float]] = []
    previous = None
    try:
        for frame_index in range(int(start_frame), int(end_frame) + 1):
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                raise Phase4RemediationMaterializationError(
                    f"Cannot decode cut-scan frame {frame_index}"
                )
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            width = 240
            height = max(1, int(round(gray.shape[0] * width / gray.shape[1])))
            reduced = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
            if previous is not None:
                samples.append(
                    (
                        frame_index,
                        float(
                            np.abs(
                                reduced.astype(np.float32)
                                - previous.astype(np.float32)
                            ).mean()
                        ),
                    )
                )
            previous = reduced
    finally:
        capture.release()
    if not samples:
        raise Phase4RemediationMaterializationError("Cut scan has no comparisons")
    cut_frame, max_mad = max(samples, key=lambda item: item[1])
    baseline = float(median(value for _frame, value in samples))
    ratio = max_mad / max(0.001, baseline)
    if max_mad < 12.0 or ratio < 2.5:
        raise Phase4RemediationMaterializationError(
            "Timing remediation lacks a dominant source scene cut"
        )
    return {
        "method": "full_frame_gray_mad_v1",
        "cut_frame": cut_frame,
        "max_mad": round(max_mad, 6),
        "median_mad": round(baseline, 6),
        "peak_to_median_ratio": round(ratio, 6),
        "source_video_sha256": _sha256_file(source),
    }


def _track_hash(track: Mapping[str, Any]) -> str:
    return _sha256_json(dict(track))


def _geometry_overlap_over_smaller(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> float:
    def rect(value: Mapping[str, Any]) -> tuple[float, float, float, float]:
        x = float(value.get("x") or 0.0)
        y = float(value.get("y") or 0.0)
        width = float(value.get("width") or 0.0)
        height = float(value.get("height") or 0.0)
        return x, y, x + width, y + height

    a = rect(left)
    b = rect(right)
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1])
    )
    smaller = min(
        max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1]),
        max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]),
    )
    return intersection / smaller if smaller > 0 else 0.0


def _target_track(contract: Mapping[str, Any], text_id: str) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping) and str(row.get("text_id") or "") == text_id
    ]
    if len(rows) != 1:
        raise Phase4RemediationMaterializationError(
            f"Expected one Phase-4 track for {text_id}"
        )
    return rows[0]


def _build_operation(
    *,
    case_root: Path,
    contract: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    details = dict(decision.get("decision") or {})
    action = str(details.get("action") or "")
    text_id = str(decision.get("text_id") or "")
    if action == "DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK_GROUP":
        canonical_id = str(details.get("canonical_track_id") or "")
        drop_ids = sorted(
            {
                str(value)
                for value in list(details.get("drop_track_ids") or [])
                if str(value)
            }
        )
        canonical = _target_track(contract, canonical_id)
        canonical_coverage = dict(
            canonical.get("output_residual_coverage") or {}
        )
        canonical_source = str(
            canonical_coverage.get("source_text") or ""
        ).strip()
        canonical_vi = str(canonical.get("text_vi") or "").strip()
        if (
            not canonical_id.startswith("p4out_")
            or not drop_ids
            or canonical_id in drop_ids
            or not canonical_source
            or not canonical_vi
            or not str(canonical_coverage.get("status") or "").startswith(
                "OPERATOR_APPROVED_SOURCE_"
            )
        ):
            raise Phase4RemediationMaterializationError(
                "Duplicate output-residual group authority is incomplete"
            )
        targets: list[dict[str, Any]] = []
        for drop_id in drop_ids:
            target = _target_track(contract, drop_id)
            coverage = dict(target.get("output_residual_coverage") or {})
            overlap = _geometry_overlap_over_smaller(
                dict(canonical.get("geometry") or {}),
                dict(target.get("geometry") or {}),
            )
            if (
                not drop_id.startswith("p4out_")
                or str(coverage.get("source_text") or "").strip()
                != canonical_source
                or str(target.get("text_vi") or "").strip() != canonical_vi
                or not str(coverage.get("status") or "").startswith(
                    "OPERATOR_APPROVED_SOURCE_"
                )
                or overlap < 0.70
                or min(
                    int(canonical.get("end_frame") or -1),
                    int(target.get("end_frame") or -1),
                )
                < max(
                    int(canonical.get("start_frame") or 0),
                    int(target.get("start_frame") or 0),
                )
            ):
                raise Phase4RemediationMaterializationError(
                    f"Duplicate output-residual group guard failed: {drop_id}"
                )
            targets.append(
                {
                    "target_text_id": drop_id,
                    "expected_track_sha256": _track_hash(target),
                    "geometry_overlap_over_smaller": round(overlap, 6),
                }
            )
        return {
            "operation": "DROP_TRACK_GROUP",
            "target_text_id": canonical_id,
            "canonical_track_id": canonical_id,
            "expected_canonical_track_sha256": _track_hash(canonical),
            "targets": targets,
            "reason": "operator_approved_duplicate_output_residual_track_group",
        }
    if action == "DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK":
        target = _target_track(contract, text_id)
        duplicate_id = str(details.get("duplicate_track_id") or "")
        if not text_id.startswith("p4out_") or not duplicate_id:
            raise Phase4RemediationMaterializationError(
                "Duplicate output-residual target is incomplete"
            )
        duplicate = _target_track(contract, duplicate_id)
        target_coverage = dict(target.get("output_residual_coverage") or {})
        duplicate_coverage = dict(
            duplicate.get("output_residual_coverage") or {}
        )
        target_source = str(target_coverage.get("source_text") or "").strip()
        duplicate_source = str(
            duplicate_coverage.get("source_text") or ""
        ).strip()
        target_vi = str(target.get("text_vi") or "").strip()
        duplicate_vi = str(duplicate.get("text_vi") or "").strip()
        if (
            not target_source
            or target_source != duplicate_source
            or not target_vi
            or target_vi != duplicate_vi
            or not str(target_coverage.get("status") or "").startswith(
                "OPERATOR_APPROVED_SOURCE_"
            )
            or not str(duplicate_coverage.get("status") or "").startswith(
                "OPERATOR_APPROVED_SOURCE_"
            )
        ):
            raise Phase4RemediationMaterializationError(
                "Duplicate output-residual source authority does not match"
            )
        overlap = _geometry_overlap_over_smaller(
            dict(target.get("geometry") or {}),
            dict(duplicate.get("geometry") or {}),
        )
        target_start = int(target.get("start_frame") or 0)
        target_end = int(target.get("end_frame") or -1)
        duplicate_start = int(duplicate.get("start_frame") or 0)
        duplicate_end = int(duplicate.get("end_frame") or -1)
        if overlap < 0.70 or min(target_end, duplicate_end) < max(
            target_start, duplicate_start
        ):
            raise Phase4RemediationMaterializationError(
                "Duplicate output-residual geometry/span guard failed"
            )
        return {
            "operation": "DROP_TRACK",
            "target_text_id": text_id,
            "expected_track_sha256": _track_hash(target),
            "duplicate_track_id": duplicate_id,
            "expected_duplicate_track_sha256": _track_hash(duplicate),
            "geometry_overlap_over_smaller": round(overlap, 6),
            "reason": "operator_approved_duplicate_output_residual_track",
        }
    if action == "CAPTION_PANEL_FALLBACK_WITH_EXISTING_DAMAGE_BUDGET":
        track = _target_track(contract, text_id)
        return {
            "operation": "POLICY_OVERRIDE",
            "target_text_id": text_id,
            "expected_track_sha256": _track_hash(track),
            "context_updates": {
                "caption_row": True,
                "caption_panel_operator_approved": True,
            },
            "cover_updates": {
                "mask_mode": "ink_components",
                "fallback": "caption_panel_operator_approved",
            },
            "damage_budget_changed": False,
        }
    if action == "CONFIRM_TIMING_THEN_TIGHT_ROI_REFERENCE_PLATE_FALLBACK":
        track = _target_track(contract, text_id)
        return {
            "operation": "POLICY_OVERRIDE",
            "target_text_id": text_id,
            "expected_track_sha256": _track_hash(track),
            "context_updates": {"reference_plate_operator_approved": True},
            "cover_updates": {
                "mask_mode": "stylized_components",
                "fallback": "reference_plate_operator_approved",
            },
            "damage_budget_changed": False,
        }
    if action == "BOUNDED_MICRO_UI_SPATIAL_FALLBACK_WITH_EXISTING_DAMAGE_BUDGET":
        track = _target_track(contract, text_id)
        policy = dict(track.get("render_policy") or {})
        context = dict(policy.get("context") or {})
        if (
            not bool(context.get("micro_ui"))
            or not bool(context.get("output_residual_bounded_dense_mask"))
        ):
            raise Phase4RemediationMaterializationError(
                "Bounded spatial fallback requires source-verified micro-UI authority"
            )
        return {
            "operation": "POLICY_OVERRIDE",
            "target_text_id": text_id,
            "expected_track_sha256": _track_hash(track),
            "context_updates": {
                "reference_plate_operator_approved": False,
                "output_residual_micro_ui_reference": False,
                "bounded_spatial_fallback_operator_approved": True,
            },
            "cover_updates": {
                "mask_mode": "ink_components",
                "fallback": "bounded_output_residual_dense_roi_operator_approved",
            },
            "damage_budget_changed": False,
        }
    if action == "SPLIT_TRACK_TO_SOURCE_VISIBLE_INTERVALS_AND_SCOPE_MASK_CACHE":
        track = _target_track(contract, text_id)
        master = _load_list(case_root / "master_timeline.json")
        master_rows = [row for row in master if str(row.get("text_id") or "") == text_id]
        if len(master_rows) != 1:
            raise Phase4RemediationMaterializationError(
                f"Expected one Phase-1 track for split target {text_id}"
            )
        intervals = visible_intervals_for_split(
            master_rows[0],
            failure_frame=int(decision.get("frame_index") or -1),
        )
        return {
            "operation": "SPLIT_TRACK",
            "target_text_id": text_id,
            "expected_track_sha256": _track_hash(track),
            "intervals": intervals,
            "blank_interval": [intervals[0][1] + 1, intervals[1][0] - 1],
            "source": "phase1_hit_frames_plus_phase4_failed_frame",
        }
    if action == "TRIM_OUTPUT_RESIDUAL_TRACK_BEFORE_CONFIRMED_SOURCE_CHANGE":
        track = _target_track(contract, text_id)
        original = [
            int(track.get("start_frame") or 0),
            int(track.get("end_frame") or -1),
        ]
        failure_frame = int(decision.get("frame_index") or -1)
        if (
            not text_id.startswith("p4out_")
            or failure_frame <= original[0]
            or failure_frame > original[1]
        ):
            raise Phase4RemediationMaterializationError(
                "Output-residual trim boundary is invalid"
            )
        return {
            "operation": "TIMING_OVERRIDE",
            "target_text_id": text_id,
            "expected_track_sha256": _track_hash(track),
            "original_window": original,
            "replacement_window": [original[0], failure_frame - 1],
            "confirmed_source_change_frame": failure_frame,
            "source": "operator_confirmed_phase4_output_residual_source_change",
        }
    if action == "BOUNDED_EXACT_RESIDUAL_STYLIZED_COMPONENT_MASK":
        track = _target_track(contract, text_id)
        context = dict(
            dict(track.get("render_policy") or {}).get("context") or {}
        )
        if (
            not text_id.startswith("p4out_")
            or not bool(context.get("output_residual_geometry_aligned"))
            or not bool(context.get("output_residual_width_expanded"))
        ):
            raise Phase4RemediationMaterializationError(
                "Stylized exact-residual fallback lacks aligned coverage authority"
            )
        return {
            "operation": "POLICY_OVERRIDE",
            "target_text_id": text_id,
            "expected_track_sha256": _track_hash(track),
            "context_updates": {
                "output_residual_stylized_components_operator_approved": True,
            },
            "cover_updates": {
                "mask_mode": "stylized_components",
                "fallback": "operator_review",
            },
            "damage_budget_changed": False,
        }
    if action == "DROP_EMPTY_CONTENT_TRACK":
        track = _target_track(contract, text_id)
        if (
            str(track.get("text_vi") or "").strip()
            or track.get("content_id") is not None
            or not bool(track.get("cover_only"))
        ):
            raise Phase4RemediationMaterializationError(
                "Drop-track guard no longer matches the approved empty track"
            )
        return {
            "operation": "DROP_TRACK",
            "target_text_id": text_id,
            "expected_track_sha256": _track_hash(track),
            "reason": "operator_approved_empty_content_without_explicit_cover_authority",
        }
    if action == "UPSTREAM_PHASE1_TIMING_SPLIT_THEN_ADD_RESIDUAL_OCCURRENCE":
        attempt_ref = dict(details.get("residual_proposal_attempt") or {})
        attempt = _load_object(case_root / str(attempt_ref.get("path") or ""))
        reason = str(attempt.get("reason") or "")
        match = _COLLISION_TARGET_RE.search(reason)
        if match is None:
            raise Phase4RemediationMaterializationError(
                "Residual collision target is not explicit"
            )
        target_id = match.group(1)
        track = _target_track(contract, target_id)
        original = [int(track.get("start_frame") or 0), int(track.get("end_frame") or 0)]
        cut = _detect_hard_cut(
            case_root,
            start_frame=original[0],
            end_frame=original[1],
        )
        replacement = [original[0], int(cut["cut_frame"]) - 1]
        if replacement[1] < replacement[0]:
            raise Phase4RemediationMaterializationError(
                "Detected cut cannot produce a valid timing override"
            )
        return {
            "operation": "TIMING_OVERRIDE",
            "target_text_id": target_id,
            "expected_track_sha256": _track_hash(track),
            "original_window": original,
            "replacement_window": replacement,
            "scene_cut_evidence": cut,
            "residual_occurrence_status": "TRANSLATION_AUTHORITY_STILL_REQUIRED",
        }
    if action == "UPSTREAM_RESIDUAL_GEOMETRY_REMEDIATION_THEN_RERENDER":
        return {}
    raise Phase4RemediationMaterializationError(
        f"Unsupported approved Phase-4 remediation action: {action}"
    )


def materialize(
    *,
    run_root: str | Path,
    proposal_path: str | Path,
    approved_proposal_sha256: str,
    operator_id: str,
    approved_at: str,
    approval_name: str = DEFAULT_APPROVAL_NAME,
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    proposal_file = Path(proposal_path).resolve()
    proposal = _load_object(proposal_file)
    _verify_proposal(proposal)
    claimed = str(proposal.get("proposal_sha256") or "")
    if claimed != str(approved_proposal_sha256 or ""):
        raise Phase4RemediationMaterializationError(
            "Approved proposal SHA-256 does not match"
        )
    operator = str(operator_id or "").strip()
    timestamp = str(approved_at or "").strip()
    if not operator or not timestamp:
        raise Phase4RemediationMaterializationError(
            "operator_id and approved_at are required"
        )
    approval_filename = str(approval_name or "").strip()
    if (
        not approval_filename
        or Path(approval_filename).name != approval_filename
        or not approval_filename.endswith(".json")
    ):
        raise Phase4RemediationMaterializationError("Invalid approval artifact name")
    decisions = [
        dict(row)
        for row in list(proposal.get("decisions") or [])
        if isinstance(row, Mapping)
    ]
    if not decisions:
        raise Phase4RemediationMaterializationError("Proposal has no decisions")
    pending_cases = [
        {
            "case_id": str(row.get("case_id") or ""),
            "action": str(dict(row.get("decision") or {}).get("action") or ""),
            "status": "RESIDUAL_GEOMETRY_AND_TRANSLATION_AUTHORITY_REQUIRED",
            "residual_texts": list(
                dict(row.get("decision") or {}).get("residual_texts") or []
            ),
        }
        for row in decisions
        if str(dict(row.get("decision") or {}).get("action") or "").startswith(
            "UPSTREAM_"
        )
    ]
    approval: dict[str, Any] = {
        "schema_version": "phase4_remediation_approval_v1",
        "status": (
            "PHASE4_REMEDIATION_OPERATOR_APPROVED_PENDING_RESIDUAL_AUTHORITY"
            if pending_cases
            else "PHASE4_REMEDIATION_OPERATOR_APPROVED"
        ),
        "operator_id": operator,
        "approved_at": timestamp,
        "proposal_ref": {
            "path": proposal_file.name,
            "sha256": _sha256_file(proposal_file),
            "proposal_sha256": claimed,
        },
        "approved_case_ids": sorted(str(row.get("case_id") or "") for row in decisions),
        "pending_residual_cases": pending_cases,
    }
    approval["approval_sha256"] = _sha256_json(approval)
    materializations: list[tuple[Path, dict[str, Any], Path, dict[str, Any]]] = []
    version = claimed[:12]
    for decision in decisions:
        case_id = str(decision.get("case_id") or "")
        case_root = root / case_id
        input_path = case_root / "phase4_render_input.json"
        if not case_root.is_dir() or not input_path.is_file():
            raise Phase4RemediationMaterializationError(
                f"Case Phase-4 input is missing: {case_id}"
            )
        contract = _load_object(input_path)
        parent_payload: dict[str, Any] | None = None
        parent_path: Path | None = None
        active_path = case_root / ACTIVE_POINTER_NAME
        if active_path.is_file():
            active_pointer = _load_object(active_path)
            active_ref = dict(active_pointer.get("active_ref") or {})
            candidate = (case_root / str(active_ref.get("path") or "")).resolve()
            if (
                not candidate.is_relative_to(case_root)
                or not candidate.is_file()
                or _sha256_file(candidate) != str(active_ref.get("sha256") or "")
            ):
                raise Phase4RemediationMaterializationError(
                    f"Existing active remediation is invalid: {case_id}"
                )
            parent_path = candidate
            parent_payload = _load_object(candidate)
        effective_contract, _active_ref = apply_visual_remediation(
            case_root,
            contract,
            contract_path=input_path,
        )
        operation = _build_operation(
            case_root=case_root,
            contract=effective_contract,
            decision=decision,
        )
        if not operation:
            continue
        parent_operations = [
            dict(row)
            for row in list(dict(parent_payload or {}).get("operations") or [])
            if isinstance(row, Mapping)
        ]
        operation_identity = (
            str(operation.get("operation") or ""),
            str(operation.get("target_text_id") or ""),
        )
        combined_operations = (
            parent_operations + [operation]
            if str(operation.get("operation") or "") == "POLICY_OVERRIDE"
            else [
                row
                for row in parent_operations
                if (
                    str(row.get("operation") or ""),
                    str(row.get("target_text_id") or ""),
                )
                != operation_identity
            ]
            + [operation]
        )
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
                "batch_approval": {
                    "path": f"../../{approval_filename}",
                    "approval_sha256": approval["approval_sha256"],
                },
                "proposal": {
                    "path": f"../../{proposal_file.name}",
                    "proposal_sha256": claimed,
                },
                **(
                    {
                        "parent_visual_remediation": {
                            "path": parent_path.name,
                            "sha256": _sha256_file(parent_path),
                            "materialization_sha256": parent_payload.get(
                                "materialization_sha256"
                            ),
                        }
                    }
                    if parent_payload is not None and parent_path is not None
                    else {}
                ),
            },
            "operations": combined_operations,
            "non_goals": [
                "do_not_overwrite_master_timeline",
                "do_not_relax_qa_thresholds",
                "do_not_approve_residual_translation_suggestions",
            ],
        }
        material["materialization_sha256"] = _sha256_json(material)
        material_path = case_root / f"phase4_visual_remediation_{version}.json"
        pointer: dict[str, Any] = {
            "schema_version": "phase4_visual_remediation_pointer_v1",
            "status": "ACTIVE",
            "active_ref": {
                "path": material_path.name,
                "sha256": "",
                "materialization_sha256": material["materialization_sha256"],
            },
        }
        pointer_path = case_root / ACTIVE_POINTER_NAME
        materializations.append((material_path, material, pointer_path, pointer))
    for material_path, material, pointer_path, pointer in materializations:
        _write_json_atomic(material_path, material)
        pointer["active_ref"]["sha256"] = _sha256_file(material_path)
        pointer["pointer_sha256"] = _sha256_json(pointer)
        _write_json_atomic(pointer_path, pointer)
    pending_artifact: dict[str, Any] | None = None
    if pending_cases:
        pending_artifact = {
            "schema_version": "phase4_residual_authority_pending_v1",
            "status": "RESIDUAL_AUTHORITY_REQUIRED",
            "created_at": timestamp,
            "approval_ref": {
                "path": approval_filename,
                "approval_sha256": approval["approval_sha256"],
            },
            "proposal_ref": approval["proposal_ref"],
            "cases": pending_cases,
            "operator_approval_written_for_translation": False,
        }
        pending_artifact["pending_sha256"] = _sha256_json(pending_artifact)
        _write_json_atomic(
            root / f"phase4_residual_authority_pending_{version}.json",
            pending_artifact,
        )
    _write_json_atomic(root / approval_filename, approval)
    return {
        **approval,
        "materializations": [
            {
                "case_id": material["case_id"],
                "path": material_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(material_path),
                "materialization_sha256": material["materialization_sha256"],
            }
            for material_path, material, _pointer_path, _pointer in materializations
        ],
        "pending_residual_cases": pending_cases,
        "pending_residual_authority_sha256": (
            pending_artifact.get("pending_sha256")
            if pending_artifact is not None
            else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.materialize_phase4_remediation_proposal"
    )
    parser.add_argument("run_root")
    parser.add_argument("proposal_path")
    parser.add_argument("--approved-proposal-sha256", required=True)
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--approved-at")
    parser.add_argument("--approval-name", default=DEFAULT_APPROVAL_NAME)
    args = parser.parse_args()
    try:
        result = materialize(
            run_root=args.run_root,
            proposal_path=args.proposal_path,
            approved_proposal_sha256=args.approved_proposal_sha256,
            operator_id=args.operator_id,
            approved_at=args.approved_at or datetime.now(timezone.utc).isoformat(),
            approval_name=args.approval_name,
        )
    except (
        OSError,
        ValueError,
        VisualRemediationError,
        Phase4RemediationMaterializationError,
    ) as exc:
        print(f"[PHASE4-REMEDIATION-MATERIALIZE][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "approval_sha256": result["approval_sha256"],
                "materializations": len(result["materializations"]),
                "pending_residual_cases": len(result["pending_residual_cases"]),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
