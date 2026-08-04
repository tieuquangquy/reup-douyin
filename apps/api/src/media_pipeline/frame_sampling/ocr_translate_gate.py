"""Pre-Phase-3 gate: clean OCR timeline before Caption AI translate.

Authority stays ``master_timeline.json``. This module only curates ``ocr_text`` /
``translate_ready`` so Phase 3 does not burn tokens or VI on UI/noise.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from src.media_pipeline.frame_sampling.master_phase1_extractor import (
    _cjk_count,
    classify_ocr_box_role,
)

logger = logging.getLogger(__name__)

# Cheap deterministic OCR typo fixes (cooking / Douyin hardsub).
_OCR_TYPO_REPAIRS: tuple[tuple[str, str], ...] = (
    ("分钢", "分钟"),
    ("虾位", "虾仁"),
    ("定上联", "水开上锅蒸"),
)

_KCAL_TAIL_RE = re.compile(
    r"^(?P<cap>.+?)(?P<ui>\d{2,4}\s*千卡)$"
)
_PURE_KCAL_RE = re.compile(r"^\d{1,4}\s*千卡$")
_PURE_GRAMS_RE = re.compile(r"^\d{1,4}\s*克$")
_WEAK_SINGLE_CJK = frozenset("产花的个了在是有和不")


def repair_ocr_typos(text: str) -> str:
    out = str(text or "").strip()
    for bad, good in _OCR_TYPO_REPAIRS:
        if bad in out:
            out = out.replace(bad, good)
    return out


def split_caption_and_ui(text: str) -> tuple[str, str | None]:
    """
    Split glued caption+calorie strings.

    ``虾仁豆腐蒸蛋634千卡`` → (``虾仁豆腐蒸蛋``, ``634千卡``).
    """
    raw = str(text or "").strip()
    if not raw:
        return "", None
    m = _KCAL_TAIL_RE.match(raw)
    if not m:
        return raw, None
    cap = str(m.group("cap") or "").strip()
    ui = str(m.group("ui") or "").strip()
    if _cjk_count(cap) < 2:
        return raw, None
    return cap, ui


def _is_ui_numeric(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    if _PURE_KCAL_RE.match(raw) or _PURE_GRAMS_RE.match(raw):
        return True
    # Mostly digits / units, little CJK prose.
    cjk = _cjk_count(raw)
    digits = sum(1 for ch in raw if ch.isdigit())
    if digits >= 2 and cjk <= 2 and len(raw) <= 8:
        return True
    return False


def _is_noise_token(text: str, *, role: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return True
    if len(raw) == 1 and raw in _WEAK_SINGLE_CJK:
        return True
    if len(raw) == 1 and raw.isdigit():
        return True
    if len(raw) == 1 and ("A" <= raw <= "Z" or "a" <= raw <= "z"):
        return True
    if role == "mid_label" and len(raw) == 1 and _cjk_count(raw) == 1:
        # Single mid glyph is usually a fragment unless common action words.
        if raw not in {"盐", "油", "水", "糖", "醋"}:
            return True
    return False


def evaluate_translate_gate(
    entry: Mapping[str, Any],
    *,
    frame_w: int = 1920,
    frame_h: int = 1080,
) -> tuple[bool, str, str]:
    """
    Return ``(translate_ready, reason, cleaned_ocr_text)``.

    Geometry is never modified. Empty cleaned text → not ready (cover_only).
    """
    coords = list(entry.get("box_coords") or [])
    role = "generic"
    if len(coords) >= 4:
        role = classify_ocr_box_role(coords, frame_w=frame_w, frame_h=frame_h)

    raw = repair_ocr_typos(str(entry.get("ocr_text") or entry.get("text") or ""))
    if not raw:
        return False, "empty", ""

    cap, ui = split_caption_and_ui(raw)
    if ui:
        raw = cap
        reason_split = "split_ui"
    else:
        reason_split = ""

    if _is_ui_numeric(raw) or role in {"ui_chip"} and _is_ui_numeric(raw):
        return False, "ui_numeric", raw

    if role == "ui_chip" and _cjk_count(raw) < 2 and not (
        len(raw) >= 2 and _cjk_count(raw) >= 1
    ):
        # Short UI chips (grams/kcal) — cover only.
        if _is_ui_numeric(raw) or _cjk_count(raw) == 0:
            return False, "ui_chip", raw

    if _is_noise_token(raw, role=role):
        return False, "noise", raw

    if _cjk_count(raw) < 1:
        return False, "no_cjk", raw

    # Hardsub / mid labels with meaningful CJK prose.
    if role == "hardsub" and _cjk_count(raw) < 2 and len(raw) < 3:
        return False, "hardsub_too_short", raw

    if reason_split:
        return True, reason_split, raw
    if entry.get("ocr_suspect") and ui is None and _is_ui_numeric(
        str(entry.get("ocr_text") or "")
    ):
        return False, "suspect_ui", raw
    return True, "ok", raw


def _texts_similar(a: str, b: str) -> bool:
    x = str(a or "").strip()
    y = str(b or "").strip()
    if not x or not y:
        return False
    if x == y:
        return True
    if x in y or y in x:
        return True
    return False


def _time_overlap(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    a0 = int(a.get("start_frame") or 0)
    a1 = int(a.get("end_frame") or a0)
    b0 = int(b.get("start_frame") or 0)
    b1 = int(b.get("end_frame") or b0)
    # Identical content split by one inclusive frame transition should be
    # translated once while both Phase-1 geometry occurrences stay coverable.
    return not (a1 + 1 < b0 or b1 + 1 < a0)


def dedupe_overlapping_translate_tracks(
    tracks: Sequence[MutableMapping[str, Any]],
) -> list[MutableMapping[str, Any]]:
    """
    Keep one translate_primary among overlapping similar texts.

    Secondary stays geometry-coverable but ``translate_ready=False``.
    """
    out: list[MutableMapping[str, Any]] = [dict(t) for t in tracks]
    for i, a in enumerate(out):
        if not a.get("translate_ready"):
            continue
        for j in range(i + 1, len(out)):
            b = out[j]
            if not b.get("translate_ready"):
                continue
            if not _time_overlap(a, b):
                continue
            if not _texts_similar(str(a.get("ocr_text") or ""), str(b.get("ocr_text") or "")):
                continue
            # Prefer longer lifespan as primary.
            a_span = int(a.get("end_frame") or 0) - int(a.get("start_frame") or 0)
            b_span = int(b.get("end_frame") or 0) - int(b.get("start_frame") or 0)
            if b_span > a_span:
                a["translate_ready"] = False
                a["translate_reject_reason"] = "dedupe_secondary"
                a["translate_primary_id"] = b.get("text_id")
            else:
                b["translate_ready"] = False
                b["translate_reject_reason"] = "dedupe_secondary"
                b["translate_primary_id"] = a.get("text_id")
    return out


def finalize_ocr_for_translate(
    timeline: Sequence[MutableMapping[str, Any]],
    *,
    qa_dir: str | Path,
    frame_w: int = 1920,
    frame_h: int = 1080,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Curate timeline for Phase 3.

    - repair typos
    - split caption/UI
    - set ``translate_ready`` / reject reason
    - dedupe overlapping similars
    - write ``qa/translate_queue.json``
    """
    qa_path = Path(qa_dir)
    qa_path.mkdir(parents=True, exist_ok=True)

    curated: list[dict[str, Any]] = []
    for raw in timeline:
        entry = dict(raw)
        original = str(entry.get("ocr_text") or entry.get("text") or "").strip()
        entry["ocr_text_raw"] = original
        ready, reason, cleaned = evaluate_translate_gate(
            entry, frame_w=frame_w, frame_h=frame_h
        )
        ocr_review_required = (
            not original
            and str(entry.get("ocr_source") or "") in {"failed", "none"}
        )
        entry["ocr_review_required"] = bool(ocr_review_required)
        if ocr_review_required:
            reason = "ocr_failed"
        # Re-run split on original for ui side-car.
        _cap, ui = split_caption_and_ui(repair_ocr_typos(original))
        if ui:
            entry["ocr_text_ui"] = ui
        entry["ocr_text"] = cleaned if ready else ""
        entry["translate_ready"] = bool(ready)
        entry["translate_reject_reason"] = "" if ready else str(reason)
        if ready and reason == "split_ui":
            entry["translate_reject_reason"] = ""
            entry["translate_note"] = "split_ui"
        curated.append(entry)

    curated = [dict(t) for t in dedupe_overlapping_translate_tracks(curated)]

    queue = []
    ready_n = 0
    for entry in curated:
        item = {
            "text_id": entry.get("text_id"),
            "ocr_text": entry.get("ocr_text"),
            "ocr_text_raw": entry.get("ocr_text_raw"),
            "ocr_text_ui": entry.get("ocr_text_ui"),
            "translate_ready": bool(entry.get("translate_ready")),
            "reason": entry.get("translate_note")
            or entry.get("translate_reject_reason")
            or ("ok" if entry.get("translate_ready") else "rejected"),
            "start_frame": entry.get("start_frame"),
            "end_frame": entry.get("end_frame"),
            "ocr_source": entry.get("ocr_source"),
            "ocr_review_required": bool(entry.get("ocr_review_required")),
        }
        if entry.get("translate_ready"):
            ready_n += 1
        queue.append(item)

    review_required_n = sum(
        1 for entry in curated if entry.get("ocr_review_required")
    )
    audit = {
        "tracks": len(curated),
        "ready": ready_n,
        "rejected": len(curated) - ready_n,
        "review_required": review_required_n,
        "queue_path": str((qa_path / "translate_queue.json").as_posix()),
    }
    (qa_path / "translate_queue.json").write_text(
        json.dumps({"audit": audit, "tracks": queue}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "ocr_translate_gate ready=%s rejected=%s review_required=%s out=%s",
        ready_n,
        len(curated) - ready_n,
        review_required_n,
        audit["queue_path"],
    )
    return curated, audit
