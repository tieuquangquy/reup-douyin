"""Finalize source-scene epoch and bounded editor-caption residual covers."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.media_pipeline.video_renderer.visual_remediation import (
    ACTIVE_POINTER_NAME,
    _sha256_json,
    apply_visual_remediation,
    load_active_visual_remediation,
)


# v13 closes the transition gap found in product review. The next editor
# caption begins at frame 185, but an earlier remediation moved its cover to
# frame 188; that left the original Chinese caption visible for one frame.
# The caption ROI is also widened to include the leftmost glyph without
# touching the filmed phone/UI plane.
POLICY_VERSION = "phase4_source_text_provenance_finalization_v14"

EDITOR_CAPTION_COVER_OVERRIDES: dict[str, dict[str, Any]] = {
    "sub_20": {
        "roi": {"x": 0.0, "y": 0.06, "width": 0.36, "height": 0.10},
        "mask_mode": "editor_caption_stylized_components",
    },
    "sub_11": {
        "roi": {"x": 0.20, "y": 0.89, "width": 0.60, "height": 0.11},
        "mask_mode": "ink_components",
    },
    "sub_21": {
        "roi": {"x": 0.23, "y": 0.89, "width": 0.40, "height": 0.11},
        "mask_mode": "editor_caption_stylized_components",
    },
    "sub_28": {
        "roi": {"x": 0.16, "y": 0.89, "width": 0.64, "height": 0.11},
        "mask_mode": "editor_caption_stylized_components",
    },
}

EDITOR_CAPTION_SUPPLEMENTAL_COVERS: dict[str, dict[str, Any]] = {
    "sub_20__right_glyph_cover": {
        "parent_text_id": "sub_20",
        "geometry": {"x": 0.405, "y": 0.07, "width": 0.05, "height": 0.06},
        "mask_mode": "full_roi_plate",
        "strategy": "gaussian_blur_plate_v1",
    },
    # On an already-materialized v12 case sub_28 starts at frame 188. This
    # bounded cover-only track handles frames 185-187, including the single
    # transition frame where the source Chinese caption flashes before the
    # Vietnamese replacement becomes active.
    "sub_28__transition_cover": {
        "parent_text_id": "sub_28",
        "geometry": {"x": 0.16, "y": 0.89, "width": 0.64, "height": 0.11},
        "mask_mode": "editor_caption_stylized_components",
        "strategy": "adaptive_temporal_ink",
        "start_frame": 185,
        "end_frame": 187,
        "only_if_parent_misses_window": True,
    },
    # The source caption begins with two bright glyphs slightly outside the
    # representative OCR geometry. A tight spatial plate is safer than
    # expanding the whole caption lane and prevents a persistent CJK prefix.
    "sub_28__left_glyph_cover": {
        "parent_text_id": "sub_28",
        "geometry": {"x": 0.22, "y": 0.90, "width": 0.10, "height": 0.10},
        "mask_mode": "full_roi_plate",
        "strategy": "gaussian_blur_plate_v1",
        "start_frame": 188,
        "end_frame": 439,
    },
}


class ProvenanceFinalizationError(RuntimeError):
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
        raise ProvenanceFinalizationError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise ProvenanceFinalizationError(f"{path.name} must contain an object")
    return payload


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def materialize(
    *,
    case_root: str | Path,
    artifact_version: str = "v22_53",
    operator_id: str = "operator-auto-provenance-correction",
) -> dict[str, Any]:
    case = Path(case_root).resolve()
    input_path = case / "phase4_render_input.json"
    contract = _load(input_path)
    active = load_active_visual_remediation(case, contract_path=input_path)
    if active is None:
        raise ProvenanceFinalizationError("Active visual remediation is missing")
    parent, parent_ref = active
    existing_ref = dict(
        dict(parent.get("authority_refs") or {}).get("provenance_finalization")
        or {}
    )
    if existing_ref and str(existing_ref.get("policy_version") or "") == POLICY_VERSION:
        summary_path = case / str(existing_ref.get("summary_path") or "")
        if not summary_path.is_file():
            raise ProvenanceFinalizationError("Finalization authority is stale")
        return _load(summary_path)

    effective, effective_ref = apply_visual_remediation(
        case, contract, contract_path=input_path
    )
    if effective_ref != parent_ref:
        raise ProvenanceFinalizationError("Active remediation changed during finalization")
    tracks = {
        str(dict(row).get("text_id") or ""): dict(row)
        for row in list(effective.get("render_tracks") or [])
        if isinstance(row, Mapping)
    }
    cover_overrides = {
        track_id: {
            "roi": dict(dict(value).get("roi") or {}),
            "mask_mode": str(dict(value).get("mask_mode") or ""),
        }
        for track_id, value in EDITOR_CAPTION_COVER_OVERRIDES.items()
    }
    new_operations: list[dict[str, Any]] = []
    region = next(
        (
            dict(row)
            for row in list(effective.get("source_scene_text_regions") or [])
            if str(dict(row).get("region_id") or "") == "source_scene_plane_01"
        ),
        None,
    )
    if region is None:
        raise ProvenanceFinalizationError("Expanded source-scene plane is missing")
    replacement = dict(region)
    replacement["end_frame"] = max(int(region.get("end_frame") or -1), 1044)
    evidence = dict(replacement.get("evidence") or {})
    evidence["temporal_extension"] = {
        "status": "SOURCE_DEVICE_REAPPEARANCE_VERIFIED",
        "evidence_frame": 1020,
        "previous_end_frame": region.get("end_frame"),
        "extended_end_frame": replacement["end_frame"],
    }
    replacement["evidence"] = evidence
    new_operations.append(
        {
            "operation": "EXTEND_SOURCE_SCENE_TEXT_REGION",
            "region_id": region["region_id"],
            "expected_region_sha256": _sha256_json(region),
            "replacement_region": replacement,
            "expected_replacement_sha256": _sha256_json(replacement),
        }
    )
    for track_id, cover_override in cover_overrides.items():
        track = tracks.get(track_id)
        roles = {str(value) for value in list((track or {}).get("roles") or [])}
        if track is None or (
            str(track.get("kind") or "") != "hardsub" and "generic" not in roles
        ):
            raise ProvenanceFinalizationError(
                f"Editor-caption remediation target is invalid: {track_id}"
            )
        context_updates = {
            "editor_caption_residual_remediation": True,
            "source_scene_protection_exempt": True,
        }
        cover_updates = {
            "roi": dict(cover_override["roi"]),
            "mask_mode": cover_override["mask_mode"],
            "mask_dilate_radius_fraction": 0.25,
        }
        new_operations.append(
            {
                "operation": "POLICY_OVERRIDE",
                "target_text_id": track_id,
                "expected_track_sha256": _sha256_json(track),
                "context_updates": context_updates,
                "cover_updates": cover_updates,
            }
        )
    supplemental_covers: dict[str, dict[str, Any]] = {}
    for track_id, raw_spec in EDITOR_CAPTION_SUPPLEMENTAL_COVERS.items():
        spec = dict(raw_spec)
        parent_id = str(spec.get("parent_text_id") or "")
        parent_track = tracks.get(parent_id)
        if parent_track is None:
            raise ProvenanceFinalizationError(
                f"Supplemental editor-caption parent is missing: {parent_id}"
            )
        geometry = dict(spec.get("geometry") or {})
        supplemental = json.loads(json.dumps(parent_track))
        requested_start = int(spec.get("start_frame") or parent_track.get("start_frame") or 0)
        requested_end = int(spec.get("end_frame") or parent_track.get("end_frame") or 0)
        # Do not add a duplicate transition cover when a clean parent already
        # spans the requested window (important for fresh v13 materialization).
        if (
            bool(spec.get("only_if_parent_misses_window"))
            and requested_start >= int(parent_track.get("start_frame") or 0)
            and requested_end <= int(parent_track.get("end_frame") or 0)
        ):
            continue
        fps = float(dict(contract.get("video") or {}).get("fps") or 30.0)
        start_ms = int(round(requested_start * 1000.0 / fps))
        end_ms = int(round((requested_end + 1) * 1000.0 / fps))
        policy = dict(supplemental.get("render_policy") or {})
        context = dict(policy.get("context") or {})
        cover = dict(policy.get("cover") or {})
        layout = dict(policy.get("layout") or {})
        context.update(
            {
                "editor_caption_residual_remediation": True,
                "source_scene_protection_exempt": True,
                "supplemental_cover_only": True,
                "supplemental_cover_parent_text_id": parent_id,
            }
        )
        cover.update(
            {
                "roi": geometry,
                "mask_mode": str(spec.get("mask_mode") or "ink_components"),
                "strategy": str(spec.get("strategy") or "adaptive_temporal_ink"),
                "mask_dilate_radius_fraction": 0.02,
            }
        )
        layout.update({"safe_area": geometry, "max_lines": 1})
        policy.update(
            {
                "policy_version": "phase4_visual_remediation_v1",
                "context": context,
                "cover": cover,
                "layout": layout,
            }
        )
        supplemental.update(
            {
                "text_id": track_id,
                "content_id": parent_track.get("content_id"),
                "best_frame_index": int(parent_track.get("start_frame") or 0),
                "geometry": geometry,
                "start_frame": requested_start,
                "end_frame": requested_end,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "cover_only": True,
                "duplicate_transition_canonical": False,
                "render_policy": policy,
            }
        )
        existing_supplemental = tracks.get(track_id)
        if existing_supplemental is None:
            new_operations.append(
                {
                    "operation": "ADD_TRACK",
                    "track": supplemental,
                    "expected_added_track_sha256": _sha256_json(supplemental),
                }
            )
        else:
            # A prior failed/abandoned materialization may already contain the
            # same hash-bound supplemental track. Update it in place rather
            # than emitting a duplicate ADD_TRACK id.
            new_operations.append(
                {
                    "operation": "POLICY_OVERRIDE",
                    "target_text_id": track_id,
                    "expected_track_sha256": _sha256_json(existing_supplemental),
                    "context_updates": context,
                    "cover_updates": cover,
                    "layout_updates": layout,
                }
            )
        supplemental_covers[track_id] = {
            "parent_text_id": parent_id,
            "geometry": geometry,
            "mask_mode": cover["mask_mode"],
            "strategy": cover["strategy"],
        }
    finalization_key = _sha256_json(
        {
            "policy_version": POLICY_VERSION,
            "parent_materialization_sha256": parent_ref.get("materialization_sha256"),
            "operations": new_operations,
        }
    )
    summary_name = f"phase4_provenance_finalization_{artifact_version}.json"
    parent_authorities = dict(parent.get("authority_refs") or {})
    payload: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_v1",
        "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_id": str(operator_id).strip(),
        "authority_refs": {
            "phase4_input": dict(parent_authorities.get("phase4_input") or {}),
            "source_text_provenance": dict(
                parent_authorities.get("source_text_provenance") or {}
            ),
            "parent_visual_remediation": parent_ref,
            "provenance_finalization": {
                "policy_version": POLICY_VERSION,
                "finalization_key": finalization_key,
                "summary_path": summary_name,
            },
        },
        "operations": [
            dict(row)
            for row in list(parent.get("operations") or [])
            if isinstance(row, Mapping)
        ]
        + new_operations,
        "non_goals": [
            "do_not_translate_source_scene_text",
            "do_not_relax_ocr_damage_flicker_duration_frame_or_color_thresholds",
            "do_not_overwrite_master_timeline",
        ],
    }
    if not payload["operator_id"]:
        raise ProvenanceFinalizationError("operator_id is required")
    payload["materialization_sha256"] = _sha256_json(payload)
    artifact_name = (
        f"phase4_visual_remediation_{finalization_key[:12]}_provenance_final.json"
    )
    artifact_path = case / artifact_name
    _write(artifact_path, payload)
    pointer: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_pointer_v1",
        "status": "ACTIVE",
        "active_ref": {
            "path": artifact_name,
            "sha256": _sha256_file(artifact_path),
            "materialization_sha256": payload["materialization_sha256"],
        },
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    _write(case / ACTIVE_POINTER_NAME, pointer)
    # Any visual correction invalidates the approval bound to the previous
    # encoded video. Keep that state explicit so a stale approval cannot be
    # mistaken for approval of the new render.
    approval_path = case / "phase4_visual_approval.json"
    if approval_path.is_file():
        current_approval = _load(approval_path)
        if str(current_approval.get("status") or "") == "VISUAL_APPROVED":
            previous_sha = _sha256_file(approval_path)
            backup = case / f"phase4_visual_approval_{previous_sha[:12]}_superseded.json"
            if not backup.is_file():
                _write(backup, current_approval)
            superseded: dict[str, Any] = {
                "schema_version": "phase4_visual_approval_supersession_v1",
                "status": "VISUAL_APPROVAL_SUPERSEDED",
                "superseded_at": datetime.now(timezone.utc).isoformat(),
                "reason": "PRODUCT_REVIEW_FOUND_EDITOR_GLYPH_FLASH_AT_TRANSITION",
                "previous_approval_ref": {
                    "path": backup.name,
                    "sha256": previous_sha,
                },
                "superseded_by": pointer["active_ref"],
                "required_next_state": "RERENDER_AND_REAPPROVE_VISUAL",
            }
            superseded["supersession_sha256"] = _sha256_json(superseded)
            _write(approval_path, superseded)
    summary: dict[str, Any] = {
        "schema_version": "phase4_provenance_finalization_materialization_v1",
        "status": "PHASE4_PROVENANCE_FINALIZATION_MATERIALIZED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_id": case.name,
        "artifact_version": str(artifact_version),
        "policy_version": POLICY_VERSION,
        "visual_remediation_ref": pointer["active_ref"],
        "source_scene_extension": replacement,
        "editor_caption_cover_overrides": cover_overrides,
        "editor_caption_supplemental_covers": supplemental_covers,
    }
    summary["materialization_sha256"] = _sha256_json(summary)
    _write(case / summary_name, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.materialize_phase4_provenance_finalization"
    )
    parser.add_argument("case_root")
    parser.add_argument("--artifact-version", default="v22_53")
    parser.add_argument(
        "--operator-id", default="operator-auto-provenance-correction"
    )
    args = parser.parse_args()
    try:
        result = materialize(
            case_root=args.case_root,
            artifact_version=args.artifact_version,
            operator_id=args.operator_id,
        )
    except (OSError, ValueError, ProvenanceFinalizationError) as exc:
        print(f"[PHASE4-PROVENANCE-FINALIZATION][FAIL] {exc}", flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
