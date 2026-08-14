from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.api.routes.audio_analysis import get_source_video_audio_analysis_summary
from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.enums import MediaAssetType


def test_reasr_invalidates_current_translation_tts_rows_without_deleting_history() -> None:
    db = MagicMock()
    service = AudioAnalysisService(db=db, storage=MagicMock())
    source_video_id = uuid4()

    service._mark_previous_non_current(source_video_id)

    statements = [call.args[0] for call in db.execute.call_args_list]
    rendered = "\n".join(str(statement) for statement in statements)
    assert "transcript_segments" in rendered
    assert "translation_segments" in rendered
    assert "subtitle_segments" in rendered
    assert "media_assets" in rendered
    assert all("DELETE" not in str(statement).upper() for statement in statements)

    media_params = statements[3].compile().params
    asset_param = next(value for key, value in media_params.items() if "asset_type" in key)
    invalidated_types = {str(value) for value in asset_param}
    assert {
        str(MediaAssetType.TRANSLATION_DRAFT_JSON),
        str(MediaAssetType.TTS_AUDIO_CLIP),
        str(MediaAssetType.TTS_AUDIO_JOINED),
        str(MediaAssetType.SUBTITLE_JSON),
        str(MediaAssetType.SUBTITLE_SRT),
        str(MediaAssetType.SUBTITLE_ASS),
        str(MediaAssetType.RENDER_PREP_MANIFEST),
    }.issubset(invalidated_types)


def test_reasr_clears_source_projection_and_records_bounded_audit_event() -> None:
    job_id = uuid4()
    source = SimpleNamespace(
        metadata_json={
            "audio_analysis_cache": {"analysis_version": "AUDIO_ANALYSIS_V5_RUN_8"},
            "translation_quality_contract": {"complete": True, "tts_ready": True},
            "translation_v3_cache": {"fingerprint": "old"},
            "translation_count": 24,
            "dialogue_translation_review": {"status": "DIALOGUE_TRANSLATION_APPROVED"},
            "tts_temporal": {"status": "TTS_TEMPORAL_READY"},
            "unrelated_source_metadata": "keep",
        }
    )

    AudioAnalysisService._invalidate_downstream_authority(
        source,
        new_analysis_version="AUDIO_ANALYSIS_V5_RUN_9",
        job_id=job_id,
    )

    metadata = source.metadata_json
    assert "translation_quality_contract" not in metadata
    assert "translation_v3_cache" not in metadata
    assert "translation_count" not in metadata
    assert "dialogue_translation_review" not in metadata
    assert "tts_temporal" not in metadata
    assert metadata["unrelated_source_metadata"] == "keep"
    audit = metadata["downstream_authority_invalidations"][-1]
    assert audit["reason"] == "source_transcript_superseded"
    assert audit["previous_analysis_version"] == "AUDIO_ANALYSIS_V5_RUN_8"
    assert audit["new_analysis_version"] == "AUDIO_ANALYSIS_V5_RUN_9"
    assert audit["job_id"] == str(job_id)
    assert audit["history_preserved"] is True


def test_audio_summary_route_exposes_dialogue_authority_fields() -> None:
    source_video_id = uuid4()
    service = MagicMock()
    service.get_summary.return_value = {
        "source_video_id": str(source_video_id),
        "analysis_version": "AUDIO_ANALYSIS_V5_RUN_9",
        "transcript_count": 21,
        "translation_count": 0,
        "asset_count": 4,
        "manifest": {"assets": []},
        "has_speech": True,
        "dialogue_phase": "dialogue_uncertain",
    }

    response = get_source_video_audio_analysis_summary(source_video_id, service=service)

    assert response.has_speech is True
    assert response.dialogue_phase == "dialogue_uncertain"
