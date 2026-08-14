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
from src.downloaders.douyin_video_resolver import media_quality_sort_key
from src.downloaders.download_quality_policy import DownloadQualityProfile, WatermarkAuthority
from src.downloaders.download_staging import download_staging_root, staging_path
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
    codec: str | None = None
    fps: float = 0.0
    hdr: bool = False

    @property
    def format_label(self) -> str:
        parts = [self.source]
        if self.height:
            parts.append(f"{self.height}p")
        if self.bitrate:
            parts.append(f"br{self.bitrate}")
        if self.gear_name:
            parts.append(self.gear_name)
        if self.codec:
            parts.append(self.codec)
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
                    codec=_codec_from_node(download_addr),
                    fps=_as_float(download_addr.get("fps")),
                    hdr=_as_bool(download_addr.get("hdr") or download_addr.get("is_hdr")),
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
                        codec=_codec_from_node(item) or _codec_from_node(play_addr),
                        fps=_as_float(item.get("fps") or item.get("frame_rate")),
                        hdr=_as_bool(item.get("hdr") or item.get("is_hdr")),
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
                    codec=_codec_from_node(play_addr),
                    fps=_as_float(play_addr.get("fps")),
                    hdr=_as_bool(play_addr.get("hdr") or play_addr.get("is_hdr")),
                )
            )

    # Dedupe by URL, keep richer quality metadata.
    best: dict[str, RankedPlayUrl] = {}
    for item in ranked:
        current = best.get(item.url)
        if current is None or _candidate_sort_key(item) > _candidate_sort_key(current):
            best[item.url] = item
    return sorted(best.values(), key=_candidate_sort_key, reverse=True)


def _candidate_sort_key(
    item: RankedPlayUrl,
    *,
    quality_profile: str = DownloadQualityProfile.BALANCED_PROCESSING.value,
    target_long_edge: int = 1920,
) -> tuple[int, int, int, int, int, int, int]:
    # Keep browser candidate ordering identical to the cross-resolver policy.
    source_bonus = {"bit_rate": 2, "play_addr": 1, "download_addr": 0}.get(item.source, 0)
    return media_quality_sort_key(
        watermark_free=item.watermark_free,
        width=item.width,
        height=item.height,
        codec=item.codec,
        bitrate=item.bitrate,
        hdr=item.hdr,
        source_bonus=source_bonus,
        target_long_edge=target_long_edge,
        source_master=str(quality_profile).strip().lower() == DownloadQualityProfile.SOURCE_MASTER.value,
    )


def select_preferred_play_candidate(
    urls: list[RankedPlayUrl],
    *,
    quality_profile: str = DownloadQualityProfile.BALANCED_PROCESSING.value,
    target_long_edge: int = 1920,
) -> RankedPlayUrl | None:
    if not urls:
        return None
    return max(
        urls,
        key=lambda item: _candidate_sort_key(
            item,
            quality_profile=quality_profile,
            target_long_edge=target_long_edge,
        ),
    )


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


def _as_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number > 0 else 0.0


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "hdr"}


def _codec_from_node(node: Any) -> str | None:
    if not isinstance(node, dict):
        return None
    if node.get("is_bytevc1") or node.get("is_h265") or node.get("is_hevc"):
        return "hevc"
    raw = node.get("codec") or node.get("codec_name") or node.get("video_codec")
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    if any(token in value for token in ("h264", "avc")):
        return "h264"
    if any(token in value for token in ("h265", "hevc", "bytevc")):
        return "hevc"
    if "av1" in value:
        return "av1"
    return value or None


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
    if isinstance(payload.get("video"), dict):
        return payload
    return None


def playwright_download_staging_root() -> Path:
    return download_staging_root()


def staging_path_for_aweme(
    aweme_id: str,
    *,
    workspace_id: object | None = None,
    account_connection_id: object | None = None,
    transfer_id: object | None = None,
) -> Path:
    return staging_path(
        aweme_id=aweme_id,
        workspace_id=workspace_id,
        account_connection_id=account_connection_id,
        transfer_id=transfer_id,
        extension="mp4",
    )


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

    def discover(self, request: DouyinVideoResolveRequest) -> list[ResolvedDouyinVideo]:
        from src.services.douyin_browser_context_registry import douyin_browser_context_registry

        candidates = douyin_browser_context_registry.discover_aweme_video(
            aweme_id=request.aweme_id,
            page_url=request.page_url,
            account_connection_id=request.account_connection_id,
            timeout_ms=min(
                self.timeout_ms,
                max(1_000, int(request.timeout_seconds or self.timeout_ms / 1000) * 1_000),
            ),
            quality_profile=request.quality_profile,
            target_long_edge=request.target_long_edge,
        )
        return [
            ResolvedDouyinVideo(
                content=None,
                mime_type="video/mp4",
                filename=None,
                resolver_name="playwright_discovery",
                format_id=item.format_label,
                height=item.height,
                width=item.width,
                bitrate=item.bitrate,
                codec=item.codec,
                fps=item.fps or None,
                hdr=item.hdr,
                watermark_free=item.watermark_free,
                watermark_authority=(
                    WatermarkAuthority.VERIFIED_PLAYBACK_PROVENANCE.value
                    if item.watermark_free
                    else WatermarkAuthority.EXPLICIT_WATERMARKED.value
                ),
                candidate_url=item.url,
            )
            for item in candidates
        ]
    def resolve(self, request: DouyinVideoResolveRequest) -> ResolvedDouyinVideo:
        from src.services.douyin_browser_context_registry import douyin_browser_context_registry

        account_id = getattr(request, "account_connection_id", None)
        staging = staging_path_for_aweme(
            request.aweme_id,
            workspace_id=request.workspace_id,
            account_connection_id=request.account_connection_id,
            transfer_id=request.transfer_id,
        )
        request_timeout_ms = (
            max(1_000, int(request.timeout_seconds) * 1_000)
            if request.timeout_seconds is not None
            else self.timeout_ms
        )
        downloaded = douyin_browser_context_registry.download_aweme_video(
            aweme_id=request.aweme_id,
            page_url=request.page_url,
            account_connection_id=account_id,
            timeout_ms=min(self.timeout_ms, request_timeout_ms),
            destination_path=staging,
            on_progress=request.on_progress,
            quality_profile=request.quality_profile,
            target_long_edge=request.target_long_edge,
            preferred_candidate_url=request.preferred_candidate_url,
            preferred_format_id=request.preferred_format_id,
        )
        format_id = downloaded.format_id
        watermark_free = downloaded.watermark_free
        resolved_path = Path(downloaded.local_path).resolve() if downloaded.local_path else staging
        if not resolved_path.is_file() or resolved_path.stat().st_size <= 0:
            if downloaded.content:
                temp = staging.with_suffix(staging.suffix + ".part")
                temp.write_bytes(downloaded.content)
                temp.replace(staging)
                resolved_path = staging
            else:
                raise DownloadError(DownloadErrorCode.VALIDATION_FAILED, "Playwright Douyin download returned empty content")
        height = downloaded.height if isinstance(downloaded.height, int) and downloaded.height > 0 else None
        if height is None:
            height = parse_height_from_format_label(format_id)
        return ResolvedDouyinVideo(
            content=None,
            mime_type="video/mp4",
            filename=f"{request.aweme_id}.mp4",
            resolver_name="playwright_browser",
            format_id=format_id,
            height=height,
            width=downloaded.width,
            bitrate=downloaded.bitrate,
            codec=downloaded.codec,
            fps=downloaded.fps,
            hdr=downloaded.hdr,
            watermark_free=watermark_free,
            watermark_authority=(
                WatermarkAuthority.VERIFIED_PLAYBACK_PROVENANCE.value
                if watermark_free
                else WatermarkAuthority.EXPLICIT_WATERMARKED.value
            ),
            author_handle=downloaded.author_handle,
            author_display_name=downloaded.author_display_name,
            local_path=str(resolved_path),
            size_bytes=resolved_path.stat().st_size,
            cleanup_local_path=True,
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
