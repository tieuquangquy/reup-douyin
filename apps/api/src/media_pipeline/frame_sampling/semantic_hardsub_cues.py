"""Local cross-modal authority for hard-sub display cues.

OCR observations own geometry, not meaning.  This module aligns temporal OCR
epochs with the immutable ASR token timeline, canonicalizes transition variants,
and reuses an approved dialogue translation to plan Vietnamese display cues.
No OCR, translation, or cloud model call is made here.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping, Sequence


SEMANTIC_HARDSUB_RECIPE_VERSION = "semantic-hardsub-cue-authority-v1"
SEMANTIC_HARDSUB_SCHEMA_VERSION = "semantic_hardsub_cues_v1"

_CJK_OR_DIGIT_RE = re.compile(r"[0-9\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ASCII_ALNUM_RE = re.compile(r"[A-Za-z0-9]")
_SPACE_RE = re.compile(r"\s+")
_PLATFORM_UI_RE = re.compile(
    r"(?:\d+天前|\d+小时前|\d+分钟前|山东|北京|上海|广东|关注|评论|点赞|转发)"
)


@dataclass(frozen=True)
class SemanticHardsubResult:
    timeline: tuple[dict[str, Any], ...]
    protected_source_tracks: tuple[dict[str, Any], ...]
    summary: dict[str, Any]


@dataclass(frozen=True)
class _AuthorityToken:
    text: str
    start_ms: float
    end_ms: float


@dataclass(frozen=True)
class _TranscriptAuthority:
    transcript_segment_id: str
    segment_index: int
    start_ms: int
    end_ms: int
    text: str
    tokens: tuple[_AuthorityToken, ...]
    translation_segment_id: str | None
    translation_text: str | None
    translation_status: str | None
    translation_sha256: str | None


def apply_semantic_hardsub_authority(
    timeline: Sequence[Mapping[str, Any]],
    *,
    dialogue_authority: Mapping[str, Any] | None,
    fps: float,
    frame_width: int,
    frame_height: int,
) -> SemanticHardsubResult:
    """Return canonicalized OCR rows plus fail-closed source protections."""

    authority_rows = _parse_dialogue_authority(dialogue_authority or {})
    annotated: list[dict[str, Any]] = []
    protected: list[dict[str, Any]] = []
    for index, raw in enumerate(timeline):
        row = dict(raw)
        text_id = str(row.get("text_id") or f"track_{index:04d}")
        candidate = _candidate_text(row)
        start_ms, end_ms = _row_span_ms(row, fps=fps)
        role = str(row.get("semantic_role") or row.get("ocr_role") or "").strip()
        provenance = dict(row.get("visual_provenance") or {})
        classification = str(provenance.get("classification") or "UNCERTAIN")

        if classification in {
            "SOURCE_INTRINSIC",
            "SOURCE_INTRINSIC_PANEL",
            "PLATFORM_UI",
        }:
            protected.append(_protected_row(row, reason="existing_source_provenance"))
            continue
        if _looks_like_platform_ui(candidate, role=role):
            provenance = {
                "classification": "SOURCE_INTRINSIC",
                "confidence": 0.94,
                "policy_version": SEMANTIC_HARDSUB_RECIPE_VERSION,
                "reasons": ["platform_ui_lexical_signature", "preserve_source_pixels"],
            }
            row["visual_provenance"] = provenance
            protected.append(_protected_row(row, reason="semantic_platform_ui"))
            continue

        alignment = _best_dialogue_alignment(
            candidate,
            start_ms=start_ms,
            end_ms=end_ms,
            authority_rows=authority_rows,
        )
        transition_noise = _looks_like_transition_noise(
            candidate,
            duration_ms=max(0, end_ms - start_ms),
        )
        if alignment is not None:
            classification = "DIALOGUE_HARDSUB"
            provenance = {
                "classification": classification,
                "confidence": round(float(alignment["score"]), 6),
                "policy_version": SEMANTIC_HARDSUB_RECIPE_VERSION,
                "reasons": [
                    "monotonic_temporal_asr_alignment",
                    "ocr_geometry_asr_text_authority",
                ],
            }
        elif classification == "EDITOR_OVERLAY":
            classification = "EDITOR_LABEL"
            provenance = {
                **provenance,
                "classification": classification,
                "policy_version": SEMANTIC_HARDSUB_RECIPE_VERSION,
                "reasons": list(
                    dict.fromkeys(
                        [
                            *list(provenance.get("reasons") or []),
                            "explicit_editor_provenance_without_dialogue_alignment",
                        ]
                    )
                ),
            }
        elif classification not in {"EDITOR_LABEL", "DIALOGUE_HARDSUB"}:
            classification = "UNCERTAIN"
            provenance = {
                **provenance,
                "classification": "UNCERTAIN",
                "policy_version": SEMANTIC_HARDSUB_RECIPE_VERSION,
                "reasons": list(
                    dict.fromkeys(
                        [
                            *list(provenance.get("reasons") or []),
                            "missing_safe_editor_or_dialogue_authority",
                        ]
                    )
                ),
            }

        row["visual_provenance"] = provenance
        row["semantic_hardsub"] = {
            "schema_version": SEMANTIC_HARDSUB_SCHEMA_VERSION,
            "recipe_version": SEMANTIC_HARDSUB_RECIPE_VERSION,
            "classification": classification,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "ocr_text_observed": candidate,
            "text_authority": (
                str(alignment.get("asr_text") or "").strip()
                if alignment is not None
                else candidate
            ),
            "alignment": dict(alignment or {}),
            "transition_noise": transition_noise,
            "action": "CANDIDATE",
        }
        annotated.append(row)

    _canonicalize_overlapping_epochs(annotated, frame_width=frame_width, frame_height=frame_height)
    _attach_transition_noise(annotated, frame_width=frame_width, frame_height=frame_height)
    _plan_dialogue_render_text(annotated, authority_rows=authority_rows)

    localizable: list[dict[str, Any]] = []
    quarantined = 0
    for row in annotated:
        semantic = dict(row.get("semantic_hardsub") or {})
        classification = str(semantic.get("classification") or "UNCERTAIN")
        action = str(semantic.get("action") or "")
        if classification == "UNCERTAIN":
            protected.append(_protected_row(row, reason="semantic_uncertain_fail_closed"))
            continue
        if action == "COVER_ONLY_TRANSITION":
            quarantined += 1
        localizable.append(row)

    dialogue_rows = [
        row
        for row in localizable
        if str(dict(row.get("semantic_hardsub") or {}).get("classification") or "")
        == "DIALOGUE_HARDSUB"
    ]
    cue_ids = {
        str(dict(row.get("semantic_hardsub") or {}).get("cue_id") or "")
        for row in localizable
        if str(dict(row.get("semantic_hardsub") or {}).get("cue_id") or "")
    }
    dialogue_cue_ids = {
        str(dict(row.get("semantic_hardsub") or {}).get("cue_id") or "")
        for row in dialogue_rows
    }
    planned_ids = {
        str(dict(row.get("semantic_hardsub") or {}).get("cue_id") or "")
        for row in dialogue_rows
        if (
            str(
                dict(row.get("semantic_hardsub") or {}).get(
                    "vi_text_authority"
                )
                or ""
            ).strip()
            or str(
                dict(row.get("semantic_hardsub") or {}).get("action") or ""
            )
            == "COVER_ONLY_DIALOGUE_EPOCH"
        )
    }
    authority_ref = dict((dialogue_authority or {}).get("authority_ref") or {})
    summary = {
        "schema_version": SEMANTIC_HARDSUB_SCHEMA_VERSION,
        "recipe_version": SEMANTIC_HARDSUB_RECIPE_VERSION,
        "dialogue_authority_ref": authority_ref or None,
        "input_tracks": len(timeline),
        "localizable_tracks": len(localizable),
        "protected_source_tracks": len(protected),
        "canonical_cues": len(cue_ids),
        "dialogue_tracks": len(dialogue_rows),
        "dialogue_cues": len(dialogue_cue_ids),
        "dialogue_cues_with_translation_authority": len(planned_ids),
        "transition_noise_tracks": sum(
            bool(dict(row.get("semantic_hardsub") or {}).get("transition_noise"))
            for row in annotated
        ),
        "cover_only_transition_tracks": quarantined,
        "ready": bool(
            not dialogue_cue_ids or dialogue_cue_ids.issubset(planned_ids)
        ),
    }
    summary["authority_sha256"] = _sha256_json(
        {
            "recipe_version": SEMANTIC_HARDSUB_RECIPE_VERSION,
            "dialogue_authority_ref": authority_ref,
            "cues": [
                {
                    "text_id": row.get("text_id"),
                    "semantic_hardsub": row.get("semantic_hardsub"),
                }
                for row in localizable
            ],
        }
    )
    return SemanticHardsubResult(
        timeline=tuple(localizable),
        protected_source_tracks=tuple(protected),
        summary=summary,
    )


def _parse_dialogue_authority(payload: Mapping[str, Any]) -> list[_TranscriptAuthority]:
    rows: list[_TranscriptAuthority] = []
    for raw in list(payload.get("segments") or []):
        if not isinstance(raw, Mapping):
            continue
        try:
            start_ms = int(raw.get("start_ms"))
            end_ms = int(raw.get("end_ms"))
        except (TypeError, ValueError):
            continue
        if end_ms <= start_ms:
            continue
        raw_payload = dict(raw.get("raw_payload") or {})
        tokens = _authority_tokens(
            text=str(raw.get("text") or ""),
            start_ms=start_ms,
            end_ms=end_ms,
            raw_payload=raw_payload,
        )
        translation = dict(raw.get("translation") or {})
        translation_text = str(translation.get("text") or "").strip() or None
        rows.append(
            _TranscriptAuthority(
                transcript_segment_id=str(raw.get("transcript_segment_id") or ""),
                segment_index=int(raw.get("segment_index") or 0),
                start_ms=start_ms,
                end_ms=end_ms,
                text=str(raw.get("text") or "").strip(),
                tokens=tuple(tokens),
                translation_segment_id=(
                    str(translation.get("translation_segment_id") or "").strip()
                    or None
                ),
                translation_text=translation_text,
                translation_status=(
                    str(translation.get("status") or "").strip() or None
                ),
                translation_sha256=(
                    hashlib.sha256(translation_text.encode("utf-8")).hexdigest()
                    if translation_text
                    else None
                ),
            )
        )
    return sorted(rows, key=lambda row: (row.start_ms, row.segment_index))


def _authority_tokens(
    *,
    text: str,
    start_ms: int,
    end_ms: int,
    raw_payload: Mapping[str, Any],
) -> list[_AuthorityToken]:
    values = raw_payload.get("timestamps")
    raw_tokens = list(raw_payload.get("tokens") or [])
    timestamps: list[tuple[float, float]] = []
    if isinstance(values, list):
        for value in values:
            if not isinstance(value, (list, tuple)) or len(value) < 2:
                timestamps = []
                break
            try:
                left, right = float(value[0]), float(value[1])
            except (TypeError, ValueError):
                timestamps = []
                break
            if right <= left:
                timestamps = []
                break
            timestamps.append((left, right))
    tokens = [str(value) for value in raw_tokens if str(value)]
    if timestamps and len(tokens) != len(timestamps):
        split = [value for value in str(text or "").split() if value]
        compact = _SPACE_RE.sub("", str(text or ""))
        tokens = split if len(split) == len(timestamps) else list(compact)
    if timestamps and len(tokens) == len(timestamps):
        # Semantic Dialogue V3 stores absolute timestamps.  Legacy local values
        # are shifted only when they clearly sit outside the transcript window.
        if (
            raw_payload.get("timestamps_are_absolute") is not True
            and timestamps[-1][1]
            <= float(end_ms - start_ms) + 2_000.0
            and timestamps[0][0] < max(1_000.0, float(start_ms) - 1_000.0)
        ):
            timestamps = [(left + start_ms, right + start_ms) for left, right in timestamps]
        return [
            _AuthorityToken(text=token, start_ms=timing[0], end_ms=timing[1])
            for token, timing in zip(tokens, timestamps, strict=True)
        ]
    compact = _SPACE_RE.sub("", str(text or ""))
    if not compact:
        return []
    span = max(1.0, float(end_ms - start_ms) / len(compact))
    return [
        _AuthorityToken(
            text=char,
            start_ms=start_ms + index * span,
            end_ms=start_ms + (index + 1) * span,
        )
        for index, char in enumerate(compact)
    ]


def _best_dialogue_alignment(
    candidate: str,
    *,
    start_ms: int,
    end_ms: int,
    authority_rows: Sequence[_TranscriptAuthority],
) -> dict[str, Any] | None:
    ocr_signature = _signature(candidate)
    if len(ocr_signature) < 2:
        return None
    best: tuple[float, _TranscriptAuthority, str, int] | None = None
    for authority in authority_rows:
        overlap = max(0, min(end_ms, authority.end_ms) - max(start_ms, authority.start_ms))
        if overlap <= 0:
            continue
        slice_tokens = [
            token
            for token in authority.tokens
            if (token.start_ms + token.end_ms) / 2.0 >= start_ms
            and (token.start_ms + token.end_ms) / 2.0 <= end_ms
        ]
        if not slice_tokens:
            slice_tokens = [
                token
                for token in authority.tokens
                if (token.start_ms + token.end_ms) / 2.0 >= start_ms - 160
                and (token.start_ms + token.end_ms) / 2.0 <= end_ms + 160
            ]
        asr_text = _join_tokens(token.text for token in slice_tokens) or authority.text
        asr_signature = _signature(asr_text)
        if not asr_signature:
            continue
        ratio = SequenceMatcher(None, ocr_signature, asr_signature).ratio()
        block = SequenceMatcher(None, ocr_signature, asr_signature).find_longest_match(
            0, len(ocr_signature), 0, len(asr_signature)
        )
        coverage = block.size / max(1, min(len(ocr_signature), len(asr_signature)))
        temporal = overlap / max(1, min(end_ms - start_ms, authority.end_ms - authority.start_ms))
        score = 0.5 * coverage + 0.3 * ratio + 0.2 * min(1.0, temporal)
        if best is None or score > best[0]:
            best = (score, authority, asr_text, len(slice_tokens))
    if best is None or best[0] < 0.46:
        return None
    score, authority, asr_text, token_count = best
    return {
        "policy_version": SEMANTIC_HARDSUB_RECIPE_VERSION,
        "score": round(score, 6),
        "transcript_segment_id": authority.transcript_segment_id,
        "transcript_segment_index": authority.segment_index,
        "transcript_start_ms": authority.start_ms,
        "transcript_end_ms": authority.end_ms,
        "asr_text": asr_text,
        "asr_token_count": token_count,
        "translation_segment_id": authority.translation_segment_id,
        "translation_status": authority.translation_status,
        "translation_sha256": authority.translation_sha256,
    }


def _canonicalize_overlapping_epochs(
    rows: list[dict[str, Any]],
    *,
    frame_width: int,
    frame_height: int,
) -> None:
    parents = list(range(len(rows)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left_index, left in enumerate(rows):
        left_sem = dict(left.get("semantic_hardsub") or {})
        if bool(left_sem.get("transition_noise")):
            continue
        for right_index in range(left_index + 1, len(rows)):
            right = rows[right_index]
            right_sem = dict(right.get("semantic_hardsub") or {})
            if bool(right_sem.get("transition_noise")):
                continue
            if str(left_sem.get("classification")) != str(right_sem.get("classification")):
                continue
            left_start, left_end = int(left_sem.get("start_ms") or 0), int(left_sem.get("end_ms") or 0)
            right_start, right_end = int(right_sem.get("start_ms") or 0), int(right_sem.get("end_ms") or 0)
            if right_start > left_end + 220 or left_start > right_end + 220:
                continue
            if _geometry_iou(left, right, frame_width=frame_width, frame_height=frame_height) < 0.25:
                continue
            left_text = _signature(str(left_sem.get("text_authority") or ""))
            right_text = _signature(str(right_sem.get("text_authority") or ""))
            similarity = SequenceMatcher(None, left_text, right_text).ratio()
            left_alignment = dict(left_sem.get("alignment") or {})
            right_alignment = dict(right_sem.get("alignment") or {})
            same_transcript = bool(
                left_alignment.get("transcript_segment_id")
                and left_alignment.get("transcript_segment_id")
                == right_alignment.get("transcript_segment_id")
            )
            if similarity >= 0.62 or (same_transcript and similarity >= 0.48):
                union(left_index, right_index)

    groups: dict[int, list[int]] = {}
    for index in range(len(rows)):
        groups.setdefault(find(index), []).append(index)
    for indices in groups.values():
        best_index = max(indices, key=lambda index: _row_authority_quality(rows[index]))
        best_semantic = dict(rows[best_index].get("semantic_hardsub") or {})
        identity = {
            "recipe_version": SEMANTIC_HARDSUB_RECIPE_VERSION,
            "classification": best_semantic.get("classification"),
            "transcript_segment_id": dict(best_semantic.get("alignment") or {}).get("transcript_segment_id"),
            "member_text_ids": sorted(str(rows[index].get("text_id") or "") for index in indices),
            "text_authority": best_semantic.get("text_authority"),
        }
        cue_id = f"cue_{_sha256_json(identity)[:14]}"
        for index in indices:
            semantic = dict(rows[index].get("semantic_hardsub") or {})
            semantic["cue_id"] = cue_id
            semantic["canonical_text_authority"] = best_semantic.get("text_authority")
            semantic["canonical_member_text_ids"] = identity["member_text_ids"]
            semantic["canonicalization_sha256"] = _sha256_json(identity)
            rows[index]["semantic_hardsub"] = semantic


def _attach_transition_noise(
    rows: list[dict[str, Any]],
    *,
    frame_width: int,
    frame_height: int,
) -> None:
    stable = [row for row in rows if not bool(dict(row.get("semantic_hardsub") or {}).get("transition_noise"))]
    for row in rows:
        semantic = dict(row.get("semantic_hardsub") or {})
        if not bool(semantic.get("transition_noise")):
            continue
        best: tuple[float, dict[str, Any]] | None = None
        start_ms, end_ms = int(semantic.get("start_ms") or 0), int(semantic.get("end_ms") or 0)
        for candidate in stable:
            candidate_semantic = dict(candidate.get("semantic_hardsub") or {})
            other_start = int(candidate_semantic.get("start_ms") or 0)
            other_end = int(candidate_semantic.get("end_ms") or 0)
            temporal_distance = max(0, other_start - end_ms, start_ms - other_end)
            if temporal_distance > 600:
                continue
            iou = _geometry_iou(row, candidate, frame_width=frame_width, frame_height=frame_height)
            if iou < 0.22:
                continue
            score = iou - temporal_distance / 2_000.0
            if best is None or score > best[0]:
                best = (score, candidate)
        if best is not None:
            host_semantic = dict(best[1].get("semantic_hardsub") or {})
            semantic.update(
                {
                    "cue_id": host_semantic.get("cue_id"),
                    "canonical_text_authority": host_semantic.get("canonical_text_authority"),
                    "classification": host_semantic.get("classification"),
                    "alignment": host_semantic.get("alignment"),
                    "action": "ATTACHED_TRANSITION_GEOMETRY",
                }
            )
        else:
            identity = {
                "recipe_version": SEMANTIC_HARDSUB_RECIPE_VERSION,
                "text_id": row.get("text_id"),
                "start_ms": start_ms,
                "end_ms": end_ms,
            }
            semantic.update(
                {
                    "cue_id": f"transition_{_sha256_json(identity)[:14]}",
                    "classification": "TRANSITION_NOISE",
                    "action": "COVER_ONLY_TRANSITION",
                    "canonical_text_authority": str(semantic.get("ocr_text_observed") or ""),
                }
            )
        row["semantic_hardsub"] = semantic


def _plan_dialogue_render_text(
    rows: list[dict[str, Any]],
    *,
    authority_rows: Sequence[_TranscriptAuthority],
) -> None:
    authority_by_id = {row.transcript_segment_id: row for row in authority_rows}
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        semantic = dict(row.get("semantic_hardsub") or {})
        if str(semantic.get("classification") or "") != "DIALOGUE_HARDSUB":
            continue
        alignment = dict(semantic.get("alignment") or {})
        transcript_id = str(alignment.get("transcript_segment_id") or "")
        cue_id = str(semantic.get("cue_id") or "")
        if transcript_id and cue_id:
            grouped.setdefault(transcript_id, {}).setdefault(cue_id, []).append(row)

    for transcript_id, cue_map in grouped.items():
        authority = authority_by_id.get(transcript_id)
        if authority is None:
            continue
        approved_translation = (
            authority.translation_text
            if str(authority.translation_status or "").upper() == "APPROVED"
            else None
        )
        ordered_cues = sorted(
            cue_map.items(),
            key=lambda item: min(
                int(dict(row.get("semantic_hardsub") or {}).get("start_ms") or 0)
                for row in item[1]
            ),
        )
        planned = _allocate_vietnamese_cues(
            approved_translation or "",
            [
                max(
                    1,
                    max(
                        int(dict(row.get("semantic_hardsub") or {}).get("alignment", {}).get("asr_token_count") or 0)
                        for row in cue_rows
                    ),
                )
                for _cue_id, cue_rows in ordered_cues
            ],
        )
        if approved_translation and not planned and ordered_cues:
            cue_weights = [
                max(
                    1,
                    max(
                        int(
                            dict(row.get("semantic_hardsub") or {})
                            .get("alignment", {})
                            .get("asr_token_count")
                            or 0
                        )
                        for row in cue_rows
                    ),
                )
                for _cue_id, cue_rows in ordered_cues
            ]
            display_index = max(
                range(len(ordered_cues)),
                key=lambda index: cue_weights[index],
            )
            planned = ["" for _item in ordered_cues]
            planned[display_index] = approved_translation
        for cue_index, (cue_id, cue_rows) in enumerate(ordered_cues):
            vi_text = planned[cue_index] if cue_index < len(planned) else ""
            for row in cue_rows:
                semantic = dict(row.get("semantic_hardsub") or {})
                semantic["translation_authority"] = {
                    "transcript_segment_id": transcript_id,
                    "translation_segment_id": authority.translation_segment_id,
                    "translation_status": authority.translation_status,
                    "translation_sha256": authority.translation_sha256,
                    "planner_version": "weighted-monotonic-v1",
                    "cue_index": cue_index,
                    "cue_count": len(ordered_cues),
                }
                semantic["vi_text_authority"] = vi_text or None
                if approved_translation and not vi_text:
                    semantic["action"] = "COVER_ONLY_DIALOGUE_EPOCH"
                semantic["translation_ready"] = bool(
                    vi_text
                    or (
                        approved_translation
                        and semantic.get("action")
                        == "COVER_ONLY_DIALOGUE_EPOCH"
                    )
                )
                row["semantic_hardsub"] = semantic


def _allocate_vietnamese_cues(text: str, weights: Sequence[int]) -> list[str]:
    words = [value for value in str(text or "").split() if value]
    count = len(weights)
    if not words or count <= 0 or len(words) < count:
        return []
    total_weight = max(1, sum(max(1, int(value)) for value in weights))
    boundaries = [0]
    cumulative = 0
    for index, weight in enumerate(weights[:-1], start=1):
        cumulative += max(1, int(weight))
        ideal = int(round(cumulative / total_weight * len(words)))
        minimum = boundaries[-1] + 1
        maximum = len(words) - (count - index)
        boundaries.append(max(minimum, min(maximum, ideal)))
    boundaries.append(len(words))
    return [
        " ".join(words[boundaries[index] : boundaries[index + 1]]).strip()
        for index in range(count)
    ]


def _row_span_ms(row: Mapping[str, Any], *, fps: float) -> tuple[int, int]:
    safe_fps = max(0.001, float(fps or 30.0))
    try:
        start_frame = int(row.get("start_frame") or row.get("best_frame_index") or 0)
        end_frame = int(row.get("end_frame") or start_frame)
    except (TypeError, ValueError):
        start_frame = end_frame = 0
    start_ms = int(round(min(start_frame, end_frame) * 1000.0 / safe_fps))
    end_ms = int(round((max(start_frame, end_frame) + 1) * 1000.0 / safe_fps))
    return start_ms, max(start_ms + 1, end_ms)


def _candidate_text(row: Mapping[str, Any]) -> str:
    return str(
        row.get("ocr_text_raw")
        or row.get("ocr_text")
        or row.get("text")
        or ""
    ).strip()


def _signature(text: str) -> str:
    return "".join(_CJK_OR_DIGIT_RE.findall(str(text or ""))).casefold()


def _looks_like_transition_noise(text: str, *, duration_ms: int) -> bool:
    compact = _SPACE_RE.sub("", str(text or ""))
    cjk = len(_CJK_RE.findall(compact))
    ascii_alnum = len(_ASCII_ALNUM_RE.findall(compact))
    mixed_glyph_junk = cjk <= 1 and ascii_alnum >= 2
    micro_fragment = duration_ms <= 520 and cjk <= 1 and len(compact) <= 5
    repeated_ascii = bool(re.search(r"([A-Za-z])\1{1,}", compact, re.IGNORECASE))
    return bool(mixed_glyph_junk or micro_fragment or (repeated_ascii and cjk <= 2))


def _looks_like_platform_ui(text: str, *, role: str) -> bool:
    compact = _SPACE_RE.sub("", str(text or ""))
    return bool(
        compact
        and _PLATFORM_UI_RE.search(compact)
        and (str(role or "").lower() == "ui_chip" or "·" in compact)
    )


def _geometry_iou(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    frame_width: int,
    frame_height: int,
) -> float:
    left_box = _xyxy(left, frame_width=frame_width, frame_height=frame_height)
    right_box = _xyxy(right, frame_width=frame_width, frame_height=frame_height)
    if left_box is None or right_box is None:
        return 0.0
    x0 = max(left_box[0], right_box[0])
    y0 = max(left_box[1], right_box[1])
    x1 = min(left_box[2], right_box[2])
    y1 = min(left_box[3], right_box[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    left_area = max(0.0, left_box[2] - left_box[0]) * max(0.0, left_box[3] - left_box[1])
    right_area = max(0.0, right_box[2] - right_box[0]) * max(0.0, right_box[3] - right_box[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def _xyxy(
    row: Mapping[str, Any],
    *,
    frame_width: int,
    frame_height: int,
) -> tuple[float, float, float, float] | None:
    coords = list(row.get("box_coords") or [])
    if len(coords) < 4:
        return None
    try:
        values = [float(value) for value in coords]
    except (TypeError, ValueError):
        return None
    if len(values) >= 8:
        xs, ys = values[0::2], values[1::2]
        return min(xs), min(ys), max(xs), max(ys)
    x0, y0, x1, y1 = values[:4]
    if max(abs(x0), abs(y0), abs(x1), abs(y1)) <= 1.5:
        x0, x1 = x0 * frame_width, x1 * frame_width
        y0, y1 = y0 * frame_height, y1 * frame_height
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _row_authority_quality(row: Mapping[str, Any]) -> float:
    semantic = dict(row.get("semantic_hardsub") or {})
    alignment = dict(semantic.get("alignment") or {})
    text = str(semantic.get("text_authority") or "")
    duration = max(0, int(semantic.get("end_ms") or 0) - int(semantic.get("start_ms") or 0))
    return (
        float(alignment.get("score") or 0.0) * 5.0
        + min(2.0, len(_signature(text)) / 8.0)
        + min(1.0, duration / 2_000.0)
    )


def _join_tokens(values: Iterable[str]) -> str:
    output = ""
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        if output and output[-1:].isascii() and output[-1:].isalnum() and value[:1].isascii() and value[:1].isalnum():
            output += " "
        output += value
    return output


def _protected_row(row: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "text_id": str(row.get("text_id") or ""),
        "start_frame": row.get("start_frame"),
        "end_frame": row.get("end_frame"),
        "box_coords": list(row.get("box_coords") or []),
        "visual_provenance": dict(row.get("visual_provenance") or {}),
        "semantic_hardsub": dict(row.get("semantic_hardsub") or {}),
        "action": "PRESERVE_SOURCE_PIXELS",
        "source": reason,
        "coverage_authority": dict(row.get("coverage_authority") or {}),
    }


def _sha256_json(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
