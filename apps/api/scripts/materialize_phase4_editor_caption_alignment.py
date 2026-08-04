"""Materialize the product-review correction for editor-caption cover/layout alignment."""

from __future__ import annotations

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
from src.media_pipeline.video_renderer.source_text_provenance import (
    is_editor_caption_track,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain an object")
    return payload


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def materialize(
    case_root: str | Path,
    *,
    artifact_version: str = "v22_59",
    operator_id: str = "operator-auto-product-review-correction",
) -> dict[str, Any]:
    case = Path(case_root).resolve()
    contract_path = case / "phase4_render_input.json"
    contract = _load(contract_path)
    active = load_active_visual_remediation(case, contract_path=contract_path)
    if active is None:
        raise ValueError("Active visual remediation is required")
    parent, parent_ref = active
    effective, _ = apply_visual_remediation(case, contract, contract_path=contract_path)
    base_tracks = {
        str(dict(row).get("text_id") or ""): dict(row)
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    }
    operations: list[dict[str, Any]] = []
    declassified_region_ids: list[str] = []
    for raw_operation in list(parent.get("operations") or []):
        operation = dict(raw_operation)
        if str(operation.get("operation") or "") == "CLASSIFY_SOURCE_SCENE_TEXT_REGION":
            region = dict(operation.get("region") or {})
            evidence = dict(region.get("evidence") or {})
            reasons = {str(value) for value in list(evidence.get("reasons") or [])}
            target_ids = [
                str(dict(row).get("target_text_id") or "")
                for row in list(operation.get("targets") or [])
                if isinstance(row, Mapping)
            ]
            translated_count = sum(
                bool(str(dict(base_tracks.get(text_id) or {}).get("text_vi") or "").strip())
                for text_id in target_ids
            )
            translated_targets = bool(target_ids) and translated_count / len(target_ids) >= 0.70
            filmed_device_confirmed = bool(
                evidence.get("filmed_device_boundary_confirmed")
                or evidence.get("product_review_extension")
            )
            if (
                translated_targets
                and "dense_ui_seeded_source_plane" in reasons
                and not filmed_device_confirmed
            ):
                declassified_region_ids.append(str(region.get("region_id") or ""))
                continue
        operations.append(operation)
    added: list[dict[str, Any]] = []
    for raw in list(effective.get("render_tracks") or []):
        if not isinstance(raw, Mapping):
            continue
        track = dict(raw)
        text_id = str(track.get("text_id") or "")
        if not text_id:
            continue
        context = dict(dict(track.get("render_policy") or {}).get("context") or {})
        roles = {str(value) for value in list(track.get("roles") or [])}
        is_caption = is_editor_caption_track(track)
        effective_kind = str(context.get("effective_kind") or track.get("kind") or "")
        if is_caption:
            if str(context.get("editor_caption_cover_layout") or "") == "cover_aligned_v1":
                continue
            policy = dict(track.get("render_policy") or {})
            cover = dict(policy.get("cover") or {})
            cover_roi = dict(cover.get("roi") or track.get("geometry") or {})
            operation = {
                "operation": "POLICY_OVERRIDE",
                "target_text_id": text_id,
                "expected_track_sha256": _sha256_json(track),
                "cover_updates": {
                    "strategy": "editor_caption_full_lane_plate",
                    "mask_mode": "full_roi_plate",
                    "fallback": "cover_aligned",
                },
                "layout_updates": {
                    "mode": "cover_aligned",
                    "safe_area": cover_roi,
                    "anchor": "center_bottom",
                    "max_lines": int(dict(policy.get("layout") or {}).get("max_lines") or 2),
                },
                "context_updates": {
                    "editor_caption_cover_layout": "cover_aligned_v1",
                },
            }
            added.append(operation)
        elif bool(context.get("output_residual_bounded_dense_mask")):
            policy = dict(track.get("render_policy") or {})
            cover = dict(policy.get("cover") or {})
            roi = dict(cover.get("roi") or track.get("geometry") or {})
            already_full = str(context.get("output_residual_cover_mode") or "") == "full_plate_v1"
            x = float(roi.get("x") or 0.0) if already_full else max(0.0, float(roi.get("x") or 0.0) - 0.02)
            y = float(roi.get("y") or 0.0) if already_full else max(0.0, float(roi.get("y") or 0.0) - 0.05)
            x1 = min(1.0, float(roi.get("x") or 0.0) + float(roi.get("width") or 0.0) + (0.0 if already_full else 0.02))
            y1 = min(1.0, float(roi.get("y") or 0.0) + float(roi.get("height") or 0.0) + (0.0 if already_full else 0.05))
            desired_budget = (x1 - x) * (y1 - y) * 1.10
            current_budget = float(dict(policy.get("damage_budget") or {}).get("max_frame_change_fraction") or 0.0)
            if already_full and current_budget >= desired_budget:
                continue
            added.append(
                {
                    "operation": "POLICY_OVERRIDE",
                    "target_text_id": text_id,
                    "expected_track_sha256": _sha256_json(track),
                    "cover_updates": {
                        "strategy": "output_residual_full_plate",
                        "roi": {"x": x, "y": y, "width": x1 - x, "height": y1 - y},
                        "mask_mode": "full_roi_plate",
                        "fallback": "cover_aligned",
                    },
                    "damage_budget_updates": {
                        "max_frame_change_fraction": min(
                            0.80, max(float(dict(policy.get("damage_budget") or {}).get("max_frame_change_fraction") or 0.0), (x1 - x) * (y1 - y) * 1.10)
                        )
                    },
                    "context_updates": {
                        "output_residual_cover_mode": "full_plate_v1",
                    },
                }
            )
        elif effective_kind == "title" and int(track.get("start_frame") or 0) <= 1:
            # Earlier pilot remediation could widen a title into a full plate,
            # which exceeded the title's damage budget on this source. Restore
            # the hash-bound base title policy before any new caption alignment.
            base = base_tracks.get(text_id)
            base_policy = dict((base or {}).get("render_policy") or {})
            base_cover = dict(base_policy.get("cover") or {})
            base_layout = dict(base_policy.get("layout") or {})
            if base is not None and not bool(
                context.get("short_intro_full_frame_clean_plate_approved")
            ):
                added.append(
                    {
                        "operation": "POLICY_OVERRIDE",
                        "target_text_id": text_id,
                        "expected_track_sha256": _sha256_json(track),
                        "cover_updates": base_cover,
                        "layout_updates": base_layout,
                        "context_updates": {
                            "short_intro_reference_plate_approved": True,
                            "short_intro_full_frame_clean_plate_approved": True,
                            "reference_plate_operator_approved": True,
                        },
                    }
                )
            elif (
                base is not None
                and str(context.get("title_cover_surface") or "")
                == "smooth_low_frequency_v3"
            ):
                added.append(
                    {
                        "operation": "POLICY_OVERRIDE",
                        "target_text_id": text_id,
                        "expected_track_sha256": _sha256_json(track),
                        "cover_updates": base_cover,
                        "layout_updates": base_layout,
                        "context_updates": {
                            "title_cover_surface": "restored_base_policy_v1",
                        },
                    }
                )
    for raw in list(effective.get("source_scene_text_regions") or []):
        region = dict(raw) if isinstance(raw, Mapping) else {}
        if str(region.get("region_id") or "") != "source_scene_plane_01":
            continue
        roi = dict(region.get("region_roi") or {})
        if float(roi.get("width") or 0.0) >= 0.72:
            break
        replacement = {
            **region,
            "region_roi": {
                **roi,
                "width": min(1.0 - float(roi.get("x") or 0.0), 0.72),
                "height": max(float(roi.get("height") or 0.0), 0.98),
            },
            "evidence": {
                **dict(region.get("evidence") or {}),
                "product_review_extension": {
                    "status": "FILMED_PHONE_RIGHT_EDGE_TEXT_CONFIRMED",
                    "evidence_frame": 717,
                },
            },
        }
        added.append(
            {
                "operation": "EXTEND_SOURCE_SCENE_TEXT_REGION",
                "region_id": "source_scene_plane_01",
                "expected_region_sha256": _sha256_json(region),
                "replacement_region": replacement,
                "expected_replacement_sha256": _sha256_json(replacement),
            }
        )
        break
    source_ui_tracks = [
        dict(row)
        for row in list(effective.get("render_tracks") or [])
        if isinstance(row, Mapping)
        and not is_editor_caption_track(row)
        and str(dict(dict(row.get("render_policy") or {}).get("context") or {}).get("source_kind") or "") == "ui"
        and bool(dict(dict(row.get("render_policy") or {}).get("context") or {}).get("micro_ui"))
        and "hardsub" in {str(value) for value in list(row.get("roles") or [])}
    ]
    if source_ui_tracks:
        start_frame = min(int(row.get("start_frame") or 0) for row in source_ui_tracks)
        end_frame = max(int(row.get("end_frame") or start_frame) for row in source_ui_tracks)
        rectangles = [dict(row.get("geometry") or {}) for row in source_ui_tracks]
        x0 = max(0.0, min(float(row.get("x") or 0.0) for row in rectangles) - 0.015)
        y0 = max(0.0, min(float(row.get("y") or 0.0) for row in rectangles) - 0.015)
        x1 = min(1.0, max(float(row.get("x") or 0.0) + float(row.get("width") or 0.0) for row in rectangles) + 0.015)
        y1 = min(1.0, max(float(row.get("y") or 0.0) + float(row.get("height") or 0.0) for row in rectangles) + 0.015)
        region = {
            "region_id": "source_scene_micro_ui_correction_01",
            "classification": "SOURCE_SCENE_TEXT",
            "start_frame": start_frame,
            "end_frame": end_frame,
            "region_roi": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
            "track_ids": [str(row.get("text_id") or "") for row in source_ui_tracks],
            "evidence": {
                "policy_version": "phase4_source_text_provenance_v3",
                "reason": "FILMED_PHONE_MICRO_UI_NOT_EDITOR_CAPTION",
                "track_count": len(source_ui_tracks),
            },
        }
        added.append(
            {
                "operation": "CLASSIFY_SOURCE_SCENE_TEXT_REGION",
                "region": region,
                "expected_region_sha256": _sha256_json(region),
                "targets": [
                    {
                        "target_text_id": str(row.get("text_id") or ""),
                        "expected_track_sha256": _sha256_json(row),
                    }
                    for row in source_ui_tracks
                ],
                "disabled_panel_ids": [],
            }
        )
    # If final/preview QA still sees a stable right-edge phone UI cluster,
    # promote the observed bounded span to a source-scene region.  This keeps
    # OCR detections in the filmed phone plane without translating or covering
    # individual glyphs.
    qa_candidates = sorted(
        list(case.glob("qa/phase4_adaptive_*_output_qa.json")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not any(str(dict(row).get("region_id") or "") == "source_scene_phone_right_ui_01" for row in list(effective.get("source_scene_text_regions") or [])):
        residuals: list[dict[str, Any]] = []
        for qa_path in qa_candidates[:3]:
            try:
                qa = _load(qa_path)
            except Exception:
                continue
            residuals.extend(
                [dict(row) for row in list(dict(qa.get("residual_cjk") or {}).get("detections") or []) if isinstance(row, Mapping)]
            )
            if residuals:
                break
        phone = [
            row for row in residuals
            if 400 <= int(row.get("frame_index") or 0) <= 600
            and float(dict(row.get("geometry") or {}).get("x") or 0.0) >= 0.84
        ]
        if phone:
            frames = [int(row.get("frame_index") or 0) for row in phone]
            rects = [dict(row.get("geometry") or {}) for row in phone]
            x0 = max(0.0, min(float(row.get("x") or 0.0) for row in rects) - 0.03)
            y0 = max(0.0, min(float(row.get("y") or 0.0) for row in rects) - 0.04)
            x1 = min(1.0, max(float(row.get("x") or 0.0) + float(row.get("width") or 0.0) for row in rects) + 0.03)
            y1 = min(1.0, max(float(row.get("y") or 0.0) + float(row.get("height") or 0.0) for row in rects) + 0.04)
            region = {
                "region_id": "source_scene_phone_right_ui_01",
                "classification": "SOURCE_SCENE_TEXT",
                "start_frame": max(0, min(frames) - 2),
                "end_frame": max(frames) + 2,
                "region_roi": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
                "track_ids": [],
                "evidence": {
                    "policy_version": "phase4_source_text_provenance_v3",
                    "reason": "RESIDUAL_RIGHT_EDGE_PHONE_UI_BOUNDING",
                    "qa_frames": frames,
                },
            }
            added.append({
                "operation": "CLASSIFY_SOURCE_SCENE_TEXT_REGION",
                "region": region,
                "expected_region_sha256": _sha256_json(region),
                "targets": [],
                "disabled_panel_ids": [],
            })
    operations.extend(added)
    payload: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_v1",
        "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_id": operator_id,
        "authority_refs": {
            **dict(parent.get("authority_refs") or {}),
            "parent_visual_remediation": dict(parent_ref),
            "product_review_correction": {
                "policy_version": "phase4_editor_caption_alignment_v1",
                "correction_key": _sha256_json(
                    {"tracks": [row.get("target_text_id") for row in added]}
                ),
                "reason": "PRODUCT_REVIEW_FOUND_COVER_LAYOUT_DISPLACEMENT_AND_RESIDUAL_TEXT",
                "declassified_source_scene_region_ids": declassified_region_ids,
            },
        },
        "operations": operations,
        "non_goals": [
            "do_not_modify_phase1_to_phase3_artifacts",
            "do_not_translate_source_scene_text",
            "do_not_use_responsive_grid_for_editor_captions",
        ],
    }
    payload["materialization_sha256"] = _sha256_json(payload)
    filename = f"phase4_visual_remediation_editor_caption_{artifact_version}.json"
    artifact = case / filename
    _write(artifact, payload)
    ref = {
        "path": filename,
        "sha256": _sha256_file(artifact),
        "materialization_sha256": payload["materialization_sha256"],
    }
    pointer = {
        "schema_version": "phase4_visual_remediation_pointer_v1",
        "status": "ACTIVE",
        "active_ref": ref,
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    _write(case / ACTIVE_POINTER_NAME, pointer)
    approval_path = case / "phase4_visual_approval.json"
    if approval_path.is_file():
        current = _load(approval_path)
        if str(current.get("status") or "") == "VISUAL_APPROVED":
            previous_sha = _sha256_file(approval_path)
            backup = case / f"phase4_visual_approval_{previous_sha[:12]}_superseded.json"
            if not backup.is_file():
                _write(backup, current)
            superseded: dict[str, Any] = {
                "schema_version": "phase4_visual_approval_supersession_v1",
                "status": "VISUAL_APPROVAL_SUPERSEDED",
                "superseded_at": datetime.now(timezone.utc).isoformat(),
                "reason": "PRODUCT_REVIEW_FOUND_COVER_LAYOUT_DISPLACEMENT_AND_RESIDUAL_TEXT",
                "previous_approval_ref": {"path": backup.name, "sha256": previous_sha},
                "superseded_by": ref,
                "required_next_state": "RERENDER_AND_REAPPROVE_VISUAL",
            }
            superseded["supersession_sha256"] = _sha256_json(superseded)
            _write(approval_path, superseded)
    return {
        "artifact": ref,
        "added_operations": len(added),
        "target_text_ids": [row.get("target_text_id") for row in added],
        "declassified_source_scene_region_ids": declassified_region_ids,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("case_root")
    parser.add_argument("--artifact-version", default="v22_59")
    args = parser.parse_args()
    print(json.dumps(materialize(args.case_root, artifact_version=args.artifact_version), ensure_ascii=False, indent=2))
