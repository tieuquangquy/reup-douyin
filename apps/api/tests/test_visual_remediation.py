from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.media_pipeline.video_renderer.visual_remediation import (
    VisualRemediationError,
    _sha256_json,
    apply_visual_remediation,
)


def _write_authority(root: Path, contract: dict, operations: list[dict]) -> Path:
    contract_path = root / "phase4_render_input.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    payload = {
        "status": "PHASE4_VISUAL_REMEDIATION_APPROVED",
        "authority_refs": {
            "phase4_input": {
                "path": contract_path.name,
                "sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
            }
        },
        "operations": operations,
    }
    payload["materialization_sha256"] = _sha256_json(payload)
    material = root / "phase4_visual_remediation_test.json"
    material.write_text(json.dumps(payload), encoding="utf-8")
    pointer = {
        "active_ref": {
            "path": material.name,
            "sha256": hashlib.sha256(material.read_bytes()).hexdigest(),
        }
    }
    pointer["pointer_sha256"] = _sha256_json(pointer)
    (root / "phase4_visual_remediation_active.json").write_text(
        json.dumps(pointer), encoding="utf-8"
    )
    return contract_path


def _contract() -> dict:
    return {
        "video": {"fps": 30.0},
        "counts": {"render_tracks": 1},
        "render_tracks": [
            {
                "text_id": "sub_01",
                "content_id": "content_01",
                "start_frame": 0,
                "end_frame": 20,
                "start_ms": 0,
                "end_ms": 700,
                "text_vi": "Test",
                "cover_only": False,
                "render_policy": {
                    "policy_version": "base",
                    "context": {"caption_row": False},
                    "cover": {"mask_mode": "ink_components"},
                },
            }
        ],
    }


def test_applies_track_split_and_scopes_mask_cache() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract()
        track_hash = _sha256_json(contract["render_tracks"][0])
        contract_path = _write_authority(
            root,
            contract,
            [
                {
                    "operation": "SPLIT_TRACK",
                    "target_text_id": "sub_01",
                    "expected_track_sha256": track_hash,
                    "intervals": [[0, 8], [11, 20]],
                }
            ],
        )
        effective, ref = apply_visual_remediation(
            root, contract, contract_path=contract_path
        )

    assert ref is not None
    assert [row["text_id"] for row in effective["render_tracks"]] == [
        "sub_01__p4r_01",
        "sub_01__p4r_02",
    ]
    assert effective["render_tracks"][1]["start_ms"] == 367
    assert (
        effective["render_tracks"][1]["render_policy"]["context"]["mask_cache_scope"]
        == "sub_01__p4r_02"
    )


def test_fails_closed_when_track_drifted() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract()
        contract_path = _write_authority(
            root,
            contract,
            [
                {
                    "operation": "DROP_TRACK",
                    "target_text_id": "sub_01",
                    "expected_track_sha256": "0" * 64,
                }
            ],
        )
        with pytest.raises(VisualRemediationError):
            apply_visual_remediation(root, contract, contract_path=contract_path)


def test_policy_override_can_bind_layout_to_cover_lane() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract()
        contract["render_tracks"][0]["kind"] = "hardsub"
        track_hash = _sha256_json(contract["render_tracks"][0])
        contract_path = _write_authority(
            root,
            contract,
            [
                {
                    "operation": "POLICY_OVERRIDE",
                    "target_text_id": "sub_01",
                    "expected_track_sha256": track_hash,
                    "layout_updates": {
                        "mode": "cover_aligned",
                        "safe_area": {"x": 0.2, "y": 0.8, "width": 0.6, "height": 0.08},
                        "max_lines": 2,
                    },
                }
            ],
        )
        effective, _ref = apply_visual_remediation(
            root, contract, contract_path=contract_path
        )

    assert effective["render_tracks"][0]["render_policy"]["layout"]["mode"] == "cover_aligned"


def test_policy_override_can_raise_bounded_damage_budget() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract()
        contract["render_tracks"][0]["render_policy"]["damage_budget"] = {
            "max_frame_change_fraction": 0.01
        }
        track_hash = _sha256_json(contract["render_tracks"][0])
        contract_path = _write_authority(
            root,
            contract,
            [{
                "operation": "POLICY_OVERRIDE",
                "target_text_id": "sub_01",
                "expected_track_sha256": track_hash,
                "damage_budget_updates": {"max_frame_change_fraction": 0.025},
            }],
        )
        effective, _ref = apply_visual_remediation(
            root, contract, contract_path=contract_path
        )

    assert effective["render_tracks"][0]["render_policy"]["damage_budget"][
        "max_frame_change_fraction"
    ] == 0.025


def test_accepts_hash_bound_targetless_right_edge_phone_region() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract()
        contract["video"]["frame_count"] = 100
        region = {
            "region_id": "source_scene_phone_right_ui_01",
            "classification": "SOURCE_SCENE_TEXT",
            "start_frame": 40,
            "end_frame": 60,
            "region_roi": {"x": 0.82, "y": 0.25, "width": 0.16, "height": 0.4},
            "track_ids": [],
            "evidence": {
                "reason": "RESIDUAL_RIGHT_EDGE_PHONE_UI_BOUNDING",
                "qa_frames": [42, 58],
            },
        }
        contract_path = _write_authority(
            root,
            contract,
            [{
                "operation": "CLASSIFY_SOURCE_SCENE_TEXT_REGION",
                "region": region,
                "expected_region_sha256": _sha256_json(region),
                "targets": [],
                "disabled_panel_ids": [],
            }],
        )
        effective, _ref = apply_visual_remediation(
            root, contract, contract_path=contract_path
        )

    assert effective["source_scene_text_regions"] == [region]
    assert len(effective["render_tracks"]) == 1


def test_adds_hash_bound_output_residual_track() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract()
        contract["video"]["frame_count"] = 30
        added = {
            "text_id": "p4out_cluster",
            "content_id": "p4out_content_cluster",
            "start_frame": 21,
            "end_frame": 24,
            "best_frame_index": 22,
            "start_ms": 700,
            "end_ms": 833,
            "geometry": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.05},
            "roles": ["ui_chip"],
            "kind": "ui",
            "text_vi": "Nhãn mới",
            "translation_status": "TRANSLATION_APPROVED",
            "cover_only": False,
            "duplicate_transition_canonical": False,
            "render_policy": {"policy_version": "test"},
        }
        contract_path = _write_authority(
            root,
            contract,
            [
                {
                    "operation": "ADD_TRACK",
                    "track": added,
                    "expected_added_track_sha256": _sha256_json(added),
                }
            ],
        )
        effective, _ref = apply_visual_remediation(
            root, contract, contract_path=contract_path
        )

    assert effective["counts"]["render_tracks"] == 2
    assert effective["render_tracks"][-1]["text_vi"] == "Nhãn mới"


def test_adds_single_frame_output_residual_track_at_frame_zero() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract()
        contract["video"]["frame_count"] = 30
        added = {
            "text_id": "p4out_frame_zero",
            "content_id": "p4out_content_frame_zero",
            "start_frame": 0,
            "end_frame": 0,
            "best_frame_index": 0,
            "start_ms": 0,
            "end_ms": 33,
            "geometry": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.05},
            "roles": ["ui_chip"],
            "kind": "ui",
            "text_vi": "Nhãn đầu video",
            "translation_status": "TRANSLATION_APPROVED",
            "cover_only": False,
            "duplicate_transition_canonical": False,
            "render_policy": {"policy_version": "test"},
        }
        contract_path = _write_authority(
            root,
            contract,
            [
                {
                    "operation": "ADD_TRACK",
                    "track": added,
                    "expected_added_track_sha256": _sha256_json(added),
                }
            ],
        )

        effective, _ref = apply_visual_remediation(
            root, contract, contract_path=contract_path
        )

    assert effective["render_tracks"][-1]["start_frame"] == 0
    assert effective["render_tracks"][-1]["end_frame"] == 0


def _group_track(text_id: str, *, x: float = 0.2) -> dict:
    return {
        "text_id": text_id,
        "content_id": f"content_{text_id}",
        "start_frame": 5,
        "end_frame": 20,
        "start_ms": 167,
        "end_ms": 700,
        "text_vi": "Phan an duoc",
        "geometry": {"x": x, "y": 0.1, "width": 0.2, "height": 0.05},
        "output_residual_coverage": {
            "status": "OPERATOR_APPROVED_SOURCE_TEMPLATE_VERIFIED",
            "source_text": "edible portion",
        },
        "render_policy": {"policy_version": "test"},
    }


def test_drop_track_group_is_atomic_and_keeps_canonical() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        tracks = [
            _group_track("p4out_aligned"),
            _group_track("p4out_old_a", x=0.205),
            _group_track("p4out_old_b", x=0.21),
        ]
        contract = {
            "video": {"fps": 30.0},
            "counts": {"render_tracks": 3},
            "render_tracks": tracks,
        }
        contract_path = _write_authority(
            root,
            contract,
            [
                {
                    "operation": "DROP_TRACK_GROUP",
                    "target_text_id": "p4out_aligned",
                    "canonical_track_id": "p4out_aligned",
                    "expected_canonical_track_sha256": _sha256_json(tracks[0]),
                    "targets": [
                        {
                            "target_text_id": row["text_id"],
                            "expected_track_sha256": _sha256_json(row),
                        }
                        for row in tracks[1:]
                    ],
                }
            ],
        )
        effective, _ref = apply_visual_remediation(
            root, contract, contract_path=contract_path
        )

    assert effective["counts"]["render_tracks"] == 1
    assert [row["text_id"] for row in effective["render_tracks"]] == [
        "p4out_aligned"
    ]


def test_drop_track_group_fails_closed_without_partial_drop() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        tracks = [
            _group_track("p4out_aligned"),
            _group_track("p4out_old_a", x=0.205),
            _group_track("p4out_old_b", x=0.21),
        ]
        contract = {
            "video": {"fps": 30.0},
            "counts": {"render_tracks": 3},
            "render_tracks": tracks,
        }
        contract_path = _write_authority(
            root,
            contract,
            [
                {
                    "operation": "DROP_TRACK_GROUP",
                    "canonical_track_id": "p4out_aligned",
                    "expected_canonical_track_sha256": _sha256_json(tracks[0]),
                    "targets": [
                        {
                            "target_text_id": "p4out_old_a",
                            "expected_track_sha256": _sha256_json(tracks[1]),
                        },
                        {
                            "target_text_id": "p4out_old_b",
                            "expected_track_sha256": "0" * 64,
                        },
                    ],
                }
            ],
        )

        with pytest.raises(VisualRemediationError):
            apply_visual_remediation(root, contract, contract_path=contract_path)

    assert [row["text_id"] for row in contract["render_tracks"]] == [
        "p4out_aligned",
        "p4out_old_a",
        "p4out_old_b",
    ]


def test_add_dense_ui_panel_is_hash_bound_and_budget_bound() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract()
        contract["video"]["frame_count"] = 100
        contract["render_tracks"][0]["render_policy"]["damage_budget"] = {
            "max_frame_change_fraction": 0.55,
            "max_ink_roi_fill_fraction": 0.8,
        }
        panel = {
            "panel_id": "p4panel_test",
            "canonical_text_id": "sub_01",
            "start_frame": 10,
            "end_frame": 20,
            "panel_roi": {"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.4},
            "cover_strategy": "OPAQUE_SOURCE_AWARE_PHONE_UI_PLATE",
            "layout_strategy": "DEDUPLICATED_PRIORITY_GRID",
            "deduplication_key": "content_id_then_normalized_vi_text",
            "max_rendered_lines": 12,
            "max_frame_change_fraction": 0.55,
        }
        contract_path = _write_authority(
            root,
            contract,
            [
                {
                    "operation": "ADD_DENSE_UI_PANEL",
                    "panel": panel,
                    "expected_panel_sha256": _sha256_json(panel),
                    "expected_canonical_track_sha256": _sha256_json(contract["render_tracks"][0]),
                }
            ],
        )
        effective, _ = apply_visual_remediation(root, contract, contract_path=contract_path)
        assert effective["dense_ui_panels"][0]["panel_id"] == "p4panel_test"
        assert effective["dense_ui_panels"][0]["max_frame_change_fraction"] == 0.55


def test_add_dense_ui_panel_rejects_budget_drift() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract()
        contract["render_tracks"][0]["render_policy"]["damage_budget"] = {
            "max_frame_change_fraction": 0.55,
        }
        panel = {
            "panel_id": "p4panel_bad",
            "canonical_text_id": "sub_01",
            "start_frame": 0,
            "end_frame": 20,
            "panel_roi": {"x": 0.1, "y": 0.1, "width": 0.4, "height": 0.4},
            "cover_strategy": "OPAQUE_SOURCE_AWARE_PHONE_UI_PLATE",
            "layout_strategy": "DEDUPLICATED_PRIORITY_GRID",
            "max_rendered_lines": 12,
            "max_frame_change_fraction": 0.54,
        }
        contract_path = _write_authority(
            root,
            contract,
            [{"operation": "ADD_DENSE_UI_PANEL", "panel": panel,
              "expected_panel_sha256": _sha256_json(panel),
              "expected_canonical_track_sha256": _sha256_json(contract["render_tracks"][0])}],
        )
        with pytest.raises(VisualRemediationError):
            apply_visual_remediation(root, contract, contract_path=contract_path)


def test_source_scene_classification_removes_ui_but_preserves_hardsub() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        tracks = []
        for index in range(6):
            row = _group_track(f"ui_{index}", x=0.1 + index * 0.03)
            row["kind"] = "ui"
            tracks.append(row)
        hardsub = _group_track("editor_subtitle", x=0.2)
        hardsub["kind"] = "hardsub"
        tracks.append(hardsub)
        contract = {
            "video": {"fps": 30.0, "frame_count": 100},
            "counts": {"render_tracks": len(tracks)},
            "render_tracks": tracks,
            "dense_ui_panels": [{"panel_id": "old_panel"}],
        }
        region = {
            "region_id": "source_scene_dense_01",
            "classification": "SOURCE_SCENE_TEXT",
            "start_frame": 5,
            "end_frame": 20,
            "region_roi": {"x": 0.05, "y": 0.05, "width": 0.5, "height": 0.5},
            "track_ids": sorted(row["text_id"] for row in tracks[:-1]),
        }
        contract_path = _write_authority(
            root,
            contract,
            [
                {
                    "operation": "CLASSIFY_SOURCE_SCENE_TEXT_REGION",
                    "region": region,
                    "expected_region_sha256": _sha256_json(region),
                    "targets": [
                        {
                            "target_text_id": row["text_id"],
                            "expected_track_sha256": _sha256_json(row),
                        }
                        for row in tracks[:-1]
                    ],
                    "disabled_panel_ids": ["old_panel"],
                }
            ],
        )
        effective, _ = apply_visual_remediation(root, contract, contract_path=contract_path)
        assert [row["text_id"] for row in effective["render_tracks"]] == ["editor_subtitle"]
        assert effective["dense_ui_panels"] == []
        assert effective["source_scene_text_regions"][0]["region_id"] == "source_scene_dense_01"


def test_source_scene_region_extension_is_hash_bound() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        track = _group_track("editor_subtitle", x=0.2)
        track["kind"] = "hardsub"
        region = {
            "region_id": "source_scene_plane_01",
            "classification": "SOURCE_SCENE_TEXT",
            "start_frame": 10,
            "end_frame": 20,
            "region_roi": {"x": 0.05, "y": 0.05, "width": 0.5, "height": 0.7},
            "track_ids": ["already_classified"],
        }
        replacement = {**region, "start_frame": 5, "end_frame": 40}
        contract = {
            "video": {"fps": 30.0, "frame_count": 100},
            "counts": {"render_tracks": 1},
            "render_tracks": [track],
            "source_scene_text_regions": [region],
        }
        contract_path = _write_authority(
            root,
            contract,
            [
                {
                    "operation": "EXTEND_SOURCE_SCENE_TEXT_REGION",
                    "region_id": region["region_id"],
                    "expected_region_sha256": _sha256_json(region),
                    "replacement_region": replacement,
                    "expected_replacement_sha256": _sha256_json(replacement),
                }
            ],
        )
        effective, _ = apply_visual_remediation(root, contract, contract_path=contract_path)
        assert effective["source_scene_text_regions"][0]["start_frame"] == 5
        assert effective["source_scene_text_regions"][0]["end_frame"] == 40
