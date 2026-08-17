"""Batch ZH→VI caption translation via one OpenAI-compatible LLM request."""

from __future__ import annotations

import logging
from pathlib import Path
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
from src.media_pipeline.translator.fossil import write_translate_fossils
from src.media_pipeline.translator.memory import TranslationMemory
from src.media_pipeline.translator.normalize import (
    broadcast_zh_translations,
    flatten_ocr_chinese,
    merge_near_duplicate_zh,
    remap_tracking_to_representatives,
    segment_authority_zh,
    unique_chinese_texts,
)
from src.media_pipeline.translator.resolve import resolve_translator_settings
from src.media_pipeline.translator.rule_route import rule_translate_zh
from src.media_pipeline.translator.translate_llm import ContextualTranslator, MISSING_VI
from src.audio_pipeline.google_cloud_genai import is_google_cloud_retryable_error

logger = logging.getLogger(__name__)


def _is_retryable_llm_error(exc: BaseException) -> bool:
    if is_google_cloud_retryable_error(exc):
        return True
    if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError):
        code = getattr(exc, "status_code", None)
        if code is None:
            return True
        return code in {408, 409, 429} or int(code) >= 500
    return False


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_llm_error),
)
def _chat_translate_opaque(
    translator: ContextualTranslator,
    unique_zh: list[str],
) -> dict[str, str]:
    """
    Translate unique ZH via opaque ids ``u0..uN`` (avoid ZH-as-JSON-key fragility).

    Returns ZH→VI dictionary.
    """
    id_to_zh = {f"u{i}": zh for i, zh in enumerate(unique_zh)}
    id_to_vi = translator.translate_id_map(id_to_zh)
    out: dict[str, str] = {}
    for oid, zh in id_to_zh.items():
        vi = str(id_to_vi.get(oid) or "").strip()
        out[zh] = vi if vi else MISSING_VI
    return out


def _safe_terminal_print(msg: str) -> None:
    """Windows consoles may be cp1252 — never crash the translate path on glyphs."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"), flush=True)


def _log_dedupe_stats(
    *,
    tracking_n: int,
    unique_n: int,
    rule_hit: int = 0,
    cache_hit: int = 0,
    llm_sent: int = 0,
) -> None:
    if tracking_n <= 0:
        pct = 0.0
    else:
        pct = max(0.0, 100.0 * (1.0 - (float(unique_n) / float(tracking_n))))
    msg = (
        f"[INFO] Tổng số frame cần dịch: {tracking_n}. "
        f"Số câu ZH duy nhất gửi LLM: {llm_sent}. "
        f"Unique sau dedupe: {unique_n} "
        f"(rule={rule_hit}, cache={cache_hit}). "
        f"Đã giảm tải {pct:.0f}% Token vs stamp."
    )
    _safe_terminal_print(msg)
    logger.info(
        "caption_translate_dedupe tracking=%s unique=%s rule=%s cache=%s llm=%s saved_pct=%.1f",
        tracking_n,
        unique_n,
        rule_hit,
        cache_hit,
        llm_sent,
        pct,
    )


def _dry_vi(zh: str) -> str:
    dry_known = {
        "中式减脂餐": "Bữa giảm béo kiểu Trung",
        "加盐": "Thêm muối",
        "虾仁豆腐蒸蛋614千卡": "Tôm đậu hũ trứng hấp 614 kcal",
        "虾仁豆腐蒸蛋": "Tôm đậu hũ trứng hấp",
        "生抽香油调味": "Xì dầu + dầu mè",
        "香油调味": "Xì dầu + dầu mè",
        "碳水化合物": "Carbohydrate",
        "即热米饭": "Cơm ăn liền",
        "鸡蛋": "Trứng",
        "52克": "52g",
        "花": "Bông cải",
        "西兰花": "Bông cải xanh",
        "嫩豆腐": "Đậu hũ non",
        "锅蒸": "Hấp",
        "水开上锅蒸15分钟": "Nước sôi, hấp 15 phút",
        "定上联15分钟": "Hấp khoảng 15 phút",
        "每天都会更新好吃的减脂餐": "Mỗi ngày cập nhật món giảm béo ngon",
        "天都会更新好吃的减脂餐": "Mỗi ngày cập nhật món giảm béo ngon",
        "的朋友给个关注吧": "Nhớ follow nhé",
        "勺朋友给个关注吧": "Nhớ follow nhé",
        "好吃还营养": "Ngon và bổ dưỡng",
        "豆腐(南)200克": "Đậu hũ (nam) 200g",
        "豆腐(南)": "Đậu hũ (nam)",
        "鸡蛋100克": "Trứng 100g",
        "虾52克": "Tôm 52g",
        "150克": "150g",
        "字幕": "Phụ đề",
        "淋上蛋液": "Chan hỗn hợp trứng",
        "虾仁": "Tôm",
        "简简单单一锅蒸": "Đơn giản chỉ cần hấp một nồi",
        "食物4个": "4 món",
    }
    text = str(zh or "").strip()
    if not text:
        return MISSING_VI
    ruled = rule_translate_zh(text)
    if ruled is not None:
        return ruled
    if text in dry_known:
        return dry_known[text]
    if all(ord(ch) < 128 for ch in text):
        return text
    return MISSING_VI


def _resolve_unique_zh(
    ocr_data: Mapping[Any, Any] | list[Any],
    tracking_map: dict[str, str],
) -> tuple[dict[str, str], list[str], dict[str, str]]:
    """
    Apply near-dupe merge; prefer track segment set when available.

    Returns ``(remapped_tracking, unique_zh, alias_to_rep)``.
    """
    segments = segment_authority_zh(ocr_data) if not isinstance(ocr_data, list) else {}
    seed = list(segments.values()) if segments else list(unique_chinese_texts(tracking_map))
    # Include any stamp ZH not covered by segments (legacy payloads).
    for zh in unique_chinese_texts(tracking_map):
        if zh not in seed:
            seed.append(zh)
    alias_to_rep = merge_near_duplicate_zh(seed)
    remapped = remap_tracking_to_representatives(tracking_map, alias_to_rep)
    unique_zh = unique_chinese_texts(remapped)
    return remapped, unique_zh, alias_to_rep


def translate_subtitles(
    ocr_data: Mapping[Any, Any] | list[Any],
    *,
    db: Session | None = None,
    workspace_id: UUID | None = None,
    settings: TranslatorSettings | None = None,
    client: OpenAI | None = None,
    artifact_dir: str | Path | None = None,
    memory_path: str | Path | None = None,
) -> dict[str, str]:
    """
    Batch-translate Chinese captions → Vietnamese.

    Pipeline: canonicalize → track/segment seed → near-dupe → rule-route →
    translation memory → opaque-id LLM (temp=0) → broadcast ``vi_texts``.

    Settings authority:
      Ops ``/ops/caption-ai`` + ``/ops/caption-prompt`` when enabled;
      else env ``LLM_*`` / ``TRANSLATION_SYSTEM_PROMPT`` fallback.

    ``TRANSLATE_LLM_DRY=1`` → offline map (no live LLM); missing → ``...``.

    Input: `{timestamp: chinese}` or Phase 2 OCR `to_dict()`.
    Output: `{timestamp: vietnamese}` (missing LLM ids → ``...``).
    """
    import os

    tracking_map = flatten_ocr_chinese(ocr_data)
    remapped, unique_zh, _alias = _resolve_unique_zh(ocr_data, tracking_map)
    stamped_n = sum(1 for k in remapped if "#" in str(k))
    tracking_n = stamped_n if stamped_n > 0 else len(remapped)

    translated_dict: dict[str, str] = {}
    rule_hit = 0
    cache_hit = 0
    llm_sent = 0

    # 5. Rule-route before LLM.
    need_after_rules: list[str] = []
    for zh in unique_zh:
        ruled = rule_translate_zh(zh)
        if ruled is not None:
            translated_dict[zh] = ruled
            rule_hit += 1
        else:
            need_after_rules.append(zh)

    dry = os.environ.get("TRANSLATE_LLM_DRY", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    if dry:
        for zh in need_after_rules:
            translated_dict[zh] = _dry_vi(zh)
        llm_sent = 0
        _log_dedupe_stats(
            tracking_n=tracking_n,
            unique_n=len(unique_zh),
            rule_hit=rule_hit,
            cache_hit=0,
            llm_sent=0,
        )
        result = broadcast_zh_translations(
            remapped, translated_dict, missing=MISSING_VI
        )
        if artifact_dir is not None:
            write_translate_fossils(
                artifact_dir,
                unique_zh_to_vi=translated_dict,
                vi_texts=result,
                stats={
                    "tracking_n": tracking_n,
                    "unique_n": len(unique_zh),
                    "rule_hit": rule_hit,
                    "cache_hit": 0,
                    "llm_sent": 0,
                    "source": "dry",
                },
            )
        logger.info(
            "caption_translate_dry",
            extra={
                "segments": len(result),
                "unique": len(unique_zh),
                "source": "dry",
            },
        )
        return result

    cfg = settings or resolve_translator_settings(db=db, workspace_id=workspace_id)
    memory = TranslationMemory(memory_path)
    need_llm: list[str] = []
    for zh in need_after_rules:
        hit = memory.get(
            model_name=cfg.model_name,
            system_prompt=cfg.system_prompt,
            zh=zh,
        )
        if hit:
            translated_dict[zh] = hit
            cache_hit += 1
        else:
            need_llm.append(zh)

    openai_client = client or build_openai_client(cfg)
    translator = ContextualTranslator(cfg, client=openai_client)

    logger.info(
        "caption_translate_start",
        extra={
            "segments": len(remapped),
            "unique": len(unique_zh),
            "llm_pending": len(need_llm),
            "model": cfg.model_name,
            "base_url": cfg.base_url,
            "source": cfg.source,
        },
    )

    if need_llm:
        try:
            llm_dict = _chat_translate_opaque(translator, need_llm)
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
                f"LLM failed: {exc}",
            ) from exc
        llm_sent = len(need_llm)
        for zh, vi in llm_dict.items():
            safe = str(vi or "").strip() or MISSING_VI
            translated_dict[zh] = safe
            memory.put(
                model_name=cfg.model_name,
                system_prompt=cfg.system_prompt,
                zh=zh,
                vi=safe,
            )
        try:
            memory.save()
        except OSError as exc:
            logger.warning("translate_memory_save_failed err=%s", exc)

    # Fail-safe: every unique ZH has an entry.
    safe_dict = {
        zh: str(translated_dict.get(zh) or "").strip() or MISSING_VI
        for zh in unique_zh
    }
    _log_dedupe_stats(
        tracking_n=tracking_n,
        unique_n=len(unique_zh),
        rule_hit=rule_hit,
        cache_hit=cache_hit,
        llm_sent=llm_sent,
    )
    result = broadcast_zh_translations(remapped, safe_dict, missing=MISSING_VI)
    if artifact_dir is not None:
        write_translate_fossils(
            artifact_dir,
            unique_zh_to_vi=safe_dict,
            vi_texts=result,
            stats={
                "tracking_n": tracking_n,
                "unique_n": len(unique_zh),
                "rule_hit": rule_hit,
                "cache_hit": cache_hit,
                "llm_sent": llm_sent,
                "source": cfg.source,
                "model": cfg.model_name,
            },
        )
    return result
