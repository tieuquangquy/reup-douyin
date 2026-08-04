"""QA Automation report for ContextualTranslator (Step 3).

Standalone runner — not the unittest suite under ``tests/``.

Usage (from apps/api)::

    set PYTHONPATH=.
    python test_translate_llm.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Allow ``python test_translate_llm.py`` from apps/api without exporting PYTHONPATH.
_API_ROOT = Path(__file__).resolve().parent
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from src.media_pipeline.translator.config import TranslatorSettings
from src.media_pipeline.translator.translate_llm import ContextualTranslator

# --- ANSI ---
RESET = "\033[0m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
CYAN = "\033[96m"

DUMMY_INPUT: dict[str, list[dict[str, Any]]] = {
    "00:05.000": [
        {
            "text": "这件衣服太帅了",
            "box": [100.0, 900.0, 500.0, 900.0, 500.0, 960.0, 100.0, 960.0],
        }
    ],
    "00:12.500": [
        {
            "text": "家人们赶紧去冲吧",
            "box": [80.0, 880.0, 620.0, 880.0, 620.0, 940.0, 80.0, 940.0],
        },
        {
            "text": "今日特惠",
            "box": [200.0, 200.0, 400.0, 200.0, 400.0, 260.0, 200.0, 260.0],
        },
    ],
}

# Controlled VI for structure + vibe checks (offline; no live LLM).
_MOCK_VI = {
    "这件衣服太帅了": "Áo này quá chất",
    "家人们赶紧去冲吧": "Anh em tranh thủ mua",
    "今日特惠": "Ưu đãi hôm nay",
}


def _settings() -> TranslatorSettings:
    return TranslatorSettings(
        api_key="qa-test",
        base_url="https://example.test/v1",
        model_name="qa-model",
        system_prompt="QA caption-prompt (Ops caption-ai authority stub)",
        source="qa",
    )


def _pass(msg: str) -> None:
    print(f"  {GREEN}{BOLD}[PASS]{RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"  {RED}{BOLD}[FAIL]{RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}{BOLD}[WARNING]{RESET} {msg}")


def _header(title: str) -> None:
    print(f"\n{CYAN}{BOLD}=== {title} ==={RESET}")


def _mock_llm_full(text_array: Any) -> dict[str, str]:
    """Return complete id→VI map for every input row."""
    out: dict[str, str] = {}
    for row in text_array:
        item_id = str(row["id"])
        zh = str(row["text"])
        out[item_id] = _MOCK_VI.get(zh, f"VI {zh}")
    return out


def _chinese_char_count(text: str) -> int:
    """Count CJK unified ideographs (+ fall back to len for mixed strings)."""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk if cjk > 0 else len(text.strip())


def _vietnamese_word_count(text: str) -> int:
    return len([w for w in text.strip().split() if w])


async def auto_test_1_format_structure() -> tuple[bool, dict[str, Any] | None]:
    _header("Auto-Test 1: Format & Structure")
    translator = ContextualTranslator(settings=_settings())
    ok = True
    result: dict[str, Any] | None = None

    with patch.object(translator, "_chat_json", side_effect=_mock_llm_full):
        try:
            result = await translator.translate_step2(DUMMY_INPUT)
        except Exception as exc:  # noqa: BLE001
            _fail(f"translate_step2 raised: {exc}")
            return False, None

    # Assert 1: dict (JSON-shaped result, no markdown crash)
    if not isinstance(result, dict):
        _fail(f"result type is {type(result).__name__}, expected dict")
        ok = False
    else:
        _pass("Kết quả là dict (parse JSON thành công)")

    assert result is not None
    # Assert 2 + 3: keys preserved / vietnamese_text present
    required = {"original_box_coords", "original_text", "vietnamese_text"}
    try:
        # Round-trip JSON proves no non-serializable junk
        json.dumps(result, ensure_ascii=False)
        _pass("JSON serializable (không dính markdown rác)")
    except (TypeError, ValueError) as exc:
        _fail(f"JSON serialize failed: {exc}")
        ok = False

    input_ts = set(DUMMY_INPUT.keys())
    if set(result.keys()) != input_ts:
        _fail(f"timestamp keys lệch: got={sorted(result.keys())} want={sorted(input_ts)}")
        ok = False
    else:
        _pass("Giữ nguyên keys timestamp từ Bước 2")

    hit_count = 0
    for ts, hits in result.items():
        if not isinstance(hits, list):
            _fail(f"{ts}: value không phải list")
            ok = False
            continue
        for i, hit in enumerate(hits):
            hit_count += 1
            missing = required - set(hit.keys())
            if missing:
                _fail(f"{ts}[{i}] thiếu keys {sorted(missing)}")
                ok = False
                continue
            if not isinstance(hit["original_box_coords"], list):
                _fail(f"{ts}[{i}] original_box_coords không phải list")
                ok = False
            if not str(hit["original_text"]).strip():
                _fail(f"{ts}[{i}] original_text rỗng")
                ok = False
            if "vietnamese_text" not in hit:
                _fail(f"{ts}[{i}] thiếu vietnamese_text")
                ok = False

    if hit_count > 0 and ok:
        _pass(f"Mỗi object có original_* + vietnamese_text ({hit_count} hits)")

    if ok:
        _pass("Format & Structure toàn bộ đạt")
    else:
        _fail("Format & Structure không đạt")
    return ok, result


def auto_test_2_failsafe() -> bool:
    _header("Auto-Test 2: Fail-safe Resilience")
    translator = ContextualTranslator(settings=_settings())
    items = ContextualTranslator.assign_ids(DUMMY_INPUT)
    if len(items) < 2:
        _fail("DUMMY_INPUT cần ≥2 items để giả lập thiếu ID")
        return False

    # LLM returns only first id — one missing on purpose
    incomplete = {
        "translations": [
            {
                "id": items[0]["id"],
                "vietnamese_text": _MOCK_VI.get(items[0]["text"], "OK"),
            }
        ]
    }

    try:
        with patch.object(translator, "_chat_json", return_value=incomplete):
            mapped = translator.translate_step2_sync(DUMMY_INPUT)
    except KeyError as exc:
        _fail(f"CRASH KeyError khi map thiếu ID: {exc}")
        return False
    except Exception as exc:  # noqa: BLE001
        _fail(f"CRASH ngoài dự kiến: {type(exc).__name__}: {exc}")
        return False

    flat_vi: list[str] = []
    for hits in mapped.values():
        for hit in hits:
            flat_vi.append(str(hit.get("vietnamese_text") or ""))

    if len(flat_vi) != len(items):
        _fail(f"Số hit sau map={len(flat_vi)} ≠ input={len(items)}")
        return False

    missing_handled = flat_vi.count("...")
    if missing_handled < 1:
        # Also accept keeping original Chinese as safe fallback
        originals = {it["text"] for it in items[1:]}
        if not any(vi in originals for vi in flat_vi):
            _fail("ID thiếu không được gán '...' (và cũng không giữ original)")
            return False
        _pass("ID thiếu được giữ text gốc (fail-safe)")
    else:
        _pass(f"ID thiếu được gán '...' ({missing_handled} chỗ) — không KeyError")

    _pass("Fail-safe Resilience đạt")
    return True


def auto_test_3_vibe_length(result: dict[str, Any] | None) -> bool:
    _header("Auto-Test 3: Vibe & Length Check")
    if not result:
        _fail("Không có kết quả Test 1 để kiểm độ dài")
        return False

    all_ok = True
    checked = 0
    for _ts, hits in result.items():
        for hit in hits:
            zh = str(hit.get("original_text") or "")
            vi = str(hit.get("vietnamese_text") or "")
            if not zh or vi in {"", "..."}:
                continue
            checked += 1
            max_words = _chinese_char_count(zh) + 3
            words = _vietnamese_word_count(vi)
            if words <= max_words:
                _pass(
                    f"Độ dài hoàn hảo — ZH:{_chinese_char_count(zh)} chars → "
                    f"VI:{words} từ (≤{max_words}) | «{vi}»"
                )
            else:
                all_ok = False
                _warn(f"Câu dịch có nguy cơ bị tràn âm thanh: {vi}")

    if checked == 0:
        _fail("Không có câu VI hợp lệ để kiểm")
        return False
    if all_ok:
        _pass("Vibe & Length toàn bộ đạt")
    return all_ok


async def main() -> int:
    print(f"{BOLD}QA Report — ContextualTranslator (Step 3){RESET}")
    print(f"Input timestamps: {list(DUMMY_INPUT.keys())}")

    t1_ok, result = await auto_test_1_format_structure()
    t2_ok = auto_test_2_failsafe()
    t3_ok = auto_test_3_vibe_length(result)

    _header("Summary")
    rows = [
        ("Format & Structure", t1_ok),
        ("Fail-safe Resilience", t2_ok),
        ("Vibe & Length", t3_ok),
    ]
    for name, passed in rows:
        if passed:
            _pass(name)
        else:
            _fail(name)

    overall = t1_ok and t2_ok and t3_ok
    print()
    if overall:
        print(f"{GREEN}{BOLD}ALL QA CHECKS PASSED{RESET}")
        return 0
    print(f"{RED}{BOLD}QA CHECKS FAILED{RESET}")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
