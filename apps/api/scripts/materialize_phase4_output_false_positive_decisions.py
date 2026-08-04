"""Materialize approved V22.8.1 residual false-positive decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.media_pipeline.video_renderer.phase4_approvals import (
    Phase4ApprovalError,
    _sha256_json,
    load_residual_cjk_false_positive_approval,
    residual_detection_sha256,
)
from scripts.run_phase4_adaptive import _source_path


class OutputFalsePositiveMaterializationError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OutputFalsePositiveMaterializationError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise OutputFalsePositiveMaterializationError(
            f"{path.name} must contain an object"
        )
    return payload


def _verify_self(payload: Mapping[str, Any], key: str) -> None:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(key, "") or "")
    if len(claimed) != 64 or claimed != _sha256_json(unsigned):
        raise OutputFalsePositiveMaterializationError(f"Invalid self-hash: {key}")


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _copy_immutable(source: Path, target: Path) -> None:
    expected = _sha256_file(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        shutil.copy2(source, target)
    if _sha256_file(target) != expected:
        raise OutputFalsePositiveMaterializationError(
            "Immutable false-positive evidence hash mismatch"
        )


def materialize(
    *,
    run_root: str | Path,
    operator_id: str,
    materialized_at: str,
    proposal_name: str = "phase4_output_residual_decision_proposal_v22_8_1.json",
    approval_name: str = "phase4_output_residual_decision_approval_v22_8_1.json",
    review_name: str = "phase4_output_residual_review_v22_8.json",
    output_name: str = "phase4_output_false_positive_materialization_v22_8_1.json",
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    names = (proposal_name, approval_name, review_name, output_name)
    if any(
        not str(value).strip()
        or Path(str(value)).name != str(value)
        or not str(value).endswith(".json")
        for value in names
    ):
        raise OutputFalsePositiveMaterializationError("Invalid materialization filename")
    proposal_path = run / proposal_name
    approval_path = run / approval_name
    review_path = run / review_name
    proposal = _load(proposal_path)
    approval = _load(approval_path)
    review = _load(review_path)
    _verify_self(proposal, "proposal_sha256")
    _verify_self(approval, "approval_sha256")
    _verify_self(review, "review_sha256")
    proposal_ref = dict(approval.get("proposal_ref") or {})
    if (
        str(approval.get("status") or "")
        != "PHASE4_OUTPUT_RESIDUAL_DECISIONS_APPROVED"
        or str(proposal_ref.get("sha256") or "") != _sha256_file(proposal_path)
        or str(proposal_ref.get("proposal_sha256") or "")
        != str(proposal.get("proposal_sha256") or "")
    ):
        raise OutputFalsePositiveMaterializationError(
            "Residual decision approval is stale"
        )
    operator = str(operator_id or "").strip()
    timestamp = str(materialized_at or "").strip()
    if not operator or not timestamp:
        raise OutputFalsePositiveMaterializationError(
            "operator_id and materialized_at are required"
        )
    review_cases = {
        str(row.get("case_id") or ""): dict(row)
        for raw in list(review.get("cases") or [])
        if isinstance(raw, Mapping)
        for row in (dict(raw),)
    }
    case_results: list[dict[str, Any]] = []
    new_count = 0
    cumulative_count = 0
    for raw_case in list(proposal.get("cases") or []):
        case = dict(raw_case)
        case_id = str(case.get("case_id") or "")
        decisions = [
            dict(row)
            for row in list(case.get("decisions") or [])
            if isinstance(row, Mapping)
            and str(dict(row).get("proposed_action") or "")
            == "APPROVE_RESIDUAL_FALSE_POSITIVE"
        ]
        if not decisions:
            continue
        case_root = (run / case_id).resolve()
        input_path = case_root / "phase4_render_input.json"
        output_qa_path = (
            case_root / "qa" / "phase4_adaptive_visual_preview_output_qa.json"
        )
        if not case_root.is_relative_to(run) or not input_path.is_file():
            raise OutputFalsePositiveMaterializationError(
                f"Case authority is missing: {case_id}"
            )
        authority_refs = dict(case.get("authority_refs") or {})
        for label in ("output_qa", "phase4_input"):
            ref = dict(authority_refs.get(label) or {})
            source = (case_root / str(ref.get("path") or "")).resolve()
            if (
                not source.is_relative_to(case_root)
                or not source.is_file()
                or _sha256_file(source) != str(ref.get("sha256") or "")
            ):
                raise OutputFalsePositiveMaterializationError(
                    f"{case_id} {label} authority changed"
                )
        source_ref = dict(authority_refs.get("source_video") or {})
        source_video = _source_path(case_root)
        if (
            source_video.name != str(source_ref.get("path") or "")
            or _sha256_file(source_video) != str(source_ref.get("sha256") or "")
        ):
            raise OutputFalsePositiveMaterializationError(
                f"{case_id} source_video authority changed"
            )
        review_case = review_cases.get(case_id)
        if review_case is None:
            raise OutputFalsePositiveMaterializationError(
                f"Review case is missing: {case_id}"
            )
        clusters = {
            str(row.get("cluster_id") or ""): dict(row)
            for raw in list(review_case.get("clusters") or [])
            if isinstance(raw, Mapping)
            for row in (dict(raw),)
        }
        immutable_dir = case_root / "residual_cjk_false_positive_approvals"
        immutable_dir.mkdir(parents=True, exist_ok=True)
        output_qa_hash = _sha256_file(output_qa_path)
        immutable_qa = immutable_dir / f"output_qa_{output_qa_hash}.json"
        _copy_immutable(output_qa_path, immutable_qa)
        entries: list[dict[str, Any]] = []
        active_path = case_root / "phase4_residual_cjk_false_positive_approval.json"
        if active_path.is_file():
            contract = _load(input_path)
            try:
                prior = load_residual_cjk_false_positive_approval(
                    root_dir=case_root, contract=contract
                )
            except Phase4ApprovalError as exc:
                raise OutputFalsePositiveMaterializationError(str(exc)) from exc
            if prior is not None:
                prior_rows = (
                    list(prior.get("approvals") or [])
                    if str(prior.get("schema_version") or "").endswith("_v2")
                    else [prior]
                )
                for index, raw in enumerate(prior_rows, start=1):
                    row = dict(raw)
                    source_evidence = (
                        case_root / str(dict(row.get("evidence_ref") or {}).get("path") or "")
                    ).resolve()
                    evidence_hash = _sha256_file(source_evidence)
                    target_evidence = immutable_dir / f"evidence_{evidence_hash}.jpg"
                    _copy_immutable(source_evidence, target_evidence)
                    legacy: dict[str, Any] = {
                        "cluster_id": str(row.get("cluster_id") or f"legacy_v1_{index:03d}"),
                        "origin": "CUMULATIVE_PRIOR_APPROVAL",
                        "detection": dict(row.get("detection") or {}),
                        "detection_sha256": str(row.get("detection_sha256") or ""),
                        "cluster_detection_sha256s": list(
                            row.get("cluster_detection_sha256s")
                            or [str(row.get("detection_sha256") or "")]
                        ),
                        "evidence_ref": {
                            "path": target_evidence.relative_to(case_root).as_posix(),
                            "sha256": evidence_hash,
                        },
                        "prior_approval_sha256": prior.get("approval_sha256"),
                    }
                    legacy["entry_sha256"] = _sha256_json(legacy)
                    entries.append(legacy)
        for decision in decisions:
            cluster_id = str(decision.get("cluster_id") or "")
            cluster = clusters.get(cluster_id)
            if cluster is None:
                raise OutputFalsePositiveMaterializationError(
                    f"Approved cluster is missing: {cluster_id}"
                )
            detections = [
                dict(row)
                for row in list(cluster.get("detections") or [])
                if isinstance(row, Mapping)
            ]
            if not detections:
                raise OutputFalsePositiveMaterializationError(
                    f"Approved cluster is empty: {cluster_id}"
                )
            representative = max(
                detections, key=lambda row: float(row.get("confidence") or 0.0)
            )
            evidence = dict(
                dict(cluster.get("evidence") or {}).get("source_render_contact_sheet")
                or {}
            )
            source_evidence = (case_root / str(evidence.get("path") or "")).resolve()
            if (
                not source_evidence.is_relative_to(case_root)
                or not source_evidence.is_file()
                or _sha256_file(source_evidence) != str(evidence.get("sha256") or "")
            ):
                raise OutputFalsePositiveMaterializationError(
                    f"Approved evidence changed: {cluster_id}"
                )
            evidence_hash = _sha256_file(source_evidence)
            immutable_evidence = immutable_dir / f"evidence_{evidence_hash}.jpg"
            _copy_immutable(source_evidence, immutable_evidence)
            decision_hash = _sha256_json(decision)
            entry = {
                "cluster_id": cluster_id,
                "origin": "V22_8_1_OPERATOR_DECISION",
                "detection": representative,
                "detection_sha256": residual_detection_sha256(representative),
                "cluster_detection_sha256s": sorted(
                    residual_detection_sha256(row) for row in detections
                ),
                "evidence_ref": {
                    "path": immutable_evidence.relative_to(case_root).as_posix(),
                    "sha256": evidence_hash,
                },
                "decision_sha256": decision_hash,
            }
            entry["entry_sha256"] = _sha256_json(entry)
            entries = [
                row for row in entries if str(row.get("cluster_id") or "") != cluster_id
            ]
            entries.append(entry)
            new_count += 1
        source_sha = str(
            dict(authority_refs.get("source_video") or {}).get("sha256") or ""
        )
        binding = {
            "source_video_sha256": source_sha,
            "phase4_input_sha256": _sha256_file(input_path),
            "output_qa_sha256": output_qa_hash,
            "decision_approval_sha256": approval.get("approval_sha256"),
            "proposal_sha256": proposal.get("proposal_sha256"),
            "review_sha256": review.get("review_sha256"),
        }
        bundle: dict[str, Any] = {
            "schema_version": "phase4_residual_cjk_false_positive_approval_v2",
            "status": "OCR_FALSE_POSITIVES_CONFIRMED",
            "approved_at": timestamp,
            "operator_id": operator,
            "approval_token": approval.get("approval_token"),
            "authority_refs": {
                "phase4_input": {
                    "path": input_path.name,
                    "sha256": _sha256_file(input_path),
                },
                "immutable_output_qa": {
                    "path": immutable_qa.relative_to(case_root).as_posix(),
                    "sha256": output_qa_hash,
                },
                "decision_approval": {
                    "path": f"../{approval_path.name}",
                    "sha256": _sha256_file(approval_path),
                },
                "decision_proposal": {
                    "path": f"../{proposal_path.name}",
                    "sha256": _sha256_file(proposal_path),
                },
                "residual_review": {
                    "path": f"../{review_path.name}",
                    "sha256": _sha256_file(review_path),
                },
            },
            "binding": binding,
            "binding_sha256": _sha256_json(binding),
            "approvals": sorted(entries, key=lambda row: str(row.get("cluster_id") or "")),
        }
        bundle["approval_sha256"] = _sha256_json(bundle)
        versioned = immutable_dir / f"approval_bundle_{bundle['approval_sha256']}.json"
        _write(versioned, bundle)
        _write(active_path, bundle)
        cumulative_count += len(entries)
        case_results.append(
            {
                "case_id": case_id,
                "new_false_positive_decisions": len(decisions),
                "cumulative_approvals": len(entries),
                "approval_ref": {
                    "path": active_path.relative_to(run).as_posix(),
                    "sha256": _sha256_file(active_path),
                    "approval_sha256": bundle["approval_sha256"],
                },
            }
        )
    expected_new = int(
        dict(dict(proposal.get("counts") or {}).get("actions") or {}).get(
            "APPROVE_RESIDUAL_FALSE_POSITIVE"
        )
        or 0
    )
    if new_count != expected_new:
        raise OutputFalsePositiveMaterializationError(
            f"Materialized {new_count} false positives; expected {expected_new}"
        )
    index: dict[str, Any] = {
        "schema_version": "phase4_output_false_positive_materialization_v1",
        "status": "PHASE4_OUTPUT_FALSE_POSITIVES_MATERIALIZED",
        "created_at": timestamp,
        "operator_id": operator,
        "decision_approval_ref": {
            "path": approval_path.name,
            "sha256": _sha256_file(approval_path),
            "approval_sha256": approval.get("approval_sha256"),
        },
        "counts": {
            "cases": len(case_results),
            "new_false_positive_decisions": new_count,
            "cumulative_approvals": cumulative_count,
        },
        "cases": case_results,
    }
    index["materialization_sha256"] = _sha256_json(index)
    _write(run / output_name, index)
    return index


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.materialize_phase4_output_false_positive_decisions"
    )
    parser.add_argument("run_root")
    parser.add_argument("--operator-id", default="operator-user-approved")
    parser.add_argument("--materialized-at")
    parser.add_argument(
        "--proposal-name",
        default="phase4_output_residual_decision_proposal_v22_8_1.json",
    )
    parser.add_argument(
        "--approval-name",
        default="phase4_output_residual_decision_approval_v22_8_1.json",
    )
    parser.add_argument(
        "--review-name", default="phase4_output_residual_review_v22_8.json"
    )
    parser.add_argument(
        "--output-name",
        default="phase4_output_false_positive_materialization_v22_8_1.json",
    )
    args = parser.parse_args()
    try:
        result = materialize(
            run_root=args.run_root,
            operator_id=args.operator_id,
            materialized_at=args.materialized_at
            or datetime.now(timezone.utc).isoformat(),
            proposal_name=args.proposal_name,
            approval_name=args.approval_name,
            review_name=args.review_name,
            output_name=args.output_name,
        )
    except (OSError, ValueError, OutputFalsePositiveMaterializationError) as exc:
        print(f"[PHASE4-OUTPUT-FALSE-POSITIVE][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {"status": result["status"], "counts": result["counts"]},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
