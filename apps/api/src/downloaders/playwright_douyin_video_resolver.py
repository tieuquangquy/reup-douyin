from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from uuid import UUID

from src.core.settings import get_settings
from src.downloaders.douyin_video_resolver import DouyinVideoResolveRequest, ResolvedDouyinVideo
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.source_video_filename import parse_height_from_format_label

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class RankedPlayUrl:
    url: str
    source: str
    height: int = 0
    width: int = 0
    bitrate: int = 0
    watermark_free: bool = False
    gear_name: str | None = None

    @property
    def format_label(self) -> str:
        parts = [self.source]
        if self.height:
            parts.append(f"{self.height}p")
        if self.bitrate:
            parts.append(f"br{self.bitrate}")
        if self.gear_name:
            parts.append(self.gear_name)
        return "|".join(parts)


def _as_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def classify_douyin_cdn_watermark_free(url: str, *, source: str) -> bool:
    """Classify Douyin CDN URLs: download_addr is usually logo; bit_rate/play_addr usually clean.

    Explicit URL markers always win (e.g. /mps/logo/, playwm, watermark=0/1).
    """
    normalized = unquote(url or "").lower()
    if any(token in normalized for token in ("/mps/logo/", "playwm", "watermark=1", "watermark%3d1")):
        return False
    if "watermark=0" in normalized or "watermark%3d0" in normalized:
        return True
    if source == "download_addr":
        # Official "download" CDN on Douyin is typically platform-logo burned-in.
        return False
    # bit_rate / play_addr playback streams are the common no-logo HQ sources.
    return source in {"bit_rate", "play_addr"}


def extract_play_urls_from_aweme_payload(payload: dict[str, Any]) -> list[RankedPlayUrl]:
    """Collect CDN candidates with height/bitrate; watermark-free streams preferred later."""
    detail = _find_aweme_detail(payload)
    if not isinstance(detail, dict):
        return []
    video = detail.get("video")
    if not isinstance(video, dict):
        return []

    ranked: list[RankedPlayUrl] = []
    video_height = _as_int(video.get("height"))
    video_width = _as_int(video.get("width"))

    download_addr = video.get("download_addr")
    if isinstance(download_addr, dict):
        height = _as_int(download_addr.get("height")) or video_height
        width = _as_int(download_addr.get("width")) or video_width
        bitrate = _as_int(download_addr.get("bit_rate") or download_addr.get("data_size"))
        for url in _url_list(download_addr):
            ranked.append(
                RankedPlayUrl(
                    url=url,
                    source="download_addr",
                    height=height,
                    width=width,
                    bitrate=bitrate,
                    watermark_free=classify_douyin_cdn_watermark_free(url, source="download_addr"),
                )
            )

    bit_rate = video.get("bit_rate")
    if isinstance(bit_rate, list):
        for item in bit_rate:
            if not isinstance(item, dict):
                continue
            play_addr = item.get("play_addr")
            if not isinstance(play_addr, dict):
                continue
            height = _as_int(play_addr.get("height") or item.get("height")) or video_height
            width = _as_int(play_addr.get("width") or item.get("width")) or video_width
            bitrate = _as_int(item.get("bit_rate") or play_addr.get("bit_rate") or play_addr.get("data_size"))
            gear_name = item.get("gear_name") if isinstance(item.get("gear_name"), str) else None
            for url in _url_list(play_addr):
                ranked.append(
                    RankedPlayUrl(
                        url=url,
                        source="bit_rate",
                        height=height,
                        width=width,
                        bitrate=bitrate,
                        watermark_free=classify_douyin_cdn_watermark_free(url, source="bit_rate"),
                        gear_name=gear_name,
                    )
                )

    play_addr = video.get("play_addr")
    if isinstance(play_addr, dict):
        height = _as_int(play_addr.get("height")) or video_height
        width = _as_int(play_addr.get("width")) or video_width
        bitrate = _as_int(play_addr.get("bit_rate") or play_addr.get("data_size"))
        for url in _url_list(play_addr):
            ranked.append(
                RankedPlayUrl(
                    url=url,
                    source="play_addr",
                    height=height,
                    width=width,
                    bitrate=bitrate,
                    watermark_free=classify_douyin_cdn_watermark_free(url, source="play_addr"),
                )
            )

    # Dedupe by URL, keep richer quality metadata.
    best: dict[str, RankedPlayUrl] = {}
    for item in ranked:
        current = best.get(item.url)
        if current is None or _candidate_sort_key(item) > _candidate_sort_key(current):
            best[item.url] = item
    return sorted(best.values(), key=_candidate_sort_key, reverse=True)


def _candidate_sort_key(item: RankedPlayUrl) -> tuple[int, int, int, int]:
    # Prefer no-logo, then max height, then max bitrate, then play/bit_rate over download_addr.
    source_bonus = {"bit_rate": 2, "play_addr": 1, "download_addr": 0}.get(item.source, 0)
    return (1 if item.watermark_free else 0, item.height, item.bitrate, source_bonus)


def select_preferred_play_candidate(urls: list[RankedPlayUrl]) -> RankedPlayUrl | None:
    if not urls:
        return None
    return max(urls, key=_candidate_sort_key)


def select_preferred_play_url(urls: list[RankedPlayUrl]) -> str | None:
    candidate = select_preferred_play_candidate(urls)
    return candidate.url if candidate else None


def _url_list(addr: dict[str, Any]) -> list[str]:
    raw = addr.get("url_list")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.startswith("http"):
            out.append(item)
    return out


def _find_aweme_detail(payload: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(payload.get("aweme_detail"), dict):
        return payload["aweme_detail"]
    if isinstance(payload.get("aweme_details"), list) and payload["aweme_details"]:
        first = payload["aweme_details"][0]
        if isinstance(first, dict):
            return first
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("aweme_detail"), dict):
        return data["aweme_detail"]
    if isinstance(payload.get("aweme"), dict):
        return payload["aweme"]
    return None


def playwright_download_staging_root() -> Path:
    settings = get_settings()
    override = getattr(settings, "douyin_playwright_download_staging_dir", None)
    if isinstance(override, str) and override.strip():
        return Path(override).expanduser().resolve()
    return (_REPO_ROOT / ".douyin_profiles" / "download_staging").resolve()


def staging_path_for_aweme(aweme_id: str) -> Path:
    safe = re.sub(r"[^0-9A-Za-z_-]", "", aweme_id) or "unknown"
    root = playwright_download_staging_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{safe}.mp4"


class PlaywrightDouyinVideoResolver:
    """Resolve/download Douyin video through the live Playwright browser context (API process)."""

    def __init__(self, *, timeout_ms: int | None = None):
        settings = get_settings()
        self.timeout_ms = timeout_ms or int(getattr(settings, "douyin_playwright_download_timeout_ms", 90_000))

    def is_available(self) -> bool:
        settings = get_settings()
        if not getattr(settings, "douyin_playwright_download_enabled", True):
            return False
        try:
            from src.services.douyin_browser_context_registry import douyin_browser_context_registry

            return douyin_browser_context_registry.has_any_active_context()
        except Exception:
            return False

    def resolve(self, request: DouyinVideoResolveRequest) -> ResolvedDouyinVideo:
        from src.services.douyin_browser_context_registry import douyin_browser_context_registry

        account_id = getattr(request, "account_connection_id", None)
        downloaded = douyin_browser_context_registry.download_aweme_video(
            aweme_id=request.aweme_id,
            page_url=request.page_url,
            account_connection_id=account_id,
            timeout_ms=self.timeout_ms,
        )
        content = downloaded.content
        format_id = downloaded.format_id
        watermark_free = downloaded.watermark_free
        if not content:
            raise DownloadError(DownloadErrorCode.VALIDATION_FAILED, "Playwright Douyin download returned empty content")
        staging = staging_path_for_aweme(request.aweme_id)
        staging.write_bytes(content)
        height = downloaded.height if isinstance(downloaded.height, int) and downloaded.height > 0 else None
        if height is None:
            height = parse_height_from_format_label(format_id)
        return ResolvedDouyinVideo(
            content=content,
            mime_type="video/mp4",
            filename=f"{request.aweme_id}.mp4",
            resolver_name="playwright_browser",
            format_id=format_id,
            height=height,
            watermark_free=watermark_free,
            author_handle=downloaded.author_handle,
            author_display_name=downloaded.author_display_name,
        )


def parse_render_data_aweme(html: str) -> dict[str, Any] | None:
    match = re.search(r'id="RENDER_DATA"[^>]*>([^<]+)</script>', html)
    if not match:
        return None
    try:
        decoded = unquote(match.group(1))
        data = json.loads(decoded)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if isinstance(data, dict):
        return data
    return None


def extract_author_identity_from_aweme_payloads(payloads: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """Return (unique_id/handle, nickname) from aweme detail payloads when available."""
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        candidates: list[dict[str, Any]] = []
        for key in ("aweme_detail", "aweme", "item"):
            node = payload.get(key)
            if isinstance(node, dict):
                candidates.append(node)
        candidates.append(payload)
        for node in candidates:
            author = node.get("author")
            if not isinstance(author, dict):
                continue
            handle = author.get("unique_id") or author.get("short_id") or author.get("uniqueId")
            display = author.get("nickname") or author.get("nick_name") or author.get("nickName")
            handle_s = str(handle).strip().lstrip("@") if handle else None
            display_s = str(display).strip() if display else None
            if handle_s or display_s:
                return handle_s or None, display_s or None
    return None, None


def collect_aweme_payloads_from_render_data(render_data: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "aweme_detail" in node or ("video" in node and ("play_addr" in (node.get("video") or {}) if isinstance(node.get("video"), dict) else False)):
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(render_data)
    return found
