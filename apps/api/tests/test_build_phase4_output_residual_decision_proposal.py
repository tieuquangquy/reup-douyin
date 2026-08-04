import json

from scripts.build_phase4_output_residual_decision_proposal import (
    OPERATOR_SOURCE_TEMPLATE_STRATEGY,
    _sha256_json,
    approved_translation_from_phase3,
    decision_for_cluster,
    geometry_strategy_for_history,
    source_boundary_failure_history,
)


def test_reuses_phase3_approved_translation_for_output_tail(tmp_path) -> None:
    (tmp_path / "phase3_translation_timeline.json").write_text(
        json.dumps(
            {
                "content_objects": [
                    {
                        "content_id": "ocr_content_027",
                        "zh_approved": "点点水防止糊锅",
                        "vi_text_approved": "Thêm chút nước, tránh cháy chảo",
                        "review_status": "TRANSLATION_APPROVED",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cluster = {
        "recommendation": {
            "content_ids": ["ocr_content_027"],
            "source_text_suggested": "点点水防止糊锅",
        }
    }

    suggestion = approved_translation_from_phase3(tmp_path, cluster)

    assert suggestion is not None
    assert suggestion["source_text_corrected"] == "点点水防止糊锅"
    assert suggestion["vi_text_suggested"] == "Thêm chút nước, tránh cháy chảo"


def test_maps_translation_suggestion_to_approval_proposal() -> None:
    decision = decision_for_cluster(
        {
            "cluster_id": "cluster_1",
            "representative_frame_index": 10,
            "recommendation": {
                "decision": "TRANSLATION_INPUT_AND_COVERAGE_REVIEW",
                "source_text_suggested": "raw",
            },
            "evidence": {},
        },
        translation_suggestion={
            "suggestion_status": "TRANSLATION_SUGGESTION_ONLY",
            "source_text_corrected": "corrected",
            "vi_text_suggested": "Bản dịch",
        },
    )

    assert decision["proposed_action"] == "APPROVE_TRANSLATION_SUGGESTION_AND_COVERAGE"
    assert decision["source_text_suggested"] == "corrected"
    assert decision["temporal_strategy"] == "SOURCE_BOUNDARY_RESCAN_REQUIRED"


def test_maps_mixed_ocr_to_false_positive_proposal() -> None:
    decision = decision_for_cluster(
        {
            "cluster_id": "cluster_2",
            "recommendation": {
                "decision": "TRANSLATION_INPUT_AND_COVERAGE_REVIEW",
            },
            "evidence": {},
        },
        translation_suggestion={
            "suggestion_status": "MIXED_RENDER_OCR_FALSE_POSITIVE_CANDIDATE",
            "source_text_observed": "mixed",
        },
    )

    assert decision["proposed_action"] == "APPROVE_RESIDUAL_FALSE_POSITIVE"
    assert decision["temporal_strategy"] == "NOT_APPLICABLE"


def test_maps_deterministic_numeric_correction_to_ocr_carry_forward() -> None:
    decision = decision_for_cluster(
        {
            "cluster_id": "cluster_numeric",
            "recommendation": {
                "decision": "DETERMINISTIC_LOCALIZATION_AND_COVERAGE_REVIEW",
                "source_text_suggested": "17000克",
                "vi_text_suggested": "17000 g",
            },
            "evidence": {},
        },
        translation_suggestion={
            "suggestion_status": "TRANSLATION_SUGGESTION_ONLY",
            "source_text_corrected": "170.00克",
            "vi_text_suggested": "170.00 g",
        },
    )

    assert decision["proposed_action"] == "CORRECT_OCR_AND_CARRY_FORWARD_COVERAGE"
    assert decision["source_text_suggested"] == "170.00克"


def test_curated_reclassification_overrides_bad_near_match_ocr_correction() -> None:
    decision = decision_for_cluster(
        {
            "cluster_id": "cluster_bad_near_match",
            "recommendation": {
                "decision": "SOURCE_OCR_CORRECTION_AND_COVERAGE_REVIEW",
                "source_text_suggested": "0\u514b",
                "vi_text_suggested": "0 g",
                "translation_authority": "EXISTING_NEAR_MATCH_REQUIRES_OCR_REVIEW",
            },
            "evidence": {},
        },
        translation_suggestion={
            "suggestion_status": "TRANSLATION_SUGGESTION_ONLY",
            "source_text_corrected": "\u9e21\u80f8\u8089 208\u5343\u5361/176.00\u514b",
            "vi_text_suggested": "\u1ee8c g\u00e0 208 kcal/176.00 g",
        },
    )

    assert decision["proposed_action"] == (
        "APPROVE_TRANSLATION_SUGGESTION_AND_COVERAGE"
    )
    assert decision["source_text_suggested"] == (
        "\u9e21\u80f8\u8089 208\u5343\u5361/176.00\u514b"
    )
    assert decision["vi_text_suggested"] == "\u1ee8c g\u00e0 208 kcal/176.00 g"
    assert decision["translation_authority"] == (
        "CURATED_SOURCE_OCR_RECLASSIFICATION"
    )


def test_repeated_hash_valid_source_failures_select_operator_template_strategy(
    tmp_path,
) -> None:
    for index in (1, 2):
        payload = {
            "authority_refs": {
                "decision_approval": {"approval_sha256": str(index) * 64}
            },
            "attempts": [
                {
                    "cluster_id": "outres_repeat",
                    "source_text": "\u8bf7\u9009\u62e9\u98df\u7269",
                    "status": "SOURCE_BOUNDARY_VALIDATION_FAILED",
                    "failure_reason": (
                        "No approved residual frame matched exact source OCR"
                    ),
                }
            ],
        }
        payload["rescan_sha256"] = _sha256_json(payload)
        (tmp_path / f"phase4_output_source_boundary_rescan_v{index}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    history = source_boundary_failure_history(
        tmp_path,
        cluster_id="outres_repeat",
        source_text="\u8bf7\u9009\u62e9\u98df\u7269",
    )

    assert len(history) == 2
    assert geometry_strategy_for_history(history) == OPERATOR_SOURCE_TEMPLATE_STRATEGY
