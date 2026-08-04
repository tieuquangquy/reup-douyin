from __future__ import annotations

import pytest

from scripts.build_phase4_output_residual_review import (
    OutputResidualReviewError,
    classify_cluster,
    failed_residual_output_paths,
    output_stem_for_review_version,
    refine_small_source_bound_cluster,
)


def _cluster(text: str, confidence: float = 0.99) -> dict:
    return {
        "signature": text,
        "detections": [
            {
                "frame_index": 10,
                "text": text,
                "confidence": confidence,
                "geometry": {
                    "x": 0.1,
                    "y": 0.8,
                    "width": 0.2,
                    "height": 0.05,
                },
            }
        ],
    }


def test_carries_forward_exact_approved_content() -> None:
    source_text = "\u4e2d\u5f0f\u51cf\u8102\u9910"
    result = classify_cluster(
        _cluster(source_text),
        content_objects=[
            {
                "content_id": "content_01",
                "ocr_text_approved": source_text,
            }
        ],
        render_tracks=[
            {
                "text_id": "sub_01",
                "content_id": "content_01",
                "start_frame": 0,
                "end_frame": 20,
                "geometry": {"x": 0.1, "y": 0.8, "width": 0.2, "height": 0.05},
                "text_vi": "MÃ³n giáº£m cÃ¢n kiá»ƒu Trung",
                "translation_status": "TRANSLATION_APPROVED",
            }
        ],
        suggestions={},
    )

    assert result["decision"] == "CARRY_FORWARD_APPROVED_CONTENT_COVERAGE"
    assert result["translation_authority"] == "EXISTING_EXACT_APPROVAL"


def test_low_confidence_single_detection_routes_to_false_positive_review() -> None:
    result = classify_cluster(
        _cluster("\u798f", confidence=0.4),
        content_objects=[],
        render_tracks=[],
        suggestions={},
    )

    assert result["decision"] == "FALSE_POSITIVE_REVIEW"
    assert result["vi_text_suggested"] is None


def test_output_stem_is_derived_from_review_version() -> None:
    assert (
        output_stem_for_review_version("V22_42")
        == "phase4_output_residual_review_v22_42"
    )
    assert (
        output_stem_for_review_version("v22_40_2_1")
        == "phase4_output_residual_review_v22_40_2_1"
    )


def test_output_stem_rejects_unsafe_review_version() -> None:
    with pytest.raises(OutputResidualReviewError, match="Invalid review version"):
        output_stem_for_review_version("../../v22_42")


def test_failed_final_output_is_preferred_over_preview(tmp_path) -> None:
    qa = tmp_path / "qa"
    qa.mkdir()
    for stem in ("phase4_adaptive_visual_preview", "phase4_adaptive_final"):
        (tmp_path / f"{stem}.mp4").write_bytes(b"video")
        (qa / f"{stem}_output_qa.json").write_text(
            '{"status":"FAIL","failed_checks":["residual_cjk"]}',
            encoding="utf-8",
        )

    selected = failed_residual_output_paths(tmp_path)

    assert selected is not None
    assert selected[0].name == "phase4_adaptive_final_output_qa.json"
    assert selected[1].name == "phase4_adaptive_final.mp4"


def test_unchanged_small_scene_glyph_is_not_sent_to_translation() -> None:
    result = refine_small_source_bound_cluster(
        {
            "decision": "TRANSLATION_INPUT_AND_COVERAGE_REVIEW",
            "active_intersections": [],
            "translation_authority": "NONE",
        },
        cluster={"signature": "福"},
        representative={
            "geometry": {"x": 0.48, "y": 0.55, "width": 0.03, "height": 0.07}
        },
        crop_mean_abs_delta=2.1,
    )

    assert result["decision"] == "FALSE_POSITIVE_REVIEW"
    assert result["source_binding"] == "UNCHANGED_SMALL_SCENE_TEXTURE"
