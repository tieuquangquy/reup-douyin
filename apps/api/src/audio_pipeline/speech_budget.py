"""Provider-aware spoken-duration budgeting for Vietnamese dubbing.

The estimate is intentionally advisory. Synthesized audio duration remains the final
authority, but an early budget lets translation create a reviewable shorter candidate
before TTS has to apply audible time compression.
"""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import asdict, dataclass
from typing import Iterable


DEFAULT_VI_UNITS_PER_SECOND = 4.5
DEFAULT_PAUSE_MS = 250
DEFAULT_MAX_PAUSE_FRACTION = 0.40
DEFAULT_MIN_SPEECH_MS = 400
DEFAULT_FIT_TOLERANCE = 0.20
MIN_CALIBRATION_SAMPLES = 3

_TOKEN_RE = re.compile(
    r"https?://[^\s]+|\d+(?:[.,]\d+)?|[^\W\d_]+",
    re.IGNORECASE | re.UNICODE,
)
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_NUMBER_RE = re.compile(r"(?<!\w)\d+(?:[.,]\d+)?(?!\w)")
_ACRONYM_RE = re.compile(r"(?<!\w)[A-Z]{2,}(?!\w)")
_UNIT_RE = re.compile(
    r"(?<!\w)(?:kcal|cal|kg|mg|ml|cm|mm|km|g|l|%)(?!\w)",
    re.IGNORECASE,
)
_PAUSE_RE = re.compile(r"[,;:.!?]+")

_UNIT_SPOKEN_COUNTS = {
    "kcal": 4,  # ki-lô-ca-lo
    "cal": 2,
    "kg": 2,
    "mg": 2,
    "ml": 2,
    "cm": 2,
    "mm": 2,
    "km": 2,
    "g": 1,
    "l": 1,
    "%": 2,
}


@dataclass(frozen=True)
class SpeechRateSample:
    spoken_units: int
    duration_seconds: float


@dataclass(frozen=True)
class SpeechRateCalibration:
    units_per_second: float
    source: str
    sample_count: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProtectedTokenValidation:
    valid: bool
    required_tokens: tuple[str, ...]
    missing_tokens: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SpeechBudgetAssessment:
    spoken_units: int
    slot_ms: int
    pause_budget_ms: int
    speech_time_ms: int
    units_per_second: float
    target_units: float
    min_units: int
    max_units: int
    estimated_duration_seconds: float
    status: str
    requires_operator_review: bool
    flags: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def count_spoken_units(text: str) -> int:
    """Estimate Vietnamese syllable-like spoken units without external dependencies."""

    total = 0
    for match in _TOKEN_RE.finditer(str(text or "")):
        token = match.group(0).strip().rstrip(")]}>,.;:!?")
        if not token:
            continue
        lowered = token.casefold()
        if lowered.startswith(("http://", "https://")):
            total += 3
        elif token[0].isdigit():
            total += _number_spoken_units(token)
        elif lowered in _UNIT_SPOKEN_COUNTS:
            total += _UNIT_SPOKEN_COUNTS[lowered]
        else:
            total += 1
    return total


def assess_speech_budget(
    text: str,
    *,
    slot_seconds: float,
    units_per_second: float = DEFAULT_VI_UNITS_PER_SECOND,
    pause_ms: int = DEFAULT_PAUSE_MS,
    max_pause_fraction: float = DEFAULT_MAX_PAUSE_FRACTION,
    min_speech_ms: int = DEFAULT_MIN_SPEECH_MS,
    fit_tolerance: float = DEFAULT_FIT_TOLERANCE,
) -> SpeechBudgetAssessment:
    slot_ms = max(0, int(round(float(slot_seconds) * 1000.0)))
    safe_rate = max(0.5, float(units_per_second or DEFAULT_VI_UNITS_PER_SECOND))
    punctuation_pauses = len(_PAUSE_RE.findall(str(text or ""))) * max(0, int(pause_ms))
    pause_cap_ms = int(round(slot_ms * max(0.0, min(0.9, max_pause_fraction))))
    pause_budget_ms = min(punctuation_pauses, pause_cap_ms)
    raw_speech_ms = max(0, slot_ms - pause_budget_ms)
    speech_time_ms = max(int(min_speech_ms), raw_speech_ms)
    spoken_units = count_spoken_units(text)
    target_units = (speech_time_ms / 1000.0) * safe_rate
    tolerance = max(0.0, min(0.8, float(fit_tolerance)))
    min_units = max(1, int(math.floor(target_units * (1.0 - tolerance))))
    max_units = max(min_units, int(math.ceil(target_units * (1.0 + tolerance))))

    flags: list[str] = []
    if slot_ms < int(min_speech_ms):
        flags.append("slot_below_minimum_speech_time")
    if spoken_units > max_units:
        status = "too_long"
        flags.append("duration_rewrite_recommended")
    elif spoken_units < min_units:
        status = "too_short"
        flags.append("duration_underfilled_review")
    else:
        status = "fits_budget"
    estimated_duration = (spoken_units / safe_rate) + (pause_budget_ms / 1000.0)
    requires_review = status != "fits_budget" or bool(flags)
    return SpeechBudgetAssessment(
        spoken_units=spoken_units,
        slot_ms=slot_ms,
        pause_budget_ms=pause_budget_ms,
        speech_time_ms=speech_time_ms,
        units_per_second=round(safe_rate, 6),
        target_units=round(target_units, 3),
        min_units=min_units,
        max_units=max_units,
        estimated_duration_seconds=round(estimated_duration, 6),
        status=status,
        requires_operator_review=requires_review,
        flags=tuple(flags),
    )


def calibrate_units_per_second(
    samples: Iterable[SpeechRateSample],
    *,
    default_units_per_second: float = DEFAULT_VI_UNITS_PER_SECOND,
    min_samples: int = MIN_CALIBRATION_SAMPLES,
) -> SpeechRateCalibration:
    rates = [
        float(sample.spoken_units) / float(sample.duration_seconds)
        for sample in samples
        if sample.spoken_units > 0
        and sample.duration_seconds > 0
        and 2.0 <= (float(sample.spoken_units) / float(sample.duration_seconds)) <= 9.0
    ]
    if len(rates) < max(1, int(min_samples)):
        return SpeechRateCalibration(
            units_per_second=round(float(default_units_per_second), 6),
            source="default_insufficient_samples",
            sample_count=len(rates),
        )
    value = max(2.5, min(8.0, float(statistics.median(rates))))
    return SpeechRateCalibration(
        units_per_second=round(value, 6),
        source="calibrated_median",
        sample_count=len(rates),
    )


def extract_protected_tokens(
    *texts: str,
    include_acronyms: bool = True,
) -> tuple[str, ...]:
    tokens: list[str] = []
    for raw in texts:
        text = str(raw or "")
        urls = [match.group(0).rstrip(")]}>,.;:!?") for match in _URL_RE.finditer(text)]
        tokens.extend(urls)
        without_urls = _URL_RE.sub(" ", text)
        tokens.extend(match.group(0) for match in _NUMBER_RE.finditer(without_urls))
        if include_acronyms:
            tokens.extend(match.group(0) for match in _ACRONYM_RE.finditer(without_urls))
        tokens.extend(match.group(0) for match in _UNIT_RE.finditer(without_urls))
    unique: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        key = token.casefold()
        if key and key not in seen:
            seen.add(key)
            unique.append(token)
    return tuple(unique)


def validate_protected_tokens(
    required_tokens: Iterable[str],
    candidate_text: str,
) -> ProtectedTokenValidation:
    required = tuple(str(token) for token in required_tokens if str(token))
    missing = tuple(
        token for token in required if not _protected_token_present(token, candidate_text)
    )
    return ProtectedTokenValidation(
        valid=not missing,
        required_tokens=required,
        missing_tokens=missing,
    )


def _protected_token_present(token: str, text: str) -> bool:
    candidate = str(text or "")
    if token.lower().startswith(("http://", "https://")):
        return token.casefold() in candidate.casefold()
    escaped = re.escape(token)
    if token[0].isdigit():
        return bool(re.search(rf"(?<!\d){escaped}(?!\d)", candidate))
    return bool(re.search(rf"(?<!\w){escaped}(?!\w)", candidate, re.IGNORECASE))


def _number_spoken_units(token: str) -> int:
    normalized = token.replace(",", ".")
    integer_raw, dot, decimal_raw = normalized.partition(".")
    try:
        integer = int(integer_raw or "0")
    except ValueError:
        return 1
    total = _integer_spoken_units(integer)
    if dot and decimal_raw:
        total += 1 + len([char for char in decimal_raw if char.isdigit()])
    return max(1, total)


def _integer_spoken_units(value: int) -> int:
    number = abs(int(value))
    if number == 0:
        return 1
    total = 0
    group_index = 0
    while number > 0:
        group = number % 1000
        if group:
            total += _under_thousand_units(group)
            if group_index > 0:
                total += 1
        number //= 1000
        group_index += 1
    return total


def _under_thousand_units(value: int) -> int:
    number = int(value)
    count = 0
    if number >= 100:
        count += 2
        number %= 100
    if number >= 20:
        count += 2
        if number % 10:
            count += 1
    elif number >= 10:
        count += 1
        if number % 10:
            count += 1
    elif number > 0:
        count += 1
    return count
