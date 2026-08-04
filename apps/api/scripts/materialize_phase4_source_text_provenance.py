"""Protect filmed device/UI text from Phase-4 translation and rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.media_pipeline.video_renderer.source_text_provenance import (
    SOURCE_SCENE_POLICY_VERSION,
    classify_source_scene_components,
)
from src.media_pipeline.video_renderer.visual_remediation import (
    ACTIVE_POINTER_NAME,
    _sha256_json,
    apply_visual_remediation,
    load_active_visual_remediation,
)


class SourceTextProvenanceMaterializationError(RuntimeError):
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
        raise SourceTextProvenanceMaterializationError(
            f"Cannot read valid {path.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise SourceTextProvenanceMaterializationError(
            f"{path.name} must contain an object"
        )
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _rect(raw: Mapping[str, Any], key: str) -> tuple[float, float, float, float]:
    roi = dict(raw.get(key) or {})
    x = float(roi.get("x") or 0.0)
    y = float(roi.get("y") or 0.0)
    return x, y, x + float(roi.get("width") or 0.0), y + float(
        roi.get("height") or 0.0
    )


def _overlap_over_smaller(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    intersection = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )
    smaller = min(
        max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1]),
        max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1]),
    )
    return intersection / smaller if smaller > 0.0 else 0.0


def _disabled_panel_ids(
    region: Mapping[str, Any], panels: Sequence[Mapping[str, Any]]
) -> list[str]:
    output: list[str] = []
    for raw in panels:
        panel = dict(raw)
        if (
            int(panel.get("end_frame") or -1)
            < int(region.get("start_frame") or 0)
            or int(panel.get("start_frame") or 0)
            > int(region.get("end_frame") or -1)
        ):
            continue
        if _overlap_over_smaller(
            _rect(region, "region_roi"), _rect(panel, "panel_roi")
        ) >= 0.10:
            panel_id = str(panel.get("panel_id") or "")
            if panel_id:
                output.append(panel_id)
    return sorted(set(output))


def _supersede_visual_approval(
    case: Path, *, remediation_ref: Mapping[str, Any]
) -> dict[str, Any] | None:
    approval_path = case / "phase4_visual_approval.json"
    if not approval_path.is_file():
        return None
    current = _load(approval_path)
    if str(current.get("status") or "") == "VISUAL_APPROVAL_SUPERSEDED":
        return current
    if str(current.get("status") or "") != "VISUAL_APPROVED":
        raise SourceTextProvenanceMaterializationError(
            "Unexpected active visual approval status"
        )
    previous_sha = _sha256_file(approval_path)
    backup_name = f"phase4_visual_approval_{previous_sha[:12]}_superseded.json"
    backup_path = case / backup_name
    if backup_path.is_file() and _sha256_file(backup_path) != previous_sha:
        raise SourceTextProvenanceMaterializationError(
            "Visual approval supersession backup drifted"
        )
    if not backup_path.is_file():
        _write_json_atomic(backup_path, current)
    payload: dict[str, Any] = {
        "schema_version": "phase4_visual_approval_supersession_v1",
        "status": "VISUAL_APPROVAL_SUPERSEDED",
        "superseded_at": datetime.now(timezone.utc).isoformat(),
        "reason": "SOURCE_SCENE_TEXT_WAS_MISCLASSIFIED_AS_EDITOR_OVERLAY",
        "previous_approval_ref": {
            "path": backup_name,
            "sha256": previous_sha,
            "previous_status": "VISUAL_APPROVED",
        },
        "superseded_by": dict(remediation_ref),
        "required_next_state": "RERENDER_AND_REAPPROVE_VISUAL",
    }
    payload["supersession_sha256"] = _sha256_json(payload)
    _write_json_atomic(approval_path, payload)
    return payload


def materialize(
    *,
    case_root: str | Path,
    artifact_version: str = "v22_51",
    operator_id: str = "operator-auto-provenance-correction",
) -> dict[str, Any]:
    case = Path(case_root).resolve()
    contract_path = case / "phase4_render_input.json"
    contract = _load(contract_path)
    active = load_active_visual_remediation(case, contract_path=contract_path)
    if active is None:
        raise SourceTextProvenanceMaterializationError(
            "Source provenance requires an active visual remediation parent"
        )
    parent, parent_ref = active
    provenance_ref = dict(
        dict(parent.get("authority_refs") or {}).get("source_text_provenance") or {}
    )
    if provenance_ref and str(provenance_ref.get("policy_version") or "") == SOURCE_SCENE_POLICY_VERSION:
        if (
            str(provenance_ref.get("phase4_input_sha256") or "")
            != _sha256_file(contract_path)
        ):
            raise SourceTextProvenanceMaterializationError(
                "Active source provenance authority is stale"
            )
        summary_path = case / str(provenance_ref.get("summary_path") or "")
        if not summary_path.is_file():
            raise SourceTextProvenanceMaterializationError(
                "Source provenance summary is missing"
            )
        return _load(summary_path)

    effective, effective_parent_ref = apply_visual_remediation(
        case, contract, contract_path=contract_path
    )
    if effective_parent_ref != parent_ref:
        raise SourceTextProvenanceMaterializationError(
            "Active remediation changed during provenance classification"
        )
    frame_count = int(dict(effective.get("video") or {}).get("frame_count") or 0)
    regions = classify_source_scene_components(
        list(effective.get("render_tracks") or []),
        frame_count=frame_count,
        seed_regions=list(effective.get("source_scene_text_regions") or []),
    )
    if not regions:
        raise SourceTextProvenanceMaterializationError(
            "No conservative source-scene text component was found"
        )
    tracks = {
        str(dict(row).get("text_id") or ""): dict(row)
        for row in list(effective.get("render_tracks") or [])
        if isinstance(row, Mapping)
    }
    panels = [
        dict(row)
        for row in list(effective.get("dense_ui_panels") or [])
        if isinstance(row, Mapping)
    ]
    new_operations: list[dict[str, Any]] = []
    for region in regions:
        targets = []
        for track_id in list(region.get("track_ids") or []):
            track = tracks.get(str(track_id))
            if track is None or str(track.get("kind") or "") == "hardsub":
                raise SourceTextProvenanceMaterializationError(
                    f"Unsafe source-scene target: {track_id}"
                )
            targets.append(
                {
                    "target_text_id": track_id,
                    "expected_track_sha256": _sha256_json(track),
                }
            )
        new_operations.append(
            {
                "operation": "CLASSIFY_SOURCE_SCENE_TEXT_REGION",
                "region": region,
                "expected_region_sha256": _sha256_json(region),
                "targets": targets,
                "disabled_panel_ids": _disabled_panel_ids(region, panels),
            }
        )

    operations = [
        dict(row)
        for row in list(parent.get("operations") or [])
        if isinstance(row, Mapping)
    ] + new_operations
    provenance_key = _sha256_json(
        {
            "policy_version": SOURCE_SCENE_POLICY_VERSION,
            "phase4_input_sha256": _sha256_file(contract_path),
            "parent_materialization_sha256": parent_ref.get("materialization_sha256"),
            "regions": regions,
        }
    )
    summary_name = f"phase4_source_text_provenance_{artifact_version}.json"
    payload: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_v1",
        "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_id": str(operator_id).strip(),
        "authority_refs": {
            "phase4_input": dict(
                dict(parent.get("authority_refs") or {}).get("phase4_input") or {}
            ),
            "parent_visual_remediation": parent_ref,
            "source_text_provenance": {
                "policy_version": SOURCE_SCENE_POLICY_VERSION,
                "phase4_input_sha256": _sha256_file(contract_path),
                "provenance_key": provenance_key,
                "summary_path": summary_name,
            },
        },
        "operations": operations,
        "non_goals": [
            "do_not_overwrite_master_timeline",
            "do_not_modify_phase1_v58_authority",
            "do_not_use_authority_v3_6_full_duration",
            "do_not_relax_output_qa_thresholds",
            "do_not_translate_source_scene_text",
        ],
    }
    if not payload["operator_id"]:
        raise SourceTextProvenanceMaterializationError("operator_id is required")
    payload["materialization_sha256"] = _sha256_json(payload)
    artifact_name = (
        f"phase4_visual_remediation_{provenance_key[:12]}_source_provenance.json"
    )
    artifact_path = case / artifact_name
    _write_json_atomic(artifact_path, payload)
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
    _write_json_atomic(case / ACTIVE_POINTER_NAME, pointer)
    supersession = _supersede_visual_approval(
        case, remediation_ref=pointer["active_ref"]
    )
    summary: dict[str, Any] = {
        "schema_version": "phase4_source_text_provenance_materialization_v1",
        "status": "PHASE4_SOURCE_TEXT_PROVENANCE_MATERIALIZED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_id": case.name,
        "artifact_version": str(artifact_version),
        "policy_version": SOURCE_SCENE_POLICY_VERSION,
        "provenance_key": provenance_key,
        "parent_visual_remediation_ref": parent_ref,
        "visual_remediation_ref": pointer["active_ref"],
        "regions": regions,
        "classified_track_count": sum(
            len(list(region.get("track_ids") or [])) for region in regions
        ),
        "disabled_panel_ids": sorted(
            {
                value
                for operation in new_operations
                for value in list(operation.get("disabled_panel_ids") or [])
            }
        ),
        "visual_approval_supersession": supersession,
    }
    summary["materialization_sha256"] = _sha256_json(summary)
    _write_json_atomic(case / summary_name, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.materialize_phase4_source_text_provenance"
    )
    parser.add_argument("case_root")
    parser.add_argument("--artifact-version", default="v22_51")
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
    except (OSError, ValueError, SourceTextProvenanceMaterializationError) as exc:
        print(f"[PHASE4-SOURCE-TEXT-PROVENANCE][FAIL] {exc}", flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "case_id": result["case_id"],
                "regions": len(result["regions"]),
                "classified_track_count": result["classified_track_count"],
                "disabled_panel_ids": result["disabled_panel_ids"],
                "visual_remediation_ref": result["visual_remediation_ref"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
