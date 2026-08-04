"""Materialize an explicitly approved residual-CJK proposal."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.build_phase2_residual_remediation_proposal import (
    ResidualRemediationProposalError,
    validate_proposal,
)
from src.services.residual_remediation_authority import (
    ACTIVE_POINTER_NAME,
    LEGACY_REMEDIATION_NAME,
    ResidualRemediationAuthorityError,
    build_active_remediation_pointer,
    resolve_active_residual_remediation,
)


class ResidualRemediationMaterializationError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResidualRemediationMaterializationError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise ResidualRemediationMaterializationError(
            f"{path.name} must contain an object"
        )
    return payload


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
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _capture_translation_authority(root: Path) -> dict[str, Any]:
    timeline_path = root / "phase3_translation_timeline.json"
    approvals_path = root / "phase3_approvals.json"
    handoff_path = root / "phase3_render_handoff.json"
    for path in (timeline_path, approvals_path, handoff_path):
        if not path.is_file():
            raise ResidualRemediationMaterializationError(
                f"Missing translation authority: {path.name}"
            )
    timeline = _load_object(timeline_path)
    approvals = _load_object(approvals_path)
    handoff = _load_object(handoff_path)
    if (
        str(dict(timeline.get("review_summary") or {}).get("status") or "")
        != "TRANSLATION_APPROVED"
        or str(handoff.get("status") or "") != "READY_FOR_RENDER"
    ):
        raise ResidualRemediationMaterializationError(
            "Translation authority is not fully approved"
        )
    approvals_by_id = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(approvals.get("approvals") or [])
        if isinstance(row, Mapping) and str(row.get("content_id") or "")
    }
    carry_rows: list[dict[str, Any]] = []
    for raw in list(timeline.get("content_objects") or []):
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        if str(row.get("review_status") or "") != "TRANSLATION_APPROVED":
            continue
        content_id = str(row.get("content_id") or "")
        approval = approvals_by_id.get(content_id) or {}
        operator_review = dict(row.get("operator_review") or {})
        if (
            str(approval.get("decision") or "").upper() not in {"APPROVE", "EDIT"}
            or str(approval.get("review_input_sha256") or "")
            != str(row.get("review_input_sha256") or "")
            or str(approval.get("vi_text_approved") or "").strip()
            != str(row.get("vi_text_approved") or "").strip()
            or not str(approval.get("reviewer") or "").strip()
            or not str(approval.get("reviewed_at") or "").strip()
            or bool(operator_review.get("stale"))
        ):
            raise ResidualRemediationMaterializationError(
                f"Invalid translation approval authority for {content_id}"
            )
        carry_rows.append(
            {
                "content_id": content_id,
                "decision": str(approval.get("decision") or "").upper(),
                "zh_approved": str(row.get("zh_approved") or ""),
                "vi_text_candidate": str(row.get("vi_text_candidate") or ""),
                "vi_text_approved": str(row.get("vi_text_approved") or ""),
                "reviewer": str(approval.get("reviewer") or ""),
                "reviewed_at": str(approval.get("reviewed_at") or ""),
                "previous_review_input_sha256": str(
                    approval.get("review_input_sha256") or ""
                ),
            }
        )
    if not carry_rows:
        raise ResidualRemediationMaterializationError(
            "No operator-reviewed translations are available to carry forward"
        )
    return {
        "source_refs": {
            "phase3_translation_timeline": {
                "path": timeline_path.name,
                "sha256": _sha256_file(timeline_path),
            },
            "phase3_approvals": {
                "path": approvals_path.name,
                "sha256": _sha256_file(approvals_path),
            },
            "phase3_render_handoff": {
                "path": handoff_path.name,
                "sha256": _sha256_file(handoff_path),
            },
        },
        "rows": carry_rows,
    }


def proposal_visual_override(
    proposal_row: Mapping[str, Any], *, proposal_sha256: str
) -> dict[str, Any]:
    """Bind an approved additive text to the exact reviewed image evidence."""
    row = dict(proposal_row)
    evidence = dict(row.get("evidence") or {})
    source_ocr = dict(evidence.get("source_ocr") or {})
    source_frame_ref = dict(evidence.get("source_frame_ref") or {})
    crop_ref = dict(evidence.get("crop_ref") or {})
    approved_text = str(row.get("ocr_text_suggested") or "").strip()
    detections = [
        dict(value)
        for value in list(evidence.get("phase4_detections") or [])
        if isinstance(value, Mapping)
    ]
    if (
        str(row.get("proposed_action") or "") != "ADD_PHASE2_OCCURRENCE"
        or len(str(proposal_sha256 or "")) != 64
        or not approved_text
        or str(source_ocr.get("text") or "").strip() != approved_text
        or not any(
            str(value.get("text") or "").strip().startswith(approved_text)
            for value in detections
        )
        or any(
            not str(ref.get("path") or "")
            or len(str(ref.get("sha256") or "")) != 64
            for ref in (source_frame_ref, crop_ref)
        )
    ):
        return {}
    return {
        "policy_version": "phase2_operator_visual_override_v1",
        "batch_decision_proposal_sha256": proposal_sha256,
        "cluster_evidence_sha256": _sha256_json(evidence),
        "approved_source_text_sha256": hashlib.sha256(
            approved_text.encode("utf-8")
        ).hexdigest(),
        "source_frame_ref": source_frame_ref,
        "crop_ref": crop_ref,
    }


def materialize_remediation(
    *,
    root_dir: str | Path,
    proposal_path: str | Path,
    approved_proposal_sha256: str,
    operator_id: str,
    approved_at: str,
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    proposal_file = Path(proposal_path).resolve()
    proposal = _load_object(proposal_file)
    try:
        validate_proposal(root, proposal)
    except ResidualRemediationProposalError as exc:
        raise ResidualRemediationMaterializationError(str(exc)) from exc
    claimed = str(proposal.get("proposal_sha256") or "")
    if claimed != str(approved_proposal_sha256 or ""):
        raise ResidualRemediationMaterializationError(
            "Operator-approved proposal SHA-256 does not match"
        )
    operator = str(operator_id or "").strip()
    timestamp = str(approved_at or "").strip()
    if not operator or not timestamp:
        raise ResidualRemediationMaterializationError(
            "operator_id and approved_at are required"
        )
    approved_occurrences: list[dict[str, Any]] = []
    approved_geometry_overrides: list[dict[str, Any]] = []
    for raw in list(proposal.get("proposals") or []):
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        action = str(row.get("proposed_action") or "")
        if action == "EXPAND_EXISTING_PHASE2_GEOMETRY":
            geometry_override = dict(
                row.get("proposed_geometry_override") or {}
            )
            approved_geometry_overrides.append(
                {
                    "remediation_id": row.get("remediation_id"),
                    "geometry_override": geometry_override,
                    "ocr_text_approved": row.get("ocr_text_suggested"),
                    "vi_text_approved": row.get("render_text_suggested"),
                    "accepted_candidate_signatures": list(
                        row.get("accepted_candidate_signatures") or []
                    ),
                    "localization": row.get("localization"),
                    "operator_review": {
                        "decision": "EDIT",
                        "reviewer": operator,
                        "reviewed_at": timestamp,
                        "proposal_sha256": claimed,
                    },
                }
            )
            continue
        occurrence = dict(row.get("proposed_occurrence") or {})
        if action != "ADD_PHASE2_OCCURRENCE":
            raise ResidualRemediationMaterializationError(
                "Unsupported residual remediation action"
            )
        approved_occurrences.append(
            {
                "remediation_id": row.get("remediation_id"),
                "occurrence": occurrence,
                "ocr_text_approved": row.get("ocr_text_suggested"),
                "vi_text_approved": row.get("render_text_suggested"),
                "localization": row.get("localization"),
                **(
                    {
                        "visual_override": visual_override,
                    }
                    if (
                        visual_override := proposal_visual_override(
                            row,
                            proposal_sha256=claimed,
                        )
                    )
                    else {}
                ),
                "operator_review": {
                    "decision": "APPROVE",
                    "reviewer": operator,
                    "reviewed_at": timestamp,
                    "proposal_sha256": claimed,
                },
            }
        )
    if not approved_occurrences and not approved_geometry_overrides:
        raise ResidualRemediationMaterializationError(
            "Proposal has no materializable changes"
        )
    payload: dict[str, Any] = {
        "schema_version": "phase2_residual_remediation_v2",
        "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
        "approved_at": timestamp,
        "operator_id": operator,
        "proposal_ref": {
            "path": proposal_file.name,
            "file_sha256": _sha256_file(proposal_file),
            "proposal_sha256": claimed,
        },
        "authority_refs": proposal.get("authority_refs"),
        "approved_occurrences": approved_occurrences,
        "approved_geometry_overrides": approved_geometry_overrides,
        "translation_carry_forward": _capture_translation_authority(root),
    }
    payload["remediation_sha256"] = _sha256_json(payload)
    return payload


def verify_remediation(payload: Mapping[str, Any]) -> bool:
    unsigned = dict(payload)
    claimed = str(unsigned.pop("remediation_sha256", "") or "")
    return (
        len(claimed) == 64
        and claimed == _sha256_json(unsigned)
        and str(payload.get("status") or "")
        == "OCR_RESIDUAL_REMEDIATION_APPROVED"
    )


def _snapshot_legacy_parent(
    *, root: Path, parent_path: Path, parent: Mapping[str, Any]
) -> Path:
    """Preserve a mutable legacy authority before it becomes a parent ref."""
    if parent_path.name != LEGACY_REMEDIATION_NAME:
        return parent_path
    self_hash = str(parent.get("remediation_sha256") or "")
    if len(self_hash) != 64:
        raise ResidualRemediationMaterializationError(
            "Legacy parent remediation self-hash is invalid"
        )
    snapshot = root / f"phase2_residual_remediation_{self_hash[:12]}.json"
    if snapshot.is_file():
        existing = _load_object(snapshot)
        if not verify_remediation(existing) or existing != dict(parent):
            raise ResidualRemediationMaterializationError(
                "Legacy parent snapshot conflicts with an existing artifact"
            )
        return snapshot
    _write_json_atomic(snapshot, parent)
    return snapshot


def merge_cumulative_remediation(
    *,
    root_dir: str | Path,
    delta: Mapping[str, Any],
    parent_path: str | Path | None,
) -> dict[str, Any]:
    """Merge one approved delta with an immutable remediation generation."""
    root = Path(root_dir).resolve()
    merged = dict(delta)
    merged.pop("remediation_sha256", None)
    delta_occurrences = [
        dict(row)
        for row in list(delta.get("approved_occurrences") or [])
        if isinstance(row, Mapping)
    ]
    delta_overrides = [
        dict(row)
        for row in list(delta.get("approved_geometry_overrides") or [])
        if isinstance(row, Mapping)
    ]
    if parent_path is None:
        merged.update(
            {
                "approved_occurrences": delta_occurrences,
                "approved_geometry_overrides": delta_overrides,
                "generation": 1,
                "delta_counts": {
                    "occurrences": len(delta_occurrences),
                    "geometry_overrides": len(delta_overrides),
                },
            }
        )
        merged["remediation_sha256"] = _sha256_json(merged)
        return merged

    resolved_parent = Path(parent_path).resolve()
    if not resolved_parent.is_relative_to(root) or not resolved_parent.is_file():
        raise ResidualRemediationMaterializationError(
            "Parent remediation is outside the artifact root"
        )
    parent = _load_object(resolved_parent)
    if not verify_remediation(parent):
        raise ResidualRemediationMaterializationError(
            "Parent residual remediation self-hash is invalid"
        )
    resolved_parent = _snapshot_legacy_parent(
        root=root,
        parent_path=resolved_parent,
        parent=parent,
    )
    parent_master = dict(
        dict(parent.get("authority_refs") or {}).get("master_timeline") or {}
    )
    delta_master = dict(
        dict(delta.get("authority_refs") or {}).get("master_timeline") or {}
    )
    if str(parent_master.get("sha256") or "") != str(
        delta_master.get("sha256") or ""
    ):
        raise ResidualRemediationMaterializationError(
            "Cumulative remediation targets another Phase 1 authority"
        )

    parent_occurrences = [
        dict(row)
        for row in list(parent.get("approved_occurrences") or [])
        if isinstance(row, Mapping)
    ]
    occurrence_ids = [
        str(dict(row.get("occurrence") or {}).get("text_id") or "")
        for row in [*parent_occurrences, *delta_occurrences]
    ]
    if any(not value for value in occurrence_ids) or len(set(occurrence_ids)) != len(
        occurrence_ids
    ):
        raise ResidualRemediationMaterializationError(
            "Cumulative remediation contains duplicate occurrence ids"
        )

    parent_overrides = [
        dict(row)
        for row in list(parent.get("approved_geometry_overrides") or [])
        if isinstance(row, Mapping)
    ]
    override_ids = [
        str(dict(row.get("geometry_override") or {}).get("target_text_id") or "")
        for row in [*parent_overrides, *delta_overrides]
    ]
    if any(not value for value in override_ids) or len(set(override_ids)) != len(
        override_ids
    ):
        raise ResidualRemediationMaterializationError(
            "Cumulative remediation contains duplicate geometry overrides"
        )

    authority = dict(delta.get("authority_refs") or {})
    authority["parent_remediation"] = {
        "path": resolved_parent.relative_to(root).as_posix(),
        "sha256": _sha256_file(resolved_parent),
        "remediation_sha256": parent.get("remediation_sha256"),
    }
    merged.update(
        {
            "authority_refs": authority,
            "approved_occurrences": [*parent_occurrences, *delta_occurrences],
            "approved_geometry_overrides": [*parent_overrides, *delta_overrides],
            "generation": int(parent.get("generation") or 1) + 1,
            "delta_counts": {
                "occurrences": len(delta_occurrences),
                "geometry_overrides": len(delta_overrides),
            },
        }
    )
    merged["remediation_sha256"] = _sha256_json(merged)
    return merged


def activate_cumulative_remediation(
    *,
    root_dir: str | Path,
    delta: Mapping[str, Any],
    parent_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Persist an immutable cumulative generation and atomically activate it."""
    root = Path(root_dir).resolve()
    if not verify_remediation(delta):
        raise ResidualRemediationMaterializationError(
            "Delta residual remediation self-hash is invalid"
        )
    proposal_sha = str(
        dict(delta.get("proposal_ref") or {}).get("proposal_sha256") or ""
    )
    if len(proposal_sha) != 64:
        raise ResidualRemediationMaterializationError(
            "Delta proposal SHA-256 is invalid"
        )
    resolved_parent: Path | None
    if parent_path is not None:
        resolved_parent = Path(parent_path).resolve()
    else:
        try:
            resolved_parent = resolve_active_residual_remediation(root)
        except ResidualRemediationAuthorityError as exc:
            raise ResidualRemediationMaterializationError(str(exc)) from exc
    if resolved_parent is not None:
        parent = _load_object(resolved_parent)
        if not verify_remediation(parent):
            raise ResidualRemediationMaterializationError(
                "Active parent remediation self-hash is invalid"
            )
        parent_proposal_sha = str(
            dict(parent.get("proposal_ref") or {}).get("proposal_sha256") or ""
        )
        if parent_proposal_sha == proposal_sha:
            return resolved_parent, parent

    delta_path = root / (
        f"phase2_residual_remediation_delta_{proposal_sha[:12]}.json"
    )
    if delta_path.is_file():
        existing_delta = _load_object(delta_path)
        if existing_delta != dict(delta):
            raise ResidualRemediationMaterializationError(
                "Approved remediation delta conflicts with an existing artifact"
            )
    else:
        _write_json_atomic(delta_path, delta)

    cumulative = merge_cumulative_remediation(
        root_dir=root,
        delta=delta,
        parent_path=resolved_parent,
    )
    if not verify_remediation(cumulative):
        raise ResidualRemediationMaterializationError(
            "Cumulative remediation self-hash is invalid"
        )
    output = root / f"phase2_residual_remediation_{proposal_sha[:12]}.json"
    if output.is_file():
        existing = _load_object(output)
        if existing != cumulative:
            raise ResidualRemediationMaterializationError(
                "Cumulative remediation conflicts with an existing generation"
            )
    else:
        _write_json_atomic(output, cumulative)
    pointer = build_active_remediation_pointer(
        root=root,
        remediation_path=output,
        remediation_sha256=str(cumulative.get("remediation_sha256") or ""),
    )
    _write_json_atomic(root / ACTIVE_POINTER_NAME, pointer)
    return output, cumulative


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.materialize_phase2_residual_remediation"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("proposal_json")
    parser.add_argument("--approve-proposal-sha", required=True)
    parser.add_argument("--operator", default="operator-user-approved-v20-1")
    args = parser.parse_args()
    try:
        root = Path(args.artifact_root).resolve()
        payload = materialize_remediation(
            root_dir=root,
            proposal_path=args.proposal_json,
            approved_proposal_sha256=args.approve_proposal_sha,
            operator_id=args.operator,
            approved_at=datetime.now(timezone.utc).isoformat(),
        )
        if not verify_remediation(payload):
            raise ResidualRemediationMaterializationError(
                "Materialized remediation self-hash is invalid"
            )
        output, cumulative = activate_cumulative_remediation(
            root_dir=root,
            delta=payload,
        )
        print(
            json.dumps(
                {
                    "status": cumulative["status"],
                    "occurrences": len(cumulative["approved_occurrences"]),
                    "geometry_overrides": len(
                        cumulative["approved_geometry_overrides"]
                    ),
                    "translation_carry_forward": len(
                        cumulative["translation_carry_forward"]["rows"]
                    ),
                    "generation": cumulative.get("generation"),
                    "remediation_sha256": cumulative["remediation_sha256"],
                    "output": str(output),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, ResidualRemediationMaterializationError) as exc:
        print(f"[P2-RESIDUAL-MATERIALIZE][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
