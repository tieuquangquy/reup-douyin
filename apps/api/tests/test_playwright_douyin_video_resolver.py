from __future__ import annotations

import unittest

from src.downloaders.playwright_douyin_video_resolver import (
    extract_play_urls_from_aweme_payload,
    select_preferred_play_candidate,
    select_preferred_play_url,
)


class AwemePlayUrlExtractionTests(unittest.TestCase):
    def test_prefers_hq_bit_rate_over_logo_download_addr(self) -> None:
        payload = {
            "aweme_detail": {
                "video": {
                    "play_addr": {"url_list": ["https://cdn.example/play.mp4"], "height": 720, "width": 1280},
                    "download_addr": {
                        "url_list": ["https://cdn.example/mps/logo/download.mp4"],
                        "height": 720,
                        "width": 1280,
                        "data_size": 1,
                    },
                    "bit_rate": [
                        {
                            "gear_name": "1080p",
                            "bit_rate": 4_000_000,
                            "play_addr": {
                                "url_list": ["https://cdn.example/tos/cn/tos-cn-ve-15/br1080.mp4"],
                                "height": 1080,
                                "width": 1920,
                            },
                        }
                    ],
                }
            }
        }
        urls = extract_play_urls_from_aweme_payload(payload)
        preferred = select_preferred_play_candidate(urls)
        self.assertIsNotNone(preferred)
        assert preferred is not None
        self.assertEqual(preferred.url, "https://cdn.example/tos/cn/tos-cn-ve-15/br1080.mp4")
        self.assertTrue(preferred.watermark_free)
        download = next(item for item in urls if item.source == "download_addr")
        self.assertFalse(download.watermark_free)

    def test_selects_highest_height_then_bitrate_among_bit_rate(self) -> None:
        payload = {
            "aweme_detail": {
                "video": {
                    "play_addr": {"url_list": ["https://cdn.example/play720.mp4"], "height": 720},
                    "bit_rate": [
                        {
                            "gear_name": "720p",
                            "bit_rate": 2_000_000,
                            "play_addr": {"url_list": ["https://cdn.example/br720.mp4"], "height": 720, "width": 1280},
                        },
                        {
                            "gear_name": "1080p_low",
                            "bit_rate": 3_000_000,
                            "play_addr": {"url_list": ["https://cdn.example/br1080low.mp4"], "height": 1080, "width": 1920},
                        },
                        {
                            "gear_name": "1080p_high",
                            "bit_rate": 5_000_000,
                            "play_addr": {"url_list": ["https://cdn.example/br1080high.mp4"], "height": 1080, "width": 1920},
                        },
                    ],
                }
            }
        }
        candidate = select_preferred_play_candidate(extract_play_urls_from_aweme_payload(payload))
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.url, "https://cdn.example/br1080high.mp4")
        self.assertEqual(candidate.height, 1080)
        self.assertEqual(candidate.bitrate, 5_000_000)

    def test_among_no_logo_bit_rate_ignores_logo_download_addr(self) -> None:
        payload = {
            "aweme_detail": {
                "video": {
                    "download_addr": {"url_list": ["https://cdn.example/mps/logo/dl720.mp4"], "height": 720},
                    "bit_rate": [
                        {
                            "is_bytevc1": 0,
                            "bit_rate": 6_000_000,
                            "play_addr": {"url_list": ["https://cdn.example/dl1080.mp4"], "height": 1080},
                            "gear_name": "normal_1080",
                        }
                    ],
                }
            }
        }
        urls = extract_play_urls_from_aweme_payload(payload)
        self.assertEqual(select_preferred_play_url(urls), "https://cdn.example/dl1080.mp4")

    def test_falls_back_to_bit_rate_then_play_addr(self) -> None:
        payload = {
            "aweme_detail": {
                "video": {
                    "play_addr": {"url_list": ["https://cdn.example/play.mp4"], "height": 540},
                    "bit_rate": [
                        {"bit_rate": 1_500_000, "play_addr": {"url_list": ["https://cdn.example/hq.mp4"], "height": 720}},
                    ],
                }
            }
        }
        urls = extract_play_urls_from_aweme_payload(payload)
        preferred = select_preferred_play_url(urls)
        self.assertEqual(preferred, "https://cdn.example/hq.mp4")

    def test_url_markers_override_source_defaults(self) -> None:
        from src.downloaders.playwright_douyin_video_resolver import classify_douyin_cdn_watermark_free

        self.assertFalse(classify_douyin_cdn_watermark_free("https://x/mps/logo/a.mp4", source="bit_rate"))
        self.assertTrue(classify_douyin_cdn_watermark_free("https://x/play/?watermark=0", source="download_addr"))
        self.assertFalse(classify_douyin_cdn_watermark_free("https://x/playwm/a.mp4", source="play_addr"))

    def test_empty_payload_returns_none(self) -> None:
        self.assertEqual(extract_play_urls_from_aweme_payload({}), [])
        self.assertIsNone(select_preferred_play_url([]))
        self.assertIsNone(select_preferred_play_candidate([]))


class PrimaryFetcherCookieStoreFirstTests(unittest.TestCase):
    def test_douyin_page_uses_yt_dlp_before_playwright_when_fallback_allowed(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        from src.downloaders.base import DownloadedObject
        from src.downloaders.douyin_video_resolver import ResolvedDouyinVideo
        from src.downloaders.source_video_primary_fetcher import SourceVideoPrimaryFetcher
        from src.enums import SourcePlatformEnum

        class FakeHttp:
            def fetch(self, url: str) -> DownloadedObject:
                raise AssertionError("http should not run")

        class FakeYt:
            def is_available(self) -> bool:
                return True

            def resolve(self, request):
                return ResolvedDouyinVideo(
                    content=b"yt-bytes",
                    mime_type="video/mp4",
                    filename="yt.mp4",
                    resolver_name="yt_dlp_browser",
                    format_id="download",
                    watermark_free=True,
                )

        class FakePw:
            def is_available(self) -> bool:
                return True

            def resolve(self, request):
                raise AssertionError("playwright should not run when cookie-store yt-dlp succeeds")

        class DisabledBridge:
            def is_available(self) -> bool:
                return False

            def resolve(self, request):
                raise AssertionError("bridge should not run")

        fetcher = SourceVideoPrimaryFetcher(
            http_downloader=FakeHttp(),
            yt_dlp_resolver=FakeYt(),
            playwright_resolver=FakePw(),
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
                SimpleNamespace(
                    source_platform=SourcePlatformEnum.DOUYIN,
                    source_video_external_id="123",
                    source_url="https://www.douyin.com/video/123",
                ),
                session_cookie="sessionid=abc",
                user_agent="ua",
                playwright_cookies=(
                    {"name": "sessionid", "value": "abc", "domain": ".douyin.com", "path": "/"},
                ),
                cookie_source="browser_store",
            )
        self.assertEqual(result.downloaded.content, b"yt-bytes")
        self.assertEqual(result.resolver_name, "yt_dlp_browser")


if __name__ == "__main__":
    unittest.main()
