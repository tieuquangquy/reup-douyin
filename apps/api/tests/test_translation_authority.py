from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.audio_pipeline.translation_authority import (
    build_translation_authority,
    transcript_authority_sha256,
    validate_translation_authority,
)
from src.audio_pipeline.services.transcript_edit_service import TranscriptEditService
from src.enums import TranscriptSegmentStatus
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.services.translation_input_resolver import TranslationInputResolver


def _rows():
    source_id = uuid4()
    transcript = SimpleNamespace(
        id=uuid4(),
        source_video_id=source_id,
        segment_index=0,
        start_ms=0,
        end_ms=2_000,
        text="你好",
        normalized_text="你好",
        confidence=0.95,
        speaker_label=None,
        difficulty_flags_json={"flags": []},
        metadata_json={},
    )
    translation = SimpleNamespace(
        id=uuid4(),
        source_video_id=source_id,
        transcript_segment_id=transcript.id,
        transcript_segment=transcript,
        segment_index=0,
        version=1,
        text="Xin chào",
        status=TranscriptSegmentStatus.DRAFT,
        translation_preset="literal_safe",
        duration_budget_ms=2_000,
        estimated_tts_duration_ms=1_200,
        quality_flags_json={"flags": []},
        metadata_json={},
    )
    return source_id, transcript, translation


def test_translation_authority_detects_row_mutation() -> None:
    source_id, transcript, translation = _rows()
    manifest = build_translation_authority(
        source_video_id=source_id,
        analysis_version="AUDIO_ANALYSIS_V5_RUN_1",
        source_transcript_sha256=transcript_authority_sha256([transcript]),
        translation_fingerprint="fingerprint",
        prompt="operator prompt",
        provider_identity={"provider": "test", "model": "test-model"},
        quality_contract={"tts_ready": True},
        translation_rows=[translation],
        job_id=uuid4(),
    )
    valid, reason = validate_translation_authority(
        manifest,
        source_video_id=source_id,
        transcript_rows=[transcript],
        translation_rows=[translation],
    )
    assert valid and reason is None

    translation.text = "Nội dung đã bị thay đổi"
    valid, reason = validate_translation_authority(
        manifest,
        source_video_id=source_id,
        transcript_rows=[transcript],
        translation_rows=[translation],
    )
    assert not valid
    assert reason == "translation_authority_rows_hash_mismatch"


def test_tts_resolver_fails_closed_on_stale_translation_authority() -> None:
    source_id, transcript, translation = _rows()
    manifest = build_translation_authority(
        source_video_id=source_id,
        analysis_version="AUDIO_ANALYSIS_V5_RUN_1",
        source_transcript_sha256=transcript_authority_sha256([transcript]),
        translation_fingerprint="fingerprint",
        prompt="operator prompt",
        provider_identity={"provider": "test", "model": "test-model"},
        quality_contract={"tts_ready": True},
        translation_rows=[translation],
        job_id=None,
    )
    source = SimpleNamespace(metadata_json={"translation_authority": manifest})
    translation.text = "stale mutation"
    db = MagicMock()
    db.scalars.return_value = [translation]
    db.get.return_value = source

    with pytest.raises(TtsPipelineError) as raised:
        TranslationInputResolver(db).resolve(source_id)

    assert raised.value.code == TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED


def test_operator_approval_rebinds_translation_authority() -> None:
    source_id, transcript, translation = _rows()
    translation.status = TranscriptSegmentStatus.NEEDS_REVIEW
    translation.quality_flags_json = {"flags": ["needs_operator_review"]}
    quality_contract = {
        "tts_ready": False,
        "review_required_count": 1,
    }
    manifest = build_translation_authority(
        source_video_id=source_id,
        analysis_version="AUDIO_ANALYSIS_V5_RUN_1",
        source_transcript_sha256=transcript_authority_sha256([transcript]),
        translation_fingerprint="fingerprint",
        prompt="operator prompt",
        provider_identity={"provider": "test", "model": "test-model"},
        quality_contract=quality_contract,
        translation_rows=[translation],
        job_id=None,
    )
    source = SimpleNamespace(
        metadata_json={
            "translation_authority": manifest,
            "translation_quality_contract": quality_contract,
        }
    )
    db = MagicMock()
    db.scalars.return_value = [translation]
    db.get.return_value = source

    result = TranscriptEditService(db).approve_translation_draft(
        source_id,
        operator_id="operator",
    )

    rebound = source.metadata_json["translation_authority"]
    assert rebound["operator_approved"] is True
    assert rebound["tts_ready"] is True
    assert rebound["operator_approval_binding_sha256"] == result["binding_sha256"]
    valid, reason = validate_translation_authority(
        rebound,
        source_video_id=source_id,
        transcript_rows=[transcript],
        translation_rows=[translation],
    )
    assert valid and reason is None
