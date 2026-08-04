from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from scripts.build_phase4_residual_visual_triage import (
    Phase4ResidualVisualTriageError,
    build_visual_triage_pack,
    phase1_geometry_intersections,
    recommend_cluster,
)


def _hash_json(payload: dict) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_image(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = np.full((120, 200, 3), value, dtype=np.uint8)
    cv2.rectangle(frame, (50, 45), (150, 75), (255, 255, 255), 2)
    assert cv2.imwrite(str(path), frame)


def _fixture(run: Path) -> tuple[Path, dict, Path]:
    case_id = "triage_case"
    root = run / case_id
    sample = root / "qa" / "phase4_preflight_samples"
    temporal = sample / "residual_temporal_confirmation"
    source = run / "source.mp4"
    source.write_bytes(b"source-authority")
    source_ref = {"path": source.name, "sha256": _hash_file(source)}

    master = [
        {
            "text_id": "sub_01",
            "start_frame": 9,
            "end_frame": 11,
            "box_coords": [48.0, 43.0, 152.0, 77.0],
            "ocr_text": "午餐",
        }
    ]
    master_path = root / "master_timeline.json"
    _write_json(master_path, master)
    phase3_path = root / "phase3_render_handoff.json"
    _write_json(phase3_path, {})
    phase3_ref = {
        "path": phase3_path.name,
        "sha256": _hash_file(phase3_path),
    }
    video = {
        "frame_width": 200,
        "frame_height": 120,
        "frame_count": 20,
        "fps": 30.0,
    }
    contract = {
        "refs": {
            "source_video_ref": source_ref,
            "phase3_render_handoff_ref": phase3_ref,
            "phase1_ref": {
                "path": master_path.name,
                "sha256": _hash_file(master_path),
            },
        },
        "video": video,
    }
    preview = {
        "status": "PHASE4_PREFLIGHT_BLOCKED",
        "final_render_gate": "BLOCKED_VISUAL_RESIDUAL_CJK",
        "refs": contract["refs"],
        "video": video,
        "render_tracks": [],
    }
    _write_json(root / "phase4_render_input_preview.json", preview)

    exact = sample / "frame_000010.jpg"
    before = temporal / "frame_000009.jpg"
    after = temporal / "frame_000011.jpg"
    _write_image(exact, 90)
    _write_image(before, 80)
    _write_image(after, 100)
    detection = {
        "frame_index": 10,
        "text": "午餐",
        "confidence": 0.99,
        "geometry": {"x": 0.25, "y": 0.375, "width": 0.5, "height": 0.25},
        "temporal_confirmation": {
            "status": "CONFIRMED_ON_ADJACENT_FRAME",
            "match": {"frame_index": 9, "text": "午餐"},
        },
    }
    meta = {
        "status": "PHASE4_PREFLIGHT_BLOCKED",
        "final_render_gate": "BLOCKED_VISUAL_RESIDUAL_CJK",
        "phase3_render_handoff_sha256": _hash_file(phase3_path),
        "residual_cjk": {
            "complete": True,
            "error": None,
            "detections": [detection],
            "temporal_confirmation_frames": [
                before.relative_to(root).as_posix(),
                after.relative_to(root).as_posix(),
            ],
        },
        "artifacts": {"samples": [exact.relative_to(root).as_posix()]},
    }
    meta_path = root / "phase4_preflight_meta.json"
    _write_json(meta_path, meta)
    report_path = root / "qa" / "phase4_preflight_report.json"
    _write_json(
        report_path,
        {
            "status": "PHASE4_PREFLIGHT_BLOCKED",
            "blocked_reasons": ["residual_cjk:1"],
        },
    )
    attempt = {
        "status": "PROPOSAL_BLOCKED_OPERATOR_TRIAGE_REQUIRED",
        "reason": "ambiguous boundary",
        "operator_approval_written": False,
        "phase4_preflight_meta_ref": {"sha256": _hash_file(meta_path)},
    }
    attempt["attempt_sha256"] = _hash_json(attempt)
    attempt_path = root / "phase2_residual_remediation_proposal_attempt.json"
    _write_json(attempt_path, attempt)

    protected = [
        root / "phase2_ocr_timeline.json",
        root / "phase3_approvals.json",
    ]
    for path in protected:
        _write_json(path, {"locked": True})
    state_path = run / "batch_regression_state.json"
    _write_json(
        state_path,
        {
            "run_sha256": "a" * 64,
            "cases": [
                {
                    "case_id": case_id,
                    "status": "WAITING_RESIDUAL_CJK_OPERATOR_TRIAGE",
                }
            ],
        },
    )
    index = {
        "status": "PHASE4_PREFLIGHT_OPERATOR_TRIAGE_REQUIRED",
        "batch_state_ref": {
            "path": state_path.name,
            "sha256": _hash_file(state_path),
        },
        "cases": [
            {
                "case_id": case_id,
                "review_result": "OPERATOR_TRIAGE_REQUIRED",
                "preflight_meta_ref": {
                    "path": meta_path.relative_to(run).as_posix(),
                    "sha256": _hash_file(meta_path),
                },
                "preflight_report_ref": {
                    "path": report_path.relative_to(run).as_posix(),
                    "sha256": _hash_file(report_path),
                },
                "triage_ref": {
                    "path": attempt_path.relative_to(run).as_posix(),
                    "sha256": _hash_file(attempt_path),
                },
            }
        ],
    }
    index["batch_preflight_sha256"] = _hash_json(index)
    _write_json(run / "phase4_batch_preflight_index.json", index)
    return root, contract, source


def _frames(_source: Path, indices: list[int]) -> dict[int, np.ndarray]:
    return {
        int(index): np.full((120, 200, 3), 30 + int(index), dtype=np.uint8)
        for index in indices
    }


def test_builds_complete_hash_bound_source_render_adjacent_pack() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        root, contract, source = _fixture(run)
        protected = {
            path.name: _hash_file(path)
            for path in (
                root / "master_timeline.json",
                root / "phase2_ocr_timeline.json",
                root / "phase3_approvals.json",
            )
        }

        with patch(
            "scripts.build_phase4_residual_visual_triage.prepare_phase4_from_root",
            return_value=(contract, {}, source),
        ):
            batch = build_visual_triage_pack(
                run_root=run, frame_loader=_frames
            )

        assert batch["counts"] == {
            "cases": 1,
            "clusters": 1,
            "evidence_frames": 3,
            "remediate": 0,
            "false_positive": 0,
            "needs_operator_input": 1,
        }
        case = json.loads(
            (root / "phase4_residual_visual_triage.json").read_text(
                encoding="utf-8"
            )
        )
        unsigned = dict(case)
        claimed = unsigned.pop("triage_sha256")
        assert claimed == _hash_json(unsigned)
        cluster = case["clusters"][0]
        assert cluster["source_render_adjacent_complete"] is True
        assert cluster["coverage_by_detection"] == [
            {
                "detection_frame_index": 10,
                "expected_source_render_frames": [9, 10, 11],
                "complete": True,
            }
        ]
        assert cluster["recommendation"]["action"] == "NEEDS_OPERATOR_INPUT"
        assert len(cluster["phase1_geometry_intersections"]) == 1
        assert [row["frame_index"] for row in cluster["evidence_frames"]] == [
            9,
            10,
            11,
        ]
        for evidence in cluster["evidence_frames"]:
            for key in (
                "source_frame_ref",
                "rendered_frame_ref",
                "source_crop_ref",
                "rendered_crop_ref",
            ):
                ref = evidence[key]
                artifact = root / ref["path"]
                assert artifact.is_file()
                assert _hash_file(artifact) == ref["sha256"]
        contact_ref = cluster["contact_sheet_ref"]
        assert _hash_file(root / contact_ref["path"]) == contact_ref["sha256"]
        for path in (
            root / "master_timeline.json",
            root / "phase2_ocr_timeline.json",
            root / "phase3_approvals.json",
        ):
            assert _hash_file(path) == protected[path.name]
        assert not (root / "phase2_residual_remediation.json").exists()
        assert not (root / "phase4_visual_approval.json").exists()


def test_rejects_stale_preflight_before_writing_evidence() -> None:
    with TemporaryDirectory() as tmp:
        run = Path(tmp)
        root, contract, source = _fixture(run)
        meta_path = root / "phase4_preflight_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["tampered"] = True
        _write_json(meta_path, meta)

        with patch(
            "scripts.build_phase4_residual_visual_triage.prepare_phase4_from_root",
            return_value=(contract, {}, source),
        ):
            with pytest.raises(
                Phase4ResidualVisualTriageError, match="Stale .*preflight meta"
            ):
                build_visual_triage_pack(run_root=run, frame_loader=_frames)

        assert not (root / "phase4_residual_visual_triage.json").exists()
        assert not (root / "qa" / "phase4_residual_visual_triage").exists()


def test_conservative_recommendations_cover_all_operator_outcomes() -> None:
    base = {
        "signature": "午餐",
        "detections": [
            {
                "frame_index": 10,
                "text": "午餐",
                "confidence": 0.99,
                "temporal_confirmation": {
                    "status": "CONFIRMED_ON_ADJACENT_FRAME"
                },
            }
        ],
    }
    assert recommend_cluster(base, [])["action"] == "REMEDIATE"
    weak = {
        **base,
        "detections": [
            {"frame_index": 10, "text": "福", "confidence": 0.30}
        ],
    }
    assert recommend_cluster(weak, [])["action"] == "FALSE_POSITIVE"
    intersection = [{"intersection_over_smaller": 0.9}]
    assert recommend_cluster(base, intersection)["action"] == "NEEDS_OPERATOR_INPUT"


def test_surfaces_spatial_phase1_geometry_reuse_outside_active_window() -> None:
    cluster = {
        "detections": [
            {
                "frame_index": 10,
                "geometry": {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5},
            }
        ]
    }
    intersections = phase1_geometry_intersections(
        cluster,
        [
            {
                "text_id": "sub_later",
                "start_frame": 100,
                "end_frame": 110,
                "box_coords": [50, 25, 150, 75],
            }
        ],
        frame_width=200,
        frame_height=100,
    )

    assert len(intersections) == 1
    assert intersections[0]["active_on_residual_frame"] is False
    assert intersections[0]["active_matched_frame_indices"] == []
