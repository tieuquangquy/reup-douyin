from __future__ import annotations

import re
import unicodedata
from datetime import datetime

_WINDOWS_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTI_DASH = re.compile(r"-{2,}")
_NON_TOKEN = re.compile(r"[^0-9A-Za-z_\u4e00-\u9fff-]+")
_HEIGHT_TOKEN = re.compile(r"(?<![0-9])(\d{3,4})p(?![0-9A-Za-z])", re.IGNORECASE)


def parse_height_from_format_label(value: str | None) -> int | None:
    """Extract height from labels like play_addr|1080p|br123 when resolver height is missing."""
    if not value:
        return None
    match = _HEIGHT_TOKEN.search(str(value))
    if not match:
        return None
    try:
        height = int(match.group(1))
    except ValueError:
        return None
    return height if height > 0 else None


def sanitize_filename_token(value: str | None, *, max_len: int = 40) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    normalized = unicodedata.normalize("NFKC", raw)
    cleaned = _WINDOWS_UNSAFE.sub("", normalized)
    cleaned = cleaned.replace(" ", "-")
    cleaned = _NON_TOKEN.sub("-", cleaned)
    cleaned = _MULTI_DASH.sub("-", cleaned).strip("-._ ")
    if not cleaned:
        return ""
    return cleaned[:max_len].rstrip("-._")


def caption_slug_for_filename(caption: str | None, *, max_len: int = 40) -> str:
    slug = sanitize_filename_token(caption, max_len=max_len)
    return slug or "nocap"


def build_source_video_raw_filename(
    *,
    aweme_id: str,
    caption: str | None,
    watermark_free: bool | None,
    posted_at: datetime | None = None,
    height: int | None = None,
    fallback_date: datetime | None = None,
    extension: str = "mp4",
    author: str | None = None,  # deprecated: kept for call-site compat; ignored (profile folder owns author)
) -> str:
    """Operator name: {date}__{aweme_id}__{caption_slug}__{height}p__{nl|wm}.ext

    Author is intentionally omitted — videos are grouped under the profile folder.
    """
    _ = author
    day = posted_at or fallback_date
    date_token = day.strftime("%Y-%m-%d") if day is not None else "undated"
    safe_aweme = sanitize_filename_token(aweme_id, max_len=64) or "unknown"
    safe_caption = caption_slug_for_filename(caption, max_len=40)
    height_token = f"{int(height)}p" if isinstance(height, int) and height > 0 else "unkp"
    tag = "nl" if watermark_free is True else "wm"
    ext = (extension or "mp4").lstrip(".").lower() or "mp4"
    name = f"{date_token}__{safe_aweme}__{safe_caption}__{height_token}__{tag}.{ext}"
    if len(name) > 180:
        overflow = len(name) - 180
        keep = max(8, len(safe_caption) - overflow)
        safe_caption = safe_caption[:keep].rstrip("-._") or "nocap"
        name = f"{date_token}__{safe_aweme}__{safe_caption}__{height_token}__{tag}.{ext}"
    return name
