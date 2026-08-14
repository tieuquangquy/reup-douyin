from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.downloaders.base import DownloadedObject
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.source_video_primary_fetcher import (
    PrimaryVideoFetchResult,
    SourceVideoPrimaryFetcher,
    _isolate_staging_result,
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


class CapturingStreamDownloader:
    def __init__(self):
        self.calls: list[dict] = []

    def fetch(self, _url: str) -> DownloadedObject:
        raise AssertionError("streaming boundary should be used")

    def fetch_to_file(self, url, destination, *, resume, on_progress, headers, proxy_url):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "proxy_url": proxy_url,
            }
        )
        from pathlib import Path

        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")
        return DownloadedObject(local_path=str(path), size_bytes=5, mime_type="video/mp4")


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
                "timeout_seconds": getattr(request, "timeout_seconds", None),
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
    def test_discovery_first_downloads_only_the_winning_candidate(self):
        class DiscoverableYt:
            def __init__(self):
                self.discover_calls = 0
                self.resolve_calls = []

            def is_available(self):
                return True

            def discover(self, request):
                self.discover_calls += 1
                return [
                    ResolvedDouyinVideo(
                        content=None,
                        mime_type="video/mp4",
                        filename=None,
                        resolver_name="yt_dlp_discovery",
                        format_id="play-720+bestaudio/best",
                        width=720,
                        height=1280,
                        codec="h264",
                        watermark_free=True,
                        watermark_authority="verified_ytdlp_provenance",
                    )
                ]

            def resolve(self, request):
                self.resolve_calls.append(request.preferred_format_id)
                return ResolvedDouyinVideo(
                    content=b"winner",
                    mime_type="video/mp4",
                    filename="winner.mp4",
                    resolver_name="yt_dlp",
                    format_id=request.preferred_format_id,
                    width=720,
                    height=1280,
                    codec="h264",
                    watermark_free=True,
                    watermark_authority="verified_ytdlp_provenance",
                )

        class DiscoverablePw:
            def __init__(self):
                self.resolve_calls = 0

            def is_available(self):
                return True

            def discover(self, request):
                return [
                    ResolvedDouyinVideo(
                        content=None,
                        mime_type="video/mp4",
                        filename=None,
                        resolver_name="playwright_discovery",
                        format_id="bit_rate|1920p|h264",
                        width=1080,
                        height=1920,
                        codec="h264",
                        fps=30.0,
                        watermark_free=True,
                        watermark_authority="verified_playback_provenance",
                        candidate_url="https://cdn.example/winner.mp4",
                    )
                ]

            def resolve(self, request):
                self.resolve_calls += 1
                self.preferred_url = request.preferred_candidate_url
                return ResolvedDouyinVideo(
                    content=b"winner",
                    mime_type="video/mp4",
                    filename="winner.mp4",
                    resolver_name="playwright_browser",
                    format_id="bit_rate|1920p|h264",
                    width=1080,
                    height=1920,
                    codec="h264",
                    fps=30.0,
                    watermark_free=True,
                    watermark_authority="verified_playback_provenance",
                )

        yt = DiscoverableYt()
        pw = DiscoverablePw()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=FakeHttpDownloader(),
            yt_dlp_resolver=yt,
            playwright_resolver=pw,
            playwright_bridge_resolver=SimpleNamespace(is_available=lambda: False),
        )
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=False,
                douyin_download_prefer_yt_dlp_fast_path=True,
                douyin_download_quality_profile="balanced_processing",
                douyin_download_target_long_edge=1920,
                douyin_yt_dlp_fast_path_timeout_seconds=30,
                douyin_playwright_download_auto_open=True,
            ),
        ):
            result = fetcher.fetch(source_video(), session_cookie="sessionid=abc", user_agent="ua")

        self.assertEqual(result.resolver_name, "playwright_browser")
        self.assertEqual(pw.resolve_calls, 1)
        self.assertEqual(pw.preferred_url, "https://cdn.example/winner.mp4")
        self.assertEqual(yt.resolve_calls, [])
        self.assertNotIn("https://cdn.example", str(result.selection_trace))

    def test_quality_escalation_isolates_fast_artifact_from_playwright_target(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "video.mp4"
            source.write_bytes(b"fast-candidate")
            source.with_name("video.info.json").write_text("{}", encoding="utf-8")
            result = PrimaryVideoFetchResult(
                downloaded=DownloadedObject(
                    local_path=str(source),
                    filename=source.name,
                    size_bytes=source.stat().st_size,
                    cleanup_local_path=True,
                ),
                resolver_name="yt_dlp_browser",
                source_url="https://www.douyin.com/video/1",
                watermark_free=True,
            )
            with patch("src.downloaders.download_staging.is_managed_staging_path", return_value=True):
                isolated = _isolate_staging_result(result, stem="yt_dlp_fast")

            isolated_path = Path(isolated.downloaded.local_path or "")
            self.assertEqual(isolated_path.name, "yt_dlp_fast.mp4")
            self.assertEqual(isolated_path.read_bytes(), b"fast-candidate")
            self.assertFalse(source.exists())
            self.assertTrue(Path(tmp, "yt_dlp_fast.info.json").is_file())

    def test_fast_path_hevc_720_escalates_and_selects_playwright_h264_1080(self):
        class PoorYt(FakeYtDlpResolver):
            def resolve(self, request):
                self.calls.append({"aweme_id": request.aweme_id})
                return ResolvedDouyinVideo(
                    content=b"hevc-720",
                    mime_type="video/mp4",
                    filename="yt.mp4",
                    resolver_name="yt_dlp_browser",
                    format_id="play-720",
                    height=1280,
                    width=720,
                    codec="hevc",
                    watermark_free=True,
                )

        class BetterPw:
            calls = 0
            timeout_seconds = None

            def is_available(self):
                return True

            def resolve(self, request):
                self.calls += 1
                self.timeout_seconds = request.timeout_seconds
                return ResolvedDouyinVideo(
                    content=b"h264-1080",
                    mime_type="video/mp4",
                    filename="pw.mp4",
                    resolver_name="playwright_browser",
                    format_id="bit_rate|1920p|h264",
                    height=1920,
                    width=1080,
                    codec="h264",
                    fps=30.0,
                    hdr=False,
                    watermark_free=True,
                )

        class DisabledBridge:
            def is_available(self):
                return False

        yt = PoorYt()
        pw = BetterPw()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=FakeHttpDownloader(),
            yt_dlp_resolver=yt,
            playwright_resolver=pw,
            playwright_bridge_resolver=DisabledBridge(),
        )
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=False,
                douyin_download_prefer_yt_dlp_fast_path=True,
                douyin_yt_dlp_fast_path_timeout_seconds=30,
                douyin_playwright_download_auto_open=True,
            ),
        ):
            result = fetcher.fetch(
                source_video(),
                session_cookie="sessionid=abc",
                user_agent="ua",
            )

        self.assertEqual(result.resolver_name, "playwright_browser")
        self.assertEqual(result.downloaded.content, b"h264-1080")
        self.assertEqual(len(yt.calls), 1)
        self.assertEqual(pw.calls, 1)
        self.assertEqual(pw.timeout_seconds, 45)

    def test_fast_path_h264_1080_skips_playwright(self):
        class PreferredYt(FakeYtDlpResolver):
            def resolve(self, request):
                self.calls.append({"aweme_id": request.aweme_id})
                return ResolvedDouyinVideo(
                    content=b"h264-1080",
                    mime_type="video/mp4",
                    filename="yt.mp4",
                    resolver_name="yt_dlp_browser",
                    format_id="play-1080",
                    height=1920,
                    width=1080,
                    codec="h264",
                    fps=30.0,
                    hdr=False,
                    watermark_free=True,
                )

        class PwMustNotRun:
            def is_available(self):
                return True

            def resolve(self, request):
                raise AssertionError("preferred fast path must skip Playwright")

        yt = PreferredYt()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=FakeHttpDownloader(),
            yt_dlp_resolver=yt,
            playwright_resolver=PwMustNotRun(),
            playwright_bridge_resolver=PwMustNotRun(),
        )
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=False,
                douyin_download_prefer_yt_dlp_fast_path=True,
                douyin_yt_dlp_fast_path_timeout_seconds=30,
                douyin_playwright_download_auto_open=True,
            ),
        ):
            result = fetcher.fetch(
                source_video(),
                session_cookie="sessionid=abc",
                user_agent="ua",
            )

        self.assertEqual(result.resolver_name, "yt_dlp_browser")
        self.assertEqual(len(yt.calls), 1)

    def test_source_master_accepts_validated_yt_dlp_without_second_full_transfer(self):
        class PwMustNotRun:
            def is_available(self):
                return True

            def resolve(self, request):
                raise AssertionError("source-master should not download a second candidate")

        yt = FakeYtDlpResolver()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=FakeHttpDownloader(),
            yt_dlp_resolver=yt,
            playwright_resolver=PwMustNotRun(),
            playwright_bridge_resolver=PwMustNotRun(),
        )
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=False,
                douyin_download_prefer_yt_dlp_fast_path=True,
                douyin_download_quality_profile="source_master",
                douyin_download_target_long_edge=1920,
                douyin_yt_dlp_fast_path_timeout_seconds=30,
                douyin_playwright_download_auto_open=True,
            ),
        ):
            result = fetcher.fetch(source_video(), session_cookie="sessionid=abc", user_agent="ua")

        self.assertEqual(result.quality_profile, "source_master")
        self.assertEqual(result.selection_trace[0]["decision"], "source_master_resolver_winner")

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
        cdn_url = "https://v26-dy.ixigua.com/obj/tos-cn-v-1234/video.mp4?watermark=0"
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

    def test_strict_ambiguous_direct_cdn_url_uses_provenance_resolver(self):
        http = FakeHttpDownloader(content=b"ambiguous")
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
                douyin_download_prefer_yt_dlp_fast_path=True,
                douyin_yt_dlp_fast_path_timeout_seconds=30,
            ),
        ):
            result = fetcher.fetch(
                source_video(
                    source_url="https://v26-dy.ixigua.com/obj/tos-cn-v-1234/video.mp4"
                ),
                session_cookie="sessionid=abc",
                user_agent="ua",
            )

        self.assertEqual(result.resolver_name, "yt_dlp")
        self.assertEqual(http.urls, [])
        self.assertEqual(len(yt_dlp.calls), 1)
        self.assertEqual(yt_dlp.calls[0]["timeout_seconds"], 30)

    def test_expired_direct_cdn_url_reresolves_from_aweme(self):
        class ExpiredHttp(FakeHttpDownloader):
            def fetch(self, url: str) -> DownloadedObject:
                self.urls.append(url)
                raise DownloadError(DownloadErrorCode.DOWNLOAD_FAILED, "Download failed: HTTP 403")

        http = ExpiredHttp()
        yt_dlp = FakeYtDlpResolver()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=http,
            yt_dlp_resolver=yt_dlp,
            yt_dlp_enabled=True,
            playwright_enabled=False,
        )
        direct_url = "https://v26-dy.ixigua.com/video.mp4?watermark=0"
        with patch(
            "src.core.settings.get_settings",
            return_value=MagicMock(
                douyin_download_allow_watermarked_fallback=False,
                douyin_playwright_download_auto_open=True,
                douyin_download_prefer_yt_dlp_fast_path=True,
                douyin_yt_dlp_fast_path_timeout_seconds=30,
            ),
        ):
            result = fetcher.fetch(
                source_video(source_url=direct_url),
                session_cookie="sessionid=abc",
                user_agent="ua",
            )

        self.assertEqual(http.urls, [direct_url])
        self.assertEqual(result.resolver_name, "yt_dlp")
        self.assertEqual(len(yt_dlp.calls), 1)

    def test_direct_validation_failure_does_not_open_a_second_resolver(self):
        class InvalidHttp(FakeHttpDownloader):
            def fetch(self, url: str) -> DownloadedObject:
                self.urls.append(url)
                raise DownloadError(
                    DownloadErrorCode.VALIDATION_FAILED,
                    "HTTP source returned non-video content type: text/html",
                )

        http = InvalidHttp()
        yt_dlp = FakeYtDlpResolver()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=http,
            yt_dlp_resolver=yt_dlp,
            yt_dlp_enabled=True,
            playwright_enabled=False,
        )
        direct_url = "https://v26-dy.ixigua.com/video.mp4?watermark=0"

        with self.assertRaises(DownloadError) as caught:
            fetcher.fetch(
                source_video(source_url=direct_url),
                session_cookie="sessionid=abc",
                user_agent="ua",
            )

        self.assertEqual(caught.exception.code, DownloadErrorCode.VALIDATION_FAILED)
        self.assertEqual(http.urls, [direct_url])
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

    def test_generic_media_transfer_never_forwards_douyin_cookie(self):
        http = CapturingStreamDownloader()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=http,
            yt_dlp_enabled=False,
            playwright_enabled=False,
        )
        result = fetcher.fetch(
            source_video(
                source_platform="OTHER",
                source_url="https://media.example.test/video.mp4",
            ),
            session_cookie="sessionid=must-not-leak",
            user_agent="ua",
            proxy_url="http://127.0.0.1:8080",
        )

        self.assertTrue(result.downloaded.has_payload)
        self.assertEqual(http.calls[0]["proxy_url"], "http://127.0.0.1:8080")
        self.assertNotIn("Cookie", http.calls[0]["headers"])
        self.assertNotIn("Referer", http.calls[0]["headers"])

    def test_stream_downloader_internal_type_error_is_not_retried_without_proxy(self):
        class BrokenDownloader(CapturingStreamDownloader):
            def fetch_to_file(self, url, destination, *, resume, on_progress, headers, proxy_url):
                self.calls.append({"headers": headers, "proxy_url": proxy_url})
                raise TypeError("internal parser bug")

        http = BrokenDownloader()
        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=http,
            yt_dlp_enabled=False,
            playwright_enabled=False,
        )
        with self.assertRaisesRegex(TypeError, "internal parser bug"):
            fetcher.fetch(
                source_video(source_platform="OTHER", source_url="https://media.example.test/video.mp4"),
                session_cookie="sessionid=secret",
                user_agent="ua",
                proxy_url="http://127.0.0.1:8080",
            )
        self.assertEqual(len(http.calls), 1)


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
        self.assertIn("download_codec", metadata)


if __name__ == "__main__":
    unittest.main()
