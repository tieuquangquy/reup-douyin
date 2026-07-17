"""Batch ZH→VI caption translation via one OpenAI-compatible LLM request."""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping
from uuid import UUID

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.media_pipeline.translator.client import build_openai_client
from src.media_pipeline.translator.config import TranslatorSettings
from src.media_pipeline.translator.errors import TranslatorError, TranslatorErrorCode
from src.media_pipeline.translator.normalize import flatten_ocr_chinese
from src.media_pipeline.translator.resolve import resolve_translator_settings

logger = logging.getLogger(__name__)

USER_INSTRUCTION = (
    "Dưới đây là JSON object: khóa = timestamp (ms hoặc id), giá trị = câu tiếng Trung. "
    "Hãy dịch sang tiếng Việt và trả về ĐÚNG một JSON object với CÙNG các khóa, "
    "giá trị là bản dịch tiếng Việt đã rút gọn cho phụ đề. "
    "Không thêm khóa khác, không markdown."
)


def _is_retryable_llm_error(exc: BaseException) -> bool:
    if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        code = getattr(exc, "status_code", None)
        if code is None:
            return True
        return code in {408, 409, 429} or int(code) >= 500
    return False


def _parse_translation_json(content: str, *, expected_keys: list[str]) -> dict[str, str]:
    raw = (content or "").strip()
    if not raw:
        raise TranslatorError(
            TranslatorErrorCode.INVALID_RESPONSE,
            "LLM returned empty content",
        )
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TranslatorError(
            TranslatorErrorCode.INVALID_RESPONSE,
            f"LLM response is not valid JSON: {exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise TranslatorError(
            TranslatorErrorCode.INVALID_RESPONSE,
            "LLM JSON must be an object mapping timestamp → Vietnamese text",
        )

    out: dict[str, str] = {}
    for key in expected_keys:
        if key in payload:
            out[key] = str(payload[key]).strip()
            continue
        alt = None
        try:
            alt = payload.get(int(key))
        except (TypeError, ValueError):
            alt = None
        if alt is None and str(key) in payload:
            alt = payload[str(key)]
        if alt is None:
            raise TranslatorError(
                TranslatorErrorCode.INVALID_RESPONSE,
                f"LLM JSON missing key {key!r}",
            )
        out[key] = str(alt).strip()
    return out


def _chat_translate(
    client: OpenAI,
    settings: TranslatorSettings,
    chinese_map: dict[str, str],
) -> dict[str, str]:
    user_payload = json.dumps(chinese_map, ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": settings.system_prompt},
        {
            "role": "user",
            "content": f"{USER_INSTRUCTION}\n\n{user_payload}",
        },
    ]
    try:
        response = client.chat.completions.create(
            model=settings.model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.3,
        )
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError, APIStatusError)):
            raise
        raise TranslatorError(
            TranslatorErrorCode.LLM_FAILED,
            f"LLM request failed: {exc}",
        ) from exc

    try:
        content = response.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError) as exc:
        raise TranslatorError(
            TranslatorErrorCode.INVALID_RESPONSE,
            f"Unexpected LLM response shape: {exc}",
        ) from exc

    return _parse_translation_json(content, expected_keys=list(chinese_map.keys()))


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_llm_error),
)
def _chat_translate_with_retry(
    client: OpenAI,
    settings: TranslatorSettings,
    chinese_map: dict[str, str],
) -> dict[str, str]:
    return _chat_translate(client, settings, chinese_map)


def translate_subtitles(
    ocr_data: Mapping[Any, Any] | list[Any],
    *,
    db: Session | None = None,
    workspace_id: UUID | None = None,
    settings: TranslatorSettings | None = None,
    client: OpenAI | None = None,
) -> dict[str, str]:
    """
    Batch-translate Chinese captions → Vietnamese in **one** LLM call.

    Settings authority:
      Ops Console → Translation settings (workspace DB) when override enabled;
      else env ``LLM_*`` fallback.

    Input: `{timestamp: chinese}` or Phase 2 OCR `to_dict()`.
    Output: `{timestamp: vietnamese}`.
    """
    chinese_map = flatten_ocr_chinese(ocr_data)
    cfg = settings or resolve_translator_settings(db=db, workspace_id=workspace_id)
    openai_client = client or build_openai_client(cfg)

    logger.info(
        "caption_translate_start",
        extra={
            "segments": len(chinese_map),
            "model": cfg.model_name,
            "base_url": cfg.base_url,
            "source": cfg.source,
        },
    )

    try:
        result = _chat_translate_with_retry(openai_client, cfg, chinese_map)
    except TranslatorError:
        raise
    except (APITimeoutError, APIConnectionError, RateLimitError, APIStatusError) as exc:
        raise TranslatorError(
            TranslatorErrorCode.LLM_FAILED,
            f"LLM failed after retries: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise TranslatorError(
            TranslatorErrorCode.LLM_FAILED,
            f"LLM translation failed: {exc}",
        ) from exc

    logger.info(
        "caption_translate_done",
        extra={"segments": len(result), "model": cfg.model_name, "source": cfg.source},
    )
    return result
