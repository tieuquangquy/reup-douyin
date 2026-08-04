"""Build a hash-bound operator decision proposal from Phase-4 visual triage.

The builder validates curated, run-specific suggestions against the immutable
Phase 1-4 chain.  It never writes OCR/remediation/approval/render authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "phase4_residual_triage_decision_proposal_v1"
ALLOWED_ACTIONS = {
    "ADD_PHASE2_OCCURRENCE",
    "EXPAND_EXISTING_PHASE2_GEOMETRY",
    "APPROVE_SOURCE_INTRINSIC_FALSE_POSITIVE",
    "COVERED_BY_PROPOSED_OCCURRENCE",
}


class ResidualTriageDecisionProposalError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResidualTriageDecisionProposalError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise ResidualTriageDecisionProposalError(
            f"{path.name} must contain an object"
        )
    return payload


def _load_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResidualTriageDecisionProposalError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, list):
        raise ResidualTriageDecisionProposalError(
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
        raise ResidualTriageDecisionProposalError(f"{label} self-hash is invalid")


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


def _safe_ref(root: Path, raw_path: str, *, label: str) -> Path:
    path = (root / raw_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ResidualTriageDecisionProposalError(f"Invalid {label} path")
    return path


def _verify_ref(
    root: Path, ref: Mapping[str, Any], *, label: str
) -> Path:
    path = _safe_ref(root, str(ref.get("path") or ""), label=label)
    expected = str(ref.get("sha256") or "")
    if len(expected) != 64 or expected != _sha256_file(path):
        raise ResidualTriageDecisionProposalError(f"Stale {label} artifact")
    return path


def _rect(raw: Mapping[str, Any]) -> tuple[float, float, float, float]:
    try:
        x = float(raw.get("x") or 0.0)
        y = float(raw.get("y") or 0.0)
        width = float(raw.get("width") or 0.0)
        height = float(raw.get("height") or 0.0)
    except (TypeError, ValueError) as exc:
        raise ResidualTriageDecisionProposalError(
            "Proposed geometry is invalid"
        ) from exc
    if (
        width <= 0
        or height <= 0
        or min(x, y) < 0
        or x + width > 1.001
        or y + height > 1.001
    ):
        raise ResidualTriageDecisionProposalError(
            "Proposed geometry is out of bounds"
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


def _verify_cluster_evidence(root: Path, cluster: Mapping[str, Any]) -> None:
    _verify_ref(
        root,
        dict(cluster.get("contact_sheet_ref") or {}),
        label="cluster contact sheet",
    )
    evidence = list(cluster.get("evidence_frames") or [])
    if not evidence or not bool(cluster.get("source_render_adjacent_complete")):
        raise ResidualTriageDecisionProposalError(
            "Cluster source/render adjacent evidence is incomplete"
        )
    for raw in evidence:
        row = dict(raw)
        for key in (
            "source_frame_ref",
            "rendered_frame_ref",
            "source_crop_ref",
            "rendered_crop_ref",
        ):
            _verify_ref(root, dict(row.get(key) or {}), label=f"cluster {key}")


def _crop_mean_abs_delta(root: Path, cluster: Mapping[str, Any]) -> float:
    import cv2
    import numpy as np

    values: list[float] = []
    for raw in list(cluster.get("evidence_frames") or []):
        row = dict(raw)
        source_path = _verify_ref(
            root, dict(row.get("source_crop_ref") or {}), label="source crop"
        )
        rendered_path = _verify_ref(
            root, dict(row.get("rendered_crop_ref") or {}), label="rendered crop"
        )
        source = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
        rendered = cv2.imread(str(rendered_path), cv2.IMREAD_COLOR)
        if source is None or rendered is None or source.shape != rendered.shape:
            raise ResidualTriageDecisionProposalError(
                "False-positive crop evidence is unreadable"
            )
        values.append(
            float(
                np.abs(source.astype(np.float32) - rendered.astype(np.float32)).mean()
            )
        )
    return max(values) if values else 255.0


def _geometry_for_decision(
    decision: Mapping[str, Any], cluster: Mapping[str, Any]
) -> dict[str, Any]:
    strategy = str(decision.get("geometry_strategy") or "")
    detections = [dict(row) for row in list(cluster.get("detections") or [])]
    if not detections:
        raise ResidualTriageDecisionProposalError("Residual cluster is empty")
    representative = max(
        detections, key=lambda row: float(row.get("confidence") or 0.0)
    )
    cluster_geometry = dict(representative.get("geometry") or {})
    cluster_rect = _rect(cluster_geometry)
    if strategy == "CLUSTER_GEOMETRY":
        geometry = cluster_geometry
    elif strategy == "MANUAL_TIGHT_GEOMETRY":
        geometry = dict(decision.get("geometry") or {})
        geometry_rect = _rect(geometry)
        if _intersection_over_smaller(cluster_rect, geometry_rect) < 0.50:
            raise ResidualTriageDecisionProposalError(
                "Manual geometry is not supported by the residual cluster"
            )
        cluster_area = (cluster_rect[2] - cluster_rect[0]) * (
            cluster_rect[3] - cluster_rect[1]
        )
        geometry_area = (geometry_rect[2] - geometry_rect[0]) * (
            geometry_rect[3] - geometry_rect[1]
        )
        if geometry_area >= cluster_area:
            raise ResidualTriageDecisionProposalError(
                "Manual tight geometry must be smaller than the detector cluster"
            )
    elif strategy == "MANUAL_EVIDENCE_GEOMETRY":
        geometry = dict(decision.get("geometry") or {})
        geometry_rect = _rect(geometry)
        if _intersection_over_smaller(cluster_rect, geometry_rect) < 0.80:
            raise ResidualTriageDecisionProposalError(
                "Manual evidence geometry must contain the residual cluster"
            )
        cluster_width = cluster_rect[2] - cluster_rect[0]
        cluster_height = cluster_rect[3] - cluster_rect[1]
        cluster_area = cluster_width * cluster_height
        geometry_width = geometry_rect[2] - geometry_rect[0]
        geometry_height = geometry_rect[3] - geometry_rect[1]
        geometry_area = geometry_width * geometry_height
        if (
            geometry_area <= cluster_area
            or geometry_area > cluster_area * 12.0
            or geometry_area > 0.02
            or geometry_width > cluster_width * 6.0
            or geometry_height > cluster_height * 6.0
        ):
            raise ResidualTriageDecisionProposalError(
                "Manual evidence geometry expansion exceeds safety limits"
            )
    else:
        raise ResidualTriageDecisionProposalError(
            f"Unsupported geometry strategy: {strategy or 'missing'}"
        )
    return {
        "strategy": strategy,
        "geometry": geometry,
        "representative_frame_index": int(
            representative.get("frame_index") or 0
        ),
        "detector_geometry": cluster_geometry,
    }


def _content_by_geometry(
    phase2_timeline: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for raw in list(phase2_timeline.get("content_objects") or []):
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        for text_id in list(row.get("geometry_refs") or []):
            output[str(text_id)] = row
    return output


def _validate_temporal_reference(
    decision: Mapping[str, Any],
    master_by_id: Mapping[str, Mapping[str, Any]],
    *,
    frame_index: int,
) -> dict[str, Any]:
    strategy = str(decision.get("temporal_strategy") or "")
    if strategy == "SOURCE_BOUNDARY_RESCAN_REQUIRED":
        return {"strategy": strategy, "materialization_rescan_required": True}
    if strategy != "ALIGN_AND_RESCAN_FROM_PHASE1_WINDOW":
        raise ResidualTriageDecisionProposalError(
            f"Unsupported temporal strategy: {strategy or 'missing'}"
        )
    text_id = str(decision.get("temporal_reference_text_id") or "")
    row = dict(master_by_id.get(text_id) or {})
    if not row:
        raise ResidualTriageDecisionProposalError(
            f"Temporal reference is missing: {text_id or 'unknown'}"
        )
    start = int(row.get("start_frame") or 0)
    end = int(row.get("end_frame") or start)
    if not start <= frame_index <= end:
        raise ResidualTriageDecisionProposalError(
            f"Temporal reference does not cover frame {frame_index}: {text_id}"
        )
    return {
        "strategy": strategy,
        "reference_text_id": text_id,
        "reference_window": [start, end],
        "materialization_rescan_required": True,
    }


def _build_decision(
    *,
    root: Path,
    raw_decision: Mapping[str, Any],
    cluster: Mapping[str, Any],
    master_by_id: Mapping[str, Mapping[str, Any]],
    content_by_geometry: Mapping[str, Mapping[str, Any]],
    phase3_geometry_map: Mapping[str, Any],
    translation_suggestions: Mapping[str, str],
) -> dict[str, Any]:
    action = str(raw_decision.get("proposed_action") or "")
    if action not in ALLOWED_ACTIONS:
        raise ResidualTriageDecisionProposalError(
            f"Unsupported proposed action: {action or 'missing'}"
        )
    cluster_id = str(cluster.get("cluster_id") or "")
    source_text = str(raw_decision.get("source_text_suggested") or "").strip()
    vi_text = str(raw_decision.get("vi_text_suggested") or "").strip()
    rationale = str(raw_decision.get("rationale") or "").strip()
    if not rationale:
        raise ResidualTriageDecisionProposalError(
            f"Decision rationale is missing for {cluster_id}"
        )
    base: dict[str, Any] = {
        "cluster_id": cluster_id,
        "signature": cluster.get("signature"),
        "proposal_status": "OPERATOR_REVIEW_REQUIRED",
        "proposed_action": action,
        "source_text_suggested": source_text or None,
        "vi_text_suggested": vi_text or None,
        "source_text_basis": raw_decision.get("source_text_basis"),
        "rationale": rationale,
        "proposal_only": True,
        "operator_approval_written": False,
        "visual_evidence_ref": cluster.get("contact_sheet_ref"),
        "cluster_evidence_sha256": _sha256_json(cluster),
    }
    if action == "COVERED_BY_PROPOSED_OCCURRENCE":
        linked_cluster_id = str(raw_decision.get("linked_cluster_id") or "")
        if not source_text or not vi_text or not linked_cluster_id:
            raise ResidualTriageDecisionProposalError(
                f"Linked remediation proposal is incomplete: {cluster_id}"
            )
        base.update(
            {
                "linked_cluster_id": linked_cluster_id,
                "materialization_gate": (
                    "LINKED_PHASE2_REMEDIATION_MATERIALIZATION_REQUIRED"
                ),
            }
        )
        return base
    if action == "APPROVE_SOURCE_INTRINSIC_FALSE_POSITIVE":
        if (
            str(raw_decision.get("false_positive_scope") or "")
            != "SOURCE_INTRINSIC_PHYSICAL_TEXT"
            or not source_text
            or vi_text
        ):
            raise ResidualTriageDecisionProposalError(
                f"Invalid source-intrinsic false-positive proposal: {cluster_id}"
            )
        max_delta = _crop_mean_abs_delta(root, cluster)
        if max_delta > 2.5:
            raise ResidualTriageDecisionProposalError(
                f"Source/render delta is too high for false positive: {cluster_id}"
            )
        base.update(
            {
                "false_positive_scope": "SOURCE_INTRINSIC_PHYSICAL_TEXT",
                "source_render_crop_max_mean_abs_delta": round(max_delta, 6),
                "materialization_gate": "PHASE4_FALSE_POSITIVE_APPROVAL_REQUIRED",
            }
        )
        return base

    if not source_text or not vi_text:
        raise ResidualTriageDecisionProposalError(
            f"Remediation text is incomplete for {cluster_id}"
        )
    if action == "ADD_PHASE2_OCCURRENCE":
        geometry = _geometry_for_decision(raw_decision, cluster)
        temporal = _validate_temporal_reference(
            raw_decision,
            master_by_id,
            frame_index=int(geometry["representative_frame_index"]),
        )
        base.update(
            {
                "proposed_occurrence": {
                    **geometry,
                    "temporal": temporal,
                },
                "translation_suggestion_match": (
                    translation_suggestions.get(source_text) == vi_text
                ),
                "materialization_gate": "PHASE2_REMEDIATION_MATERIALIZATION_REQUIRED",
            }
        )
        return base

    target_text_id = str(raw_decision.get("target_text_id") or "")
    intersection_ids = {
        str(row.get("text_id") or "")
        for row in list(cluster.get("phase1_geometry_intersections") or [])
        if isinstance(row, Mapping)
    }
    target = dict(master_by_id.get(target_text_id) or {})
    content = dict(content_by_geometry.get(target_text_id) or {})
    phase3 = dict(phase3_geometry_map.get(target_text_id) or {})
    if (
        not target
        or target_text_id not in intersection_ids
        or str(content.get("ocr_text_approved") or "") != source_text
        or str(phase3.get("text_vi") or "") != vi_text
        or str(phase3.get("translation_status") or "")
        not in {"TRANSLATION_APPROVED", "TRANSLATION_DETERMINISTIC"}
    ):
        raise ResidualTriageDecisionProposalError(
            f"Geometry expansion authority is invalid for {cluster_id}"
        )
    base.update(
        {
            "target_text_id": target_text_id,
            "target_content_id": content.get("content_id"),
            "target_window": [
                int(target.get("start_frame") or 0),
                int(target.get("end_frame") or 0),
            ],
            "approved_translation_carry_forward": True,
            "materialization_gate": "PHASE2_REMEDIATION_MATERIALIZATION_REQUIRED",
        }
    )
    return base


def _markdown_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def render_markdown(payload: Mapping[str, Any]) -> str:
    counts = dict(payload.get("counts") or {})
    lines = [
        "# Phase 4 Residual Triage Decision Proposal",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Approval token: `{payload.get('operator_approval_token')}`",
        f"- Proposal SHA-256: `{payload.get('proposal_sha256')}`",
        f"- Decisions: `{counts.get('decisions', 0)}`",
        f"- Add occurrence: `{counts.get('add_occurrence', 0)}`",
        f"- Expand geometry: `{counts.get('expand_geometry', 0)}`",
        f"- Source-intrinsic false positive: `{counts.get('false_positive', 0)}`",
        f"- Covered by proposed occurrence: `{counts.get('linked_coverage', 0)}`",
        "- Proposal này chưa ghi OCR/remediation/approval authority.",
        "",
        "| Case | Cluster | Action | OCR đề xuất | Tiếng Việt đề xuất | Evidence |",
        "|---|---|---|---|---|---|",
    ]
    for case in list(payload.get("cases") or []):
        for decision in list(dict(case).get("decisions") or []):
            evidence = dict(decision.get("visual_evidence_ref") or {}).get("path")
            lines.append(
                f"| `{case.get('case_id')}` | `{decision.get('cluster_id')}` | "
                f"`{decision.get('proposed_action')}` | "
                f"{_markdown_escape(decision.get('source_text_suggested'))} | "
                f"{_markdown_escape(decision.get('vi_text_suggested'))} | "
                f"[{decision.get('signature')}]({case.get('case_id')}/{evidence}) |"
            )
    lines.append("")
    return "\n".join(lines)


def build_decision_proposal(
    *, run_root: str | Path, decisions_path: str | Path
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    decisions_file = Path(decisions_path).resolve()
    if not run.is_dir() or not decisions_file.is_file():
        raise ResidualTriageDecisionProposalError(
            "Run root or curated decisions file is missing"
        )
    if not decisions_file.is_relative_to(run):
        raise ResidualTriageDecisionProposalError(
            "Curated decisions must live inside the batch run root"
        )
    index_path = run / "phase4_residual_visual_triage_index.json"
    index = _load_object(index_path)
    _verify_self_hash(index, "batch_triage_sha256", label="Visual triage index")
    curated = _load_object(decisions_file)
    if (
        str(curated.get("status") or "") != "CURATED_PROPOSAL_INPUT"
        or bool(curated.get("operator_approval_written"))
        or str(curated.get("batch_triage_sha256") or "")
        != str(index.get("batch_triage_sha256") or "")
    ):
        raise ResidualTriageDecisionProposalError(
            "Curated decisions are stale or authoritative"
        )
    raw_decisions = [
        dict(row)
        for row in list(curated.get("decisions") or [])
        if isinstance(row, Mapping)
    ]
    keyed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in raw_decisions:
        key = (
            str(row.get("case_id") or ""),
            str(row.get("cluster_id") or ""),
        )
        if not all(key) or key in keyed:
            raise ResidualTriageDecisionProposalError(
                "Curated decisions contain a duplicate or missing key"
            )
        keyed[key] = row

    cases: list[dict[str, Any]] = []
    expected_keys: set[tuple[str, str]] = set()
    totals = {
        "cases": 0,
        "decisions": 0,
        "add_occurrence": 0,
        "expand_geometry": 0,
        "false_positive": 0,
        "linked_coverage": 0,
        "manual_tight_geometry": 0,
        "manual_evidence_geometry": 0,
    }
    for case_row_raw in list(index.get("cases") or []):
        case_row = dict(case_row_raw)
        case_id = str(case_row.get("case_id") or "")
        root = (run / case_id).resolve()
        if not root.is_relative_to(run) or not root.is_dir():
            raise ResidualTriageDecisionProposalError(
                f"Invalid case root: {case_id or 'unknown'}"
            )
        triage_path = _verify_ref(
            run,
            dict(case_row.get("triage_ref") or {}),
            label=f"{case_id} visual triage",
        )
        triage = _load_object(triage_path)
        _verify_self_hash(triage, "triage_sha256", label=f"{case_id} triage")
        if bool(triage.get("operator_approval_written")):
            raise ResidualTriageDecisionProposalError(
                f"{case_id} visual triage unexpectedly contains approval"
            )
        master_path = root / "master_timeline.json"
        phase2_path = root / "phase2_ocr_timeline.json"
        phase3_path = root / "phase3_render_handoff.json"
        master = _load_list(master_path)
        phase2 = _load_object(phase2_path)
        phase3 = _load_object(phase3_path)
        master_by_id = {
            str(row.get("text_id") or ""): row
            for row in master
            if str(row.get("text_id") or "")
        }
        content_map = _content_by_geometry(phase2)
        phase3_geometry = dict(phase3.get("geometry_map") or {})
        suggestions_path = root / "phase2_residual_translation_suggestions.json"
        suggestions: dict[str, str] = {}
        if suggestions_path.is_file():
            suggestion_payload = _load_object(suggestions_path)
            if (
                str(suggestion_payload.get("status") or "") != "SUGGESTION_ONLY"
                or bool(suggestion_payload.get("operator_approval_written"))
            ):
                raise ResidualTriageDecisionProposalError(
                    f"{case_id} translation suggestions are authoritative"
                )
            for raw in list(suggestion_payload.get("suggestions") or []):
                row = dict(raw)
                source = str(row.get("ocr_text") or "")
                vi_text = str(row.get("vi_text_suggested") or "")
                if source and vi_text:
                    suggestions[source] = vi_text

        built: list[dict[str, Any]] = []
        for cluster_raw in list(triage.get("clusters") or []):
            cluster = dict(cluster_raw)
            cluster_id = str(cluster.get("cluster_id") or "")
            key = (case_id, cluster_id)
            expected_keys.add(key)
            raw_decision = keyed.get(key)
            if raw_decision is None:
                raise ResidualTriageDecisionProposalError(
                    f"Missing curated decision: {case_id}/{cluster_id}"
                )
            _verify_cluster_evidence(root, cluster)
            decision = _build_decision(
                root=root,
                raw_decision=raw_decision,
                cluster=cluster,
                master_by_id=master_by_id,
                content_by_geometry=content_map,
                phase3_geometry_map=phase3_geometry,
                translation_suggestions=suggestions,
            )
            built.append(decision)
            totals["decisions"] += 1
            action = str(decision.get("proposed_action") or "")
            totals["add_occurrence"] += int(
                action == "ADD_PHASE2_OCCURRENCE"
            )
            totals["expand_geometry"] += int(
                action == "EXPAND_EXISTING_PHASE2_GEOMETRY"
            )
            totals["false_positive"] += int(
                action == "APPROVE_SOURCE_INTRINSIC_FALSE_POSITIVE"
            )
            totals["linked_coverage"] += int(
                action == "COVERED_BY_PROPOSED_OCCURRENCE"
            )
            totals["manual_tight_geometry"] += int(
                str(
                    dict(decision.get("proposed_occurrence") or {}).get(
                        "strategy"
                    )
                    or ""
                )
                == "MANUAL_TIGHT_GEOMETRY"
            )
            totals["manual_evidence_geometry"] += int(
                str(
                    dict(decision.get("proposed_occurrence") or {}).get(
                        "strategy"
                    )
                    or ""
                )
                == "MANUAL_EVIDENCE_GEOMETRY"
            )
        built_by_cluster = {
            str(row.get("cluster_id") or ""): row for row in built
        }
        for decision in built:
            if (
                str(decision.get("proposed_action") or "")
                != "COVERED_BY_PROPOSED_OCCURRENCE"
            ):
                continue
            linked_cluster_id = str(decision.get("linked_cluster_id") or "")
            linked = dict(built_by_cluster.get(linked_cluster_id) or {})
            if (
                str(linked.get("proposed_action") or "")
                != "ADD_PHASE2_OCCURRENCE"
                or str(linked.get("source_text_suggested") or "")
                != str(decision.get("source_text_suggested") or "")
                or str(linked.get("vi_text_suggested") or "")
                != str(decision.get("vi_text_suggested") or "")
            ):
                raise ResidualTriageDecisionProposalError(
                    "Linked residual must reference an additive occurrence "
                    f"with identical content: {decision.get('cluster_id')}"
                )
        cases.append(
            {
                "case_id": case_id,
                "visual_triage_ref": case_row.get("triage_ref"),
                "authority_refs": {
                    "master_timeline": {
                        "path": master_path.name,
                        "sha256": _sha256_file(master_path),
                    },
                    "phase2_ocr_timeline": {
                        "path": phase2_path.name,
                        "sha256": _sha256_file(phase2_path),
                    },
                    "phase3_render_handoff": {
                        "path": phase3_path.name,
                        "sha256": _sha256_file(phase3_path),
                    },
                },
                "decisions": built,
            }
        )
        totals["cases"] += 1
    if set(keyed) != expected_keys:
        extras = sorted(set(keyed) - expected_keys)
        raise ResidualTriageDecisionProposalError(
            f"Curated decisions contain unknown clusters: {extras}"
        )

    token_seed = _sha256_json(
        {
            "batch_triage_sha256": index.get("batch_triage_sha256"),
            "curated_decisions_sha256": _sha256_file(decisions_file),
            "case_decisions": [
                {
                    "case_id": case.get("case_id"),
                    "decisions": case.get("decisions"),
                }
                for case in cases
            ],
        }
    )[:12].upper()
    proposal: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "RESIDUAL_TRIAGE_DECISION_PROPOSAL_READY_FOR_OPERATOR_REVIEW",
        "operator_approval_token": (
            f"RESIDUAL_TRIAGE_DECISION_PROPOSALS_APPROVED_V22_1_{token_seed}"
        ),
        "operator_approval_written": False,
        "authority_mutation_written": False,
        "batch_visual_triage_ref": {
            "path": index_path.name,
            "sha256": _sha256_file(index_path),
            "batch_triage_sha256": index.get("batch_triage_sha256"),
        },
        "curated_input_ref": {
            "path": decisions_file.relative_to(run).as_posix(),
            "sha256": _sha256_file(decisions_file),
        },
        "counts": totals,
        "cases": cases,
    }
    proposal["proposal_sha256"] = _sha256_json(proposal)
    return proposal


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase4_residual_triage_decision_proposal"
    )
    parser.add_argument("run_root")
    parser.add_argument("decisions_json")
    parser.add_argument(
        "--output-stem",
        default="phase4_residual_triage_decision_proposal",
        help="Safe filename stem for immutable/versioned proposal output.",
    )
    args = parser.parse_args()
    try:
        run = Path(args.run_root).resolve()
        output_stem = str(args.output_stem or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", output_stem):
            raise ResidualTriageDecisionProposalError(
                "Output stem contains unsafe path characters"
            )
        proposal = build_decision_proposal(
            run_root=run, decisions_path=args.decisions_json
        )
        json_path = run / f"{output_stem}.json"
        markdown_path = run / f"{output_stem}.md"
        _write_json_atomic(json_path, proposal)
        _write_text_atomic(markdown_path, render_markdown(proposal))
        print(
            json.dumps(
                {
                    "status": proposal["status"],
                    "operator_approval_token": proposal[
                        "operator_approval_token"
                    ],
                    "counts": proposal["counts"],
                    "proposal_sha256": proposal["proposal_sha256"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except (OSError, ValueError, ResidualTriageDecisionProposalError) as exc:
        print(f"[RESIDUAL-TRIAGE-DECISION-PROPOSAL][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
