"""Run Phase 3 visual-text localization from the Phase 2 handoff authority."""

from __future__ import annotations

import hashlib
import json
import logging
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.db.session import get_session_factory
from src.media_pipeline.translator.phase3_contract import (
    _review_input_sha256,
    translate_phase3_handoff,
    write_phase3_artifacts,
)
from src.media_pipeline.translator.resolve import resolve_translator_settings
from src.services.residual_remediation_authority import (
    ResidualRemediationAuthorityError,
    resolve_active_residual_remediation,
)

logger = logging.getLogger(__name__)


class Phase3RunnerError(RuntimeError):
    """Phase 3 cannot safely run against the supplied authority."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_json_atomic(path: Path, payload: Any) -> None:
    _write_text_atomic(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2),
    )


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_self_hash(payload: Mapping[str, Any], field: str) -> bool:
    unsigned = dict(payload)
    claimed = str(unsigned.pop(field, "") or "")
    return len(claimed) == 64 and claimed == _sha256_json(unsigned)


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase3RunnerError(f"Cannot read valid {label}") from exc
    if not isinstance(payload, Mapping):
        raise Phase3RunnerError(f"{label} must be a JSON object")
    return dict(payload)


def _load_approvals(
    path: Path, *, phase2_handoff_sha256: str
) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    payload = _load_json_object(path, label="phase3_approvals.json")
    authority = payload.get("phase2_handoff_ref")
    authority_hash = (
        str(authority.get("sha256") or "") if isinstance(authority, Mapping) else ""
    )
    if authority_hash != phase2_handoff_sha256:
        raise Phase3RunnerError(
            "phase3_approvals.json references a stale Phase 2 handoff"
        )

    approvals: dict[str, dict[str, Any]] = {}
    rows = payload.get("approvals")
    if not isinstance(rows, list):
        raise Phase3RunnerError("phase3_approvals.json approvals must be a list")
    for row in rows:
        if not isinstance(row, Mapping):
            raise Phase3RunnerError("phase3_approvals.json contains an invalid row")
        content_id = str(row.get("content_id") or "").strip()
        if not content_id or content_id in approvals:
            raise Phase3RunnerError(
                "phase3_approvals.json contains a missing or duplicate content_id"
            )
        approvals[content_id] = dict(row)
    return approvals


def _load_approved_review_fossils(
    root: Path,
    *,
    phase2_handoff_sha256: str,
    approvals: Mapping[str, Mapping[str, Any]],
    skip_content_ids: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    decided_ids = {
        content_id
        for content_id, row in approvals.items()
        if str(row.get("decision") or "").strip().upper()
        in {"APPROVE", "EDIT"}
    } - set(skip_content_ids or set())
    if not decided_ids:
        return {}
    audit_path = root / "phase3_operator_approval_audit.json"
    audit = _load_json_object(
        audit_path, label="phase3_operator_approval_audit.json"
    )
    if not _verify_self_hash(audit, "audit_sha256"):
        raise Phase3RunnerError("Phase 3 operator approval audit hash is invalid")
    proposal_ref = dict(audit.get("proposal_ref") or {})
    proposal_path = (root / str(proposal_ref.get("path") or "")).resolve()
    if (
        not proposal_path.is_relative_to(root)
        or not proposal_path.is_file()
        or str(proposal_ref.get("sha256") or "") != _sha256_file(proposal_path)
    ):
        raise Phase3RunnerError("Approved Phase 3 proposal is stale")
    proposal = _load_json_object(
        proposal_path, label="phase3_review_proposal.json"
    )
    if (
        not _verify_self_hash(proposal, "proposal_sha256")
        or str(proposal.get("proposal_sha256") or "")
        != str(proposal_ref.get("proposal_sha256") or "")
        or str(dict(proposal.get("phase2_handoff_ref") or {}).get("sha256") or "")
        != phase2_handoff_sha256
    ):
        raise Phase3RunnerError("Approved Phase 3 proposal authority is invalid")
    proposal_rows = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(proposal.get("proposals") or [])
        if isinstance(row, Mapping)
    }
    if not decided_ids.issubset(proposal_rows):
        raise Phase3RunnerError(
            "Approved Phase 3 proposal does not cover every decision"
        )
    fossils: dict[str, dict[str, Any]] = {}
    for content_id in decided_ids:
        proposal_row = proposal_rows[content_id]
        approval = dict(approvals[content_id])
        review_hash = str(proposal_row.get("review_input_sha256") or "")
        if review_hash != str(approval.get("review_input_sha256") or ""):
            raise Phase3RunnerError(
                "Phase 3 approval no longer matches its proposal fossil"
            )
        fossils[content_id] = {
            "vi_text_candidate": proposal_row.get("vi_text_candidate"),
            "quality_flags": list(
                proposal_row.get("candidate_quality_flags") or []
            ),
            "review_input_sha256": review_hash,
        }
    return fossils


def _load_remediation_review_fossils(
    root: Path,
    *,
    handoff: Mapping[str, Any],
    phase2_handoff_sha256: str,
) -> dict[str, dict[str, Any]]:
    """Freeze operator-approved candidates across additive OCR remediation."""

    try:
        remediation_path = resolve_active_residual_remediation(root)
    except ResidualRemediationAuthorityError as exc:
        raise Phase3RunnerError(str(exc)) from exc
    if remediation_path is None:
        return {}
    from scripts.materialize_phase2_residual_remediation import verify_remediation

    remediation = _load_json_object(
        remediation_path, label=remediation_path.name
    )
    if not verify_remediation(remediation):
        raise Phase3RunnerError("Residual remediation self-hash is invalid")
    carry_rows = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(
            dict(remediation.get("translation_carry_forward") or {}).get("rows")
            or []
        )
        if isinstance(row, Mapping) and str(row.get("content_id") or "")
    }
    additive_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    additive_groups_by_geometry: dict[str, set[tuple[str, str]]] = {}
    approved_localization_rows = [
        (raw, False) for raw in list(remediation.get("approved_occurrences") or [])
    ] + [
        (raw, True)
        for raw in list(remediation.get("approved_geometry_overrides") or [])
    ]
    for raw, requires_operator_review in approved_localization_rows:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        if str(dict(row.get("localization") or {}).get("mode") or "") == "deterministic":
            continue
        key = (
            str(row.get("ocr_text_approved") or ""),
            str(row.get("vi_text_approved") or ""),
        )
        if not all(key):
            raise Phase3RunnerError(
                "Residual remediation translation fossil is incomplete"
            )
        operator_review = dict(row.get("operator_review") or {})
        if requires_operator_review and str(operator_review.get("decision") or "") not in {"APPROVE", "EDIT"}:
            raise Phase3RunnerError(
                "Residual remediation translation fossil is not operator-approved"
            )
        additive_groups.setdefault(key, []).append(row)
        raw_geometry = (
            row.get("geometry_override")
            if requires_operator_review
            else row.get("occurrence")
        )
        geometry = dict(raw_geometry or {})
        text_id = str(
            geometry.get("target_text_id")
            if requires_operator_review
            else geometry.get("text_id")
            or ""
        )
        if text_id:
            additive_groups_by_geometry.setdefault(text_id, set()).add(key)

    fossils: dict[str, dict[str, Any]] = {}
    matched_additive: set[tuple[str, str]] = set()
    # A residual occurrence can be the exact geometry of an approved dialogue
    # hard-sub. In that case Phase 2 intentionally routes it to deterministic
    # semantic-dialogue rendering rather than the visual translation queue.
    # Treat the DB-approved dialogue translation as the stronger authority and
    # do not require a second, conflicting Phase-3 visual approval.
    for raw in list(handoff.get("deterministic_items") or []):
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        semantic = dict(item.get("semantic_hardsub") or {})
        translation = dict(semantic.get("translation_authority") or {})
        if (
            str(semantic.get("classification") or "") != "DIALOGUE_HARDSUB"
            or not bool(semantic.get("translation_ready"))
            or not str(semantic.get("vi_text_authority") or "").strip()
            or str(translation.get("translation_status") or "").upper()
            != "APPROVED"
        ):
            continue
        for geometry_ref in list(item.get("geometry_refs") or []):
            matched_additive.update(
                additive_groups_by_geometry.get(str(geometry_ref), set())
            )
    translate_items = [
        dict(row)
        for row in list(handoff.get("translate_items") or [])
        if isinstance(row, Mapping)
    ]
    for item in translate_items:
        content_id = str(item.get("content_id") or "")
        zh_approved = str(item.get("zh_approved") or "")
        carry = carry_rows.get(content_id)
        if carry is not None and str(carry.get("zh_approved") or "") != zh_approved:
            shifted_matches = [
                dict(row)
                for row in carry_rows.values()
                if str(row.get("zh_approved") or "") == zh_approved
                and str(row.get("vi_text_candidate") or "").strip()
            ]
            shifted_vi = {
                str(row.get("vi_text_candidate") or "").strip()
                for row in shifted_matches
            }
            # Additive Phase 2 occurrences can renumber projection ids.
            # Rebind only through the exact approved Chinese fossil and a
            # single unambiguous Vietnamese candidate. A newly added object
            # may reuse an old projection id, in which case its explicit
            # additive fossil below is the authority.
            carry = shifted_matches[0] if shifted_matches and len(shifted_vi) == 1 else None
        if carry is not None:
            candidate = str(carry.get("vi_text_candidate") or "").strip()
            reused_matches = [
                key
                for key in additive_groups
                if key[0] == zh_approved
                and key[1] == str(carry.get("vi_text_approved") or "")
            ]
            if len(reused_matches) > 1:
                raise Phase3RunnerError(
                    f"Ambiguous reused remediation translation for {content_id}"
                )
            matched_additive.update(reused_matches)
        else:
            matches = [
                key for key in additive_groups if key[0] == zh_approved
            ]
            if len(matches) != 1:
                detail = (
                    "content drift detected"
                    if content_id in carry_rows
                    else "translation fossil is missing"
                )
                raise Phase3RunnerError(
                    f"Remediation {detail} for {content_id}"
                )
            key = matches[0]
            matched_additive.add(key)
            candidate = key[1]
        if not candidate:
            raise Phase3RunnerError(
                f"Remediation translation candidate is empty for {content_id}"
            )
        fossil_row = {
            "content_id": content_id,
            "geometry_refs": list(item.get("geometry_refs") or []),
            "roles": list(item.get("roles") or []),
            "zh_approved": item.get("zh_approved"),
            "translation_input": item.get("translation_input"),
            "protected_values": list(item.get("protected_values") or []),
            "unit_tokens": list(item.get("unit_tokens") or []),
            "vi_text_candidate": candidate,
            "quality_flags": [],
        }
        fossils[content_id] = {
            "vi_text_candidate": candidate,
            "quality_flags": [],
            "review_input_sha256": _review_input_sha256(
                fossil_row,
                phase2_handoff_sha256=phase2_handoff_sha256,
            ),
            "source": "phase2_residual_remediation_translation_carry",
        }
    if set(additive_groups) - matched_additive:
        unresolved = sorted(key[0] for key in set(additive_groups) - matched_additive)
        raise Phase3RunnerError(
            f"Approved additive translation is missing from Phase 2 handoff: {unresolved}"
        )
    return fossils


def lock_current_candidates(
    root_dir: str | Path,
    *,
    reviewer: str,
    reviewed_at: str | None = None,
) -> int:
    """Record an explicit operator lock without translating or editing candidates."""
    root = Path(root_dir).resolve()
    reviewer_name = str(reviewer or "").strip()
    if not reviewer_name:
        raise Phase3RunnerError("Reviewer is required to lock Phase 3 candidates")
    handoff_path = root / "phase2_handoff.json"
    timeline_path = root / "phase3_translation_timeline.json"
    approvals_path = root / "phase3_approvals.json"
    for path in (handoff_path, timeline_path, approvals_path):
        if not path.is_file():
            raise Phase3RunnerError(f"Missing required Phase 3 artifact: {path.name}")

    handoff_hash = _sha256_file(handoff_path)
    timeline = _load_json_object(
        timeline_path, label="phase3_translation_timeline.json"
    )
    timeline_ref = timeline.get("phase2_handoff_ref")
    timeline_hash = (
        str(timeline_ref.get("sha256") or "")
        if isinstance(timeline_ref, Mapping)
        else ""
    )
    if timeline_hash != handoff_hash:
        raise Phase3RunnerError(
            "phase3_translation_timeline.json references a stale Phase 2 handoff"
        )

    approvals_payload = _load_json_object(
        approvals_path, label="phase3_approvals.json"
    )
    approval_map = _load_approvals(
        approvals_path,
        phase2_handoff_sha256=handoff_hash,
    )
    candidates: dict[str, dict[str, Any]] = {}
    for raw in list(timeline.get("content_objects") or []):
        if not isinstance(raw, Mapping) or not bool(raw.get("review_required")):
            continue
        row = dict(raw)
        content_id = str(row.get("content_id") or "").strip()
        candidate = str(row.get("vi_text_candidate") or "").strip()
        review_hash = str(row.get("review_input_sha256") or "").strip()
        if not content_id or not candidate or not review_hash:
            raise Phase3RunnerError(
                "Phase 3 timeline contains a candidate that cannot be locked"
            )
        candidates[content_id] = row
    if not candidates or set(candidates) != set(approval_map):
        raise Phase3RunnerError(
            "Phase 3 candidate and approval content_id sets do not match"
        )

    timestamp = reviewed_at or datetime.now(timezone.utc).isoformat()
    output_rows: list[dict[str, Any]] = []
    locked = 0
    for raw in list(approvals_payload.get("approvals") or []):
        assert isinstance(raw, Mapping)
        approval = dict(raw)
        content_id = str(approval.get("content_id") or "")
        candidate_row = candidates[content_id]
        expected_text = str(candidate_row.get("vi_text_candidate") or "").strip()
        expected_hash = str(candidate_row.get("review_input_sha256") or "")
        if (
            str(approval.get("vi_text_approved") or "").strip() != expected_text
            or str(approval.get("review_input_sha256") or "") != expected_hash
        ):
            raise Phase3RunnerError(
                "Phase 3 approval candidate/hash drift detected; lock aborted"
            )
        decision = str(approval.get("decision") or "").strip().upper()
        if decision not in {"", "APPROVE"}:
            raise Phase3RunnerError(
                "Existing EDIT/REJECT decision must be resolved before batch lock"
            )
        if not decision:
            approval["decision"] = "APPROVE"
            approval["reviewer"] = reviewer_name
            approval["reviewed_at"] = timestamp
            locked += 1
        output_rows.append(approval)
    approvals_payload["approvals"] = output_rows
    _write_json_atomic(approvals_path, approvals_payload)
    return locked


def _review_report(contract: Mapping[str, Any]) -> str:
    summary = dict(contract.get("review_summary") or {})
    lines = [
        "# Phase 3 Translation Review",
        "",
        f"- Trạng thái: `{summary.get('status') or 'UNKNOWN'}`",
        f"- Tổng content: {summary.get('content_objects', 0)}",
        f"- Chờ operator review: {summary.get('unresolved', 0)}",
        f"- Dịch lỗi: {summary.get('failed', 0)}",
        "",
        "| content_id | Vai trò | Tiếng Trung | Tiếng Việt đề xuất | Trạng thái / cảnh báo |",
        "|---|---|---|---|---|",
    ]
    for row in list(contract.get("content_objects") or []):
        if not isinstance(row, Mapping):
            continue
        def cell(value: Any) -> str:
            return str(value or "").replace("|", "\\|").replace("\n", " ")

        roles = ", ".join(str(role) for role in list(row.get("roles") or []))
        candidate = row.get("vi_text_candidate") or ""
        flags = ", ".join(str(flag) for flag in list(row.get("quality_flags") or []))
        status = str(row.get("review_status") or "")
        status_and_flags = status if not flags else f"{status}; {flags}"
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    row.get("content_id"),
                    roles,
                    row.get("zh_approved"),
                    candidate,
                    status_and_flags,
                )
            )
            + " |"
        )
    lines.append("")
    lines.append(
        "Lưu ý: các dòng `TRANSLATION_CANDIDATE` chưa được duyệt và chưa đủ điều kiện render."
    )
    lines.append("")
    return "\n".join(lines)


def _write_phase3_closeout(
    *,
    root: Path,
    handoff: Mapping[str, Any],
    contract: Mapping[str, Any],
    timeline_path: Path,
    render_handoff_path: Path,
) -> Path:
    summary = dict(contract.get("review_summary") or {})
    if (
        str(summary.get("status") or "") != "TRANSLATION_APPROVED"
        or not timeline_path.is_file()
        or not render_handoff_path.is_file()
    ):
        raise Phase3RunnerError("Cannot close Phase 3 before every translation is approved")
    render_handoff = _load_json_object(
        render_handoff_path, label="phase3_render_handoff.json"
    )
    if str(render_handoff.get("status") or "") != "READY_FOR_RENDER":
        raise Phase3RunnerError("Phase 3 render handoff is not READY_FOR_RENDER")
    closeout_path = root / "phase3_closeout.json"
    _write_json_atomic(
        closeout_path,
        {
            "schema_version": "phase3_closeout_v1",
            "status": "PHASE3_CLOSED",
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "phase1_ref": handoff.get("phase1_ref"),
            "phase2_ref": handoff.get("phase2_ref"),
            "phase2_handoff_ref": contract.get("phase2_handoff_ref"),
            "phase3_timeline_ref": {
                "path": timeline_path.name,
                "sha256": _sha256_file(timeline_path),
            },
            "phase3_render_handoff_ref": {
                "path": render_handoff_path.name,
                "sha256": _sha256_file(render_handoff_path),
            },
            "provider": contract.get("provider"),
            "stats": contract.get("stats"),
            "review_summary": summary,
        },
    )
    return closeout_path


def run(root_dir: str | Path) -> int:
    root = Path(root_dir).resolve()
    handoff_path = root / "phase2_handoff.json"
    if not handoff_path.is_file():
        raise Phase3RunnerError("Missing phase2_handoff.json; run/finalize Phase 2 first")

    handoff = _load_json_object(handoff_path, label="phase2_handoff.json")
    handoff_hash = _sha256_file(handoff_path)
    approvals = _load_approvals(
        root / "phase3_approvals.json",
        phase2_handoff_sha256=handoff_hash,
    )
    remediation_fossils = _load_remediation_review_fossils(
        root,
        handoff=handoff,
        phase2_handoff_sha256=handoff_hash,
    )
    review_fossils = _load_approved_review_fossils(
        root,
        phase2_handoff_sha256=handoff_hash,
        approvals=approvals,
        skip_content_ids=set(remediation_fossils),
    )
    review_fossils.update(remediation_fossils)

    session = get_session_factory()()
    try:
        settings = resolve_translator_settings(db=session, workspace_id=None)
    finally:
        session.close()

    logger.info(
        "phase3_translation_started model=%s source=%s translate_items=%s deterministic_items=%s",
        settings.model_name,
        settings.source,
        len(list(handoff.get("translate_items") or [])),
        len(list(handoff.get("deterministic_items") or [])),
    )
    started = time.perf_counter()
    contract = translate_phase3_handoff(
        handoff,
        settings=settings,
        memory_path=root / "qa" / "phase3_translation_memory.json",
        approvals=approvals,
        review_fossils=review_fossils,
        phase2_handoff_path=handoff_path,
    )
    artifact_paths = write_phase3_artifacts(root_dir=root, contract=contract)
    elapsed_seconds = round(time.perf_counter() - started, 2)

    closeout_path: Path | None = None
    timeline_artifact = artifact_paths.get("timeline")
    render_artifact = artifact_paths.get("render_handoff")
    if (
        isinstance(timeline_artifact, Path)
        and isinstance(render_artifact, Path)
        and timeline_artifact.is_file()
        and render_artifact.is_file()
        and str(dict(contract.get("review_summary") or {}).get("status") or "")
        == "TRANSLATION_APPROVED"
    ):
        closeout_path = _write_phase3_closeout(
            root=root,
            handoff=handoff,
            contract=contract,
            timeline_path=timeline_artifact,
            render_handoff_path=render_artifact,
        )

    report_path = root / "PHASE3_TRANSLATION_REVIEW_REPORT.md"
    _write_text_atomic(report_path, _review_report(contract))
    meta = {
        "schema_version": "phase3_run_meta_v1",
        "phase": 3,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phase2_handoff_sha256": handoff_hash,
        "model": settings.model_name,
        "source": settings.source,
        "elapsed_seconds": elapsed_seconds,
        "stats": contract.get("stats"),
        "review_summary": contract.get("review_summary"),
        "artifacts": {
            "timeline": "phase3_translation_timeline.json",
            "review_queue": "phase3_review_queue.json",
            "approvals": "phase3_approvals.json",
            "render_handoff_preview": "phase3_render_handoff_preview.json",
            "review_report": report_path.name,
            "raw_response": "qa/phase3_translation_raw.json",
            "translation_stats": "qa/phase3_translation_stats.json",
            "translation_memory": "qa/phase3_translation_memory.json",
            "closeout": closeout_path.name if closeout_path is not None else None,
        },
    }
    _write_json_atomic(root / "phase3_meta.json", meta)
    summary = dict(contract.get("review_summary") or {})
    logger.info(
        "phase3_translation_completed model=%s source=%s content_objects=%s unresolved=%s failed=%s elapsed_seconds=%s",
        settings.model_name,
        settings.source,
        summary.get("content_objects", 0),
        summary.get("unresolved", 0),
        summary.get("failed", 0),
        elapsed_seconds,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.run_phase3_only",
        description="Translate/review Phase 3 from the Phase 2 handoff authority.",
    )
    parser.add_argument("phase2_output_dir")
    parser.add_argument(
        "--lock-current-candidates",
        action="store_true",
        help="Record explicit operator approval for the unchanged current candidates.",
    )
    parser.add_argument("--reviewer", default="operator")
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    except SystemExit as exc:
        return int(exc.code)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.lock_current_candidates:
            locked = lock_current_candidates(
                args.phase2_output_dir,
                reviewer=args.reviewer,
            )
            logger.info(
                "phase3_candidates_operator_locked reviewer=%s count=%s",
                args.reviewer,
                locked,
            )
        return run(args.phase2_output_dir)
    except Phase3RunnerError as exc:
        print(f"[P3][FAIL] {exc}", flush=True)
        return 1
    except Exception as exc:  # Provider/contract errors: type only, never credentials/URL/path.
        print(f"[P3][FAIL] {type(exc).__name__}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
