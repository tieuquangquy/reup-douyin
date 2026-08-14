"""Final semantic/execution acceptance report for Gemini emotion synthesis."""

from __future__ import annotations

from typing import Any, Mapping


EMOTION_ACCEPTANCE_VERSION = "gemini-emotion-acceptance-v1"


def build_emotion_acceptance_report(
    *,
    planner_enabled: bool,
    policy_report: Mapping[str, Any] | None,
    provider_metadata: Mapping[str, Any] | None,
    prosody_audio_qa: Mapping[str, Any] | None,
    waveform_valid: bool,
    timing_ratio: float,
    review_atempo_limit: float,
) -> dict:
    metadata = dict(provider_metadata or {})
    execution = dict(metadata.get("execution_contract") or {})
    degraded = list(execution.get("degraded_features") or [])
    single_voice_verified = bool(
        execution.get("single_voice_mode") == "required"
        and int(execution.get("semantic_chunk_count") or 0) == 1
        and int(metadata.get("provider_http_call_count") or 0) == 1
        and not bool(metadata.get("fallback_used"))
    )
    execution_verified = bool(dict(prosody_audio_qa or {}).get("execution_verified"))
    timing_passed = float(timing_ratio) <= float(review_atempo_limit)
    warnings: list[str] = []
    if planner_enabled and not execution_verified:
        warnings.append("emotion_execution_not_verified")
    if degraded:
        warnings.append("emotion_features_degraded")
    if planner_enabled and not single_voice_verified:
        warnings.append("emotion_single_voice_not_verified")
    if not waveform_valid:
        warnings.append("emotion_waveform_invalid")
    if not timing_passed:
        warnings.append("emotion_timing_translation_repair_recommended")
    policy = dict(policy_report or {})
    return {
        "schema_version": EMOTION_ACCEPTANCE_VERSION,
        "planner_enabled": bool(planner_enabled),
        "policy_applied": bool(policy),
        "policy_adjustment_count": int(policy.get("downgraded_count") or 0),
        "policy_violation_count": len(list(policy.get("violations") or [])),
        "execution_verified": execution_verified,
        "single_voice_verified": single_voice_verified,
        "voice_identity_verification": (
            "single_provider_request" if single_voice_verified else "not_verified"
        ),
        "degraded_features": degraded,
        "waveform_valid": bool(waveform_valid),
        "timing_ratio": round(float(timing_ratio), 6),
        "review_atempo_limit": round(float(review_atempo_limit), 6),
        "timing_passed": timing_passed,
        "passed": not warnings,
        "warnings": warnings,
    }

