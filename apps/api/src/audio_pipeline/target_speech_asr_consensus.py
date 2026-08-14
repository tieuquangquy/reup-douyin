"""Fail-closed consensus between original-mix and separated-vocal ASR."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Any, Sequence

from src.audio_pipeline.types import TranscriptionUnit


TARGET_SPEECH_ASR_CONSENSUS_VERSION = "target-speech-asr-consensus-v1"
_SIGNATURE_RE = re.compile(r"[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


@dataclass(frozen=True)
class TargetSpeechAsrConsensus:
    units: tuple[TranscriptionUnit, ...]
    diagnostics: dict[str, Any]


def choose_target_speech_asr(
    *,
    original_units: Sequence[TranscriptionUnit],
    separated_units: Sequence[TranscriptionUnit] = (),
    target_seconds: float,
    prefer_separated: bool,
) -> TargetSpeechAsrConsensus:
    original = list(original_units)
    separated = list(separated_units)
    original_score = _quality(original, target_seconds=target_seconds)
    separated_score = _quality(separated, target_seconds=target_seconds)
    original_text = _signature("".join(row.text for row in original))
    separated_text = _signature("".join(row.text for row in separated))
    agreement = (
        SequenceMatcher(None, original_text, separated_text).ratio()
        if original_text and separated_text
        else None
    )
    flags: list[str] = []
    if original and separated:
        if agreement is not None and agreement < 0.34:
            flags.extend(["asr_stem_disagreement", "needs_operator_review"])
        elif agreement is not None and agreement >= 0.72:
            flags.append("asr_stem_consensus")
        choose_separated = bool(
            separated_score > original_score + 0.02
            or (prefer_separated and separated_score >= original_score - 0.04)
        )
    else:
        choose_separated = bool(separated and not original)
        if separated and not original:
            flags.append("asr_recovered_from_separated_vocal")
        elif original and not separated and prefer_separated:
            flags.extend(["separated_asr_empty", "needs_operator_review"])
    chosen = separated if choose_separated else original
    source = "separated_vocal" if choose_separated else "target_mix"
    if not chosen:
        source = "none"
    if flags:
        chosen = [
            replace(
                row,
                flags=list(dict.fromkeys([*(row.flags or []), *flags])),
                raw_payload={
                    **dict(row.raw_payload or {}),
                    "target_speech_asr_consensus": {
                        "recipe_version": TARGET_SPEECH_ASR_CONSENSUS_VERSION,
                        "selected_source": source,
                        "agreement": agreement,
                        "original_score": original_score,
                        "separated_score": separated_score,
                    },
                },
            )
            for row in chosen
        ]
    return TargetSpeechAsrConsensus(
        units=tuple(chosen),
        diagnostics={
            "recipe_version": TARGET_SPEECH_ASR_CONSENSUS_VERSION,
            "selected_source": source,
            "agreement": round(agreement, 6) if agreement is not None else None,
            "original_score": original_score,
            "separated_score": separated_score,
            "original_units": len(original),
            "separated_units": len(separated),
            "flags": flags,
        },
    )


def _quality(units: Sequence[TranscriptionUnit], *, target_seconds: float) -> float:
    if not units:
        return 0.0
    confidences = [
        max(0.0, min(1.0, float(row.confidence)))
        for row in units
        if row.confidence is not None
    ]
    confidence = sum(confidences) / len(confidences) if confidences else 0.60
    text = _signature("".join(row.text for row in units))
    rate = len(text) / max(0.25, target_seconds)
    rate_score = 1.0 if 0.8 <= rate <= 9.5 else 0.55 if 0.25 <= rate <= 13.0 else 0.15
    timed = sum(row.end_seconds > row.start_seconds for row in units) / len(units)
    repetition = _repetition_penalty(text)
    score = 0.55 * confidence + 0.20 * rate_score + 0.15 * timed + 0.10 * (1.0 - repetition)
    return round(max(0.0, min(1.0, score)), 6)


def _repetition_penalty(text: str) -> float:
    if len(text) < 8:
        return 0.0
    chunks = [text[index : index + 3] for index in range(len(text) - 2)]
    if not chunks:
        return 0.0
    return max(0.0, min(1.0, 1.0 - len(set(chunks)) / len(chunks)))


def _signature(text: str) -> str:
    return "".join(_SIGNATURE_RE.findall(str(text or ""))).casefold()
