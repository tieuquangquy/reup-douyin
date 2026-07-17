from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import importlib.util
from pathlib import Path
import re
import sys
from typing import Any, Literal

_SHARED_ZERO_SENTINELS_PATH = Path(__file__).resolve().parents[4] / "packages" / "shared" / "src" / "douyin_engagement_zero_sentinels.py"
_SHARED_ZERO_SENTINELS_SPEC = importlib.util.spec_from_file_location(
    "douyin_engagement_zero_sentinels",
    _SHARED_ZERO_SENTINELS_PATH,
)
assert _SHARED_ZERO_SENTINELS_SPEC and _SHARED_ZERO_SENTINELS_SPEC.loader
_SHARED_ZERO_SENTINELS = importlib.util.module_from_spec(_SHARED_ZERO_SENTINELS_SPEC)
sys.modules[_SHARED_ZERO_SENTINELS_SPEC.name] = _SHARED_ZERO_SENTINELS
_SHARED_ZERO_SENTINELS_SPEC.loader.exec_module(_SHARED_ZERO_SENTINELS)
normalize_douyin_engagement_count = _SHARED_ZERO_SENTINELS.normalize_douyin_engagement_count
parse_douyin_engagement_text = _SHARED_ZERO_SENTINELS.parse_douyin_engagement_text

ParseConfidence = Literal["high", "medium", "low", "none"]
PostedSource = Literal[
    "network_json",
    "detail_hydrate",
    "dom_detail_modal",
    "dom_text",
    "dom_snapshot",
    "existing_canonical",
    "missing",
    "fallback_none",
    "modal_author_row",
    "modal_author_row_profile_link",
    "direct_publish_time",
    "embedded_aweme_json",
    "profile_card",
]


@dataclass(frozen=True)
class NormalizedDuration:
    duration_text_raw: str | None
    duration_text: str | None
    duration_seconds: float | None
    duration_parse_confidence: ParseConfidence


@dataclass(frozen=True)
class NormalizedPosted:
    posted_text_raw: str | None
    posted_text: str | None
    posted_display: str | None
    posted_at: datetime | None
    posted_source: PostedSource | None
    posted_parse_confidence: ParseConfidence


@dataclass(frozen=True)
class NormalizedEstimatedViews:
    estimated_views_text_raw: str | None
    estimated_views_display: str | None
    estimated_views_min: int | None
    estimated_views_max: int | None
    estimated_views_mid: int | None
    estimated_views_parse_confidence: ParseConfidence


@dataclass(frozen=True)
class EngagementMetrics:
    engagement_score: int | None
    engagement_rate: float | None
    engagement_rate_basis: Literal["estimated_views_mid", "view_count", "none"]


@dataclass(frozen=True)
class DataQualityFlags:
    has_thumbnail: bool
    has_posted: bool
    has_duration: bool
    has_views: bool
    has_likes: bool
    has_comments: bool
    has_shares: bool
    has_all_core_metadata: bool
    missing_metadata_fields: list[str]


def normalize_douyin_duration(*, raw_text: Any = None, seconds: Any = None) -> NormalizedDuration:
    duration_text_raw = _string_or_none(raw_text)
    parsed_seconds = _float_or_none(seconds)
    confidence: ParseConfidence = "none"

    if parsed_seconds is not None and parsed_seconds >= 0:
        confidence = "high"
    elif duration_text_raw:
        parsed_seconds = _duration_seconds_from_text(duration_text_raw)
        confidence = "high" if parsed_seconds is not None else "none"

    duration_text = _format_duration(parsed_seconds) if parsed_seconds is not None else duration_text_raw
    return NormalizedDuration(
        duration_text_raw=duration_text_raw,
        duration_text=duration_text,
        duration_seconds=parsed_seconds,
        duration_parse_confidence=confidence,
    )


def normalize_douyin_posted(
    *,
    posted_at: datetime | None,
    posted_text: str | None,
    posted_text_raw: str | None,
    posted_display: str | None,
    posted_source: str | None,
) -> NormalizedPosted:
    normalized_raw = _string_or_none(posted_text_raw) or _string_or_none(posted_text)
    display = _string_or_none(posted_display)
    normalized_text = display or _string_or_none(posted_text) or normalized_raw
    parsed_source = posted_source if posted_source in _POSTED_SOURCES else None
    confidence: ParseConfidence
    if posted_at is not None and display:
        confidence = "high"
    elif posted_at is not None or display:
        confidence = "medium"
    elif normalized_raw:
        confidence = "low"
    else:
        confidence = "none"
    return NormalizedPosted(
        posted_text_raw=normalized_raw,
        posted_text=normalized_text,
        posted_display=display,
        posted_at=posted_at,
        posted_source=parsed_source,  # type: ignore[arg-type]
        posted_parse_confidence=confidence,
    )


def normalize_douyin_estimated_views(*values: Any) -> NormalizedEstimatedViews:
    raw = next((_string_or_none(value) for value in values if _string_or_none(value)), None)
    if not raw:
        numeric = next((_non_negative_int(value) for value in values if _non_negative_int(value) is not None), None)
        if numeric is None:
            return NormalizedEstimatedViews(None, None, None, None, None, "none")
        display = _format_compact_count(numeric)
        return NormalizedEstimatedViews(display, display, numeric, numeric, numeric, "high")

    text = _normalize_range_text(raw)
    parts = [part.strip() for part in re.split(r"\s*(?:-|–|—|~|至|到)\s*", text) if part.strip()]
    if len(parts) >= 2:
        low = normalize_douyin_count(parts[0])
        high = normalize_douyin_count(parts[1])
        if low is not None and high is not None:
            minimum, maximum = sorted((low, high))
            return NormalizedEstimatedViews(raw, raw, minimum, maximum, round((minimum + maximum) / 2), "high")
    single = normalize_douyin_count(text)
    if single is not None:
        return NormalizedEstimatedViews(raw, raw, single, single, single, "high")
    return NormalizedEstimatedViews(raw, raw, None, None, None, "none")


def normalize_douyin_count(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        parsed = int(float(value))
        return parsed if parsed >= 0 else None
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "").replace("，", "")
    if not text:
        return None
    text = re.sub(r"(?:次播放|播放|views?|likes?|comments?|shares?|赞|评论|分享|收藏)", "", text, flags=re.IGNORECASE).strip()
    multiplier = 1.0
    lowered = text.lower()
    if lowered.endswith("k"):
        multiplier = 1_000.0
        text = text[:-1]
    elif lowered.endswith("m"):
        multiplier = 1_000_000.0
        text = text[:-1]
    elif lowered.endswith("b"):
        multiplier = 1_000_000_000.0
        text = text[:-1]
    elif text.endswith("万"):
        multiplier = 10_000.0
        text = text[:-1]
    elif text.endswith("亿"):
        multiplier = 100_000_000.0
        text = text[:-1]
    try:
        parsed = int(round(float(text.strip()) * multiplier))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def calculate_engagement(
    *,
    like_count: int | None,
    comment_count: int | None,
    share_count: int | None,
    favorite_count: int | None,
    estimated_views_mid: int | None,
    view_count: int | None,
) -> EngagementMetrics:
    score = sum(value or 0 for value in (like_count, comment_count, share_count, favorite_count))
    basis = estimated_views_mid if estimated_views_mid and estimated_views_mid > 0 else view_count if view_count and view_count > 0 else None
    if score <= 0:
        score_value = None
    else:
        score_value = score
    if basis is None or score <= 0:
        return EngagementMetrics(score_value, None, "none")
    rate_basis: Literal["estimated_views_mid", "view_count", "none"] = "estimated_views_mid" if estimated_views_mid and estimated_views_mid > 0 else "view_count"
    return EngagementMetrics(score_value, round(score / basis, 6), rate_basis)


def build_data_quality_flags(
    *,
    thumbnail_url: str | None,
    preview_url: str | None,
    posted_at: datetime | None,
    posted_text: str | None,
    duration_seconds: float | None,
    duration_text: str | None,
    estimated_views_mid: int | None,
    view_count: int | None,
    view_count_text: str | None,
    like_count: int | None,
    like_count_text: str | None,
    comment_count: int | None,
    comment_count_text: str | None,
    share_count: int | None,
    share_count_text: str | None = None,
) -> DataQualityFlags:
    has_thumbnail = bool(thumbnail_url or preview_url)
    has_posted = posted_at is not None or bool(_string_or_none(posted_text))
    has_duration = duration_seconds is not None or bool(_string_or_none(duration_text))
    has_views = estimated_views_mid is not None or view_count is not None or bool(_string_or_none(view_count_text))
    has_likes = like_count is not None or bool(_string_or_none(like_count_text))
    has_comments = comment_count is not None or bool(_string_or_none(comment_count_text))
    has_shares = share_count is not None or bool(_string_or_none(share_count_text))
    checks = {
        "thumbnail": has_thumbnail,
        "posted": has_posted,
        "duration": has_duration,
        "views": has_views,
        "likes": has_likes,
        "comments": has_comments,
        "shares": has_shares,
    }
    missing = [key for key, present in checks.items() if not present]
    return DataQualityFlags(
        has_thumbnail=has_thumbnail,
        has_posted=has_posted,
        has_duration=has_duration,
        has_views=has_views,
        has_likes=has_likes,
        has_comments=has_comments,
        has_shares=has_shares,
        has_all_core_metadata=not missing,
        missing_metadata_fields=missing,
    )


def _duration_seconds_from_text(value: str) -> float | None:
    text = value.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        parsed = float(text)
        return parsed if parsed >= 0 else None
    match = re.fullmatch(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    if minutes > 59 or seconds > 59:
        return None
    return float(hours * 3600 + minutes * 60 + seconds)


def _format_duration(value: float | None) -> str | None:
    if value is None:
        return None
    total = int(round(value))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _normalize_range_text(value: str) -> str:
    return re.sub(r"\s+", "", value.strip())


def _format_compact_count(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:g}M"
    if value >= 1_000:
        return f"{value / 1_000:g}K"
    return str(value)


def _string_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _non_negative_int(value: Any) -> int | None:
    parsed = normalize_douyin_count(value)
    return parsed if parsed is not None and parsed >= 0 else None


_POSTED_SOURCES = {
    "network_json",
    "detail_hydrate",
    "dom_detail_modal",
    "dom_text",
    "dom_snapshot",
    "existing_canonical",
    "missing",
    "fallback_none",
    "modal_author_row",
    "modal_author_row_profile_link",
    "direct_publish_time",
    "embedded_aweme_json",
    "profile_card",
}
