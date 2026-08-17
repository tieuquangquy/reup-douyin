from __future__ import annotations

from src.audio_pipeline.adaptive_separation import (
    ADAPTIVE_SEPARATION_MIN_GAIN,
    ADAPTIVE_SEPARATION_RECIPE_VERSION,
    AdaptiveSeparationTrigger,
    decide_adaptive_separation,
    evaluate_adaptive_separation_outcome,
)
from src.audio_pipeline.asr_evidence import ASREvidenceScore, ASREvidenceState


def _evidence(
    score: float,
    *,
    state: ASREvidenceState = ASREvidenceState.BORDERLINE,
    recovery: bool = False,
    reasons: tuple[str, ...] = (),
) -> ASREvidenceScore:
    return ASREvidenceScore(
        overall_score=score,
        confidence_score=score,
        linguistic_score=score,
        temporal_score=score,
        stability_score=None,
        state=state,
        recovery_recommended=recovery,
        unit_count=1,
        non_empty_unit_count=1,
        char_count=8,
        observed_seconds=2.0,
        char_rate_per_second=4.0,
        timed_unit_ratio=1.0,
        confidence_coverage=1.0,
        repetition_ratio=0.0,
        invalid_char_ratio=0.0,
        reasons=reasons,
    )


def test_clean_good_evidence_skips_demucs() -> None:
    decision = decide_adaptive_separation(
        _evidence(0.86, state=ASREvidenceState.GOOD),
        mix_quality={
            "voice_band_ratio": 0.60,
            "spectral_flatness": 0.18,
            "clipping_ratio": 0.0,
            "rms_dbfs": -20.0,
            "separation_recommended": False,
        },
        vad_speech_ratio=0.35,
    )
    assert decision.should_retry is False
    assert decision.primary_reason is None


def test_music_masking_retries_even_when_asr_is_not_weak() -> None:
    decision = decide_adaptive_separation(
        _evidence(0.79),
        mix_quality={"voice_band_ratio": 0.20, "spectral_flatness": 0.55},
    )
    assert decision.should_retry is True
    assert decision.primary_reason == AdaptiveSeparationTrigger.MUSIC_MASKING
    assert "low_voice_band_ratio" in decision.mix_signals


def test_boundary_only_failure_does_not_pay_demucs_cost() -> None:
    decision = decide_adaptive_separation(
        _evidence(
            0.58,
            state=ASREvidenceState.WEAK,
            recovery=True,
            reasons=("weak_timing_coverage", "timeline_overlap_or_reversal", "evidence_below_recovery_threshold"),
        ),
        mix_quality={"separation_recommended": False},
    )
    assert decision.should_retry is False
    assert decision.primary_reason == AdaptiveSeparationTrigger.BAD_BOUNDARY


def test_uncertain_content_evidence_retries() -> None:
    decision = decide_adaptive_separation(
        _evidence(
            0.56,
            state=ASREvidenceState.WEAK,
            recovery=True,
            reasons=("low_model_confidence", "evidence_below_recovery_threshold"),
        )
    )
    assert decision.should_retry is True
    assert decision.primary_reason == AdaptiveSeparationTrigger.UNCERTAIN


def test_clipping_is_classified_as_other_mix_problem() -> None:
    decision = decide_adaptive_separation(
        _evidence(0.82, state=ASREvidenceState.GOOD),
        mix_quality={"clipping_ratio": 0.03},
    )
    assert decision.should_retry is True
    assert decision.primary_reason == AdaptiveSeparationTrigger.OTHER
    assert "clipping" in decision.mix_signals


def test_sparse_vad_speech_is_a_retry_signal() -> None:
    decision = decide_adaptive_separation(
        _evidence(0.84, state=ASREvidenceState.GOOD),
        vad_speech_ratio=0.04,
    )
    assert decision.should_retry is True
    assert decision.primary_reason == AdaptiveSeparationTrigger.OTHER
    assert "sparse_vad_speech" in decision.mix_signals


def test_candidate_requires_meaningful_gain_not_tie_or_micro_gain() -> None:
    primary = _evidence(0.70)
    micro_gain = _evidence(0.72)
    meaningful_gain = _evidence(0.75)

    rejected = evaluate_adaptive_separation_outcome(
        primary,
        micro_gain,
        attempted=True,
    )
    accepted = evaluate_adaptive_separation_outcome(
        primary,
        meaningful_gain,
        attempted=True,
    )

    assert ADAPTIVE_SEPARATION_MIN_GAIN == 0.03
    assert rejected.accepted is False
    assert rejected.reason == "candidate_below_min_gain"
    assert accepted.accepted is True
    assert accepted.reason == "candidate_meaningful_gain"


def test_provider_fallback_never_becomes_separation_authority() -> None:
    outcome = evaluate_adaptive_separation_outcome(
        _evidence(0.55, state=ASREvidenceState.WEAK, recovery=True),
        None,
        attempted=True,
        fallback_used=True,
    )
    assert outcome.accepted is False
    assert outcome.gain is None
    assert outcome.reason == "provider_fallback"


def test_contract_payload_is_versioned_and_json_friendly() -> None:
    decision = decide_adaptive_separation(
        _evidence(0.80, state=ASREvidenceState.GOOD),
        mix_quality={"voice_band_ratio": 0.25},
    )
    payload = decision.to_dict()
    assert payload["recipe_version"] == ADAPTIVE_SEPARATION_RECIPE_VERSION
    assert payload["primary_reason"] == "music_masking"
    assert isinstance(payload["reasons"], list)


def test_service_wiring_promotes_background_only_after_accepted_gain() -> None:
    from pathlib import Path

    service = Path("src/audio_pipeline/services/audio_analysis_service.py").read_text(encoding="utf-8")
    assert "adaptive_decision.should_retry" in service
    assert "if adaptive_outcome.accepted:" in service
    assert "candidate_background_storage_key" in service
    assert "original_mix_adaptive_candidate_rejected" in service
    assert "evidence_prefers_candidate(" not in service


def test_audio_recipe_binds_adaptive_separation_v2() -> None:
    from pathlib import Path

    types_text = Path("src/audio_pipeline/types.py").read_text(encoding="utf-8")
    assert "asr-evidence1-adaptive-separation2" in types_text
