"""Script filters for OCR boxes (Chinese vs Latin/VI)."""

from __future__ import annotations

import re

# Han Unified ideographs — enough to gate ZH UI labels vs Latin/VI hard-subs.
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def contains_cjk(text: str) -> bool:
    """True when ``text`` includes at least one Chinese Han character."""
    return bool(_CJK_RE.search(text or ""))
