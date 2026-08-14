from uuid import uuid4

from src.tts_pipeline.services.input_preflight import (
    TtsPreflightStatus,
    build_tts_input_preflight,
)
from src.tts_pipeline.services.tts_service import _voice_rate_samples
from src.tts_pipeline.types import TranslationInputSegment, VoiceConfig


def _segment(text: str, *, start=0, end=1000, source_text="", **overrides):
    source_id = uuid4()
    payload = dict(
        translation_segment_id=uuid4(),
        transcript_segment_id=uuid4(),
        source_video_id=source_id,
        segment_index=0,
        start_ms=start,
        end_ms=end,
        translated_text=text,
        duration_budget_ms=max(1, end - start),
        translation_version=1,
        translation_preset="contextual",
        source_text=source_text,
    )
    payload.update(overrides)
    return TranslationInputSegment(**payload)


def _run(segment, *, duration=1000):
    return build_tts_input_preflight(
        [segment],
        source_video_id=segment.source_video_id,
        timeline_duration_ms=duration,
        translation_input_sha256="input",
        translation_authority_sha256="authority",
        voice_config=VoiceConfig(),
        voice_authority={"profile_id": "voice"},
        units_per_second=4.5,
    )


def test_preflight_blocks_empty_cjk_and_out_of_video_rows():
    for segment, reason in (
        (_segment(""), "empty_translation"),
        (_segment("这是中文"), "cjk_remaining_in_translation"),
        (_segment("Xin chào", start=900, end=1200), "timing_exceeds_source_video"),
    ):
        manifest = _run(segment)
        row = manifest["segments"][0]
        assert row["status"] == TtsPreflightStatus.BLOCKED
        assert reason in row["reasons"]
        assert not manifest["admission_ready"]


def test_preflight_emits_auto_fit_plan_without_remote_calls():
    manifest = _run(_segment("một hai ba bốn năm sáu"))
    row = manifest["segments"][0]
    assert row["status"] == TtsPreflightStatus.AUTO_FIT
    assert row["initial_rate_plan"]["action"] == "increase_rate_for_predicted_overflow"
    assert manifest["admission_ready"]


def test_preflight_preserves_protected_number_contract():
    manifest = _run(_segment("Dùng hai gam", source_text="Use 200 g"))
    row = manifest["segments"][0]
    assert row["status"] == TtsPreflightStatus.BLOCKED
    assert "protected_tokens_missing" in row["reasons"]


def test_preflight_accepts_review_flag_after_operator_approval():
    manifest = _run(
        _segment(
            "Xin chào",
            quality_flags=["translation_selective_semantic_review"],
            translation_status="APPROVED",
        )
    )
    assert manifest["admission_ready"]
    assert manifest["segments"][0]["status"] in {
        TtsPreflightStatus.READY,
        TtsPreflightStatus.AUTO_FIT,
    }


def test_calibration_filters_model_and_explicit_invalid_waveform():
    def asset(model, valid):
        return type(
            "Asset",
            (),
            {
                "metadata_json": {
                    "provider": {
                        "provider": "provider",
                        "model_id": model,
                        "voice_id": "voice",
                        "speaking_rate": 1.0,
                        "waveform_qa": {
                            "valid_speech_audio": valid,
                            "warnings": [],
                        },
                        "speech_budget": {
                            "timing_quality_band": "no_speed_adjustment",
                            "observed_audio_duration_seconds": 2.0,
                        },
                    },
                    "speech_budget": {
                        "spoken_units": 8,
                        "observed_audio_duration_seconds": 2.0,
                    },
                }
            },
        )()

    samples = _voice_rate_samples(
        [asset("model-a", True), asset("model-a", False), asset("model-b", True)],
        provider_name="provider",
        model_id="model-a",
        voice_config=VoiceConfig(voice_id="voice", speaking_rate=1.0),
    )
    assert len(samples) == 1
