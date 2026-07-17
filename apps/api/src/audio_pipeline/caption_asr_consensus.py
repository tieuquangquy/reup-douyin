"""Caption ↔ ASR consensus for machine-first Chinese DialogueBeats.

Caption Douyin (title/hashtags) is a quality signal only — never DialogueBeat text.
Spoken authority is FunASR units + timing.
"""

from __future__ import annotations

import re
from dataclasses import replace
from difflib import SequenceMatcher

from src.audio_pipeline.types import TranscriptionUnit

_ZH_NOISE_RE = re.compile(r"[\s\W_]+", re.UNICODE)
_PUNCT_ONLY_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)

# Similarity thresholds (normalized character overlap).
AGREE_THRESHOLD = 0.72
AUTO_APPROVE_MIN_CONFIDENCE = 0.55
AUTO_APPROVE_CONFLICT_MIN_CONFIDENCE = 0.7


def normalize_zh_for_compare(text: str) -> str:
    return _ZH_NOISE_RE.sub("", (text or "").strip().lower())


def caption_asr_similarity(caption: str, asr_text: str) -> float:
    left = normalize_zh_for_compare(caption)
    right = normalize_zh_for_compare(asr_text)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def is_punctuation_only_unit(unit: TranscriptionUnit) -> bool:
    text = (unit.text or "").strip()
    if not text:
        return True
    return bool(_PUNCT_ONLY_RE.match(text))


def drop_punctuation_only_units(units: list[TranscriptionUnit]) -> list[TranscriptionUnit]:
    """Remove junk beats like '!' left by bad caption segmentation / ASR noise."""
    return [unit for unit in units if not is_punctuation_only_unit(unit)]


def _with_flag(unit: TranscriptionUnit, flag: str) -> TranscriptionUnit:
    flags = list(unit.flags or [])
    if flag not in flags:
        flags.append(flag)
    return replace(unit, flags=flags)


def _add_flag_all(units: list[TranscriptionUnit], flag: str) -> list[TranscriptionUnit]:
    return [_with_flag(unit, flag) for unit in units]


def apply_caption_asr_consensus(
    units: list[TranscriptionUnit],
    *,
    caption: str | None,
    duration_seconds: float | None,
) -> list[TranscriptionUnit]:
    """
    Compare caption to ASR for flags only. DialogueBeat text+timing stay ASR.

    - No ASR units → [] (never invent from caption).
    - No caption → keep ASR, flag source_unverified.
    - High similarity → keep ASR, flag caption_agreed.
    - Soft/hard mismatch → keep ASR, flag caption_asr_conflict.
    """
    del duration_seconds  # caption is never retimed onto the timeline as dialogue
    if not units:
        return []

    cleaned_caption = (caption or "").strip()
    if not cleaned_caption:
        return _add_flag_all(units, "source_unverified")

    asr_joined = "".join((unit.text or "").strip() for unit in units)
    similarity = caption_asr_similarity(cleaned_caption, asr_joined)

    if similarity >= AGREE_THRESHOLD:
        return _add_flag_all(units, "caption_agreed")

    # Soft or hard conflict: ASR remains speech authority.
    return _add_flag_all(units, "caption_asr_conflict")


def should_auto_approve_source(flags: list[str], *, avg_confidence: float | None) -> bool:
    """
    Machine-first approve gate.

    Auto-approve when consensus is clean, or when conflict still has usable confidence
    so a non-Chinese operator can move to Vietnamese review. Block only heavy conflict
    combined with weak confidence.
    """
    flag_set = set(flags or [])
    confidence = float(avg_confidence) if avg_confidence is not None else 0.0
    if "caption_agreed" in flag_set:
        return True
    if "caption_asr_conflict" in flag_set:
        return "low_confidence" not in flag_set and confidence >= AUTO_APPROVE_CONFLICT_MIN_CONFIDENCE
    if confidence >= AUTO_APPROVE_MIN_CONFIDENCE:
        return True
    return False
