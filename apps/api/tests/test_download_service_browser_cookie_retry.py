from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.douyin_browser_download_cookies import BrowserDownloadCookieExport
from src.downloaders.douyin_download_session import DouyinDownloadSession
from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.source_video_primary_fetcher import PrimaryVideoFetchResult
from src.downloaders.base import DownloadedObject
from src.services.download_service import DownloadService


class DownloadServiceBrowserCookieRetryTests(unittest.TestCase):
    def test_run_download_retries_with_browser_cookies_after_download_failed(self) -> None:
        source_video_id = uuid4()
        workspace_id = uuid4()
        source_video = SimpleNamespace(
            id=source_video_id,
            workspace_id=workspace_id,
            source_platform="DOUYIN",
            source_url="https://www.douyin.com/video/1",
            source_video_external_id="1",
            caption=None,
            metadata_json={},
            raw_payload_json=None,
            status="QUEUED",
        )
        env_session = DouyinDownloadSession(
            session_cookie="sessionid=env",
            user_agent="ua-env",
            proxy_url=None,
            cookie_source="env",
        )
        browser_session = DouyinDownloadSession(
            session_cookie="sessionid=live",
            user_agent="ua-live",
            proxy_url=None,
            playwright_cookies=(
                {"name": "sessionid", "value": "live", "domain": ".douyin.com", "path": "/", "secure": True},
            ),
            cookie_source="browser_live",
        )
        fetcher = MagicMock()
        fetcher.fetch.side_effect = [
            DownloadError(DownloadErrorCode.DOWNLOAD_FAILED, "Fresh cookies are needed"),
            PrimaryVideoFetchResult(
                downloaded=DownloadedObject(content=b"video", mime_type="video/mp4", filename="a.mp4"),
                resolver_name="yt_dlp_browser",
                source_url="https://www.douyin.com/video/1",
                watermark_free=True,
            ),
        ]

        db = MagicMock()
        service = DownloadService(db, primary_fetcher=fetcher)
        service._get_source_video = MagicMock(return_value=source_video)
        service._storage_context = MagicMock(return_value=SimpleNamespace())
        service._persist_primary_video = MagicMock(return_value=SimpleNamespace())
        service._persist_json_asset = MagicMock(return_value=SimpleNamespace())
        service.get_manifest = MagicMock(return_value={"assets": []})

        with patch(
            "src.services.download_service.resolve_douyin_download_session",
            side_effect=[env_session, browser_session],
        ):
            manifest = service.run_download(source_video_id)

        self.assertEqual(fetcher.fetch.call_count, 2)
        self.assertEqual(fetcher.fetch.call_args_list[1].kwargs.get("playwright_cookies"), browser_session.playwright_cookies)
        self.assertEqual(manifest, {"assets": []})


if __name__ == "__main__":
    unittest.main()
