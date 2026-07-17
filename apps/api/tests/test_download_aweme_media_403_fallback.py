from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.playwright_douyin_video_resolver import RankedPlayUrl
from src.services.douyin_browser_context_registry import DouyinBrowserContextRegistry


class PlaywrightMedia403FallbackTests(unittest.TestCase):
    def test_download_retries_next_ranked_url_after_403(self) -> None:
        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        now = datetime.now(UTC)
        page = MagicMock()
        page.on = MagicMock()
        page.goto = MagicMock()
        page.wait_for_timeout = MagicMock()
        page.content = MagicMock(return_value="<html></html>")
        page.evaluate = MagicMock(return_value=None)
        page.remove_listener = MagicMock()

        forbidden = MagicMock()
        forbidden.status = 403
        forbidden.body.return_value = b""

        ok = MagicMock()
        ok.status = 200
        ok.body.return_value = b"mp4-bytes-ok"

        page.context.request.get.side_effect = [forbidden, ok]

        record = SimpleNamespace(
            runtime_context_id="live",
            browser_profile_id="main",
            browser_profile_path="C:/tmp/.douyin_profiles/main",
            persistent_profile=True,
            workspace_id=uuid4(),
            connect_session_id=uuid4(),
            account_connection_id=account_id,
            playwright=MagicMock(),
            browser=None,
            context=page.context,
            page=page,
            user_agent="ua-test",
            proxy_url=None,
            status="active",
            started_at=now,
            last_used_at=now,
            last_validated_at=None,
            reason=None,
        )
        registry._records[record.runtime_context_id] = record

        ranked = [
            RankedPlayUrl(
                url="https://cdn.example/download_addr.mp4",
                source="download_addr",
                height=1080,
                width=1920,
                bitrate=5000,
                watermark_free=True,
            ),
            RankedPlayUrl(
                url="https://cdn.example/bit_rate.mp4",
                source="bit_rate",
                height=720,
                width=1280,
                bitrate=2000,
                watermark_free=False,
            ),
        ]

        with (
            patch.object(registry, "_record_for_account", return_value=record),
            patch.object(registry, "_ensure_usable", return_value=SimpleNamespace(status="active", reason=None)),
            patch(
                "src.downloaders.playwright_douyin_video_resolver.parse_render_data_aweme",
                return_value={"ok": True},
            ),
            patch(
                "src.downloaders.playwright_douyin_video_resolver.collect_aweme_payloads_from_render_data",
                return_value=[{"aweme_detail": True}],
            ),
            patch(
                "src.downloaders.playwright_douyin_video_resolver.extract_play_urls_from_aweme_payload",
                return_value=ranked,
            ),
            patch(
                "src.core.settings.get_settings",
                return_value=MagicMock(douyin_download_allow_watermarked_fallback=True),
            ),
        ):
            downloaded = registry.download_aweme_video(
                aweme_id="7480899554267696423",
                account_connection_id=account_id,
            )

        self.assertEqual(downloaded.content, b"mp4-bytes-ok")
        self.assertEqual(downloaded.play_url, "https://cdn.example/bit_rate.mp4")
        self.assertEqual(downloaded.format_id, ranked[1].format_label)
        self.assertFalse(downloaded.watermark_free)
        self.assertEqual(page.context.request.get.call_count, 2)
        first_headers = page.context.request.get.call_args_list[0].kwargs["headers"]
        self.assertEqual(first_headers.get("Origin"), "https://www.douyin.com")
        self.assertEqual(first_headers.get("Referer"), "https://www.douyin.com/")

    def test_download_falls_back_to_in_page_fetch_when_all_context_gets_forbidden(self) -> None:
        registry = DouyinBrowserContextRegistry()
        page = MagicMock()
        forbidden = MagicMock()
        forbidden.status = 403
        forbidden.body.return_value = b""
        page.context.request.get.return_value = forbidden

        candidates = [
            RankedPlayUrl(
                url="https://cdn.example/a.mp4",
                source="download_addr",
                height=1080,
                width=1920,
                bitrate=1,
                watermark_free=True,
            )
        ]
        with patch.object(
            registry,
            "_fetch_cdn_bytes_in_page",
            return_value=b"from-page-fetch",
            create=True,
        ) as in_page:
            content, used_url, format_id, watermark_free = registry._download_ranked_media_bytes(
                page=page,
                candidates=candidates,
                user_agent="ua",
                timeout_ms=5_000,
            )

        self.assertEqual(content, b"from-page-fetch")
        self.assertEqual(used_url, "https://cdn.example/a.mp4")
        self.assertTrue(format_id.startswith("download_addr"))
        self.assertTrue(watermark_free)
        in_page.assert_called()

    def test_download_raises_when_all_candidates_fail(self) -> None:
        registry = DouyinBrowserContextRegistry()
        page = MagicMock()
        forbidden = MagicMock()
        forbidden.status = 403
        forbidden.body.return_value = b""
        page.context.request.get.return_value = forbidden

        with patch.object(registry, "_fetch_cdn_bytes_in_page", return_value=None, create=True):
            with self.assertRaises(DownloadError) as ctx:
                registry._download_ranked_media_bytes(
                    page=page,
                    candidates=[
                        RankedPlayUrl(
                            url="https://cdn.example/a.mp4",
                            source="download_addr",
                            height=1,
                            width=1,
                            bitrate=1,
                            watermark_free=True,
                        )
                    ],
                    user_agent="ua",
                    timeout_ms=1_000,
                )
        self.assertEqual(ctx.exception.code, DownloadErrorCode.DOWNLOAD_FAILED)
        self.assertIn("403", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
