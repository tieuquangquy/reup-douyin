"""Deterministic local policy for unattended quality-localization checkpoints.

The policy never invents OCR text or translations.  It only promotes artifacts that
the locked local pipeline has already classified/generated, and fails closed when the
editor-overlay/source-intrinsic distinction is ambiguous.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

from src.services.residual_translation import (
    RESIDUAL_TRANSLATION_CACHE_VERSION,
    RESIDUAL_TRANSLATION_PROMPT_VERSION,
    load_translation_cache,
    partition_translation_batches,
    translation_cache_key,
    write_translation_cache,
)


AUTO_QUALITY_POLICY_VERSION = "quality_auto_to_render_v1"
AUTO_QUALITY_ACTOR = "local_auto_quality_policy"

_EDITOR_CLASSES = frozenset({"EDITOR_OVERLAY"})
_PROTECTED_CLASSES = frozenset(
    {"SOURCE_INTRINSIC", "SOURCE_INTRINSIC_PANEL", "PLATFORM_UI"}
)
_BLOCKING_TRANSLATION_FLAGS = frozenset(
    {
        "MISSING_TRANSLATION",
        "EMPTY_TRANSLATION",
        "OPERATOR_INPUT_REQUIRED",
        "TRANSLATION_REVIEW_REQUIRED",
    }
)
_BLOCKING_TIMING_KEYS = frozenset(
    {"too_long", "too_short", "failed", "rewrite_required", "unresolved"}
)


class QualityAutoPolicyBlocked(ValueError):
    """Raised when deterministic evidence is insufficient for unattended approval."""


def build_ocr_decisions(
    review_objects: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for raw in review_objects:
        row = dict(raw)
        content_id = str(row.get("content_id") or "").strip()
        text = str(row.get("ocr_text_candidate") or "").strip()
        classes = {
            str(value or "").strip().upper()
            for value in list(row.get("provenance_classifications") or [])
            if str(value or "").strip()
        }
        if not classes:
            visual = dict(row.get("visual_provenance") or {})
            fallback = str(visual.get("classification") or "").strip().upper()
            if fallback:
                classes.add(fallback)
        if not content_id:
            raise QualityAutoPolicyBlocked("OCR review object is missing content_id")
        if classes and classes <= _PROTECTED_CLASSES:
            decision = "PRESERVE_SOURCE"
        elif classes and classes <= _EDITOR_CLASSES:
            if not text:
                raise QualityAutoPolicyBlocked(
                    f"Editor overlay {content_id} has no OCR text candidate"
                )
            decision = "APPROVE"
        else:
            rendered = ",".join(sorted(classes)) or "UNCLASSIFIED"
            raise QualityAutoPolicyBlocked(
                f"OCR provenance is ambiguous for {content_id}: {rendered}"
            )
        decisions.append(
            {
                "content_id": content_id,
                "decision": decision,
                "ocr_text_approved": text,
            }
        )
    if not decisions:
        raise QualityAutoPolicyBlocked("OCR review queue is empty")
    return decisions


def build_translation_decisions(
    translation_objects: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    decisions: list[dict[str, str]] = []
    for raw in translation_objects:
        row = dict(raw)
        content_id = str(row.get("content_id") or "").strip()
        vi_text = str(row.get("vi_text_candidate") or "").strip()
        flags = {
            str(value or "").strip().upper()
            for value in list(row.get("quality_flags") or [])
            if str(value or "").strip()
        }
        blockers = flags & _BLOCKING_TRANSLATION_FLAGS
        if not content_id or not vi_text or blockers:
            reason = ",".join(sorted(blockers)) or "missing Vietnamese candidate"
            raise QualityAutoPolicyBlocked(
                f"Translation cannot be auto-approved for {content_id or 'unknown'}: {reason}"
            )
        decisions.append({"content_id": content_id, "vi_text": vi_text})
    if not decisions:
        raise QualityAutoPolicyBlocked("Translation review queue is empty")
    return decisions


def assert_audio_ready(summary: Mapping[str, Any]) -> None:
    stage = str(summary.get("workflow_stage") or "")
    # A resumed auto lane may already have a hash-bound AUDIO_APPROVED
    # narration/background handoff.  OCR/visual artifact regeneration must
    # not downgrade that durable audio authority to a missing preview file.
    # The renderer still verifies the narration/background hashes at its own
    # boundary; this branch only avoids re-opening an approved audio gate.
    approved_audio = {
        str(summary.get("audio_review_status") or ""),
        str(summary.get("audio_mix_review_status") or ""),
    }
    if stage == "AUDIO_APPROVED" and approved_audio & {
        "AUDIO_APPROVED",
        "AUDIO_MIX_APPROVED",
    }:
        return
    if stage != "WAITING_AUDIO_REVIEW":
        raise QualityAutoPolicyBlocked("Audio review preview was not staged")
    if not str(summary.get("audio_mix_preview_path") or "").strip():
        raise QualityAutoPolicyBlocked("Audio mix preview is missing")
    timing = dict(summary.get("timing_fit_summary") or {})
    blocking = {
        key: int(timing.get(key) or 0)
        for key in _BLOCKING_TIMING_KEYS
        if int(timing.get(key) or 0) > 0
    }
    if blocking:
        raise QualityAutoPolicyBlocked(
            "TTS timing still has unresolved segments: "
            + ", ".join(f"{key}={value}" for key, value in sorted(blocking.items()))
        )


def translate_residual_texts(
    *,
    db: Any,
    workspace_id: Any,
    residual_objects: Sequence[Mapping[str, Any]],
    fallback_suggestions: Sequence[Mapping[str, Any]] | None = None,
    authority_suggestions: Sequence[Mapping[str, Any]] | None = None,
    cache_path: str | Path | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    batch_size: int = 12,
    batch_max_utf8_bytes: int = 6_000,
) -> list[dict[str, str]]:
    """Translate normalized residual content with bounded, resumable batches.

    Detection, geometry and decisions remain local/deterministic. Translation is the
    one explicitly permitted AI boundary and uses the same workspace Caption AI
    configuration as Phase 3.  Successful objects are committed to a per-text cache
    immediately; a later provider failure never discards earlier batches.
    """

    content_id_by_text: dict[str, str] = {}
    for index, raw in enumerate(residual_objects):
        row = dict(raw)
        text = str(row.get("text") or "").strip()
        if text and text not in content_id_by_text:
            content_id_by_text[text] = str(
                row.get("content_id") or f"residual_{index + 1:03d}"
            )
    if not content_id_by_text:
        raise QualityAutoPolicyBlocked("Residual CJK evidence contains no translatable text")
    from src.media_pipeline.translator.client import build_openai_client
    from src.media_pipeline.translator.resolve import resolve_translator_settings

    settings = resolve_translator_settings(db=db, workspace_id=workspace_id)
    model_name = str(settings.model_name or "")
    base_url = str(settings.base_url or "")
    system_prompt = str(getattr(settings, "system_prompt", "") or "")
    fossil_rows = [
        dict(row)
        for row in [*(fallback_suggestions or []), *(authority_suggestions or [])]
        if isinstance(row, Mapping)
    ]
    reusable_by_text = {
        str(row.get("ocr_text") or "").strip(): row
        for row in fossil_rows
        if str(row.get("ocr_text") or "").strip()
        and str(row.get("ocr_text_corrected") or "").strip()
        and str(row.get("vi_text_suggested") or "").strip()
    }
    cache = load_translation_cache(cache_path)
    cache_entries = dict(cache.get("entries") or {})
    resolved: dict[str, dict[str, str]] = {}

    def suggestion(
        text: str,
        corrected: str,
        vi_text: str,
        *,
        source: str,
    ) -> dict[str, str]:
        # Keep text-keyed translation/cache reuse while carrying the stable
        # temporal content id into review and proposal materialization. This
        # prevents repeated captions with the same OCR string from borrowing
        # another occurrence's operator edit.
        return {
            "content_id": content_id_by_text[text],
            "ocr_text": text,
            "ocr_text_corrected": corrected,
            "vi_text_suggested": vi_text,
        }

    pending: list[tuple[str, str]] = []
    for sequence, text in enumerate(content_id_by_text, start=1):
        fossil = reusable_by_text.get(text)
        if fossil is not None:
            resolved[text] = suggestion(
                text,
                str(fossil.get("ocr_text_corrected") or text).strip(),
                str(fossil.get("vi_text_suggested") or "").strip(),
                source=str(fossil.get("suggestion_source") or "translation_fossil"),
            )
            continue
        key = translation_cache_key(
            text=text,
            model_name=model_name,
            base_url=base_url,
            system_prompt=system_prompt,
        )
        hit = dict(cache_entries.get(key) or {})
        corrected = str(hit.get("ocr_text_corrected") or "").strip()
        vi_text = str(hit.get("vi_text_suggested") or "").strip()
        if corrected and vi_text:
            resolved[text] = suggestion(
                text, corrected, vi_text, source="content_cache"
            )
            continue
        pending.append((content_id_by_text[text] or f"residual_{sequence:03d}", text))

    total = len(content_id_by_text)
    if on_progress is not None:
        on_progress(len(resolved), total)
    if not pending:
        return [resolved[text] for text in content_id_by_text]

    try:
        client = build_openai_client(settings)
    except Exception as exc:  # noqa: BLE001 - configuration/provider boundary
        raise QualityAutoPolicyBlocked(
            f"Residual OCR/translation provider unavailable: {type(exc).__name__}"
        ) from exc

    system_message = (
        "You repair OCR for Chinese editor-added short-video captions and translate them to concise, "
        "natural Vietnamese. For every input id return an object with zh_corrected and vi_text. "
        "Correct only obvious OCR glyph errors using the phrase context; otherwise preserve the Chinese. "
        "Never merge ids, omit ids, invent text, or return markdown."
    )
    failures = 0
    max_provider_failures = 3

    def persist_result(text: str, corrected: str, vi_text: str) -> None:
        nonlocal cache_entries
        resolved[text] = suggestion(text, corrected, vi_text, source="provider")
        key = translation_cache_key(
            text=text,
            model_name=model_name,
            base_url=base_url,
            system_prompt=system_prompt,
        )
        cache_entries[key] = {
            "ocr_text": text,
            "ocr_text_corrected": corrected,
            "vi_text_suggested": vi_text,
            "model_name": model_name,
            "base_url": base_url.rstrip("/"),
            "prompt_version": RESIDUAL_TRANSLATION_PROMPT_VERSION,
        }
        cache["schema_version"] = RESIDUAL_TRANSLATION_CACHE_VERSION
        cache["entries"] = cache_entries
        write_translation_cache(cache_path, cache)
        if on_progress is not None:
            on_progress(len(resolved), total)

    def translate_batch(batch: list[tuple[str, str]]) -> None:
        nonlocal failures
        if not batch:
            return
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                key: {
                                    "ocr_text": value,
                                    "context": "Chinese editor-added short-video overlay",
                                }
                                for key, value in batch
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            payload = json.loads(str(response.choices[0].message.content or ""))
            if not isinstance(payload, Mapping):
                raise ValueError("response must be a JSON object")
            staged: list[tuple[str, str, str]] = []
            for item_id, zh_text in batch:
                row = payload.get(item_id)
                if not isinstance(row, Mapping):
                    raise ValueError(f"missing id {item_id}")
                corrected = str(row.get("zh_corrected") or zh_text).strip()
                vi_text = str(row.get("vi_text") or "").strip()
                if not corrected or not vi_text or vi_text == "...":
                    raise ValueError(f"empty translation for {item_id}")
                staged.append((zh_text, corrected, vi_text))
            for zh_text, corrected, vi_text in staged:
                persist_result(zh_text, corrected, vi_text)
            failures = 0
            return
        except Exception as exc:  # noqa: BLE001 - split/circuit-break provider boundary
            failures += 1
            # A provider can return HTTP 500 for an oversized JSON request.
            # Bisect a bounded batch, but stop quickly when even small batches
            # fail so a provider outage cannot fan out into hundreds of calls.
            if len(batch) > 3 and failures < max_provider_failures:
                midpoint = len(batch) // 2
                translate_batch(batch[:midpoint])
                translate_batch(batch[midpoint:])
                return
            unresolved = [text for _item_id, text in batch if text not in resolved]
            raise QualityAutoPolicyBlocked(
                "Residual OCR/translation provider unavailable: "
                f"{type(exc).__name__}; completed={len(resolved)}/{total}; "
                f"unresolved_batch={len(unresolved)}"
            ) from exc

    for batch in partition_translation_batches(
        pending,
        max_items=batch_size,
        max_utf8_bytes=batch_max_utf8_bytes,
    ):
        translate_batch(batch)
    missing = [text for text in content_id_by_text if text not in resolved]
    if missing:
        raise QualityAutoPolicyBlocked(
            f"Residual translation remains incomplete: {len(missing)}/{total}"
        )
    return [resolved[text] for text in content_id_by_text]
