"""Text-conditioned emotion planning for the Google Gemini Expressive lane.

The planner is intentionally provider-scoped at the orchestration boundary:
it produces a semantic decision only when the active profile explicitly opts
in.  Other providers receive neutral prosody and never see these tags.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

from src.audio_pipeline.speech_budget import count_spoken_units
from src.tts_pipeline.types import TranslationInputSegment


EMOTION_PLANNER_VERSION = "text-conditioned-emotion-v1"
_CLAUSE_RE = re.compile(r"(?<=[.!?;:\u2026])\s+|\n+")

_SERIOUS_TERMS = (
    "canh bao", "nguy hiem", "nghiem trong", "dang so", "warning", "danger",
    "serious", "khong duoc", "do not", "never", "avoid",
)
_POSITIVE_TERMS = (
    "tuyet voi", "thanh cong", "hy vong", "tin tot", "loi ich", "ngon",
    "great", "amazing", "successful", "benefit", "good news",
)
_EXCITED_TERMS = (
    "bat ngo", "khong the tin", "tuyet qua", "wow", "amazing", "incredible",
    "surprise", "unbelievable",
)
_REFLECTIVE_TERMS = (
    "bai hoc", "suy ngam", "nhin lai", "nho rang", "toi nghi", "reflect",
    "lesson", "remember",
)
_CTA_TERMS = (
    "nho theo doi", "hay theo doi", "dang ky", "chia se", "binh luan", "follow",
    "subscribe", "comment", "share", "like",
)
_INSTRUCTION_STARTS = (
    "cho ", "them ", "xao ", "tron ", "lat ", "de ", "cat ", "dun ", "su dung ",
    "add ", "put ", "mix ", "stir ", "cut ", "use ", "place ", "bo ",
)


@dataclass(frozen=True)
class EmotionDecision:
    segment_index: int
    intent: str = "neutral_statement"
    emotion: str = "neutral"
    valence: float = 0.0
    arousal: float = 0.25
    intensity: float = 0.4
    confidence: float = 0.5
    evidence: tuple[str, ...] = field(default_factory=tuple)
    rejected_signals: tuple[str, ...] = field(default_factory=tuple)
    decision: str = "neutral_fallback"
    policy_action: str = "none"
    policy_reasons: tuple[str, ...] = field(default_factory=tuple)
    span_decisions: tuple[dict, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "schema_version": EMOTION_PLANNER_VERSION,
            "segment_index": int(self.segment_index),
            "intent": self.intent,
            "emotion": self.emotion,
            "valence": round(float(self.valence), 6),
            "arousal": round(float(self.arousal), 6),
            "intensity": round(float(self.intensity), 6),
            "confidence": round(float(self.confidence), 6),
            "evidence": list(self.evidence),
            "rejected_signals": list(self.rejected_signals),
            "decision": self.decision,
            "policy_action": self.policy_action,
            "policy_reasons": list(self.policy_reasons),
            "span_decisions": [dict(item) for item in self.span_decisions],
        }


@dataclass(frozen=True)
class EmotionPolicyReport:
    schema_version: str = "text-conditioned-emotion-policy-v1"
    enabled: bool = False
    accepted_count: int = 0
    downgraded_count: int = 0
    rejected_count: int = 0
    strong_emotion_ratio: float = 0.0
    violations: tuple[dict, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "enabled": self.enabled,
            "accepted_count": self.accepted_count,
            "downgraded_count": self.downgraded_count,
            "rejected_count": self.rejected_count,
            "strong_emotion_ratio": round(float(self.strong_emotion_ratio), 6),
            "violations": [dict(item) for item in self.violations],
        }


def planner_enabled(
    *,
    provider: str,
    options: Mapping[str, object] | None,
    capabilities: Mapping[str, object] | None = None,
) -> bool:
    """Opt in only for the Google Gemini Expressive profile."""

    raw = dict(options or {}).get("emotion_planner")
    config = dict(raw) if isinstance(raw, Mapping) else {}
    caps = dict(capabilities or {})
    return bool(
        str(provider or "").strip().lower() in {"google_gemini", "google_cloud_tts"}
        and config.get("enabled") is True
        and caps.get("supports_audio_tags", True) is True
        and caps.get("supports_voice_direction", True) is True
    )


def plan_emotions(
    segments: Sequence[TranslationInputSegment],
    *,
    min_confidence: float = 0.70,
    max_intensity_delta: float = 0.25,
) -> dict[int, EmotionDecision]:
    """Plan bounded semantic emotion decisions for all translation segments.

    The algorithm is deliberately conservative: intent and semantic evidence
    outrank punctuation, and neutral is selected whenever evidence is weak.
    """

    decisions: dict[int, EmotionDecision] = {}
    previous_intensity = 0.4
    previous_emotion = "neutral"
    for segment in sorted(segments, key=lambda row: (row.start_ms, row.segment_index)):
        text = " ".join(str(segment.translated_text or "").split())
        decision = _decide(text, int(segment.segment_index), min_confidence=min_confidence)
        bounded_intensity = max(
            0.15,
            min(0.90, previous_intensity + max(-max_intensity_delta, min(max_intensity_delta, decision.intensity - previous_intensity))),
        )
        if decision.emotion == "neutral" and previous_emotion != "neutral" and decision.confidence < min_confidence:
            bounded_intensity = min(bounded_intensity, 0.48)
        decision = EmotionDecision(
            **{
                **decision.__dict__,
                "intensity": round(bounded_intensity, 6),
                "span_decisions": tuple(
                    _span_decision(part, bounded_intensity, min_confidence=min_confidence)
                    for part in _clauses(text)
                ),
            }
        )
        decisions[int(segment.segment_index)] = decision
        previous_intensity = bounded_intensity
        previous_emotion = decision.emotion
    return decisions


def enforce_emotion_policy(
    decisions: Mapping[int, EmotionDecision],
    segments: Sequence[TranslationInputSegment],
    *,
    min_confidence: float = 0.70,
    allow_excited: bool = True,
    max_strong_emotion_ratio: float = 0.20,
) -> tuple[dict[int, EmotionDecision], EmotionPolicyReport]:
    """Apply final conservative policy before provider lowering."""

    durations = {
        int(row.segment_index): max(0, int(row.end_ms) - int(row.start_ms))
        for row in segments
    }
    total_duration = max(1, sum(durations.values()))
    strong_indexes = {
        index
        for index, decision in decisions.items()
        if decision.emotion in {"excited", "serious"} and decision.confidence >= min_confidence
    }
    strong_ratio = sum(durations.get(index, 0) for index in strong_indexes) / total_duration
    output: dict[int, EmotionDecision] = dict(decisions)
    violations: list[dict] = []
    downgraded = 0
    rejected = 0
    for index, original in decisions.items():
        reasons: list[str] = []
        current = original
        if current.confidence < min_confidence and current.emotion != "neutral":
            reasons.append("confidence_below_threshold")
        if current.emotion == "excited" and not allow_excited:
            reasons.append("allow_excited_disabled")
        if current.intent == "instruction" and current.emotion in {"positive", "excited"}:
            reasons.append("instruction_neutrality_guard")
        if current.intent == "cta" and current.emotion == "excited":
            reasons.append("cta_intensity_cap")
        if strong_ratio > max(0.05, min(1.0, max_strong_emotion_ratio)) and index in strong_indexes:
            reasons.append("strong_emotion_duration_cap")
        if not reasons:
            continue
        next_emotion = "positive" if current.emotion in {"excited", "serious"} and current.intent == "cta" else "neutral"
        next_intensity = 0.54 if next_emotion == "positive" else 0.4
        current = replace(
            current,
            emotion=next_emotion,
            valence=0.68 if next_emotion == "positive" else 0.0,
            arousal=0.48 if next_emotion == "positive" else 0.25,
            intensity=next_intensity,
            decision="downgraded" if next_emotion != "neutral" else "neutral_fallback",
            policy_action="downgraded",
            policy_reasons=tuple(dict.fromkeys(reasons)),
            rejected_signals=tuple(dict.fromkeys((*current.rejected_signals, *reasons))),
            span_decisions=tuple(
                {
                    **dict(span),
                    "emotion": (
                        next_emotion
                        if str(dict(span).get("emotion") or "neutral") in {original.emotion, "excited", "serious"}
                        else str(dict(span).get("emotion") or "neutral")
                    ),
                    "intensity": (
                        next_intensity
                        if str(dict(span).get("emotion") or "neutral") in {original.emotion, "excited", "serious"}
                        else float(dict(span).get("intensity") or 0.4)
                    ),
                }
                for span in current.span_decisions
            ),
        )
        output[index] = current
        downgraded += 1
        violations.append(
            {
                "segment_index": index,
                "requested_emotion": original.emotion,
                "final_emotion": current.emotion,
                "reasons": list(dict.fromkeys(reasons)),
            }
        )
    accepted = sum(1 for decision in output.values() if decision.decision == "accepted")
    rejected = sum(1 for decision in output.values() if decision.decision == "neutral_fallback")
    return output, EmotionPolicyReport(
        enabled=True,
        accepted_count=accepted,
        downgraded_count=downgraded,
        rejected_count=rejected,
        strong_emotion_ratio=strong_ratio,
        violations=tuple(violations),
    )


def _decide(text: str, segment_index: int, *, min_confidence: float) -> EmotionDecision:
    folded = _fold(text)
    intent, intent_evidence = _intent(folded)
    evidence: list[str] = list(intent_evidence)
    rejected: list[str] = []
    serious = _has_term(folded, _SERIOUS_TERMS)
    positive = _has_term(folded, _POSITIVE_TERMS)
    excited = _has_term(folded, _EXCITED_TERMS)
    reflective = _has_term(folded, _REFLECTIVE_TERMS)
    exclamation = "!" in text
    if serious:
        evidence.append("serious_lexical_evidence")
    if positive:
        evidence.append("positive_lexical_evidence")
    if excited:
        evidence.append("reveal_or_reaction_lexical_evidence")
    if reflective:
        evidence.append("reflective_lexical_evidence")
    if exclamation:
        evidence.append("punctuation_signal_weak")

    emotion = "neutral"
    valence = 0.0
    arousal = 0.25
    intensity = 0.4
    if intent == "warning" or serious:
        emotion, valence, arousal, intensity = "serious", -0.35, 0.68, 0.62
    elif intent == "reflection" or reflective:
        emotion, valence, arousal, intensity = "reflective", 0.05, 0.30, 0.46
    elif intent == "question":
        emotion, valence, arousal, intensity = "curious", 0.08, 0.48, 0.50
    elif intent == "reaction" or (excited and intent in {"reveal", "reaction"}):
        emotion, valence, arousal, intensity = "excited", 0.72, 0.78, 0.72
    elif intent in {"cta", "positive_result"} or positive:
        emotion, valence, arousal, intensity = "positive", 0.68, 0.48, 0.54

    independent_signals = sum(
        bool(value)
        for value in (
            intent in {"warning", "reflection", "question", "cta", "positive_result", "reveal", "reaction"},
            serious or positive or excited or reflective,
        )
    )
    confidence = 0.50 + (0.14 * independent_signals) + (0.08 if intent != "neutral_statement" else 0.0)
    if exclamation and independent_signals < 2:
        rejected.append("punctuation_only")
    if emotion == "excited" and independent_signals < 2:
        rejected.append("excited_requires_two_evidence_sources")
        emotion, valence, arousal, intensity = "neutral", 0.0, 0.25, 0.4
    if intent == "instruction" and emotion in {"positive", "excited"}:
        rejected.append("instruction_neutrality_guard")
        emotion, valence, arousal, intensity = "neutral", 0.0, 0.25, 0.4
    if confidence < float(min_confidence):
        if emotion != "neutral":
            rejected.append("confidence_below_threshold")
        emotion, valence, arousal, intensity = "neutral", 0.0, 0.25, 0.4
        decision = "neutral_fallback"
    else:
        decision = "accepted"
    return EmotionDecision(
        segment_index=segment_index,
        intent=intent,
        emotion=emotion,
        valence=valence,
        arousal=arousal,
        intensity=intensity,
        confidence=min(0.96, round(confidence, 6)),
        evidence=tuple(dict.fromkeys(evidence)),
        rejected_signals=tuple(dict.fromkeys(rejected)),
        decision=decision,
    )


def _span_decision(text: str, intensity: float, *, min_confidence: float) -> dict:
    decision = _decide(text, -1, min_confidence=min_confidence)
    return {
        "text": text,
        "intent": decision.intent,
        "emotion": decision.emotion,
        "intensity": round(min(0.9, max(0.15, min(intensity, decision.intensity + 0.15))), 6),
        "confidence": decision.confidence,
        "evidence": list(decision.evidence),
        "decision": decision.decision,
    }


def _intent(text: str) -> tuple[str, tuple[str, ...]]:
    if _has_term(text, _CTA_TERMS):
        return "cta", ("cta_lexical_evidence",)
    if _has_term(text, _SERIOUS_TERMS):
        return "warning", ("warning_lexical_evidence",)
    if "?" in text:
        return "question", ("question_speech_act",)
    if text.startswith(_INSTRUCTION_STARTS):
        return "instruction", ("imperative_instruction",)
    if _has_term(text, _EXCITED_TERMS):
        return "reveal", ("reveal_lexical_evidence",)
    if _has_term(text, _REFLECTIVE_TERMS):
        return "reflection", ("reflection_lexical_evidence",)
    if _has_term(text, _POSITIVE_TERMS):
        return "positive_result", ("positive_result_lexical_evidence",)
    if "!" in text:
        return "reaction", ("exclamation_weak_signal",)
    return "neutral_statement", ()


def _clauses(text: str) -> tuple[str, ...]:
    return tuple(" ".join(part.split()) for part in _CLAUSE_RE.split(text) if part.strip()) or (text,)


def _has_term(text: str, terms: Sequence[str]) -> bool:
    return any(term in text for term in terms)


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))
