from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from src.downloaders.api_bridged_playwright_douyin_resolver import ApiBridgedPlaywrightDouyinResolver
from src.downloaders.douyin_video_resolver import DouyinVideoResolveRequest
from src.downloaders.errors import DownloadError, DownloadErrorCode


class ApiBridgedPlaywrightTimeoutTests(unittest.TestCase):
    def test_socket_timeout_becomes_download_error(self) -> None:
        resolver = ApiBridgedPlaywrightDouyinResolver()
        request = DouyinVideoResolveRequest(
            aweme_id="7604842081471915210",
            page_url="https://www.douyin.com/video/7604842081471915210",
            session_cookie=None,
            user_agent="test-agent",
            workspace_id=uuid4(),
        )

        with patch(
            "src.downloaders.api_bridged_playwright_douyin_resolver.urlrequest.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            with self.assertRaises(DownloadError) as ctx:
                resolver.resolve(request)

        self.assertEqual(ctx.exception.code, DownloadErrorCode.DOWNLOAD_FAILED)
        self.assertIn("timed out", ctx.exception.message.lower())

    def test_bridge_http_timeout_exceeds_playwright_budget(self) -> None:
        settings = SimpleNamespace(
            douyin_playwright_download_enabled=True,
            douyin_download_api_base_url="http://127.0.0.1:8000",
            douyin_playwright_download_timeout_ms=90_000,
        )
        timeout = ApiBridgedPlaywrightDouyinResolver.bridge_http_timeout_seconds(settings)
        self.assertGreaterEqual(timeout, 180.0)


if __name__ == "__main__":
    unittest.main()
