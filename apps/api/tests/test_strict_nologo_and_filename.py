from __future__ import annotations

import json
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.base import DownloadedObject
from src.downloaders.douyin_video_resolver import DouyinVideoResolveRequest, ResolvedDouyinVideo
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.playwright_douyin_video_resolver import RankedPlayUrl
from src.downloaders.source_video_filename import (
    build_source_video_raw_filename,
    caption_slug_for_filename,
    sanitize_filename_token,
)
from src.downloaders.source_video_primary_fetcher import SourceVideoPrimaryFetcher
from src.downloaders.yt_dlp_douyin_resolver import (
    YtDlpDouyinVideoResolver,
    is_yt_dlp_no_logo_format,
    yt_dlp_no_logo_format_selector,
)
from src.enums import MediaAssetType, SourcePlatformEnum
from src.services.douyin_browser_context_registry import DouyinBrowserContextRegistry
from src.storage.path_strategy import VideoStorageContext, asset_logical_key, slugify_filename


class SourceVideoFilenameTests(unittest.TestCase):
    def test_builds_date_aweme_caption_height_tag(self) -> None:
        from datetime import UTC, datetime

        name = build_source_video_raw_filename(
            aweme_id="7423381219443887414",
            caption="靠吃瘦了51.8斤 减肥食谱",
            watermark_free=True,
            posted_at=datetime(2026, 7, 14, tzinfo=UTC),
            height=1080,
        )
        self.assertTrue(name.endswith("__1080p__nl.mp4"))
        self.assertTrue(name.startswith("2026-07-14__7423381219443887414__"))
        self.assertIn("靠吃瘦了", name)
        self.assertNotIn(" ", name)
        self.assertLessEqual(len(name), 180)

    def test_watermarked_tag_and_missing_fields(self) -> None:
        from datetime import UTC, datetime

        name = build_source_video_raw_filename(
            aweme_id="123",
            caption=None,
            watermark_free=False,
            fallback_date=datetime(2026, 1, 2, tzinfo=UTC),
        )
        self.assertEqual(name, "2026-01-02__123__nocap__unkp__wm.mp4")

    def test_sanitize_strips_windows_unsafe(self) -> None:
        self.assertEqual(sanitize_filename_token('a<>:"/\\|?*b'), "ab")
        self.assertEqual(caption_slug_for_filename("Hello  World!!!"), "Hello-World")

    def test_asset_logical_key_preserves_cjk_readable_name(self) -> None:
        from datetime import UTC, datetime

        name = build_source_video_raw_filename(
            aweme_id="7423381219443887414",
            caption="靠吃瘦了51.8斤",
            watermark_free=True,
            posted_at=datetime(2026, 7, 14, tzinfo=UTC),
            height=1080,
        )
        self.assertIn("靠吃瘦了", name)
        key = asset_logical_key(
            VideoStorageContext(
                workspace_id="ws",
                source_platform=SourcePlatformEnum.DOUYIN,
                source_profile_external_id="MS4wLjABAAAAp1",
                source_video_external_id="7423381219443887414",
                profile_handle="Agu_z",
            ),
            MediaAssetType.SOURCE_VIDEO_RAW,
            filename=name,
        )
        self.assertIn("靠吃瘦了", key)
        self.assertIn("__1080p__nl.mp4", key)
        self.assertIn("/dy/@Agu_z__", key)
        self.assertEqual(slugify_filename(name), name)


class YtDlpNoLogoFormatTests(unittest.TestCase):
    def test_strict_selector_avoids_download_prefs_for_hq_nologo(self) -> None:
        self.assertEqual(
            yt_dlp_no_logo_format_selector("download/bestvideo*+bestaudio/best", strict=True),
            "bestvideo*+bestaudio/best",
        )
        self.assertEqual(
            yt_dlp_no_logo_format_selector("download/bestvideo*+bestaudio/best", strict=False),
            "download/bestvideo*+bestaudio/best",
        )

    def test_format_id_download_is_logo_best_is_no_logo(self) -> None:
        self.assertFalse(is_yt_dlp_no_logo_format("download", info=None))
        self.assertFalse(is_yt_dlp_no_logo_format("download+影音", info={"format_id": "download"}))
        self.assertTrue(is_yt_dlp_no_logo_format("best", info={"format_id": "best", "height": 1080}))
        self.assertFalse(
            is_yt_dlp_no_logo_format(
                "x+y",
                info={"requested_formats": [{"format_id": "download_1080"}, {"format_id": "audio"}]},
            )
        )


class StrictNoLogoDownloadTests(unittest.TestCase):
    def test_strict_mode_does_not_use_watermarked_fallback(self) -> None:
        registry = DouyinBrowserContextRegistry()
        page = MagicMock()
        forbidden = MagicMock()
        forbidden.status = 403
        forbidden.body.return_value = b""
        page.context.request.get.return_value = forbidden

        candidates = [
            RankedPlayUrl("https://cdn.example/nl-high.mp4", "download_addr", 1080, 1920, 5000, True),
            RankedPlayUrl("https://cdn.example/nl-low.mp4", "download_addr", 720, 1280, 2000, True),
            RankedPlayUrl("https://cdn.example/wm.mp4", "bit_rate", 1080, 1920, 8000, False),
        ]

        with (
            patch.object(registry, "_fetch_cdn_bytes_in_page", return_value=None),
            patch("src.core.settings.get_settings", return_value=MagicMock(douyin_download_allow_watermarked_fallback=False)),
        ):
            with self.assertRaises(DownloadError) as ctx:
                registry._download_ranked_media_bytes(
                    page=page,
                    candidates=candidates,
                    user_agent="ua",
                    timeout_ms=1000,
                    allow_watermarked_fallback=False,
                )

        self.assertEqual(ctx.exception.code, DownloadErrorCode.DOWNLOAD_FAILED)
        self.assertIn("no-logo", ctx.exception.message.lower())
        urls_tried = [call.args[0] for call in page.context.request.get.call_args_list]
        self.assertEqual(urls_tried, ["https://cdn.example/nl-high.mp4", "https://cdn.example/nl-low.mp4"])
        self.assertNotIn("https://cdn.example/wm.mp4", urls_tried)

    def test_allowed_fallback_returns_honest_watermark_flag(self) -> None:
        registry = DouyinBrowserContextRegistry()
        page = MagicMock()
        forbidden = MagicMock()
        forbidden.status = 403
        forbidden.body.return_value = b""
        ok = MagicMock()
        ok.status = 200
        ok.body.return_value = b"logo-bytes"
        page.context.request.get.side_effect = [forbidden, ok]

        candidates = [
            RankedPlayUrl("https://cdn.example/nl.mp4", "download_addr", 1080, 1920, 5000, True),
            RankedPlayUrl("https://cdn.example/wm.mp4", "bit_rate", 1080, 1920, 8000, False),
        ]

        with patch.object(registry, "_fetch_cdn_bytes_in_page", return_value=None):
            content, used_url, format_id, watermark_free = registry._download_ranked_media_bytes(
                page=page,
                candidates=candidates,
                user_agent="ua",
                timeout_ms=1000,
                allow_watermarked_fallback=True,
            )

        self.assertEqual(content, b"logo-bytes")
        self.assertEqual(used_url, "https://cdn.example/wm.mp4")
        self.assertTrue(format_id.startswith("bit_rate"))
        self.assertFalse(watermark_free)

    def test_no_logo_success_returns_watermark_free_true(self) -> None:
        registry = DouyinBrowserContextRegistry()
        page = MagicMock()
        ok = MagicMock()
        ok.status = 200
        ok.body.return_value = b"clean-bytes"
        page.context.request.get.return_value = ok

        candidates = [
            RankedPlayUrl("https://cdn.example/nl.mp4", "download_addr", 1080, 1920, 5000, True),
            RankedPlayUrl("https://cdn.example/wm.mp4", "bit_rate", 1080, 1920, 8000, False),
        ]

        with patch.object(registry, "_fetch_cdn_bytes_in_page", return_value=None):
            content, used_url, format_id, watermark_free = registry._download_ranked_media_bytes(
                page=page,
                candidates=candidates,
                user_agent="ua",
                timeout_ms=1000,
                allow_watermarked_fallback=False,
            )

        self.assertEqual(content, b"clean-bytes")
        self.assertEqual(used_url, "https://cdn.example/nl.mp4")
        self.assertTrue(watermark_free)
        self.assertEqual(page.context.request.get.call_count, 1)


class StrictFetcherOrderTests(unittest.TestCase):
    def test_strict_prefers_playwright_hq_nologo_before_yt_dlp(self) -> None:
        class FakeHttp:
            def fetch(self, url: str) -> DownloadedObject:
                raise AssertionError("http should not run")

        class FakeYt:
            def __init__(self) -> None:
                self.calls = 0

            def is_available(self) -> bool:
                return True

            def resolve(self, request):
                self.calls += 1
                raise AssertionError("yt-dlp must not run first in strict mode")

        class FakePw:
            def __init__(self) -> None:
                self.calls = 0

            def is_available(self) -> bool:
                return True

            def resolve(self, request):
                self.calls += 1
                return ResolvedDouyinVideo(
                    content=b"pw-hq",
                    mime_type="video/mp4",
                    filename="pw.mp4",
                    resolver_name="playwright_browser",
                    format_id="download_addr:1080",
                    watermark_free=True,
                    height=1080,
                    width=1920,
                )

        class DisabledBridge:
            def is_available(self) -> bool:
                return False

            def resolve(self, request):
                raise AssertionError("bridge should not run")

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
                SimpleNamespace(
                    source_platform=SourcePlatformEnum.DOUYIN,
                    source_video_external_id="123",
                    source_url="https://www.douyin.com/video/123",
                    workspace_id=uuid4(),
                ),
                session_cookie="sessionid=abc",
                user_agent="ua",
                playwright_cookies=({"name": "sessionid", "value": "abc", "domain": ".douyin.com", "path": "/"},),
                cookie_source="browser_store",
            )
        self.assertEqual(result.downloaded.content, b"pw-hq")
        self.assertEqual(result.resolver_name, "playwright_browser")
        self.assertTrue(result.watermark_free)
        self.assertEqual(result.height, 1080)
        self.assertEqual(pw.calls, 1)
        self.assertEqual(yt.calls, 0)


class YtDlpStrictResolveTests(unittest.TestCase):
    def test_strict_rejects_actual_download_format_as_watermarked(self) -> None:
        resolver = YtDlpDouyinVideoResolver(
            binary="yt-dlp",
            format_selector="download/bestvideo*+bestaudio/best",
            timeout_seconds=30,
        )
        request = DouyinVideoResolveRequest(
            aweme_id="1",
            page_url="https://www.douyin.com/video/1",
            session_cookie="sessionid=abc",
            user_agent="ua",
            proxy_url=None,
        )

        def fake_run(command, **kwargs):
            self.assertEqual(command[command.index("-f") + 1], "bestvideo*+bestaudio/best")
            output_template = command[command.index("-o") + 1]
            output_path = Path(output_template.replace("%(ext)s", "mp4"))
            output_path.write_bytes(b"wm-bytes")
            info_path = output_path.with_name(f"{output_path.stem}.info.json")
            info_path.write_text(json.dumps({"format_id": "download", "height": 1080}), encoding="utf-8")
            return CompletedProcess(command, 0, stdout="", stderr="")

        with (
            patch.object(resolver, "is_available", return_value=True),
            patch("src.downloaders.yt_dlp_douyin_resolver.subprocess.run", side_effect=fake_run),
            patch(
                "src.core.settings.get_settings",
                return_value=MagicMock(douyin_download_allow_watermarked_fallback=False),
            ),
        ):
            with self.assertRaises(DownloadError) as ctx:
                resolver.resolve(request)
        self.assertEqual(ctx.exception.code, DownloadErrorCode.DOWNLOAD_FAILED)
        self.assertIn("no-logo", ctx.exception.message.lower())

    def test_strict_accepts_verified_best_play_format(self) -> None:
        resolver = YtDlpDouyinVideoResolver(
            binary="yt-dlp",
            format_selector="bestvideo*+bestaudio/best",
            timeout_seconds=30,
        )
        request = DouyinVideoResolveRequest(
            aweme_id="1",
            page_url="https://www.douyin.com/video/1",
            session_cookie="sessionid=abc",
            user_agent="ua",
            proxy_url=None,
        )

        def fake_run(command, **kwargs):
            output_template = command[command.index("-o") + 1]
            output_path = Path(output_template.replace("%(ext)s", "mp4"))
            output_path.write_bytes(b"nl-hq")
            info_path = output_path.with_name(f"{output_path.stem}.info.json")
            info_path.write_text(
                json.dumps({"format_id": "best", "height": 1080, "width": 1920}),
                encoding="utf-8",
            )
            return CompletedProcess(command, 0, stdout="", stderr="")

        with (
            patch.object(resolver, "is_available", return_value=True),
            patch("src.downloaders.yt_dlp_douyin_resolver.subprocess.run", side_effect=fake_run),
            patch(
                "src.core.settings.get_settings",
                return_value=MagicMock(douyin_download_allow_watermarked_fallback=False),
            ),
        ):
            result = resolver.resolve(request)
        self.assertEqual(result.content, b"nl-hq")
        self.assertTrue(result.watermark_free)
        self.assertEqual(result.height, 1080)


if __name__ == "__main__":
    unittest.main()
