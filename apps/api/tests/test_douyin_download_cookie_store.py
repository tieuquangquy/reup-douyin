from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.douyin_browser_download_cookies import (
    BrowserDownloadCookieExport,
    resolve_browser_download_cookies,
)
from src.downloaders.douyin_download_cookie_store import (
    DownloadCookieStorePayload,
    read_download_cookie_store,
    write_download_cookie_store,
)
from src.downloaders.douyin_download_session import resolve_douyin_download_session
from src.downloaders.yt_dlp_douyin_resolver import playwright_cookies_to_netscape_lines


class DownloadCookieStoreTests(unittest.TestCase):
    def test_write_and_read_roundtrip(self) -> None:
        account_id = uuid4()
        cookies = (
            {
                "name": "sessionid",
                "value": "live-abc",
                "domain": ".douyin.com",
                "path": "/",
                "secure": True,
            },
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            written = write_download_cookie_store(
                store_root=root,
                account_id=account_id,
                playwright_cookies=cookies,
                user_agent="Mozilla/5.0 store",
            )
            self.assertTrue(written.cookie_file.exists())
            payload = read_download_cookie_store(store_root=root, account_id=account_id)
            self.assertIsNotNone(payload)
            assert payload is not None
            self.assertEqual(payload.user_agent, "Mozilla/5.0 store")
            self.assertEqual(payload.playwright_cookies[0]["value"], "live-abc")
            self.assertIn("sessionid\tlive-abc", "\n".join(playwright_cookies_to_netscape_lines(list(payload.playwright_cookies))))


class ResolveSessionPrefersStoreOverEnvTests(unittest.TestCase):
    def test_prefer_browser_uses_store_when_live_export_unavailable(self) -> None:
        workspace_id = uuid4()
        account_id = uuid4()
        store_export = BrowserDownloadCookieExport(
            playwright_cookies=(
                {
                    "name": "sessionid",
                    "value": "from-store",
                    "domain": ".douyin.com",
                    "path": "/",
                    "secure": True,
                },
            ),
            user_agent="ua-store",
            proxy_url=None,
            account_id=account_id,
            cookie_source="browser_store",
        )
        db = MagicMock()
        settings = MagicMock()
        settings.douyin_yt_dlp_prefer_browser_cookies = True
        settings.douyin_session_cookie = "sessionid=stale-env"
        settings.douyin_user_agent = "ua-env"
        settings.douyin_proxy_url = None

        with patch("src.downloaders.douyin_download_session.get_settings", return_value=settings), patch(
            "src.downloaders.douyin_download_session.resolve_browser_download_cookies",
            return_value=store_export,
        ):
            session = resolve_douyin_download_session(db, workspace_id)

        self.assertEqual(session.cookie_source, "browser_store")
        self.assertEqual(session.playwright_cookies[0]["value"], "from-store")
        self.assertNotIn("stale-env", session.session_cookie or "")

    def test_live_unavailable_store_missing_skips_env_when_prefer_browser_strict(self) -> None:
        """When prefer_browser and account has profile but no live/store, do not poison with env."""
        workspace_id = uuid4()
        account_id = uuid4()
        account = MagicMock()
        account.id = account_id
        account.workspace_id = workspace_id
        account.user_agent = "ua-account"
        account.proxy_url = None
        account.metadata_json = {"browser_profile_id": "main", "browser_profile_path": "C:/profiles/main"}

        service = MagicMock()
        service.default_account.return_value = account
        runtime = MagicMock()
        runtime.session_cookie = "sessionid=from-account"
        runtime.user_agent = "ua-account"
        runtime.proxy_url = None
        service.resolve_runtime_config.return_value = runtime

        db = MagicMock()
        settings = MagicMock()
        settings.douyin_yt_dlp_prefer_browser_cookies = True
        settings.douyin_session_cookie = "sessionid=stale-env"
        settings.douyin_user_agent = "ua-env"
        settings.douyin_proxy_url = None
        settings.douyin_persistent_browser_profile_enabled = True

        with patch("src.downloaders.douyin_download_session.get_settings", return_value=settings), patch(
            "src.downloaders.douyin_download_session.resolve_browser_download_cookies",
            return_value=None,
        ), patch(
            "src.downloaders.douyin_download_session.DouyinAccountService",
            return_value=service,
        ):
            session = resolve_douyin_download_session(db, workspace_id)

        # Must not silently use stale env when browser profile is configured.
        self.assertNotEqual(session.cookie_source, "env")
        self.assertNotIn("stale-env", session.session_cookie or "")



class ResolveBrowserDownloadCookiesStoreFallbackTests(unittest.TestCase):
    def test_resolve_falls_back_to_store_when_live_export_none(self) -> None:
        workspace_id = uuid4()
        account_id = uuid4()
        account = MagicMock()
        account.id = account_id
        account.workspace_id = workspace_id
        account.user_agent = "ua"
        account.proxy_url = None
        account.metadata_json = {"browser_profile_id": "main", "browser_profile_path": "C:/p/main"}

        service = MagicMock()
        service.default_account.return_value = account
        db = MagicMock()

        store_payload = DownloadCookieStorePayload(
            playwright_cookies=(
                {"name": "sessionid", "value": "stored", "domain": ".douyin.com", "path": "/", "secure": True},
            ),
            user_agent="ua-stored",
            cookie_file=Path("dummy"),
        )

        with patch("src.downloaders.douyin_browser_download_cookies.DouyinAccountService", return_value=service), patch(
            "src.downloaders.douyin_browser_download_cookies.douyin_browser_context_registry.export_playwright_cookies_for_download",
            return_value=None,
        ), patch(
            "src.downloaders.douyin_browser_download_cookies.read_download_cookie_store_for_account",
            return_value=store_payload,
        ):
            result = resolve_browser_download_cookies(db, workspace_id)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.cookie_source, "browser_store")
        self.assertEqual(result.playwright_cookies[0]["value"], "stored")


if __name__ == "__main__":
    unittest.main()
