"""Deterministic pre-translation repair for unusably short dialogue beats."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from src.audio_pipeline.semantic_dialogue_segmentation import SEMANTIC_DIALOGUE_RECIPE_VERSION


MICRO_BEAT_MS = 800
SHORT_INCOMPLETE_BEAT_MS = 1_600
MICRO_NEIGHBOR_GAP_MS = 350
INCOMPLETE_NEIGHBOR_GAP_MS = 1_000
MAX_MERGED_SPAN_MS = 15_000
TRANSLATION_PREMERGE_RECIPE_VERSION = "translation-temporal-premerge-1"

_TRAILING_PUNCTUATION_RE = re.compile(r"[\s，。！？、；：,.!?;:]+$")
_INCOMPLETE_SUFFIXES = (
    "因为",
    "所以",
    "如果",
    "然后",
    "接着",
    "以及",
    "是",
    "的",
    "把",
    "被",
    "和",
    "与",
    "及",
    "在",
    "用",
    "为",
    "给",
    "向",
    "到",
    "从",
    "就",
    "还",
    "又",
    "再",
    "先",
    "喷",
    "腌",
)


@dataclass(frozen=True)
class TranslationPremergeGroup:
    members: tuple[object, ...]
    reasons: tuple[str, ...]


def plan_translation_premerge(beats: Sequence[object]) -> list[TranslationPremergeGroup]:
    """Return ordered temporal groups; singleton groups mean no mutation."""

    ordered = sorted(beats, key=lambda row: (int(row.start_ms), int(row.segment_index)))
    if not ordered:
        return []
    parents = list(range(len(ordered)))
    reasons_by_root: dict[int, list[str]] = {}

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def members_for(root: int) -> list[int]:
        return [index for index in range(len(ordered)) if find(index) == root]

    def union(left: int, right: int, reason: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        combined = members_for(left_root) + members_for(right_root)
        known_speakers = {
            str(getattr(ordered[index], "speaker_label", None) or "").strip()
            for index in combined
            if str(getattr(ordered[index], "speaker_label", None) or "").strip()
        }
        if len(known_speakers) > 1:
            return
        start_ms = min(int(ordered[index].start_ms) for index in combined)
        end_ms = max(int(ordered[index].end_ms) for index in combined)
        if end_ms - start_ms > MAX_MERGED_SPAN_MS:
            return
        parents[right_root] = left_root
        reasons = [
            *reasons_by_root.pop(left_root, []),
            *reasons_by_root.pop(right_root, []),
            reason,
        ]
        reasons_by_root[left_root] = list(dict.fromkeys(reasons))

    for index, beat in enumerate(ordered):
        duration_ms = max(0, int(beat.end_ms) - int(beat.start_ms))
        if (
            duration_ms <= SHORT_INCOMPLETE_BEAT_MS
            and index + 1 < len(ordered)
            and _ends_in_incomplete_clause(str(getattr(beat, "normalized_text", None) or beat.text or ""))
        ):
            following = ordered[index + 1]
            gap_ms = int(following.start_ms) - int(beat.end_ms)
            if (
                0 <= gap_ms <= INCOMPLETE_NEIGHBOR_GAP_MS
                and _speaker_compatible(beat, following)
            ):
                union(index, index + 1, "short_incomplete_clause")
                continue

        if duration_ms > MICRO_BEAT_MS:
            continue
        candidates: list[tuple[int, int]] = []
        if index > 0:
            previous = ordered[index - 1]
            gap_ms = int(beat.start_ms) - int(previous.end_ms)
            if 0 <= gap_ms <= MICRO_NEIGHBOR_GAP_MS and _speaker_compatible(previous, beat):
                candidates.append((gap_ms, index - 1))
        if index + 1 < len(ordered):
            following = ordered[index + 1]
            gap_ms = int(following.start_ms) - int(beat.end_ms)
            if 0 <= gap_ms <= MICRO_NEIGHBOR_GAP_MS and _speaker_compatible(beat, following):
                candidates.append((gap_ms, index + 1))
        if not candidates:
            continue
        # Terminal fragments naturally belong to the preceding phrase. Otherwise use
        # the closest boundary, preferring the previous beat on an exact tie.
        if index == len(ordered) - 1 and any(target == index - 1 for _, target in candidates):
            target = index - 1
        else:
            target = min(candidates, key=lambda item: (item[0], 0 if item[1] < index else 1))[1]
        union(min(index, target), max(index, target), "micro_beat")

    groups: list[TranslationPremergeGroup] = []
    seen_roots: set[int] = set()
    for index in range(len(ordered)):
        root = find(index)
        if root in seen_roots:
            continue
        seen_roots.add(root)
        indices = members_for(root)
        groups.append(
            TranslationPremergeGroup(
                members=tuple(ordered[position] for position in indices),
                reasons=tuple(reasons_by_root.get(root, [])),
            )
        )
    return sorted(groups, key=lambda group: int(group.members[0].start_ms))


def _speaker_compatible(left: object, right: object) -> bool:
    if _premerge_locked(left) or _premerge_locked(right):
        return False
    left_speaker = str(getattr(left, "speaker_label", None) or "").strip()
    right_speaker = str(getattr(right, "speaker_label", None) or "").strip()
    return not left_speaker or not right_speaker or left_speaker == right_speaker


def _ends_in_incomplete_clause(text: str) -> bool:
    compact = re.sub(r"\s+", "", _TRAILING_PUNCTUATION_RE.sub("", str(text or "")))
    return bool(compact) and compact.endswith(_INCOMPLETE_SUFFIXES)


def merge_translation_premerge_text(values: Sequence[object]) -> str:
    """Join Chinese-first ASR fragments without inventing audible pauses."""

    merged = ""
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        separator = " " if merged and merged[-1:].isalnum() and value[:1].isascii() and value[:1].isalnum() else ""
        merged = f"{merged}{separator}{value}"
    return merged


def _premerge_locked(row: object) -> bool:
    metadata = getattr(row, "metadata_json", None)
    if not isinstance(metadata, dict):
        return False
    payload = metadata.get("translation_premerge")
    if isinstance(payload, dict) and payload.get("recipe_version") == TRANSLATION_PREMERGE_RECIPE_VERSION:
        return True
    raw = metadata.get("raw_payload")
    semantic = dict(raw).get("semantic_segmentation") if isinstance(raw, dict) else None
    return (
        isinstance(semantic, dict)
        and semantic.get("recipe_version") == SEMANTIC_DIALOGUE_RECIPE_VERSION
    )
