"""Recover a lost residual-remediation generation from approved Phase-2 artifacts.

This is a fail-closed operational repair for the legacy period where a later
materialization could overwrite ``phase2_residual_remediation.json``. It does
not create new operator decisions; it projects only already-approved content
and geometry recorded in the hash-bound Phase-2 timeline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.materialize_phase2_residual_remediation import (
    ResidualRemediationMaterializationError,
    _capture_translation_authority,
    _load_object,
    _sha256_file,
    _sha256_json,
    _write_json_atomic,
    verify_remediation,
)


class ResidualRemediationRecoveryError(RuntimeError):
    pass


_OCR_RUNTIME_FIELDS = {"ocr_text", "ocr_source", "ocr_frame"}


def _approved_content_by_text_id(
    contract: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    content_by_id = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(contract.get("content_objects") or [])
        if isinstance(row, Mapping) and str(row.get("content_id") or "")
    }
    result: dict[str, dict[str, Any]] = {}
    for raw in list(contract.get("track_enrichments") or []):
        if not isinstance(raw, Mapping):
            continue
        text_id = str(raw.get("text_id") or "")
        content_id = str(raw.get("content_id") or "")
        content = content_by_id.get(content_id)
        if text_id and content is not None:
            result[text_id] = content
    return result


def _operator_authority(content: Mapping[str, Any], *, text_id: str) -> dict[str, Any]:
    review = dict(content.get("operator_review") or {})
    decision = str(review.get("decision") or "").upper()
    reviewer = str(review.get("reviewer") or "").strip()
    reviewed_at = str(review.get("reviewed_at") or "").strip()
    if (
        str(content.get("review_status") or "") != "OCR_APPROVED"
        or decision not in {"APPROVE", "EDIT"}
        or not reviewer
        or not reviewed_at
        or bool(review.get("stale"))
    ):
        raise ResidualRemediationRecoveryError(
            f"Phase-2 operator authority is incomplete for {text_id}"
        )
    return {
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "recovered_from_review_input_sha256": review.get("review_input_sha256"),
    }


def reconstruct_remediation(
    *,
    root_dir: str | Path,
    phase2_timeline_path: str | Path,
) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    timeline_path = Path(phase2_timeline_path).resolve()
    if not timeline_path.is_relative_to(root) or not timeline_path.is_file():
        raise ResidualRemediationRecoveryError(
            "Phase-2 timeline is outside the artifact root"
        )
    contract = _load_object(timeline_path)
    original_ref = dict(contract.get("residual_remediation_ref") or {})
    original_file_sha = str(original_ref.get("sha256") or "")
    original_self_sha = str(original_ref.get("remediation_sha256") or "")
    if len(original_file_sha) != 64 or len(original_self_sha) != 64:
        raise ResidualRemediationRecoveryError(
            "Phase-2 timeline has no hash-bound remediation reference"
        )
    legacy = (root / str(original_ref.get("path") or "")).resolve()
    if legacy.is_file() and _sha256_file(legacy) == original_file_sha:
        raise ResidualRemediationRecoveryError(
            "Original remediation still exists; recovery is unnecessary"
        )

    content_by_text = _approved_content_by_text_id(contract)
    occurrences: list[dict[str, Any]] = []
    reviewers: set[str] = set()
    reviewed_at_values: list[str] = []
    for raw in list(contract.get("supplemental_occurrences") or []):
        if not isinstance(raw, Mapping):
            continue
        occurrence = {
            key: value
            for key, value in dict(raw).items()
            if key not in _OCR_RUNTIME_FIELDS
        }
        text_id = str(occurrence.get("text_id") or "")
        content = content_by_text.get(text_id)
        if not text_id or content is None:
            raise ResidualRemediationRecoveryError(
                f"Cannot bind recovered occurrence to approved content: {text_id}"
            )
        review = _operator_authority(content, text_id=text_id)
        reviewers.add(str(review["reviewer"]))
        reviewed_at_values.append(str(review["reviewed_at"]))
        ocr_text = str(content.get("ocr_text_approved") or "").strip()
        vi_text = str(content.get("vi_text_approved") or "").strip()
        if not ocr_text or not vi_text:
            raise ResidualRemediationRecoveryError(
                f"Recovered content text is incomplete for {text_id}"
            )
        occurrences.append(
            {
                "remediation_id": text_id,
                "occurrence": occurrence,
                "ocr_text_approved": ocr_text,
                "vi_text_approved": vi_text,
                "localization": dict(content.get("localization") or {}),
                "operator_review": review,
            }
        )
    if not occurrences:
        raise ResidualRemediationRecoveryError(
            "Phase-2 timeline contains no recoverable supplemental occurrences"
        )
    occurrence_ids = [
        str(dict(row.get("occurrence") or {}).get("text_id") or "")
        for row in occurrences
    ]
    if len(set(occurrence_ids)) != len(occurrence_ids):
        raise ResidualRemediationRecoveryError(
            "Recovered Phase-2 timeline contains duplicate occurrence ids"
        )

    master_path = root / "master_timeline.json"
    if not master_path.is_file():
        raise ResidualRemediationRecoveryError("master_timeline.json is missing")
    master_sha = _sha256_file(master_path)
    phase1_ref = dict(contract.get("phase1_ref") or {})
    if str(phase1_ref.get("sha256") or "") != master_sha:
        raise ResidualRemediationRecoveryError(
            "Recovered Phase-2 timeline targets a stale Phase-1 authority"
        )

    payload: dict[str, Any] = {
        "schema_version": "phase2_residual_remediation_v2",
        "status": "OCR_RESIDUAL_REMEDIATION_APPROVED",
        "approved_at": max(reviewed_at_values),
        "operator_id": (
            next(iter(reviewers)) if len(reviewers) == 1 else "authority-recovery"
        ),
        "proposal_ref": {
            "path": str(original_ref.get("path") or ""),
            "file_sha256": original_file_sha,
            "proposal_sha256": original_self_sha,
            "recovered": True,
        },
        "authority_refs": {
            "master_timeline": {
                "path": master_path.name,
                "sha256": master_sha,
            },
            "recovered_phase2_timeline": {
                "path": timeline_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(timeline_path),
            },
            "overwritten_remediation_ref": original_ref,
        },
        "approved_occurrences": occurrences,
        "approved_geometry_overrides": [],
        "translation_carry_forward": _capture_translation_authority(root),
        "generation": 1,
        "delta_counts": {
            "occurrences": len(occurrences),
            "geometry_overrides": 0,
        },
        "recovery": {
            "method": "approved_phase2_timeline_projection_v1",
            "creates_new_operator_decisions": False,
            "reason": "legacy_remediation_was_overwritten_by_later_delta",
        },
    }
    payload["remediation_sha256"] = _sha256_json(payload)
    if not verify_remediation(payload):
        raise ResidualRemediationRecoveryError(
            "Recovered remediation self-hash is invalid"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.recover_phase2_residual_remediation"
    )
    parser.add_argument("artifact_root")
    parser.add_argument(
        "--phase2-timeline",
        default="phase2_ocr_timeline.json",
    )
    args = parser.parse_args()
    try:
        root = Path(args.artifact_root).resolve()
        timeline = (root / args.phase2_timeline).resolve()
        payload = reconstruct_remediation(
            root_dir=root,
            phase2_timeline_path=timeline,
        )
        original_self_sha = str(
            dict(payload.get("proposal_ref") or {}).get("proposal_sha256") or ""
        )
        output = root / (
            f"phase2_residual_remediation_recovered_{original_self_sha[:12]}.json"
        )
        _write_json_atomic(output, payload)
        print(
            json.dumps(
                {
                    "status": "RECOVERED_AUTHORITY_READY",
                    "occurrences": len(payload["approved_occurrences"]),
                    "remediation_sha256": payload["remediation_sha256"],
                    "output": str(output),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (
        OSError,
        ValueError,
        ResidualRemediationMaterializationError,
        ResidualRemediationRecoveryError,
    ) as exc:
        print(f"[P2-RESIDUAL-RECOVER][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
