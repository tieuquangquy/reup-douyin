from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import hashlib
import inspect
import logging
from pathlib import Path
import re
from typing import Callable, Protocol
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from src.downloaders.api_bridged_playwright_douyin_resolver import ApiBridgedPlaywrightDouyinResolver
from src.downloaders.base import AssetDownloader, DownloadedObject
from src.downloaders.douyin_video_resolver import (
    DouyinVideoResolveRequest,
    ResolvedDouyinVideo,
    is_preferred_download_quality,
    media_quality_sort_key,
)
from src.downloaders.download_quality_policy import (
    DownloadQualityProfile,
    WatermarkAuthority,
    is_verified_no_logo,
)
from src.downloaders.errors import DownloadError, DownloadErrorCode, DownloadFailureReason
from src.downloaders.playwright_douyin_video_resolver import PlaywrightDouyinVideoResolver
from src.downloaders.yt_dlp_douyin_resolver import YtDlpDouyinVideoResolver
from src.downloaders.download_staging import staging_path
from src.enums import SourcePlatformEnum
from src.services.douyin_browser_context_registry import has_authenticated_douyin_cookies

logger = logging.getLogger(__name__)

_REFRESH_SESSION_HINT = (
    "Refresh download session: open the app-managed Douyin Chromium, log in once, "
    "keep it open until cookies sync, then retry with the browser closed."
)


class DouyinVideoResolver(Protocol):
    def is_available(self) -> bool:
        ...

    def resolve(self, request: DouyinVideoResolveRequest) -> ResolvedDouyinVideo:
        ...

    def discover(self, request: DouyinVideoResolveRequest) -> list[ResolvedDouyinVideo]:
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
    watermark_authority: str | None = None
    height: int | None = None
    width: int | None = None
    bitrate: int | None = None
    codec: str | None = None
    fps: float | None = None
    hdr: bool | None = None
    format_id: str | None = None
    cookie_source: str | None = None
    author_handle: str | None = None
    author_display_name: str | None = None
    quality_escalated: bool = False
    quality_fallback_used: bool = False
    selection_trace: tuple[dict, ...] = ()
    quality_profile: str = DownloadQualityProfile.BALANCED_PROCESSING.value
    target_long_edge: int = 1920

    def asset_metadata(self) -> dict:
        return {
            "download_resolver": self.resolver_name,
            "download_source_url": self.source_url,
            "watermark_free": self.watermark_free,
            "watermark_authority": self.watermark_authority,
            "download_height": self.height,
            "download_width": self.width,
            "download_bitrate": self.bitrate,
            "download_codec": self.codec,
            "download_fps": self.fps,
            "download_hdr": self.hdr,
            "download_format": self.format_id,
            "cookie_source": self.cookie_source,
            "author_handle": self.author_handle,
            "author_display_name": self.author_display_name,
            "download_quality_escalated": self.quality_escalated,
            "download_quality_fallback_used": self.quality_fallback_used,
            "download_selection_trace": [dict(row) for row in self.selection_trace],
            "download_quality_profile": self.quality_profile,
            "download_target_long_edge": self.target_long_edge,
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
        transfer_id: UUID | str | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
    ) -> PrimaryVideoFetchResult:
        source_url = (source_video.source_url or "").strip()
        aweme_id = (source_video.source_video_external_id or "").strip() or extract_aweme_id_from_url(source_url)
        if not source_url and not aweme_id:
            raise DownloadError(DownloadErrorCode.MISSING_SOURCE_URL, "Source video has no download URL or aweme id")

        if source_video.source_platform != SourcePlatformEnum.DOUYIN:
            return self._fetch_via_http(
                source_url or aweme_id,
                resolver_name="http_legacy",
                workspace_id=workspace_id or getattr(source_video, "workspace_id", None),
                aweme_id=aweme_id or source_url,
                account_connection_id=account_connection_id,
                transfer_id=transfer_id,
                on_progress=on_progress,
                user_agent=user_agent,
                session_cookie=session_cookie,
                referer=source_url,
                proxy_url=proxy_url,
            )

        if source_url and is_direct_media_url(source_url) and not is_segmented_media_url(source_url):
            from src.core.settings import get_settings

            strict_nologo = not bool(
                getattr(get_settings(), "douyin_download_allow_watermarked_fallback", False)
            )
            direct_watermark_free = classify_direct_media_watermark_free(source_url)
            # ``watermark=0`` is retained as a fast transfer hint.  It is
            # deliberately recorded as non-authoritative and the persistence
            # gate will require resolver provenance in strict mode.  This
            # avoids wasting a second transfer for a healthy signed URL while
            # still preventing it from becoming a trusted cache artifact.
            if not strict_nologo or direct_watermark_free is True:
                try:
                    return self._fetch_via_http(
                        source_url,
                        resolver_name="http_direct",
                        workspace_id=workspace_id or getattr(source_video, "workspace_id", None),
                        aweme_id=aweme_id or source_url,
                        account_connection_id=account_connection_id,
                        transfer_id=transfer_id,
                        on_progress=on_progress,
                        watermark_free=direct_watermark_free,
                        watermark_authority=(
                            WatermarkAuthority.URL_HINT_ONLY.value
                            if direct_watermark_free is not None
                            else WatermarkAuthority.UNKNOWN.value
                        ),
                        user_agent=user_agent,
                        session_cookie=session_cookie,
                        referer=source_url,
                        proxy_url=proxy_url,
                    )
                except DownloadError as exc:
                    if not aweme_id or not _should_reresolve_direct_media_error(exc):
                        raise
                    logger.info(
                        "direct_media_fetch_failed_reresolving_aweme",
                        extra={
                            "aweme_id": aweme_id,
                            "error_code": str(exc.code),
                            "reason": "signed_url_or_cdn_status",
                        },
                    )
            if not aweme_id:
                raise DownloadError(
                    DownloadErrorCode.DOWNLOAD_FAILED,
                    "Strict no-logo download rejected a direct CDN URL without clean-stream provenance",
                    reason=DownloadFailureReason.NO_CLEAN_STREAM,
                )

        from src.core.settings import get_settings

        settings = get_settings()
        page_url = source_url if is_douyin_page_url(source_url) or is_segmented_media_url(source_url) else f"https://www.douyin.com/video/{aweme_id}"
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
            transfer_id=transfer_id,
            on_progress=on_progress,
            quality_profile=str(
                getattr(settings, "douyin_download_quality_profile", DownloadQualityProfile.BALANCED_PROCESSING.value)
                or DownloadQualityProfile.BALANCED_PROCESSING.value
            ),
            target_long_edge=_positive_int_setting(settings, "douyin_download_target_long_edge", 1920),
        )

        cookie_ready = has_usable_cookie_session(
            playwright_cookies=playwright_cookies,
            session_cookie=session_cookie,
            cookie_source=cookie_source,
        )
        yt_dlp_error: DownloadError | None = None
        playwright_error: DownloadError | None = None
        strict_nologo = not bool(getattr(settings, "douyin_download_allow_watermarked_fallback", False))
        prefer_fast_yt_dlp = getattr(settings, "douyin_download_prefer_yt_dlp_fast_path", None) is True
        fast_path_timeout = _positive_int_setting(
            settings,
            "douyin_yt_dlp_fast_path_timeout_seconds",
            90,
        )

        # Discovery-first is deliberately optional: injected legacy adapters
        # and older bridge implementations continue through the proven
        # resolve-and-validate path below. When available, metadata discovery
        # ranks candidates before any full media transfer is started.
        if strict_nologo and request.quality_profile == DownloadQualityProfile.BALANCED_PROCESSING.value:
            discovered_result = self._try_discovery_first(
                request=request,
                page_url=page_url,
                cookie_ready=cookie_ready,
                strict_nologo=strict_nologo,
                on_progress=on_progress,
                fast_path_timeout=fast_path_timeout,
                prefer_fast_yt_dlp=prefer_fast_yt_dlp,
            )
            if discovered_result is not None:
                return discovered_result

        def try_playwright(resolve_request: DouyinVideoResolveRequest = request) -> PrimaryVideoFetchResult | None:
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
                    resolved = resolver.resolve(resolve_request)
                    authority = resolved.watermark_authority or (
                        "legacy_explicit_true" if resolved.watermark_free is True else None
                    )
                    if strict_nologo and not is_verified_no_logo(
                        watermark_free=resolved.watermark_free,
                        watermark_authority=authority,
                    ):
                        playwright_error = DownloadError(
                            DownloadErrorCode.DOWNLOAD_FAILED,
                            "Playwright download was not a verified no-logo (bit_rate/play_addr) stream",
                            reason=DownloadFailureReason.NO_CLEAN_STREAM,
                        )
                        continue
                    return PrimaryVideoFetchResult(
                        downloaded=DownloadedObject(
                            content=resolved.content,
                            mime_type=resolved.mime_type,
                            filename=resolved.filename,
                            local_path=resolved.local_path,
                            size_bytes=resolved.size_bytes,
                            cleanup_local_path=resolved.cleanup_local_path,
                        ),
                        resolver_name=resolved.resolver_name,
                        source_url=page_url,
                        watermark_free=resolved.watermark_free,
                        watermark_authority=authority or WatermarkAuthority.UNKNOWN.value,
                        height=resolved.height,
                        width=resolved.width,
                        bitrate=resolved.bitrate,
                        codec=resolved.codec,
                        fps=resolved.fps,
                        hdr=resolved.hdr,
                        format_id=resolved.format_id,
                        cookie_source=cookie_source or "playwright_browser",
                        author_handle=getattr(resolved, "author_handle", None),
                        author_display_name=getattr(resolved, "author_display_name", None),
                        quality_profile=resolve_request.quality_profile,
                        target_long_edge=resolve_request.target_long_edge,
                    )
                except DownloadError as exc:
                    playwright_error = exc
                    continue
            return None

        # Strict HQ/no-logo: use the cheap cookie-backed yt-dlp fast path when
        # enabled, then fall back to Playwright's browser-resolved candidates.
        if strict_nologo:
            fast_result: PrimaryVideoFetchResult | None = None
            if prefer_fast_yt_dlp and self.yt_dlp_enabled and cookie_ready:
                try:
                    fast_result = self._fetch_via_yt_dlp(
                        request=request,
                        cookie_source=cookie_source,
                        on_progress=on_progress,
                        timeout_seconds=fast_path_timeout,
                    )
                    if request.quality_profile == DownloadQualityProfile.SOURCE_MASTER.value:
                        return replace(
                            fast_result,
                            selection_trace=(
                                _selection_trace_row(
                                    fast_result,
                                    selected=True,
                                    decision="source_master_resolver_winner",
                                ),
                            ),
                        )
                    if _is_preferred_fetch_quality(fast_result):
                        return replace(
                            fast_result,
                            selection_trace=(
                                _selection_trace_row(fast_result, selected=True, decision="fast_path_target_met"),
                            ),
                        )
                    # Both resolvers normally write ``video.mp4`` in the same
                    # transfer namespace. Preserve the fast candidate before
                    # Playwright writes its candidate so comparison is real.
                    fast_result = _isolate_staging_result(fast_result, stem="yt_dlp_fast")
                    fast_result = replace(fast_result, quality_escalated=True)
                    logger.info(
                        "yt_dlp_fast_path_quality_escalation",
                        extra={
                            "aweme_id": request.aweme_id,
                            "resolver": fast_result.resolver_name,
                            "width": fast_result.width,
                            "height": fast_result.height,
                            "codec": fast_result.codec,
                            "reason": "preferred_h264_target_not_met",
                        },
                    )
                except DownloadError as exc:
                    yt_dlp_error = exc
            escalation_timeout = _positive_int_setting(
                settings,
                "douyin_download_quality_escalation_timeout_seconds",
                45,
            )
            pw_result = try_playwright(replace(request, timeout_seconds=escalation_timeout))
            if pw_result is not None:
                if fast_result is None or _quality_result_key(pw_result) > _quality_result_key(fast_result):
                    if fast_result is not None:
                        _discard_staging_result(fast_result)
                    return replace(
                        pw_result,
                        quality_escalated=fast_result is not None,
                        selection_trace=tuple(
                            row
                            for row in (
                                _selection_trace_row(fast_result, selected=False, decision="browser_candidate_won")
                                if fast_result is not None
                                else None,
                                _selection_trace_row(pw_result, selected=True, decision="browser_candidate_won"),
                            )
                            if row is not None
                        ),
                    )
                _discard_staging_result(pw_result)
                return replace(
                    fast_result,
                    quality_fallback_used=True,
                    selection_trace=(
                        _selection_trace_row(fast_result, selected=True, decision="fast_candidate_won"),
                        _selection_trace_row(pw_result, selected=False, decision="fast_candidate_won"),
                    ),
                )
            if fast_result is not None:
                # Browser resolution may be unavailable on a headless worker;
                # keep the verified fast-path artifact rather than downloading it again.
                return replace(
                    fast_result,
                    quality_fallback_used=True,
                    selection_trace=(
                        _selection_trace_row(fast_result, selected=True, decision="browser_unavailable"),
                    ),
                )
            if self.yt_dlp_enabled and yt_dlp_error is None:
                try:
                    return self._fetch_via_yt_dlp(
                        request=request,
                        cookie_source=cookie_source,
                        on_progress=on_progress,
                    )
                except DownloadError as exc:
                    yt_dlp_error = exc
        else:
            # Cookie-store-first when watermarked fallback is allowed (legacy speed path).
            if self.yt_dlp_enabled and cookie_ready:
                try:
                    return self._fetch_via_yt_dlp(
                        request=request,
                        cookie_source=cookie_source,
                        on_progress=on_progress,
                        timeout_seconds=fast_path_timeout,
                    )
                except DownloadError as exc:
                    yt_dlp_error = exc

            pw_result = try_playwright()
            if pw_result is not None:
                return pw_result

            # yt-dlp without prior cookie_ready (legacy env cookie / last resort).
            if self.yt_dlp_enabled and not cookie_ready:
                try:
                    return self._fetch_via_yt_dlp(
                        request=request,
                        cookie_source=cookie_source,
                        on_progress=on_progress,
                    )
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
        return self._fetch_via_http(
            source_url,
            resolver_name="http_legacy",
            workspace_id=workspace_id or getattr(source_video, "workspace_id", None),
            aweme_id=aweme_id or source_url,
            account_connection_id=account_connection_id,
            transfer_id=transfer_id,
            on_progress=on_progress,
            user_agent=user_agent,
            session_cookie=session_cookie,
            referer=source_url,
            proxy_url=proxy_url,
        )

    def _fetch_via_http(
        self,
        url: str,
        *,
        resolver_name: str,
        workspace_id: object | None = None,
        aweme_id: str | None = None,
        account_connection_id: object | None = None,
        transfer_id: object | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
        watermark_free: bool | None = None,
        watermark_authority: str | None = None,
        quality_profile: str = DownloadQualityProfile.BALANCED_PROCESSING.value,
        user_agent: str | None = None,
        session_cookie: str | None = None,
        referer: str | None = None,
        proxy_url: str | None = None,
    ) -> PrimaryVideoFetchResult:
        stream_fetch = getattr(self.http_downloader, "fetch_to_file", None)
        if callable(stream_fetch):
            identifier = (aweme_id or "").strip() or hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
            extension = Path(urlparse(url).path).suffix.lower().lstrip(".")
            if extension not in {"mp4", "mov", "m4v", "webm", "mkv"}:
                extension = "mp4"
            target = staging_path(
                aweme_id=identifier,
                workspace_id=workspace_id,
                account_connection_id=account_connection_id,
                transfer_id=transfer_id,
                extension=extension,
                stem="http",
            )
            try:
                target_is_douyin = is_trusted_douyin_media_url(url)
                target_allows_cookie = target_is_douyin and urlparse(url).scheme.lower() == "https"
                safe_referer = _safe_media_referer(url=url, referer=referer)
                headers = {
                    key: value
                    for key, value in {
                        "User-Agent": user_agent or "reup-douyin-local/0.1",
                        "Referer": safe_referer,
                        # A Douyin session is a credential.  It must never be
                        # forwarded to an arbitrary .mp4 URL captured from
                        # metadata or supplied by another source adapter.
                        "Cookie": session_cookie if target_allows_cookie else None,
                    }.items()
                    if value
                }
                call_kwargs: dict[str, object] = {
                    "resume": True,
                    "on_progress": on_progress,
                }
                # Keep compatibility with small test/legacy adapters by using
                # their declared signature.  Do not catch TypeError from inside
                # the downloader: that used to hide real bugs and retry without
                # credentials/proxy.
                try:
                    parameters = inspect.signature(stream_fetch).parameters
                except (TypeError, ValueError):
                    parameters = {}
                accepts_kwargs = any(
                    parameter.kind is inspect.Parameter.VAR_KEYWORD
                    for parameter in parameters.values()
                )
                if accepts_kwargs or "headers" in parameters:
                    call_kwargs["headers"] = headers
                if accepts_kwargs or "proxy_url" in parameters:
                    call_kwargs["proxy_url"] = proxy_url
                downloaded = stream_fetch(url, target, **call_kwargs)
                downloaded = replace(downloaded, cleanup_local_path=True)
            except NotImplementedError:
                downloaded = self.http_downloader.fetch(url)
        else:
            downloaded = self.http_downloader.fetch(url)
        if not downloaded.has_payload:
            raise DownloadError(DownloadErrorCode.VALIDATION_FAILED, "HTTP downloader returned empty video content")
        return PrimaryVideoFetchResult(
            downloaded=downloaded,
            resolver_name=resolver_name,
            source_url=url,
            watermark_free=watermark_free,
            watermark_authority=watermark_authority,
            quality_profile=quality_profile,
            target_long_edge=1920,
        )

    def _fetch_via_yt_dlp(
        self,
        *,
        request: DouyinVideoResolveRequest,
        cookie_source: str | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
        timeout_seconds: int | None = None,
    ) -> PrimaryVideoFetchResult:
        if not request.aweme_id and not request.page_url:
            raise DownloadError(DownloadErrorCode.MISSING_SOURCE_URL, "Douyin download requires aweme_id/source_video_external_id")
        if not self.yt_dlp_resolver.is_available():
            raise DownloadError(
                DownloadErrorCode.RESOLVE_FAILED,
                "Douyin yt-dlp resolver is not available on this host",
            )
        if on_progress is not None and request.on_progress is None:
            request = replace(request, on_progress=on_progress)
        if timeout_seconds is not None:
            request = replace(request, timeout_seconds=max(1, int(timeout_seconds)))
        resolved = self.yt_dlp_resolver.resolve(request)
        from src.core.settings import get_settings

        strict_nologo = not bool(getattr(get_settings(), "douyin_download_allow_watermarked_fallback", False))
        authority = resolved.watermark_authority or (
            "legacy_explicit_true" if resolved.watermark_free is True else None
        )
        if strict_nologo and not is_verified_no_logo(
            watermark_free=resolved.watermark_free,
            watermark_authority=authority,
        ):
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                "yt-dlp did not produce a verified no-logo download/* stream under strict mode",
                reason=DownloadFailureReason.NO_CLEAN_STREAM,
            )
        return PrimaryVideoFetchResult(
            downloaded=DownloadedObject(
                content=resolved.content,
                mime_type=resolved.mime_type,
                filename=resolved.filename,
                local_path=resolved.local_path,
                size_bytes=resolved.size_bytes,
                cleanup_local_path=resolved.cleanup_local_path,
            ),
            resolver_name=resolved.resolver_name,
            source_url=request.page_url or f"https://www.douyin.com/video/{request.aweme_id}",
            watermark_free=resolved.watermark_free,
            watermark_authority=authority or WatermarkAuthority.UNKNOWN.value,
            height=resolved.height,
            width=resolved.width,
            bitrate=resolved.bitrate,
            codec=resolved.codec,
            fps=resolved.fps,
            hdr=resolved.hdr,
            format_id=resolved.format_id,
            cookie_source=cookie_source,
            quality_profile=request.quality_profile,
            target_long_edge=request.target_long_edge,
        )

    def _try_discovery_first(
        self,
        *,
        request: DouyinVideoResolveRequest,
        page_url: str,
        cookie_ready: bool,
        strict_nologo: bool,
        on_progress: Callable[[int, int | None], None] | None,
        fast_path_timeout: int,
        prefer_fast_yt_dlp: bool,
    ) -> PrimaryVideoFetchResult | None:
        resolvers: list[tuple[str, DouyinVideoResolver]] = []
        if (
            prefer_fast_yt_dlp
            and self.yt_dlp_enabled
            and cookie_ready
            and hasattr(self.yt_dlp_resolver, "discover")
        ):
            resolvers.append(("yt_dlp", self.yt_dlp_resolver))
        if self.playwright_enabled and hasattr(self.playwright_resolver, "discover"):
            resolvers.append(("playwright", self.playwright_resolver))
        if self.playwright_enabled and hasattr(self.playwright_bridge_resolver, "discover"):
            resolvers.append(("playwright_bridge", self.playwright_bridge_resolver))
        if not resolvers:
            return None

        discovered: list[tuple[str, DouyinVideoResolver, ResolvedDouyinVideo]] = []
        discovery_trace: list[dict] = []
        for name, resolver in resolvers:
            try:
                if not resolver.is_available():
                    continue
                candidates = resolver.discover(
                    replace(request, timeout_seconds=fast_path_timeout)
                )
                for candidate in candidates:
                    if strict_nologo and not is_verified_no_logo(
                        watermark_free=candidate.watermark_free,
                        watermark_authority=candidate.watermark_authority,
                    ):
                        continue
                    discovered.append((name, resolver, candidate))
                    discovery_trace.append(
                        {
                            "resolver": name,
                            "format_id": candidate.format_id,
                            "width": candidate.width,
                            "height": candidate.height,
                            "codec": candidate.codec,
                            "bitrate": candidate.bitrate,
                            "watermark_authority": candidate.watermark_authority,
                        }
                    )
            except (DownloadError, NotImplementedError) as exc:
                logger.info(
                    "download_metadata_discovery_unavailable",
                    extra={"resolver": name, "error": type(exc).__name__},
                )
                continue
        if not discovered:
            return None

        def score(item: tuple[str, DouyinVideoResolver, ResolvedDouyinVideo]):
            candidate = item[2]
            return media_quality_sort_key(
                watermark_free=candidate.watermark_free,
                width=candidate.width,
                height=candidate.height,
                codec=candidate.codec,
                bitrate=candidate.bitrate,
                hdr=candidate.hdr,
                target_long_edge=request.target_long_edge,
                source_bonus=2 if item[0] == "yt_dlp" else 1,
            )

        discovered.sort(key=score, reverse=True)
        for resolver_name, resolver, candidate in discovered:
            try:
                resolved = resolver.resolve(
                    replace(
                        request,
                        timeout_seconds=fast_path_timeout,
                        preferred_format_id=(
                            candidate.format_id
                            if resolver_name in {"yt_dlp", "playwright", "playwright_bridge"}
                            else None
                        ),
                        preferred_candidate_url=(
                            candidate.candidate_url
                            if resolver_name == "playwright"
                            else None
                        ),
                    )
                )
                authority = resolved.watermark_authority or (
                    "legacy_explicit_true" if resolved.watermark_free is True else None
                )
                if strict_nologo and not is_verified_no_logo(
                    watermark_free=resolved.watermark_free,
                    watermark_authority=authority,
                ):
                    continue
                return PrimaryVideoFetchResult(
                    downloaded=DownloadedObject(
                        content=resolved.content,
                        mime_type=resolved.mime_type,
                        filename=resolved.filename,
                        local_path=resolved.local_path,
                        size_bytes=resolved.size_bytes,
                        cleanup_local_path=resolved.cleanup_local_path,
                    ),
                    resolver_name=resolved.resolver_name,
                    source_url=page_url,
                    watermark_free=resolved.watermark_free,
                    watermark_authority=authority or WatermarkAuthority.UNKNOWN.value,
                    height=resolved.height,
                    width=resolved.width,
                    bitrate=resolved.bitrate,
                    codec=resolved.codec,
                    fps=resolved.fps,
                    hdr=resolved.hdr,
                    format_id=resolved.format_id,
                    cookie_source=request.cookie_source or resolver_name,
                    quality_profile=request.quality_profile,
                    target_long_edge=request.target_long_edge,
                    selection_trace=tuple(
                        {
                            "resolver": row["resolver"],
                            "selected": row["resolver"] == resolver_name and row["format_id"] == candidate.format_id,
                            "decision": "discovery_first_selected" if row["resolver"] == resolver_name and row["format_id"] == candidate.format_id else "discovery_candidate_rejected",
                            **{key: value for key, value in row.items() if key != "resolver"},
                        }
                        for row in discovery_trace
                    ),
                )
            except DownloadError:
                continue
        return None


def is_direct_media_url(url: str) -> bool:
    normalized = url.strip().lower()
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if parsed.path.endswith((".mp4", ".m3u8", ".mpd", ".mov", ".webm", ".m4v", ".mkv")):
        # This helper is used for the Douyin resolver branch.  An arbitrary
        # user-supplied ``https://host/video.mp4`` must not bypass provenance,
        # no-logo checks, or the page resolver.
        if is_trusted_douyin_media_url(normalized):
            return True
    host = (parsed.hostname or "").lower().rstrip(".")
    return any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in _TRUSTED_DOUYIN_CDN_SUFFIXES
    )


def is_douyin_page_url(url: str) -> bool:
    normalized = url.strip().lower()
    if not normalized:
        return False
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").rstrip(".")
    is_douyin_host = host == "douyin.com" or host.endswith(".douyin.com")
    return bool(
        is_douyin_host
        and (
            "/video/" in normalized
            or "/share/video/" in normalized
            or "/note/" in normalized
            or host.startswith("v.")
        )
    )


_TRUSTED_DOUYIN_MEDIA_SUFFIXES = (
    "douyin.com",
    "iesdouyin.com",
    "douyinvod.com",
    "ixigua.com",
    "snssdk.com",
    "bytecdn.cn",
    "amemv.com",
    "tiktokcdn.com",
)

_TRUSTED_DOUYIN_CDN_SUFFIXES = tuple(
    suffix
    for suffix in _TRUSTED_DOUYIN_MEDIA_SUFFIXES
    if suffix not in {"douyin.com", "iesdouyin.com"}
)


def is_trusted_douyin_media_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in _TRUSTED_DOUYIN_MEDIA_SUFFIXES
    )


def _safe_media_referer(*, url: str, referer: str | None) -> str | None:
    """Return a referer only when it cannot disclose a credential-bearing URL."""
    # Do not echo arbitrary source URLs (which may contain signed query
    # credentials) as a Referer.  CDN requests only need the canonical Douyin
    # origin; non-Douyin adapters get no Referer from this boundary.
    if not is_trusted_douyin_media_url(url):
        return None
    if referer and is_douyin_page_url(referer):
        return referer
    return "https://www.douyin.com/"


def classify_direct_media_watermark_free(url: str) -> bool | None:
    normalized = (url or "").lower()
    if any(token in normalized for token in ("/mps/logo/", "playwm", "watermark=1", "watermark%3d1")):
        return False
    if "watermark=0" in normalized or "watermark%3d0" in normalized:
        return True
    # A first-party CDN host proves origin, not whether the selected stream is
    # play_addr/bit_rate (clean) or download_addr (logo).  Ambiguous direct URLs
    # must go through a resolver that carries candidate provenance.
    return None


def is_hls_media_url(url: str) -> bool:
    return urlparse((url or "").strip().lower()).path.endswith(".m3u8")


def is_dash_media_url(url: str) -> bool:
    return urlparse((url or "").strip().lower()).path.endswith(".mpd")


def is_segmented_media_url(url: str) -> bool:
    """Return true for manifests that must be assembled by yt-dlp/ffmpeg."""
    return is_hls_media_url(url) or is_dash_media_url(url)


def _positive_int_setting(settings: object, name: str, fallback: int) -> int:
    raw = getattr(settings, name, fallback)
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return fallback
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def _is_preferred_fetch_quality(result: PrimaryVideoFetchResult) -> bool:
    return is_preferred_download_quality(
        ResolvedDouyinVideo(
            content=None,
            mime_type=result.downloaded.mime_type,
            filename=result.downloaded.filename,
            resolver_name=result.resolver_name,
            format_id=result.format_id,
            height=result.height,
            width=result.width,
            bitrate=result.bitrate,
            codec=result.codec,
            fps=result.fps,
            hdr=result.hdr,
            watermark_free=result.watermark_free,
        ),
        quality_profile=result.quality_profile,
        target_long_edge=result.target_long_edge,
    )


def _quality_result_key(result: PrimaryVideoFetchResult) -> tuple[int, int, int, int, int, int, int]:
    return media_quality_sort_key(
        watermark_free=result.watermark_free,
        width=result.width,
        height=result.height,
        codec=result.codec,
        bitrate=result.bitrate,
        hdr=result.hdr,
        source_master=result.quality_profile == DownloadQualityProfile.SOURCE_MASTER.value,
        target_long_edge=result.target_long_edge,
    )


def _selection_trace_row(
    result: PrimaryVideoFetchResult,
    *,
    selected: bool,
    decision: str,
) -> dict:
    """Bounded resolver evidence persisted with the selected source asset."""

    return {
        "resolver": result.resolver_name,
        "selected": bool(selected),
        "decision": str(decision),
        "watermark_free": result.watermark_free,
        "watermark_authority": result.watermark_authority,
        "width": result.width,
        "height": result.height,
        "codec": result.codec,
        "fps": result.fps,
        "hdr": result.hdr,
        "bitrate": result.bitrate,
        "format_id": result.format_id,
    }


def _isolate_staging_result(result: PrimaryVideoFetchResult, *, stem: str) -> PrimaryVideoFetchResult:
    downloaded = result.downloaded
    if not downloaded.cleanup_local_path or not downloaded.local_path:
        return result
    source = Path(downloaded.local_path).resolve()
    from src.downloaders.download_staging import is_managed_staging_path

    if not source.is_file() or not is_managed_staging_path(source):
        return result
    target = source.with_name(f"{stem}{source.suffix}")
    if target == source:
        return result
    source.replace(target)
    info_source = source.with_name(f"{source.stem}.info.json")
    info_target = target.with_name(f"{target.stem}.info.json")
    if info_source.is_file():
        info_source.replace(info_target)
    return replace(
        result,
        downloaded=replace(downloaded, local_path=str(target), filename=target.name),
    )


def _discard_staging_result(result: PrimaryVideoFetchResult) -> None:
    """Remove only an unselected managed staging artifact after comparison."""
    downloaded = result.downloaded
    if not downloaded.cleanup_local_path or not downloaded.local_path:
        return
    candidate = Path(downloaded.local_path).resolve()
    from src.downloaders.download_staging import is_managed_staging_path

    if not is_managed_staging_path(candidate):
        logger.warning("download_quality_cleanup_skipped_outside_staging", extra={"path_name": candidate.name})
        return
    try:
        candidate.unlink(missing_ok=True)
        companion_names = {
            f"{candidate.name}.resume.json",
            f"{candidate.stem}.info.json",
            f"{candidate.name}.part",
            f"{candidate.stem}.part",
            f"{candidate.name}.ytdl",
            f"{candidate.stem}.ytdl",
        }
        for sibling in list(candidate.parent.iterdir()):
            if sibling.is_file() and sibling.name in companion_names:
                sibling.unlink(missing_ok=True)
    except OSError:
        logger.warning("download_quality_cleanup_failed", extra={"path_name": candidate.name}, exc_info=True)


def _should_reresolve_direct_media_error(error: DownloadError) -> bool:
    """Only refresh a canonical page for errors that indicate a stale CDN URL.

    Validation and storage failures must remain terminal for this transfer; a
    second resolver attempt cannot repair a corrupt payload or a local disk
    problem.  HTTP auth/not-found responses are the cases where Douyin commonly
    invalidates a signed play URL while the aweme itself is still available.
    """
    if error.code != DownloadErrorCode.DOWNLOAD_FAILED:
        return False
    message = str(error.message or "").lower()
    return any(
        marker in message
        for marker in (
            "http 401",
            "http 403",
            "http 404",
            "http 410",
        )
    )


def extract_aweme_id_from_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    for pattern in (r"/(?:video|note)/(\d{8,})", r"/share/video/(\d{8,})"):
        match = re.search(pattern, parsed.path, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    query = parse_qs(parsed.query)
    for key in ("aweme_id", "item_id", "modal_id"):
        values = query.get(key) or []
        if values and str(values[0]).isdigit():
            return str(values[0])
    return ""
