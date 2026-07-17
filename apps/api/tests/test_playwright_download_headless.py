from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException


class DownloadHeadlessAutoOpenTests(unittest.TestCase):
    def test_ensure_live_opens_profile_headless_by_default(self) -> None:
        from src.api.routes import internal_douyin_download as route

        workspace_id = uuid4()
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            metadata_json={"browser_profile_path": "C:/tmp/.douyin_profiles/main", "browser_profile_id": "main"},
            user_agent="ua",
            proxy_url=None,
        )
        settings = MagicMock()
        settings.douyin_playwright_download_auto_open = True
        settings.douyin_playwright_download_headless = True

        with (
            patch.object(route, "_account_for_workspace", return_value=account),
            patch.object(route.douyin_browser_context_registry, "has_any_active_context", return_value=False),
            patch.object(
                route.douyin_browser_context_registry,
                "open_profile_for_account",
                return_value=SimpleNamespace(status="active", reason=None),
            ) as open_profile,
            patch.object(route, "get_settings", return_value=settings, create=True),
        ):
            resolved = route._ensure_live_playwright_context(
                db=MagicMock(),
                workspace_id=workspace_id,
                account_id=account_id,
            )

        self.assertEqual(resolved, account_id)
        self.assertTrue(open_profile.call_args.kwargs.get("headless") is True)

    def test_ensure_live_skips_open_when_auto_open_disabled(self) -> None:
        from src.api.routes import internal_douyin_download as route

        workspace_id = uuid4()
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            metadata_json={"browser_profile_path": "C:/tmp/.douyin_profiles/main", "browser_profile_id": "main"},
            user_agent="ua",
            proxy_url=None,
        )
        settings = MagicMock()
        settings.douyin_playwright_download_auto_open = False
        settings.douyin_playwright_download_headless = True

        with (
            patch.object(route, "_account_for_workspace", return_value=account),
            patch.object(route.douyin_browser_context_registry, "has_any_active_context", return_value=False),
            patch.object(route.douyin_browser_context_registry, "open_profile_for_account") as open_profile,
            patch.object(route, "get_settings", return_value=settings, create=True),
        ):
            with self.assertRaises(HTTPException) as ctx:
                route._ensure_live_playwright_context(
                    db=MagicMock(),
                    workspace_id=workspace_id,
                    account_id=account_id,
                )

        open_profile.assert_not_called()
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("Refresh download session", str(ctx.exception.detail))

    def test_open_profile_for_account_respects_headless_flag(self) -> None:
        from src.services.douyin_browser_context_registry import DouyinBrowserContextRegistry

        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        workspace_id = uuid4()
        fake_playwright = MagicMock()
        fake_context = MagicMock()
        fake_page = MagicMock()
        fake_context.pages = [fake_page]
        fake_context.new_page.return_value = fake_page
        fake_context.cookies.return_value = [{"name": "sessionid", "value": "x", "domain": ".douyin.com"}]

        with (
            patch("src.services.douyin_browser_context_registry.get_settings") as settings_factory,
            patch("src.services.douyin_browser_context_registry.ensure_windows_playwright_event_loop_policy"),
            patch("playwright.sync_api.sync_playwright") as sync_pw,
            patch.object(registry, "_launch_persistent_context", return_value=fake_context) as launch,
            patch.object(registry, "get_or_create_live_page", return_value=(fake_page, "live_runtime_attached")),
            patch.object(registry, "profile_identity_for_account", return_value=("main", "C:/tmp/.douyin_profiles/main")),
            patch.object(registry, "_close_other_managed_records_for_profile"),
            patch.object(registry, "_record_for_account", return_value=None),
            patch.object(registry, "_close_handles"),
            patch("time.sleep", return_value=None),
        ):
            settings = MagicMock()
            settings.douyin_persistent_browser_profile_enabled = True
            settings.douyin_user_agent = "ua"
            settings_factory.return_value = settings
            sync_pw.return_value.start.return_value = fake_playwright

            registry.open_profile_for_account(
                workspace_id=workspace_id,
                account_connection_id=account_id,
                browser_profile_id="main",
                browser_profile_path="C:/tmp/.douyin_profiles/main",
                user_agent="ua",
                proxy_url=None,
                headless=True,
            )

        self.assertTrue(launch.called)
        self.assertTrue(launch.call_args.kwargs["launch_options"].get("headless") is True)


if __name__ == "__main__":
    unittest.main()
