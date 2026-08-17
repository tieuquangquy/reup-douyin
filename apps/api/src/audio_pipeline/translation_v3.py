"""Context-aware, duration-constrained Translation V3 primitives.

The module intentionally has no provider or database dependency.  It builds stable
dialogue blocks, validates/ranks provider candidates locally, fingerprints a run and
serializes durable per-block checkpoints.  Provider calls remain in
``translation_llm.py`` and persistence remains in ``AudioAnalysisService``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from src.audio_pipeline.machine_translate import contains_cjk
from src.audio_pipeline.speech_budget import (
    DEFAULT_VI_UNITS_PER_SECOND,
    assess_speech_budget,
    extract_protected_tokens,
    validate_protected_tokens,
)
from src.audio_pipeline.types import (
    TranscriptDraftSegment,
    TranslationDraftSegment,
    TranslationPreset,
)


TRANSLATION_V3_RECIPE_VERSION = "translation-v3-contextual-semantic-utterance-ranking-6"


@dataclass(frozen=True)
class TranslationV3Policy:
    max_core_beats: int = 10
    max_block_seconds: float = 30.0
    context_overlap_beats: int = 2
    candidate_count: int = 3
    units_per_second: float = DEFAULT_VI_UNITS_PER_SECOND
    excellent_tolerance: float = 0.08
    acceptable_tolerance: float = 0.12
    rewrite_tolerance: float = 0.15

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_TRANSLATION_V3_POLICY = TranslationV3Policy()


@dataclass(frozen=True)
class TranslationContextBlock:
    block_id: str
    block_index: int
    core_segments: tuple[TranscriptDraftSegment, ...]
    context_before: tuple[TranscriptDraftSegment, ...]
    context_after: tuple[TranscriptDraftSegment, ...]

    def request_payload(
        self,
        *,
        glossary: Mapping[str, str] | None = None,
        translation_memory: Mapping[int, str] | None = None,
        policy: TranslationV3Policy = DEFAULT_TRANSLATION_V3_POLICY,
    ) -> dict[str, Any]:
        memory = translation_memory or {}
        return {
            "schema_version": "translation_context_block_v3",
            "recipe_version": TRANSLATION_V3_RECIPE_VERSION,
            "block_id": self.block_id,
            "block_index": self.block_index,
            "candidate_count": policy.candidate_count,
            "glossary": dict(glossary or {}),
            "context_before": [_context_row(row) for row in self.context_before],
            "segments": [
                {
                    **_context_row(row),
                    "duration_seconds": round(row.duration_seconds, 3),
                    "max_vi_spoken_units": _spoken_unit_cap(row, policy=policy),
                    "candidate_count": adaptive_candidate_count(row, policy=policy),
                    "translation_memory_vi": str(memory.get(row.segment_index) or "").strip() or None,
                }
                for row in self.core_segments
            ],
            "context_after": [_context_row(row) for row in self.context_after],
        }


@dataclass(frozen=True)
class TranslationCandidate:
    text: str
    style: str = "natural"
    semantic_fidelity: float | None = None
    context_consistency: float | None = None
    prosody_score: float | None = None


@dataclass(frozen=True)
class CandidateSelection:
    selected: TranslationCandidate | None
    selected_evaluation: dict[str, Any] | None
    evaluations: tuple[dict[str, Any], ...]
    requires_rewrite: bool
    requires_review: bool


def build_context_blocks(
    segments: Sequence[TranscriptDraftSegment],
    *,
    policy: TranslationV3Policy = DEFAULT_TRANSLATION_V3_POLICY,
) -> list[TranslationContextBlock]:
    """Build non-overlapping authority blocks with read-only neighboring context."""

    ordered = sorted(segments, key=lambda row: (row.segment_index, row.start_seconds))
    if not ordered:
        return []
    groups: list[tuple[int, int]] = []
    start = 0
    for position in range(1, len(ordered)):
        prospective_count = position - start + 1
        prospective_span = ordered[position].end_seconds - ordered[start].start_seconds
        if (
            prospective_count > max(1, int(policy.max_core_beats))
            or prospective_span > max(1.0, float(policy.max_block_seconds))
        ):
            groups.append((start, position))
            start = position
    groups.append((start, len(ordered)))

    overlap = max(0, int(policy.context_overlap_beats))
    blocks: list[TranslationContextBlock] = []
    for block_index, (left, right) in enumerate(groups):
        core = tuple(ordered[left:right])
        before = tuple(ordered[max(0, left - overlap) : left])
        after = tuple(ordered[right : min(len(ordered), right + overlap)])
        identity = {
            "recipe": TRANSLATION_V3_RECIPE_VERSION,
            "indices": [row.segment_index for row in core],
            "texts": [row.normalized_source_text for row in core],
        }
        digest = _sha256_json(identity)[:12]
        blocks.append(
            TranslationContextBlock(
                block_id=f"b{block_index + 1:03d}-{digest}",
                block_index=block_index,
                core_segments=core,
                context_before=before,
                context_after=after,
            )
        )
    return blocks


def parse_candidate(value: Mapping[str, Any] | str, *, fallback_style: str = "natural") -> TranslationCandidate:
    if isinstance(value, str):
        return TranslationCandidate(text=value.strip(), style=fallback_style)
    return TranslationCandidate(
        text=str(value.get("text") or value.get("vi") or "").strip(),
        style=str(value.get("style") or fallback_style).strip() or fallback_style,
        semantic_fidelity=_optional_score(value.get("semantic_fidelity")),
        context_consistency=_optional_score(value.get("context_consistency")),
        prosody_score=_optional_score(value.get("prosody_score")),
    )


def translation_run_fingerprint(
    segments: Sequence[TranscriptDraftSegment],
    *,
    preset: TranslationPreset,
    provider_identity: Mapping[str, Any],
    user_prompt: str | None,
    glossary: Mapping[str, str] | None,
    policy: TranslationV3Policy = DEFAULT_TRANSLATION_V3_POLICY,
) -> str:
    payload = {
        "recipe_version": TRANSLATION_V3_RECIPE_VERSION,
        "preset": str(preset),
        "provider": dict(provider_identity),
        "prompt_sha256": hashlib.sha256(str(user_prompt or "").encode("utf-8")).hexdigest(),
        "glossary_sha256": _sha256_json(dict(glossary or {})),
        "policy": policy.to_dict(),
        "segments": [
            {
                "segment_index": row.segment_index,
                "start_ms": round(row.start_seconds * 1000),
                "end_ms": round(row.end_seconds * 1000),
                "source": row.normalized_source_text,
                "speaker": row.speaker_label,
            }
            for row in sorted(segments, key=lambda item: item.segment_index)
        ],
    }
    return _sha256_json(payload)


def translation_provider_identity(provider: object) -> dict[str, Any]:
    primary = getattr(provider, "primary", None)
    target = primary or provider
    return {
        "provider": str(getattr(target, "provider_name", type(target).__name__)),
        "model": str(getattr(target, "model", "") or "") or None,
        "base_url_sha256": (
            hashlib.sha256(str(getattr(target, "base_url", "")).encode("utf-8")).hexdigest()
            if getattr(target, "base_url", None)
            else None
        ),
    }


def draft_to_checkpoint(row: TranslationDraftSegment) -> dict[str, Any]:
    return {
        "segment_index": row.segment_index,
        "translated_text": row.translated_text,
        "translation_preset": str(row.translation_preset),
        "duration_budget_seconds": row.duration_budget_seconds,
        "estimated_tts_duration_seconds": row.estimated_tts_duration_seconds,
        "quality_flags": list(row.quality_flags),
        "metadata": dict(row.metadata),
    }


def draft_from_checkpoint(payload: Mapping[str, Any]) -> TranslationDraftSegment:
    return TranslationDraftSegment(
        segment_index=int(payload.get("segment_index") or 0),
        translated_text=str(payload.get("translated_text") or ""),
        translation_preset=TranslationPreset(
            str(payload.get("translation_preset") or TranslationPreset.LITERAL_SAFE)
        ),
        duration_budget_seconds=float(payload.get("duration_budget_seconds") or 0.0),
        estimated_tts_duration_seconds=(
            float(payload["estimated_tts_duration_seconds"])
            if payload.get("estimated_tts_duration_seconds") is not None
            else None
        ),
        quality_flags=[str(value) for value in list(payload.get("quality_flags") or [])],
        metadata=dict(payload.get("metadata") or {}),
    )


def build_translation_quality_contract(
    rows: Sequence[TranslationDraftSegment],
    *,
    total_count: int,
    cache_hit: bool = False,
) -> dict[str, Any]:
    hard_block_flags = {
        "translation_gate_failed",
        "translation_too_long_for_slot",
        "duration_rewrite_no_safe_candidate",
        "duration_adaptation_required",
    }
    filled = [row for row in rows if row.translated_text.strip()]
    blocked = [
        row
        for row in rows
        if not row.translated_text.strip() or bool(set(row.quality_flags).intersection(hard_block_flags))
    ]
    review = [
        row
        for row in rows
        if "needs_operator_review" in row.quality_flags and row not in blocked
    ]
    providers = sorted(
        {
            str(row.metadata.get("llm_provider") or row.metadata.get("provider") or "unknown")
            for row in rows
        }
    )
    requested_candidates = sum(
        int(
            dict(row.metadata.get("translation_v3") or {}).get(
                "requested_candidate_count"
            )
            or 1
        )
        for row in rows
    )
    generated_candidates = sum(
        int(dict(row.metadata.get("translation_v3") or {}).get("candidate_count") or 1)
        for row in rows
    )
    selective_review_count = sum(
        1
        for row in rows
        if "translation_selective_semantic_review" in row.quality_flags
    )
    complete = len(filled) == int(total_count) and not blocked
    return {
        "schema_version": "translation_quality_contract_v3",
        "recipe_version": TRANSLATION_V3_RECIPE_VERSION,
        "total_count": int(total_count),
        "filled_count": len(filled),
        "review_required_count": len(review),
        "blocked_count": len(blocked),
        "complete": complete,
        "tts_ready": complete and not review,
        "provider_mix": providers,
        "requested_candidate_count": requested_candidates,
        "generated_candidate_count": generated_candidates,
        "adaptive_candidate_tokens_saved_vs_three_each": max(
            0,
            (int(total_count) * 3) - requested_candidates,
        ),
        "selective_semantic_review_count": selective_review_count,
        "cache_hit": bool(cache_hit),
    }


def _evaluate_candidate(
    source_text: str,
    candidate: TranslationCandidate,
    *,
    slot_seconds: float,
    glossary: Mapping[str, str] | None,
    translation_memory_vi: str | None,
    policy: TranslationV3Policy,
) -> dict[str, Any]:
    text = candidate.text.strip()
    required_tokens = extract_protected_tokens(source_text)
    protected = validate_protected_tokens(required_tokens, text)
    issues: list[str] = []
    if not text:
        issues.append("empty_candidate")
    if contains_cjk(text):
        issues.append("candidate_contains_cjk")
    if not protected.valid:
        issues.append("protected_token_mismatch")

    budget = assess_speech_budget(
        text,
        slot_seconds=max(0.1, float(slot_seconds)),
        units_per_second=policy.units_per_second,
        fit_tolerance=policy.acceptable_tolerance,
    )
    slot = max(0.1, float(slot_seconds))
    estimate = max(0.0, float(budget.estimated_duration_seconds))
    delta_ratio = abs(estimate - slot) / slot
    over_ratio = max(0.0, estimate - slot) / slot
    under_ratio = max(0.0, slot - estimate) / slot
    requires_rewrite = over_ratio > policy.rewrite_tolerance
    requires_review = (
        requires_rewrite
        or delta_ratio > policy.acceptable_tolerance
        or bool(issues)
    )

    semantic_prior = {
        "faithful": 0.97,
        "literal": 0.97,
        "natural": 0.92,
        "compact": 0.86,
    }.get(candidate.style.casefold(), 0.90)
    semantic = _blend_optional_score(semantic_prior, candidate.semantic_fidelity)
    if not protected.valid:
        semantic = min(semantic, 0.35)

    context = _context_score(
        source_text,
        text,
        glossary=glossary,
        translation_memory_vi=translation_memory_vi,
        provider_score=candidate.context_consistency,
    )
    naturalness = _naturalness_score(text)
    duration = max(0.0, min(1.0, 1.0 - (delta_ratio / 0.45)))
    if requires_rewrite:
        duration = min(duration, 0.30)
    prosody = _blend_optional_score(_prosody_score(text), candidate.prosody_score)
    tts_eligibility_reasons: list[str] = []
    if issues:
        tts_eligibility_reasons.extend(issues)
    if semantic < 0.75:
        tts_eligibility_reasons.append("semantic_score_below_tts_floor")
    if context < 0.70:
        tts_eligibility_reasons.append("context_score_below_tts_floor")
    if naturalness < 0.55:
        tts_eligibility_reasons.append("naturalness_score_below_tts_floor")
    if budget.status == "too_long":
        tts_eligibility_reasons.append("speech_budget_too_long")
    total = (
        semantic * 0.30
        + context * 0.20
        + naturalness * 0.20
        + duration * 0.20
        + prosody * 0.10
    )
    return {
        "candidate_index": -1,  # replaced below to keep the record JSON-only
        "style": candidate.style,
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "hard_valid": not issues,
        # TTS may probe alternatives only when Translation explicitly grants
        # semantic/naturalness authority. ``hard_valid`` alone merely proves
        # that the string is structurally safe.
        "tts_eligible": not tts_eligibility_reasons,
        "tts_eligibility_reasons": list(dict.fromkeys(tts_eligibility_reasons)),
        "issues": issues,
        "protected_tokens": list(required_tokens),
        "missing_protected_tokens": list(protected.missing_tokens),
        "speech_budget": budget.to_dict(),
        "duration_delta_ratio": round(delta_ratio, 6),
        "duration_over_ratio": round(over_ratio, 6),
        "duration_under_ratio": round(under_ratio, 6),
        "requires_rewrite": requires_rewrite,
        "requires_review": requires_review,
        "scores": {
            "semantic": round(semantic, 4),
            "context": round(context, 4),
            "naturalness": round(naturalness, 4),
            "duration": round(duration, 4),
            "prosody": round(prosody, 4),
        },
        "total_score": round(total, 6),
    }


def _context_score(
    source_text: str,
    candidate_text: str,
    *,
    glossary: Mapping[str, str] | None,
    translation_memory_vi: str | None,
    provider_score: float | None,
) -> float:
    score = 0.92
    applicable = 0
    matched = 0
    for source_term, target_term in dict(glossary or {}).items():
        if str(source_term) and str(source_term) in source_text:
            applicable += 1
            if str(target_term).casefold() in candidate_text.casefold():
                matched += 1
    if applicable:
        score = matched / applicable
    memory = str(translation_memory_vi or "").strip()
    if memory and candidate_text.casefold() == memory.casefold():
        score = min(1.0, score + 0.06)
    return _blend_optional_score(score, provider_score)


def _naturalness_score(text: str) -> float:
    if not text.strip() or contains_cjk(text):
        return 0.0
    score = 1.0
    if re.search(r"\b([\wÀ-ỹ]+)(?:\s+\1){2,}\b", text, re.IGNORECASE):
        score -= 0.35
    if re.search(r"[!?.,]{3,}", text):
        score -= 0.15
    if re.search(r"\s{2,}", text):
        score -= 0.10
    if len(text.split()) == 1 and len(text) > 18:
        score -= 0.15
    if re.search(r"(?i)\b(?:analysis|reasoning|translation|final answer)\s*:", text):
        score = 0.0
    return max(0.0, min(1.0, score))


def _prosody_score(text: str) -> float:
    punctuation = len(re.findall(r"[,;:.!?]", text))
    words = max(1, len(text.split()))
    density = punctuation / words
    if density > 0.45:
        return 0.55
    if text.rstrip().endswith((",", ";", ":")):
        return 0.75
    return 0.95


def _context_row(row: TranscriptDraftSegment) -> dict[str, Any]:
    return {
        "id": str(row.segment_index),
        "segment_index": row.segment_index,
        "zh": row.normalized_source_text,
        "speaker": row.speaker_label,
        "source_confidence": row.confidence,
        "start_seconds": round(row.start_seconds, 3),
        "end_seconds": round(row.end_seconds, 3),
    }


def _spoken_unit_cap(
    row: TranscriptDraftSegment,
    *,
    policy: TranslationV3Policy,
) -> int:
    # Vietnamese often needs more spoken units than Chinese has characters.
    # The calibrated physical slot is the hard authority; source length is a
    # quality signal only and must never force semantic omission.
    return max(
        3,
        int(math.ceil(row.duration_seconds * policy.units_per_second * 1.12)),
    )


def adaptive_candidate_count(
    row: TranscriptDraftSegment,
    *,
    policy: TranslationV3Policy = DEFAULT_TRANSLATION_V3_POLICY,
) -> int:
    """Spend candidate tokens only where ambiguity or timing risk justifies it."""

    maximum = max(1, int(policy.candidate_count))
    flags = set(row.difficulty_flags or [])
    protected = extract_protected_tokens(row.normalized_source_text)
    confidence = float(row.confidence) if row.confidence is not None else 0.75
    if (
        confidence < 0.72
        or flags.intersection(
            {
                "needs_operator_review",
                "low_confidence",
                "caption_asr_conflict",
                "duration_fit",
                "asr_temporal_overlap",
            }
        )
        or protected
        or row.duration_seconds < 1.8
    ):
        return maximum
    if row.duration_seconds < 3.2 or confidence < 0.86:
        return min(maximum, 2)
    return 1


def _optional_score(value: object) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _blend_optional_score(base: float, provider: float | None) -> float:
    if provider is None:
        return max(0.0, min(1.0, base))
    # Provider self-scores are useful tie-breakers, never local authority.
    return max(0.0, min(1.0, (base * 0.8) + (provider * 0.2)))


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def select_translation_candidate(
    source_text: str,
    candidates: Sequence[TranslationCandidate],
    *,
    slot_seconds: float,
    glossary: Mapping[str, str] | None = None,
    translation_memory_vi: str | None = None,
    policy: TranslationV3Policy = DEFAULT_TRANSLATION_V3_POLICY,
) -> CandidateSelection:
    indexed: list[dict[str, Any]] = []
    non_empty_candidates: list[TranslationCandidate] = []
    for candidate in candidates:
        if not candidate.text.strip():
            continue
        row = _evaluate_candidate(
            source_text,
            candidate,
            slot_seconds=slot_seconds,
            glossary=glossary,
            translation_memory_vi=translation_memory_vi,
            policy=policy,
        )
        row["candidate_index"] = len(non_empty_candidates)
        indexed.append(row)
        non_empty_candidates.append(candidate)
    evaluations = tuple(indexed)
    hard_valid = [row for row in evaluations if row["hard_valid"]]
    within_acceptable_timing = [row for row in hard_valid if not row["requires_review"]]
    preferred = [row for row in hard_valid if not row["requires_rewrite"]]
    # A semantically valid candidate already inside the accepted physical slot
    # beats a marginally higher-scoring candidate that would force review/TTS
    # correction. Weighted score remains the tie-breaker within the same band.
    if not hard_valid:
        return CandidateSelection(None, None, evaluations, True, True)
    if within_acceptable_timing or preferred:
        pool = within_acceptable_timing or preferred
        chosen = max(
            pool,
            key=lambda row: (float(row["total_score"]), -int(row["candidate_index"])),
        )
    else:
        # Every structurally valid candidate is too long. Start the controlled
        # rewrite from the closest physical fit, not from a marginally higher
        # semantic score that costs more tokens to repair.
        chosen = min(
            hard_valid,
            key=lambda row: (
                int(dict(row.get("speech_budget") or {}).get("spoken_units") or 10**9),
                -float(row["total_score"]),
                int(row["candidate_index"]),
            ),
        )
    selected = non_empty_candidates[int(chosen["candidate_index"])]
    return CandidateSelection(
        selected=selected,
        selected_evaluation=chosen,
        evaluations=evaluations,
        requires_rewrite=bool(chosen["requires_rewrite"]),
        requires_review=bool(chosen["requires_review"]),
    )
