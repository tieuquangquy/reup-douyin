"""Materialize an operator-approved source-intrinsic text region correction."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.run_phase4_adaptive import _load_json
from src.media_pipeline.video_renderer.source_text_provenance import (
    SOURCE_INTRINSIC_REGION_POLICY_VERSION,
)
from src.media_pipeline.video_renderer.visual_remediation import (
    ACTIVE_POINTER_NAME,
    _sha256_file,
    _sha256_json,
    _track_hash,
    apply_visual_remediation,
    load_active_visual_remediation,
)


def materialize(
    *,
    case_root: str | Path,
    track_ids: list[str],
    region_roi: dict[str, float],
    start_frame: int,
    end_frame: int,
    artifact_version: str,
    operator_id: str,
    evidence_reason: str,
) -> dict[str, Any]:
    root = Path(case_root).resolve()
    input_path = root / "phase4_render_input.json"
    contract = _load_json(input_path)
    effective, _ = apply_visual_remediation(root, contract, contract_path=input_path)
    by_id = {
        str(row.get("text_id") or ""): dict(row)
        for row in list(effective.get("render_tracks") or [])
        if str(row.get("text_id") or "")
    }
    targets = []
    for text_id in track_ids:
        track = by_id.get(text_id)
        if track is None:
            raise ValueError(f"Unknown source-intrinsic track: {text_id}")
        if str(track.get("kind") or "") == "hardsub":
            raise ValueError(f"Cannot classify editor hardsub as source text: {text_id}")
        targets.append(
            {
                "target_text_id": text_id,
                "expected_track_sha256": _track_hash(track),
            }
        )

    region = {
        "region_id": f"source_intrinsic_{artifact_version}",
        "classification": "SOURCE_SCENE_TEXT",
        "region_roi": dict(region_roi),
        "start_frame": int(start_frame),
        "end_frame": int(end_frame),
        "track_ids": list(track_ids),
        "evidence": {
            "reason": evidence_reason,
            "qa_frames": [int(start_frame), int((start_frame + end_frame) // 2), int(end_frame)],
            "source_object": "moving_transparent_packaging",
            "operator_decision": "preserve_source_pixels_do_not_translate",
        },
    }
    operation = {
        "operation": "CLASSIFY_SOURCE_SCENE_TEXT_REGION",
        "region": region,
        "expected_region_sha256": _sha256_json(region),
        "targets": targets,
    }

    active_payload, parent_ref = load_active_visual_remediation(
        root, contract_path=input_path
    )
    created_at = datetime.now(timezone.utc).isoformat()
    payload = dict(active_payload)
    payload["created_at"] = created_at
    payload["operator_id"] = operator_id
    payload["authority_refs"] = {
        **dict(payload.get("authority_refs") or {}),
        "parent_visual_remediation": dict(parent_ref),
        "source_intrinsic_region": {
            "policy_version": SOURCE_INTRINSIC_REGION_POLICY_VERSION,
            "reason": evidence_reason,
            "phase4_input_sha256": _sha256_file(input_path),
        },
    }
    payload["operations"] = [*list(active_payload.get("operations") or []), operation]
    payload["non_goals"] = [
        *list(payload.get("non_goals") or []),
        "Do not remove or translate editor hardsub tracks outside the classified source region",
    ]
    payload.pop("materialization_sha256", None)
    payload["materialization_sha256"] = _sha256_json(payload)

    filename = f"phase4_visual_remediation_source_intrinsic_{artifact_version}.json"
    artifact_path = root / filename
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    active_ref = {
        "path": filename,
        "sha256": _sha256_file(artifact_path),
        "materialization_sha256": payload["materialization_sha256"],
    }
    pointer = {
        "schema_version": "phase4_visual_remediation_pointer_v1",
        "status": "ACTIVE",
        "active_ref": active_ref,
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    (root / ACTIVE_POINTER_NAME).write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "artifact": str(artifact_path),
        "artifact_sha256": active_ref["sha256"],
        "materialization_sha256": active_ref["materialization_sha256"],
        "region_id": region["region_id"],
        "dropped_track_ids": track_ids,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_root", type=Path)
    parser.add_argument("--artifact-version", required=True)
    parser.add_argument("--operator-id", default="operator-auto-source-intrinsic-review")
    parser.add_argument("--start-frame", type=int, required=True)
    parser.add_argument("--end-frame", type=int, required=True)
    parser.add_argument("--roi", nargs=4, type=float, metavar=("X", "Y", "W", "H"), required=True)
    parser.add_argument("--track-id", action="append", required=True)
    args = parser.parse_args()
    result = materialize(
        case_root=args.case_root,
        track_ids=args.track_id,
        region_roi={"x": args.roi[0], "y": args.roi[1], "width": args.roi[2], "height": args.roi[3]},
        start_frame=args.start_frame,
        end_frame=args.end_frame,
        artifact_version=args.artifact_version,
        operator_id=args.operator_id,
        evidence_reason="OPERATOR_CONFIRMED_MOVING_PACKAGING_PRINT_SOURCE_INTRINSIC",
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
