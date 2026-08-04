from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.materialize_phase4_source_text_provenance import materialize
from src.media_pipeline.video_renderer.visual_remediation import (
    _sha256_json,
    apply_visual_remediation,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _track(index: int, *, kind: str = "ui") -> dict:
    return {
        "text_id": f"ui_{index}" if kind == "ui" else "editor_subtitle",
        "content_id": f"content_{index}",
        "kind": kind,
        "start_frame": 10 + index,
        "end_frame": 30 + index,
        "text_vi": "Nhãn nguồn" if kind == "ui" else "Phụ đề editor",
        "geometry": {
            "x": 0.1 + index * 0.04,
            "y": 0.1 + index * 0.06,
            "width": 0.08,
            "height": 0.04,
        },
        "render_policy": {
            "context": {"dense_ui": True, "simultaneous_count": 10},
            "cover": {
                "roi": {
                    "x": 0.1 + index * 0.04,
                    "y": 0.1 + index * 0.06,
                    "width": 0.08,
                    "height": 0.04,
                }
            },
            "layout": {
                "safe_area": {"x": 0.05, "y": 0.05, "width": 0.4, "height": 0.5}
            },
            "damage_budget": {"max_frame_change_fraction": 0.5},
        },
    }


def _fixture(tmp_path: Path) -> Path:
    case = tmp_path / "case_01"
    case.mkdir()
    tracks = [_track(index) for index in range(7)] + [_track(7, kind="hardsub")]
    contract = {
        "video": {"fps": 30.0, "frame_count": 100},
        "counts": {"render_tracks": len(tracks)},
        "render_tracks": tracks,
        "dense_ui_panels": [
            {
                "panel_id": "wrong_phone_panel",
                "start_frame": 10,
                "end_frame": 40,
                "panel_roi": {"x": 0.08, "y": 0.08, "width": 0.4, "height": 0.5},
            }
        ],
    }
    contract_path = case / "phase4_render_input.json"
    _write(contract_path, contract)
    parent = {
        "schema_version": "phase4_visual_remediation_v1",
        "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
        "created_at": "2026-07-31T00:00:00+00:00",
        "operator_id": "operator",
        "authority_refs": {
            "phase4_input": {
                "path": contract_path.name,
                "sha256": _sha(contract_path),
            }
        },
        "operations": [],
    }
    parent["materialization_sha256"] = _sha256_json(parent)
    parent_path = case / "phase4_visual_remediation_parent.json"
    _write(parent_path, parent)
    pointer = {
        "schema_version": "phase4_visual_remediation_pointer_v1",
        "status": "ACTIVE",
        "active_ref": {
            "path": parent_path.name,
            "sha256": _sha(parent_path),
            "materialization_sha256": parent["materialization_sha256"],
        },
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    _write(case / "phase4_visual_remediation_active.json", pointer)
    _write(
        case / "phase4_visual_approval.json",
        {
            "schema_version": "phase4_visual_approval_v1",
            "status": "VISUAL_APPROVED",
            "video_ref": {"path": "old.mp4", "sha256": "a" * 64},
            "output_qa_ref": {"path": "old.json", "sha256": "b" * 64},
        },
    )
    return case


def test_materializer_is_hash_bound_idempotent_and_supersedes_approval(
    tmp_path: Path,
) -> None:
    case = _fixture(tmp_path)
    first = materialize(case_root=case, artifact_version="vtest")
    second = materialize(case_root=case, artifact_version="vtest")

    assert second["materialization_sha256"] == first["materialization_sha256"]
    assert first["classified_track_count"] == 7
    assert first["disabled_panel_ids"] == ["wrong_phone_panel"]
    approval = json.loads(
        (case / "phase4_visual_approval.json").read_text(encoding="utf-8")
    )
    assert approval["status"] == "VISUAL_APPROVAL_SUPERSEDED"
    assert (case / approval["previous_approval_ref"]["path"]).is_file()

    contract_path = case / "phase4_render_input.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    effective, ref = apply_visual_remediation(
        case, contract, contract_path=contract_path
    )
    assert [row["text_id"] for row in effective["render_tracks"]] == [
        "editor_subtitle"
    ]
    assert effective["dense_ui_panels"] == []
    assert len(effective["source_scene_text_regions"]) == 1
    assert len(ref["sha256"]) == 64
