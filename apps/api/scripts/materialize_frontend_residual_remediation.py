"""Materialize hash-bound residual editor-text coverage for a frontend run.

The decision file is deliberately explicit: OCR evidence and Vietnamese text
are reviewed together, then this script creates only an ADD_TRACK visual
remediation. Phase 1-3 timelines remain untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.media_pipeline.video_renderer.render_policy import plan_render_track
from src.media_pipeline.video_renderer.visual_remediation import (
    ACTIVE_POINTER_NAME,
    _sha256_json,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def materialize(root_dir: str | Path, decision_path: str | Path) -> dict[str, Any]:
    root = Path(root_dir).resolve()
    decisions_path = Path(decision_path).resolve()
    input_path = root / "phase4_render_input.json"
    if not input_path.is_file() or not decisions_path.is_file():
        raise RuntimeError("Phase 4 input or residual decision file is missing")
    contract = json.loads(input_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if not isinstance(contract, Mapping) or not isinstance(decisions, list):
        raise RuntimeError("Invalid Phase 4 residual decision shape")
    video = dict(contract.get("video") or {})
    fps = float(video.get("fps") or 30.0)
    frame_count = int(video.get("frame_count") or 0)
    existing = {
        str(row.get("text_id") or "")
        for row in list(contract.get("render_tracks") or [])
        if isinstance(row, Mapping)
    }
    operations: list[dict[str, Any]] = []
    for raw in decisions:
        if not isinstance(raw, Mapping):
            raise RuntimeError("Residual decision must be an object")
        text_id = str(raw.get("text_id") or "").strip()
        start = int(raw.get("start_frame") or 0)
        end_value = raw.get("end_frame")
        end = int(-1 if end_value is None else end_value)
        geometry = dict(raw.get("geometry") or {})
        text_vi = str(raw.get("text_vi") or "").strip()
        if (
            not text_id
            or text_id in existing
            or start < 0
            or end < start
            or (frame_count and end >= frame_count)
            or not text_vi
        ):
            raise RuntimeError(f"Invalid or duplicate residual track: {text_id}")
        track: dict[str, Any] = {
            "text_id": text_id,
            "content_id": f"residual_{text_id}",
            "start_frame": start,
            "end_frame": end,
            "start_ms": int(round(start * 1000.0 / fps)),
            "end_ms": int(round((end + 1) * 1000.0 / fps)),
            "best_frame_index": start,
            "geometry": geometry,
            "roles": ["generic"],
            "kind": "ui",
            "text_vi": text_vi,
            "translation_status": "TRANSLATION_APPROVED",
            "cover_only": False,
            "duplicate_transition_canonical": False,
        }
        track["render_policy"] = plan_render_track(track, simultaneous_count=1)
        operations.append(
            {
                "operation": "ADD_TRACK",
                "track": track,
                "expected_added_track_sha256": _sha256_json(track),
                "evidence": dict(raw.get("evidence") or {}),
            }
        )
        existing.add(text_id)
    payload: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_v1",
        "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operator_id": "frontend_auto_quality_recovery",
        "authority_refs": {
            "phase4_input": {
                "path": input_path.name,
                "sha256": _sha256_file(input_path),
            },
            "residual_decisions": {
                "path": decisions_path.name,
                "sha256": _sha256_file(decisions_path),
            },
        },
        "operations": operations,
        "non_goals": [
            "do_not_overwrite_master_timeline",
            "do_not_relax_output_qa_thresholds",
            "do_not_translate_source_intrinsic_text",
        ],
    }
    payload["materialization_sha256"] = _sha256_json(payload)
    material_path = root / (
        f"phase4_visual_remediation_{payload['materialization_sha256'][:12]}_auto.json"
    )
    _write(material_path, payload)
    pointer: dict[str, Any] = {
        "schema_version": "phase4_visual_remediation_pointer_v1",
        "status": "ACTIVE",
        "active_ref": {
            "path": material_path.name,
            "sha256": _sha256_file(material_path),
            "materialization_sha256": payload["materialization_sha256"],
        },
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    _write(root / ACTIVE_POINTER_NAME, pointer)
    return pointer["active_ref"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("decisions")
    args = parser.parse_args()
    print(json.dumps(materialize(args.root, args.decisions), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
