from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.enums import TranscriptSegmentStatus
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.services.translation_input_resolver import TranslationInputResolver


def _translation(status: TranscriptSegmentStatus):
    source_id = uuid4()
    transcript = SimpleNamespace(id=uuid4(), start_ms=0, end_ms=4_000, segment_index=0)
    return SimpleNamespace(
        id=uuid4(),
        source_video_id=source_id,
        transcript_segment=transcript,
        segment_index=0,
        text="Bản fallback cần duyệt",
        duration_budget_ms=4_000,
        version=1,
        translation_preset="literal_safe",
        quality_flags_json={"flags": ["machine_translate_recovery", "needs_operator_review"]},
        status=status,
    )


def test_unapproved_machine_translation_never_reaches_tts_provider() -> None:
    row = _translation(TranscriptSegmentStatus.NEEDS_REVIEW)
    db = MagicMock()
    db.scalars.return_value = [row]

    with pytest.raises(TtsPipelineError) as raised:
        TranslationInputResolver(db).resolve(row.source_video_id)

    assert raised.value.code == TtsPipelineErrorCode.TRANSLATION_REVIEW_REQUIRED


def test_operator_approved_machine_translation_can_enter_tts() -> None:
    row = _translation(TranscriptSegmentStatus.APPROVED)
    db = MagicMock()
    db.scalars.return_value = [row]

    segments = TranslationInputResolver(db).resolve(row.source_video_id)

    assert len(segments) == 1
    assert segments[0].translated_text == row.text


def test_v3_ranked_candidates_are_available_for_selective_tts_correction() -> None:
    row = _translation(TranscriptSegmentStatus.APPROVED)
    row.quality_flags_json = {"flags": []}
    row.metadata_json = {
        "translation_v3": {
            "candidate_evaluations": [
                {"text": row.text, "hard_valid": True, "tts_eligible": True},
                {
                    "text": "Bản ngắn hơn để vừa nhịp",
                    "hard_valid": True,
                    "tts_eligible": True,
                },
                {"text": "残留中文", "hard_valid": False, "tts_eligible": False},
            ]
        }
    }
    db = MagicMock()
    db.scalars.return_value = [row]

    segments = TranslationInputResolver(db).resolve(row.source_video_id)

    assert "Bản ngắn hơn để vừa nhịp" in segments[0].candidate_texts
    assert "残留中文" not in segments[0].candidate_texts


def test_tts_rebinds_stale_translation_budget_to_current_transcript_slot() -> None:
    row = _translation(TranscriptSegmentStatus.APPROVED)
    row.duration_budget_ms = 9_000
    row.quality_flags_json = {"flags": []}
    db = MagicMock()
    db.scalars.return_value = [row]

    segment = TranslationInputResolver(db).resolve(row.source_video_id)[0]

    assert segment.duration_budget_ms == 4_000
    assert "duration_budget_rebound_to_current_timeline" in segment.quality_flags
