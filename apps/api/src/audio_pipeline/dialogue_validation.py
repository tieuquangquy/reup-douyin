"""High-recall ASR validation and temporal decoding for dialogue units.

Audio-event models are useful evidence but are not transcript authority. This
module evaluates ASR output after recognition, removes high-confidence acoustic
hallucinations, preserves valid short replies, and routes uncertain spans to a
small selective verification pass. Everything is deterministic and local.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any, Sequence

from src.audio_pipeline.target_speech_authority import (
    AudioEventLabel,
    TargetSpeechAuthority,
    TargetSpeechInterval,
)
from src.audio_pipeline.types import TranscriptionUnit
from src.audio_pipeline.types import VadResult


DIALOGUE_VALIDATION_RECIPE_VERSION = "dialogue-validation-v1"
_SIGNATURE_RE = re.compile(r"[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ISOLATED_GAP_SECONDS = 2.0
_SHORT_DURATION_SECONDS = 0.45


class DialogueDecision(StrEnum):
    KEEP = "KEEP"
    REVIEW = "REVIEW"
    DROP_NON_DIALOGUE = "DROP_NON_DIALOGUE"


@dataclass(frozen=True)
class DialogueUnitAssessment:
    unit: TranscriptionUnit
    decision: DialogueDecision
    score: float
    reasons: tuple[str, ...]
    speech_score: float
    music_score: float
    singing_score: float
    secondary_agreement: float | None


@dataclass(frozen=True)
class DialogueValidationResult:
    units: tuple[TranscriptionUnit, ...]
    dropped_units: tuple[TranscriptionUnit, ...]
    verification_intervals: tuple[TargetSpeechInterval, ...]
    assessments: tuple[DialogueUnitAssessment, ...]
    diagnostics: dict[str, Any]


def high_recall_candidate_authority(
    authority: TargetSpeechAuthority,
    *,
    vad: VadResult,
) -> TargetSpeechAuthority:
    """Promote measured VAD spans to ASR candidates without changing evidence.

    This is deliberately high recall. Acoustic event classifications remain on
    ``authority`` and are applied after ASR; they no longer delete potentially
    valid words before recognition.
    """

    raw_intervals = list(dict(vad.metadata or {}).get("speech_intervals") or [])
    candidates: list[TargetSpeechInterval] = []
    for raw in raw_intervals:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        try:
            start = max(0.0, float(raw[0]) - 0.12)
            end = min(authority.duration_seconds, float(raw[1]) + 0.12)
        except (TypeError, ValueError):
            continue
        if end - start < 0.08:
            continue
        evidence = _interval_acoustic_evidence(start, end, authority=authority)
        candidates.append(
            TargetSpeechInterval(
                start_seconds=round(start, 3),
                end_seconds=round(end, 3),
                decision="ASR_CANDIDATE_HIGH_RECALL",
                confidence=round(max(0.50, evidence["speech"]), 6),
                speech_score=round(evidence["speech"], 6),
                music_score=round(evidence["music"], 6),
                singing_score=round(evidence["singing"], 6),
                reasons=("silero_measured_high_recall_candidate",),
                requires_separation=bool(
                    evidence["music"] >= 0.48 or evidence["singing"] >= 0.42
                ),
            )
        )
    if not candidates and authority.target_intervals:
        candidates = [
            replace(
                row,
                decision="ASR_CANDIDATE_HIGH_RECALL",
                reasons=tuple(
                    dict.fromkeys(
                        [*(row.reasons or ()), "authority_interval_compatibility_fallback"]
                    )
                ),
            )
            for row in authority.target_intervals
        ]
    merged = _merge_candidate_intervals(candidates, authority.duration_seconds)
    return replace(
        authority,
        target_intervals=tuple(merged),
        ambiguous_intervals=(),
        rejected_intervals=(),
        requires_separation=bool(
            authority.requires_separation
            or any(row.requires_separation for row in merged)
        ),
        diagnostics={
            **dict(authority.diagnostics),
            "asr_candidate_policy": "silero_high_recall_soft_event_evidence_v1",
            "asr_candidate_seconds": round(
                sum(row.duration_seconds for row in merged),
                3,
            ),
            "asr_candidate_count": len(merged),
        },
    )


def validate_dialogue_units(
    units: Sequence[TranscriptionUnit],
    *,
    authority: TargetSpeechAuthority,
    secondary_units: Sequence[TranscriptionUnit] = (),
) -> DialogueValidationResult:
    ordered = sorted(
        [row for row in units if _signature(row.text)],
        key=lambda row: (float(row.start_seconds), float(row.end_seconds)),
    )
    preliminary: list[dict[str, Any]] = []
    for index, unit in enumerate(ordered):
        previous = ordered[index - 1] if index > 0 else None
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        previous_gap = (
            max(0.0, float(unit.start_seconds) - float(previous.end_seconds))
            if previous is not None
            else math.inf
        )
        next_gap = (
            max(0.0, float(following.start_seconds) - float(unit.end_seconds))
            if following is not None
            else math.inf
        )
        evidence = _acoustic_evidence(unit, authority=authority)
        agreement = _secondary_agreement(unit, secondary_units)
        confidence = (
            max(0.0, min(1.0, float(unit.confidence)))
            if unit.confidence is not None
            else 0.60
        )
        text_length = len(_signature(unit.text))
        duration = max(0.0, float(unit.end_seconds) - float(unit.start_seconds))
        isolated = previous_gap >= _ISOLATED_GAP_SECONDS and next_gap >= _ISOLATED_GAP_SECONDS
        short = text_length <= 1 and duration <= _SHORT_DURATION_SECONDS
        music_dominant = evidence["music"] >= 0.62 and evidence["music"] >= evidence["speech"] - 0.08
        strong_non_dialogue = bool(
            evidence["rejected_overlap"] >= 0.50
            and (evidence["singing"] >= 0.68 or evidence["music"] >= 0.78)
        )
        strong_clean_speech = evidence["speech"] >= 0.76 and evidence["music"] < 0.52
        neighbor_support = min(previous_gap, next_gap) <= 1.20

        score = (
            0.31 * evidence["speech"]
            + 0.15 * (1.0 - evidence["music"])
            + 0.10 * (1.0 - evidence["singing"])
            + 0.16 * confidence
            + 0.14 * (agreement if agreement is not None else 0.50)
            + 0.14 * (1.0 if neighbor_support else 0.35)
        )
        reasons: list[str] = []
        hard_drop = bool(
            strong_non_dialogue
            or (short and isolated and music_dominant and not strong_clean_speech)
        )
        if hard_drop:
            score = min(score, 0.08)
            if strong_non_dialogue:
                reasons.append("sustained_non_dialogue_acoustic_consensus")
            if short and isolated:
                reasons.extend(
                    [
                        "isolated_short_token",
                        "music_dominant_span",
                        "no_temporal_dialogue_support",
                    ]
                )
        else:
            if strong_clean_speech:
                score = max(score, 0.78)
                reasons.append("strong_clean_speech")
            if neighbor_support:
                reasons.append("neighbor_dialogue_support")
            if agreement is not None and agreement >= 0.72:
                score = max(score, 0.74)
                reasons.append("selective_asr_agreement")
            elif agreement is not None and agreement < 0.34:
                score = min(score, 0.44)
                reasons.append("selective_asr_disagreement")
            if music_dominant:
                score -= 0.16
                reasons.append("music_dominant_span")
            if short and isolated:
                score -= 0.18
                reasons.append("isolated_short_token")
        preliminary.append(
            {
                "unit": unit,
                "score": max(0.01, min(0.99, score)),
                "hard_drop": hard_drop,
                "reasons": reasons,
                "speech": evidence["speech"],
                "music": evidence["music"],
                "singing": evidence["singing"],
                "agreement": agreement,
            }
        )

    states = _decode_temporal_states(preliminary)
    assessments: list[DialogueUnitAssessment] = []
    accepted: list[TranscriptionUnit] = []
    dropped: list[TranscriptionUnit] = []
    review_intervals: list[TargetSpeechInterval] = list(authority.ambiguous_intervals)
    for raw, state in zip(preliminary, states, strict=True):
        unit = raw["unit"]
        score = float(raw["score"])
        reasons = list(raw["reasons"])
        if raw["hard_drop"] or (state == "NON_DIALOGUE" and score <= 0.30):
            decision = DialogueDecision.DROP_NON_DIALOGUE
            reasons.append("temporal_decoder_non_dialogue")
            dropped.append(_annotate(unit, decision=decision, score=score, reasons=reasons, raw=raw))
        elif state == "NON_DIALOGUE" or score < 0.48:
            decision = DialogueDecision.REVIEW
            reasons.append("temporal_decoder_uncertain")
            annotated = _annotate(unit, decision=decision, score=score, reasons=reasons, raw=raw)
            accepted.append(annotated)
            review_intervals.append(_verification_interval(unit, score=score, reasons=reasons))
        else:
            decision = DialogueDecision.KEEP
            reasons.append("temporal_decoder_dialogue")
            accepted.append(_annotate(unit, decision=decision, score=score, reasons=reasons, raw=raw))
        assessments.append(
            DialogueUnitAssessment(
                unit=unit,
                decision=decision,
                score=round(score, 6),
                reasons=tuple(dict.fromkeys(reasons)),
                speech_score=round(float(raw["speech"]), 6),
                music_score=round(float(raw["music"]), 6),
                singing_score=round(float(raw["singing"]), 6),
                secondary_agreement=(
                    round(float(raw["agreement"]), 6)
                    if raw["agreement"] is not None
                    else None
                ),
            )
        )

    verification = _merge_verification_intervals(review_intervals, authority.duration_seconds)
    review_count = sum(row.decision == DialogueDecision.REVIEW for row in assessments)
    orphan_drop_count = sum(
        row.decision == DialogueDecision.DROP_NON_DIALOGUE
        and "isolated_short_token" in row.reasons
        for row in assessments
    )
    quality_complete = bool(accepted) and review_count == 0
    diagnostics = {
        "schema_version": "dialogue_quality_contract_v1",
        "recipe_version": DIALOGUE_VALIDATION_RECIPE_VERSION,
        "input_unit_count": len(ordered),
        "accepted_unit_count": len(accepted),
        "dropped_unit_count": len(dropped),
        "review_unit_count": review_count,
        "isolated_orphan_drop_count": orphan_drop_count,
        "verification_interval_count": len(verification),
        "quality_complete": quality_complete,
        "translation_ready": quality_complete,
        "dropped": [
            {
                "start_seconds": row.start_seconds,
                "end_seconds": row.end_seconds,
                "text": row.text,
                "reasons": list(assessment.reasons),
            }
            for row, assessment in zip(
                dropped,
                [
                    item
                    for item in assessments
                    if item.decision == DialogueDecision.DROP_NON_DIALOGUE
                ],
                strict=False,
            )
        ],
        "review": [
            {
                "start_seconds": item.unit.start_seconds,
                "end_seconds": item.unit.end_seconds,
                "text": item.unit.text,
                "score": item.score,
                "reasons": list(item.reasons),
                "secondary_agreement": item.secondary_agreement,
            }
            for item in assessments
            if item.decision == DialogueDecision.REVIEW
        ],
    }
    return DialogueValidationResult(
        units=tuple(accepted),
        dropped_units=tuple(dropped),
        verification_intervals=tuple(verification),
        assessments=tuple(assessments),
        diagnostics=diagnostics,
    )


def merge_selective_verification(
    primary_units: Sequence[TranscriptionUnit],
    verification_units: Sequence[TranscriptionUnit],
) -> list[TranscriptionUnit]:
    """Add only genuinely missing verifier units; overlaps remain score evidence."""

    output = list(primary_units)
    for candidate in verification_units:
        if any(_temporal_overlap_ratio(candidate, row) >= 0.25 for row in output):
            continue
        output.append(
            replace(
                candidate,
                flags=list(
                    dict.fromkeys(
                        [*(candidate.flags or []), "selective_asr_recovered"]
                    )
                ),
            )
        )
    return sorted(output, key=lambda row: (row.start_seconds, row.end_seconds))


def verification_authority(
    authority: TargetSpeechAuthority,
    intervals: Sequence[TargetSpeechInterval],
) -> TargetSpeechAuthority:
    return replace(
        authority,
        target_intervals=tuple(intervals),
        ambiguous_intervals=(),
        rejected_intervals=(),
        requires_separation=False,
        diagnostics={
            **dict(authority.diagnostics),
            "selective_verification": True,
            "target_seconds": round(sum(row.duration_seconds for row in intervals), 3),
        },
    )


def _decode_temporal_states(rows: Sequence[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    states = ("DIALOGUE", "NON_DIALOGUE")
    paths: dict[str, tuple[float, list[str]]] = {}
    for index, row in enumerate(rows):
        score = max(0.01, min(0.99, float(row["score"])))
        emissions = {
            "DIALOGUE": math.log(score),
            "NON_DIALOGUE": math.log(1.0 - score),
        }
        if index == 0:
            paths = {state: (emissions[state], [state]) for state in states}
            continue
        previous_unit = rows[index - 1]["unit"]
        current_unit = row["unit"]
        gap = max(0.0, float(current_unit.start_seconds) - float(previous_unit.end_seconds))
        transition_penalty = 0.0 if gap >= 2.5 else 0.72
        next_paths: dict[str, tuple[float, list[str]]] = {}
        for state in states:
            candidates = []
            for previous_state in states:
                transition = 0.0 if previous_state == state else -transition_penalty
                previous_score, previous_path = paths[previous_state]
                candidates.append(
                    (previous_score + transition + emissions[state], [*previous_path, state])
                )
            next_paths[state] = max(candidates, key=lambda value: value[0])
        paths = next_paths
    return max(paths.values(), key=lambda value: value[0])[1]


def _acoustic_evidence(
    unit: TranscriptionUnit,
    *,
    authority: TargetSpeechAuthority,
) -> dict[str, float]:
    weighted: list[tuple[Any, float]] = []
    start = float(unit.start_seconds)
    end = float(unit.end_seconds)
    for window in authority.event_windows:
        overlap = max(0.0, min(end, window.end_seconds) - max(start, window.start_seconds))
        if overlap > 0:
            weighted.append((window, overlap))
    rejected_overlap = _authority_interval_overlap(
        start,
        end,
        authority.rejected_intervals,
    )
    if not weighted:
        interval_evidence = _interval_acoustic_evidence(start, end, authority=authority)
        return {**interval_evidence, "rejected_overlap": rejected_overlap}
    total = sum(weight for _row, weight in weighted)
    return {
        "speech": sum(row.speech_score * weight for row, weight in weighted) / total,
        "music": sum(row.music_score * weight for row, weight in weighted) / total,
        "singing": sum(row.singing_score * weight for row, weight in weighted) / total,
        "rejected_overlap": rejected_overlap,
    }


def _interval_acoustic_evidence(
    start: float,
    end: float,
    *,
    authority: TargetSpeechAuthority,
) -> dict[str, float]:
    rows = [
        *authority.target_intervals,
        *authority.ambiguous_intervals,
        *authority.rejected_intervals,
    ]
    weighted: list[tuple[TargetSpeechInterval, float]] = []
    for row in rows:
        overlap = max(0.0, min(end, row.end_seconds) - max(start, row.start_seconds))
        if overlap > 0:
            weighted.append((row, overlap))
    if not weighted:
        return {"speech": 0.55, "music": 0.35, "singing": 0.25}
    total = sum(weight for _row, weight in weighted)
    return {
        "speech": sum(row.speech_score * weight for row, weight in weighted) / total,
        "music": sum(row.music_score * weight for row, weight in weighted) / total,
        "singing": sum(row.singing_score * weight for row, weight in weighted) / total,
    }


def _authority_interval_overlap(
    start: float,
    end: float,
    intervals: Sequence[TargetSpeechInterval],
) -> float:
    overlap = sum(
        max(0.0, min(end, row.end_seconds) - max(start, row.start_seconds))
        for row in intervals
    )
    return max(0.0, min(1.0, overlap / max(0.05, end - start)))


def _merge_candidate_intervals(
    intervals: Sequence[TargetSpeechInterval],
    duration_seconds: float,
) -> list[TargetSpeechInterval]:
    output: list[TargetSpeechInterval] = []
    for row in sorted(intervals, key=lambda value: (value.start_seconds, value.end_seconds)):
        if output and row.start_seconds <= output[-1].end_seconds + 0.08:
            previous = output[-1]
            output[-1] = replace(
                previous,
                end_seconds=min(duration_seconds, max(previous.end_seconds, row.end_seconds)),
                confidence=max(previous.confidence, row.confidence),
                speech_score=max(previous.speech_score, row.speech_score),
                music_score=max(previous.music_score, row.music_score),
                singing_score=max(previous.singing_score, row.singing_score),
                requires_separation=previous.requires_separation or row.requires_separation,
            )
        else:
            output.append(row)
    return output


def _secondary_agreement(
    unit: TranscriptionUnit,
    secondary_units: Sequence[TranscriptionUnit],
) -> float | None:
    matches = [row for row in secondary_units if _temporal_overlap_ratio(unit, row) >= 0.20]
    if not matches:
        return None
    ratios: list[float] = []
    for match in matches:
        left = _signature(
            _text_in_span(
                unit,
                start_seconds=float(match.start_seconds),
                end_seconds=float(match.end_seconds),
            )
            or unit.text
        )
        right = _signature(match.text)
        if left and right:
            ratios.append(SequenceMatcher(None, left, right).ratio())
    return max(ratios) if ratios else None


def _text_in_span(
    unit: TranscriptionUnit,
    *,
    start_seconds: float,
    end_seconds: float,
) -> str:
    raw = dict(unit.raw_payload or {})
    values = raw.get("timestamps")
    if not isinstance(values, list) or not values:
        return ""
    compact_text = "".join(str(unit.text or "").split())
    split_tokens = [piece for piece in str(unit.text or "").split() if piece]
    tokens = (
        split_tokens
        if len(split_tokens) == len(values)
        else list(compact_text)
        if len(compact_text) == len(values)
        else []
    )
    if len(tokens) != len(values):
        return ""
    selected: list[str] = []
    for token, value in zip(tokens, values, strict=True):
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return ""
        try:
            token_start = float(value[0]) / 1000.0
            token_end = float(value[1]) / 1000.0
        except (TypeError, ValueError):
            return ""
        if min(token_end, end_seconds) - max(token_start, start_seconds) > 0:
            selected.append(token)
    return "".join(selected)


def _temporal_overlap_ratio(left: TranscriptionUnit, right: TranscriptionUnit) -> float:
    overlap = max(
        0.0,
        min(float(left.end_seconds), float(right.end_seconds))
        - max(float(left.start_seconds), float(right.start_seconds)),
    )
    return overlap / max(
        0.05,
        min(
            float(left.end_seconds) - float(left.start_seconds),
            float(right.end_seconds) - float(right.start_seconds),
        ),
    )


def _annotate(
    unit: TranscriptionUnit,
    *,
    decision: DialogueDecision,
    score: float,
    reasons: Sequence[str],
    raw: dict[str, Any],
) -> TranscriptionUnit:
    flags = [*(unit.flags or []), "dialogue_validation_v1"]
    if decision == DialogueDecision.REVIEW:
        flags.append("needs_operator_review")
    if decision == DialogueDecision.DROP_NON_DIALOGUE:
        flags.append("asr_non_dialogue_rejected")
    payload = dict(unit.raw_payload or {})
    payload["dialogue_validation"] = {
        "recipe_version": DIALOGUE_VALIDATION_RECIPE_VERSION,
        "decision": decision.value,
        "score": round(score, 6),
        "speech_score": round(float(raw["speech"]), 6),
        "music_score": round(float(raw["music"]), 6),
        "singing_score": round(float(raw["singing"]), 6),
        "secondary_agreement": (
            round(float(raw["agreement"]), 6)
            if raw["agreement"] is not None
            else None
        ),
        "reasons": list(dict.fromkeys(reasons)),
    }
    return replace(unit, flags=list(dict.fromkeys(flags)), raw_payload=payload)


def _verification_interval(
    unit: TranscriptionUnit,
    *,
    score: float,
    reasons: Sequence[str],
) -> TargetSpeechInterval:
    return TargetSpeechInterval(
        start_seconds=max(0.0, round(float(unit.start_seconds) - 0.18, 3)),
        end_seconds=round(float(unit.end_seconds) + 0.18, 3),
        decision="VERIFY_DIALOGUE",
        confidence=round(max(0.0, min(1.0, 1.0 - score)), 6),
        speech_score=0.5,
        music_score=0.5,
        singing_score=0.5,
        reasons=tuple(dict.fromkeys([*reasons, "selective_asr_verification"])),
    )


def _merge_verification_intervals(
    intervals: Sequence[TargetSpeechInterval],
    duration_seconds: float,
) -> list[TargetSpeechInterval]:
    output: list[TargetSpeechInterval] = []
    for row in sorted(intervals, key=lambda value: (value.start_seconds, value.end_seconds)):
        current = replace(
            row,
            start_seconds=max(0.0, row.start_seconds),
            end_seconds=min(duration_seconds, row.end_seconds),
        )
        if current.duration_seconds < 0.10:
            continue
        if output and current.start_seconds <= output[-1].end_seconds + 0.18:
            previous = output[-1]
            output[-1] = replace(
                previous,
                end_seconds=max(previous.end_seconds, current.end_seconds),
                confidence=max(previous.confidence, current.confidence),
                reasons=tuple(dict.fromkeys([*previous.reasons, *current.reasons])),
            )
        else:
            output.append(current)
    return output


def _signature(text: str) -> str:
    return "".join(_SIGNATURE_RE.findall(str(text or ""))).casefold()
