from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
import math
import re
from typing import Iterable, Protocol


ASR_EVIDENCE_SCHEMA_VERSION = "asr_evidence_v1"
ASR_EVIDENCE_RECIPE_VERSION = "asr-evidence-v1"
ASR_RECOVERY_SCORE_THRESHOLD = 0.72


class _TranscriptionLike(Protocol):
    text: str
    start_seconds: float
    end_seconds: float
    confidence: float | None
    flags: list[str]


class ASREvidenceState(StrEnum):
    GOOD = "GOOD"
    BORDERLINE = "BORDERLINE"
    WEAK = "WEAK"
    EMPTY = "EMPTY"


@dataclass(frozen=True)
class ASREvidenceScore:
    overall_score: float
    confidence_score: float
    linguistic_score: float
    temporal_score: float
    stability_score: float | None
    state: ASREvidenceState
    recovery_recommended: bool
    unit_count: int
    non_empty_unit_count: int
    char_count: int
    observed_seconds: float
    char_rate_per_second: float | None
    timed_unit_ratio: float
    confidence_coverage: float
    repetition_ratio: float
    invalid_char_ratio: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "schema_version": ASR_EVIDENCE_SCHEMA_VERSION,
            "recipe_version": ASR_EVIDENCE_RECIPE_VERSION,
            "overall_score": self.overall_score,
            "confidence_score": self.confidence_score,
            "linguistic_score": self.linguistic_score,
            "temporal_score": self.temporal_score,
            "stability_score": self.stability_score,
            "state": self.state.value,
            "recovery_recommended": self.recovery_recommended,
            "unit_count": self.unit_count,
            "non_empty_unit_count": self.non_empty_unit_count,
            "char_count": self.char_count,
            "observed_seconds": self.observed_seconds,
            "char_rate_per_second": self.char_rate_per_second,
            "timed_unit_ratio": self.timed_unit_ratio,
            "confidence_coverage": self.confidence_coverage,
            "repetition_ratio": self.repetition_ratio,
            "invalid_char_ratio": self.invalid_char_ratio,
            "reasons": list(self.reasons),
        }


def evaluate_asr_evidence(
    units: Iterable[_TranscriptionLike],
    *,
    stability_score: float | None = None,
) -> ASREvidenceScore:
    rows = list(units)
    if not rows:
        return ASREvidenceScore(
            overall_score=0.0,
            confidence_score=0.0,
            linguistic_score=0.0,
            temporal_score=0.0,
            stability_score=None,
            state=ASREvidenceState.EMPTY,
            recovery_recommended=True,
            unit_count=0,
            non_empty_unit_count=0,
            char_count=0,
            observed_seconds=0.0,
            char_rate_per_second=None,
            timed_unit_ratio=0.0,
            confidence_coverage=0.0,
            repetition_ratio=0.0,
            invalid_char_ratio=0.0,
            reasons=("no_asr_units",),
        )

    texts = [str(getattr(row, "text", "") or "").strip() for row in rows]
    non_empty_texts = [text for text in texts if text]
    raw_joined = "".join(non_empty_texts)
    compact_texts = [_compact_text(text) for text in non_empty_texts]
    compact_texts = [text for text in compact_texts if text]
    joined = "".join(compact_texts)
    char_count = len(joined)

    confidences = [
        _clamp01(float(row.confidence))
        for row in rows
        if getattr(row, "confidence", None) is not None
    ]
    confidence_coverage = len(confidences) / max(1, len(rows))
    raw_confidence = sum(confidences) / len(confidences) if confidences else 0.62
    # Missing model confidence is evidence absence, not automatic failure. Keep the
    # prior conservative default while preventing one scored unit from representing
    # an otherwise unscored transcript.
    confidence_score = _clamp01(
        raw_confidence * (0.82 + 0.18 * confidence_coverage)
    )

    valid_timings: list[tuple[float, float]] = []
    untimed_flag_count = 0
    for row in rows:
        start = _finite_float(getattr(row, "start_seconds", None))
        end = _finite_float(getattr(row, "end_seconds", None))
        flags = {str(flag) for flag in (getattr(row, "flags", None) or [])}
        if "funasr_untimed" in flags:
            untimed_flag_count += 1
        if start is not None and end is not None and end > start >= 0.0:
            valid_timings.append((start, end))

    timed_unit_ratio = len(valid_timings) / max(1, len(rows))
    observed_seconds = round(sum(end - start for start, end in valid_timings), 4)
    char_rate = (
        round(char_count / observed_seconds, 4)
        if char_count > 0 and observed_seconds > 1e-6
        else None
    )

    invalid_char_ratio = _invalid_char_ratio(raw_joined)
    repetition_ratio = _repetition_ratio(compact_texts)
    lexical_diversity = _lexical_diversity(joined)
    non_empty_ratio = len(non_empty_texts) / max(1, len(rows))

    linguistic_score = _clamp01(
        0.32
        + 0.24 * non_empty_ratio
        + 0.26 * lexical_diversity
        + 0.18 * (1.0 - invalid_char_ratio)
        - 0.38 * repetition_ratio
    )

    ordering_score = _timeline_order_score(valid_timings)
    rate_score = _char_rate_score(char_rate)
    untimed_ratio = untimed_flag_count / max(1, len(rows))
    temporal_score = _clamp01(
        0.10
        + 0.48 * timed_unit_ratio
        + 0.22 * ordering_score
        + 0.20 * rate_score
        - 0.28 * untimed_ratio
    )

    normalized_stability = (
        _clamp01(float(stability_score))
        if stability_score is not None and math.isfinite(float(stability_score))
        else None
    )
    if normalized_stability is None:
        overall = (
            0.45 * confidence_score
            + 0.30 * linguistic_score
            + 0.25 * temporal_score
        )
    else:
        overall = (
            0.38 * confidence_score
            + 0.26 * linguistic_score
            + 0.21 * temporal_score
            + 0.15 * normalized_stability
        )

    reasons: list[str] = []
    if confidence_score < 0.62:
        reasons.append("low_model_confidence")
    if confidence_coverage < 0.60:
        reasons.append("sparse_confidence_coverage")
    if non_empty_ratio < 0.80:
        reasons.append("empty_asr_units")
    if repetition_ratio >= 0.35:
        reasons.append("high_text_repetition")
    if invalid_char_ratio >= 0.08:
        reasons.append("invalid_text_content")
    if timed_unit_ratio < 0.85:
        reasons.append("weak_timing_coverage")
    if untimed_ratio > 0.0:
        reasons.append("funasr_untimed_present")
    if char_rate is not None and rate_score < 0.55:
        reasons.append("implausible_text_rate")
    if ordering_score < 0.75:
        reasons.append("timeline_overlap_or_reversal")
    if normalized_stability is not None and normalized_stability < 0.55:
        reasons.append("asr_unstable")

    # Explicit evidence penalties are applied after the weighted score so a very
    # confident hallucination cannot remain "good" only because the provider was
    # over-confident.
    if repetition_ratio >= 0.60:
        overall -= 0.12
    if untimed_ratio >= 0.50:
        overall -= 0.10
    if char_rate is not None and rate_score <= 0.15:
        overall -= 0.12
    if invalid_char_ratio >= 0.20:
        overall -= 0.10

    overall = round(_clamp01(overall), 4)
    if not compact_texts:
        state = ASREvidenceState.EMPTY
    elif overall >= 0.80:
        state = ASREvidenceState.GOOD
    elif overall >= 0.60:
        state = ASREvidenceState.BORDERLINE
    else:
        state = ASREvidenceState.WEAK

    recovery_recommended = bool(
        state in {ASREvidenceState.EMPTY, ASREvidenceState.WEAK}
        or overall < ASR_RECOVERY_SCORE_THRESHOLD
    )
    if recovery_recommended and "evidence_below_recovery_threshold" not in reasons:
        reasons.append("evidence_below_recovery_threshold")

    return ASREvidenceScore(
        overall_score=overall,
        confidence_score=round(confidence_score, 4),
        linguistic_score=round(linguistic_score, 4),
        temporal_score=round(temporal_score, 4),
        stability_score=(round(normalized_stability, 4) if normalized_stability is not None else None),
        state=state,
        recovery_recommended=recovery_recommended,
        unit_count=len(rows),
        non_empty_unit_count=len(non_empty_texts),
        char_count=char_count,
        observed_seconds=observed_seconds,
        char_rate_per_second=char_rate,
        timed_unit_ratio=round(timed_unit_ratio, 4),
        confidence_coverage=round(confidence_coverage, 4),
        repetition_ratio=round(repetition_ratio, 4),
        invalid_char_ratio=round(invalid_char_ratio, 4),
        reasons=tuple(dict.fromkeys(reasons)),
    )


def compare_asr_stability(
    primary_units: Iterable[_TranscriptionLike],
    secondary_units: Iterable[_TranscriptionLike],
) -> float | None:
    primary_rows = list(primary_units)
    secondary_rows = list(secondary_units)
    if not primary_rows or not secondary_rows:
        return None

    # Selective verification normally covers only uncertain spans. Compare the
    # primary transcript on those same spans instead of penalizing it for clean
    # dialogue that was intentionally not re-run.
    secondary_intervals = [
        interval
        for row in secondary_rows
        if (interval := _valid_interval(row)) is not None
    ]
    aligned_primary = (
        [
            row
            for row in primary_rows
            if (interval := _valid_interval(row)) is not None
            and any(_intervals_overlap(interval, other) for other in secondary_intervals)
        ]
        if secondary_intervals
        else primary_rows
    )
    if not aligned_primary:
        return None

    primary = _compact_text(
        "".join(str(getattr(row, "text", "") or "") for row in aligned_primary)
    )
    secondary = _compact_text(
        "".join(str(getattr(row, "text", "") or "") for row in secondary_rows)
    )
    if not primary or not secondary:
        return None
    return round(SequenceMatcher(a=primary, b=secondary, autojunk=False).ratio(), 4)


def evidence_prefers_candidate(
    candidate: ASREvidenceScore,
    incumbent: ASREvidenceScore,
    *,
    min_gain: float = 0.0,
) -> bool:
    return candidate.overall_score >= incumbent.overall_score + max(0.0, float(min_gain))



def _valid_interval(row: _TranscriptionLike) -> tuple[float, float] | None:
    start = _finite_float(getattr(row, "start_seconds", None))
    end = _finite_float(getattr(row, "end_seconds", None))
    if start is None or end is None or start < 0.0 or end <= start:
        return None
    return (start, end)


def _intervals_overlap(
    left: tuple[float, float],
    right: tuple[float, float],
) -> bool:
    return min(left[1], right[1]) > max(left[0], right[0])

def _compact_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _finite_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _lexical_diversity(text: str) -> float:
    if not text:
        return 0.0
    unique_ratio = len(set(text)) / len(text)
    # Short utterances naturally have high uniqueness. Longer dialogue can repeat
    # function characters, so normalize against a deliberately forgiving floor.
    return _clamp01((unique_ratio - 0.08) / 0.42)


def _repetition_ratio(texts: list[str]) -> float:
    if not texts:
        return 0.0
    duplicate_units = len(texts) - len(set(texts))
    duplicate_ratio = duplicate_units / max(1, len(texts))
    joined = "".join(texts)
    if len(joined) < 6:
        return round(duplicate_ratio, 4)
    grams = [joined[index : index + 3] for index in range(len(joined) - 2)]
    gram_repeat = (len(grams) - len(set(grams))) / max(1, len(grams))
    return round(_clamp01(max(duplicate_ratio, gram_repeat)), 4)


def _invalid_char_ratio(text: str) -> float:
    if not text:
        return 0.0
    invalid = sum(
        1
        for char in text
        if ord(char) < 32 or char in {"\ufffd", "\x00"}
    )
    return invalid / len(text)


def _timeline_order_score(intervals: list[tuple[float, float]]) -> float:
    if len(intervals) <= 1:
        return 1.0 if intervals else 0.0
    ordered = sorted(intervals, key=lambda item: (item[0], item[1]))
    violations = 0
    previous_end = ordered[0][1]
    for start, end in ordered[1:]:
        if start + 0.05 < previous_end:
            violations += 1
        previous_end = max(previous_end, end)
    return _clamp01(1.0 - violations / max(1, len(ordered) - 1))


def _char_rate_score(char_rate: float | None) -> float:
    if char_rate is None:
        return 0.45
    rate = max(0.0, float(char_rate))
    # Wide, language-agnostic envelope. Chinese dialogue normally lives well
    # inside this range, while obvious hallucination/timing failures do not.
    if 0.6 <= rate <= 9.5:
        return 1.0
    if 0.25 <= rate < 0.6:
        return 0.65
    if 9.5 < rate <= 14.0:
        return 0.62
    if 0.10 <= rate < 0.25:
        return 0.30
    if 14.0 < rate <= 20.0:
        return 0.28
    return 0.05
