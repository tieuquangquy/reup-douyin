"""Build a fail-closed Phase 2 OCR proposal without recording approval.

Only byte-identical crops backed by a real prior operator decision are marked
eligible for carry-forward.  Everything else remains an explicit operator
checkpoint, even when an OCR candidate or a Codex-assisted suggestion exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.media_pipeline.frame_sampling.phase2_ocr_contract import (
    PHASE2_DUPLICATE_TRANSITION_POLICY_VERSION,
)


class Phase2ReviewProposalError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase2ReviewProposalError(f"Cannot read valid {path}") from exc
    if not isinstance(payload, dict):
        raise Phase2ReviewProposalError(f"{path} must contain an object")
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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _reviewed_crop_authority(reference_root: Path) -> dict[str, dict[str, str]]:
    timeline = _load_object(reference_root / "phase2_ocr_timeline.json")
    approvals_path = reference_root / "phase2_approvals.json"
    approvals = _load_object(approvals_path)
    approved_by_id: dict[str, dict[str, str]] = {}
    for raw in list(approvals.get("approvals") or []):
        if not isinstance(raw, Mapping):
            continue
        decision = str(raw.get("decision") or "").upper()
        text = str(raw.get("ocr_text_approved") or "").strip()
        reviewer = str(raw.get("reviewer") or "").strip()
        reviewed_at = str(raw.get("reviewed_at") or "").strip()
        content_id = str(raw.get("content_id") or "").strip()
        if (
            decision not in {"APPROVE", "EDIT"}
            or not text
            or not reviewer
            or not reviewed_at
            or not content_id
        ):
            continue
        approved_by_id[content_id] = {
            "content_id": content_id,
            "text": text,
            "decision": decision,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
        }

    authority: dict[str, dict[str, str]] = {}
    conflicted_hashes: set[str] = set()
    for raw in list(timeline.get("content_objects") or []):
        if not isinstance(raw, Mapping):
            continue
        content_id = str(raw.get("content_id") or "")
        reviewed = approved_by_id.get(content_id)
        if reviewed is None:
            continue
        for text_id in list(raw.get("geometry_refs") or []):
            crop = reference_root / "crops" / f"{text_id}.jpg"
            if not crop.is_file():
                continue
            crop_sha = _sha256_file(crop)
            previous = authority.get(crop_sha)
            if previous is not None and previous["text"] != reviewed["text"]:
                conflicted_hashes.add(crop_sha)
                continue
            authority[crop_sha] = dict(reviewed)
    for crop_sha in conflicted_hashes:
        authority.pop(crop_sha, None)
    return authority


def _proposal_spans(row: Mapping[str, Any]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for raw in list(row.get("review_assets") or []):
        if not isinstance(raw, Mapping):
            continue
        try:
            start = int(raw.get("start_frame"))
            end = int(raw.get("end_frame"))
        except (TypeError, ValueError):
            continue
        spans.append((min(start, end), max(start, end)))
    return spans


def _proposals_touch(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return any(
        left_start <= right_end + 1 and right_start <= left_end + 1
        for left_start, left_end in _proposal_spans(left)
        for right_start, right_end in _proposal_spans(right)
    )


def _transition_merge_groups(
    proposal_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for row in proposal_rows:
        text = "".join(str(row.get("ocr_text_suggested") or "").split())
        if not text:
            continue
        host = next(
            (
                group
                for group in groups
                if group["normalized_text"] == text
                and any(
                    _proposals_touch(member, row)
                    for member in group["members"]
                )
            ),
            None,
        )
        if host is None:
            groups.append({"normalized_text": text, "members": [row]})
        else:
            host["members"].append(row)
    return [
        {
            "policy_version": PHASE2_DUPLICATE_TRANSITION_POLICY_VERSION,
            "canonical_content_id": str(group["members"][0]["content_id"]),
            "source_content_ids": [
                str(member["content_id"]) for member in group["members"]
            ],
            "geometry_refs": [
                str(text_id)
                for member in group["members"]
                for text_id in list(member.get("geometry_refs") or [])
            ],
            "ocr_text_suggested": str(
                group["members"][0].get("ocr_text_suggested") or ""
            ),
            "status": "MERGE_AFTER_EXACT_OPERATOR_APPROVAL",
        }
        for group in groups
        if len(group["members"]) > 1
    ]


def _normalize_recommendations(
    recommendations: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for raw_content_id, raw in dict(recommendations or {}).items():
        content_id = str(raw_content_id).strip()
        if not content_id:
            raise Phase2ReviewProposalError("Recommendation has an empty content id")
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                raise Phase2ReviewProposalError(
                    f"Recommendation text is empty for {content_id}"
                )
            normalized[content_id] = {
                "decision": None,
                "ocr_text_suggested": text,
                "source_kind": "text_suggestion",
                "confidence": None,
                "reason": None,
                "evidence": [],
            }
            continue
        if not isinstance(raw, Mapping):
            raise Phase2ReviewProposalError(
                f"Recommendation for {content_id} must be text or an object"
            )
        decision = str(
            raw.get("decision") or raw.get("action") or ""
        ).strip().upper()
        if decision not in {
            "",
            "APPROVE",
            "EDIT",
            "REJECT_UI",
            "OPERATOR_INPUT_REQUIRED",
        }:
            raise Phase2ReviewProposalError(
                f"Unsupported recommendation decision for {content_id}: {decision}"
            )
        text = str(
            raw.get("ocr_text_suggested") or raw.get("text") or ""
        ).strip()
        if decision == "EDIT" and not text:
            raise Phase2ReviewProposalError(
                f"EDIT recommendation needs text for {content_id}"
            )
        if decision in {"REJECT_UI", "OPERATOR_INPUT_REQUIRED"} and text:
            raise Phase2ReviewProposalError(
                f"{decision} recommendation cannot include text for {content_id}"
            )
        evidence = raw.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        if not isinstance(evidence, list):
            raise Phase2ReviewProposalError(
                f"Recommendation evidence must be a list for {content_id}"
            )
        normalized[content_id] = {
            "decision": decision or None,
            "ocr_text_suggested": text or None,
            "source_kind": "structured_recommendation",
            "confidence": str(raw.get("confidence") or "").strip() or None,
            "reason": str(raw.get("reason") or "").strip() or None,
            "evidence": [str(value) for value in evidence if str(value).strip()],
        }
    return normalized


def build_review_proposal(
    *,
    target_root: Path,
    reference_root: Path,
    suggestions: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    queue_path = target_root / "phase2_review_queue.json"
    queue = _load_object(queue_path)
    authority = _reviewed_crop_authority(reference_root)
    recommendations_by_id = _normalize_recommendations(suggestions)
    queue_objects = [
        dict(raw)
        for raw in list(queue.get("content_objects") or [])
        if isinstance(raw, Mapping)
    ]
    queue_ids = {str(raw.get("content_id") or "") for raw in queue_objects}
    unknown_suggestions = sorted(set(recommendations_by_id) - queue_ids)
    if unknown_suggestions:
        raise Phase2ReviewProposalError(
            f"Unknown suggestion ids: {unknown_suggestions}"
        )

    proposal_rows: list[dict[str, Any]] = []
    carry_count = 0
    manual_count = 0
    input_required_count = 0
    decision_counts = {"APPROVE": 0, "EDIT": 0, "REJECT_UI": 0}
    for content in queue_objects:
        content_id = str(content.get("content_id") or "").strip()
        if not content_id:
            raise Phase2ReviewProposalError("Queue contains an empty content_id")
        crop_matches: list[dict[str, str]] = []
        crop_hashes: list[str] = []
        for text_id in list(content.get("geometry_refs") or []):
            crop = target_root / "crops" / f"{text_id}.jpg"
            if not crop.is_file():
                continue
            crop_sha = _sha256_file(crop)
            crop_hashes.append(crop_sha)
            if crop_sha in authority:
                crop_matches.append(authority[crop_sha])
        authority_texts = {row["text"] for row in crop_matches}
        inherited_text = authority_texts.pop() if len(authority_texts) == 1 else ""
        recommendation = recommendations_by_id.get(content_id)
        explicit_suggestion = str(
            dict(recommendation or {}).get("ocr_text_suggested") or ""
        ).strip()
        explicit_decision = str(
            dict(recommendation or {}).get("decision") or ""
        ).upper()
        candidate = str(content.get("ocr_text_candidate") or "").strip()
        proposed_text = explicit_suggestion or inherited_text or candidate
        carry_eligible = bool(
            inherited_text
            and not recommendation
        )
        if carry_eligible:
            carry_count += 1
            status = "CARRY_FORWARD_ELIGIBLE"
            suggestion_source = "exact_reviewed_crop_sha256"
        elif explicit_decision == "OPERATOR_INPUT_REQUIRED":
            manual_count += 1
            input_required_count += 1
            status = "OPERATOR_INPUT_REQUIRED"
            suggestion_source = "explicit_fail_closed_operator_input"
            proposed_text = ""
        else:
            manual_count += 1
            status = "OPERATOR_REVIEW_REQUIRED"
            suggestion_source = (
                "explicit_unapproved_suggestion"
                if dict(recommendation or {}).get("source_kind")
                == "text_suggestion"
                else "explicit_unapproved_recommendation"
                if recommendation
                else "current_ocr_candidate"
            )
        proposed_decision = None
        if explicit_decision == "REJECT_UI":
            proposed_text = ""
            proposed_decision = "REJECT_UI"
        elif explicit_decision in {"APPROVE", "EDIT"}:
            proposed_decision = explicit_decision
        elif proposed_text:
            proposed_decision = "APPROVE" if proposed_text == candidate else "EDIT"
        if proposed_decision == "APPROVE" and proposed_text != candidate:
            raise Phase2ReviewProposalError(
                f"APPROVE recommendation must preserve candidate for {content_id}"
            )
        if proposed_decision == "EDIT" and not proposed_text:
            raise Phase2ReviewProposalError(
                f"EDIT recommendation needs text for {content_id}"
            )
        if proposed_decision in decision_counts:
            decision_counts[proposed_decision] += 1
        proposal_rows.append(
            {
                "content_id": content_id,
                "geometry_refs": list(content.get("geometry_refs") or []),
                "review_assets": list(content.get("review_assets") or []),
                "ocr_text_candidate": candidate,
                "ocr_text_suggested": proposed_text or None,
                "proposed_decision": proposed_decision,
                "proposal_status": status,
                "suggestion_source": suggestion_source,
                "recommendation_confidence": dict(recommendation or {}).get(
                    "confidence"
                ),
                "recommendation_reason": dict(recommendation or {}).get("reason"),
                "recommendation_evidence": list(
                    dict(recommendation or {}).get("evidence") or []
                ),
                "review_input_sha256": content.get("review_input_sha256"),
                "crop_sha256": sorted(set(crop_hashes)),
                "reference_authority": (
                    {
                        "content_ids": sorted(
                            {row["content_id"] for row in crop_matches}
                        ),
                        "reviewers": sorted({row["reviewer"] for row in crop_matches}),
                        "reviewed_at": sorted(
                            {row["reviewed_at"] for row in crop_matches}
                        ),
                    }
                    if carry_eligible
                    else None
                ),
            }
        )

    proposal: dict[str, Any] = {
        "schema_version": "phase2_review_proposal_v1",
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat(),
        "status": "OPERATOR_APPROVAL_REQUIRED",
        "review_queue_ref": {
            "path": queue_path.name,
            "sha256": _sha256_file(queue_path),
        },
        "phase1_ref": queue.get("phase1_ref"),
        "reference": {
            "root": str(reference_root),
            "approvals_sha256": _sha256_file(
                reference_root / "phase2_approvals.json"
            ),
            "matching_policy": "exact_crop_sha256_and_reviewed_decision_only",
        },
        "counts": {
            "objects": len(proposal_rows),
            "carry_forward_eligible": carry_count,
            "operator_review_required": manual_count,
            "explicit_suggestions": len(recommendations_by_id),
            "operator_input_required": input_required_count,
            "proposed_approve": decision_counts["APPROVE"],
            "proposed_edit": decision_counts["EDIT"],
            "proposed_reject_ui": decision_counts["REJECT_UI"],
            "transition_merge_groups": 0,
        },
        "proposals": proposal_rows,
    }
    transition_merge_groups = _transition_merge_groups(proposal_rows)
    proposal["transition_merge_groups"] = transition_merge_groups
    proposal["counts"]["transition_merge_groups"] = len(
        transition_merge_groups
    )
    proposal["proposal_sha256"] = _sha256_json(proposal)
    return proposal


def validate_review_proposal(
    *, target_root: Path, proposal: Mapping[str, Any]
) -> None:
    unsigned = dict(proposal)
    claimed = str(unsigned.pop("proposal_sha256", "") or "")
    if len(claimed) != 64 or claimed != _sha256_json(unsigned):
        raise Phase2ReviewProposalError("Proposal self-hash is invalid")
    queue_path = target_root / "phase2_review_queue.json"
    queue = _load_object(queue_path)
    if str(dict(proposal.get("review_queue_ref") or {}).get("sha256") or "") != (
        _sha256_file(queue_path)
    ):
        raise Phase2ReviewProposalError("Proposal is stale for the review queue")
    queue_ids = {
        str(row.get("content_id") or "")
        for row in list(queue.get("content_objects") or [])
        if isinstance(row, Mapping)
    }
    proposal_ids = [
        str(row.get("content_id") or "")
        for row in list(proposal.get("proposals") or [])
        if isinstance(row, Mapping)
    ]
    if len(proposal_ids) != len(set(proposal_ids)) or set(proposal_ids) != queue_ids:
        raise Phase2ReviewProposalError(
            "Proposal must cover every queue object exactly once"
        )
    for raw in list(proposal.get("proposals") or []):
        if not isinstance(raw, Mapping):
            raise Phase2ReviewProposalError("Proposal contains an invalid row")
        content_id = str(raw.get("content_id") or "")
        decision = str(raw.get("proposed_decision") or "").upper()
        status = str(raw.get("proposal_status") or "")
        text = str(raw.get("ocr_text_suggested") or "").strip()
        candidate = str(raw.get("ocr_text_candidate") or "").strip()
        if decision not in {"", "APPROVE", "EDIT", "REJECT_UI"}:
            raise Phase2ReviewProposalError(
                f"Unsupported proposal decision for {content_id}"
            )
        if decision == "APPROVE" and text != candidate:
            raise Phase2ReviewProposalError(
                f"APPROVE proposal changed candidate for {content_id}"
            )
        if decision == "EDIT" and not text:
            raise Phase2ReviewProposalError(
                f"EDIT proposal is missing text for {content_id}"
            )
        if decision == "REJECT_UI" and text:
            raise Phase2ReviewProposalError(
                f"REJECT_UI proposal includes text for {content_id}"
            )
        if status == "OPERATOR_INPUT_REQUIRED" and (decision or text):
            raise Phase2ReviewProposalError(
                f"Operator-input row is materializable for {content_id}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target_root")
    parser.add_argument("reference_root")
    parser.add_argument("--suggestions")
    parser.add_argument("--output")
    args = parser.parse_args()
    target = Path(args.target_root).resolve()
    reference = Path(args.reference_root).resolve()
    suggestions: dict[str, Any] = {}
    if args.suggestions:
        raw = _load_object(Path(args.suggestions).resolve())
        values = raw.get("suggestions", raw)
        if not isinstance(values, Mapping):
            raise Phase2ReviewProposalError("Suggestions must be an object")
        suggestions = {str(key): value for key, value in values.items()}
    proposal = build_review_proposal(
        target_root=target,
        reference_root=reference,
        suggestions=suggestions,
    )
    validate_review_proposal(target_root=target, proposal=proposal)
    output = (
        Path(args.output).resolve()
        if args.output
        else target / "phase2_review_proposal.json"
    )
    _write_json_atomic(output, proposal)
    print(
        json.dumps(
            {
                "output": str(output),
                "status": proposal["status"],
                "counts": proposal["counts"],
                "proposal_sha256": proposal["proposal_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
