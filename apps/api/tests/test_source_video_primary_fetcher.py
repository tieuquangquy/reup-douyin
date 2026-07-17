from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.downloaders.base import DownloadedObject
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.source_video_primary_fetcher import (
    PrimaryVideoFetchResult,
    SourceVideoPrimaryFetcher,
    is_direct_media_url,
    is_douyin_page_url,
)
from src.downloaders.yt_dlp_douyin_resolver import ResolvedDouyinVideo
from src.enums import SourcePlatformEnum


class FakeHttpDownloader:
    def __init__(self, content: bytes = b"http-bytes"):
        self.urls: list[str] = []
        self.content = content

    def fetch(self, url: str) -> DownloadedObject:
        self.urls.append(url)
        return DownloadedObject(content=self.content, mime_type="video/mp4", filename="http.mp4")


class FakeYtDlpResolver:
    def __init__(self, *, available: bool = True, content: bytes = b"yt-dlp-bytes"):
        self.available = available
        self.content = content
        self.calls: list[dict] = []

    def is_available(self) -> bool:
        return self.available

    def resolve(self, request):
        self.calls.append(
            {
                "aweme_id": request.aweme_id,
                "page_url": request.page_url,
                "session_cookie": request.session_cookie,
            }
        )
        return ResolvedDouyinVideo(
            content=self.content,
            mime_type="video/mp4",
            filename="yt-dlp.mp4",
            resolver_name="yt_dlp",
            format_id="download",
            height=1080,
            width=1920,
            watermark_free=True,
        )


def source_video(**overrides):
    base = {
        "source_platform": SourcePlatformEnum.DOUYIN,
        "source_video_external_id": "7123456789012345678",
        "source_url": "https://www.douyin.com/video/7123456789012345678",
        "workspace_id": "workspace-1",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class SourceVideoPrimaryFetcherTests(unittest.TestCase):
    def test_direct_media_url_detection(self):
        self.assertTrue(is_direct_media_url("https://v3-dy.ixigua.com/obj/video.mp4"))
        self.assertFalse(is_douyin_page_url("https://v3-dy.ixigua.com/obj/video.mp4"))

    def test_douyin_page_url_uses_yt_dlp(self):
        http = FakeHttpDownloader()
        yt_dlp = FakeYtDlpResolver()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=http,
            yt_dlp_resolver=yt_dlp,
            yt_dlp_enabled=True,
            playwright_enabled=False,
        )
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=False,
                douyin_playwright_download_auto_open=True,
            ),
        ):
            result = fetcher.fetch(
                source_video(),
                session_cookie="sessionid=abc",
                user_agent="ua",
            )
        self.assertEqual(result.downloaded.content, b"yt-dlp-bytes")
        self.assertEqual(result.resolver_name, "yt_dlp")
        self.assertEqual(yt_dlp.calls[0]["aweme_id"], "7123456789012345678")
        self.assertEqual(http.urls, [])

    def test_direct_cdn_url_uses_http_first(self):
        http = FakeHttpDownloader(content=b"cdn-bytes")
        yt_dlp = FakeYtDlpResolver()
        cdn_url = "https://v26-dy.ixigua.com/obj/tos-cn-v-1234/video.mp4"
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=http,
            yt_dlp_resolver=yt_dlp,
            yt_dlp_enabled=True,
            playwright_enabled=False,
        )
        result = fetcher.fetch(
            source_video(source_url=cdn_url),
            session_cookie=None,
            user_agent="ua",
        )
        self.assertEqual(result.downloaded.content, b"cdn-bytes")
        self.assertEqual(result.resolver_name, "http_direct")
        self.assertEqual(http.urls, [cdn_url])
        self.assertEqual(yt_dlp.calls, [])

    def test_yt_dlp_unavailable_raises_resolve_failed(self):
        http = FakeHttpDownloader()
        yt_dlp = FakeYtDlpResolver(available=False)
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=http,
            yt_dlp_resolver=yt_dlp,
            yt_dlp_enabled=True,
            playwright_enabled=False,
        )
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=False,
                douyin_playwright_download_auto_open=True,
            ),
        ):
            with self.assertRaises(DownloadError) as ctx:
                fetcher.fetch(source_video(), session_cookie=None, user_agent="ua")
        self.assertIn(ctx.exception.code, {DownloadErrorCode.RESOLVE_FAILED, DownloadErrorCode.DOWNLOAD_FAILED})

    def test_is_douyin_page_url(self):
        self.assertTrue(is_douyin_page_url("https://www.douyin.com/video/123"))

    def test_yt_dlp_disabled_uses_http_legacy_when_fallback_allowed(self):
        http = FakeHttpDownloader(content=b"legacy-bytes")
        yt_dlp = FakeYtDlpResolver()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=http,
            yt_dlp_resolver=yt_dlp,
            yt_dlp_enabled=False,
            playwright_enabled=False,
        )
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=True,
                douyin_playwright_download_auto_open=True,
            ),
        ):
            result = fetcher.fetch(
                source_video(source_url="https://www.douyin.com/video/7123456789012345678"),
                session_cookie=None,
                user_agent="ua",
            )
        self.assertEqual(result.resolver_name, "http_legacy")
        self.assertEqual(http.urls, ["https://www.douyin.com/video/7123456789012345678"])

    def test_strict_rejects_http_legacy_page_url(self):
        http = FakeHttpDownloader(content=b"legacy-bytes")
        yt_dlp = FakeYtDlpResolver()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=http,
            yt_dlp_resolver=yt_dlp,
            yt_dlp_enabled=False,
            playwright_enabled=False,
        )
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=False,
                douyin_playwright_download_auto_open=True,
            ),
        ):
            with self.assertRaises(DownloadError) as ctx:
                fetcher.fetch(
                    source_video(source_url="https://www.douyin.com/video/7123456789012345678"),
                    session_cookie=None,
                    user_agent="ua",
                )
        self.assertEqual(ctx.exception.code, DownloadErrorCode.DOWNLOAD_FAILED)
        self.assertIn("no-logo", ctx.exception.message.lower())


class PrimaryVideoFetchResultTests(unittest.TestCase):
    def test_metadata_includes_resolver_fields(self):
        result = PrimaryVideoFetchResult(
            downloaded=DownloadedObject(content=b"x", mime_type="video/mp4", filename="a.mp4"),
            resolver_name="yt_dlp",
            source_url="https://www.douyin.com/video/1",
            watermark_free=True,
            height=720,
            width=1280,
            format_id="download",
        )
        metadata = result.asset_metadata()
        self.assertEqual(metadata["download_resolver"], "yt_dlp")
        self.assertTrue(metadata["watermark_free"])


if __name__ == "__main__":
    unittest.main()
