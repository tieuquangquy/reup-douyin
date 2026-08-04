"""Normalize Phase 2 OCR payloads into {timestamp_str: chinese_text}.

Each OCR box with Chinese (CJK) becomes its own key ``{time_ms}#{box_index}``
so Caption AI and render can cover+burn VI **per label**. Latin/VI-only boxes
(e.g. existing Vietnamese hard-subs, dates) are skipped.

Phase 2.5:
  - ``canonical_zh`` before dedupe (spaces / fullwidth)
  - ``segment_authority_zh`` prefers ``master_timeline`` ``text_id`` SSOT
  - ``merge_near_duplicate_zh`` collapses OCR near-duplicates
  - ``flatten_ocr_chinese`` builds the full tracking map (key → canonical ZH)
  - ``unique_chinese_texts`` extracts the ZH set sent toward the LLM once
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping, Sequence

from src.media_pipeline.ocr_filtering.script_filter import contains_cjk
from src.media_pipeline.translator.errors import TranslatorError, TranslatorErrorCode

_WS_RE = re.compile(r"\s+")


def canonical_zh(text: str) -> str:
    """
    Normalize ZH for dedupe / cache keys.

    NFKC + strip + drop internal whitespace so ``加 盐`` == ``加盐``.
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    folded = unicodedata.normalize("NFKC", raw)
    return _WS_RE.sub("", folded)


def _box_text(box: Any) -> str:
    if isinstance(box, Mapping):
        return canonical_zh(_box_text_raw(box))
    return canonical_zh(str(box or ""))


def _box_text_raw(box: Mapping[str, Any]) -> str:
    return str(box.get("text") or "").strip()


def unique_chinese_texts(tracking_map: Mapping[str, str]) -> list[str]:
    """Ordered unique ZH strings from a key→ZH tracking map (first-seen order)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in tracking_map.values():
        zh = canonical_zh(str(raw or ""))
        if not zh or zh in seen:
            continue
        seen.add(zh)
        out.append(zh)
    return out


def segment_authority_zh(ocr_data: Mapping[Any, Any] | list[Any]) -> dict[str, str]:
    """
    Track-level ZH authority: ``text_id → canonical ZH``.

    Prefers ``master_timeline`` when present; else first-seen ``text_id`` on frames.
    Only ``translate_ready`` tracks with CJK text are included.
    """
    if isinstance(ocr_data, list):
        return {}

    out: dict[str, str] = {}
    timeline = ocr_data.get("master_timeline")
    if isinstance(timeline, list) and timeline:
        for raw in timeline:
            if not isinstance(raw, Mapping):
                continue
            if raw.get("translate_ready") is False:
                continue
            tid = str(raw.get("text_id") or "").strip()
            if not tid:
                continue
            text = canonical_zh(str(raw.get("ocr_text") or raw.get("text") or ""))
            if not text or not contains_cjk(text):
                continue
            out.setdefault(tid, text)
        return out

    frames = ocr_data.get("frames")
    if not isinstance(frames, list):
        return out
    for frame in frames:
        if not isinstance(frame, Mapping):
            continue
        for box in list(frame.get("boxes") or []):
            if not isinstance(box, Mapping):
                continue
            if bool(box.get("cover_only")):
                continue
            if box.get("translate_ready") is False:
                continue
            tid = str(box.get("text_id") or "").strip()
            if not tid:
                continue
            text = _box_text(box)
            if not text or not contains_cjk(text):
                continue
            out.setdefault(tid, text)
    return out


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def _should_merge_near_dupe(a: str, b: str) -> bool:
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) < 3:
        return False
    if shorter in longer and (len(longer) - len(shorter)) <= 2:
        return True
    if abs(len(a) - len(b)) <= 1 and min(len(a), len(b)) >= 3:
        return _edit_distance(a, b) <= 1
    return False


def merge_near_duplicate_zh(texts: Sequence[str]) -> dict[str, str]:
    """
    Map each ZH → representative (prefer longer string).

    Collapses OCR near-duplicates (missing/extra char, containment).
    """
    cleaned = [canonical_zh(t) for t in texts if canonical_zh(t)]
    # Stable unique preserve order.
    ordered: list[str] = []
    seen: set[str] = set()
    for zh in cleaned:
        if zh in seen:
            continue
        seen.add(zh)
        ordered.append(zh)

    parent: dict[str, str] = {zh: zh for zh in ordered}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        # Prefer longer representative; tie → first-seen (stable via ordered index).
        if len(rb) > len(ra) or (
            len(rb) == len(ra) and ordered.index(rb) < ordered.index(ra)
        ):
            parent[ra] = rb
        else:
            parent[rb] = ra

    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if _should_merge_near_dupe(a, b):
                union(a, b)

    return {zh: find(zh) for zh in ordered}


def flatten_ocr_chinese(ocr_data: Mapping[Any, Any] | list[Any]) -> dict[str, str]:
    """
    Build tracking map ``{time_ms#box_index → canonical ZH}`` (and time_ms aliases).

    Does **not** dedupe values — callers that talk to the LLM should use
    ``unique_chinese_texts(tracking_map)`` then broadcast VI back onto keys.
    """
    if isinstance(ocr_data, list):
        frames = ocr_data
        flat: dict[str, str] = {}
        for frame in frames:
            if not isinstance(frame, Mapping):
                continue
            time_ms = int(frame.get("time_ms", 0) or 0)
            raw_boxes = [b for b in list(frame.get("boxes") or []) if isinstance(b, Mapping)]
            if not raw_boxes:
                continue
            box_index = 0
            for box in raw_boxes:
                if bool(box.get("cover_only")):
                    continue
                if box.get("translate_ready") is False:
                    continue
                text = _box_text(box)
                if not text or not contains_cjk(text):
                    continue
                key = f"{time_ms}#{box_index}"
                flat[key] = text
                # Convenience alias for first CJK box on this timestamp.
                if box_index == 0 and str(time_ms) not in flat:
                    flat[str(time_ms)] = text
                box_index += 1
        if not flat:
            raise TranslatorError(
                TranslatorErrorCode.EMPTY_INPUT,
                "OCR frame list has no Chinese text to translate",
            )
        return flat

    if "frames" in ocr_data and isinstance(ocr_data.get("frames"), list):
        return flatten_ocr_chinese(list(ocr_data["frames"]))

    flat = {}
    for key, value in ocr_data.items():
        if key in {"provider", "frame_count", "warnings", "frames", "master_timeline", "authority", "fps", "frame_width", "frame_height"}:
            continue
        if isinstance(value, Mapping) and "boxes" in value:
            texts = [
                _box_text(b)
                for b in list(value.get("boxes") or [])
                if contains_cjk(_box_text(b))
            ]
            texts = [t for t in texts if t]
            text = "".join(texts) if texts else ""
            # Prefer space-joined only when multiple boxes; canonical already dropped spaces inside.
            if len(texts) > 1:
                text = " ".join(texts)
                text = canonical_zh(text)
            time_key = value.get("time_ms", key)
        else:
            text = canonical_zh(str(value or ""))
            time_key = key
            if text and not contains_cjk(text):
                continue
        if not text:
            continue
        flat[str(time_key)] = text

    if not flat:
        raise TranslatorError(
            TranslatorErrorCode.EMPTY_INPUT,
            "No Chinese text to translate",
        )
    return flat


def broadcast_zh_translations(
    tracking_map: Mapping[str, str],
    translated_dict: Mapping[str, str],
    *,
    missing: str = "...",
) -> dict[str, str]:
    """Map each tracking key → VI via ZH dictionary; empty/missing → ``missing``."""
    out: dict[str, str] = {}
    for key, zh in tracking_map.items():
        text = canonical_zh(str(zh or ""))
        vi = str(translated_dict.get(text) or "").strip()
        out[str(key)] = vi if vi else missing
    return out


def remap_tracking_to_representatives(
    tracking_map: Mapping[str, str],
    alias_to_rep: Mapping[str, str],
) -> dict[str, str]:
    """Rewrite tracking values through near-dupe representatives."""
    out: dict[str, str] = {}
    for key, zh in tracking_map.items():
        canon = canonical_zh(str(zh or ""))
        out[str(key)] = str(alias_to_rep.get(canon, canon))
    return out
