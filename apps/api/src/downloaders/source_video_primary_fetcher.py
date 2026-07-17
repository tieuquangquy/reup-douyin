from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID

from src.downloaders.api_bridged_playwright_douyin_resolver import ApiBridgedPlaywrightDouyinResolver
from src.downloaders.base import AssetDownloader, DownloadedObject
from src.downloaders.douyin_video_resolver import DouyinVideoResolveRequest, ResolvedDouyinVideo
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.playwright_douyin_video_resolver import PlaywrightDouyinVideoResolver
from src.downloaders.yt_dlp_douyin_resolver import YtDlpDouyinVideoResolver
from src.enums import SourcePlatformEnum
from src.services.douyin_browser_context_registry import has_authenticated_douyin_cookies

_REFRESH_SESSION_HINT = (
    "Refresh download session: open the app-managed Douyin Chromium, log in once, "
    "keep it open until cookies sync, then retry with the browser closed."
)


class DouyinVideoResolver(Protocol):
    def is_available(self) -> bool:
        ...

    def resolve(self, request: DouyinVideoResolveRequest) -> ResolvedDouyinVideo:
        ...


def has_usable_cookie_session(
    *,
    playwright_cookies: tuple[dict, ...] | list[dict] | None,
    session_cookie: str | None,
    cookie_source: str | None = None,
) -> bool:
    """True when we can attempt headless yt-dlp without launching Chromium."""
    if playwright_cookies and has_authenticated_douyin_cookies(list(playwright_cookies)):
        return True
    if isinstance(session_cookie, str) and session_cookie.strip():
        return True
    return False


@dataclass(frozen=True)
class PrimaryVideoFetchResult:
    downloaded: DownloadedObject
    resolver_name: str
    source_url: str
    watermark_free: bool | None = None
    height: int | None = None
    width: int | None = None
    format_id: str | None = None
    cookie_source: str | None = None
    author_handle: str | None = None
    author_display_name: str | None = None

    def asset_metadata(self) -> dict:
        return {
            "download_resolver": self.resolver_name,
            "download_source_url": self.source_url,
            "watermark_free": self.watermark_free,
            "download_height": self.height,
            "download_width": self.width,
            "download_format": self.format_id,
            "cookie_source": self.cookie_source,
            "author_handle": self.author_handle,
            "author_display_name": self.author_display_name,
        }


class SourceVideoPrimaryFetcher:
    def __init__(
        self,
        *,
        http_downloader: AssetDownloader,
        yt_dlp_resolver: DouyinVideoResolver | None = None,
        playwright_resolver: DouyinVideoResolver | None = None,
        playwright_bridge_resolver: DouyinVideoResolver | None = None,
        yt_dlp_enabled: bool = True,
        playwright_enabled: bool = True,
    ):
        self.http_downloader = http_downloader
        self.yt_dlp_resolver = yt_dlp_resolver or YtDlpDouyinVideoResolver()
        self.playwright_resolver = playwright_resolver if playwright_resolver is not None else PlaywrightDouyinVideoResolver()
        self.playwright_bridge_resolver = (
            playwright_bridge_resolver if playwright_bridge_resolver is not None else ApiBridgedPlaywrightDouyinResolver()
        )
        self.yt_dlp_enabled = yt_dlp_enabled
        self.playwright_enabled = playwright_enabled

    def fetch(
        self,
        source_video,
        *,
        session_cookie: str | None,
        user_agent: str,
        proxy_url: str | None = None,
        playwright_cookies: tuple[dict, ...] | None = None,
        cookie_source: str | None = None,
        workspace_id: UUID | None = None,
        account_connection_id: UUID | None = None,
    ) -> PrimaryVideoFetchResult:
        source_url = (source_video.source_url or "").strip()
        aweme_id = (source_video.source_video_external_id or "").strip()
        if not source_url and not aweme_id:
            raise DownloadError(DownloadErrorCode.MISSING_SOURCE_URL, "Source video has no download URL or aweme id")

        if source_video.source_platform != SourcePlatformEnum.DOUYIN:
            return self._fetch_via_http(source_url or aweme_id, resolver_name="http_legacy")

        if source_url and is_direct_media_url(source_url):
            return self._fetch_via_http(source_url, resolver_name="http_direct")

        page_url = source_url if is_douyin_page_url(source_url) else f"https://www.douyin.com/video/{aweme_id}"
        request = DouyinVideoResolveRequest(
            aweme_id=aweme_id,
            page_url=page_url,
            session_cookie=session_cookie,
            user_agent=user_agent,
            proxy_url=proxy_url,
            playwright_cookies=playwright_cookies,
            cookie_source=cookie_source,
            account_connection_id=account_connection_id,
            workspace_id=workspace_id or getattr(source_video, "workspace_id", None),
        )

        cookie_ready = has_usable_cookie_session(
            playwright_cookies=playwright_cookies,
            session_cookie=session_cookie,
            cookie_source=cookie_source,
        )
        yt_dlp_error: DownloadError | None = None
        playwright_error: DownloadError | None = None
        from src.core.settings import get_settings

        settings = get_settings()
        strict_nologo = not bool(getattr(settings, "douyin_download_allow_watermarked_fallback", False))

        def try_playwright() -> PrimaryVideoFetchResult | None:
            nonlocal playwright_error
            playwright_allowed = self.playwright_enabled
            if playwright_allowed and cookie_ready and yt_dlp_error is not None:
                # After cookie-backed yt-dlp failure, honor auto-open setting before launching Chromium.
                if not bool(getattr(settings, "douyin_playwright_download_auto_open", True)):
                    playwright_allowed = False
            if not playwright_allowed:
                if self.playwright_enabled and playwright_error is None:
                    playwright_error = DownloadError(
                        DownloadErrorCode.RESOLVE_FAILED,
                        f"Playwright download auto-open is disabled. {_REFRESH_SESSION_HINT}",
                    )
                return None
            for resolver in (self.playwright_resolver, self.playwright_bridge_resolver):
                if not resolver.is_available():
                    continue
                try:
                    resolved = resolver.resolve(request)
                    if strict_nologo and resolved.watermark_free is not True:
                        playwright_error = DownloadError(
                            DownloadErrorCode.DOWNLOAD_FAILED,
                            "Playwright download was not a verified no-logo (bit_rate/play_addr) stream",
                        )
                        continue
                    return PrimaryVideoFetchResult(
                        downloaded=DownloadedObject(
                            content=resolved.content,
                            mime_type=resolved.mime_type,
                            filename=resolved.filename,
                        ),
                        resolver_name=resolved.resolver_name,
                        source_url=page_url,
                        watermark_free=resolved.watermark_free,
                        height=resolved.height,
                        width=resolved.width,
                        format_id=resolved.format_id,
                        cookie_source=cookie_source or "playwright_browser",
                        author_handle=getattr(resolved, "author_handle", None),
                        author_display_name=getattr(resolved, "author_display_name", None),
                    )
                except DownloadError as exc:
                    playwright_error = exc
                    continue
            return None

        # Strict HQ/no-logo: Playwright first (prefer bit_rate/play_addr), then verified yt-dlp.
        if strict_nologo:
            pw_result = try_playwright()
            if pw_result is not None:
                return pw_result
            if self.yt_dlp_enabled:
                try:
                    return self._fetch_via_yt_dlp(request=request, cookie_source=cookie_source)
                except DownloadError as exc:
                    yt_dlp_error = exc
        else:
            # Cookie-store-first when watermarked fallback is allowed (legacy speed path).
            if self.yt_dlp_enabled and cookie_ready:
                try:
                    return self._fetch_via_yt_dlp(request=request, cookie_source=cookie_source)
                except DownloadError as exc:
                    yt_dlp_error = exc

            pw_result = try_playwright()
            if pw_result is not None:
                return pw_result

            # yt-dlp without prior cookie_ready (legacy env cookie / last resort).
            if self.yt_dlp_enabled and not cookie_ready:
                try:
                    return self._fetch_via_yt_dlp(request=request, cookie_source=cookie_source)
                except DownloadError as exc:
                    yt_dlp_error = exc

        if playwright_error is not None and yt_dlp_error is not None:
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                f"{playwright_error.message}; yt-dlp also failed. {_REFRESH_SESSION_HINT}",
            )
        if playwright_error is not None:
            raise DownloadError(
                playwright_error.code,
                f"{playwright_error.message}. {_REFRESH_SESSION_HINT}",
            )
        if yt_dlp_error is not None:
            if yt_dlp_error.code in {DownloadErrorCode.RESOLVE_FAILED, DownloadErrorCode.MISSING_SOURCE_URL}:
                raise yt_dlp_error
            raise DownloadError(
                yt_dlp_error.code,
                f"{yt_dlp_error.message}. {_REFRESH_SESSION_HINT}",
            )

        if not cookie_ready and self.playwright_enabled:
            raise DownloadError(
                DownloadErrorCode.RESOLVE_FAILED,
                f"No usable Douyin download cookies and Playwright browser is not available. {_REFRESH_SESSION_HINT}",
            )

        if not source_url:
            raise DownloadError(
                DownloadErrorCode.RESOLVE_FAILED,
                f"Douyin resolvers are disabled/unavailable. {_REFRESH_SESSION_HINT}",
            )
        if strict_nologo:
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                "Strict no-logo download could not obtain a verified watermark-free stream. "
                f"{_REFRESH_SESSION_HINT}",
            )
        return self._fetch_via_http(source_url, resolver_name="http_legacy")

    def _fetch_via_http(self, url: str, *, resolver_name: str) -> PrimaryVideoFetchResult:
        downloaded = self.http_downloader.fetch(url)
        if not downloaded.content:
            raise DownloadError(DownloadErrorCode.VALIDATION_FAILED, "HTTP downloader returned empty video content")
        return PrimaryVideoFetchResult(
            downloaded=downloaded,
            resolver_name=resolver_name,
            source_url=url,
        )

    def _fetch_via_yt_dlp(
        self,
        *,
        request: DouyinVideoResolveRequest,
        cookie_source: str | None = None,
    ) -> PrimaryVideoFetchResult:
        if not request.aweme_id:
            raise DownloadError(DownloadErrorCode.MISSING_SOURCE_URL, "Douyin download requires aweme_id/source_video_external_id")
        if not self.yt_dlp_resolver.is_available():
            raise DownloadError(
                DownloadErrorCode.RESOLVE_FAILED,
                "Douyin yt-dlp resolver is not available on this host",
            )
        resolved = self.yt_dlp_resolver.resolve(request)
        from src.core.settings import get_settings

        strict_nologo = not bool(getattr(get_settings(), "douyin_download_allow_watermarked_fallback", False))
        if strict_nologo and resolved.watermark_free is not True:
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                "yt-dlp did not produce a verified no-logo download/* stream under strict mode",
            )
        return PrimaryVideoFetchResult(
            downloaded=DownloadedObject(
                content=resolved.content,
                mime_type=resolved.mime_type,
                filename=resolved.filename,
            ),
            resolver_name=resolved.resolver_name,
            source_url=request.page_url or f"https://www.douyin.com/video/{request.aweme_id}",
            watermark_free=resolved.watermark_free,
            height=resolved.height,
            width=resolved.width,
            format_id=resolved.format_id,
            cookie_source=cookie_source,
        )


def is_direct_media_url(url: str) -> bool:
    normalized = url.strip().lower()
    if not normalized:
        return False
    if normalized.endswith((".mp4", ".m3u8", ".mov", ".webm")):
        return True
    host = urlparse(normalized).netloc
    return any(
        token in host
        for token in (
            "douyinvod.com",
            "ixigua.com",
            "snssdk.com",
            "bytecdn.cn",
            "tiktokcdn",
            "amemv.com",
        )
    )


def is_douyin_page_url(url: str) -> bool:
    normalized = url.strip().lower()
    return "douyin.com/video/" in normalized or "iesdouyin.com/share/video/" in normalized
