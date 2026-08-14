"""Rebind unchanged Phase-3 approvals after an additive OCR remediation."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts.materialize_phase2_residual_remediation import verify_remediation
from src.services.residual_remediation_authority import (
    ResidualRemediationAuthorityError,
    resolve_active_residual_remediation,
)


class Phase3ApprovalRebindError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase3ApprovalRebindError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise Phase3ApprovalRebindError(f"{path.name} must contain an object")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _active_remediation_path(root: Path) -> Path:
    try:
        path = resolve_active_residual_remediation(root)
    except ResidualRemediationAuthorityError as exc:
        raise Phase3ApprovalRebindError(str(exc)) from exc
    if path is None:
        raise Phase3ApprovalRebindError("Residual remediation authority is missing")
    return path


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


def _resolve_phase2_handoff_for_queue(
    root: Path,
    queue: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve the queue-bound handoff even after a failed retry quarantines it."""

    ref = dict(queue.get("phase2_handoff_ref") or {})
    expected_sha = str(ref.get("sha256") or "")
    relative = str(ref.get("path") or "phase2_handoff.json")
    if len(expected_sha) != 64:
        return {}
    stale = root / "qa" / "stale"
    candidates = [root / relative]
    if stale.is_dir():
        candidates.extend(
            sorted(
                stale.glob(f"{Path(relative).stem}_*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        )
    for candidate in candidates:
        resolved = candidate.resolve()
        if (
            not resolved.is_relative_to(root)
            or not resolved.is_file()
            or _sha256_file(resolved) != expected_sha
        ):
            continue
        payload = _load_object(resolved)
        if str(payload.get("status") or "") == "READY_FOR_PHASE3":
            return payload
    return {}


def _collapse_merged_carry_rows(
    carry_rows: dict[str, dict[str, Any]],
    queue_rows: Mapping[str, Mapping[str, Any]],
    remediation: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """Drop stale carry IDs only when geometry was hash-bound into a peer.

    A second geometry override can make Phase 2 merge two previously separate
    content IDs. Rebinding remains safe when the missing ID's exact target
    geometry now belongs to one queued peer with the same approved source and
    Vietnamese text.
    """

    collapsed: list[dict[str, str]] = []
    output = dict(carry_rows)
    overrides = [
        dict(row)
        for row in list(remediation.get("approved_geometry_overrides") or [])
        if isinstance(row, Mapping)
    ]
    for missing_id in sorted(set(output) - set(queue_rows)):
        missing = output[missing_id]
        target_ids = {
            str(dict(row.get("geometry_override") or {}).get("target_text_id") or "")
            for row in overrides
            if str(dict(row.get("localization") or {}).get("content_id") or "")
            == missing_id
        }
        target_ids.discard("")
        matches = [
            content_id
            for content_id, raw in queue_rows.items()
            if content_id in output
            and str(dict(raw).get("zh_approved") or "")
            == str(missing.get("zh_approved") or "")
            and str(output[content_id].get("vi_text_approved") or "")
            == str(missing.get("vi_text_approved") or "")
            and target_ids.intersection(
                {str(value) for value in list(dict(raw).get("geometry_refs") or [])}
            )
        ]
        if len(matches) != 1:
            continue
        output.pop(missing_id)
        collapsed.append(
            {"missing_content_id": missing_id, "merged_into_content_id": matches[0]}
        )
    return output, collapsed


def _rebind_shifted_carry_rows(
    carry_rows: Mapping[str, Mapping[str, Any]],
    queue_rows: Mapping[str, Mapping[str, Any]],
    additive_groups: Mapping[tuple[str, str], list[dict[str, Any]]],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]], list[str]]:
    """Bind carry fossils to current projection ids by exact semantic content.

    Phase 2 content ids are deterministic projection ids, not durable semantic
    identities. Adding a residual occurrence can shift every later id. Existing
    approvals remain authoritative only when both the approved Chinese text and
    Vietnamese candidate match exactly. Any queue row not covered this way must
    be covered by exactly one approved additive translation group.
    """

    rebound: dict[str, dict[str, Any]] = {}
    used_queue_ids: set[str] = set()
    pending: list[tuple[str, dict[str, Any]]] = []
    audit_rows: list[dict[str, str]] = []

    def exact_match(
        carry_row: Mapping[str, Any], queue_row: Mapping[str, Any]
    ) -> bool:
        return bool(str(queue_row.get("review_input_sha256") or "")) and (
            str(queue_row.get("zh_approved") or "")
            == str(carry_row.get("zh_approved") or "")
            and str(queue_row.get("vi_text_candidate") or "")
            == str(carry_row.get("vi_text_candidate") or "")
        )

    # Preserve exact same-id matches first so duplicate text groups stay stable.
    for old_content_id, raw in carry_rows.items():
        row = dict(raw)
        current = queue_rows.get(old_content_id)
        if current is not None and exact_match(row, current):
            rebound[old_content_id] = row
            used_queue_ids.add(old_content_id)
        else:
            pending.append((old_content_id, row))

    stale_carry_ids: list[str] = []
    for old_content_id, row in pending:
        matches = [
            content_id
            for content_id, current in queue_rows.items()
            if content_id not in used_queue_ids and exact_match(row, current)
        ]
        if len(matches) > 1:
            raise Phase3ApprovalRebindError(
                f"Ambiguous shifted translation content for {old_content_id}"
            )
        if not matches:
            stale_carry_ids.append(old_content_id)
            continue
        current_content_id = matches[0]
        rebound[current_content_id] = row
        used_queue_ids.add(current_content_id)
        audit_rows.append(
            {
                "previous_content_id": old_content_id,
                "current_content_id": current_content_id,
            }
        )

    # A stale carry fossil is safe to retire only if every current queue row is
    # still covered by either an exact carry match or one approved additive row.
    for content_id in set(queue_rows) - used_queue_ids:
        approved_zh = str(queue_rows[content_id].get("zh_approved") or "")
        matches = [key for key in additive_groups if key[0] == approved_zh]
        if len(matches) != 1:
            raise Phase3ApprovalRebindError(
                f"Translation carry-forward content set changed at {content_id}"
            )

    return rebound, audit_rows, stale_carry_ids


def stage_unapproved_placeholders(root_dir: str | Path) -> dict[str, Any]:
    """Bind empty decisions to the new handoff so candidates can be rebuilt."""
    root = Path(root_dir).resolve()
    remediation_path = _active_remediation_path(root)
    handoff_path = root / "phase2_handoff.json"
    approvals_path = root / "phase3_approvals.json"
    remediation = _load_object(remediation_path)
    handoff = _load_object(handoff_path)
    if not verify_remediation(remediation):
        raise Phase3ApprovalRebindError("Residual remediation self-hash is invalid")
    if str(handoff.get("status") or "") != "READY_FOR_PHASE3":
        raise Phase3ApprovalRebindError("Phase 2 handoff is not ready")
    carry_rows = [
        dict(row)
        for row in list(
            dict(remediation.get("translation_carry_forward") or {}).get("rows")
            or []
        )
        if isinstance(row, Mapping)
    ]
    if not carry_rows:
        raise Phase3ApprovalRebindError("Translation carry-forward is empty")
    handoff_ref = {
        "path": handoff_path.name,
        "sha256": _sha256_file(handoff_path),
    }
    payload = {
        "schema_version": "phase3_translation_approvals_v1",
        "phase2_handoff_ref": handoff_ref,
        "approvals": [
            {
                "content_id": row.get("content_id"),
                "decision": "",
                "review_input_sha256": "",
                "vi_text_approved": row.get("vi_text_approved"),
                "reviewer": None,
                "reviewed_at": None,
            }
            for row in carry_rows
        ],
    }
    _write_json_atomic(approvals_path, payload)
    audit: dict[str, Any] = {
        "schema_version": "phase3_additive_approval_rebind_staging_v1",
        "status": "UNAPPROVED_PLACEHOLDERS_STAGED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "phase2_handoff_ref": handoff_ref,
        "remediation_ref": {
            "path": remediation_path.name,
            "sha256": _sha256_file(remediation_path),
            "remediation_sha256": remediation.get("remediation_sha256"),
        },
        "counts": {"placeholders": len(carry_rows)},
    }
    audit["audit_sha256"] = _sha256_json(audit)
    _write_json_atomic(root / "phase3_additive_approval_rebind_staging.json", audit)
    return audit


def rebind_approvals(root_dir: str | Path) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    remediation_path = _active_remediation_path(root)
    queue_path = root / "phase3_review_queue.json"
    approvals_path = root / "phase3_approvals.json"
    remediation = _load_object(remediation_path)
    queue = _load_object(queue_path)
    if not verify_remediation(remediation):
        raise Phase3ApprovalRebindError("Residual remediation self-hash is invalid")
    carry = dict(remediation.get("translation_carry_forward") or {})
    carry_rows = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(carry.get("rows") or [])
        if isinstance(row, Mapping) and str(row.get("content_id") or "")
    }
    queue_rows = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(queue.get("content_objects") or [])
        if isinstance(row, Mapping) and str(row.get("content_id") or "")
    }
    carry_rows, collapsed_carry_rows = _collapse_merged_carry_rows(
        carry_rows,
        queue_rows,
        remediation,
    )
    additive_rows = [
        dict(row)
        for row in [
            *list(remediation.get("approved_occurrences") or []),
            *list(remediation.get("approved_geometry_overrides") or []),
        ]
        if isinstance(row, Mapping)
        and str(dict(row.get("localization") or {}).get("mode") or "")
        != "deterministic"
    ]
    extra_content_ids = set(queue_rows) - set(carry_rows)
    additive_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    additive_groups_by_geometry: dict[str, set[tuple[str, str]]] = {}
    for row in additive_rows:
        key = (
            str(row.get("ocr_text_approved") or ""),
            str(row.get("vi_text_approved") or ""),
        )
        if not all(key):
            raise Phase3ApprovalRebindError(
                "Additive remediation translation is incomplete"
            )
        additive_groups.setdefault(key, []).append(row)
        geometry = dict(
            row.get("geometry_override")
            if row.get("geometry_override")
            else row.get("occurrence")
            or {}
        )
        text_id = str(
            geometry.get("target_text_id") or geometry.get("text_id") or ""
        )
        if text_id:
            additive_groups_by_geometry.setdefault(text_id, set()).add(key)
    carry_rows, shifted_carry_rows, stale_carry_ids = _rebind_shifted_carry_rows(
        carry_rows,
        queue_rows,
        additive_groups,
    )
    if not carry_rows:
        raise Phase3ApprovalRebindError(
            "Translation carry-forward content set changed"
        )
    extra_content_ids = set(queue_rows) - set(carry_rows)
    approval_rows: list[dict[str, Any]] = []
    for content_id in carry_rows:
        current = queue_rows[content_id]
        previous = carry_rows[content_id]
        if (
            str(current.get("zh_approved") or "")
            != str(previous.get("zh_approved") or "")
            or str(current.get("vi_text_candidate") or "")
            != str(previous.get("vi_text_candidate") or "")
            or not str(current.get("review_input_sha256") or "")
        ):
            raise Phase3ApprovalRebindError(
                f"Translation content drift detected for {content_id}"
            )
        approval_rows.append(
            {
                "content_id": content_id,
                "decision": previous.get("decision"),
                "review_input_sha256": current.get("review_input_sha256"),
                "vi_text_approved": previous.get("vi_text_approved"),
                "reviewer": previous.get("reviewer"),
                "reviewed_at": previous.get("reviewed_at"),
            }
        )
    remaining_groups = dict(additive_groups)
    handoff = _resolve_phase2_handoff_for_queue(root, queue)
    semantic_dialogue_groups: set[tuple[str, str]] = set()
    semantic_dialogue_geometry_refs: set[str] = set()
    deterministic_geometry_refs: set[str] = set()
    cover_only_geometry_refs: set[str] = set()
    for raw in list(handoff.get("deterministic_items") or []):
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        deterministic_geometry_refs.update(
            str(value)
            for value in list(item.get("geometry_refs") or [])
            if str(value)
        )
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
            semantic_dialogue_geometry_refs.add(str(geometry_ref))
            semantic_dialogue_groups.update(
                additive_groups_by_geometry.get(str(geometry_ref), set())
            )
    for raw in list(handoff.get("cover_only_items") or []):
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        semantic = dict(item.get("semantic_hardsub") or {})
        if (
            str(semantic.get("action") or "") != "COVER_ONLY_TRANSITION"
            and str(item.get("reason") or "") != "semantic_transition_noise"
        ):
            continue
        cover_only_geometry_refs.update(
            str(value)
            for value in list(item.get("geometry_refs") or [])
            if str(value)
        )
    for key in semantic_dialogue_groups:
        rows = list(remaining_groups.get(key) or [])
        non_semantic_rows = [
            row
            for row in rows
            if str(
                dict(row.get("occurrence") or {}).get("text_id")
                or dict(row.get("geometry_override") or {}).get("target_text_id")
                or row.get("remediation_id")
                or ""
            )
            not in semantic_dialogue_geometry_refs
        ]
        if non_semantic_rows:
            remaining_groups[key] = non_semantic_rows
        else:
            remaining_groups.pop(key, None)
    # Cover-only transition rows are deterministic visual operations. They do
    # not enter Phase 3 review and therefore must not remain as an allegedly
    # missing translation group.
    for key, rows in list(remaining_groups.items()):
        unresolved_rows = [
            row
            for row in rows
            if str(
                dict(row.get("occurrence") or {}).get("text_id")
                or dict(row.get("geometry_override") or {}).get("target_text_id")
                or row.get("remediation_id")
                or ""
            )
            not in (deterministic_geometry_refs | cover_only_geometry_refs)
        ]
        if unresolved_rows:
            remaining_groups[key] = unresolved_rows
        else:
            remaining_groups.pop(key, None)
    for content_id in sorted(extra_content_ids):
        current = queue_rows[content_id]
        current_geometry_refs = {
            str(value)
            for value in list(current.get("geometry_refs") or [])
            if str(value)
        }
        matches = [
            (key, rows)
            for key, rows in remaining_groups.items()
            if str(current.get("zh_approved") or "") == key[0]
            and (
                not current_geometry_refs
                or any(
                    str(
                        dict(row.get("occurrence") or {}).get("text_id")
                        or dict(row.get("geometry_override") or {}).get(
                            "target_text_id"
                        )
                        or row.get("remediation_id")
                        or ""
                    )
                    in current_geometry_refs
                    for row in rows
                )
            )
        ]
        if len(matches) != 1 or not str(current.get("review_input_sha256") or ""):
            raise Phase3ApprovalRebindError(
                f"Additive remediation translation drift detected for {content_id}"
            )
        key, approved_rows = matches[0]
        consumed_rows = [
            row
            for row in approved_rows
            if str(
                dict(row.get("occurrence") or {}).get("text_id")
                or dict(row.get("geometry_override") or {}).get("target_text_id")
                or row.get("remediation_id")
                or ""
            )
            in current_geometry_refs
        ]
        if not consumed_rows:
            consumed_rows = list(approved_rows)
        approved = consumed_rows[0]
        remaining_rows = [row for row in approved_rows if row not in consumed_rows]
        if remaining_rows:
            remaining_groups[key] = remaining_rows
        else:
            remaining_groups.pop(key)
        operator_review = dict(approved.get("operator_review") or {})
        if (
            str(operator_review.get("decision") or "") not in {"APPROVE", "EDIT"}
            or not str(operator_review.get("reviewer") or "")
            or not str(operator_review.get("reviewed_at") or "")
            or any(
                str(dict(row.get("operator_review") or {}).get("decision") or "")
                not in {"APPROVE", "EDIT"}
                or str(row.get("ocr_text_approved") or "") != key[0]
                or str(row.get("vi_text_approved") or "") != key[1]
                for row in consumed_rows
            )
        ):
            raise Phase3ApprovalRebindError(
                f"Additive remediation approval is incomplete for {content_id}"
            )
        approval_rows.append(
            {
                "content_id": content_id,
                "decision": (
                    "APPROVE"
                    if str(current.get("vi_text_candidate") or "")
                    == str(approved.get("vi_text_approved") or "")
                    else "EDIT"
                ),
                "review_input_sha256": current.get("review_input_sha256"),
                "vi_text_approved": approved.get("vi_text_approved"),
                "reviewer": operator_review.get("reviewer"),
                "reviewed_at": operator_review.get("reviewed_at"),
            }
        )
    reused_existing_groups = 0
    for (approved_zh, approved_vi), rows in remaining_groups.items():
        matches = [
            content_id
            for content_id in carry_rows
            if str(queue_rows[content_id].get("zh_approved") or "") == approved_zh
            and str(carry_rows[content_id].get("vi_text_approved") or "")
            == approved_vi
        ]
        approved_geometry_refs = {
            str(dict(row.get("occurrence") or {}).get("text_id") or "")
            or str(row.get("remediation_id") or "")
            for row in rows
        }
        approved_geometry_refs.discard("")
        geometry_resolved = False
        if approved_geometry_refs:
            geometry_matches_by_ref = {
                geometry_ref: [
                    content_id
                    for content_id in matches
                    if geometry_ref
                    in {
                        str(ref)
                        for ref in list(
                            queue_rows[content_id].get("geometry_refs") or []
                        )
                        if str(ref)
                    }
                ]
                for geometry_ref in approved_geometry_refs
            }
            if all(
                len(content_ids) == 1
                for content_ids in geometry_matches_by_ref.values()
            ):
                matches = sorted(
                    {
                        content_ids[0]
                        for content_ids in geometry_matches_by_ref.values()
                    }
                )
                geometry_resolved = True
        if not matches or (not geometry_resolved and len(matches) != 1) or any(
            str(dict(row.get("operator_review") or {}).get("decision") or "")
            not in {"APPROVE", "EDIT"}
            for row in rows
        ):
            raise Phase3ApprovalRebindError(
                "Approved additive remediation translation is missing from review queue"
            )
        reused_existing_groups += 1
    payload = {
        "schema_version": "phase3_translation_approvals_v1",
        "phase2_handoff_ref": queue.get("phase2_handoff_ref"),
        "approvals": approval_rows,
    }
    _write_json_atomic(approvals_path, payload)
    audit: dict[str, Any] = {
        "schema_version": "phase3_additive_approval_rebind_audit_v1",
        "status": "EXACT_TRANSLATION_APPROVALS_REBOUND_RERUN_REQUIRED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": "exact_carry_forward_plus_operator_approved_additive_match",
        "remediation_ref": {
            "path": remediation_path.name,
            "sha256": _sha256_file(remediation_path),
            "remediation_sha256": remediation.get("remediation_sha256"),
        },
        "review_queue_ref": {
            "path": queue_path.name,
            "sha256": _sha256_file(queue_path),
        },
        "approvals_ref": {
            "path": approvals_path.name,
            "sha256": _sha256_file(approvals_path),
        },
        "counts": {
            "rebound": len(approval_rows),
            "carry_forward": len(carry_rows),
            "remediation_approved": len(additive_rows),
            "remediation_content_groups": len(additive_groups),
            "reused_existing_content_groups": reused_existing_groups,
            "semantic_dialogue_content_groups": len(semantic_dialogue_groups),
            "cover_only_geometry_rows": len(cover_only_geometry_refs),
            "collapsed_carry_rows": len(collapsed_carry_rows),
            "shifted_carry_rows": len(shifted_carry_rows),
            "stale_carry_rows": len(stale_carry_ids),
        },
        "collapsed_carry_rows": collapsed_carry_rows,
        "shifted_carry_rows": shifted_carry_rows,
        "stale_carry_ids": stale_carry_ids,
    }
    audit["audit_sha256"] = _sha256_json(audit)
    _write_json_atomic(root / "phase3_additive_approval_rebind_audit.json", audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.rebind_phase3_approvals_after_residual_remediation"
    )
    parser.add_argument("artifact_root")
    parser.add_argument("--stage", action="store_true")
    args = parser.parse_args()
    try:
        audit = (
            stage_unapproved_placeholders(args.artifact_root)
            if args.stage
            else rebind_approvals(args.artifact_root)
        )
        count_key = "placeholders" if args.stage else "rebound"
        print(
            json.dumps(
                {
                    "status": audit["status"],
                    count_key: audit["counts"][count_key],
                    "audit_sha256": audit["audit_sha256"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, Phase3ApprovalRebindError) as exc:
        print(f"[PHASE3-APPROVAL-REBIND][FAIL] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
