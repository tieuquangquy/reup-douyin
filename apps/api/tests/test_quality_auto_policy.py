from __future__ import annotations

import pytest
from fastapi import HTTPException
from types import SimpleNamespace
from unittest.mock import patch

from src.services.quality_auto_policy import (
    QualityAutoPolicyBlocked,
    assert_audio_ready,
    build_ocr_decisions,
    build_translation_decisions,
    translate_residual_texts,
)
from src.api.routes.ocr import OcrDecision, _validate_ocr_review_decisions


def test_ocr_policy_approves_editor_overlay_and_preserves_source_text() -> None:
    decisions = build_ocr_decisions(
        [
            {
                "content_id": "editor",
                "ocr_text_candidate": "字幕",
                "provenance_classifications": ["EDITOR_OVERLAY"],
            },
            {
                "content_id": "phone_ui",
                "ocr_text_candidate": "设置",
                "provenance_classifications": ["SOURCE_INTRINSIC_PANEL"],
            },
        ]
    )

    assert [row["decision"] for row in decisions] == ["APPROVE", "PRESERVE_SOURCE"]


def test_ocr_policy_blocks_ambiguous_provenance() -> None:
    with pytest.raises(QualityAutoPolicyBlocked, match="ambiguous"):
        build_ocr_decisions(
            [
                {
                    "content_id": "mixed",
                    "ocr_text_candidate": "文本",
                    "provenance_classifications": [
                        "EDITOR_OVERLAY",
                        "SOURCE_INTRINSIC",
                    ],
                }
            ]
        )


def test_ocr_policy_blocks_empty_editor_candidate_before_job_enqueue() -> None:
    with pytest.raises(HTTPException, match="requires non-empty approved text"):
        _validate_ocr_review_decisions(
            [OcrDecision(content_id="ocr_content_044", decision="APPROVE", ocr_text_approved="")]
        )


def test_ocr_review_allows_explicit_false_detection_for_empty_candidate() -> None:
    _validate_ocr_review_decisions(
        [OcrDecision(content_id="ocr_content_044", decision="REJECT_UI", ocr_text_approved=None)]
    )


def test_translation_policy_uses_existing_candidate_without_retranslation() -> None:
    assert build_translation_decisions(
        [{"content_id": "c1", "vi_text_candidate": "Bản dịch"}]
    ) == [{"content_id": "c1", "vi_text": "Bản dịch"}]


def test_audio_policy_accepts_staged_mix_with_resolved_timing() -> None:
    assert_audio_ready(
        {
            "workflow_stage": "WAITING_AUDIO_REVIEW",
            "audio_mix_preview_path": "phase4_audio_mix_preview.wav",
            "timing_fit_summary": {"fits_well": 12},
        }
    )


def test_audio_policy_reuses_hash_bound_approved_cache_on_visual_resume() -> None:
    assert_audio_ready(
        {
            "workflow_stage": "AUDIO_APPROVED",
            "audio_review_status": "AUDIO_APPROVED",
            "audio_mix_review_status": "AUDIO_APPROVED",
            "audio_mix_preview_path": None,
            "timing_fit_summary": {"fits_well": 21, "too_short": 1},
        }
    )


def test_audio_policy_blocks_unresolved_timing() -> None:
    with pytest.raises(QualityAutoPolicyBlocked, match="too_long=1"):
        assert_audio_ready(
            {
                "workflow_stage": "WAITING_AUDIO_REVIEW",
                "audio_mix_preview_path": "phase4_audio_mix_preview.wav",
                "timing_fit_summary": {"fits_well": 11, "too_long": 1},
            }
        )


def test_residual_policy_returns_ocr_correction_and_translation_in_one_batch() -> None:
    completion = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"residual_001":{"zh_corrected":"百搭日常妆","vi_text":"Trang điểm hằng ngày"}}'
                )
            )
        ]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_kwargs: completion)
        )
    )
    settings = SimpleNamespace(model_name="model", api_key="key", base_url="url")
    with patch(
        "src.media_pipeline.translator.resolve.resolve_translator_settings",
        return_value=settings,
    ), patch(
        "src.media_pipeline.translator.client.build_openai_client",
        return_value=client,
    ):
        suggestions = translate_residual_texts(
            db=object(),
            workspace_id=object(),
            residual_objects=[{"text": "百搭昌常妆"}],
        )

    assert suggestions == [
        {
            "content_id": "residual_001",
            "ocr_text": "百搭昌常妆",
            "ocr_text_corrected": "百搭日常妆",
            "vi_text_suggested": "Trang điểm hằng ngày",
        }
    ]


def test_residual_policy_reuses_cached_suggestion_when_provider_is_temporarily_down() -> None:
    settings = SimpleNamespace(model_name="model", api_key="key", base_url="url")
    with patch(
        "src.media_pipeline.translator.resolve.resolve_translator_settings",
        return_value=settings,
    ), patch(
        "src.media_pipeline.translator.client.build_openai_client",
        side_effect=RuntimeError("HTTP 500"),
    ):
        suggestions = translate_residual_texts(
            db=object(),
            workspace_id=object(),
            residual_objects=[{"text": "百搭昌常妆"}],
            fallback_suggestions=[
                {
                    "ocr_text": "百搭昌常妆",
                    "ocr_text_corrected": "百搭日常妆",
                    "vi_text_suggested": "Trang điểm hằng ngày dễ phối",
                }
            ],
        )
    assert suggestions[0]["ocr_text_corrected"] == "百搭日常妆"
