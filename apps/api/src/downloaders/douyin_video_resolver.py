from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.downloaders.download_quality_policy import DownloadQualityProfile


@dataclass(frozen=True)
class DouyinVideoResolveRequest:
    aweme_id: str
    page_url: str | None
    session_cookie: str | None
    user_agent: str | None
    proxy_url: str | None = None
    playwright_cookies: tuple[dict, ...] | None = None
    cookie_source: str | None = None
    account_connection_id: object | None = None
    workspace_id: object | None = None
    transfer_id: object | None = None
    on_progress: Callable[[int, int | None], None] | None = None
    timeout_seconds: int | None = None
    quality_profile: str = DownloadQualityProfile.BALANCED_PROCESSING.value
    target_long_edge: int = 1920
    preferred_format_id: str | None = None
    preferred_candidate_url: str | None = None


@dataclass(frozen=True)
class ResolvedDouyinVideo:
    content: bytes | None
    mime_type: str | None
    filename: str | None
    resolver_name: str
    format_id: str | None = None
    height: int | None = None
    width: int | None = None
    bitrate: int | None = None
    codec: str | None = None
    fps: float | None = None
    hdr: bool | None = None
    watermark_free: bool | None = None
    watermark_authority: str | None = None
    author_handle: str | None = None
    author_display_name: str | None = None
    local_path: str | None = None
    size_bytes: int | None = None
    cleanup_local_path: bool = False
    # In-memory discovery hint only. Never persist this signed URL in asset metadata.
    candidate_url: str | None = None


class DouyinVideoResolverProtocol:
    """Optional resolver surface used by discovery-first orchestration."""

    def discover(self, request: DouyinVideoResolveRequest) -> list[ResolvedDouyinVideo]:
        raise NotImplementedError


def video_long_edge(*, width: int | None, height: int | None) -> int:
    """Return the display long edge without assuming portrait metadata order."""
    return max(int(width or 0), int(height or 0))


def media_quality_sort_key(
    *,
    watermark_free: bool | None,
    width: int | None,
    height: int | None,
    codec: str | None,
    bitrate: int | None,
    hdr: bool | None,
    source_bonus: int = 0,
    target_long_edge: int = 1920,
    source_master: bool = False,
) -> tuple[int, int, int, int, int, int, int]:
    """Shared quality policy for browser and yt-dlp candidates.

    Clean provenance and render-compatible H.264 intentionally outrank a larger
    HEVC stream: the latter is slower to decode/encode and frequently unavailable
    to the local renderer. The 1920 long-edge band is the preferred ceiling.
    """
    normalized_codec = (codec or "").strip().lower()
    codec_score = (
        2
        if normalized_codec in {"h264", "avc", "avc1", "h.264"}
        else 0
        if normalized_codec in {"hevc", "h265", "h.265", "bytevc1", "av1", "av01"}
        else 1
    )
    long_edge = video_long_edge(width=width, height=height)
    target_long_edge = max(1, int(target_long_edge))
    in_target_band = 2 if 0 < long_edge <= target_long_edge else 1 if long_edge > target_long_edge else 0
    pixels = max(0, int(width or 0)) * max(0, int(height or 0))
    # Balanced processing prefers the renderer's target band. Source-master
    # keeps the highest clean source instead of penalising larger media.
    pixel_score = pixels if source_master or long_edge <= target_long_edge else -pixels
    band_score = long_edge if source_master else in_target_band
    return (
        1 if watermark_free is True else 0,
        band_score,
        codec_score,
        pixel_score,
        int(source_bonus or 0),
        max(0, int(bitrate or 0)),
        0 if hdr is True else 1,
    )


def is_preferred_download_quality(
    video: ResolvedDouyinVideo,
    *,
    target_long_edge: int = 1920,
    quality_profile: str = DownloadQualityProfile.BALANCED_PROCESSING.value,
) -> bool:
    """Whether a cheap fast-path result is good enough to skip browser escalation."""
    codec = (video.codec or "").strip().lower()
    if str(quality_profile).strip().lower() == DownloadQualityProfile.SOURCE_MASTER.value:
        return False
    return bool(
        video.watermark_free is True
        and codec in {"h264", "avc", "avc1", "h.264"}
        and video_long_edge(width=video.width, height=video.height) == max(1, int(target_long_edge))
        and (video.fps is None or video.fps >= 24.0)
        and video.hdr is not True
    )
