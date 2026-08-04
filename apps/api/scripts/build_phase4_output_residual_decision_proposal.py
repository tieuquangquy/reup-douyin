"""Combine V22.8 residual review and translations into operator decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


class OutputResidualDecisionProposalError(RuntimeError):
    pass


OPERATOR_SOURCE_TEMPLATE_STRATEGY = "OPERATOR_CONFIRMED_SOURCE_TEMPLATE_V1"


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
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise OutputResidualDecisionProposalError(f"{path.name} must contain an object")
    return payload


def _verify_self_hash(payload: Mapping[str, Any], field: str) -> None:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    if len(claimed) != 64 or claimed != _sha256_json(unsigned):
        raise OutputResidualDecisionProposalError(f"Invalid self-hash: {field}")


def _source_key(value: Any) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")))


def source_boundary_failure_history(
    case_root: str | Path,
    *,
    cluster_id: str,
    source_text: str,
) -> list[dict[str, Any]]:
    """Return distinct hash-valid prior approval failures for one source label."""

    root = Path(case_root).resolve()
    wanted_cluster = str(cluster_id or "")
    wanted_source = _source_key(source_text)
    rows: list[dict[str, Any]] = []
    seen_approvals: set[str] = set()
    for path in sorted(root.glob("phase4_output_source_boundary_rescan_*.json")):
        payload = _load_object(path)
        try:
            _verify_self_hash(payload, "rescan_sha256")
        except OutputResidualDecisionProposalError:
            continue
        approval_ref = dict(
            dict(payload.get("authority_refs") or {}).get("decision_approval") or {}
        )
        approval_identity = str(
            approval_ref.get("approval_sha256")
            or approval_ref.get("sha256")
            or _sha256_file(path)
        )
        if approval_identity in seen_approvals:
            continue
        attempt = next(
            (
                dict(raw)
                for raw in list(payload.get("attempts") or [])
                if isinstance(raw, Mapping)
                and str(dict(raw).get("status") or "")
                == "SOURCE_BOUNDARY_VALIDATION_FAILED"
                and (
                    str(dict(raw).get("cluster_id") or "") == wanted_cluster
                    or (
                        wanted_source
                        and _source_key(dict(raw).get("source_text")) == wanted_source
                    )
                )
            ),
            None,
        )
        if attempt is None:
            continue
        seen_approvals.add(approval_identity)
        rows.append(
            {
                "path": path.name,
                "sha256": _sha256_file(path),
                "rescan_sha256": payload.get("rescan_sha256"),
                "decision_approval_sha256": approval_ref.get("approval_sha256"),
                "attempt_cluster_id": attempt.get("cluster_id"),
                "source_text": attempt.get("source_text"),
                "failure_reason": attempt.get("failure_reason"),
            }
        )
    return rows


def geometry_strategy_for_history(history: Sequence[Mapping[str, Any]]) -> str:
    return (
        OPERATOR_SOURCE_TEMPLATE_STRATEGY
        if len(list(history)) >= 2
        else "CLUSTER_GEOMETRY"
    )


def decision_for_cluster(
    cluster: Mapping[str, Any],
    *,
    translation_suggestion: Mapping[str, Any] | None = None,
    geometry_strategy: str = "CLUSTER_GEOMETRY",
) -> dict[str, Any]:
    recommendation = dict(cluster.get("recommendation") or {})
    category = str(recommendation.get("decision") or "")
    source_text = recommendation.get("source_text_suggested")
    vi_text = recommendation.get("vi_text_suggested")
    translation_authority = recommendation.get("translation_authority")
    if category == "CARRY_FORWARD_APPROVED_CONTENT_COVERAGE":
        action = "CARRY_FORWARD_APPROVED_CONTENT_COVERAGE"
    elif category == "FALSE_POSITIVE_REVIEW":
        suggestion = dict(translation_suggestion or {})
        if (
            str(suggestion.get("suggestion_status") or "")
            == "TRANSLATION_SUGGESTION_ONLY"
        ):
            action = "APPROVE_TRANSLATION_SUGGESTION_AND_COVERAGE"
            source_text = suggestion.get("source_text_corrected")
            vi_text = suggestion.get("vi_text_suggested")
            translation_authority = "CURATED_FALSE_POSITIVE_RECLASSIFICATION"
        else:
            action = "APPROVE_RESIDUAL_FALSE_POSITIVE"
    elif category == "SOURCE_OCR_CORRECTION_AND_COVERAGE_REVIEW":
        suggestion = dict(translation_suggestion or {})
        if (
            str(suggestion.get("suggestion_status") or "")
            == "TRANSLATION_SUGGESTION_ONLY"
        ):
            action = "APPROVE_TRANSLATION_SUGGESTION_AND_COVERAGE"
            source_text = suggestion.get("source_text_corrected")
            vi_text = suggestion.get("vi_text_suggested")
            translation_authority = "CURATED_SOURCE_OCR_RECLASSIFICATION"
        else:
            action = "CORRECT_OCR_AND_CARRY_FORWARD_COVERAGE"
    elif category == "TRANSLATION_SUGGESTION_AND_COVERAGE_REVIEW":
        action = "APPROVE_TRANSLATION_SUGGESTION_AND_COVERAGE"
    elif category == "TRANSLATION_INPUT_AND_COVERAGE_REVIEW":
        suggestion = dict(translation_suggestion or {})
        if not suggestion:
            raise OutputResidualDecisionProposalError(
                f"Missing translation suggestion for {cluster.get('cluster_id')}"
            )
        if (
            str(suggestion.get("suggestion_status") or "")
            == "MIXED_RENDER_OCR_FALSE_POSITIVE_CANDIDATE"
        ):
            action = "APPROVE_RESIDUAL_FALSE_POSITIVE"
            source_text = suggestion.get("source_text_observed")
            vi_text = None
            translation_authority = "FALSE_POSITIVE_CANDIDATE"
        else:
            action = "APPROVE_TRANSLATION_SUGGESTION_AND_COVERAGE"
            source_text = suggestion.get("source_text_corrected")
            vi_text = suggestion.get("vi_text_suggested")
            translation_authority = "SUGGESTION_ONLY"
    elif category == "DETERMINISTIC_LOCALIZATION_AND_COVERAGE_REVIEW":
        suggestion = dict(translation_suggestion or {})
        if (
            str(suggestion.get("suggestion_status") or "")
            == "TRANSLATION_SUGGESTION_ONLY"
        ):
            action = "CORRECT_OCR_AND_CARRY_FORWARD_COVERAGE"
            source_text = suggestion.get("source_text_corrected")
            vi_text = suggestion.get("vi_text_suggested")
            translation_authority = "DETERMINISTIC_CORRECTION_SUGGESTION"
        else:
            action = "APPROVE_DETERMINISTIC_LOCALIZATION_AND_COVERAGE"
            translation_authority = "DETERMINISTIC_CANDIDATE"
    else:
        raise OutputResidualDecisionProposalError(
            f"Unsupported residual category: {category or 'missing'}"
        )
    if action != "APPROVE_RESIDUAL_FALSE_POSITIVE" and (
        not str(source_text or "").strip() or not str(vi_text or "").strip()
    ):
        raise OutputResidualDecisionProposalError(
            f"Incomplete remediation decision: {cluster.get('cluster_id')}"
        )
    evidence = dict(cluster.get("evidence") or {})
    return {
        "cluster_id": cluster.get("cluster_id"),
        "proposed_action": action,
        "source_text_suggested": source_text,
        "vi_text_suggested": vi_text,
        "translation_authority": translation_authority,
        "content_ids": list(recommendation.get("content_ids") or []),
        "active_intersections": list(
            recommendation.get("active_intersections") or []
        ),
        "geometry_strategy": str(geometry_strategy),
        "temporal_strategy": (
            "NOT_APPLICABLE"
            if action == "APPROVE_RESIDUAL_FALSE_POSITIVE"
            else "SOURCE_BOUNDARY_RESCAN_REQUIRED"
        ),
        "representative_frame_index": cluster.get("representative_frame_index"),
        "evidence_ref": evidence.get("source_render_contact_sheet"),
        "source_render_crop_mean_abs_delta": evidence.get(
            "source_render_crop_mean_abs_delta"
        ),
        "proposal_only": True,
        "operator_approval_written": False,
    }


def approved_translation_from_phase3(
    case_root: Path, cluster: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Reuse approved Phase-3 translation when an output tail has no active track."""

    path = case_root / "phase3_translation_timeline.json"
    if not path.is_file():
        return None
    try:
        payload = _load_object(path)
    except (OSError, json.JSONDecodeError, OutputResidualDecisionProposalError):
        return None
    wanted = {
        str(value or "")
        for value in list(
            dict(cluster.get("recommendation") or {}).get("content_ids") or []
        )
        if str(value or "")
    }
    if not wanted:
        return None
    for raw in list(payload.get("content_objects") or []):
        if not isinstance(raw, Mapping) or str(raw.get("content_id") or "") not in wanted:
            continue
        source = str(raw.get("zh_approved") or "").strip()
        vi_text = str(raw.get("vi_text_approved") or "").strip()
        if (
            not source
            or not vi_text
            or str(raw.get("review_status") or "") != "TRANSLATION_APPROVED"
        ):
            continue
        return {
            "suggestion_status": "TRANSLATION_SUGGESTION_ONLY",
            "source_text_observed": str(
                dict(cluster.get("recommendation") or {}).get(
                    "source_text_suggested"
                )
                or ""
            ),
            "source_text_corrected": source,
            "vi_text_suggested": vi_text,
            "review_decision_overridden": "PHASE3_APPROVED_CONTENT_FALLBACK",
        }
    return None


def build_proposal(
    run_root: str | Path,
    *,
    review_name: str = "phase4_output_residual_review_v22_8.json",
    approval_name: str = "phase4_output_residual_review_approval_v22_8.json",
    suggestions_name: str = (
        "phase4_output_residual_translation_suggestions_v22_8_1.json"
    ),
    decision_version: str = "V22_8_1",
) -> dict[str, Any]:
    root = Path(run_root).resolve()
    for value in (review_name, approval_name, suggestions_name):
        if Path(str(value)).name != str(value) or not str(value).endswith(".json"):
            raise OutputResidualDecisionProposalError(
                "Invalid decision authority filename"
            )
    review_path = root / review_name
    approval_path = root / approval_name
    suggestions_path = root / suggestions_name
    review = _load_object(review_path)
    approval = _load_object(approval_path)
    suggestions = _load_object(suggestions_path)
    _verify_self_hash(review, "review_sha256")
    _verify_self_hash(approval, "approval_sha256")
    _verify_self_hash(suggestions, "suggestions_sha256")
    if (
        str(approval.get("status") or "")
        != "PHASE4_OUTPUT_RESIDUAL_REVIEW_APPROVED"
        or str(suggestions.get("status") or "")
        != "SUGGESTIONS_READY_FOR_OPERATOR_REVIEW"
        or int(dict(suggestions.get("counts") or {}).get("unresolved") or 0) != 0
    ):
        raise OutputResidualDecisionProposalError(
            "Review approval or translations are not proposal-ready"
        )
    if (
        str(dict(approval.get("review_ref") or {}).get("sha256") or "")
        != _sha256_file(review_path)
        or str(dict(approval.get("review_ref") or {}).get("review_sha256") or "")
        != str(review.get("review_sha256") or "")
        or str(
            dict(dict(suggestions.get("authority_refs") or {}).get("review") or {}).get(
                "sha256"
            )
            or ""
        )
        != _sha256_file(review_path)
        or str(
            dict(
                dict(suggestions.get("authority_refs") or {}).get("review_approval")
                or {}
            ).get("sha256")
            or ""
        )
        != _sha256_file(approval_path)
    ):
        raise OutputResidualDecisionProposalError(
            "Decision proposal dependencies are stale"
        )
    suggestion_by_cluster = {
        str(row.get("cluster_id") or ""): dict(row)
        for raw in list(suggestions.get("suggestions") or [])
        if isinstance(raw, Mapping)
        for row in (dict(raw),)
        if str(row.get("cluster_id") or "")
    }
    cases: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    seen_suggestions: set[str] = set()
    for raw_case in list(review.get("cases") or []):
        case = dict(raw_case)
        case_id = str(case.get("case_id") or "")
        decisions: list[dict[str, Any]] = []
        for raw_cluster in list(case.get("clusters") or []):
            cluster = dict(raw_cluster)
            cluster_id = str(cluster.get("cluster_id") or "")
            suggestion = suggestion_by_cluster.get(cluster_id)
            if suggestion is not None:
                seen_suggestions.add(cluster_id)
            if suggestion is None:
                suggestion = approved_translation_from_phase3(
                    root / case_id, cluster
                )
            decision = decision_for_cluster(
                cluster,
                translation_suggestion=suggestion,
                geometry_strategy=(
                    "SOURCE_OCR_EXACT_BOX_RESCAN"
                    if str(decision_version).strip().upper() == "V22_9"
                    else "CLUSTER_GEOMETRY"
                ),
            )
            if str(decision_version).strip().upper() != "V22_9":
                failure_history = source_boundary_failure_history(
                    root / case_id,
                    cluster_id=cluster_id,
                    source_text=str(decision.get("source_text_suggested") or ""),
                )
                geometry_strategy = geometry_strategy_for_history(failure_history)
                decision["geometry_strategy"] = geometry_strategy
                decision["source_boundary_failure_count"] = len(failure_history)
                decision["source_boundary_failure_history"] = failure_history
                decision["operator_confirmed_source_template_required"] = (
                    geometry_strategy == OPERATOR_SOURCE_TEMPLATE_STRATEGY
                )
                if geometry_strategy == OPERATOR_SOURCE_TEMPLATE_STRATEGY:
                    decision["temporal_strategy"] = (
                        "OPERATOR_CONFIRMED_TEMPLATE_TRACKING_REQUIRED"
                    )
            counts[str(decision["proposed_action"])] += 1
            decisions.append(decision)
        cases.append(
            {
                "case_id": case_id,
                "authority_refs": case.get("authority_refs"),
                "decisions": decisions,
            }
        )
    if seen_suggestions != set(suggestion_by_cluster):
        raise OutputResidualDecisionProposalError(
            "Translation suggestions contain unknown residual clusters"
        )
    geometry_counts = Counter(
        str(decision.get("geometry_strategy") or "UNKNOWN")
        for case in cases
        for decision in list(case.get("decisions") or [])
    )
    template_required = bool(
        geometry_counts.get(OPERATOR_SOURCE_TEMPLATE_STRATEGY, 0)
    )
    payload: dict[str, Any] = {
        "schema_version": "phase4_output_residual_decision_proposal_v1",
        "decision_version": str(decision_version).strip().upper(),
        "status": "OUTPUT_RESIDUAL_DECISIONS_READY_FOR_OPERATOR_REVIEW",
        "operator_approval_written": False,
        "authority_mutation_written": False,
        "authority_refs": {
            "review": {
                "path": review_path.name,
                "sha256": _sha256_file(review_path),
                "review_sha256": review.get("review_sha256"),
            },
            "review_approval": {
                "path": approval_path.name,
                "sha256": _sha256_file(approval_path),
                "approval_sha256": approval.get("approval_sha256"),
            },
            "translation_suggestions": {
                "path": suggestions_path.name,
                "sha256": _sha256_file(suggestions_path),
                "suggestions_sha256": suggestions.get("suggestions_sha256"),
            },
        },
        "counts": {
            "cases": len(cases),
            "decisions": sum(len(case["decisions"]) for case in cases),
            "actions": dict(sorted(counts.items())),
            "geometry_strategies": dict(sorted(geometry_counts.items())),
        },
        "cases": cases,
        "materialization_requirements": [
            "exact_source_boundary_rescan",
            *(
                [
                    "operator_confirmed_source_contact_sheet_hash",
                    "source_frame_and_geometry_template_binding",
                    "template_tracking_with_immediate_negative_evidence",
                ]
                if template_required
                else []
            ),
            "negative_evidence_outside_each_span",
            "operator_hash_match",
            "rerun_encoded_output_qa",
        ],
        "non_goals": [
            "do_not_overwrite_master_timeline",
            "do_not_relax_qa_thresholds",
            "do_not_write_approval_from_this_proposal",
        ],
    }
    token_seed = _sha256_json(payload)[:12].upper()
    payload["operator_approval_token"] = (
        "PHASE4_OUTPUT_RESIDUAL_DECISIONS_APPROVED_"
        f"{str(decision_version).strip().upper()}_{token_seed}"
    )
    payload["proposal_sha256"] = _sha256_json(payload)
    return payload


def _markdown(payload: Mapping[str, Any]) -> str:
    version = str(payload.get("decision_version") or "V22_8_1").replace("_", ".")
    lines = [
        f"# Phase 4 Output Residual Decision Proposal {version}",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Token: `{payload.get('operator_approval_token')}`",
        f"- Proposal SHA-256: `{payload.get('proposal_sha256')}`",
        f"- Decisions: `{dict(payload.get('counts') or {}).get('decisions')}`",
        "",
        "| Case | Cluster | Action | Geometry | Source | Vietnamese |",
        "|---|---|---|---|---|---|",
    ]
    for case in list(payload.get("cases") or []):
        for decision in list(dict(case).get("decisions") or []):
            lines.append(
                f"| `{case.get('case_id')}` | `{decision.get('cluster_id')}` | "
                f"`{decision.get('proposed_action')}` | "
                f"`{decision.get('geometry_strategy')}` | "
                f"{str(decision.get('source_text_suggested') or '').replace('|', '/')} | "
                f"{str(decision.get('vi_text_suggested') or '').replace('|', '/')} |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_phase4_output_residual_decision_proposal"
    )
    parser.add_argument("run_root")
    parser.add_argument(
        "--review-name", default="phase4_output_residual_review_v22_8.json"
    )
    parser.add_argument(
        "--approval-name",
        default="phase4_output_residual_review_approval_v22_8.json",
    )
    parser.add_argument(
        "--suggestions-name",
        default="phase4_output_residual_translation_suggestions_v22_8_1.json",
    )
    parser.add_argument("--decision-version", default="V22_8_1")
    parser.add_argument(
        "--output-stem",
        default="phase4_output_residual_decision_proposal_v22_8_1",
    )
    args = parser.parse_args()
    try:
        root = Path(args.run_root).resolve()
        payload = build_proposal(
            root,
            review_name=args.review_name,
            approval_name=args.approval_name,
            suggestions_name=args.suggestions_name,
            decision_version=args.decision_version,
        )
        stem = str(args.output_stem or "").strip()
        if not stem or Path(stem).name != stem:
            raise OutputResidualDecisionProposalError("Invalid output stem")
        json_path = root / f"{stem}.json"
        markdown_path = root / f"{stem}.md"
        temporary = json_path.with_suffix(json_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(json_path)
        markdown_path.write_text(_markdown(payload), encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, OutputResidualDecisionProposalError) as exc:
        print(f"[PHASE4-OUTPUT-RESIDUAL-DECISIONS][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": payload["status"],
                "counts": payload["counts"],
                "operator_approval_token": payload["operator_approval_token"],
                "proposal_sha256": payload["proposal_sha256"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
