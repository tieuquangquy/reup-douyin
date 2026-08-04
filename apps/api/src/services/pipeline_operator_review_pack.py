"""Build a hash-bound, read-only operator review pack for regression gates."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.media_pipeline.frame_sampling.phase1_no_text_contract import (
    evaluate_no_text_operator_gate,
)
from src.media_pipeline.frame_sampling.phase1_geometry_review import (
    evaluate_phase1_geometry_operator_gate_safe,
)


class PipelineOperatorReviewPackError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineOperatorReviewPackError(
            f"Cannot read valid review evidence: {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise PipelineOperatorReviewPackError(f"{path.name} must contain an object")
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


def _verify_self_hash(payload: Mapping[str, Any], field: str) -> bool:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    return len(claimed) == 64 and claimed == _sha256_json(unsigned)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _write_text_atomic(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _workspace_path(workspace: Path, raw: str, *, label: str) -> Path:
    path = (workspace / raw).resolve()
    if not path.is_relative_to(workspace) or not path.is_file():
        raise PipelineOperatorReviewPackError(f"Invalid {label}")
    return path


def _workspace_relative(workspace: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(workspace).as_posix()
    except ValueError as exc:
        raise PipelineOperatorReviewPackError("Review evidence escaped workspace") from exc


def _markdown_link(run: Path, workspace: Path, workspace_relative: str) -> str:
    target = workspace / workspace_relative
    return Path(os.path.relpath(target, run)).as_posix()


def _asset_rows(
    artifact_root: Path,
    workspace: Path,
    review_assets: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in review_assets:
        text_id = str(raw.get("text_id") or "")
        assets: dict[str, str] = {}
        for key in (
            "crop_path",
            "best_keyframe_path",
            "overlay_path",
            "boundary_path",
        ):
            value = str(raw.get(key) or "").strip()
            if not value:
                continue
            candidate = (artifact_root / value).resolve()
            if candidate.is_relative_to(artifact_root) and candidate.is_file():
                assets[key] = _workspace_relative(workspace, candidate)
        if not any(key in assets for key in ("crop_path", "best_keyframe_path")):
            raise PipelineOperatorReviewPackError(
                f"Missing visual OCR evidence for {text_id or 'unknown track'}"
            )
        ocr_inputs = sorted((artifact_root / "qa" / "ocr_inputs").glob(f"{text_id}_*.jpg"))
        rows.append(
            {
                "text_id": text_id,
                "start_frame": raw.get("start_frame"),
                "end_frame": raw.get("end_frame"),
                "assets": assets,
                "ocr_inputs": [
                    _workspace_relative(workspace, item) for item in ocr_inputs
                ],
            }
        )
    return rows


def _render_markdown(pack: Mapping[str, Any], *, run: Path, workspace: Path) -> str:
    lines = [
        "# Pipeline Operator Review Pack",
        "",
        f"- Status: `{pack['status']}`",
        f"- Selected cases: `{pack['counts']['selected_cases']}`",
        f"- NO_TEXT full-video decisions: `{pack['counts']['no_text_reviews']}`",
        f"- Phase 1 geometry issues: `{pack['counts']['phase1_geometry_issues']}`",
        f"- Exact OCR objects: `{pack['counts']['ocr_objects']}`",
        f"- Pack SHA-256: `{pack['review_pack_sha256']}`",
        "",
    ]
    if pack["status"] == "NO_OPERATOR_REVIEW_REQUIRED":
        lines.extend(
            [
                "No case is currently waiting at a supported operator review gate.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Automation has not written any operator decision. Review the complete source video for NO_TEXT and the linked visual evidence for every OCR object.",
                "",
            ]
        )
    for case in list(pack.get("cases") or []):
        case_id = str(case.get("case_id") or "")
        review_type = str(case.get("review_type") or "")
        lines.extend([f"## {case_id}", "", f"Review type: `{review_type}`", ""])
        if review_type == "PHASE1_NO_TEXT":
            source = dict(case.get("source_video") or {})
            source_link = _markdown_link(run, workspace, str(source["path"]))
            lines.extend(
                [
                    f"- [Open and watch the complete source video]({source_link})",
                    f"- Duration: `{source.get('duration_seconds')} s`",
                    f"- Source SHA-256: `{source.get('sha256')}`",
                    f"- Review SHA-256: `{case.get('review_sha256')}`",
                    "- Allowed decisions: `NO_TEXT_CONFIRMED` or `TEXT_PRESENT_REJECTED`.",
                    "",
                    "Do not decide from detector counts or contact sheets alone.",
                    "",
                ]
            )
            contact_sheet = case.get("contact_sheet")
            if isinstance(contact_sheet, Mapping):
                contact_link = _markdown_link(
                    run, workspace, str(contact_sheet["path"])
                )
                lines.extend(
                    [
                        f"- [Open sampled contact sheet]({contact_link})",
                        f"- Contact-sheet SHA-256: `{contact_sheet.get('sha256')}`",
                        "",
                    ]
                )
            continue
        if review_type == "PHASE1_GEOMETRY":
            source = dict(case.get("source_video") or {})
            source_link = _markdown_link(run, workspace, str(source["path"]))
            lines.extend(
                [
                    f"- [Open and watch the complete source video]({source_link})",
                    f"- Source SHA-256: `{source.get('sha256')}`",
                    f"- Review SHA-256: `{case.get('review_sha256')}`",
                    "- Allowed decisions: `APPROVE_GEOMETRY`, `EDIT_GEOMETRY`, `REJECT_TRACK`, `EXPLAIN_SHADOW`.",
                    "- This checkpoint does not approve OCR text.",
                    "",
                ]
            )
            for issue in list(case.get("issues") or []):
                lines.extend(
                    [
                        f"### {issue.get('issue_id')}",
                        "",
                        f"- Type: `{issue.get('issue_type')}`",
                        f"- Track: `{issue.get('text_id') or '-'}`",
                        f"- Span: `{issue.get('span') or '-'}`",
                        f"- Reasons: `{', '.join(str(value) for value in issue.get('reasons') or [])}`",
                    ]
                )
                links: list[str] = []
                for asset in list(issue.get("review_assets") or []):
                    for label, raw_ref in dict(asset.get("assets") or {}).items():
                        ref = dict(raw_ref or {})
                        target = _markdown_link(run, workspace, str(ref.get("path") or ""))
                        links.append(f"[{label}]({target})")
                if links:
                    lines.append("- Evidence: " + " · ".join(links))
                lines.append("")
            continue
        approval_path = str(case.get("approval_path") or "")
        approval_link = _markdown_link(run, workspace, approval_path)
        lines.extend(
            [
                f"Edit decisions only in [phase2_approvals.json]({approval_link}), then rerun Phase 2 to validate freshness.",
                "Allowed decisions: `APPROVE`, `EDIT`, `ACCEPT_LLM`, `PRESERVE_SOURCE` (`REJECT_UI` is legacy).",
                "",
            ]
        )
        proposal_ref = case.get("proposal_ref")
        if isinstance(proposal_ref, Mapping):
            proposal_link = _markdown_link(
                run, workspace, str(proposal_ref["path"])
            )
            lines.extend(
                [
                    f"Review the hash-bound [OCR proposal]({proposal_link}).",
                    f"Proposal SHA-256: `{proposal_ref.get('proposal_sha256')}`",
                    "",
                ]
            )
        for item in list(case.get("content_objects") or []):
            lines.extend(
                [
                    f"### {item.get('content_id')}",
                    "",
                    f"- OCR candidate: `{json.dumps(str(item.get('ocr_text_candidate') or ''), ensure_ascii=False)}`",
                    f"- LLM suggestion: `{json.dumps(str(item.get('ocr_text_llm_suggested') or ''), ensure_ascii=False)}`",
                    f"- Review proposal: `{json.dumps(str(item.get('ocr_text_suggested') or ''), ensure_ascii=False)}`",
                    f"- Proposed decision: `{item.get('proposed_decision')}`",
                    f"- Roles: `{', '.join(str(value) for value in item.get('roles') or [])}`",
                    f"- Geometry refs: `{', '.join(str(value) for value in item.get('geometry_refs') or [])}`",
                    f"- Review-input SHA-256: `{item.get('review_input_sha256')}`",
                    "",
                ]
            )
            for asset in list(item.get("review_assets") or []):
                links: list[str] = []
                for label, raw_path in dict(asset.get("assets") or {}).items():
                    target = _markdown_link(run, workspace, str(raw_path))
                    links.append(f"[{label}]({target})")
                for index, raw_path in enumerate(list(asset.get("ocr_inputs") or []), 1):
                    target = _markdown_link(run, workspace, str(raw_path))
                    links.append(f"[ocr_input_{index}]({target})")
                lines.append(
                    f"- `{asset.get('text_id')}` frames `{asset.get('start_frame')}-{asset.get('end_frame')}`: "
                    + " · ".join(links)
                )
            lines.append("")
        merge_groups = list(case.get("transition_merge_groups") or [])
        if merge_groups:
            lines.extend(["### Transition merge after approval", ""])
            for group in merge_groups:
                lines.append(
                    "- "
                    + ", ".join(str(value) for value in group.get("source_content_ids") or [])
                    + " -> "
                    + str(group.get("canonical_content_id") or "")
                    + f"; text `{group.get('ocr_text_suggested')}`; geometries "
                    + ", ".join(str(value) for value in group.get("geometry_refs") or [])
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_operator_review_pack(
    *,
    run_root: str | Path,
    workspace_root: str | Path,
    selected_case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    run = Path(run_root).resolve()
    workspace = Path(workspace_root).resolve()
    state_path = run / "batch_regression_state.json"
    state = _load_object(state_path)
    corpus_ref = dict(state.get("corpus_ref") or {})
    corpus_path = _workspace_path(
        workspace, str(corpus_ref.get("path") or ""), label="corpus reference"
    )
    corpus = _load_object(corpus_path)
    corpus_cases = {
        str(item.get("case_id") or ""): dict(item)
        for item in list(corpus.get("cases") or [])
        if isinstance(item, Mapping)
    }
    selected = {str(value) for value in selected_case_ids or [] if str(value)}
    cases: list[dict[str, Any]] = []
    no_text_reviews = 0
    phase1_geometry_issues = 0
    ocr_objects = 0
    for raw_case in list(state.get("cases") or []):
        if not isinstance(raw_case, Mapping):
            continue
        case = dict(raw_case)
        case_id = str(case.get("case_id") or "")
        if selected and case_id not in selected:
            continue
        status = str(case.get("status") or "")
        artifact_raw = (workspace / str(case.get("artifact_root") or "")).resolve()
        if not artifact_raw.is_relative_to(workspace) or not artifact_raw.is_dir():
            raise PipelineOperatorReviewPackError(f"Invalid artifact root for {case_id}")
        artifact_root = artifact_raw
        if status == "WAITING_NO_TEXT_OPERATOR_REVIEW":
            gate = evaluate_no_text_operator_gate(artifact_root)
            candidate = _load_object(artifact_root / "phase1_no_text_review.json")
            corpus_case = corpus_cases.get(case_id) or {}
            source_path = _workspace_path(
                workspace,
                str(corpus_case.get("video_path") or ""),
                label=f"source video for {case_id}",
            )
            source_ref = dict(candidate.get("source_video") or {})
            source_sha = _sha256_file(source_path)
            if source_sha != str(source_ref.get("sha256") or ""):
                raise PipelineOperatorReviewPackError(
                    f"Source video changed after NO_TEXT candidate: {case_id}"
                )
            no_text_case: dict[str, Any] = {
                    "case_id": case_id,
                    "review_type": "PHASE1_NO_TEXT",
                    "status": gate["status"],
                    "artifact_root": _workspace_relative(workspace, artifact_root),
                    "review_sha256": gate["review_sha256"],
                    "source_video": {
                        "path": _workspace_relative(workspace, source_path),
                        "sha256": source_sha,
                        "size_bytes": source_path.stat().st_size,
                        "duration_seconds": dict(corpus_case.get("probe") or {}).get(
                            "duration_seconds"
                        ),
                    },
                    "decision_options": [
                        "NO_TEXT_CONFIRMED",
                        "TEXT_PRESENT_REJECTED",
                    ],
                }
            contact_sheet = artifact_root / "qa" / "no_text_review_contact_sheet.jpg"
            if contact_sheet.is_file():
                no_text_case["contact_sheet"] = {
                    "path": _workspace_relative(workspace, contact_sheet),
                    "sha256": _sha256_file(contact_sheet),
                    "scope": "SAMPLED_REVIEW_AID_NOT_FULL_VIDEO_AUTHORITY",
                }
            cases.append(no_text_case)
            no_text_reviews += 1
            continue
        if status == "WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW":
            gate = evaluate_phase1_geometry_operator_gate_safe(artifact_root)
            candidate_path = artifact_root / "phase1_geometry_review.json"
            candidate = _load_object(candidate_path)
            corpus_case = corpus_cases.get(case_id) or {}
            source_path = _workspace_path(
                workspace,
                str(corpus_case.get("video_path") or ""),
                label=f"source video for {case_id}",
            )
            source_sha = _sha256_file(source_path)
            if source_sha != str(
                dict(candidate.get("source_video") or {}).get("sha256") or ""
            ):
                raise PipelineOperatorReviewPackError(
                    f"Source video changed after geometry candidate: {case_id}"
                )
            issues: list[dict[str, Any]] = []
            for raw_issue in list(candidate.get("issues") or []):
                if not isinstance(raw_issue, Mapping):
                    continue
                issue = dict(raw_issue)
                converted_assets: list[dict[str, Any]] = []
                for raw_asset in list(issue.get("review_assets") or []):
                    if not isinstance(raw_asset, Mapping):
                        continue
                    converted: dict[str, Any] = {
                        "text_id": raw_asset.get("text_id"),
                        "assets": {},
                    }
                    for label, raw_ref in dict(raw_asset.get("assets") or {}).items():
                        ref = dict(raw_ref or {})
                        asset = (artifact_root / str(ref.get("path") or "")).resolve()
                        if (
                            not asset.is_relative_to(artifact_root)
                            or not asset.is_file()
                            or _sha256_file(asset) != str(ref.get("sha256") or "")
                        ):
                            raise PipelineOperatorReviewPackError(
                                f"Geometry evidence drifted for {case_id}"
                            )
                        converted["assets"][label] = {
                            "path": _workspace_relative(workspace, asset),
                            "sha256": ref.get("sha256"),
                        }
                    converted_assets.append(converted)
                issue["review_assets"] = converted_assets
                issues.append(issue)
            geometry_case = {
                "case_id": case_id,
                "review_type": "PHASE1_GEOMETRY",
                "status": gate["status"],
                "artifact_root": _workspace_relative(workspace, artifact_root),
                "review_sha256": gate["review_sha256"],
                "review_ref": {
                    "path": _workspace_relative(workspace, candidate_path),
                    "sha256": _sha256_file(candidate_path),
                },
                "source_video": {
                    "path": _workspace_relative(workspace, source_path),
                    "sha256": source_sha,
                    "size_bytes": source_path.stat().st_size,
                    "duration_seconds": dict(corpus_case.get("probe") or {}).get(
                        "duration_seconds"
                    ),
                },
                "failed_geometry_checks": list(
                    candidate.get("failed_geometry_checks") or []
                ),
                "decision_options": list(candidate.get("allowed_decisions") or []),
                "issues": issues,
            }
            cases.append(geometry_case)
            phase1_geometry_issues += len(issues)
            continue
        if status == "WAITING_OCR_OPERATOR_REVIEW":
            queue_path = artifact_root / "phase2_review_queue.json"
            approvals_path = artifact_root / "phase2_approvals.json"
            queue = _load_object(queue_path)
            proposal_by_id: dict[str, dict[str, Any]] = {}
            transition_merge_groups: list[dict[str, Any]] = []
            proposal_ref: dict[str, Any] | None = None
            proposal_path = artifact_root / "phase2_review_proposal.json"
            if proposal_path.is_file():
                proposal = _load_object(proposal_path)
                if not _verify_self_hash(proposal, "proposal_sha256"):
                    raise PipelineOperatorReviewPackError(
                        f"OCR proposal self-hash is invalid for {case_id}"
                    )
                if str(
                    dict(proposal.get("review_queue_ref") or {}).get("sha256")
                    or ""
                ) != _sha256_file(queue_path):
                    raise PipelineOperatorReviewPackError(
                        f"OCR proposal is stale for {case_id}"
                    )
                proposal_by_id = {
                    str(row.get("content_id") or ""): dict(row)
                    for row in list(proposal.get("proposals") or [])
                    if isinstance(row, Mapping)
                }
                transition_merge_groups = [
                    dict(row)
                    for row in list(proposal.get("transition_merge_groups") or [])
                    if isinstance(row, Mapping)
                ]
                proposal_ref = {
                    "path": _workspace_relative(workspace, proposal_path),
                    "sha256": _sha256_file(proposal_path),
                    "proposal_sha256": proposal.get("proposal_sha256"),
                }
            objects: list[dict[str, Any]] = []
            for raw_object in list(queue.get("content_objects") or []):
                if not isinstance(raw_object, Mapping):
                    continue
                item = dict(raw_object)
                proposal_row = proposal_by_id.get(
                    str(item.get("content_id") or "")
                ) or {}
                review_hash = str(item.get("review_input_sha256") or "")
                if len(review_hash) != 64:
                    raise PipelineOperatorReviewPackError(
                        f"Missing OCR review hash for {case_id}"
                    )
                objects.append(
                    {
                        "content_id": item.get("content_id"),
                        "ocr_text_candidate": item.get("ocr_text_candidate"),
                        "ocr_text_llm_suggested": item.get(
                            "ocr_text_llm_suggested"
                        ),
                        "roles": list(item.get("roles") or []),
                        "geometry_refs": list(item.get("geometry_refs") or []),
                        "review_input_sha256": review_hash,
                        "ocr_text_suggested": proposal_row.get(
                            "ocr_text_suggested"
                        ),
                        "proposed_decision": proposal_row.get(
                            "proposed_decision"
                        ),
                        "proposal_status": proposal_row.get(
                            "proposal_status"
                        ),
                        "review_assets": _asset_rows(
                            artifact_root,
                            workspace,
                            list(item.get("review_assets") or []),
                        ),
                    }
                )
            expected = int(dict(queue.get("review_summary") or {}).get("unresolved") or 0)
            if expected != len(objects):
                raise PipelineOperatorReviewPackError(
                    f"OCR review queue count mismatch for {case_id}"
                )
            ocr_case: dict[str, Any] = {
                    "case_id": case_id,
                    "review_type": "PHASE2_EXACT_OCR",
                    "status": status,
                    "artifact_root": _workspace_relative(workspace, artifact_root),
                    "phase1_ref": queue.get("phase1_ref"),
                    "review_queue_sha256": _sha256_file(queue_path),
                    "approval_path": _workspace_relative(workspace, approvals_path),
                    "content_objects": objects,
                    "transition_merge_groups": transition_merge_groups,
                }
            if proposal_ref is not None:
                ocr_case["proposal_ref"] = proposal_ref
            cases.append(ocr_case)
            ocr_objects += len(objects)
    missing = selected - {str(case.get("case_id") or "") for case in cases}
    if missing:
        raise PipelineOperatorReviewPackError(
            "Selected cases are not waiting at a supported operator gate: "
            + ", ".join(sorted(missing))
        )
    pack: dict[str, Any] = {
        "schema_version": "pipeline_operator_review_pack_v1",
        "status": (
            "OPERATOR_REVIEW_REQUIRED"
            if cases
            else "NO_OPERATOR_REVIEW_REQUIRED"
        ),
        "run_ref": {
            "path": _workspace_relative(workspace, state_path),
            "sha256": _sha256_file(state_path),
            "run_sha256": state.get("run_sha256"),
        },
        "selection": sorted(selected) if selected else "ALL_WAITING_CASES",
        "counts": {
            "selected_cases": len(cases),
            "no_text_reviews": no_text_reviews,
            "phase1_geometry_issues": phase1_geometry_issues,
            "ocr_objects": ocr_objects,
        },
        "cases": cases,
    }
    pack["review_pack_sha256"] = _sha256_json(pack)
    json_path = run / "operator_review_pack.json"
    markdown_path = run / "OPERATOR_REVIEW_PACK.md"
    _write_json_atomic(json_path, pack)
    _write_text_atomic(
        markdown_path, _render_markdown(pack, run=run, workspace=workspace)
    )
    return pack
