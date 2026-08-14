from src.tts_pipeline.services.emotion_acceptance import build_emotion_acceptance_report


def test_acceptance_passes_one_verified_gemini_request():
    report = build_emotion_acceptance_report(
        planner_enabled=True,
        policy_report={"downgraded_count": 0, "violations": []},
        provider_metadata={
            "provider_http_call_count": 1,
            "fallback_used": False,
            "execution_contract": {
                "single_voice_mode": "required",
                "semantic_chunk_count": 1,
                "degraded_features": [],
            },
        },
        prosody_audio_qa={"execution_verified": True},
        waveform_valid=True,
        timing_ratio=1.08,
        review_atempo_limit=1.10,
    )
    assert report["passed"]
    assert report["single_voice_verified"]


def test_acceptance_flags_timing_and_multiple_provider_calls():
    report = build_emotion_acceptance_report(
        planner_enabled=True,
        policy_report={"downgraded_count": 1, "violations": [{"reason": "x"}]},
        provider_metadata={
            "provider_http_call_count": 2,
            "execution_contract": {
                "single_voice_mode": "required",
                "semantic_chunk_count": 1,
                "degraded_features": [],
            },
        },
        prosody_audio_qa={"execution_verified": True},
        waveform_valid=True,
        timing_ratio=1.12,
        review_atempo_limit=1.10,
    )
    assert not report["passed"]
    assert "emotion_single_voice_not_verified" in report["warnings"]
    assert "emotion_timing_translation_repair_recommended" in report["warnings"]
