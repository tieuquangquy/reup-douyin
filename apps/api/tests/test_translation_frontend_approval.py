from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.audio_pipeline.services.transcript_edit_service import TranscriptEditService
from src.enums import TranscriptSegmentStatus


def _row(text: str, *, duration_ms: int = 4_000):
    return SimpleNamespace(
        id=uuid4(),
        source_video_id=uuid4(),
        segment_index=0,
        text=text,
        duration_budget_ms=duration_ms,
        status=TranscriptSegmentStatus.NEEDS_REVIEW,
        metadata_json={"provider": "mymemory"},
        transcript_segment=SimpleNamespace(start_ms=0, end_ms=duration_ms),
    )


def test_translation_approval_rejects_overlong_vietnamese() -> None:
    row = _row(" ".join(["quá"] * 40), duration_ms=4_000)
    db = MagicMock()
    db.scalars.return_value = [row]

    with pytest.raises(ValueError, match="exceed safe maximum"):
        TranscriptEditService(db).approve_translation_draft(
            row.source_video_id,
            operator_id="operator",
        )

    assert row.status == TranscriptSegmentStatus.NEEDS_REVIEW
    db.commit.assert_not_called()


def test_translation_approval_hash_binds_fit_text_and_marks_approved() -> None:
    row = _row("Tán nền thật mỏng rồi dặm đều", duration_ms=4_000)
    source = SimpleNamespace(metadata_json={})
    db = MagicMock()
    db.scalars.return_value = [row]
    db.get.return_value = source

    result = TranscriptEditService(db).approve_translation_draft(
        row.source_video_id,
        operator_id="operator",
    )

    assert row.status == TranscriptSegmentStatus.APPROVED
    assert len(result["binding_sha256"]) == 64
    assert source.metadata_json["dialogue_translation_review"]["status"] == "DIALOGUE_TRANSLATION_APPROVED"
    db.commit.assert_called_once()
