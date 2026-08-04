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
