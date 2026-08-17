"""Phase 3 visual-text localization over a READY_FOR_PHASE3 OCR handoff."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.media_pipeline.ocr_filtering.script_filter import contains_cjk
from src.media_pipeline.translator.client import build_openai_client
from src.media_pipeline.translator.config import TranslatorSettings
from src.media_pipeline.translator.memory import TranslationMemory
from src.audio_pipeline.google_cloud_genai import is_google_cloud_retryable_error

PHASE3_SCHEMA_VERSION = "phase3_translation_timeline_v1"
PHASE3_APPROVAL_SCHEMA_VERSION = "phase3_translation_approvals_v1"
PHASE3_RENDER_HANDOFF_SCHEMA_VERSION = "phase3_render_handoff_v1"
PHASE3_REVIEW_INPUT_SCHEMA_VERSION = "phase3_review_input_v1"

_PLACEHOLDER_RE = re.compile(r"\{\{(?:VALUE|UNIT)_\d+\}\}")
_NUMBER_RE = re.compile(r"(?<![\w.])[+-]?\d+(?:[.,]\d+)?(?!\d)")
_WS_RE = re.compile(r"\s+")
_CONTEXTUAL_CLASSIFIER_UNITS = {"个"}
_UNIT_RENDER_OVERRIDES = {"勺": "muỗng"}

PHASE3_MANDATORY_PROMPT = """
Bạn đang localize chữ trên video ngắn Trung Quốc sang tiếng Việt.
- Dịch tự nhiên, ngắn gọn, trung thành; không thêm giải thích hoặc quảng cáo.
- Label/UI nên 1–6 từ; hardsub nên tối đa khoảng 12 từ nếu không mất nghĩa.
- Giữ NGUYÊN tuyệt đối mọi placeholder dạng {{VALUE_N}} và {{UNIT_N}}.
- Không đổi, xóa, thêm hoặc dịch nội dung bên trong placeholder.
- Mỗi khóa input là content_id bất biến. Trả về JSON object phẳng với đúng cùng khóa.
- Giá trị output chỉ là câu tiếng Việt, không markdown, không chú thích.
""".strip()


class Phase3TranslationError(RuntimeError):
    pass


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temp.replace(path)


def _is_retryable(exc: BaseException) -> bool:
    if is_google_cloud_retryable_error(exc):
        return True
    if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        code = getattr(exc, "status_code", None)
        return code is None or int(code) in {408, 409, 429} or int(code) >= 500
    return False


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable),
)
def _translate_batch(
    client: Any,
    *,
    model_name: str,
    system_prompt: str,
    items: Mapping[str, Mapping[str, str]],
) -> tuple[dict[str, str], Any]:
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(items, ensure_ascii=False),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    try:
        content = str(response.choices[0].message.content or "").strip()
        payload = json.loads(content)
    except (AttributeError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise Phase3TranslationError(f"Invalid Caption AI JSON response: {exc}") from exc
    translated = _normalize_translation_response(payload, expected_ids=set(items))
    return translated, payload


def _normalize_translation_response(
    payload: Any, *, expected_ids: set[str]
) -> dict[str, str]:
    """Normalize both supported workspace prompt schemas without fuzzy ID matching."""
    translated: dict[str, str] = {}
    if isinstance(payload, Mapping):
        translated = {
            str(content_id): str(value or "").strip()
            for content_id, value in payload.items()
        }
    elif isinstance(payload, list):
        for row in payload:
            if not isinstance(row, Mapping):
                raise Phase3TranslationError(
                    "Caption AI list response contains an invalid row"
                )
            content_id = str(row.get("id") or "").strip()
            if not content_id or content_id in translated:
                raise Phase3TranslationError(
                    "Caption AI response contains a missing or duplicate content_id"
                )
            translated[content_id] = str(row.get("translated_text") or "").strip()
    else:
        raise Phase3TranslationError(
            "Caption AI response must be a keyed object or an id-keyed list"
        )

    actual_ids = set(translated)
    if actual_ids != expected_ids:
        missing = len(expected_ids - actual_ids)
        unexpected = len(actual_ids - expected_ids)
        raise Phase3TranslationError(
            "Caption AI response content_id set mismatch "
            f"(missing={missing}, unexpected={unexpected})"
        )
    return {content_id: translated[content_id] for content_id in expected_ids}


def _role_of(item: Mapping[str, Any]) -> str:
    roles = [str(role) for role in list(item.get("roles") or []) if str(role)]
    return roles[0] if roles else "generic"


def _memory_key_text(item: Mapping[str, Any]) -> str:
    return f"{_role_of(item)}|{str(item.get('translation_input') or '')}"


def _restore_protected_tokens(
    item: Mapping[str, Any], raw_vi: str
) -> tuple[str | None, list[str]]:
    translation_input = str(item.get("translation_input") or "")
    expected = sorted(_PLACEHOLDER_RE.findall(translation_input))
    actual = sorted(_PLACEHOLDER_RE.findall(str(raw_vi or "")))
    if expected != actual:
        return None, ["protected_token_mismatch"]

    output = str(raw_vi or "").strip()
    values = [str(value) for value in list(item.get("protected_values") or [])]
    units = list(item.get("unit_tokens") or [])
    for index, value in enumerate(values):
        output = output.replace(f"{{{{VALUE_{index}}}}}", value)
    for index, raw_unit in enumerate(units):
        token = dict(raw_unit) if isinstance(raw_unit, Mapping) else {}
        source_unit = str(token.get("raw") or "")
        rendered_unit = _UNIT_RENDER_OVERRIDES.get(
            source_unit, str(token.get("canonical") or source_unit)
        )
        output = output.replace(f"{{{{UNIT_{index}}}}}", rendered_unit)

    output = _WS_RE.sub(" ", output).strip()
    output = re.sub(r"\s+([,.;:!?])", r"\1", output)
    flags: list[str] = []
    if not output or output == "...":
        flags.append("translation_empty")
    if _PLACEHOLDER_RE.search(output):
        flags.append("protected_token_unresolved")
    if contains_cjk(output):
        flags.append("translation_contains_cjk")
    role = _role_of(item)
    word_count = len([part for part in output.split(" ") if part])
    if role == "hardsub" and word_count > 12:
        flags.append("translation_too_long_for_role")
    elif role != "hardsub" and word_count > 6:
        flags.append("translation_too_long_for_role")
    blocking = [
        flag
        for flag in flags
        if flag
        in {
            "translation_empty",
            "protected_token_unresolved",
            "translation_contains_cjk",
        }
    ]
    return (None if blocking else output), flags


def _approval_preserves_protected_tokens(
    item: Mapping[str, Any], *, candidate: str, approved: str
) -> bool:
    if sorted(_NUMBER_RE.findall(candidate)) != sorted(_NUMBER_RE.findall(approved)):
        return False
    for raw_unit in list(item.get("unit_tokens") or []):
        token = dict(raw_unit) if isinstance(raw_unit, Mapping) else {}
        source_unit = str(token.get("raw") or "")
        # ``个`` is a grammatical counter, not a physical unit. Vietnamese
        # must choose the noun-specific classifier (quả, món, phần...) while
        # the numeric value remains protected by _NUMBER_RE above.
        if source_unit in _CONTEXTUAL_CLASSIFIER_UNITS:
            continue
        rendered_unit = _UNIT_RENDER_OVERRIDES.get(
            source_unit, str(token.get("canonical") or source_unit)
        ).strip()
        if not rendered_unit:
            continue
        pattern = re.compile(
            # Digits may touch a physical unit (``2g``) without changing its
            # meaning. Only surrounding letters make this an embedded token.
            rf"(?<![^\W\d_]){re.escape(rendered_unit)}(?![^\W\d_])",
            re.IGNORECASE,
        )
        if len(pattern.findall(candidate)) != len(pattern.findall(approved)):
            return False
    return True


def _review_input_sha256(
    row: Mapping[str, Any], *, phase2_handoff_sha256: str
) -> str:
    return _sha256_json(
        {
            "schema_version": PHASE3_REVIEW_INPUT_SCHEMA_VERSION,
            "phase2_handoff_sha256": phase2_handoff_sha256,
            "content_id": row.get("content_id"),
            "zh_approved": row.get("zh_approved"),
            "vi_text_candidate": row.get("vi_text_candidate"),
            "quality_flags": list(row.get("quality_flags") or []),
        }
    )


def translate_phase3_handoff(
    handoff: Mapping[str, Any],
    *,
    settings: TranslatorSettings,
    client: Any | None = None,
    memory_path: str | Path | None = None,
    approvals: Mapping[str, Mapping[str, Any]] | None = None,
    review_fossils: Mapping[str, Mapping[str, Any]] | None = None,
    phase2_handoff_path: str | Path | None = None,
) -> dict[str, Any]:
    """Translate each Phase-2 content_id once; never approximate-dedupe."""
    if str(handoff.get("status") or "") != "READY_FOR_PHASE3":
        raise Phase3TranslationError("Phase-2 handoff is not READY_FOR_PHASE3")
    if phase2_handoff_path is not None:
        handoff_sha256 = _sha256_file(phase2_handoff_path)
        handoff_path_name = Path(phase2_handoff_path).name
    else:
        handoff_sha256 = _sha256_json(handoff)
        handoff_path_name = "phase2_handoff.json"

    prompt = f"{settings.system_prompt.strip()}\n\n{PHASE3_MANDATORY_PROMPT}"
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    memory = TranslationMemory(memory_path)
    translate_items = [
        dict(item)
        for item in list(handoff.get("translate_items") or [])
        if isinstance(item, Mapping)
    ]
    raw_by_id: dict[str, str] = {}
    pending: dict[str, dict[str, str]] = {}
    frozen_by_id = {
        str(content_id): dict(raw)
        for content_id, raw in dict(review_fossils or {}).items()
        if str(content_id) and isinstance(raw, Mapping)
    }
    translate_ids = {str(item.get("content_id") or "") for item in translate_items}
    if not set(frozen_by_id).issubset(translate_ids):
        raise Phase3TranslationError(
            "Approved review fossil contains an unknown content_id"
        )
    cache_hits = 0
    for item in translate_items:
        content_id = str(item.get("content_id") or "")
        if content_id in frozen_by_id:
            continue
        hit = memory.get(
            model_name=settings.model_name,
            system_prompt=prompt,
            zh=_memory_key_text(item),
        )
        if hit:
            raw_by_id[content_id] = hit
            cache_hits += 1
        else:
            pending[content_id] = {
                "role": _role_of(item),
                "text": str(item.get("translation_input") or ""),
            }

    raw_response: Any = {}
    if pending:
        runtime_client = client or build_openai_client(settings)
        translated, raw_response = _translate_batch(
            runtime_client,
            model_name=settings.model_name,
            system_prompt=prompt,
            items=pending,
        )
        raw_by_id.update(translated)

    content_objects: list[dict[str, Any]] = []
    for item in translate_items:
        content_id = str(item.get("content_id") or "")
        fossil = frozen_by_id.get(content_id)
        if fossil is not None:
            raw_vi = ""
            candidate = str(fossil.get("vi_text_candidate") or "").strip() or None
            flags = [
                str(value)
                for value in list(fossil.get("quality_flags") or [])
                if str(value)
            ]
            if candidate is None or contains_cjk(candidate):
                raise Phase3TranslationError(
                    f"Approved review fossil is invalid for {content_id}"
                )
        else:
            raw_vi = str(raw_by_id.get(content_id) or "").strip()
            candidate, flags = _restore_protected_tokens(item, raw_vi)
        if fossil is None and candidate is not None:
            memory.put(
                model_name=settings.model_name,
                system_prompt=prompt,
                zh=_memory_key_text(item),
                vi=raw_vi,
            )
        row: dict[str, Any] = {
            "content_id": content_id,
            "geometry_refs": list(item.get("geometry_refs") or []),
            "roles": list(item.get("roles") or []),
            "zh_approved": item.get("zh_approved"),
            "translation_input": item.get("translation_input"),
            "protected_values": list(item.get("protected_values") or []),
            "unit_tokens": list(item.get("unit_tokens") or []),
            "vi_text_raw": raw_vi or None,
            "vi_text_candidate": candidate,
            "vi_text_approved": None,
            "quality_flags": flags,
            "review_status": (
                "TRANSLATION_CANDIDATE" if candidate is not None else "TRANSLATION_FAILED"
            ),
            "review_required": True,
            "operator_review": None,
        }
        row["review_input_sha256"] = _review_input_sha256(
            row, phase2_handoff_sha256=handoff_sha256
        )
        if fossil is not None and str(
            fossil.get("review_input_sha256") or ""
        ) != row["review_input_sha256"]:
            raise Phase3TranslationError(
                f"Approved review fossil hash mismatch for {content_id}"
            )
        approval = (approvals or {}).get(content_id) or {}
        decision = str(approval.get("decision") or "").upper()
        approval_hash = str(approval.get("review_input_sha256") or "")
        stale = bool(decision) and approval_hash != row["review_input_sha256"]
        if stale:
            row["review_status"] = "TRANSLATION_REVIEW_STALE"
        elif decision in {"APPROVE", "EDIT"} and candidate is not None:
            approved_text = str(
                approval.get("vi_text_approved") or candidate or ""
            ).strip()
            approval_text_valid = (
                bool(approved_text)
                and not contains_cjk(approved_text)
                and approved_text != "..."
            )
            approval_tokens_valid = approval_text_valid and _approval_preserves_protected_tokens(
                item,
                candidate=candidate,
                approved=approved_text,
            )
            approval_is_safe = approval_text_valid and approval_tokens_valid
            if approval_is_safe:
                row["vi_text_approved"] = approved_text
                row["review_status"] = "TRANSLATION_APPROVED"
                row["review_required"] = False
            else:
                row["quality_flags"].append(
                    "approval_protected_token_mismatch"
                    if approval_text_valid
                    else "approval_invalid_text"
                )
                row["review_status"] = "TRANSLATION_REVIEW_INVALID"
        elif decision == "REJECT":
            row["review_status"] = "TRANSLATION_REJECTED"
            row["review_required"] = False
        if decision:
            row["operator_review"] = {
                "decision": decision,
                "reviewer": approval.get("reviewer"),
                "reviewed_at": approval.get("reviewed_at"),
                "review_input_sha256": approval_hash or None,
                "stale": stale,
            }
        content_objects.append(row)

    try:
        memory.save()
    except OSError as exc:
        raise Phase3TranslationError(f"Cannot save translation memory: {exc}") from exc

    for item in list(handoff.get("deterministic_items") or []):
        if not isinstance(item, Mapping):
            continue
        content_objects.append(
            {
                "content_id": item.get("content_id"),
                "geometry_refs": list(item.get("geometry_refs") or []),
                "roles": list(item.get("roles") or []),
                "zh_approved": item.get("zh_approved"),
                "translation_input": None,
                "protected_values": list(item.get("protected_values") or []),
                "unit_tokens": list(item.get("unit_tokens") or []),
                "vi_text_raw": None,
                "vi_text_candidate": item.get("render_text"),
                "vi_text_approved": item.get("render_text"),
                "quality_flags": [],
                "review_status": "TRANSLATION_DETERMINISTIC",
                "review_required": False,
                "review_input_sha256": None,
                "operator_review": None,
            }
        )

    unresolved = sum(1 for row in content_objects if row["review_required"])
    failed = sum(1 for row in content_objects if row["review_status"] == "TRANSLATION_FAILED")
    stale = sum(
        1 for row in content_objects if row["review_status"] == "TRANSLATION_REVIEW_STALE"
    )
    approved_n = sum(
        1 for row in content_objects if row["review_status"] == "TRANSLATION_APPROVED"
    )
    deterministic_n = sum(
        1 for row in content_objects if row["review_status"] == "TRANSLATION_DETERMINISTIC"
    )
    if unresolved == 0:
        status = "TRANSLATION_APPROVED"
    elif failed:
        status = "TRANSLATION_FAILED"
    elif stale:
        status = "TRANSLATION_REVIEW_STALE"
    else:
        status = "NEEDS_TRANSLATION_REVIEW"
    return {
        "schema_version": PHASE3_SCHEMA_VERSION,
        "phase2_handoff_ref": {
            "path": handoff_path_name,
            "sha256": handoff_sha256,
        },
        "provider": {
            "source": settings.source,
            "model": settings.model_name,
            "prompt_sha256": prompt_sha256,
            "temperature": 0,
        },
        "stats": {
            "translate_items": len(translate_items),
            "deterministic_items": deterministic_n,
            "cache_hits": cache_hits,
            "llm_sent": len(pending),
            "review_fossil_hits": len(frozen_by_id),
        },
        "content_objects": content_objects,
        "review_summary": {
            "content_objects": len(content_objects),
            "approved": approved_n,
            "deterministic": deterministic_n,
            "failed": failed,
            "stale": stale,
            "unresolved": unresolved,
            "status": status,
        },
        "_raw_response": raw_response,
    }


def _build_render_handoff(contract: Mapping[str, Any]) -> dict[str, Any]:
    geometry_map: dict[str, dict[str, Any]] = {}
    blocked: list[str] = []
    for row in list(contract.get("content_objects") or []):
        if not isinstance(row, Mapping):
            continue
        status = str(row.get("review_status") or "")
        vi = str(row.get("vi_text_approved") or "").strip()
        content_id = str(row.get("content_id") or "")
        if status not in {"TRANSLATION_APPROVED", "TRANSLATION_DETERMINISTIC"}:
            blocked.append(f"translation_not_approved:{content_id}")
        for text_id in list(row.get("geometry_refs") or []):
            geometry_map[str(text_id)] = {
                "content_id": content_id,
                "text_vi": vi or None,
                "translation_status": status,
            }
    blocked = list(dict.fromkeys(blocked))
    return {
        "schema_version": PHASE3_RENDER_HANDOFF_SCHEMA_VERSION,
        "phase2_handoff_ref": contract.get("phase2_handoff_ref"),
        "status": "READY_FOR_RENDER" if not blocked else "RENDER_HANDOFF_BLOCKED",
        "blocked_reasons": blocked,
        "counts": {
            "content_objects": len(list(contract.get("content_objects") or [])),
            "geometry_refs": len(geometry_map),
        },
        "geometry_map": geometry_map,
    }


def _quarantine(path: Path, *, root: Path) -> None:
    if not path.is_file():
        return
    stale_dir = root / "qa" / "stale"
    stale_dir.mkdir(parents=True, exist_ok=True)
    destination = stale_dir / f"{path.stem}_{_sha256_file(path)[:12]}{path.suffix}"
    path.replace(destination)


def write_phase3_artifacts(
    *, root_dir: str | Path, contract: Mapping[str, Any]
) -> dict[str, Path]:
    root = Path(root_dir)
    timeline_path = root / "phase3_translation_timeline.json"
    review_path = root / "phase3_review_queue.json"
    approvals_path = root / "phase3_approvals.json"
    render_preview_path = root / "phase3_render_handoff_preview.json"
    render_path = root / "phase3_render_handoff.json"
    raw_path = root / "qa" / "phase3_translation_raw.json"
    stats_path = root / "qa" / "phase3_translation_stats.json"

    public_contract = {
        key: value for key, value in dict(contract).items() if not key.startswith("_")
    }
    _write_json_atomic(timeline_path, public_contract)
    review_rows = [
        row
        for row in list(contract.get("content_objects") or [])
        if isinstance(row, Mapping) and row.get("review_required")
    ]
    _write_json_atomic(
        review_path,
        {
            "schema_version": PHASE3_SCHEMA_VERSION,
            "phase2_handoff_ref": contract.get("phase2_handoff_ref"),
            "review_summary": contract.get("review_summary"),
            "content_objects": review_rows,
        },
    )
    if not approvals_path.exists():
        _write_json_atomic(
            approvals_path,
            {
                "schema_version": PHASE3_APPROVAL_SCHEMA_VERSION,
                "phase2_handoff_ref": contract.get("phase2_handoff_ref"),
                "approvals": [
                    {
                        "content_id": row.get("content_id"),
                        "decision": "",
                        "review_input_sha256": row.get("review_input_sha256"),
                        "vi_text_approved": row.get("vi_text_candidate"),
                        "reviewer": None,
                        "reviewed_at": None,
                    }
                    for row in review_rows
                    if row.get("vi_text_candidate")
                ],
            },
        )
    render_handoff = _build_render_handoff(contract)
    _write_json_atomic(render_preview_path, render_handoff)
    if render_handoff["status"] == "READY_FOR_RENDER":
        _write_json_atomic(render_path, render_handoff)
    else:
        _quarantine(render_path, root=root)
    _write_json_atomic(raw_path, contract.get("_raw_response") or {})
    _write_json_atomic(
        stats_path,
        {
            "phase2_handoff_ref": contract.get("phase2_handoff_ref"),
            "provider": contract.get("provider"),
            "stats": contract.get("stats"),
            "review_summary": contract.get("review_summary"),
        },
    )
    return {
        "timeline": timeline_path,
        "review_queue": review_path,
        "approvals": approvals_path,
        "render_handoff_preview": render_preview_path,
        "render_handoff": render_path,
        "raw_response": raw_path,
        "stats": stats_path,
    }
