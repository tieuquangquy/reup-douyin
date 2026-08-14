"""Run Phase 2 OCR on an existing Master Phase 1 folder (timeline + crops)."""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping

from src.services.residual_remediation_authority import (
    ResidualRemediationAuthorityError,
    resolve_active_residual_remediation,
)

API_ROOT = Path(__file__).resolve().parents[1]
LOCAL_OCR_ENDPOINT_ENV = "LOCAL_OCR_ENDPOINT_URL"
DEFAULT_LOCAL_OCR_ENDPOINT = "http://127.0.0.1:8080/predict"
_OCR_SIGNATURE_RE = re.compile(r"[0-9\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LEADING_UI_DATE_RE = re.compile(
    r"^(?:[0-9]{1,4}\u5e74)?(?:[0-9]{1,2}\u6708)?[0-9]{1,2}[\u65e5\u53f7]"
)
_MEANINGFUL_SHORT_VALUE_RE = re.compile(
    r"^\d+(?:[.,]\d+)?(?:%|g|kg|ml|kcal|Â°C|â„ƒ)?$",
    re.IGNORECASE,
)


def _ocr_signature(text: str) -> str:
    return "".join(_OCR_SIGNATURE_RE.findall(str(text or "")))


def _is_symbol_dominant_non_text(text: str) -> bool:
    normalized = "".join(str(text or "").split())
    if not normalized or _MEANINGFUL_SHORT_VALUE_RE.fullmatch(normalized):
        return False
    cjk = sum(1 for char in normalized if "\u3400" <= char <= "\u9fff")
    alnum = sum(1 for char in normalized if char.isalnum())
    symbols = sum(1 for char in normalized if not char.isalnum())
    return cjk == 0 and alnum <= 1 and symbols >= 1


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_semantic_dialogue_authority(
    path: Path,
    *,
    expected_phase1_sha256: str,
) -> dict[str, Any]:
    """Load the frontend bridge only when every authority hash is current."""

    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("semantic_dialogue_authority.json must be an object")
    phase1_ref = dict(payload.get("phase1_ref") or {})
    if str(phase1_ref.get("sha256") or "") != str(expected_phase1_sha256):
        raise RuntimeError(
            "semantic_dialogue_authority.json is stale for master_timeline.json"
        )
    recorded_sha256 = str(payload.get("authority_sha256") or "")
    hash_payload = dict(payload)
    hash_payload.pop("authority_sha256", None)
    if not recorded_sha256 or recorded_sha256 != _sha256_json(hash_payload):
        raise RuntimeError(
            "semantic_dialogue_authority.json authority SHA-256 mismatch"
        )
    file_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    authority_ref = dict(payload.get("authority_ref") or {})
    payload["authority_ref"] = {
        **authority_ref,
        "path": path.name,
        "sha256": file_digest,
        "authority_sha256": recorded_sha256,
    }
    return payload


def _is_single_deletion_variant(candidate: str, approved: str) -> bool:
    """Allow one missing OCR glyph, never an inserted/substituted glyph."""
    if len(candidate) < 4 or len(approved) - len(candidate) != 1:
        return False
    candidate_index = 0
    for char in approved:
        if candidate_index < len(candidate) and candidate[candidate_index] == char:
            candidate_index += 1
    return candidate_index == len(candidate)


def _is_hash_bound_date_prefix_noise(
    candidate: str, accepted_signatures: set[str]
) -> bool:
    """Accept a cropped adjacent date only when the remaining label still matches.

    This is intentionally narrower than the normal OCR edit tolerance: it only
    recognizes a leading Chinese UI date marker and requires the suffix to be an
    exact accepted label or a one-glyph deletion from an accepted label. The
    caller additionally requires hash-bound visual evidence.
    """
    match = _LEADING_UI_DATE_RE.match(candidate)
    if match is None:
        return False
    label_candidate = candidate[match.end() :]
    if len(label_candidate) < 3 or any(char.isdigit() for char in label_candidate):
        return False
    for accepted in accepted_signatures:
        if any(char.isdigit() for char in accepted):
            continue
        if label_candidate == accepted:
            return True
        if len(accepted) - len(label_candidate) != 1:
            continue
        candidate_index = 0
        for char in accepted:
            if (
                candidate_index < len(label_candidate)
                and label_candidate[candidate_index] == char
            ):
                candidate_index += 1
        if candidate_index == len(label_candidate):
            return True
    return False


def _hash_bound_visual_override_is_valid(
    *,
    root: Path | None,
    visual_override: Mapping[str, Any],
    approved_text: str,
    operator_review: Mapping[str, Any],
) -> bool:
    """Verify that an operator-approved residual is bound to immutable pixels."""

    if root is None or not approved_text:
        return False
    override = dict(visual_override)
    operator = dict(operator_review)
    proposal_sha256 = str(
        override.get("batch_decision_proposal_sha256") or ""
    )
    if (
        str(override.get("policy_version") or "")
        != "phase2_operator_visual_override_v1"
        or len(proposal_sha256) != 64
        or len(str(override.get("cluster_evidence_sha256") or "")) != 64
        or str(override.get("approved_source_text_sha256") or "")
        != hashlib.sha256(approved_text.encode("utf-8")).hexdigest()
        or str(operator.get("decision") or "").upper()
        not in {"APPROVE", "EDIT"}
        or not str(operator.get("reviewer") or "").strip()
        or not str(operator.get("reviewed_at") or "").strip()
        or str(operator.get("proposal_sha256") or "") != proposal_sha256
    ):
        return False

    resolved_root = root.resolve()
    for key in ("source_frame_ref", "crop_ref"):
        ref = dict(override.get(key) or {})
        evidence_path = (resolved_root / str(ref.get("path") or "")).resolve()
        if (
            not evidence_path.is_relative_to(resolved_root)
            or not evidence_path.is_file()
            or hashlib.sha256(evidence_path.read_bytes()).hexdigest()
            != str(ref.get("sha256") or "")
        ):
            return False
    return True


def _bind_operator_approved_residual_provenance(
    *,
    root: Path,
    occurrence: Mapping[str, Any],
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Make a reviewed additive residual localizable without guessing provenance.

    Generic rows with missing provenance still fail closed. Only a remediation
    whose operator decision, proposal hash, approved text hash and image hashes
    all agree is promoted to an editor overlay.
    """

    bound = dict(occurrence)
    approved_text = str(authority.get("ocr_text_approved") or "").strip()
    visual_override = dict(authority.get("visual_override") or {})
    operator = dict(authority.get("operator_review") or {})
    if not _hash_bound_visual_override_is_valid(
        root=root,
        visual_override=visual_override,
        approved_text=approved_text,
        operator_review=operator,
    ):
        raise RuntimeError(
            "Residual visual override authority is stale for "
            f"{str(bound.get('text_id') or 'unknown')}"
        )
    bound["visual_provenance"] = {
        "classification": "EDITOR_OVERLAY",
        "confidence": 1.0,
        "policy_version": "phase2_hash_bound_residual_editor_provenance_v1",
        "reasons": [
            "operator_approved_additive_residual",
            "proposal_and_visual_evidence_hashes_verified",
        ],
        "authority": {
            "proposal_sha256": visual_override.get(
                "batch_decision_proposal_sha256"
            ),
            "cluster_evidence_sha256": visual_override.get(
                "cluster_evidence_sha256"
            ),
            "approved_source_text_sha256": visual_override.get(
                "approved_source_text_sha256"
            ),
        },
    }
    return bound


def _configure_stdout_utf8() -> None:
    """Keep CJK OCR previews printable on the Windows console."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _parse_cli_args(args: list[str]) -> tuple[list[str], str]:
    positional: list[str] = []
    provider_mode = "local"
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--mock":
            provider_mode = "mock"
            index += 1
            continue
        if arg == "--provider":
            if index + 1 >= len(args):
                raise ValueError("--provider requires local, cloud, or mock")
            provider_mode = str(args[index + 1]).strip().lower()
            if provider_mode not in {"local", "cloud", "mock"}:
                raise ValueError("--provider must be local, cloud, or mock")
            index += 2
            continue
        positional.append(arg)
        index += 1
    return positional, provider_mode


def _resolve_provider_endpoint(provider_mode: str) -> str | None:
    mode = str(provider_mode or "local").strip().lower()
    if mode == "mock":
        return None
    if mode == "local":
        return (
            os.environ.get(LOCAL_OCR_ENDPOINT_ENV, "").strip()
            or DEFAULT_LOCAL_OCR_ENDPOINT
        )
    if mode == "cloud":
        from src.media_pipeline.ocr_filtering.providers import (
            resolve_ocr_endpoint_url,
        )

        return resolve_ocr_endpoint_url()
    raise ValueError(f"Unsupported OCR provider mode: {provider_mode}")


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _load_content_map(
    path: Path,
    *,
    list_key: str,
    value_key: str | None = None,
    expected_phase1_sha256: str | None = None,
) -> dict[str, object]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if expected_phase1_sha256:
        recorded_hash = str(
            ((payload.get("phase1_ref") or {}).get("sha256") if isinstance(payload, dict) else "")
            or ""
        )
        if recorded_hash != str(expected_phase1_sha256):
            raise RuntimeError(
                f"Stale Phase 2 input {path.name}: Phase 1 SHA-256 mismatch"
            )
    rows = payload.get(list_key) if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    out: dict[str, object] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        content_id = str(row.get("content_id") or "").strip()
        if not content_id:
            continue
        out[content_id] = row.get(value_key) if value_key else row
    return out


def _load_residual_remediation(
    root: Path,
    *,
    master_timeline_path: Path,
    master_timeline: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, str],
]:
    """Load approved additive/geometry remediation without mutating Phase 1."""
    try:
        path = resolve_active_residual_remediation(root)
    except ResidualRemediationAuthorityError as exc:
        raise RuntimeError(str(exc)) from exc
    if path is None:
        return [], {}, {}, {}
    from scripts.materialize_phase2_residual_remediation import (
        proposal_visual_override,
        verify_remediation,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not verify_remediation(payload):
        raise RuntimeError("Invalid Phase 2 residual remediation authority")
    master_hash = hashlib.sha256(master_timeline_path.read_bytes()).hexdigest()
    recorded_master_hash = str(
        dict(dict(payload.get("authority_refs") or {}).get("master_timeline") or {}).get(
            "sha256"
        )
        or ""
    )
    if recorded_master_hash != master_hash:
        raise RuntimeError("Residual remediation master authority is stale")
    proposal_rows: dict[tuple[str, str], dict[str, Any]] = {}
    chain_payload = payload
    seen_parent_paths: set[Path] = set()
    while True:
        proposal_ref = dict(chain_payload.get("proposal_ref") or {})
        if not bool(proposal_ref.get("recovered")):
            proposal_path = (
                root / str(proposal_ref.get("path") or "")
            ).resolve()
            if (
                not proposal_path.is_relative_to(root)
                or not proposal_path.is_file()
                or hashlib.sha256(proposal_path.read_bytes()).hexdigest()
                != str(proposal_ref.get("file_sha256") or "")
            ):
                raise RuntimeError(
                    "Residual remediation proposal authority is stale"
                )
            proposal_payload = json.loads(
                proposal_path.read_text(encoding="utf-8")
            )
            if not isinstance(proposal_payload, dict):
                raise RuntimeError(
                    "Residual remediation proposal authority is invalid"
                )
            unsigned_proposal = dict(proposal_payload)
            claimed_proposal_sha = str(
                unsigned_proposal.pop("proposal_sha256", "") or ""
            )
            if (
                claimed_proposal_sha
                != str(proposal_ref.get("proposal_sha256") or "")
                or claimed_proposal_sha != _sha256_json(unsigned_proposal)
            ):
                raise RuntimeError(
                    "Residual remediation proposal self-hash is invalid"
                )
            for raw_row in list(proposal_payload.get("proposals") or []):
                if not isinstance(raw_row, Mapping):
                    continue
                proposal_row = dict(raw_row)
                remediation_id = str(
                    proposal_row.get("remediation_id") or ""
                )
                if remediation_id:
                    proposal_rows[(claimed_proposal_sha, remediation_id)] = (
                        proposal_row
                    )

        parent_ref = dict(
            dict(chain_payload.get("authority_refs") or {}).get(
                "parent_remediation"
            )
            or {}
        )
        if not parent_ref:
            break
        parent_path = (root / str(parent_ref.get("path") or "")).resolve()
        if (
            parent_path in seen_parent_paths
            or not parent_path.is_relative_to(root)
            or not parent_path.is_file()
            or hashlib.sha256(parent_path.read_bytes()).hexdigest()
            != str(parent_ref.get("sha256") or "")
        ):
            raise RuntimeError("Residual remediation parent authority is stale")
        seen_parent_paths.add(parent_path)
        parent_payload = json.loads(parent_path.read_text(encoding="utf-8"))
        if (
            not isinstance(parent_payload, dict)
            or not verify_remediation(parent_payload)
            or str(parent_payload.get("remediation_sha256") or "")
            != str(parent_ref.get("remediation_sha256") or "")
        ):
            raise RuntimeError("Residual remediation parent self-hash is invalid")
        chain_payload = parent_payload

    existing_ids = {
        str(row.get("text_id") or "")
        for row in master_timeline
        if str(row.get("text_id") or "")
    }
    occurrences: list[dict[str, Any]] = []
    geometry_overrides: dict[str, dict[str, Any]] = {}
    authority_by_text_id: dict[str, dict[str, Any]] = {}
    visual_probe_geometries: dict[str, tuple[dict[str, float], str]] = {}
    visual_ref = dict(dict(payload.get("authority_refs") or {}).get("visual_triage") or {})
    visual_relative = str(visual_ref.get("path") or "")
    if visual_relative:
        batch_root = root.parent.resolve()
        visual_path = (batch_root / visual_relative).resolve()
        if (
            not visual_path.is_relative_to(batch_root)
            or not visual_path.is_file()
            or hashlib.sha256(visual_path.read_bytes()).hexdigest()
            != str(visual_ref.get("sha256") or "")
        ):
            raise RuntimeError("Residual remediation visual triage authority is stale")
        visual_payload = json.loads(visual_path.read_text(encoding="utf-8"))
        unsigned_visual = dict(visual_payload)
        claimed_visual_hash = str(unsigned_visual.pop("triage_sha256", "") or "")
        if (
            claimed_visual_hash != str(visual_ref.get("triage_sha256") or "")
            or claimed_visual_hash != _sha256_json(unsigned_visual)
        ):
            raise RuntimeError("Residual remediation visual triage self-hash is invalid")
        for raw_cluster in list(visual_payload.get("clusters") or []):
            if not isinstance(raw_cluster, Mapping):
                continue
            cluster = dict(raw_cluster)
            cluster_id = str(cluster.get("cluster_id") or "")
            detections = [
                dict(value)
                for value in list(cluster.get("detections") or [])
                if isinstance(value, Mapping)
            ]
            if not cluster_id or not detections:
                continue
            detector = max(
                detections, key=lambda value: float(value.get("confidence") or 0.0)
            )
            geometry = dict(detector.get("geometry") or {})
            try:
                normalized = {
                    key: float(geometry[key])
                    for key in ("x", "y", "width", "height")
                }
            except (KeyError, TypeError, ValueError):
                continue
            if (
                normalized["x"] < 0.0
                or normalized["y"] < 0.0
                or normalized["width"] <= 0.0
                or normalized["height"] <= 0.0
                or normalized["x"] + normalized["width"] > 1.0
                or normalized["y"] + normalized["height"] > 1.0
            ):
                continue
            visual_probe_geometries[cluster_id] = (
                normalized,
                _sha256_json(cluster),
            )
    for raw in list(payload.get("approved_occurrences") or []):
        if not isinstance(raw, Mapping):
            raise RuntimeError("Residual remediation contains an invalid occurrence")
        row = dict(raw)
        occurrence = dict(row.get("occurrence") or {})
        text_id = str(occurrence.get("text_id") or "").strip()
        approved_text = str(row.get("ocr_text_approved") or "").strip()
        render_text = str(row.get("vi_text_approved") or "").strip()
        if (
            not text_id
            or text_id in existing_ids
            or text_id in authority_by_text_id
            or not approved_text
            or not render_text
        ):
            raise RuntimeError("Residual remediation occurrence is unsafe")
        for key in ("best_keyframe_path", "crop_path"):
            evidence = (root / str(occurrence.get(key) or "")).resolve()
            if not evidence.is_relative_to(root) or not evidence.is_file():
                raise RuntimeError("Residual remediation evidence is missing")
        visual_override = dict(row.get("visual_override") or {})
        review_proposal_sha = str(
            dict(row.get("operator_review") or {}).get("proposal_sha256") or ""
        )
        proposal_row = proposal_rows.get((review_proposal_sha, text_id))
        if not visual_override and proposal_row is not None:
            visual_override = proposal_visual_override(
                proposal_row,
                proposal_sha256=review_proposal_sha,
            )
            if visual_override:
                row["visual_override"] = visual_override
        occurrence = _bind_operator_approved_residual_provenance(
            root=root,
            occurrence=occurrence,
            authority=row,
        )
        cluster_id = str(visual_override.get("cluster_id") or "")
        probe = visual_probe_geometries.get(cluster_id)
        if (
            probe is not None
            and probe[1]
            == str(visual_override.get("cluster_evidence_sha256") or "")
        ):
            occurrence["ocr_probe_geometry"] = probe[0]
            occurrence["ocr_probe_authority"] = {
                "policy_version": "phase2_hash_bound_detector_probe_v1",
                "cluster_id": cluster_id,
                "cluster_evidence_sha256": probe[1],
            }
        occurrences.append(occurrence)
        authority_by_text_id[text_id] = row
    master_by_id = {
        str(row.get("text_id") or ""): dict(row)
        for row in master_timeline
        if str(row.get("text_id") or "")
    }
    for raw in list(payload.get("approved_geometry_overrides") or []):
        if not isinstance(raw, Mapping):
            raise RuntimeError("Residual remediation contains an invalid override")
        row = dict(raw)
        override = dict(row.get("geometry_override") or {})
        text_id = str(override.get("target_text_id") or "").strip()
        master_row = master_by_id.get(text_id)
        coords = list(override.get("box_coords") or [])
        original = list(override.get("original_box_coords") or [])
        if (
            not text_id
            or master_row is None
            or text_id in geometry_overrides
            or text_id in authority_by_text_id
            or len(coords) != 4
            or original != list(master_row.get("box_coords") or [])
            or int(override.get("start_frame") or -1)
            != int(master_row.get("start_frame") or 0)
            or int(override.get("end_frame") or -1)
            != int(master_row.get("end_frame") or 0)
        ):
            raise RuntimeError("Residual remediation geometry override is unsafe")
        for key in ("best_keyframe_path", "crop_path"):
            evidence = (root / str(override.get(key) or "")).resolve()
            if not evidence.is_relative_to(root) or not evidence.is_file():
                raise RuntimeError("Residual remediation evidence is missing")
        geometry_overrides[text_id] = override
        authority_by_text_id[text_id] = row
    if not occurrences and not geometry_overrides:
        raise RuntimeError("Residual remediation has no approved changes")
    remediation_ref = {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "remediation_sha256": str(payload.get("remediation_sha256") or ""),
    }
    return occurrences, geometry_overrides, authority_by_text_id, remediation_ref


def _remediation_approvals(
    contract: Mapping[str, Any],
    authority_by_text_id: Mapping[str, Mapping[str, Any]],
    *,
    root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    enrichments = {
        str(row.get("text_id") or ""): dict(row)
        for row in list(contract.get("track_enrichments") or [])
        if isinstance(row, Mapping)
    }
    contents = {
        str(row.get("content_id") or ""): dict(row)
        for row in list(contract.get("content_objects") or [])
        if isinstance(row, Mapping)
    }
    approvals: dict[str, dict[str, Any]] = {}
    for text_id, authority_raw in authority_by_text_id.items():
        authority = dict(authority_raw)
        operator = dict(authority.get("operator_review") or {})
        content_id = str(dict(enrichments.get(text_id) or {}).get("content_id") or "")
        content = dict(contents.get(content_id) or {})
        approved_text = str(authority.get("ocr_text_approved") or "").strip()
        candidate_text = str(content.get("ocr_text_candidate") or "").strip()
        accepted_signatures = {
            str(value)
            for value in list(authority.get("accepted_candidate_signatures") or [])
            if str(value)
        }
        exact_candidate = candidate_text == approved_text
        accepted_operator_edit = (
            not exact_candidate
            and (
                _ocr_signature(candidate_text) in accepted_signatures
                or any(
                    _is_single_deletion_variant(
                        _ocr_signature(candidate_text), accepted
                    )
                    for accepted in accepted_signatures
                )
            )
        )
        geometry_only_carry_forward = bool(authority.get("geometry_override")) and str(
            dict(authority.get("localization") or {}).get("mode") or ""
        ) == "translation_carry_forward_exact"
        if geometry_only_carry_forward:
            # A geometry delta changes only the cover rectangle. Its text and
            # translation were already hash-bound to the prior approved Phase
            # 3 row; a fresh OCR sample from a transition frame must not turn
            # that visual-only operation into a new text decision.
            accepted_operator_edit = True
        visual_override = dict(authority.get("visual_override") or {})
        visual_override_accepted = False
        if (
            not exact_candidate
            and not accepted_operator_edit
            and root is not None
            and str(visual_override.get("policy_version") or "")
            == "phase2_operator_visual_override_v1"
        ):
            approved_digits = "".join(char for char in approved_text if char.isdigit())
            candidate_digits = "".join(char for char in candidate_text if char.isdigit())
            date_prefix_noise_safe = (
                not approved_digits
                and _is_hash_bound_date_prefix_noise(
                    _ocr_signature(candidate_text), accepted_signatures
                )
            )
            digit_shape_safe = (
                approved_digits == candidate_digits
                or not approved_digits
                and not candidate_digits
                or date_prefix_noise_safe
            )
            visual_override_accepted = (
                _hash_bound_visual_override_is_valid(
                    root=root,
                    visual_override=visual_override,
                    approved_text=approved_text,
                    operator_review=operator,
                )
                and digit_shape_safe
            )
        if not content_id or not (
            exact_candidate or accepted_operator_edit or visual_override_accepted
        ):
            raise RuntimeError(
                "Residual OCR candidate drift detected "
                f"for {text_id}: candidate={_ocr_signature(candidate_text)!r} "
                f"accepted={sorted(accepted_signatures)!r}"
            )
        approvals[content_id] = {
            "content_id": content_id,
            "decision": "APPROVE" if exact_candidate else "EDIT",
            "review_input_sha256": content.get("review_input_sha256"),
            "ocr_text_approved": approved_text,
            "vi_text_approved": authority.get("vi_text_approved"),
            "reviewer": operator.get("reviewer"),
            "reviewed_at": operator.get("reviewed_at"),
            **(
                {
                    "visual_override": {
                        "policy_version": visual_override.get("policy_version"),
                        "cluster_id": visual_override.get("cluster_id"),
                        "cluster_evidence_sha256": visual_override.get(
                            "cluster_evidence_sha256"
                        ),
                    }
                }
                if visual_override_accepted
                else {}
            ),
        }
    return approvals


def _apply_operator_approved_residual_text_authority(
    timeline: list[dict[str, Any]],
    authority_by_text_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Make hash-reviewed additive text authoritative after OCR/ASR alignment.

    A residual occurrence is re-OCRed to refresh geometry diagnostics, and the
    semantic hard-sub pass may also align it to ASR. Neither observation may
    replace text that the operator approved against hash-bound source pixels.
    Geometry-only overrides are deliberately excluded because their existing
    Phase-2 content authority already owns the text.
    """

    rebound: list[dict[str, Any]] = []
    for raw in timeline:
        row = dict(raw)
        text_id = str(row.get("text_id") or "").strip()
        authority = dict(authority_by_text_id.get(text_id) or {})
        approved_text = str(authority.get("ocr_text_approved") or "").strip()
        is_additive = bool(dict(authority.get("occurrence") or {}))
        if not text_id or not approved_text or not is_additive:
            rebound.append(row)
            continue
        observed_text = str(
            row.get("ocr_text_raw")
            or row.get("ocr_text")
            or row.get("text")
            or ""
        ).strip()
        semantic = dict(row.get("semantic_hardsub") or {})
        previous_authority = str(
            semantic.get("canonical_text_authority")
            or semantic.get("text_authority")
            or ""
        ).strip()
        semantic.update(
            {
                "ocr_text_observed": observed_text,
                "pre_review_text_authority": previous_authority or None,
                "canonical_text_authority": approved_text,
                "text_authority": approved_text,
                "operator_approved_text_authority": {
                    "policy_version": "phase2_hash_bound_residual_text_authority_v1",
                    "remediation_id": str(
                        authority.get("remediation_id") or text_id
                    ),
                    "proposal_sha256": str(
                        dict(authority.get("operator_review") or {}).get(
                            "proposal_sha256"
                        )
                        or ""
                    ),
                    "approved_source_text_sha256": hashlib.sha256(
                        approved_text.encode("utf-8")
                    ).hexdigest(),
                },
            }
        )
        row["semantic_hardsub"] = semantic
        rebound.append(row)
    return rebound


def _carry_forward_transient_ocr_failures(
    contract: Mapping[str, Any],
    approvals: Mapping[str, Mapping[str, Any]],
    *,
    remediated_text_ids: set[str],
) -> dict[str, dict[str, Any]]:
    """Rebind an unchanged approval when a retry returns no OCR candidate."""
    enrichments = {
        str(row.get("text_id") or ""): dict(row)
        for row in list(contract.get("track_enrichments") or [])
        if isinstance(row, Mapping)
    }
    carried: dict[str, dict[str, Any]] = {}
    for raw in list(contract.get("content_objects") or []):
        if not isinstance(raw, Mapping):
            continue
        content = dict(raw)
        content_id = str(content.get("content_id") or "")
        refs = {
            str(value)
            for value in list(content.get("geometry_refs") or [])
            if str(value)
        }
        previous = dict(approvals.get(content_id) or {})
        previous_decision = str(previous.get("decision") or "").upper()
        source_preservation = previous_decision in {
            "REJECT_UI",
            "PRESERVE_SOURCE",
        }
        if (
            str(content.get("review_status") or "") != "OCR_REVIEW_STALE"
            or (
                str(content.get("ocr_text_candidate") or "").strip()
                and not source_preservation
            )
            or not refs
            or refs.intersection(remediated_text_ids)
            or previous_decision not in {"APPROVE", "EDIT", "REJECT_UI", "PRESERVE_SOURCE"}
            or (
                not source_preservation
                and not str(previous.get("ocr_text_approved") or "").strip()
            )
            or any(
                str(dict(enrichments.get(text_id) or {}).get("ocr_source") or "")
                != "failed"
                for text_id in refs
            )
        ):
            continue
        carried[content_id] = {
            **previous,
            "review_input_sha256": content.get("review_input_sha256"),
            "carry_forward": {
                "policy_version": (
                    "phase2_source_preservation_carry_v1"
                    if source_preservation
                    else "phase2_transient_ocr_failure_carry_v1"
                ),
                "reason": (
                    "unchanged_phase1_source_preservation_decision"
                    if source_preservation
                    else "unchanged_phase1_retry_returned_empty_ocr"
                ),
                "previous_review_input_sha256": previous.get(
                    "review_input_sha256"
                ),
            },
        }
    return carried


def _stable_semantic_identity(content: Mapping[str, Any]) -> dict[str, Any]:
    semantic = dict(content.get("semantic_hardsub") or {})
    return {
        key: semantic.get(key)
        for key in (
            "schema_version",
            "recipe_version",
            "cue_id",
            "classification",
            "action",
            "canonical_text_authority",
        )
    }


def _previous_phase2_handoff(root: Path) -> dict[str, Any]:
    """Resolve the exact Phase-2 handoff consumed by the current Phase 3.

    Phase 2 quarantines its previous generated handoff before writing a new
    preview.  Residual retries still need that hash-bound artifact to prove an
    unaffected source-preservation decision refers to the same geometry.
    """

    phase3_path = root / "phase3_render_handoff.json"
    phase3_candidates = [phase3_path]
    stale = root / "qa" / "stale"
    if stale.is_dir():
        phase3_candidates.extend(
            sorted(
                stale.glob("phase3_render_handoff_*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        )
    handoff_candidates = [root / "phase2_handoff.json"]
    if stale.is_dir():
        handoff_candidates.extend(
            sorted(
                stale.glob("phase2_handoff_*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        )
    for candidate in phase3_candidates:
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        ref = dict(payload.get("phase2_handoff_ref") or {})
        expected_sha = str(ref.get("sha256") or "")
        if len(expected_sha) != 64:
            continue
        for handoff_candidate in handoff_candidates:
            resolved = handoff_candidate.resolve()
            if (
                not resolved.is_relative_to(root)
                or not resolved.is_file()
                or hashlib.sha256(resolved.read_bytes()).hexdigest()
                != expected_sha
            ):
                continue
            try:
                handoff = json.loads(resolved.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(handoff, Mapping):
                return dict(handoff)
    return {}


def _carry_forward_unchanged_source_preservation(
    contract: Mapping[str, Any],
    approvals: Mapping[str, Mapping[str, Any]],
    *,
    root: Path,
    remediated_text_ids: set[str],
) -> dict[str, dict[str, Any]]:
    """Rebind source-preservation only from exact per-object evidence.

    Adding an unrelated residual changes the clip-wide semantic authority hash
    and consequently the review-input hash.  That is not content drift.  This
    carry path accepts only identical geometry, OCR text and stable semantic
    identity, and never carries a decision onto remediated geometry.
    """

    previous_handoff = _previous_phase2_handoff(root)
    previous_preserved = [
        dict(row)
        for row in list(previous_handoff.get("preserved_source_items") or [])
        if isinstance(row, Mapping)
    ]
    carried: dict[str, dict[str, Any]] = {}
    for raw in list(contract.get("content_objects") or []):
        if not isinstance(raw, Mapping):
            continue
        content = dict(raw)
        content_id = str(content.get("content_id") or "")
        refs = [str(value) for value in content.get("geometry_refs") or [] if str(value)]
        if (
            not content_id
            or str(content.get("review_status") or "") != "OCR_REVIEW_STALE"
            or not refs
            or set(refs).intersection(remediated_text_ids)
        ):
            continue

        previous = dict(approvals.get(content_id) or {})
        if str(previous.get("decision") or "").upper() not in {
            "REJECT_UI",
            "PRESERVE_SOURCE",
        }:
            continue

        current_evidence = {
            "geometry_refs": refs,
            "ocr_text_candidate": str(content.get("ocr_text_candidate") or ""),
            "provenance_classifications": [
                str(value)
                for value in content.get("provenance_classifications") or []
            ],
            "semantic_identity": _stable_semantic_identity(content),
        }
        recorded_evidence = dict(previous.get("review_evidence") or {})
        evidence_source = "phase2_approval_review_evidence_v1"
        if not recorded_evidence:
            matches = [
                row
                for row in previous_preserved
                if [str(value) for value in row.get("geometry_refs") or []] == refs
                and str(row.get("content_id") or "") == content_id
            ]
            if len(matches) != 1:
                continue
            old = matches[0]
            old_semantic = dict(old.get("semantic_hardsub") or {})
            recorded_evidence = {
                "geometry_refs": refs,
                "ocr_text_candidate": str(
                    old.get("zh_approved")
                    or old_semantic.get("canonical_text_authority")
                    or previous.get("ocr_text_approved")
                    or ""
                ),
                "provenance_classifications": [
                    str(old_semantic.get("classification") or "")
                ],
                "semantic_identity": _stable_semantic_identity(old),
            }
            evidence_source = "hash_bound_previous_phase2_handoff_v1"

        # Older handoffs carry only the canonical semantic classification,
        # while new approval evidence records the complete provenance list.
        recorded_classes = [
            value
            for value in list(recorded_evidence.get("provenance_classifications") or [])
            if str(value)
        ]
        current_classes = current_evidence["provenance_classifications"]
        classes_match = (
            recorded_classes == current_classes
            or len(recorded_classes) == 1
            and recorded_classes[0]
            == str(current_evidence["semantic_identity"].get("classification") or "")
        )
        if (
            list(recorded_evidence.get("geometry_refs") or []) != refs
            or str(recorded_evidence.get("ocr_text_candidate") or "")
            != current_evidence["ocr_text_candidate"]
            or dict(recorded_evidence.get("semantic_identity") or {})
            != current_evidence["semantic_identity"]
            or not classes_match
        ):
            continue

        carried[content_id] = {
            **previous,
            "review_input_sha256": content.get("review_input_sha256"),
            "review_evidence": current_evidence,
            "carry_forward": {
                "policy_version": "phase2_unchanged_source_preservation_v1",
                "reason": "unrelated_residual_changed_clip_wide_authority_hash",
                "evidence_source": evidence_source,
                "previous_review_input_sha256": previous.get(
                    "review_input_sha256"
                ),
            },
        }
    return carried


def _rebind_shifted_content_approvals(
    contract: Mapping[str, Any],
    approvals: Mapping[str, Mapping[str, Any]],
    *,
    remediated_text_ids: set[str],
) -> dict[str, dict[str, Any]]:
    """Rebind unchanged approval fossils after additive content-id shifts.

    ``ocr_content_NNN`` is a projection identifier, not semantic authority.
    Inserting a residual occurrence earlier on the timeline can renumber every
    later object.  Preserve an old approval only when its exact approved OCR
    text matches the new candidate, and never use this path for the newly
    remediated geometry (which has its own hash-bound authority).
    """

    approvals_by_text: dict[str, list[dict[str, Any]]] = {}
    for raw in approvals.values():
        previous = dict(raw)
        approved_text = str(previous.get("ocr_text_approved") or "").strip()
        if approved_text and str(previous.get("decision") or "").upper() in {
            "APPROVE",
            "EDIT",
        }:
            approvals_by_text.setdefault(approved_text, []).append(previous)

    rebound: dict[str, dict[str, Any]] = {}
    for raw in list(contract.get("content_objects") or []):
        if not isinstance(raw, Mapping):
            continue
        content = dict(raw)
        content_id = str(content.get("content_id") or "")
        refs = {
            str(value)
            for value in list(content.get("geometry_refs") or [])
            if str(value)
        }
        candidate = str(content.get("ocr_text_candidate") or "").strip()
        matches = approvals_by_text.get(candidate, [])
        if (
            not content_id
            or str(content.get("review_status") or "") != "OCR_REVIEW_STALE"
            or not candidate
            or refs.intersection(remediated_text_ids)
            or not matches
        ):
            continue
        previous = matches[0]
        rebound[content_id] = {
            **previous,
            "content_id": content_id,
            "review_input_sha256": content.get("review_input_sha256"),
            "carry_forward": {
                "policy_version": "phase2_content_identity_rebind_v1",
                "reason": "additive_residual_shifted_projection_content_id",
                "previous_content_id": previous.get("content_id"),
                "previous_review_input_sha256": previous.get(
                    "review_input_sha256"
                ),
            },
        }
    return rebound


def main(argv: list[str] | None = None) -> int:
    _configure_stdout_utf8()
    args, provider_mode = _parse_cli_args(
        list(sys.argv[1:] if argv is None else argv)
    )
    if not args:
        print(
            "Usage: python -m scripts.run_phase2_only "
            "[--provider local|cloud|mock] [--mock] "
            "<phase1_out_dir> [video.mp4]",
            flush=True,
        )
        return 2

    _load_env_file(API_ROOT / ".env")
    _load_env_file(API_ROOT.parents[1] / ".env")

    from src.media_pipeline.frame_sampling.master_phase1_extractor import (
        ocr_timeline_keyframes,
    )
    from src.media_pipeline.frame_sampling.phase2_ocr_contract import (
        PHASE2_PREPROCESSING_VERSION,
        _write_json_atomic,
        build_phase2_contract,
        sha256_file,
        write_phase2_artifacts,
    )

    root = Path(args[0]).resolve()
    timeline_path = root / "master_timeline.json"
    if not timeline_path.is_file():
        print(f"[FAIL] missing timeline: {timeline_path}", flush=True)
        return 1

    meta_path = root / "phase1_meta.json"
    meta: dict = {}
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    video = Path(args[1]) if len(args) > 1 else Path(str(meta.get("video") or ""))
    fps = float(meta.get("fps") or 30.0)
    frame_count = int(meta.get("frame_count") or 0)
    # Phase 1 may store analysis keyframes at proxy resolution while timeline
    # geometry remains in source-video pixels. Prefer the explicit source
    # raster contract and inspect a keyframe only for legacy artifacts.
    frame_w = int(meta.get("frame_width") or 0)
    frame_h = int(meta.get("frame_height") or 0)
    frames_dir = root / "frames"
    sample = next(iter(sorted(frames_dir.glob("*.jpg"))), None) if frames_dir.is_dir() else None
    if (frame_w <= 0 or frame_h <= 0) and sample is not None:
        import cv2

        img = cv2.imread(str(sample))
        if img is not None:
            frame_h, frame_w = int(img.shape[0]), int(img.shape[1])
    if frame_w <= 0 or frame_h <= 0:
        frame_w, frame_h = 1920, 1080

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("onnxruntime").setLevel(logging.ERROR)

    master_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    if not isinstance(master_timeline, list):
        raise RuntimeError("master_timeline.json must contain a list")
    current_phase1_sha256 = sha256_file(timeline_path)
    dialogue_authority = _load_semantic_dialogue_authority(
        root / "semantic_dialogue_authority.json",
        expected_phase1_sha256=current_phase1_sha256,
    )
    from src.media_pipeline.frame_sampling.phase1_geometry_review import (
        apply_phase1_geometry_materialization,
    )

    effective_phase1, phase1_geometry_review_ref = (
        apply_phase1_geometry_materialization(root, master_timeline)
    )
    supplemental, geometry_overrides, remediation_authority, remediation_ref = (
        _load_residual_remediation(
            root,
            master_timeline_path=timeline_path,
            master_timeline=master_timeline,
        )
    )
    timeline: list[dict[str, Any]] = []
    for raw in effective_phase1:
        row = dict(raw)
        text_id = str(row.get("text_id") or "")
        override = geometry_overrides.get(text_id)
        if override is not None:
            row.update(
                {
                    "box_coords": list(override.get("box_coords") or []),
                    "best_keyframe_path": override.get("best_keyframe_path"),
                    "crop_path": override.get("crop_path"),
                    "best_frame_index": override.get("best_frame_index"),
                    "geometry_remediation": {
                        "status": "OPERATOR_APPROVED_OVERRIDE",
                        "original_box_coords": list(
                            override.get("original_box_coords") or []
                        ),
                    },
                }
            )
        timeline.append(row)
    timeline.extend(supplemental)
    provenance_path = root / "visual_text_provenance_v2.json"
    provenance_payload: dict[str, Any] = {}
    provenance_by_id: dict[str, dict[str, Any]] = {}
    protected_source_by_id: dict[str, dict[str, Any]] = {}
    if provenance_path.is_file():
        provenance_payload = json.loads(provenance_path.read_text(encoding="utf-8"))
        phase1_ref = dict(provenance_payload.get("phase1_ref") or {})
        if str(phase1_ref.get("sha256") or "") != sha256_file(timeline_path):
            raise RuntimeError(
                "visual_text_provenance_v2.json is stale for master_timeline.json"
            )
        provenance_by_id = {
            str(row.get("text_id") or ""): dict(row)
            for row in list(provenance_payload.get("tracks") or [])
            if isinstance(row, Mapping) and str(row.get("text_id") or "")
        }
        protected_source_by_id = {
            str(row.get("text_id") or ""): dict(row)
            for row in list(provenance_payload.get("protected_source_tracks") or [])
            if isinstance(row, Mapping) and str(row.get("text_id") or "")
        }
    localizable_timeline: list[dict[str, Any]] = []
    protected_source_tracks: list[dict[str, Any]] = []
    coverage_path = root / "phase1_track_coverage_v2.json"
    coverage_by_id: dict[str, dict[str, Any]] = {}
    phase1_coverage_ref: dict[str, Any] = {}
    if coverage_path.is_file():
        coverage_payload = json.loads(coverage_path.read_text(encoding="utf-8"))
        if not isinstance(coverage_payload, Mapping):
            raise RuntimeError("phase1_track_coverage_v2.json must be an object")
        coverage_master_ref = dict(
            coverage_payload.get("master_timeline_ref") or {}
        )
        if str(coverage_master_ref.get("sha256") or "") != sha256_file(
            timeline_path
        ):
            raise RuntimeError(
                "phase1_track_coverage_v2.json is stale for master_timeline.json"
            )
        coverage_by_id = {
            str(item.get("text_id") or ""): dict(item)
            for item in list(coverage_payload.get("tracks") or [])
            if isinstance(item, Mapping) and str(item.get("text_id") or "")
        }
        phase1_coverage_ref = {
            "path": coverage_path.name,
            "sha256": sha256_file(coverage_path),
            "schema_version": coverage_payload.get("schema_version"),
            "policy_version": coverage_payload.get("policy_version"),
        }
    for raw in timeline:
        row = dict(raw)
        text_id = str(row.get("text_id") or "")
        provenance = dict(row.get("visual_provenance") or {})
        if text_id in provenance_by_id:
            provenance = {
                key: value
                for key, value in provenance_by_id[text_id].items()
                if key != "text_id"
            }
        if not provenance:
            # Missing provenance is never evidence that pixels were added by
            # an editor. Legacy rows fail closed until semantic dialogue or an
            # explicit operator/source authority classifies them.
            provenance = {
                "classification": "UNCERTAIN",
                "confidence": 0.0,
                "policy_version": "missing_provenance_fail_closed_v1",
                "reasons": ["missing_explicit_visual_provenance"],
            }
        row["visual_provenance"] = provenance
        if text_id in coverage_by_id:
            row["coverage_authority"] = dict(coverage_by_id[text_id])
        if text_id in protected_source_by_id:
            protected = dict(protected_source_by_id[text_id])
            provenance = dict(protected.get("visual_provenance") or provenance)
            protected_source_tracks.append(
                {
                    "text_id": text_id,
                    "start_frame": row.get("start_frame"),
                    "end_frame": row.get("end_frame"),
                    "box_coords": list(row.get("box_coords") or []),
                    "visual_provenance": provenance,
                    "action": "PRESERVE_SOURCE_PIXELS",
                    "source": "phase1_protected_source_partition",
                    "coverage_authority": dict(
                        coverage_by_id.get(text_id) or {}
                    ),
                }
            )
            continue
        # Uncertain tracks are preserve-only until an operator proves editor
        # provenance.  Localizing them would violate the source/editor boundary.
        if str(provenance.get("classification") or "") == "UNCERTAIN":
            protected_source_tracks.append(
                {
                    "text_id": text_id,
                    "start_frame": row.get("start_frame"),
                    "end_frame": row.get("end_frame"),
                    "box_coords": list(row.get("box_coords") or []),
                    "visual_provenance": provenance,
                    "action": "PRESERVE_SOURCE_PIXELS",
                    "source": "phase1_uncertain_fail_closed",
                    "coverage_authority": dict(
                        coverage_by_id.get(text_id) or {}
                    ),
                }
            )
            continue
        if str(provenance.get("classification") or "") in {
            "SOURCE_INTRINSIC",
            "SOURCE_INTRINSIC_PANEL",
            "PLATFORM_UI",
        }:
            protected_source_tracks.append(
                {
                    "text_id": text_id,
                    "start_frame": row.get("start_frame"),
                    "end_frame": row.get("end_frame"),
                    "box_coords": list(row.get("box_coords") or []),
                    "visual_provenance": provenance,
                    "action": "PRESERVE_SOURCE_PIXELS",
                    "coverage_authority": dict(
                        coverage_by_id.get(text_id) or {}
                    ),
                }
            )
            continue
        localizable_timeline.append(row)
    timeline = localizable_timeline
    endpoint_url = _resolve_provider_endpoint(provider_mode)
    model_version = (
        os.environ.get("LOCAL_OCR_MODEL_VERSION", "").strip()
        if provider_mode == "local"
        else os.environ.get("OCR_MODEL_VERSION", "").strip()
    ) or (
        "mock"
        if provider_mode == "mock"
        else "ppocrv6-medium-det-rec"
        if provider_mode == "local"
        else "paddleocr-endpoint-managed"
    )
    endpoint_fingerprint = (
        hashlib.sha256(str(endpoint_url).encode("utf-8")).hexdigest()[:12]
        if endpoint_url
        else "none"
    )
    cache_namespace = ":".join(
        (
            provider_mode,
            model_version,
            PHASE2_PREPROCESSING_VERSION,
            endpoint_fingerprint,
        )
    )
    print(f"[P2] root={root}", flush=True)
    print(f"[P2] video={video if video.is_file() else '(missing — crop-only OCR)'}", flush=True)
    print(
        f"[P2] tracks={len(timeline)} size={frame_w}x{frame_h} "
        f"ocr_mode={provider_mode}",
        flush=True,
    )

    t0 = time.perf_counter()
    timeline = ocr_timeline_keyframes(
        timeline,
        root_dir=root,
        prefer_mock=provider_mode == "mock",
        video_path=video if video.is_file() else None,
        frame_width=frame_w,
        frame_height=frame_h,
        endpoint_url=endpoint_url,
        cache_path=root / "qa" / "ocr_cache.json",
        cache_namespace=cache_namespace,
    )
    from src.media_pipeline.frame_sampling.phase2_local_recovery import (
        PHASE2_LOCAL_RECOVERY_POLICY_VERSION,
        PHASE2_TEMPORAL_SHADOW_POLICY_VERSION,
        reconcile_temporal_shadow_tracks,
        repeated_recovered_source_ui_indices,
    )

    timeline, temporal_shadow_audit = reconcile_temporal_shadow_tracks(
        timeline,
        frame_width=frame_w,
        frame_height=frame_h,
        fps=fps,
    )

    recovery_rows = [
        dict(row.get("ocr_recovery") or {})
        for row in timeline
        if dict(row.get("ocr_recovery") or {})
    ]
    geometry_recovery_rows = [
        dict(row.get("geometry_recovery") or {})
        for row in timeline
        if dict(row.get("geometry_recovery") or {})
    ]
    recovered_source_indices = repeated_recovered_source_ui_indices(
        timeline,
        frame_width=frame_w,
        frame_height=frame_h,
    )
    if recovered_source_indices:
        localizable_after_recovery: list[dict[str, Any]] = []
        for index, raw in enumerate(timeline):
            row = dict(raw)
            if index not in recovered_source_indices:
                localizable_after_recovery.append(row)
                continue
            provenance = {
                "classification": "SOURCE_INTRINSIC_PANEL",
                "confidence": 0.96,
                "policy_version": PHASE2_LOCAL_RECOVERY_POLICY_VERSION,
                "reasons": [
                    "repeated_short_ui_label_same_geometry",
                    "preserve_source_when_editor_provenance_is_ambiguous",
                ],
            }
            row["visual_provenance"] = provenance
            protected_source_tracks.append(
                {
                    "text_id": str(row.get("text_id") or ""),
                    "start_frame": row.get("start_frame"),
                    "end_frame": row.get("end_frame"),
                    "box_coords": list(row.get("box_coords") or []),
                    "visual_provenance": provenance,
                    "ocr_recovery": dict(row.get("ocr_recovery") or {}),
                    "action": "PRESERVE_SOURCE_PIXELS",
                }
            )
        timeline = localizable_after_recovery
    from src.media_pipeline.frame_sampling.semantic_hardsub_cues import (
        apply_semantic_hardsub_authority,
    )

    semantic_result = apply_semantic_hardsub_authority(
        timeline,
        dialogue_authority=dialogue_authority,
        fps=fps,
        frame_width=frame_w,
        frame_height=frame_h,
    )
    timeline = [dict(row) for row in semantic_result.timeline]
    if remediation_authority:
        timeline = _apply_operator_approved_residual_text_authority(
            timeline,
            remediation_authority,
        )
    protected_source_tracks.extend(
        dict(row) for row in semantic_result.protected_source_tracks
    )
    semantic_hardsub_summary = dict(semantic_result.summary)
    local_recovery_summary = {
        "policy_version": PHASE2_LOCAL_RECOVERY_POLICY_VERSION,
        "temporal_shadow_policy_version": PHASE2_TEMPORAL_SHADOW_POLICY_VERSION,
        "temporal_shadow_tracks_purged": len(temporal_shadow_audit),
        "temporal_shadow_audit": temporal_shadow_audit,
        "attempted_tracks": len(recovery_rows),
        "recovered_tracks": sum(
            str(row.get("status") or "")
            == "RECOVERED_FOR_OPERATOR_REVIEW"
            for row in recovery_rows
        ),
        "promoted_source_ui_tracks": len(recovered_source_indices),
        "editor_candidates_recovered": max(
            0,
            sum(
                str(row.get("status") or "")
                == "RECOVERED_FOR_OPERATOR_REVIEW"
                for row in recovery_rows
            )
            - len(recovered_source_indices),
        ),
        "unresolved_tracks": sum(
            str(row.get("status") or "") == "UNRESOLVED"
            for row in recovery_rows
        ),
        "prepared_inputs": sum(
            int(row.get("prepared_inputs") or 0) for row in recovery_rows
        ),
        "decoded_frames": len(
            {
                int(frame)
                for row in recovery_rows
                for frame in list(row.get("decoded_frames") or [])
            }
        ),
        "geometry_tracks_derived": sum(
            str(row.get("status") or "") == "LOCAL_DERIVED_TEMPORAL_CONSENSUS"
            for row in geometry_recovery_rows
        ),
        "geometry_tracks_fail_closed": sum(
            str(row.get("status") or "") == "UNRESOLVED_FAIL_CLOSED"
            for row in geometry_recovery_rows
        ),
    }
    non_text_noise_tracks: list[dict[str, Any]] = []
    filtered_timeline: list[dict[str, Any]] = []
    for raw in timeline:
        row = dict(raw)
        candidate = str(
            row.get("ocr_text_raw")
            or row.get("ocr_text")
            or row.get("text")
            or ""
        ).strip()
        if _is_symbol_dominant_non_text(candidate):
            non_text_noise_tracks.append(
                {
                    "text_id": str(row.get("text_id") or ""),
                    "ocr_text": candidate,
                    "action": "IGNORE_NON_TEXT_GLYPH",
                    "reason": "symbol_dominant_single_glyph",
                }
            )
            continue
        filtered_timeline.append(row)
    timeline = filtered_timeline
    approvals = _load_content_map(
        root / "phase2_approvals.json",
        list_key="approvals",
        expected_phase1_sha256=current_phase1_sha256,
    )
    llm_suggestions = _load_content_map(
        root / "phase2_llm_suggestions.json",
        list_key="suggestions",
        value_key="ocr_text_llm_suggested",
        expected_phase1_sha256=current_phase1_sha256,
    )
    contract = build_phase2_contract(
        timeline,
        phase1_timeline_path=timeline_path,
        provider_mode=provider_mode,
        model_version=model_version,
        preprocessing_version=PHASE2_PREPROCESSING_VERSION,
        approvals=approvals,
        llm_suggestions={
            key: str(value or "") for key, value in llm_suggestions.items()
        },
        phase1_geometry_review_ref=phase1_geometry_review_ref,
        residual_remediation_ref=remediation_ref or None,
        supplemental_occurrences=supplemental,
        geometry_overrides=geometry_overrides,
        protected_source_tracks=protected_source_tracks,
        phase1_coverage_ref=phase1_coverage_ref or None,
        semantic_hardsub_summary=semantic_hardsub_summary,
        fps=fps,
        frame_width=frame_w,
        frame_height=frame_h,
    )
    contract["local_recovery_summary"] = dict(local_recovery_summary)
    if remediation_authority:
        shifted_rebind = _rebind_shifted_content_approvals(
            contract,
            approvals,
            remediated_text_ids=set(remediation_authority),
        )
        transient_carry = _carry_forward_transient_ocr_failures(
            contract,
            approvals,
            remediated_text_ids=set(remediation_authority),
        )
        source_preservation_carry = _carry_forward_unchanged_source_preservation(
            contract,
            approvals,
            root=root,
            remediated_text_ids=set(remediation_authority),
        )
        approvals = {
            **approvals,
            **shifted_rebind,
            **transient_carry,
            **source_preservation_carry,
            **_remediation_approvals(
                contract,
                remediation_authority,
                root=root,
            ),
        }
        contract = build_phase2_contract(
            timeline,
            phase1_timeline_path=timeline_path,
            provider_mode=provider_mode,
            model_version=model_version,
            preprocessing_version=PHASE2_PREPROCESSING_VERSION,
            approvals=approvals,
            llm_suggestions={
                key: str(value or "") for key, value in llm_suggestions.items()
            },
            phase1_geometry_review_ref=phase1_geometry_review_ref,
            residual_remediation_ref=remediation_ref,
            supplemental_occurrences=supplemental,
            geometry_overrides=geometry_overrides,
            protected_source_tracks=protected_source_tracks,
            phase1_coverage_ref=phase1_coverage_ref or None,
            semantic_hardsub_summary=semantic_hardsub_summary,
            fps=fps,
            frame_width=frame_w,
            frame_height=frame_h,
        )
        contract["local_recovery_summary"] = dict(local_recovery_summary)
    if frame_count <= 0 and timeline:
        frame_count = max(int(e.get("end_frame") or 0) for e in timeline) + 1
    artifact_paths = write_phase2_artifacts(
        root_dir=root,
        contract=contract,
        phase1_timeline=timeline,
        fps=fps,
        frame_count=frame_count,
        frame_width=frame_w,
        frame_height=frame_h,
    )
    (root / "qa").mkdir(parents=True, exist_ok=True)
    review_summary = dict(contract.get("review_summary") or {})
    local_recovery_summary = dict(contract.get("local_recovery_summary") or {})
    content_objects = list(contract.get("content_objects") or [])
    handoff_preview = json.loads(
        artifact_paths["handoff_preview"].read_text(encoding="utf-8")
    )
    summary = {
        "phase": 2,
        "schema_version": contract.get("schema_version"),
        "root": str(root),
        "video": str(video) if video else None,
        "tracks": len(master_timeline),
        "localizable_tracks": len(timeline),
        "protected_source_tracks": len(protected_source_tracks),
        "provenance_counts": dict(provenance_payload.get("counts") or {}),
        "provenance_artifact": (
            "visual_text_provenance_v2.json" if provenance_path.is_file() else None
        ),
        "ocr_ok": sum(1 for e in timeline if str(e.get("ocr_text") or "").strip()),
        "content_objects": len(content_objects),
        "translate_ready": sum(
            1 for item in content_objects if item.get("ready_for_translation")
        ),
        "deterministic_ready": sum(
            1
            for item in content_objects
            if item.get("review_status") == "OCR_APPROVED"
            and (item.get("localization") or {}).get("mode") == "deterministic"
        ),
        "review_required": int(review_summary.get("unresolved") or 0),
        "non_text_noise_tracks": len(non_text_noise_tracks),
        "status": review_summary.get("status"),
        "handoff_status": handoff_preview.get("status"),
        "ready_for_phase3": handoff_preview.get("status")
        == "READY_FOR_PHASE3",
        "ocr_mode": provider_mode,
        "model_version": model_version,
        "phase1_ref": contract.get("phase1_ref"),
        "phase1_geometry_review_ref": contract.get(
            "phase1_geometry_review_ref"
        ),
        "residual_remediation_ref": contract.get("residual_remediation_ref"),
        "review_summary": review_summary,
        "local_recovery_summary": local_recovery_summary,
        "semantic_hardsub_summary": semantic_hardsub_summary,
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "timeline_path": str(timeline_path),
        "phase2_timeline_path": str(artifact_paths["phase2_timeline"]),
        "review_queue_path": str(artifact_paths["review_queue"]),
        "preview_payload_path": str(artifact_paths["preview_payload"]),
        "ocr_payload_path": (
            str(artifact_paths["final_payload"])
            if artifact_paths["final_payload"].is_file()
            else None
        ),
        "phase2_handoff_path": (
            str(artifact_paths["phase2_handoff"])
            if artifact_paths["phase2_handoff"].is_file()
            else None
        ),
        "ocr_inputs_dir": str(root / "qa" / "ocr_inputs"),
        "ocr_cache_path": str(root / "qa" / "ocr_cache.json"),
    }
    _write_json_atomic(root / "phase2_meta.json", summary)
    _write_json_atomic(root / "qa" / "phase2_summary.json", summary)

    print(
        f"[P2] DONE elapsed_s={summary['elapsed_s']} "
        f"ocr_ok={summary['ocr_ok']}/{summary['tracks']} "
        f"content={summary['content_objects']} "
        f"review_required={summary['review_required']} "
        f"status={summary['status']} "
        f"handoff={summary['handoff_status']}",
        flush=True,
    )
    for item in content_objects[:8]:
        print(
            f"  {item.get('content_id')}: {item.get('ocr_text_candidate')!r} "
            f"status={item.get('review_status')} "
            f"geometry={len(item.get('geometry_refs') or [])}",
            flush=True,
        )
    if len(content_objects) > 8:
        print(f"  ... +{len(content_objects) - 8} content objects", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
