from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.audio_pipeline.speech_budget import SpeechRateCalibration
from src.storage.local import LocalStorageBackend
from src.tts_pipeline.providers import _build_tone_wav
from src.tts_pipeline.services.duration_planner import plan_initial_speaking_rate
from src.tts_pipeline.services.speech_text import build_vietnamese_speech_text
from src.tts_pipeline.services.tts_service import (
    TtsPipelineService,
    _translation_input_sha256,
    _tts_idempotency_key,
)
from src.tts_pipeline.services.waveform_qa import analyze_waveform, apply_edge_fades
from src.tts_pipeline.types import (
    TranslationInputSegment,
    TtsProviderInput,
    TtsProviderOutput,
    TtsRequest,
    VoiceConfig,
)


def test_duration_planner_speeds_only_predicted_overflow() -> None:
    keep = plan_initial_speaking_rate(
        "một câu ngắn",
        slot_seconds=3.0,
        units_per_second=4.5,
        base_speaking_rate=1.0,
    )
    speed = plan_initial_speaking_rate(
        "một câu tiếng Việt khá dài cần đọc trong một giây",
        slot_seconds=1.0,
        units_per_second=4.5,
        base_speaking_rate=1.0,
    )
    assert keep.speaking_rate == 1.0
    assert speed.speaking_rate == 1.12
    assert speed.action == "increase_rate_for_predicted_overflow"


def test_speech_text_expands_units_and_model_without_changing_display() -> None:
    result = build_vietnamese_speech_text("Thêm 15 ml, dùng G7X3 và 510 kcal")
    assert result.display_text == "Thêm 15 ml, dùng G7X3 và 510 kcal"
    assert "mười lăm mi li lít" in result.speech_text
    assert "giê bảy ích ba" in result.speech_text
    assert "năm trăm mười ki lô ca lo" in result.speech_text


def test_waveform_qa_and_edge_fade_keep_duration() -> None:
    source = _build_tone_wav(duration_seconds=0.8, sample_rate=8000)
    faded, metadata = apply_edge_fades(source)
    qa = analyze_waveform(faded)
    assert metadata["applied"] is True
    assert abs(qa.duration_seconds - 0.8) < 0.01
    assert qa.valid_speech_audio is True


def test_pipeline_uses_speech_text_and_persists_runtime_performance() -> None:
    class RecordingProvider:
        provider_name = "recording"
        model_id = "local"
        options: dict = {}

        def __init__(self) -> None:
            self.requests: list[TtsProviderInput] = []

        def synthesize(self, request: TtsProviderInput) -> TtsProviderOutput:
            self.requests.append(request)
            return TtsProviderOutput(
                audio_bytes=_build_tone_wav(duration_seconds=0.4, sample_rate=24_000),
                duration_seconds=0.4,
                mime_type="audio/wav",
                file_extension="wav",
                provider_metadata={"provider": self.provider_name},
            )

    with TemporaryDirectory() as tmp:
        provider = RecordingProvider()
        db = MagicMock()
        service = TtsPipelineService(
            db,
            storage=LocalStorageBackend(Path(tmp)),
            tts_provider=provider,
        )
        source_id = uuid4()
        workspace_id = uuid4()
        source = SimpleNamespace(
            id=source_id,
            workspace_id=workspace_id,
            duration_seconds=2.0,
            source_video_external_id="demo",
            status=None,
            metadata_json={},
        )
        segment = TranslationInputSegment(
            translation_segment_id=uuid4(),
            transcript_segment_id=uuid4(),
            source_video_id=source_id,
            segment_index=0,
            start_ms=0,
            end_ms=2000,
            translated_text="Thêm 15 ml",
            duration_budget_ms=2000,
            translation_version=1,
            translation_preset="literal_safe",
        )
        debug_payloads: list[dict] = []

        def persist_json(*args, **kwargs):
            if len(args) > 3 and isinstance(args[3], dict):
                debug_payloads.append(args[3])
            return MagicMock()

        with (
            patch.object(service, "_load_source_video", return_value=source),
            patch.object(service, "_provider_for_workspace", return_value=provider),
            patch.object(
                service,
                "_voice_config_for_request",
                return_value=VoiceConfig(voice_id="voice", language_code="vi", speaking_rate=1.0),
            ),
            patch.object(service, "_storage_context", return_value=SimpleNamespace()),
            patch.object(service, "_speech_rate_calibration", return_value=SpeechRateCalibration(4.5, "test", 3)),
            patch("src.tts_pipeline.services.tts_service.TranslationInputResolver") as resolver,
            patch.object(service, "_next_subtitle_version", return_value="TTS_RUN_1"),
            patch.object(service, "_mark_previous_outputs_non_current"),
            patch.object(service, "_persist_asset", return_value=MagicMock()),
            patch.object(service, "_persist_json_asset", side_effect=persist_json),
            patch.object(service, "_persist_subtitles", return_value=[]),
            patch.object(service, "_assets_for_video", return_value=[]),
            patch.object(service, "_background_stem_ref", return_value=None),
            patch(
                "src.tts_pipeline.services.tts_service.bind_active_tts_profile_authority",
                return_value={
                    "schema_version": "tts_active_profile_authority_v1",
                    "provider": "recording",
                    "model_id": "local",
                    "voice_id": "voice",
                    "config_fingerprint": "a" * 64,
                },
            ),
            patch(
                "src.tts_pipeline.services.tts_service.build_render_prep_manifest",
                return_value={"manifest_version": "test"},
            ),
        ):
            resolver.return_value.resolve.return_value = [segment]
            result = service.run_pipeline(TtsRequest(source_video_id=source_id))

        assert result.tts_clip_count == 1
        assert provider.requests
        assert "mười lăm mi li lít" in provider.requests[0].text
        performance = next(
            payload
            for payload in debug_payloads
            if payload.get("schema_version") == "tts_runtime_performance_v1"
        )
        assert performance["provider_synthesis_clip_count"] == 1
        assert performance["total_clip_count"] == 1


def test_v4_idempotency_and_input_hash_cover_candidate_authority() -> None:
    source_id = uuid4()
    base = TranslationInputSegment(
        translation_segment_id=uuid4(),
        transcript_segment_id=uuid4(),
        source_video_id=source_id,
        segment_index=0,
        start_ms=0,
        end_ms=1000,
        translated_text="Bản chính",
        duration_budget_ms=1000,
        translation_version=1,
        translation_preset="literal_safe",
    )
    alternative = TranslationInputSegment(
        **{
            **base.__dict__,
            "candidate_texts": ("Bản ngắn",),
        }
    )
    assert _translation_input_sha256([base]) != _translation_input_sha256([alternative])
    key = _tts_idempotency_key(
        source_video_id=source_id,
        translation_input_sha256=_translation_input_sha256([base]),
        voice_config=VoiceConfig(),
        runtime_authority={"provider": "omnivoice"},
    )
    assert key.startswith("tts:TTS_TEMPORAL_V6:")
