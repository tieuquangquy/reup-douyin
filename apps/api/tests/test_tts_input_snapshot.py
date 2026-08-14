from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.services.tts_service import (
    TtsPipelineService,
    _assert_translation_snapshot_current,
    _same_translation_snapshot,
    _translation_authority_sha256,
    _translation_input_sha256,
)
from src.tts_pipeline.types import TtsRequest, TranslationInputSegment, VoiceConfig


def _segment(source_id):
    return TranslationInputSegment(
        translation_segment_id=uuid4(),
        transcript_segment_id=uuid4(),
        source_video_id=source_id,
        segment_index=0,
        start_ms=0,
        end_ms=1000,
        translated_text="Xin chào",
        duration_budget_ms=1000,
        translation_version=1,
        translation_preset="contextual",
    )


def test_translation_snapshot_detects_changed_rows_before_provider() -> None:
    source_id = uuid4()
    current = [_segment(source_id)]
    source = SimpleNamespace(
        id=source_id,
        metadata_json={"translation_authority": {"translation_rows_sha256": "rows-v1"}},
    )
    expected_input = _translation_input_sha256(current)
    expected_authority = _translation_authority_sha256(source)
    changed = [
        TranslationInputSegment(**{**current[0].__dict__, "translated_text": "Bản dịch mới"})
    ]
    with pytest.raises(TtsPipelineError) as caught:
        _assert_translation_snapshot_current(
            TtsRequest(
                source_video_id=source_id,
                translation_input_sha256=expected_input,
                translation_authority_sha256=expected_authority,
            ),
            source_video=source,
            input_segments=changed,
        )
    assert caught.value.code == TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED


def test_translation_snapshot_helpers_require_both_hashes() -> None:
    assert _same_translation_snapshot(
        {"translation_input_sha256": "input", "translation_authority_sha256": "authority"},
        translation_input_sha256="input",
        translation_authority_sha256="authority",
    )
    assert not _same_translation_snapshot(
        {"translation_input_sha256": "input"},
        translation_input_sha256="input",
        translation_authority_sha256=None,
    )


def test_create_job_persists_snapshot_and_preflight_manifest() -> None:
    source_id = uuid4()
    workspace_id = uuid4()
    source = SimpleNamespace(
        id=source_id,
        workspace_id=workspace_id,
        duration_seconds=1.0,
        metadata_json={"translation_authority": {"translation_rows_sha256": "rows-v1"}},
    )
    segment = _segment(source_id)
    db = MagicMock()
    db.scalar.side_effect = [None, None]
    job_service = MagicMock()
    job_service.create_job.return_value = SimpleNamespace(id=uuid4())
    authority = {
        "schema_version": "tts_active_profile_authority_v1",
        "workspace_id": str(workspace_id),
        "profile_id": "voice",
        "provider": "provider",
        "model_id": "model",
        "voice_id": "voice",
        "config_fingerprint": "f" * 64,
    }
    service = TtsPipelineService(db)
    with (
        patch.object(service, "_load_source_video", return_value=source),
        patch.object(service, "_voice_config_for_request", return_value=VoiceConfig()),
        patch("src.tts_pipeline.services.tts_service.bind_active_tts_profile_authority", return_value=authority),
        patch("src.tts_pipeline.services.tts_service.TranslationInputResolver") as resolver,
        patch("src.tts_pipeline.services.tts_service.JobService", return_value=job_service),
    ):
        resolver.return_value.resolve.return_value = [segment]
        service.create_tts_job(TtsRequest(source_video_id=source_id))
    payload = job_service.create_job.call_args.kwargs["payload_json"]
    assert payload["translation_input_sha256"] == _translation_input_sha256([segment])
    assert payload["translation_authority_sha256"] == _translation_authority_sha256(source)
    assert payload["tts_input_preflight"]["admission_ready"]


def test_stale_worker_snapshot_fails_before_provider_construction() -> None:
    source_id = uuid4()
    workspace_id = uuid4()
    current = [_segment(source_id)]
    source = SimpleNamespace(
        id=source_id,
        workspace_id=workspace_id,
        metadata_json={"translation_authority": {"translation_rows_sha256": "rows-v1"}},
    )
    service = TtsPipelineService(MagicMock())
    provider_factory = MagicMock()
    with (
        patch.object(service, "_load_source_video", return_value=source),
        patch.object(service, "_voice_config_for_request", return_value=VoiceConfig()),
        patch.object(service, "_storage_context", return_value=SimpleNamespace()),
        patch.object(service, "_provider_for_workspace", provider_factory),
        patch("src.tts_pipeline.services.tts_service.TranslationInputResolver") as resolver,
    ):
        resolver.return_value.resolve.return_value = current
        with pytest.raises(TtsPipelineError):
            service.run_pipeline(
                TtsRequest(
                    source_video_id=source_id,
                    runtime_authority={"provider": "provider"},
                    translation_input_sha256="stale",
                    translation_authority_sha256=_translation_authority_sha256(source),
                )
            )
    provider_factory.assert_not_called()
