"""Deterministic, local semantic utterance reconstruction for Chinese ASR.

FunASR timestamps are timing evidence, not sentence authority.  This module keeps
the measured token timeline immutable, then derives translation-ready utterances
with a global boundary optimizer.  No cloud/model call is made here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from typing import Any, Iterable, Sequence

from src.audio_pipeline.types import TranscriptionUnit


SEMANTIC_DIALOGUE_RECIPE_VERSION = "semantic-dialogue-segmentation-v1"

_SPACE_RE = re.compile(r"\s+")
_STRONG_PUNCTUATION = "。！？!?；;"
_SOFT_PUNCTUATION = "，、,：:"

# These are grammatical continuation signals, not a domain glossary.  A boundary
# after one of them is possible, but must be backed by much stronger pause/prosody
# evidence than a normal candidate.
_INCOMPLETE_SUFFIXES = (
    "因为", "所以", "如果", "虽然", "但是", "然后", "接着", "以及", "而且",
    "还有", "不是说", "就是说", "比如", "例如", "只要", "为了", "关于",
    "的", "地", "得", "把", "被", "给", "在", "从", "向", "和", "与", "及",
    "或", "但", "而", "就", "还", "又", "再", "先", "让", "使", "有", "是",
    "为", "到", "用", "跟", "像", "比", "对", "我", "你", "他", "她", "它",
    "这", "那",
)

_DISCOURSE_STARTS = (
    "首先", "其次", "然后", "接着", "最后", "另外", "同时", "而且", "但是",
    "不过", "所以", "如果", "其实", "今天", "下面", "接下来", "再来", "你看",
    "大家看", "姐妹们", "什么都别说", "话不多说",
)

_TERMINAL_SUFFIXES = (
    "就行", "就好", "好了", "可以了", "完成了", "结束了", "没错", "对吧",
    "试试吧", "看看吧", "知道了", "明白了", "画起来", "戴好了",
)

_CONTINUATION_STARTS = (
    "了", "着", "过", "的", "地", "得", "多了", "一点", "一些", "一下",
    "起来", "进去", "出来", "上去", "下去", "以后", "之后",
)

# Protect frequent multi-character lexical units at a proposed boundary.  This is
# deliberately small and general; punctuation/pause remains the primary signal.
_NO_SPLIT_TERMS = (
    "然后", "还有", "而且", "但是", "因为", "所以", "如果", "这个", "那个",
    "什么", "怎么", "一下", "一起", "已经", "可以", "时候", "里面", "上面",
    "下面", "后面", "前面", "颜色", "黑色", "白色", "粉色", "总结", "高光",
    "鼻影", "眼影", "化妆", "修容", "鼻子", "眼睛", "帽子", "衣服",
    "提亮", "面中", "只要", "看到", "立体鼻", "方便多了", "粉质", "说牛不牛",
)


@dataclass(frozen=True)
class SemanticSegmentationPolicy:
    min_utterance_ms: int = 1_800
    target_min_ms: int = 3_000
    target_max_ms: int = 9_500
    max_utterance_ms: int = 14_000
    hard_max_utterance_ms: int = 18_000
    hard_pause_ms: int = 1_200
    strong_pause_ms: int = 700
    medium_pause_ms: int = 350
    soft_pause_ms: int = 160

    def to_dict(self) -> dict[str, int]:
        return {
            "min_utterance_ms": self.min_utterance_ms,
            "target_min_ms": self.target_min_ms,
            "target_max_ms": self.target_max_ms,
            "max_utterance_ms": self.max_utterance_ms,
            "hard_max_utterance_ms": self.hard_max_utterance_ms,
            "hard_pause_ms": self.hard_pause_ms,
            "strong_pause_ms": self.strong_pause_ms,
            "medium_pause_ms": self.medium_pause_ms,
            "soft_pause_ms": self.soft_pause_ms,
        }


DEFAULT_SEMANTIC_SEGMENTATION_POLICY = SemanticSegmentationPolicy()


@dataclass(frozen=True)
class SemanticSegmentationResult:
    units: tuple[TranscriptionUnit, ...]
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class _Token:
    text: str
    start_ms: float
    end_ms: float
    confidence: float | None
    speaker_label: str | None
    flags: tuple[str, ...]
    source_unit_index: int
    source_token_index: int
    source_unit_duration_ms: float
    chunk_index: int | None


@dataclass(frozen=True)
class _BoundaryEvidence:
    score: float
    reasons: tuple[str, ...]
    incomplete: bool
    legacy_cap: bool


def segment_semantic_dialogue(
    units: Sequence[TranscriptionUnit],
    *,
    policy: SemanticSegmentationPolicy = DEFAULT_SEMANTIC_SEGMENTATION_POLICY,
) -> SemanticSegmentationResult:
    """Build translation-ready utterances from a stitched ASR token timeline."""

    ordered = sorted(
        [unit for unit in units if str(unit.text or "").strip() and unit.end_seconds > unit.start_seconds],
        key=lambda unit: (unit.start_seconds, unit.end_seconds),
    )
    tokens = _flatten_tokens(ordered)
    if not tokens:
        return SemanticSegmentationResult(
            units=tuple(ordered),
            diagnostics={
                "recipe_version": SEMANTIC_DIALOGUE_RECIPE_VERSION,
                "translation_ready": False,
                "reason": "no_timed_tokens",
                "input_unit_count": len(ordered),
                "token_count": 0,
                "output_utterance_count": len(ordered),
            },
        )

    boundaries = {
        index: _boundary_evidence(tokens, index, policy=policy)
        for index in range(1, len(tokens))
    }
    cuts = _optimize_boundaries(tokens, boundaries, policy=policy)
    utterances = _materialize_utterances(tokens, cuts, boundaries)
    utterances, overlap_repairs = _repair_output_overlaps(utterances)

    input_text = _join_token_text(token.text for token in tokens)
    output_text = _join_token_text(unit.text for unit in utterances)
    authority_preserved = _normalize_authority_text(input_text) == _normalize_authority_text(output_text)
    output_overlap_count = sum(
        1
        for left, right in zip(utterances, utterances[1:])
        if right.start_seconds < left.end_seconds - 0.001
    )
    selected_evidence = [boundaries[index] for index in cuts[:-1] if index in boundaries]
    low_confidence_count = sum(
        1 for evidence in selected_evidence if evidence.score < 0.0 or evidence.incomplete
    )
    legacy_cap_observed = sum(1 for evidence in boundaries.values() if evidence.legacy_cap)
    legacy_cap_selected = sum(1 for evidence in selected_evidence if evidence.legacy_cap)
    authority_sha = hashlib.sha256(
        json.dumps(
            [
                [token.text, round(token.start_ms, 3), round(token.end_ms, 3), token.source_unit_index]
                for token in tokens
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    translation_ready = bool(utterances and authority_preserved and output_overlap_count == 0)
    diagnostics = {
        "recipe_version": SEMANTIC_DIALOGUE_RECIPE_VERSION,
        "policy": policy.to_dict(),
        "input_unit_count": len(ordered),
        "token_count": len(tokens),
        "output_utterance_count": len(utterances),
        "legacy_cap_boundary_observed_count": legacy_cap_observed,
        "legacy_cap_boundary_selected_count": legacy_cap_selected,
        "low_confidence_boundary_count": low_confidence_count,
        "timeline_overlap_repair_count": overlap_repairs,
        "output_overlap_count": output_overlap_count,
        "authority_preserved": authority_preserved,
        "authority_sha256": authority_sha,
        "translation_ready": translation_ready,
    }
    return SemanticSegmentationResult(units=tuple(utterances), diagnostics=diagnostics)


def _flatten_tokens(units: Sequence[TranscriptionUnit]) -> list[_Token]:
    tokens: list[_Token] = []
    for unit_index, unit in enumerate(units):
        raw = dict(unit.raw_payload or {})
        timestamps = raw.get("timestamps")
        parsed_timestamps: list[tuple[float, float]] = []
        if isinstance(timestamps, list):
            for value in timestamps:
                if not isinstance(value, (list, tuple)) or len(value) < 2:
                    parsed_timestamps = []
                    break
                try:
                    start_ms = float(value[0])
                    end_ms = float(value[1])
                except (TypeError, ValueError):
                    parsed_timestamps = []
                    break
                if start_ms < 0 or end_ms <= start_ms:
                    parsed_timestamps = []
                    break
                parsed_timestamps.append((start_ms, end_ms))

        pieces = _tokenize_unit_text(str(unit.text or ""), len(parsed_timestamps))
        if parsed_timestamps and len(pieces) == len(parsed_timestamps):
            offset_ms = _timestamp_offset_ms(unit, raw, parsed_timestamps)
            for token_index, (piece, timing) in enumerate(zip(pieces, parsed_timestamps, strict=True)):
                tokens.append(
                    _Token(
                        text=piece,
                        start_ms=timing[0] + offset_ms,
                        end_ms=timing[1] + offset_ms,
                        confidence=unit.confidence,
                        speaker_label=unit.speaker_label,
                        flags=tuple(unit.flags or ()),
                        source_unit_index=unit_index,
                        source_token_index=token_index,
                        source_unit_duration_ms=max(0.0, (unit.end_seconds - unit.start_seconds) * 1000.0),
                        chunk_index=_int_or_none(raw.get("chunk_index")),
                    )
                )
            continue

        # sentence_info and untimed compatibility rows remain atomic.  Their
        # measured outer timing is still safe to merge with neighboring units.
        tokens.append(
            _Token(
                text=str(unit.text or "").strip(),
                start_ms=float(unit.start_seconds) * 1000.0,
                end_ms=float(unit.end_seconds) * 1000.0,
                confidence=unit.confidence,
                speaker_label=unit.speaker_label,
                flags=tuple(unit.flags or ()),
                source_unit_index=unit_index,
                source_token_index=0,
                source_unit_duration_ms=max(0.0, (unit.end_seconds - unit.start_seconds) * 1000.0),
                chunk_index=_int_or_none(raw.get("chunk_index")),
            )
        )
    return sorted(tokens, key=lambda token: (token.start_ms, token.end_ms, token.source_unit_index))


def _timestamp_offset_ms(
    unit: TranscriptionUnit,
    raw: dict[str, Any],
    timestamps: Sequence[tuple[float, float]],
) -> float:
    if raw.get("timestamps_are_absolute") is True:
        return 0.0
    measured_start = float(unit.start_seconds) * 1000.0
    first_start = timestamps[0][0]
    chunk_offset = max(0.0, float(raw.get("chunk_start_seconds") or 0.0) * 1000.0)
    # Pick the interpretation that best matches the already-normalized unit.
    if abs((first_start + chunk_offset) - measured_start) + 1.0 < abs(first_start - measured_start):
        return chunk_offset
    return 0.0


def _tokenize_unit_text(text: str, expected_count: int) -> list[str]:
    if expected_count <= 0:
        return []
    split = [piece for piece in text.split() if piece]
    if len(split) == expected_count:
        return split
    compact = _SPACE_RE.sub("", text)
    if len(compact) == expected_count:
        return list(compact)
    return []


def _boundary_evidence(
    tokens: Sequence[_Token],
    index: int,
    *,
    policy: SemanticSegmentationPolicy,
) -> _BoundaryEvidence:
    left_token = tokens[index - 1]
    right_token = tokens[index]
    left_context = _join_token_text(token.text for token in tokens[max(0, index - 10):index])
    right_context = _join_token_text(token.text for token in tokens[index:min(len(tokens), index + 10)])
    compact_left = _normalize_authority_text(left_context)
    compact_right = _normalize_authority_text(right_context)
    pause_ms = max(0.0, right_token.start_ms - left_token.end_ms)
    score = 0.0
    reasons: list[str] = []

    last = compact_left[-1:] if compact_left else ""
    if last in _STRONG_PUNCTUATION:
        score += 12.0
        reasons.append("strong_punctuation")
    elif last in _SOFT_PUNCTUATION:
        score += 4.0
        reasons.append("soft_punctuation")

    if pause_ms >= max(1, policy.hard_pause_ms):
        score += 22.0 + min(6.0, (pause_ms - policy.hard_pause_ms) / 400.0)
        reasons.append("hard_pause")
    elif pause_ms >= max(1, policy.strong_pause_ms):
        score += 10.0 + min(4.0, (pause_ms - policy.strong_pause_ms) / 300.0)
        reasons.append("strong_pause")
    elif pause_ms >= max(1, policy.medium_pause_ms):
        score += 6.0
        reasons.append("medium_pause")
    elif pause_ms >= max(1, policy.soft_pause_ms):
        score += 2.5
        reasons.append("soft_pause")
    elif pause_ms >= 60.0:
        score += 0.75
        reasons.append("micro_pause")

    left_speaker = str(left_token.speaker_label or "").strip()
    right_speaker = str(right_token.speaker_label or "").strip()
    if left_speaker and right_speaker and left_speaker != right_speaker:
        score += 14.0
        reasons.append("speaker_change")

    if any(compact_right.startswith(value) for value in _DISCOURSE_STARTS):
        score += 4.5
        reasons.append("discourse_restart")
    if any(compact_left.endswith(value) for value in _TERMINAL_SUFFIXES):
        score += 3.0
        reasons.append("terminal_phrase")
    if last in "吧吗呢呀啊啦嘛哦哇呗":
        score += 2.5
        reasons.append("sentence_final_particle")

    if any(compact_right.startswith(value) for value in _CONTINUATION_STARTS):
        score -= 8.0
        reasons.append("continuation_prefix_veto")

    incomplete = any(compact_left.endswith(value) for value in _INCOMPLETE_SUFFIXES)
    if incomplete:
        score -= 7.0
        reasons.append("incomplete_clause_veto")

    if _crosses_protected_lexeme(compact_left, compact_right):
        score -= 12.0
        incomplete = True
        reasons.append("lexeme_split_veto")

    legacy_cap = False
    if left_token.source_unit_index != right_token.source_unit_index:
        duration = left_token.source_unit_duration_ms
        legacy_cap = 7_700 <= duration <= 8_400 or 14_500 <= duration <= 15_500
        if legacy_cap and not any(
            reason in reasons for reason in ("strong_punctuation", "hard_pause", "strong_pause", "speaker_change")
        ):
            score -= 5.0
            reasons.append("legacy_duration_cap_veto")

    return _BoundaryEvidence(
        score=round(score, 4),
        reasons=tuple(dict.fromkeys(reasons)),
        incomplete=incomplete,
        legacy_cap=legacy_cap,
    )


def _crosses_protected_lexeme(left: str, right: str) -> bool:
    if not left or not right:
        return False
    for term in _NO_SPLIT_TERMS:
        for split in range(1, len(term)):
            if left.endswith(term[:split]) and right.startswith(term[split:]):
                return True
    return False


def _optimize_boundaries(
    tokens: Sequence[_Token],
    boundaries: dict[int, _BoundaryEvidence],
    *,
    policy: SemanticSegmentationPolicy,
) -> list[int]:
    count = len(tokens)
    costs = [math.inf] * (count + 1)
    previous: list[int | None] = [None] * (count + 1)
    costs[0] = 0.0
    hard_boundaries = {
        index
        for index, evidence in boundaries.items()
        if "hard_pause" in evidence.reasons or "speaker_change" in evidence.reasons
    }
    hard_prefix = [0] * (count + 1)
    for index in range(1, count + 1):
        hard_prefix[index] = hard_prefix[index - 1] + (1 if index in hard_boundaries else 0)

    for right in range(1, count + 1):
        for left in range(right - 1, -1, -1):
            duration_ms = max(0.0, tokens[right - 1].end_ms - tokens[left].start_ms)
            atomic_oversize = left == right - 1 and duration_ms > policy.hard_max_utterance_ms
            if duration_ms > policy.hard_max_utterance_ms and not atomic_oversize:
                break
            if not math.isfinite(costs[left]):
                continue
            if hard_prefix[right - 1] - hard_prefix[left] > 0:
                continue
            duration_cost = _duration_cost(duration_ms, policy=policy)
            evidence = boundaries.get(right)
            boundary_cost = 0.0 if right == count else -(evidence.score if evidence else 0.0)
            candidate = costs[left] + duration_cost + boundary_cost + 0.04
            if candidate < costs[right]:
                costs[right] = candidate
                previous[right] = left

    if previous[count] is None:
        return list(range(1, count + 1))
    cuts: list[int] = []
    cursor = count
    while cursor > 0:
        cuts.append(cursor)
        cursor = previous[cursor] if previous[cursor] is not None else 0
    cuts.reverse()
    return cuts


def _duration_cost(duration_ms: float, *, policy: SemanticSegmentationPolicy) -> float:
    if duration_ms < policy.min_utterance_ms:
        return 9.0 + (policy.min_utterance_ms - duration_ms) / 160.0
    if duration_ms < policy.target_min_ms:
        return 1.5 + (policy.target_min_ms - duration_ms) / 550.0
    if duration_ms <= policy.target_max_ms:
        # A shallow preference around seven seconds avoids both subtitle chatter
        # and oversized TTS slots without inventing a hard time boundary.
        return abs(duration_ms - 7_000.0) / 10_000.0
    cost = 0.8 + (duration_ms - policy.target_max_ms) / 1_700.0
    if duration_ms > policy.max_utterance_ms:
        cost += 5.0 + (duration_ms - policy.max_utterance_ms) / 500.0
    return cost


def _materialize_utterances(
    tokens: Sequence[_Token],
    cuts: Sequence[int],
    boundaries: dict[int, _BoundaryEvidence],
) -> list[TranscriptionUnit]:
    units: list[TranscriptionUnit] = []
    left = 0
    for utterance_index, right in enumerate(cuts):
        members = list(tokens[left:right])
        if not members:
            left = right
            continue
        text = _join_token_text(token.text for token in members)
        confidences = [token.confidence for token in members if token.confidence is not None]
        confidence = sum(confidences) / len(confidences) if confidences else None
        speakers = list(dict.fromkeys(str(token.speaker_label).strip() for token in members if token.speaker_label))
        flags = list(dict.fromkeys(flag for token in members for flag in token.flags))
        if "asr_temporal_overlap" in flags:
            flags.remove("asr_temporal_overlap")
            flags.append("asr_source_overlap_observed")
        flags.append("semantic_dialogue_segmented")
        end_evidence = boundaries.get(right)
        if end_evidence is not None and (end_evidence.score < 0.0 or end_evidence.incomplete):
            flags.append("semantic_boundary_low_confidence")
        source_units = list(dict.fromkeys(token.source_unit_index for token in members))
        chunks = list(dict.fromkeys(token.chunk_index for token in members if token.chunk_index is not None))
        authority_payload = [
            [token.text, round(token.start_ms, 3), round(token.end_ms, 3), token.source_unit_index, token.source_token_index]
            for token in members
        ]
        authority_sha = hashlib.sha256(
            json.dumps(authority_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        units.append(
            TranscriptionUnit(
                text=text,
                start_seconds=round(members[0].start_ms / 1000.0, 3),
                end_seconds=round(members[-1].end_ms / 1000.0, 3),
                confidence=round(confidence, 6) if confidence is not None else None,
                speaker_label=speakers[0] if len(speakers) == 1 else None,
                flags=list(dict.fromkeys(flags)),
                raw_payload={
                    "provider": "semantic_dialogue_local",
                    "tokens": [token.text for token in members],
                    "timestamps": [[round(token.start_ms, 3), round(token.end_ms, 3)] for token in members],
                    "timestamps_are_absolute": True,
                    "semantic_segmentation": {
                        "recipe_version": SEMANTIC_DIALOGUE_RECIPE_VERSION,
                        "utterance_index": utterance_index,
                        "global_token_range": [left, right - 1],
                        "source_unit_indices": source_units,
                        "source_chunk_indices": chunks,
                        "authority_sha256": authority_sha,
                        "end_boundary_score": end_evidence.score if end_evidence else None,
                        "end_boundary_reasons": list(end_evidence.reasons) if end_evidence else ["timeline_end"],
                    },
                },
            )
        )
        left = right
    return units


def _repair_output_overlaps(units: Sequence[TranscriptionUnit]) -> tuple[list[TranscriptionUnit], int]:
    repaired = list(units)
    count = 0
    for index in range(1, len(repaired)):
        previous = repaired[index - 1]
        current = repaired[index]
        if current.start_seconds >= previous.end_seconds:
            continue
        boundary = round((current.start_seconds + previous.end_seconds) / 2.0, 3)
        boundary = max(previous.start_seconds + 0.05, min(current.end_seconds - 0.05, boundary))
        previous_flags = list(dict.fromkeys([*(previous.flags or []), "semantic_timeline_overlap_repaired"]))
        current_flags = list(dict.fromkeys([*(current.flags or []), "semantic_timeline_overlap_repaired"]))
        repaired[index - 1] = replace(previous, end_seconds=boundary, flags=previous_flags)
        repaired[index] = replace(current, start_seconds=boundary, flags=current_flags)
        count += 1
    return repaired, count


def _join_token_text(values: Iterable[str]) -> str:
    result = ""
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        if not result:
            result = value
            continue
        if value[:1] in _STRONG_PUNCTUATION + _SOFT_PUNCTUATION + ".":
            result += value
            continue
        left = result[-1:]
        if left.isascii() and left.isalnum() and value[:1].isascii() and value[:1].isalnum():
            result += " " + value
        else:
            result += value
    return result.strip()


def _normalize_authority_text(value: str) -> str:
    return _SPACE_RE.sub("", str(value or "")).strip()


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
