from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

DouyinEngagementMetric = Literal["comment", "share", "like", "view"]

COMMENT_ZERO_SENTINELS: tuple[str, ...] = (
    "抢首评",
    "快来抢首评",
    "抢沙发",
)

SHARE_ZERO_SENTINEL_PATTERN = re.compile(r"^分享$")


@dataclass(frozen=True)
class DouyinEngagementParseResult:
    kind: Literal["numeric", "zero_sentinel", "missing"]
    value: int | None = None
    raw_text: str | None = None
    sentinel: str | None = None


def _compact_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.strip())


def parse_douyin_engagement_text(
    metric: DouyinEngagementMetric,
    raw_text: Any,
    *,
    share_icon_context: bool = False,
) -> DouyinEngagementParseResult:
    text = _compact_text(raw_text)
    if not text:
        return DouyinEngagementParseResult(kind="missing")

    if metric == "comment":
        for sentinel in COMMENT_ZERO_SENTINELS:
            if text == sentinel or sentinel in text:
                return DouyinEngagementParseResult(kind="zero_sentinel", value=0, raw_text=sentinel, sentinel=sentinel)
        return DouyinEngagementParseResult(kind="missing")

    if metric == "share":
        if share_icon_context and SHARE_ZERO_SENTINEL_PATTERN.fullmatch(text):
            return DouyinEngagementParseResult(kind="zero_sentinel", value=0, raw_text=text, sentinel=text)
        return DouyinEngagementParseResult(kind="missing")

    return DouyinEngagementParseResult(kind="missing")


def normalize_douyin_engagement_count(
    metric: DouyinEngagementMetric,
    value: Any = None,
    text: Any = None,
    *,
    share_icon_context: bool = False,
) -> int | None:
    if value is not None and value != "":
        if isinstance(value, (int, float)):
            parsed = int(float(value))
            return parsed if parsed >= 0 else None
    compact = _compact_text(text)
    if not compact:
        return None
    parsed = parse_douyin_engagement_text(metric, compact, share_icon_context=share_icon_context)
    if parsed.kind == "zero_sentinel":
        return 0
    return None
