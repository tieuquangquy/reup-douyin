from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.douyin_browser_download_cookies import (
    BrowserDownloadCookieExport,
    resolve_browser_download_cookies,
)
from src.downloaders.yt_dlp_douyin_resolver import (
    playwright_cookies_to_netscape_lines,
    write_netscape_cookie_file_from_playwright,
)
from pathlib import Path
from tempfile import TemporaryDirectory


class PlaywrightCookieNetscapeTests(unittest.TestCase):
    def test_playwright_cookies_to_netscape_lines(self) -> None:
        lines = playwright_cookies_to_netscape_lines(
            [
                {
                    "name": "sessionid",
                    "value": "abc",
                    "domain": ".douyin.com",
                    "path": "/",
                    "secure": True,
                    "expires": 1893456000,
                },
                {
                    "name": "ignored",
                    "value": "x",
                    "domain": "example.com",
                    "path": "/",
                },
            ]
        )
        joined = "\n".join(lines)
        self.assertIn("sessionid\tabc", joined)
        self.assertNotIn("example.com", joined)

    def test_write_netscape_cookie_file_from_playwright(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "cookies.txt"
            write_netscape_cookie_file_from_playwright(
                [
                    {
                        "name": "ttwid",
                        "value": "1",
                        "domain": "www.douyin.com",
                        "path": "/",
                        "secure": False,
                    }
                ],
                path,
            )
            self.assertIn("ttwid\t1", path.read_text(encoding="utf-8"))


class ResolveBrowserDownloadCookiesTests(unittest.TestCase):
    def test_resolve_browser_download_cookies_returns_export(self) -> None:
        workspace_id = uuid4()
        account_id = uuid4()
        account = MagicMock()
        account.id = account_id
        account.workspace_id = workspace_id
        account.user_agent = "Mozilla/5.0"
        account.proxy_url = None
        account.metadata_json = {
            "browser_profile_id": "main",
            "browser_profile_path": "C:/profiles/main",
        }

        db = MagicMock()
        service = MagicMock()
        service.default_account.return_value = account

        export = BrowserDownloadCookieExport(
            playwright_cookies=(
                {
                    "name": "sessionid",
                    "value": "live",
                    "domain": ".douyin.com",
                    "path": "/",
                    "secure": True,
                },
            ),
            user_agent="Mozilla/5.0 live",
            proxy_url=None,
            account_id=account_id,
        )

        with patch("src.downloaders.douyin_browser_download_cookies.DouyinAccountService", return_value=service), patch(
            "src.downloaders.douyin_browser_download_cookies.douyin_browser_context_registry.export_playwright_cookies_for_download",
            return_value=(list(export.playwright_cookies), export.user_agent),
        ):
            result = resolve_browser_download_cookies(db, workspace_id)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.user_agent, "Mozilla/5.0 live")
        self.assertEqual(result.playwright_cookies[0]["value"], "live")


if __name__ == "__main__":
    unittest.main()
