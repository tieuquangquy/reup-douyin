from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from src.audio_pipeline.asr_evidence import (
    ASREvidenceScore,
    ASREvidenceState,
    evidence_prefers_candidate,
)


ADAPTIVE_SEPARATION_SCHEMA_VERSION = "adaptive_separation_v2"
ADAPTIVE_SEPARATION_RECIPE_VERSION = "adaptive-separation-v2"
ADAPTIVE_SEPARATION_MIN_GAIN = 0.03
ADAPTIVE_SEPARATION_SPARSE_SPEECH_RATIO = 0.08


class AdaptiveSeparationTrigger(StrEnum):
    MUSIC_MASKING = "music_masking"
    BAD_BOUNDARY = "bad_boundary"
    UNCERTAIN = "uncertain"
    OTHER = "other"


_BOUNDARY_REASONS = {
    "weak_timing_coverage",
    "funasr_untimed_present",
    "timeline_overlap_or_reversal",
    "implausible_text_rate",
}
_UNCERTAIN_REASONS = {
    "no_asr_units",
    "low_model_confidence",
    "sparse_confidence_coverage",
    "empty_asr_units",
    "high_text_repetition",
    "invalid_text_content",
    "asr_unstable",
}


@dataclass(frozen=True)
class AdaptiveSeparationDecision:
    should_retry: bool
    primary_reason: AdaptiveSeparationTrigger | None
    reasons: tuple[str, ...]
    evidence_score: float
    evidence_state: ASREvidenceState
    mix_signals: tuple[str, ...]
    vad_speech_ratio: float | None

    def to_dict(self) -> dict:
        return {
            "schema_version": ADAPTIVE_SEPARATION_SCHEMA_VERSION,
            "recipe_version": ADAPTIVE_SEPARATION_RECIPE_VERSION,
            "should_retry": self.should_retry,
            "primary_reason": (
                self.primary_reason.value if self.primary_reason is not None else None
            ),
            "reasons": list(self.reasons),
            "evidence_score": self.evidence_score,
            "evidence_state": self.evidence_state.value,
            "mix_signals": list(self.mix_signals),
            "vad_speech_ratio": self.vad_speech_ratio,
        }


@dataclass(frozen=True)
class AdaptiveSeparationOutcome:
    attempted: bool
    accepted: bool
    gain: float | None
    min_gain: float
    reason: str
    primary_score: float
    candidate_score: float | None

    def to_dict(self) -> dict:
        return {
            "schema_version": ADAPTIVE_SEPARATION_SCHEMA_VERSION,
            "recipe_version": ADAPTIVE_SEPARATION_RECIPE_VERSION,
            "attempted": self.attempted,
            "accepted": self.accepted,
            "gain": self.gain,
            "min_gain": self.min_gain,
            "reason": self.reason,
            "primary_score": self.primary_score,
            "candidate_score": self.candidate_score,
        }


def decide_adaptive_separation(
    evidence: ASREvidenceScore,
    *,
    mix_quality: Mapping[str, object] | None = None,
    vad_speech_ratio: float | None = None,
) -> AdaptiveSeparationDecision:
    mix = dict(mix_quality or {})
    evidence_reasons = set(evidence.reasons)
    material_reasons = evidence_reasons - {"evidence_below_recovery_threshold"}
    boundary_reasons = sorted(material_reasons.intersection(_BOUNDARY_REASONS))
    uncertain_reasons = sorted(material_reasons.intersection(_UNCERTAIN_REASONS))

    mix_signals: list[str] = []
    voice_band_ratio = _float_or_none(mix.get("voice_band_ratio"))
    spectral_flatness = _float_or_none(mix.get("spectral_flatness"))
    clipping_ratio = _float_or_none(mix.get("clipping_ratio"))
    rms_dbfs = _float_or_none(mix.get("rms_dbfs"))

    music_masking = False
    if voice_band_ratio is not None and voice_band_ratio < 0.34:
        mix_signals.append("low_voice_band_ratio")
        music_masking = True
    if spectral_flatness is not None and spectral_flatness > 0.42:
        mix_signals.append("high_spectral_flatness")
        music_masking = True

    other_mix_problem = False
    if clipping_ratio is not None and clipping_ratio > 0.01:
        mix_signals.append("clipping")
        other_mix_problem = True
    if rms_dbfs is not None and rms_dbfs < -42.0:
        mix_signals.append("very_low_level")
        other_mix_problem = True
    if bool(mix.get("separation_recommended")) and not (music_masking or other_mix_problem):
        mix_signals.append("mix_probe_recommended")
        other_mix_problem = True

    sparse_speech = bool(
        vad_speech_ratio is not None
        and 0.0 < float(vad_speech_ratio) < ADAPTIVE_SEPARATION_SPARSE_SPEECH_RATIO
    )
    if sparse_speech:
        mix_signals.append("sparse_vad_speech")
        other_mix_problem = True

    boundary_only = bool(boundary_reasons) and material_reasons.issubset(_BOUNDARY_REASONS)
    reasons: list[str] = []
    primary_reason: AdaptiveSeparationTrigger | None = None
    should_retry = False

    if music_masking:
        primary_reason = AdaptiveSeparationTrigger.MUSIC_MASKING
        should_retry = True
        reasons.extend(mix_signals)
    elif boundary_only:
        # Demucs cannot repair ASR segmentation/timestamp authority by itself.
        # Keep this distinct so PR4/temporal validation can own that recovery path.
        primary_reason = AdaptiveSeparationTrigger.BAD_BOUNDARY
        should_retry = False
        reasons.extend(boundary_reasons)
    elif uncertain_reasons or evidence.state in {ASREvidenceState.EMPTY, ASREvidenceState.WEAK}:
        primary_reason = AdaptiveSeparationTrigger.UNCERTAIN
        should_retry = True
        reasons.extend(uncertain_reasons or sorted(material_reasons))
    elif other_mix_problem:
        primary_reason = AdaptiveSeparationTrigger.OTHER
        should_retry = True
        reasons.extend(mix_signals)
    elif evidence.recovery_recommended:
        primary_reason = AdaptiveSeparationTrigger.UNCERTAIN
        should_retry = True
        reasons.extend(sorted(material_reasons))

    if not reasons and primary_reason is not None:
        reasons.append(primary_reason.value)

    return AdaptiveSeparationDecision(
        should_retry=should_retry,
        primary_reason=primary_reason,
        reasons=tuple(dict.fromkeys(reasons)),
        evidence_score=evidence.overall_score,
        evidence_state=evidence.state,
        mix_signals=tuple(dict.fromkeys(mix_signals)),
        vad_speech_ratio=(round(float(vad_speech_ratio), 4) if vad_speech_ratio is not None else None),
    )


def evaluate_adaptive_separation_outcome(
    primary: ASREvidenceScore,
    candidate: ASREvidenceScore | None,
    *,
    attempted: bool,
    fallback_used: bool = False,
    min_gain: float = ADAPTIVE_SEPARATION_MIN_GAIN,
) -> AdaptiveSeparationOutcome:
    threshold = max(0.0, float(min_gain))
    if not attempted:
        return AdaptiveSeparationOutcome(
            attempted=False,
            accepted=False,
            gain=None,
            min_gain=threshold,
            reason="not_attempted",
            primary_score=primary.overall_score,
            candidate_score=None,
        )
    if fallback_used or candidate is None:
        return AdaptiveSeparationOutcome(
            attempted=True,
            accepted=False,
            gain=None,
            min_gain=threshold,
            reason="provider_fallback",
            primary_score=primary.overall_score,
            candidate_score=(candidate.overall_score if candidate is not None else None),
        )

    gain = round(candidate.overall_score - primary.overall_score, 4)
    accepted = evidence_prefers_candidate(
        candidate,
        primary,
        min_gain=threshold,
    )
    if accepted:
        reason = "candidate_meaningful_gain"
    elif candidate.state == ASREvidenceState.EMPTY:
        reason = "candidate_empty"
    elif gain < 0.0:
        reason = "candidate_worse"
    else:
        reason = "candidate_below_min_gain"
    return AdaptiveSeparationOutcome(
        attempted=True,
        accepted=accepted,
        gain=gain,
        min_gain=threshold,
        reason=reason,
        primary_score=primary.overall_score,
        candidate_score=candidate.overall_score,
    )


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
