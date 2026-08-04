"""Step 3: Contextual ZH→VI translation using Ops Caption AI settings.

Authority for model + system prompt:
  ``resolve_translator_settings`` → ``/ops/caption-ai`` + ``/ops/caption-prompt``
  (env ``LLM_*`` / ``TRANSLATION_SYSTEM_PROMPT`` fallback).

Uses OpenAI-compatible JSON mode (Gemini included via caption-ai base_url).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Mapping, Sequence, TypedDict

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from src.media_pipeline.translator.client import build_openai_client
from src.media_pipeline.translator.config import TranslatorSettings
from src.media_pipeline.translator.errors import TranslatorError, TranslatorErrorCode
from src.media_pipeline.translator.resolve import resolve_translator_settings

logger = logging.getLogger(__name__)

MISSING_VI = "..."

USER_BATCH_INSTRUCTION = (
    "Dưới đây là JSON object: khóa = id ô chữ, giá trị = nhãn/UI hoặc phụ đề tiếng Trung. "
    "Hãy dịch sang tiếng Việt RÚT GỌN theo system prompt (ưu tiên 1–6 từ cho label UI; "
    "tối đa ~12 chữ nếu là câu phụ đề). "
    "Bắt buộc tiếng Việt có dấu đầy đủ. Giữ số và đơn vị (g, kcal, %). "
    "Trả về ĐÚNG một JSON object với CÙNG các khóa, giá trị là tiếng Việt. "
    "Không thêm khóa khác, không markdown. "
    "(Tuỳ chọn tương đương: {\"translations\":[{\"id\":\"box_0\",\"vietnamese_text\":\"...\"}, ...]})."
)


class TextItem(TypedDict):
    id: str
    text: str
    timestamp: str
    original_box_coords: list[float]


class TranslatedHit(TypedDict):
    original_box_coords: list[float]
    original_text: str
    vietnamese_text: str


# timestamp → list of translated hits
Step3Result = dict[str, list[TranslatedHit]]


def _as_float_list(raw: Any) -> list[float]:
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[float] = []
    for value in raw:
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            continue
    return out


class ContextualTranslator:
    """
    Flatten Step-2 OCR JSON → one LLM batch → remap Vietnamese with fail-safe.
    """

    def __init__(
        self,
        settings: TranslatorSettings,
        *,
        client: OpenAI | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or build_openai_client(settings)

    @staticmethod
    def assign_ids(step2_grouped: Mapping[str, Any]) -> list[TextItem]:
        """
        Flatten timestamp-grouped Step-2 hits into a 1-D list with unique ``box_N`` ids.

        Expected hit shape: ``{"text": "...", "box": [8 floats]}`` (analyze_ocr).
        """
        items: list[TextItem] = []
        # Stable order by timestamp key string (same as analyze_ocr ordered output).
        for timestamp in sorted(step2_grouped.keys()):
            hits = step2_grouped.get(timestamp) or []
            if not isinstance(hits, list):
                continue
            for hit in hits:
                if not isinstance(hit, Mapping):
                    continue
                text = str(hit.get("text") or "").strip()
                if not text:
                    continue
                coords = _as_float_list(hit.get("box") or hit.get("original_box_coords"))
                items.append(
                    {
                        "id": f"box_{len(items)}",
                        "text": text,
                        "timestamp": str(timestamp),
                        "original_box_coords": coords,
                    }
                )
        return items

    def _chat_json(self, text_array: Sequence[Mapping[str, Any]]) -> Any:
        """One OpenAI-compatible chat call; returns parsed JSON (object)."""
        # Object map matches Ops caption-prompt ("cùng khóa với input").
        id_to_zh = {str(row["id"]): str(row["text"]) for row in text_array}
        user_body = json.dumps(id_to_zh, ensure_ascii=False, indent=2)
        messages = [
            {"role": "system", "content": self.settings.system_prompt},
            {
                "role": "user",
                "content": f"{USER_BATCH_INSTRUCTION}\n\n{user_body}",
            },
        ]
        try:
            response = self.client.chat.completions.create(
                model=self.settings.model_name,
                messages=messages,
                response_format={"type": "json_object"},
                # Deterministic captions: same ZH → same VI across re-runs.
                temperature=0,
            )
        except (APITimeoutError, APIConnectionError, RateLimitError, APIStatusError):
            raise
        except Exception as exc:  # noqa: BLE001
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

        return self._parse_llm_json(content)

    @staticmethod
    def _parse_llm_json(content: str) -> Any:
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
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TranslatorError(
                TranslatorErrorCode.INVALID_RESPONSE,
                f"LLM response is not valid JSON: {exc}",
            ) from exc

    @staticmethod
    def _translations_by_id(payload: Any, *, expected_ids: Sequence[str]) -> dict[str, str]:
        """
        Accept ``{"translations":[{"id","vietnamese_text"}]}``, flat ``{id: vi}``,
        or a bare list. Missing ids → ``...`` (fail-safe, no crash).
        """
        by_id: dict[str, str] = {}
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, Mapping):
            if isinstance(payload.get("translations"), list):
                rows = list(payload["translations"])
            else:
                # Flat object map id → vietnamese
                for key in expected_ids:
                    if key in payload:
                        by_id[key] = str(payload[key]).strip() or MISSING_VI
                rows = []
        else:
            rows = []

        for row in rows:
            if not isinstance(row, Mapping):
                continue
            item_id = str(row.get("id") or "").strip()
            if not item_id:
                continue
            vi = str(
                row.get("vietnamese_text")
                or row.get("text_vi")
                or row.get("text")
                or ""
            ).strip()
            by_id[item_id] = vi or MISSING_VI

        missing = [item_id for item_id in expected_ids if item_id not in by_id]
        if missing:
            logger.warning(
                "caption_translate_missing_ids count=%s ids=%s",
                len(missing),
                missing[:12],
            )
        for item_id in expected_ids:
            if item_id not in by_id:
                by_id[item_id] = MISSING_VI
            elif not by_id[item_id]:
                by_id[item_id] = MISSING_VI
        return by_id

    def map_translations(
        self,
        items: Sequence[TextItem],
        by_id: Mapping[str, str],
    ) -> Step3Result:
        nested: Step3Result = {}
        for item in items:
            ts = item["timestamp"]
            nested.setdefault(ts, []).append(
                {
                    "original_box_coords": list(item["original_box_coords"]),
                    "original_text": item["text"],
                    "vietnamese_text": str(by_id.get(item["id"], MISSING_VI)),
                }
            )
        return nested

    async def translate_batch(
        self,
        text_array: Sequence[Mapping[str, Any]],
    ) -> dict[str, str]:
        """Async wrapper: one LLM request for the whole batch → id→vietnamese."""
        if not text_array:
            return {}
        payload = await asyncio.to_thread(self._chat_json, text_array)
        expected = [str(row["id"]) for row in text_array]
        return self._translations_by_id(payload, expected_ids=expected)

    def translate_step2_sync(self, step2_grouped: Mapping[str, Any]) -> Step3Result:
        """Full Step-3 pipeline (sync) for scripts / hardsub callers."""
        items = self.assign_ids(step2_grouped)
        if not items:
            raise TranslatorError(
                TranslatorErrorCode.EMPTY_INPUT,
                "No Step-2 text items to translate",
            )
        payload = self._chat_json(items)
        by_id = self._translations_by_id(
            payload,
            expected_ids=[item["id"] for item in items],
        )
        return self.map_translations(items, by_id)

    async def translate_step2(self, step2_grouped: Mapping[str, Any]) -> Step3Result:
        items = self.assign_ids(step2_grouped)
        if not items:
            raise TranslatorError(
                TranslatorErrorCode.EMPTY_INPUT,
                "No Step-2 text items to translate",
            )
        by_id = await self.translate_batch(items)
        return self.map_translations(items, by_id)

    def translate_id_map(self, chinese_map: Mapping[str, str]) -> dict[str, str]:
        """
        Phase 2.5 compatibility: ``{segment_id: zh}`` → ``{segment_id: vi}``.

        Fail-safe missing keys with ``...`` (does not raise).
        """
        items: list[dict[str, Any]] = [
            {"id": str(key), "text": str(text)}
            for key, text in chinese_map.items()
            if str(text or "").strip()
        ]
        if not items:
            raise TranslatorError(
                TranslatorErrorCode.EMPTY_INPUT,
                "No Chinese text to translate",
            )
        payload = self._chat_json(items)
        return self._translations_by_id(
            payload,
            expected_ids=[str(row["id"]) for row in items],
        )


def build_contextual_translator(
    settings: TranslatorSettings | None = None,
    *,
    client: OpenAI | None = None,
    db: Any = None,
    workspace_id: Any = None,
) -> ContextualTranslator:
    cfg = settings or resolve_translator_settings(db=db, workspace_id=workspace_id)
    return ContextualTranslator(cfg, client=client)


if __name__ == "__main__":
    # Dummy Step-2 payload (analyze_ocr grouped shape).
    # TRANSLATE_LLM_DRY=1 → offline mock; else caption-ai / env LLM.
    import os
    from types import SimpleNamespace

    dummy_step2 = {
        "00:01.167": [
            {
                "text": "虾仁豆腐蒸蛋614千卡",
                "box": [0.0, 934.8, 1239.3, 934.8, 1239.3, 989.25, 0.0, 989.25],
            }
        ],
        "00:02.000": [
            {
                "text": "加盐",
                "box": [301.2, 499.2, 430.8, 499.2, 430.8, 568.5, 301.2, 568.5],
            }
        ],
        "00:27.500": [
            {
                "text": "碳水化合物",
                "box": [100.0, 200.0, 300.0, 200.0, 300.0, 240.0, 100.0, 240.0],
            },
            {
                "text": "52克",
                "box": [144.0, 962.0, 220.0, 992.0, 220.0, 992.0, 144.0, 992.0],
            },
        ],
    }

    _VI = {
        "虾仁豆腐蒸蛋614千卡": "Tôm đậu hũ trứng hấp 614 kcal",
        "加盐": "Thêm muối",
        "碳水化合物": "Carbohydrate",
        "52克": "52g",
    }

    if os.environ.get("TRANSLATE_LLM_DRY", "").strip().lower() in {"1", "true", "yes"}:

        class _DryCompletions:
            @staticmethod
            def create(**kwargs: Any) -> Any:
                raw_user = str(kwargs["messages"][1]["content"])
                body = raw_user.split("\n\n", 1)[-1]
                id_to_zh = json.loads(body)
                # Prefer flat object (matches caption-prompt); also valid for parser.
                translated = {
                    item_id: _VI.get(zh, "...") for item_id, zh in id_to_zh.items()
                }
                content = json.dumps(translated, ensure_ascii=False)
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
                )

        class _DryClient:
            chat = SimpleNamespace(completions=_DryCompletions())

        dry_settings = TranslatorSettings(
            api_key="dry",
            base_url="https://example.test/v1",
            model_name="dry-model",
            system_prompt="DRY caption-prompt from Ops",
            source="dry",
        )
        translator = ContextualTranslator(dry_settings, client=_DryClient())  # type: ignore[arg-type]
        result = translator.translate_step2_sync(dummy_step2)
    else:
        try:
            translator = build_contextual_translator()
            result = translator.translate_step2_sync(dummy_step2)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[hint] live LLM unavailable ({exc}); "
                "retry with TRANSLATE_LLM_DRY=1"
            )
            raise SystemExit(1) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))
