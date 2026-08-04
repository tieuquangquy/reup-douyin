from __future__ import annotations

import hashlib
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from scripts.materialize_phase4_output_coverage_decisions import (
    OutputCoverageMaterializationError,
    _bind_operator_source_template,
    _contact_sheet_source_half,
    _image_similarity_metrics,
    _is_verified_source_status,
    _match_source_cluster_full_frame,
    _match_source_template_frame,
    _merge_added_track_operations,
    _micro_ui_reference_overrides,
    _output_residual_alignment_overrides,
    _tracks_from_verified,
    _review_source_crop,
    _template_hit_window,
)


class _Provider:
    provider_name = "local-test"

    def __init__(self, text: str) -> None:
        self.text = text

    def detect_frame(self, _path, *, frame_time_ms: int):
        assert frame_time_ms == 100
        return SimpleNamespace(
            boxes=[
                SimpleNamespace(
                    text=self.text,
                    confidence=0.99,
                    x=0.0,
                    y=0.80,
                    width=0.60,
                    height=0.05,
                )
            ]
        )


class _FrameCache:
    def __init__(self, frames: dict[int, np.ndarray]) -> None:
        self.frames = frames

    def get(self, frame_index: int) -> np.ndarray:
        return self.frames[int(frame_index)]


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _template_candidate(evidence_ref: dict[str, str]) -> dict:
    geometry = {"x": 0.2, "y": 0.2, "width": 0.4, "height": 0.3}
    return {
        "decision": {
            "geometry_strategy": "OPERATOR_CONFIRMED_SOURCE_TEMPLATE_V1",
            "operator_confirmed_source_template_required": True,
            "source_boundary_failure_count": 2,
            "source_boundary_failure_history": [{"sha256": "a"}, {"sha256": "b"}],
            "representative_frame_index": 3,
            "evidence_ref": evidence_ref,
        },
        "cluster": {
            "evidence": {"source_render_contact_sheet": evidence_ref},
        },
        "representative": {"frame_index": 3, "geometry": geometry},
    }


def test_full_frame_rescue_accepts_only_approved_exact_substring() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    residual = {
        "signature": "中式減脂餐",
        "approved_signatures": ["中式減脂餐", "中式减脂餐"],
        "anchor_rect": (0.0, 0.80, 0.20, 0.85),
    }
    match = _match_source_cluster_full_frame(
        frame,
        residual,
        provider=_Provider("中式减脂餐虾仁豆腐蒸蛋"),
        frame_time_ms=100,
    )

    assert match is not None
    assert match["match_mode"] == "APPROVED_SIGNATURE_IN_MERGED_OCR_ROW"
    assert match["geometry"]["x"] == pytest.approx(0.0)
    assert match["geometry"]["y"] == pytest.approx(0.80)
    assert match["geometry"]["width"] == pytest.approx(0.20)
    assert match["geometry"]["height"] == pytest.approx(0.05)
    rejected = _match_source_cluster_full_frame(
        frame,
        residual,
        provider=_Provider("中式虾仁豆腐"),
        frame_time_ms=100,
    )
    assert rejected is None


def test_long_verified_micro_ui_gets_bounded_dense_policy_override() -> None:
    track = {
        "text_id": "p4out_test",
        "start_frame": 10,
        "end_frame": 30,
        "geometry": {"x": 0.1, "y": 0.8, "width": 0.2, "height": 0.04},
        "render_policy": {
            "context": {"micro_ui": True},
            "cover": {"mask_mode": "ink_components"},
        },
    }
    operations = _micro_ui_reference_overrides([track])

    assert len(operations) == 1
    assert operations[0]["operation"] == "POLICY_OVERRIDE"
    assert operations[0]["context_updates"][
        "output_residual_bounded_dense_mask"
    ] is True
    assert operations[0]["cover_updates"] == {}


def test_readded_track_replaces_parent_add_before_dependent_override() -> None:
    old_add = {
        "operation": "ADD_TRACK",
        "track": {"text_id": "p4out_test", "text_vi": "old"},
        "expected_added_track_sha256": "old",
    }
    dependent_override = {
        "operation": "POLICY_OVERRIDE",
        "target_text_id": "p4out_test",
        "expected_track_sha256": "new",
        "context_updates": {"output_residual_bounded_dense_mask": True},
        "cover_updates": {},
        "damage_budget_changed": False,
    }
    unrelated = {"operation": "DROP_TRACK", "target_text_id": "other"}
    replacement = {
        "operation": "ADD_TRACK",
        "track": {"text_id": "p4out_test", "text_vi": "new"},
        "expected_added_track_sha256": "new",
    }

    operations = _merge_added_track_operations(
        [unrelated, old_add, dependent_override],
        [replacement],
    )

    assert operations == [unrelated, replacement]


def test_readded_track_keeps_distinct_parent_override() -> None:
    old_add = {
        "operation": "ADD_TRACK",
        "track": {"text_id": "p4out_test", "text_vi": "old"},
    }
    distinct_override = {
        "operation": "POLICY_OVERRIDE",
        "target_text_id": "p4out_test",
        "context_updates": {"manual_distinct_policy": True},
        "cover_updates": {},
        "damage_budget_changed": False,
    }
    replacement = {
        "operation": "ADD_TRACK",
        "track": {"text_id": "p4out_test", "text_vi": "new"},
    }

    assert _merge_added_track_operations(
        [old_add, distinct_override], [replacement]
    ) == [replacement, distinct_override]


def test_new_track_is_appended_when_parent_has_no_matching_add() -> None:
    unrelated = {"operation": "DROP_TRACK", "target_text_id": "other"}
    addition = {
        "operation": "ADD_TRACK",
        "track": {"text_id": "p4out_new", "text_vi": "new"},
        "expected_added_track_sha256": "new",
    }

    assert _merge_added_track_operations([unrelated], [addition]) == [
        unrelated,
        addition,
    ]


def test_contact_sheet_source_crop_binding_is_hash_and_metric_ready(tmp_path) -> None:
    x = np.linspace(20, 220, 120, dtype=np.uint8)
    y = np.linspace(10, 80, 100, dtype=np.uint8)[:, None]
    frame = np.dstack(
        [
            np.broadcast_to(x, (100, 120)),
            np.broadcast_to(y, (100, 120)),
            np.broadcast_to((x // 2) + y, (100, 120)),
        ]
    ).astype(np.uint8)
    cv2.putText(
        frame,
        "OCR",
        (28, 45),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    geometry = {"x": 0.2, "y": 0.2, "width": 0.4, "height": 0.3}
    source_crop = _review_source_crop(frame, geometry)
    divider = np.full((source_crop.shape[0], 8, 3), 255, dtype=np.uint8)
    contact = np.hstack([source_crop, divider, source_crop])
    evidence_path = tmp_path / "contact.jpg"
    assert cv2.imwrite(str(evidence_path), contact)
    decoded = cv2.imread(str(evidence_path))
    approved_source = _contact_sheet_source_half(
        decoded, expected_shape=source_crop.shape
    )
    metrics = _image_similarity_metrics(source_crop, approved_source)

    assert metrics["mad"] < 5.0
    assert metrics["ssim"] > 0.95
    assert metrics["ncc"] > 0.97
    ref = {"path": evidence_path.name, "sha256": _sha256(evidence_path)}
    binding = _bind_operator_source_template(
        case_root=tmp_path,
        candidate=_template_candidate(ref),
        frame_cache=_FrameCache({3: frame}),
    )
    assert binding["contact_sheet_ref"] == ref
    assert binding["template_stddev"] > 8.0


def test_source_template_match_is_bounded_and_tracks_shift() -> None:
    rng = np.random.default_rng(7)
    template = rng.integers(0, 255, size=(20, 30), dtype=np.uint8)
    frame = np.zeros((100, 120, 3), dtype=np.uint8)
    shifted_rect = (43, 34, 73, 54)
    frame[
        shifted_rect[1] : shifted_rect[3], shifted_rect[0] : shifted_rect[2]
    ] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)

    result = _match_source_template_frame(
        frame,
        template_gray=template,
        predicted_rect=(40, 30, 70, 50),
    )

    assert result["hit"] is True
    assert result["rect"] == shifted_rect
    assert result["ncc"] > 0.99


def test_template_hit_window_requires_immediate_negative_evidence() -> None:
    result = _template_hit_window(
        [11, 12, 13], anchor_frame=12, scan_start=10, scan_end=14
    )
    assert result == (11, 13, [11, 12, 13], 10, 14)

    with pytest.raises(
        OutputCoverageMaterializationError,
        match="negative evidence is incomplete",
    ):
        _template_hit_window(
            [10, 11, 12, 13], anchor_frame=12, scan_start=10, scan_end=14
        )


def test_source_template_rejects_low_variance_roi(tmp_path) -> None:
    frame = np.full((100, 120, 3), 128, dtype=np.uint8)
    geometry = {"x": 0.2, "y": 0.2, "width": 0.4, "height": 0.3}
    source_crop = _review_source_crop(frame, geometry)
    divider = np.full((source_crop.shape[0], 8, 3), 255, dtype=np.uint8)
    evidence_path = tmp_path / "contact.jpg"
    assert cv2.imwrite(
        str(evidence_path), np.hstack([source_crop, divider, source_crop])
    )
    ref = {"path": evidence_path.name, "sha256": _sha256(evidence_path)}

    with pytest.raises(
        OutputCoverageMaterializationError,
        match="insufficient visual variance",
    ):
        _bind_operator_source_template(
            case_root=tmp_path,
            candidate=_template_candidate(ref),
            frame_cache=_FrameCache({3: frame}),
        )


def test_resume_counts_both_source_verification_statuses() -> None:
    assert _is_verified_source_status("SOURCE_BOUNDARY_VERIFIED") is True
    assert _is_verified_source_status("SOURCE_TEMPLATE_OPERATOR_VERIFIED") is True
    assert _is_verified_source_status("SOURCE_BOUNDARY_VALIDATION_FAILED") is False


def test_reuses_equivalent_operator_verified_output_coverage_track() -> None:
    geometry = {"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.05}
    existing = {
        "text_id": "p4out_existing",
        "start_frame": 10,
        "end_frame": 20,
        "geometry": geometry,
        "text_vi": "Giờ ăn",
        "output_residual_coverage": {
            "status": "OPERATOR_APPROVED_SOURCE_BOUNDARY_VERIFIED",
            "source_text": "用餐时间",
        },
    }
    verified = {
        "cluster_id": "outres_new",
        "content_id": "content_new",
        "source_text": "用餐时间",
        "vi_text": "Giờ ăn",
        "start_frame": 10,
        "end_frame": 20,
        "best_frame_index": 15,
        "geometry": geometry,
        "output_residual_geometry": {
            "x": 0.11,
            "y": 0.26,
            "width": 0.2,
            "height": 0.05,
        },
        "verification_status": "SOURCE_BOUNDARY_VERIFIED",
        "attempt_evidence_ref": {"path": "evidence.jpg", "sha256": "a" * 64},
    }

    tracks, reused = _tracks_from_verified(
        verified=[verified], existing_tracks=[existing], fps=30.0
    )

    assert tracks == []
    assert reused[0]["equivalent_text_id"] == "p4out_existing"
    assert reused[0]["geometry_overlap_over_smaller"] == 1.0
    assert reused[0]["output_residual_geometry"]["y"] == 0.26


def test_reuses_semantically_equivalent_base_track_without_output_coverage_marker() -> None:
    geometry = {"x": 0.43, "y": 0.34, "width": 0.09, "height": 0.06}
    existing = {
        "text_id": "sub_05",
        "content_id": "ocr_content_005",
        "start_frame": 215,
        "end_frame": 266,
        "geometry": geometry,
        "text_vi": "Khối lượng tịnh: 150 g",
    }
    verified = {
        "cluster_id": "outres_repeat",
        "content_id": "p4out_content_repeat",
        "source_text": "净含量：150克",
        "vi_text": "  KHỐI LƯỢNG TỊNH: 150 g ",
        "start_frame": 215,
        "end_frame": 266,
        "best_frame_index": 240,
        "geometry": geometry,
        "verification_status": "SOURCE_BOUNDARY_VERIFIED",
        "attempt_evidence_ref": {"path": "evidence.jpg", "sha256": "a" * 64},
    }

    tracks, reused = _tracks_from_verified(
        verified=[verified], existing_tracks=[existing], fps=30.0
    )

    assert tracks == []
    assert reused[0]["equivalent_text_id"] == "sub_05"


def test_keeps_distinct_geometry_as_new_output_coverage_track() -> None:
    existing = {
        "text_id": "p4out_existing",
        "start_frame": 10,
        "end_frame": 20,
        "geometry": {"x": 0.1, "y": 0.2, "width": 0.2, "height": 0.05},
        "text_vi": "Giờ ăn",
        "output_residual_coverage": {
            "status": "OPERATOR_APPROVED_SOURCE_BOUNDARY_VERIFIED",
            "source_text": "用餐时间",
        },
    }
    verified = {
        "cluster_id": "outres_new",
        "content_id": "content_new",
        "source_text": "用餐时间",
        "vi_text": "Giờ ăn",
        "start_frame": 10,
        "end_frame": 20,
        "best_frame_index": 15,
        "geometry": {"x": 0.6, "y": 0.2, "width": 0.2, "height": 0.05},
        "verification_status": "SOURCE_BOUNDARY_VERIFIED",
        "attempt_evidence_ref": {"path": "evidence.jpg", "sha256": "a" * 64},
    }

    tracks, reused = _tracks_from_verified(
        verified=[verified], existing_tracks=[existing], fps=30.0
    )

    assert len(tracks) == 1
    assert reused == []


def test_same_attempt_equivalent_track_can_receive_alignment_override() -> None:
    base = {
        "content_id": "content_pumpkin",
        "source_text": "pumpkin source",
        "vi_text": "Bi do",
        "start_frame": 10,
        "end_frame": 20,
        "best_frame_index": 15,
        "geometry": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.05},
        "output_residual_geometry": {
            "x": 0.21,
            "y": 0.31,
            "width": 0.18,
            "height": 0.04,
        },
        "residual_signature": "pumpkinsource",
        "verification_status": "SOURCE_TEMPLATE_OPERATOR_VERIFIED",
        "attempt_evidence_ref": {"path": "evidence.jpg", "sha256": "a" * 64},
    }
    first = {**base, "cluster_id": "outres_first"}
    second = {
        **base,
        "cluster_id": "outres_second",
        "content_id": "content_pumpkin_variant",
        "output_residual_geometry": {
            "x": 0.212,
            "y": 0.35,
            "width": 0.18,
            "height": 0.04,
        },
    }

    tracks, reused = _tracks_from_verified(
        verified=[first, second], existing_tracks=[], fps=30.0
    )
    operations = _output_residual_alignment_overrides(
        reused, tracks
    )

    assert len(tracks) == 1
    assert len(reused) == 1
    assert reused[0]["equivalent_text_id"] == tracks[0]["text_id"]
    assert reused[0]["equivalent_is_same_attempt"] is True
    assert len(operations) == 1
    assert operations[0]["target_text_id"] == tracks[0]["text_id"]
    roi = operations[0]["cover_updates"]["roi"]
    original_roi = tracks[0]["render_policy"]["cover"]["roi"]
    assert roi["y"] <= original_roi["y"]
    assert roi["y"] + roi["height"] == pytest.approx(0.398)


def test_aligns_reused_cover_roi_to_encoded_residual_without_relaxing_budget() -> None:
    target = {
        "text_id": "p4out_existing",
        "render_policy": {
            "context": {"output_residual_bounded_dense_mask": True},
            "cover": {
                "roi": {"x": 0.10, "y": 0.20, "width": 0.06, "height": 0.08},
                "mask_mode": "ink_components",
            },
            "damage_budget": {"max_frame_change_fraction": 0.55},
        },
    }
    reused = {
        "equivalent_text_id": "p4out_existing",
        "cluster_ids": ["outres_new"],
        "output_residual_geometry": {
            "x": 0.12,
            "y": 0.26,
            "width": 0.20,
            "height": 0.05,
        },
    }

    operations = _output_residual_alignment_overrides([reused], [target])

    assert len(operations) == 1
    operation = operations[0]
    assert operation["operation"] == "POLICY_OVERRIDE"
    assert operation["cover_updates"]["roi"] == {
        "x": 0.11399999999999999,
        "y": 0.252,
        "width": 0.06,
        "height": 0.08,
    }
    assert operation["context_updates"]["output_residual_geometry_aligned"] is True
    assert operation["damage_budget_changed"] is False


def test_expands_only_exact_residual_signature_width() -> None:
    target = {
        "text_id": "p4out_edible",
        "render_policy": {
            "cover": {
                "roi": {"x": 0.21, "y": 0.64, "width": 0.042, "height": 0.074},
            }
        },
    }
    reused = {
        "equivalent_text_id": "p4out_edible",
        "cluster_ids": ["outres_edible"],
        "source_text": "可食部",
        "residual_signature": "可食部",
        "output_residual_geometry": {
            "x": 0.216,
            "y": 0.702,
            "width": 0.122,
            "height": 0.043,
        },
    }

    operation = _output_residual_alignment_overrides([reused], [target])[0]

    assert operation["cover_updates"]["roi"]["width"] == 0.134
    assert operation["context_updates"]["output_residual_width_expanded"] is True
    assert operation["damage_budget_changed"] is False


def test_recovers_width_expansion_when_roi_is_already_expanded() -> None:
    target = {
        "text_id": "p4out_edible",
        "render_policy": {
            "context": {"output_residual_width_expanded": False},
            "cover": {
                "roi": {"x": 0.21, "y": 0.64, "width": 0.1345, "height": 0.074},
            },
        },
    }
    reused = {
        "equivalent_text_id": "p4out_edible",
        "cluster_ids": ["outres_edible_followup"],
        "source_text": "å¯é£Ÿéƒ¨",
        "residual_signature": "å¯é£Ÿéƒ¨",
        "output_residual_geometry": {
            "x": 0.216,
            "y": 0.702,
            "width": 0.1225,
            "height": 0.043,
        },
    }
    reused["source_text"] = "\u53ef\u98df\u90e8"
    reused["residual_signature"] = "\u53ef\u98df\u90e8"

    operation = _output_residual_alignment_overrides([reused], [target])[0]

    assert operation["context_updates"]["output_residual_geometry_aligned"] is True
    assert operation["context_updates"]["output_residual_width_expanded"] is True
