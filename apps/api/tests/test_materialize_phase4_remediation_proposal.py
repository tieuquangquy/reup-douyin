from __future__ import annotations

import pytest

from scripts.materialize_phase4_remediation_proposal import (
    Phase4RemediationMaterializationError,
    _build_operation,
    visible_intervals_for_split,
)


def test_splits_at_two_frame_blank_interval_containing_failure() -> None:
    intervals = visible_intervals_for_split(
        {
            "start_frame": 6,
            "end_frame": 153,
            "hit_frames": list(range(8, 79)) + list(range(81, 152)),
        },
        failure_frame=79,
    )
    assert intervals == [[6, 78], [81, 153]]


def test_split_fails_when_failed_frame_is_not_in_blank_interval() -> None:
    with pytest.raises(Phase4RemediationMaterializationError):
        visible_intervals_for_split(
            {
                "start_frame": 6,
                "end_frame": 153,
                "hit_frames": list(range(8, 79)) + list(range(81, 152)),
            },
            failure_frame=100,
        )


def test_builds_bounded_micro_ui_spatial_fallback_without_relaxing_budget(
    tmp_path,
) -> None:
    track = {
        "text_id": "p4out_01",
        "render_policy": {
            "context": {
                "micro_ui": True,
                "output_residual_bounded_dense_mask": True,
                "reference_plate_operator_approved": True,
            },
            "cover": {"mask_mode": "stylized_components"},
            "damage_budget": {"max_frame_change_fraction": 0.55},
        },
    }
    operation = _build_operation(
        case_root=tmp_path,
        contract={"render_tracks": [track]},
        decision={
            "text_id": "p4out_01",
            "decision": {
                "action": "BOUNDED_MICRO_UI_SPATIAL_FALLBACK_WITH_EXISTING_DAMAGE_BUDGET"
            },
        },
    )

    assert operation["operation"] == "POLICY_OVERRIDE"
    assert operation["cover_updates"]["mask_mode"] == "ink_components"
    assert operation["context_updates"]["reference_plate_operator_approved"] is False
    assert operation["damage_budget_changed"] is False


def test_caption_panel_fallback_selects_ink_components_without_relaxing_budget(
    tmp_path,
) -> None:
    track = {
        "text_id": "sub_01",
        "render_policy": {
            "context": {"micro_ui": False},
            "cover": {"mask_mode": "stylized_components"},
            "damage_budget": {"max_frame_change_fraction": 0.03},
        },
    }

    operation = _build_operation(
        case_root=tmp_path,
        contract={"render_tracks": [track]},
        decision={
            "text_id": "sub_01",
            "decision": {
                "action": "CAPTION_PANEL_FALLBACK_WITH_EXISTING_DAMAGE_BUDGET"
            },
        },
    )

    assert operation["cover_updates"]["mask_mode"] == "ink_components"
    assert operation["cover_updates"]["fallback"] == "caption_panel_operator_approved"
    assert operation["damage_budget_changed"] is False


def test_drops_only_hash_guarded_duplicate_output_residual_track(tmp_path) -> None:
    coverage = {
        "status": "OPERATOR_APPROVED_SOURCE_TEMPLATE_VERIFIED",
        "source_text": "花生油 45千卡/5.00毫升",
    }
    target = {
        "text_id": "p4out_target",
        "text_vi": "Dầu đậu phộng 45 kcal/5.00 ml",
        "start_frame": 615,
        "end_frame": 618,
        "geometry": {"x": 0.18, "y": 0.05, "width": 0.22, "height": 0.07},
        "output_residual_coverage": coverage,
    }
    duplicate = {
        **target,
        "text_id": "p4out_existing",
        "geometry": {"x": 0.182, "y": 0.052, "width": 0.215, "height": 0.068},
    }

    operation = _build_operation(
        case_root=tmp_path,
        contract={"render_tracks": [target, duplicate]},
        decision={
            "text_id": "p4out_target",
            "decision": {
                "action": "DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK",
                "duplicate_track_id": "p4out_existing",
            },
        },
    )

    assert operation["operation"] == "DROP_TRACK"
    assert operation["target_text_id"] == "p4out_target"
    assert operation["duplicate_track_id"] == "p4out_existing"
    assert operation["geometry_overlap_over_smaller"] >= 0.70


def test_trims_p4out_track_before_operator_confirmed_source_change(tmp_path) -> None:
    track = {
        "text_id": "p4out_shrimp",
        "start_frame": 615,
        "end_frame": 682,
        "text_vi": "Tôm 99 kcal/106.00 g",
    }

    operation = _build_operation(
        case_root=tmp_path,
        contract={"render_tracks": [track]},
        decision={
            "text_id": "p4out_shrimp",
            "frame_index": 680,
            "decision": {
                "action": "TRIM_OUTPUT_RESIDUAL_TRACK_BEFORE_CONFIRMED_SOURCE_CHANGE"
            },
        },
    )

    assert operation["operation"] == "TIMING_OVERRIDE"
    assert operation["original_window"] == [615, 682]
    assert operation["replacement_window"] == [615, 679]
    assert operation["confirmed_source_change_frame"] == 680


def test_builds_stylized_mask_only_for_aligned_exact_residual(tmp_path) -> None:
    track = {
        "text_id": "p4out_exact",
        "render_policy": {
            "context": {
                "output_residual_geometry_aligned": True,
                "output_residual_width_expanded": True,
            },
            "cover": {"mask_mode": "ink_components"},
        },
    }

    operation = _build_operation(
        case_root=tmp_path,
        contract={"render_tracks": [track]},
        decision={
            "text_id": "p4out_exact",
            "decision": {
                "action": "BOUNDED_EXACT_RESIDUAL_STYLIZED_COMPONENT_MASK"
            },
        },
    )

    assert operation["operation"] == "POLICY_OVERRIDE"
    assert operation["cover_updates"]["mask_mode"] == "stylized_components"
    assert operation["damage_budget_changed"] is False


def _approved_residual_track(text_id: str, *, x: float = 0.2) -> dict:
    return {
        "text_id": text_id,
        "text_vi": "Phan an duoc",
        "start_frame": 525,
        "end_frame": 614,
        "geometry": {"x": x, "y": 0.1, "width": 0.2, "height": 0.05},
        "output_residual_coverage": {
            "status": "OPERATOR_APPROVED_SOURCE_TEMPLATE_VERIFIED",
            "source_text": "edible portion",
        },
    }


def test_materializes_hash_bound_duplicate_track_group(tmp_path) -> None:
    tracks = [
        _approved_residual_track("p4out_aligned"),
        _approved_residual_track("p4out_old_a", x=0.205),
        _approved_residual_track("p4out_old_b", x=0.21),
    ]

    operation = _build_operation(
        case_root=tmp_path,
        contract={"render_tracks": tracks},
        decision={
            "text_id": "p4out_old_b",
            "decision": {
                "action": "DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK_GROUP",
                "canonical_track_id": "p4out_aligned",
                "drop_track_ids": ["p4out_old_a", "p4out_old_b"],
            },
        },
    )

    assert operation["operation"] == "DROP_TRACK_GROUP"
    assert operation["canonical_track_id"] == "p4out_aligned"
    assert [row["target_text_id"] for row in operation["targets"]] == [
        "p4out_old_a",
        "p4out_old_b",
    ]
    assert all(
        len(row["expected_track_sha256"]) == 64 for row in operation["targets"]
    )


def test_group_materialization_fails_closed_on_source_drift(tmp_path) -> None:
    canonical = _approved_residual_track("p4out_aligned")
    drifted = _approved_residual_track("p4out_old")
    drifted["output_residual_coverage"]["source_text"] = "different source"

    with pytest.raises(Phase4RemediationMaterializationError):
        _build_operation(
            case_root=tmp_path,
            contract={"render_tracks": [canonical, drifted]},
            decision={
                "decision": {
                    "action": "DROP_DUPLICATE_OUTPUT_RESIDUAL_TRACK_GROUP",
                    "canonical_track_id": "p4out_aligned",
                    "drop_track_ids": ["p4out_old"],
                }
            },
        )
