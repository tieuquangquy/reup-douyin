from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.base import DownloadedObject
from src.downloaders.douyin_video_resolver import ResolvedDouyinVideo
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.source_video_primary_fetcher import (
    SourceVideoPrimaryFetcher,
    has_usable_cookie_session,
)
from src.enums import SourcePlatformEnum


class FakeHttp:
    def fetch(self, url: str) -> DownloadedObject:
        raise AssertionError("http should not run")


class FakeYt:
    def __init__(self, *, fail: bool = False, content: bytes = b"yt-store-bytes"):
        self.fail = fail
        self.content = content
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def resolve(self, request):
        self.calls += 1
        if self.fail:
            raise DownloadError(DownloadErrorCode.DOWNLOAD_FAILED, "yt-dlp rejected cookies")
        return ResolvedDouyinVideo(
            content=self.content,
            mime_type="video/mp4",
            filename="yt.mp4",
            resolver_name="yt_dlp_browser",
            format_id="download",
            watermark_free=True,
            height=1080,
            width=1920,
        )


class FakePw:
    def __init__(self):
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def resolve(self, request):
        self.calls += 1
        return ResolvedDouyinVideo(
            content=b"pw-bytes",
            mime_type="video/mp4",
            filename="pw.mp4",
            resolver_name="playwright_browser",
            format_id="download_addr",
            watermark_free=True,
        )


class DisabledBridge:
    def is_available(self) -> bool:
        return False

    def resolve(self, request):
        raise AssertionError("bridge should not run")


AUTH_COOKIES = (
    {
        "name": "sessionid",
        "value": "abc",
        "domain": ".douyin.com",
        "path": "/",
        "secure": True,
    },
)


def _video():
    return SimpleNamespace(
        source_platform=SourcePlatformEnum.DOUYIN,
        source_video_external_id="123",
        source_url="https://www.douyin.com/video/123",
        workspace_id=uuid4(),
    )


class CookieStoreFirstFetcherTests(unittest.TestCase):
    def test_has_usable_cookie_session_from_store_cookies(self) -> None:
        self.assertTrue(has_usable_cookie_session(playwright_cookies=AUTH_COOKIES, session_cookie=None, cookie_source="browser_store"))
        self.assertFalse(has_usable_cookie_session(playwright_cookies=(), session_cookie=None, cookie_source="browser_store"))
        self.assertTrue(has_usable_cookie_session(playwright_cookies=None, session_cookie="sessionid=x", cookie_source="env"))

    def test_cookie_store_uses_yt_dlp_before_playwright_when_fallback_allowed(self) -> None:
        yt = FakeYt()
        pw = FakePw()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=FakeHttp(),
            yt_dlp_resolver=yt,
            playwright_resolver=pw,
            playwright_bridge_resolver=DisabledBridge(),
            yt_dlp_enabled=True,
            playwright_enabled=True,
        )
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=True,
                douyin_playwright_download_auto_open=True,
            ),
        ):
            result = fetcher.fetch(
                _video(),
                session_cookie="sessionid=abc",
                user_agent="ua",
                playwright_cookies=AUTH_COOKIES,
                cookie_source="browser_store",
            )
        self.assertEqual(result.downloaded.content, b"yt-store-bytes")
        self.assertEqual(result.resolver_name, "yt_dlp_browser")
        self.assertEqual(yt.calls, 1)
        self.assertEqual(pw.calls, 0)

    def test_strict_cookie_store_prefers_playwright_before_yt_dlp(self) -> None:
        yt = FakeYt()
        pw = FakePw()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=FakeHttp(),
            yt_dlp_resolver=yt,
            playwright_resolver=pw,
            playwright_bridge_resolver=DisabledBridge(),
            yt_dlp_enabled=True,
            playwright_enabled=True,
        )
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=False,
                douyin_playwright_download_auto_open=True,
            ),
        ):
            result = fetcher.fetch(
                _video(),
                session_cookie="sessionid=abc",
                user_agent="ua",
                playwright_cookies=AUTH_COOKIES,
                cookie_source="browser_store",
            )
        self.assertEqual(result.downloaded.content, b"pw-bytes")
        self.assertEqual(result.resolver_name, "playwright_browser")
        self.assertEqual(pw.calls, 1)
        self.assertEqual(yt.calls, 0)

    def test_yt_dlp_failure_falls_back_to_playwright(self) -> None:
        yt = FakeYt(fail=True)
        pw = FakePw()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=FakeHttp(),
            yt_dlp_resolver=yt,
            playwright_resolver=pw,
            playwright_bridge_resolver=DisabledBridge(),
            yt_dlp_enabled=True,
            playwright_enabled=True,
        )
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=True,
                douyin_playwright_download_auto_open=True,
            ),
        ):
            result = fetcher.fetch(
                _video(),
                session_cookie="sessionid=abc",
                user_agent="ua",
                playwright_cookies=AUTH_COOKIES,
                cookie_source="browser_store",
            )
        self.assertEqual(result.downloaded.content, b"pw-bytes")
        self.assertEqual(pw.calls, 1)

    def test_no_cookies_and_playwright_unavailable_asks_refresh_session(self) -> None:
        class NoPw:
            def is_available(self) -> bool:
                return False

            def resolve(self, request):
                raise AssertionError("should not run")

        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=FakeHttp(),
            yt_dlp_resolver=FakeYt(fail=True),
            playwright_resolver=NoPw(),
            playwright_bridge_resolver=DisabledBridge(),
            yt_dlp_enabled=True,
            playwright_enabled=True,
        )
        with self.assertRaises(DownloadError) as ctx:
            fetcher.fetch(
                _video(),
                session_cookie=None,
                user_agent="ua",
                playwright_cookies=None,
                cookie_source="none",
            )
        self.assertIn("Refresh download session", ctx.exception.message)


class StoreFirstCookieResolveTests(unittest.TestCase):
    def test_resolve_uses_store_without_opening_browser(self) -> None:
        from src.downloaders.douyin_browser_download_cookies import resolve_browser_download_cookies

        workspace_id = uuid4()
        account_id = uuid4()
        account = MagicMock()
        account.id = account_id
        account.user_agent = "ua"
        account.proxy_url = None
        account.metadata_json = {"browser_profile_id": "main", "browser_profile_path": "C:/profiles/main"}

        service = MagicMock()
        service.default_account.return_value = account
        store = MagicMock()
        store.playwright_cookies = AUTH_COOKIES
        store.user_agent = "ua-store"

        with (
            patch("src.downloaders.douyin_browser_download_cookies.DouyinAccountService", return_value=service),
            patch(
                "src.downloaders.douyin_browser_download_cookies.douyin_browser_context_registry.export_playwright_cookies_for_download",
                return_value=None,
            ) as export,
            patch(
                "src.downloaders.douyin_browser_download_cookies.read_download_cookie_store_for_account",
                return_value=store,
            ),
        ):
            result = resolve_browser_download_cookies(MagicMock(), workspace_id)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.cookie_source, "browser_store")
        self.assertEqual(result.playwright_cookies[0]["value"], "abc")
        export.assert_called_once()
        self.assertFalse(export.call_args.kwargs.get("allow_open_browser", True))


if __name__ == "__main__":
    unittest.main()
