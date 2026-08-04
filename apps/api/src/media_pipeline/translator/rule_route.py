"""Deterministic ZH→VI rules for numeric / unit labels (no LLM)."""

from __future__ import annotations

import re

from src.media_pipeline.translator.normalize import canonical_zh

_GRAMS_RE = re.compile(r"^(\d{1,4})克$")
_KCAL_RE = re.compile(r"^(\d{1,4})千卡$")
_PERCENT_RE = re.compile(r"^(\d{1,3})%$")


def rule_translate_zh(text: str) -> str | None:
    """
    Return Vietnamese for pure unit labels, else ``None`` (needs LLM / memory).

    Examples: ``52克`` → ``52g``, ``614千卡`` → ``614 kcal``.
    """
    zh = canonical_zh(text)
    if not zh:
        return None
    m = _GRAMS_RE.match(zh)
    if m:
        return f"{m.group(1)}g"
    m = _KCAL_RE.match(zh)
    if m:
        return f"{m.group(1)} kcal"
    m = _PERCENT_RE.match(zh)
    if m:
        return f"{m.group(1)}%"
    return None
