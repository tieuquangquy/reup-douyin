"""Phase-2 OCR enrichment contract over an immutable Phase-1 timeline."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    classify_ocr_box_role,
    timeline_to_ocr_payload,
)

PHASE2_SCHEMA_VERSION = "phase2_ocr_timeline_v2"
PHASE2_PREPROCESSING_VERSION = "phase2_ocr_prep_v2_normalized_fallback"
PHASE2_HANDOFF_SCHEMA_VERSION = "phase2_handoff_v1"
PHASE2_REVIEW_INPUT_SCHEMA_VERSION = "phase2_review_input_v1"
PHASE2_DUPLICATE_TRANSITION_POLICY_VERSION = (
    "operator_approved_touching_text_v1"
)

_UNIT_MAP: dict[str, str] = {
    "kcal": "kcal",
    "kg": "kg",
    "ml": "ml",
    "°C": "°C",
    "℃": "°C",
    "g": "g",
    "L": "L",
    "l": "L",
    "%": "%",
    "千卡": "kcal",
    "卡路里": "kcal",
    "千克": "kg",
    "公斤": "kg",
    "毫升": "ml",
    "克": "g",
    "升": "L",
    "勺": "thìa",
    "碗": "bát",
    "个": "cái",
}
_UNIT_PATTERN = "|".join(
    re.escape(unit) for unit in sorted(_UNIT_MAP, key=len, reverse=True)
)
_NUMBER_UNIT_RE = re.compile(
    rf"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>{_UNIT_PATTERN})"
)
_PURE_NUMBER_RE = re.compile(r"^\d+(?:[.,]\d+)?%?$")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_content_text(text: str) -> str:
    return "".join(str(text or "").split())


def parse_localization_policy(text: str) -> dict[str, Any]:
    """Protect numeric values and deterministically normalize known units."""
    raw = str(text or "").strip()
    if not raw:
        return {
            "mode": "cover_only",
            "translation_input": "",
            "render_text_suggested": None,
            "protected_values": [],
            "unit_tokens": [],
        }

    if raw in _UNIT_MAP:
        return {
            "mode": "deterministic",
            "translation_input": "",
            "render_text_suggested": _UNIT_MAP[raw],
            "protected_values": [],
            "unit_tokens": [{"raw": raw, "canonical": _UNIT_MAP[raw]}],
        }
    if _PURE_NUMBER_RE.fullmatch(raw):
        return {
            "mode": "deterministic",
            "translation_input": "",
            "render_text_suggested": raw,
            "protected_values": [raw.rstrip("%")],
            "unit_tokens": [],
        }

    matches = list(_NUMBER_UNIT_RE.finditer(raw))
    if not matches:
        return {
            "mode": "llm_translate",
            "translation_input": raw,
            "render_text_suggested": None,
            "protected_values": [],
            "unit_tokens": [],
        }

    protected_values: list[str] = []
    unit_tokens: list[dict[str, str]] = []
    rendered = raw
    translation_input = raw
    for index, match in reversed(list(enumerate(matches))):
        value = str(match.group("value"))
        unit_raw = str(match.group("unit"))
        canonical = _UNIT_MAP[unit_raw]
        start, end = match.span()
        translation_input = (
            translation_input[:start]
            + f"{{{{VALUE_{index}}}}} {{{{UNIT_{index}}}}}"
            + translation_input[end:]
        )
        rendered = rendered[:start] + f"{value} {canonical}" + rendered[end:]

    for match in matches:
        value = str(match.group("value"))
        unit_raw = str(match.group("unit"))
        protected_values.append(value)
        unit_tokens.append({"raw": unit_raw, "canonical": _UNIT_MAP[unit_raw]})

    remainder = _NUMBER_UNIT_RE.sub("", raw).strip()
    mode = "llm_with_protected_tokens" if remainder else "deterministic"
    return {
        "mode": mode,
        "translation_input": translation_input if remainder else "",
        "render_text_suggested": rendered if not remainder else None,
        "protected_values": protected_values,
        "unit_tokens": unit_tokens,
    }


def _approval_for(
    approvals: Mapping[str, Mapping[str, Any]] | None,
    content_id: str,
) -> Mapping[str, Any]:
    if not approvals:
        return {}
    return approvals.get(content_id) or {}


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def content_review_input_sha256(
    content: Mapping[str, Any],
    *,
    phase1_sha256: str,
) -> str:
    """Bind an operator decision to the exact OCR evidence it reviewed."""
    return _sha256_json(
        {
            "schema_version": PHASE2_REVIEW_INPUT_SCHEMA_VERSION,
            "phase1_sha256": str(phase1_sha256),
            "content_id": str(content.get("content_id") or ""),
            "geometry_refs": list(content.get("geometry_refs") or []),
            "ocr_text_candidate": str(content.get("ocr_text_candidate") or ""),
            "ocr_text_llm_suggested": str(
                content.get("ocr_text_llm_suggested") or ""
            ),
            "provenance_classifications": list(
                content.get("provenance_classifications") or []
            ),
        }
    )


def _occurrence_spans(content: Mapping[str, Any]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for raw in list(content.get("review_assets") or []):
        if not isinstance(raw, Mapping):
            continue
        try:
            start = int(raw.get("start_frame"))
            end = int(raw.get("end_frame"))
        except (TypeError, ValueError):
            continue
        spans.append((min(start, end), max(start, end)))
    return spans


def _has_touching_occurrences(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    return any(
        left_start <= right_end + 1 and right_start <= left_end + 1
        for left_start, left_end in _occurrence_spans(left)
        for right_start, right_end in _occurrence_spans(right)
    )


def _operator_review_rows(content: Mapping[str, Any]) -> list[dict[str, Any]]:
    existing = content.get("operator_reviews")
    if isinstance(existing, list):
        return [dict(row) for row in existing if isinstance(row, Mapping)]
    review = content.get("operator_review")
    if not isinstance(review, Mapping):
        return []
    return [
        {
            "source_content_id": str(content.get("content_id") or ""),
            **dict(review),
        }
    ]


def _merge_approved_transition_duplicates(
    content_objects: Sequence[Mapping[str, Any]],
    track_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Translate an operator-confirmed transition once and retain every geometry."""
    canonical: list[dict[str, Any]] = []
    aliases: dict[str, str] = {}
    merged_count = 0
    for raw in content_objects:
        content = dict(raw)
        approved_text = _normalize_content_text(
            str(content.get("ocr_text_approved") or "")
        )
        if (
            str(content.get("review_status") or "") != "OCR_APPROVED"
            or bool(content.get("review_required"))
            or not approved_text
        ):
            canonical.append(content)
            continue
        host = next(
            (
                row
                for row in reversed(canonical)
                if str(row.get("review_status") or "") == "OCR_APPROVED"
                and not bool(row.get("review_required"))
                and _normalize_content_text(
                    str(row.get("ocr_text_approved") or "")
                )
                == approved_text
                and str(row.get("vi_text_approved") or "")
                == str(content.get("vi_text_approved") or "")
                and _has_touching_occurrences(row, content)
            ),
            None,
        )
        if host is None:
            canonical.append(content)
            continue

        host_id = str(host.get("content_id") or "")
        source_id = str(content.get("content_id") or "")
        aliases[source_id] = host_id
        merged_count += 1
        for key in ("geometry_refs", "review_assets", "roles", "ocr_text_raw_candidates"):
            target = list(host.get(key) or [])
            for value in list(content.get(key) or []):
                if value not in target:
                    target.append(value)
            host[key] = target
        source_ids = list(host.get("source_content_ids") or [host_id])
        source_ids.extend(
            value
            for value in list(content.get("source_content_ids") or [source_id])
            if value not in source_ids
        )
        review_hashes = list(
            host.get("source_review_input_sha256s")
            or [str(host.get("review_input_sha256") or "")]
        )
        review_hashes.extend(
            value
            for value in list(
                content.get("source_review_input_sha256s")
                or [str(content.get("review_input_sha256") or "")]
            )
            if value and value not in review_hashes
        )
        host["source_content_ids"] = source_ids
        host["source_review_input_sha256s"] = review_hashes
        host["operator_reviews"] = [
            *_operator_review_rows(host),
            *_operator_review_rows(content),
        ]
        canonicalization = {
            "policy_version": PHASE2_DUPLICATE_TRANSITION_POLICY_VERSION,
            "canonical_content_id": host_id,
            "source_content_ids": source_ids,
            "source_review_input_sha256s": review_hashes,
            "ocr_text_approved": str(host.get("ocr_text_approved") or ""),
            "geometry_refs": list(host.get("geometry_refs") or []),
        }
        host["duplicate_transition_canonicalization"] = {
            **canonicalization,
            "canonicalization_sha256": _sha256_json(canonicalization),
        }

    if aliases:
        for row in track_rows:
            content_id = str(row.get("content_id") or "")
            if content_id in aliases:
                row["content_id"] = aliases[content_id]
    return canonical, merged_count


def build_phase2_contract(
    timeline: Sequence[Mapping[str, Any]],
    *,
    phase1_timeline_path: str | Path,
    provider_mode: str,
    model_version: str,
    preprocessing_version: str = PHASE2_PREPROCESSING_VERSION,
    approvals: Mapping[str, Mapping[str, Any]] | None = None,
    llm_suggestions: Mapping[str, str] | None = None,
    phase1_geometry_review_ref: Mapping[str, Any] | None = None,
    residual_remediation_ref: Mapping[str, Any] | None = None,
    supplemental_occurrences: Sequence[Mapping[str, Any]] = (),
    geometry_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    protected_source_tracks: Sequence[Mapping[str, Any]] = (),
    frame_width: int = 1920,
    frame_height: int = 1080,
) -> dict[str, Any]:
    """Group OCR content independently from immutable geometry occurrences."""
    phase1_path = Path(phase1_timeline_path)
    phase1_sha256 = sha256_file(phase1_path)
    grouped: dict[str, dict[str, Any]] = {}
    group_order: list[str] = []
    track_rows: list[dict[str, Any]] = []

    for index, raw in enumerate(timeline):
        text_id = str(raw.get("text_id") or f"sub_{index + 1:02d}")
        candidate = str(
            raw.get("ocr_text_raw")
            or raw.get("ocr_text")
            or raw.get("text")
            or ""
        ).strip()
        normalized = _normalize_content_text(candidate)
        visual_provenance = dict(raw.get("visual_provenance") or {})
        provenance_class = str(
            visual_provenance.get("classification") or "EDITOR_OVERLAY"
        )
        grouping_key = (
            f"{provenance_class}:text:{normalized}"
            if normalized
            else f"{provenance_class}:failed:{text_id}"
        )
        if grouping_key not in grouped:
            content_id = f"ocr_content_{len(group_order) + 1:03d}"
            grouped[grouping_key] = {
                "content_id": content_id,
                "geometry_refs": [],
                "review_assets": [],
                "roles": [],
                "provenance_classifications": [],
                "ocr_text_raw_candidates": [],
                "ocr_text_candidate": candidate,
                "ocr_text_llm_suggested": None,
                "ocr_text_approved": None,
                "vi_text_approved": None,
                "review_status": "OCR_CANDIDATE" if candidate else "OCR_FAILED",
                "review_required": True,
                "ready_for_translation": False,
                "localization": parse_localization_policy(candidate),
                "operator_review": None,
            }
            group_order.append(grouping_key)
        content = grouped[grouping_key]
        if provenance_class not in content["provenance_classifications"]:
            content["provenance_classifications"].append(provenance_class)
        content["geometry_refs"].append(text_id)
        content["review_assets"].append(
            {
                "text_id": text_id,
                "crop_path": raw.get("crop_path"),
                "best_keyframe_path": raw.get("best_keyframe_path"),
                "overlay_path": f"qa/overlays/{text_id}.jpg",
                "boundary_path": f"qa/boundaries/{text_id}.jpg",
                "start_frame": raw.get("start_frame"),
                "end_frame": raw.get("end_frame"),
                "visual_provenance": visual_provenance,
            }
        )
        coords = list(raw.get("box_coords") or [])
        semantic_role = str(raw.get("semantic_role") or "").strip()
        role = semantic_role or (
            classify_ocr_box_role(
                coords,
                frame_w=frame_width,
                frame_h=frame_height,
            )
            if len(coords) >= 4
            else "generic"
        )
        if role not in content["roles"]:
            content["roles"].append(role)
        if candidate and candidate not in content["ocr_text_raw_candidates"]:
            content["ocr_text_raw_candidates"].append(candidate)
        track_rows.append(
            {
                "text_id": text_id,
                "content_id": content["content_id"],
                "ocr_source": raw.get("ocr_source"),
                "ocr_frame": raw.get("ocr_frame"),
                "ocr_text_raw": candidate,
                "ocr_role": role,
                "visual_provenance": visual_provenance,
            }
        )

    content_objects: list[dict[str, Any]] = []
    for key in group_order:
        content = grouped[key]
        content_id = str(content["content_id"])
        if llm_suggestions and llm_suggestions.get(content_id):
            content["ocr_text_llm_suggested"] = str(
                llm_suggestions[content_id]
            ).strip()
        review_input_sha256 = content_review_input_sha256(
            content,
            phase1_sha256=phase1_sha256,
        )
        content["review_input_sha256"] = review_input_sha256
        approval = _approval_for(approvals, content_id)
        decision = str(approval.get("decision") or "").upper()
        approval_review_hash = str(
            approval.get("review_input_sha256") or ""
        ).strip()
        approval_stale = bool(decision) and (
            approval_review_hash != review_input_sha256
        )
        if approval_stale:
            content["review_status"] = "OCR_REVIEW_STALE"
            content["review_required"] = True
            content["ready_for_translation"] = False
        elif decision in {"APPROVE", "EDIT", "ACCEPT_LLM"}:
            if decision == "ACCEPT_LLM":
                # The approval template intentionally prefills the raw candidate.
                # ACCEPT_LLM must therefore ignore that field and select only the
                # suggestion; a missing suggestion remains unresolved/fail-closed.
                approved_text = str(
                    content.get("ocr_text_llm_suggested") or ""
                ).strip()
            else:
                approved_text = str(
                    approval.get("ocr_text_approved")
                    or content.get("ocr_text_candidate")
                    or ""
                ).strip()
            if approved_text:
                content["ocr_text_approved"] = approved_text
                content["localization"] = parse_localization_policy(approved_text)
                content["review_status"] = "OCR_APPROVED"
                content["review_required"] = False
                suggested = content["localization"].get("render_text_suggested")
                if decision == "ACCEPT_LLM":
                    # Recompute deterministic render text from the accepted
                    # correction; do not retain the template value derived from
                    # the stale raw OCR candidate.
                    content["vi_text_approved"] = suggested or None
                else:
                    content["vi_text_approved"] = (
                        str(approval.get("vi_text_approved") or "").strip()
                        or suggested
                        or None
                    )
                content["ready_for_translation"] = (
                    str(content["localization"].get("mode") or "").startswith("llm")
                    and not content["vi_text_approved"]
                )
        elif decision in {"REJECT_UI", "PRESERVE_SOURCE"}:
            content["review_status"] = "SOURCE_INTRINSIC_APPROVED"
            content["review_required"] = False
            content["ready_for_translation"] = False
        if decision:
            content["operator_review"] = {
                "decision": decision,
                "reviewer": approval.get("reviewer"),
                "reviewed_at": approval.get("reviewed_at"),
                "review_input_sha256": approval_review_hash or None,
                "stale": approval_stale,
            }
            carry_forward = approval.get("carry_forward")
            if isinstance(carry_forward, Mapping):
                content["operator_review"]["carry_forward"] = dict(
                    carry_forward
                )
        content_objects.append(content)

    content_objects, merged_transition_count = (
        _merge_approved_transition_duplicates(content_objects, track_rows)
    )

    unresolved = sum(1 for item in content_objects if item["review_required"])
    approved_n = sum(
        1 for item in content_objects if item["review_status"] == "OCR_APPROVED"
    )
    rejected_ui_n = sum(
        1
        for item in content_objects
        if item["review_status"] in {"OCR_REJECTED_UI", "SOURCE_INTRINSIC_APPROVED"}
    )
    stale_n = sum(
        1 for item in content_objects if item["review_status"] == "OCR_REVIEW_STALE"
    )
    if unresolved == 0:
        review_status = "OCR_APPROVED"
    elif stale_n:
        review_status = "OCR_REVIEW_STALE"
    else:
        review_status = "NEEDS_OCR_REVIEW"
    contract = {
        "schema_version": PHASE2_SCHEMA_VERSION,
        "phase1_ref": {
            "path": phase1_path.name,
            "sha256": phase1_sha256,
        },
        "provider": {
            "mode": str(provider_mode),
            "model_version": str(model_version),
            "preprocessing_version": str(preprocessing_version),
        },
        "track_enrichments": track_rows,
        "content_objects": content_objects,
        "protected_source_tracks": [
            dict(row) for row in protected_source_tracks if isinstance(row, Mapping)
        ],
        "review_summary": {
            "content_objects": len(content_objects),
            "protected_source_tracks": len(list(protected_source_tracks)),
            "approved": approved_n,
            "rejected_ui": rejected_ui_n,
            "stale": stale_n,
            "unresolved": unresolved,
            "status": review_status,
        },
        "duplicate_transition_summary": {
            "policy_version": PHASE2_DUPLICATE_TRANSITION_POLICY_VERSION,
            "merged_content_objects": merged_transition_count,
        },
    }
    if phase1_geometry_review_ref:
        contract["phase1_geometry_review_ref"] = dict(
            phase1_geometry_review_ref
        )
    if residual_remediation_ref:
        contract["residual_remediation_ref"] = dict(residual_remediation_ref)
        contract["supplemental_occurrences"] = [
            dict(row) for row in supplemental_occurrences
        ]
        contract["geometry_overrides"] = [
            dict(row)
            for _text_id, row in sorted(
                dict(geometry_overrides or {}).items(),
                key=lambda item: str(item[0]),
            )
        ]
    return contract


def _content_by_id(contract: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item.get("content_id")): item
        for item in (contract.get("content_objects") or [])
        if isinstance(item, Mapping)
    }


def _enriched_timeline(
    phase1_timeline: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    track_map = {
        str(item.get("text_id")): item
        for item in (contract.get("track_enrichments") or [])
        if isinstance(item, Mapping)
    }
    contents = _content_by_id(contract)
    out: list[dict[str, Any]] = []
    for raw in phase1_timeline:
        entry = dict(raw)
        track = track_map.get(str(entry.get("text_id") or "")) or {}
        content = contents.get(str(track.get("content_id") or "")) or {}
        localization = dict(content.get("localization") or {})
        approved_text = str(content.get("ocr_text_approved") or "").strip()
        status = str(content.get("review_status") or "")
        entry.update(
            {
                "content_id": content.get("content_id"),
                "ocr_role": track.get("ocr_role"),
                "ocr_source": track.get("ocr_source"),
                "ocr_frame": track.get("ocr_frame"),
                "ocr_text_raw": track.get("ocr_text_raw"),
                "ocr_text_candidate": content.get("ocr_text_candidate"),
                "ocr_text_llm_suggested": content.get(
                    "ocr_text_llm_suggested"
                ),
                "ocr_text_approved": approved_text or None,
                "ocr_review_status": status,
                "ocr_review_required": bool(content.get("review_required")),
                "localization_mode": localization.get("mode"),
                "render_text_approved": content.get("vi_text_approved"),
            }
        )
        entry["ocr_text"] = approved_text
        entry["translate_ready"] = bool(content.get("ready_for_translation"))
        if status == "OCR_REJECTED_UI":
            entry["translate_reject_reason"] = "operator_rejected_ui"
        elif content.get("review_required"):
            entry["translate_reject_reason"] = "ocr_review_required"
        elif not entry["translate_ready"]:
            entry["translate_reject_reason"] = "deterministic_localization"
        else:
            entry["translate_reject_reason"] = ""
        out.append(entry)
    return out


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _quarantine_generated_artifact(path: Path, *, root: Path) -> Path | None:
    """Move a stale generated JSON into QA instead of leaving it authoritative."""
    if not path.is_file():
        return None
    stale_dir = root / "qa" / "stale"
    stale_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = sha256_file(path)[:12]
    destination = stale_dir / f"{path.stem}_{fingerprint}{path.suffix}"
    path.replace(destination)
    return destination


def build_phase2_handoff(
    contract: Mapping[str, Any],
    *,
    phase2_timeline_path: str | Path,
) -> dict[str, Any]:
    """Build the only authoritative Phase-2 → Phase-3 content boundary."""
    phase2_path = Path(phase2_timeline_path)
    translate_items: list[dict[str, Any]] = []
    deterministic_items: list[dict[str, Any]] = []
    cover_only_items: list[dict[str, Any]] = []
    preserved_source_items: list[dict[str, Any]] = [
        dict(row)
        for row in list(contract.get("protected_source_tracks") or [])
        if isinstance(row, Mapping)
    ]
    geometry_map: dict[str, dict[str, Any]] = {}
    blocked_reasons: list[str] = []

    for raw in list(contract.get("content_objects") or []):
        if not isinstance(raw, Mapping):
            continue
        content_id = str(raw.get("content_id") or "")
        geometry_refs = [str(ref) for ref in list(raw.get("geometry_refs") or [])]
        localization = dict(raw.get("localization") or {})
        mode = str(localization.get("mode") or "")
        status = str(raw.get("review_status") or "")
        base = {
            "content_id": content_id,
            "geometry_refs": geometry_refs,
            "roles": list(raw.get("roles") or []),
            "zh_approved": raw.get("ocr_text_approved"),
            "review_input_sha256": raw.get("review_input_sha256"),
            "source_content_ids": list(
                raw.get("source_content_ids") or [content_id]
            ),
            "source_review_input_sha256s": list(
                raw.get("source_review_input_sha256s")
                or [raw.get("review_input_sha256")]
            ),
            "duplicate_transition_canonicalization": raw.get(
                "duplicate_transition_canonicalization"
            ),
        }
        for text_id in geometry_refs:
            if text_id in geometry_map:
                blocked_reasons.append(f"duplicate_geometry_ref:{text_id}")
                continue
            geometry_map[text_id] = {
                "content_id": content_id,
                "localization_mode": mode,
            }

        if status in {"OCR_REJECTED_UI", "SOURCE_INTRINSIC_APPROVED"}:
            for text_id in geometry_refs:
                geometry_map.pop(text_id, None)
            preserved_source_items.append(
                {**base, "reason": "operator_confirmed_source_intrinsic"}
            )
            continue
        if status != "OCR_APPROVED":
            blocked_reasons.append(f"unapproved_content:{content_id}")
            continue
        if mode == "deterministic":
            render_text = str(raw.get("vi_text_approved") or "").strip()
            if not render_text:
                blocked_reasons.append(f"missing_deterministic_render:{content_id}")
                continue
            deterministic_items.append(
                {
                    **base,
                    "render_text": render_text,
                    "protected_values": list(
                        localization.get("protected_values") or []
                    ),
                    "unit_tokens": list(localization.get("unit_tokens") or []),
                }
            )
            continue
        if mode.startswith("llm"):
            translation_input = str(
                localization.get("translation_input")
                or raw.get("ocr_text_approved")
                or ""
            ).strip()
            if not translation_input:
                blocked_reasons.append(f"missing_translation_input:{content_id}")
                continue
            translate_items.append(
                {
                    **base,
                    "translation_input": translation_input,
                    "protected_values": list(
                        localization.get("protected_values") or []
                    ),
                    "unit_tokens": list(localization.get("unit_tokens") or []),
                }
            )
            continue
        cover_only_items.append({**base, "reason": "cover_only"})

    track_refs = {
        str(row.get("text_id") or "")
        for row in list(contract.get("track_enrichments") or [])
        if isinstance(row, Mapping) and str(row.get("text_id") or "")
    }
    preserved_refs = {
        str(text_id)
        for item in preserved_source_items
        for text_id in (
            list(item.get("geometry_refs") or [])
            if isinstance(item, Mapping)
            else []
        )
    } | {
        str(item.get("text_id") or "")
        for item in preserved_source_items
        if isinstance(item, Mapping) and str(item.get("text_id") or "")
    }
    mapped_refs = set(geometry_map)
    for missing in sorted(track_refs - mapped_refs - preserved_refs):
        blocked_reasons.append(f"missing_geometry_ref:{missing}")
    for unexpected in sorted(mapped_refs - track_refs):
        blocked_reasons.append(f"unexpected_geometry_ref:{unexpected}")

    review = dict(contract.get("review_summary") or {})
    if int(review.get("unresolved") or 0) > 0:
        blocked_reasons.append("ocr_review_unresolved")
    blocked_reasons = list(dict.fromkeys(blocked_reasons))
    status = "READY_FOR_PHASE3" if not blocked_reasons else "HANDOFF_BLOCKED"
    return {
        "schema_version": PHASE2_HANDOFF_SCHEMA_VERSION,
        "phase1_ref": contract.get("phase1_ref"),
        "phase1_geometry_review_ref": contract.get(
            "phase1_geometry_review_ref"
        ),
        "residual_remediation_ref": contract.get("residual_remediation_ref"),
        "phase2_ref": {
            "path": phase2_path.name,
            "sha256": sha256_file(phase2_path),
        },
        "status": status,
        "blocked_reasons": blocked_reasons,
        "counts": {
            "content_objects": len(list(contract.get("content_objects") or [])),
            "translate_items": len(translate_items),
            "deterministic_items": len(deterministic_items),
            "cover_only_items": len(cover_only_items),
            "preserved_source_items": len(preserved_source_items),
            "geometry_refs": len(geometry_map),
        },
        "translate_items": translate_items,
        "deterministic_items": deterministic_items,
        "cover_only_items": cover_only_items,
        "preserved_source_items": preserved_source_items,
        "geometry_map": geometry_map,
    }


def write_phase2_artifacts(
    *,
    root_dir: str | Path,
    contract: Mapping[str, Any],
    phase1_timeline: Sequence[Mapping[str, Any]],
    fps: float,
    frame_count: int,
    frame_width: int,
    frame_height: int,
) -> dict[str, Path]:
    """Write Phase-2 artifacts without mutating the Phase-1 timeline file."""
    root = Path(root_dir)
    phase2_path = root / "phase2_ocr_timeline.json"
    review_path = root / "phase2_review_queue.json"
    approved_path = root / "phase2_approved_content.json"
    approvals_path = root / "phase2_approvals.json"
    llm_suggestions_path = root / "phase2_llm_suggestions.json"
    handoff_preview_path = root / "phase2_handoff_preview.json"
    handoff_path = root / "phase2_handoff.json"
    preview_path = root / "phase2_ocr_payload_preview.json"
    final_path = root / "ocr_payload.json"

    content_objects = list(contract.get("content_objects") or [])
    review_queue = [item for item in content_objects if item.get("review_required")]
    approved = [
        item for item in content_objects if item.get("review_status") == "OCR_APPROVED"
    ]
    _write_json_atomic(phase2_path, dict(contract))
    _write_json_atomic(
        review_path,
        {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "phase1_ref": contract.get("phase1_ref"),
            "phase1_geometry_review_ref": contract.get(
                "phase1_geometry_review_ref"
            ),
            "residual_remediation_ref": contract.get(
                "residual_remediation_ref"
            ),
            "review_summary": contract.get("review_summary"),
            "content_objects": review_queue,
        },
    )
    _write_json_atomic(
        approved_path,
        {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "phase1_ref": contract.get("phase1_ref"),
            "phase1_geometry_review_ref": contract.get(
                "phase1_geometry_review_ref"
            ),
            "residual_remediation_ref": contract.get(
                "residual_remediation_ref"
            ),
            "content_objects": approved,
        },
    )
    if not approvals_path.exists():
        _write_json_atomic(
            approvals_path,
            {
                "schema_version": "phase2_approvals_v2",
                "phase1_ref": contract.get("phase1_ref"),
                "approvals": [
                    {
                        "content_id": item.get("content_id"),
                        "decision": "",
                        "review_input_sha256": item.get(
                            "review_input_sha256"
                        ),
                        "ocr_text_approved": item.get("ocr_text_candidate"),
                        "vi_text_approved": (
                            item.get("localization") or {}
                        ).get("render_text_suggested"),
                        "reviewer": None,
                        "reviewed_at": None,
                    }
                    for item in content_objects
                ],
            },
        )
    if not llm_suggestions_path.exists():
        _write_json_atomic(
            llm_suggestions_path,
            {
                "schema_version": "phase2_llm_suggestions_v1",
                "phase1_ref": contract.get("phase1_ref"),
                "suggestions": [],
            },
        )
    legacy_queue_path = root / "qa" / "translate_queue.json"
    if legacy_queue_path.is_file():
        try:
            legacy_payload = json.loads(
                legacy_queue_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            legacy_payload = {}
        if str(legacy_payload.get("schema_version") or "") == (
            "phase2_translate_queue_v1"
        ):
            _quarantine_generated_artifact(legacy_queue_path, root=root)

    enriched = _enriched_timeline(phase1_timeline, contract)
    preview_payload = timeline_to_ocr_payload(
        enriched,
        fps=fps,
        frame_count=frame_count,
        frame_width=frame_width,
        frame_height=frame_height,
    )
    preview_payload["phase2_contract"] = {
        "schema_version": contract.get("schema_version"),
        "phase1_ref": contract.get("phase1_ref"),
        "phase1_geometry_review_ref": contract.get(
            "phase1_geometry_review_ref"
        ),
        "residual_remediation_ref": contract.get("residual_remediation_ref"),
        "review_summary": contract.get("review_summary"),
    }
    _write_json_atomic(preview_path, preview_payload)
    handoff = build_phase2_handoff(
        contract,
        phase2_timeline_path=phase2_path,
    )
    _write_json_atomic(handoff_preview_path, handoff)
    if handoff["status"] == "READY_FOR_PHASE3":
        _write_json_atomic(final_path, preview_payload)
        _write_json_atomic(handoff_path, handoff)
    else:
        _quarantine_generated_artifact(final_path, root=root)
        _quarantine_generated_artifact(handoff_path, root=root)

    return {
        "phase2_timeline": phase2_path,
        "review_queue": review_path,
        "approved_content": approved_path,
        "approvals": approvals_path,
        "llm_suggestions": llm_suggestions_path,
        "handoff_preview": handoff_preview_path,
        "phase2_handoff": handoff_path,
        "preview_payload": preview_path,
        "final_payload": final_path,
    }
