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
        quality_flags_json={"flags": ["needs_operator_review"]},
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
    source = SimpleNamespace(
        metadata_json={
            "translation_quality_contract": {
                "blocked_count": 1,
                "review_required_count": 1,
                "complete": False,
                "tts_ready": False,
            }
        }
    )
    db = MagicMock()
    db.scalars.return_value = [row]
    db.get.return_value = source

    result = TranscriptEditService(db).approve_translation_draft(
        row.source_video_id,
        operator_id="operator",
    )

    assert row.status == TranscriptSegmentStatus.APPROVED
    assert "needs_operator_review" not in (row.quality_flags_json or {}).get("flags", [])
    assert len(result["binding_sha256"]) == 64
    assert source.metadata_json["dialogue_translation_review"]["status"] == "DIALOGUE_TRANSLATION_APPROVED"
    quality = source.metadata_json["translation_quality_contract"]
    assert quality["blocked_count"] == 0
    assert quality["review_required_count"] == 0
    assert quality["complete"] is True
    assert quality["tts_ready"] is True
    db.commit.assert_called_once()


def test_operator_edit_revalidates_and_clears_stale_timing_blockers() -> None:
    row = _row(
        "Còn hộp quà cú đêm có hai món quà tặng là quạt mini với máy thổi bong bóng, mở ra xem nào.",
        duration_ms=4_180,
    )
    row.quality_flags_json = {
        "flags": [
            "workspace_translation_prompt",
            "duration_adaptation_required",
            "duration_rewrite_no_safe_candidate",
            "translation_too_long_for_slot",
            "needs_operator_review",
        ]
    }
    row.metadata_json = {
        "translation_v3": {
            "speech_policy": {"units_per_second": 4.5, "acceptable_tolerance": 0.12},
            "requires_rewrite": True,
        }
    }

    TranscriptEditService._revalidate_edited_translation(
        row,
        text="Hộp quà cú đêm tặng quạt mini và máy thổi bong bóng. Mở xem nhé.",
        slot_ms=4_180,
    )

    flags = set(row.quality_flags_json["flags"])
    assert "duration_adaptation_required" not in flags
    assert "duration_rewrite_no_safe_candidate" not in flags
    assert "translation_too_long_for_slot" not in flags
    assert "operator_edit_timing_revalidated" in flags
    assert row.metadata_json["speech_budget"]["status"] == "fits_budget"
    assert row.metadata_json["translation_v3"]["requires_rewrite"] is False
