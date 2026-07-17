"""Lightweight zh→vi machine translation helpers (literal path, no API key required)."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def mymemory_zh_to_vi(
    source_text: str,
    *,
    timeout_seconds: float = 20.0,
    opener: object | None = None,
) -> str:
    """
    Free MyMemory API for literal Chinese→Vietnamese.

    Used as fail-closed recovery when chat LLMs leave Han characters in the VI draft.
    """
    source = (source_text or "").strip()
    if not source:
        raise RuntimeError("mymemory_empty_source")
    # MyMemory GET URL length budget — truncate long untimed beats safely.
    query = source[:450]
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(
        {"q": query, "langpair": "zh-CN|vi"}
    )
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(request, timeout=timeout_seconds) as response:  # type: ignore[arg-type]
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"mymemory_http_{exc.code}:{detail[:160]}") from exc
    except Exception as exc:
        raise RuntimeError(f"mymemory_unavailable:{exc}") from exc

    data = payload.get("responseData") if isinstance(payload, dict) else None
    text = str((data or {}).get("translatedText") or "").strip()
    if not text:
        raise RuntimeError("mymemory_empty_response")
    # Ignore MYIDMEMORY placeholders / quota notices containing the query echoed back.
    if contains_cjk(text):
        raise RuntimeError("mymemory_still_contains_cjk")
    if text.lower().startswith("query length limit") or "myemory" in text.lower():
        raise RuntimeError(f"mymemory_rejected:{text[:120]}")
    return text
