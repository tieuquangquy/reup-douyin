"""Pure, provider-free admission contract for Translation Draft -> TTS."""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
import hashlib
import json
import re
from typing import Mapping, Sequence

from src.audio_pipeline.speech_budget import (
    assess_speech_budget,
    extract_protected_tokens,
    validate_protected_tokens,
)
from src.tts_pipeline.services.duration_planner import plan_initial_speaking_rate
from src.tts_pipeline.services.speech_text import build_vietnamese_speech_text
from src.tts_pipeline.types import TranslationInputSegment, VoiceConfig


TTS_INPUT_PREFLIGHT_SCHEMA = "tts-input-preflight-v1"
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_REVIEW_FLAGS = frozenset(
    {
        "duration_adaptation_required",
        "duration_rewrite_no_safe_candidate",
        "machine_translate_recovery",
        "needs_operator_review",
        "translation_gate_failed",
        "translation_llm_unavailable",
        "translation_selective_semantic_review",
        "translation_too_long_for_slot",
        "translation_v3_candidate_review",
    }
)


class TtsPreflightStatus(StrEnum):
    READY = "READY"
    AUTO_FIT = "AUTO_FIT"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"


def rank_preflight_candidates(
    segment: TranslationInputSegment,
    *,
    slot_seconds: float,
    units_per_second: float,
    pronunciation_glossary: Mapping[str, str] | None = None,
) -> list[str]:
    """Keep semantic authority fixed and rank only approved, token-safe text."""

    candidates = list(
        dict.fromkeys(
            normalized
            for raw in (segment.translated_text, *segment.candidate_texts)
            if (normalized := " ".join(str(raw or "").split()))
        )
    )
    if not candidates:
        return []
    protected = extract_protected_tokens(
        str(segment.source_text or ""),
        str(segment.translated_text or ""),
        include_acronyms=False,
    )
    safe = [
        text for text in candidates if validate_protected_tokens(protected, text).valid
    ] or [candidates[0]]

    def score(item: tuple[int, str]) -> tuple[float, float, int]:
        index, text = item
        speech = build_vietnamese_speech_text(
            text,
            pronunciation_glossary=pronunciation_glossary,
        )
        assessment = assess_speech_budget(
            speech.speech_text,
            slot_seconds=max(0.001, float(slot_seconds)),
            units_per_second=units_per_second,
        )
        penalty = {"fits_budget": 0.0, "too_short": 1.0, "too_long": 2.0}.get(
            assessment.status,
            3.0,
        )
        return penalty, abs(assessment.spoken_units - assessment.target_units), index

    return [text for _, text in sorted(enumerate(safe), key=score)][:4]


def build_tts_input_preflight(
    segments: Sequence[TranslationInputSegment],
    *,
    source_video_id: object,
    timeline_duration_ms: int,
    translation_input_sha256: str,
    translation_authority_sha256: str | None,
    voice_config: VoiceConfig,
    voice_authority: Mapping[str, object] | None,
    units_per_second: float,
    pronunciation_glossary: Mapping[str, str] | None = None,
) -> dict:
    rows: list[dict] = []
    previous_end = -1
    for segment in sorted(segments, key=lambda row: (row.start_ms, row.segment_index)):
        display = " ".join(str(segment.translated_text or "").split())
        speech = build_vietnamese_speech_text(
            display,
            pronunciation_glossary=pronunciation_glossary,
        )
        slot_seconds = max(0.001, float(segment.duration_budget_ms) / 1000.0)
        candidates = rank_preflight_candidates(
            segment,
            slot_seconds=slot_seconds,
            units_per_second=units_per_second,
            pronunciation_glossary=pronunciation_glossary,
        )
        selected = candidates[0] if candidates else display
        selected_speech = build_vietnamese_speech_text(
            selected,
            pronunciation_glossary=pronunciation_glossary,
        )
        assessment = assess_speech_budget(
            selected_speech.speech_text,
            slot_seconds=slot_seconds,
            units_per_second=units_per_second,
        )
        rate_plan = plan_initial_speaking_rate(
            selected_speech.speech_text,
            slot_seconds=slot_seconds,
            units_per_second=units_per_second,
            base_speaking_rate=voice_config.speaking_rate,
        )
        reasons: list[str] = []
        blocked = False
        if not display:
            reasons.append("empty_translation")
            blocked = True
        if _CJK_RE.search(display):
            reasons.append("cjk_remaining_in_translation")
            blocked = True
        if segment.start_ms < 0 or segment.end_ms <= segment.start_ms:
            reasons.append("invalid_timing")
            blocked = True
        if segment.start_ms < previous_end:
            reasons.append("overlapping_timing")
            blocked = True
        if timeline_duration_ms > 0 and segment.end_ms > timeline_duration_ms:
            reasons.append("timing_exceeds_source_video")
            blocked = True
        protected = extract_protected_tokens(
            str(segment.source_text or ""),
            display,
            include_acronyms=False,
        )
        token_validation = validate_protected_tokens(protected, selected)
        if not token_validation.valid:
            reasons.append("protected_tokens_missing")
            blocked = True
        review_flags = sorted(set(segment.quality_flags).intersection(_REVIEW_FLAGS))
        pending_review = bool(review_flags) and str(
            segment.translation_status or ""
        ).upper() != "APPROVED"
        if pending_review:
            reasons.extend(f"review_flag:{flag}" for flag in review_flags)

        if blocked:
            status = TtsPreflightStatus.BLOCKED
        elif pending_review or rate_plan.estimated_ratio > 1.35:
            if rate_plan.estimated_ratio > 1.35:
                reasons.append("predicted_duration_overflow_above_auto_fit_limit")
            status = TtsPreflightStatus.NEEDS_REVIEW
        elif rate_plan.action != "keep_base_rate" or assessment.status == "too_long":
            reasons.append("predicted_duration_auto_fit")
            status = TtsPreflightStatus.AUTO_FIT
        else:
            status = TtsPreflightStatus.READY
        previous_end = max(previous_end, int(segment.end_ms))
        rows.append(
            {
                "translation_segment_id": str(segment.translation_segment_id),
                "transcript_segment_id": str(segment.transcript_segment_id),
                "segment_index": int(segment.segment_index),
                "display_text_sha256": _sha256_text(display),
                "speech_text_sha256": _sha256_text(selected_speech.speech_text),
                "normalizer_version": selected_speech.normalizer_version,
                "normalizer_actions": list(selected_speech.actions),
                "start_ms": int(segment.start_ms),
                "end_ms": int(segment.end_ms),
                "slot_ms": int(segment.duration_budget_ms),
                "estimated_duration_seconds": assessment.estimated_duration_seconds,
                "estimated_ratio": rate_plan.estimated_ratio,
                "selected_primary_candidate_sha256": _sha256_text(selected),
                "eligible_candidate_sha256": [_sha256_text(value) for value in candidates],
                "eligible_candidate_count": len(candidates),
                "initial_rate_plan": rate_plan.to_dict(),
                "status": status.value,
                "reasons": list(dict.fromkeys(reasons)),
            }
        )

    counts = Counter(row["status"] for row in rows)
    admission_ready = bool(rows) and not counts[
        TtsPreflightStatus.BLOCKED.value
    ] and not counts[TtsPreflightStatus.NEEDS_REVIEW.value]
    glossary_payload = dict(pronunciation_glossary or {})
    return {
        "schema_version": TTS_INPUT_PREFLIGHT_SCHEMA,
        "source_video_id": str(source_video_id),
        "translation_input_sha256": translation_input_sha256,
        "translation_authority_sha256": translation_authority_sha256,
        "voice_authority": dict(voice_authority or {}),
        "voice_config": voice_config.__dict__,
        "units_per_second": round(float(units_per_second), 6),
        "pronunciation_glossary_sha256": _sha256_json(glossary_payload),
        "segment_count": len(rows),
        "status_counts": dict(counts),
        "admission_ready": admission_ready,
        "segments": rows,
    }


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
