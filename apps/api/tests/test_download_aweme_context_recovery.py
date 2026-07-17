from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.services.douyin_browser_context_registry import DouyinBrowserContextRegistry
from src.services.douyin_playwright_orphan_release import should_retry_playwright_open_after_orphan_release


def _alive_record(*, account_id, runtime_context_id: str = "live"):
    now = datetime.now(UTC)
    page = MagicMock()
    page.on = MagicMock()
    page.goto = MagicMock()
    page.wait_for_timeout = MagicMock()
    page.content = MagicMock(return_value="<html></html>")
    page.evaluate = MagicMock(return_value=None)
    page.remove_listener = MagicMock()
    context = MagicMock()
    return SimpleNamespace(
        runtime_context_id=runtime_context_id,
        browser_profile_id="main",
        browser_profile_path="C:/tmp/.douyin_profiles/main",
        persistent_profile=True,
        workspace_id=uuid4(),
        connect_session_id=uuid4(),
        account_connection_id=account_id,
        playwright=MagicMock(),
        browser=None,
        context=context,
        page=page,
        user_agent="ua",
        proxy_url=None,
        status="active",
        started_at=now,
        last_used_at=now,
        last_validated_at=None,
        reason=None,
    )


class PlaywrightDownloadRecoveryTests(unittest.TestCase):
    def test_should_retry_includes_browser_context_lost(self) -> None:
        self.assertTrue(should_retry_playwright_open_after_orphan_release("browser_context_lost:TargetClosedError"))

    def test_has_any_active_context_health_checks_dead_records(self) -> None:
        registry = DouyinBrowserContextRegistry()
        dead = _alive_record(account_id=uuid4(), runtime_context_id="dead")
        dead.context.cookies.side_effect = Exception("TargetClosedError")
        registry._records[dead.runtime_context_id] = dead

        with patch.object(registry, "_page_for_record", side_effect=Exception("TargetClosedError")):
            self.assertFalse(registry.has_any_active_context())

        self.assertNotIn(dead.runtime_context_id, registry._records)

    def test_download_aweme_video_reopens_once_on_context_loss(self) -> None:
        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        dead = _alive_record(account_id=account_id, runtime_context_id="dead")
        recovered = _alive_record(account_id=account_id, runtime_context_id="live")
        registry._records[dead.runtime_context_id] = dead

        ensure_calls = {"n": 0}

        def ensure_side_effect(record):
            ensure_calls["n"] += 1
            if ensure_calls["n"] == 1:
                return SimpleNamespace(status="invalid", reason="browser_context_lost:TargetClosedError")
            return SimpleNamespace(status="active", reason=None)

        with (
            patch.object(registry, "_record_for_account", side_effect=[dead, recovered, recovered]),
            patch.object(registry, "_ensure_usable", side_effect=ensure_side_effect),
            patch.object(registry, "_reopen_context_after_download_loss", return_value=recovered) as reopen,
            patch(
                "src.downloaders.playwright_douyin_video_resolver.parse_render_data_aweme",
                return_value=None,
            ),
            patch(
                "src.downloaders.playwright_douyin_video_resolver.extract_play_urls_from_aweme_payload",
                return_value=[],
            ),
            patch(
                "src.downloaders.playwright_douyin_video_resolver.select_preferred_play_candidate",
                return_value=None,
            ),
        ):
            with self.assertRaises(DownloadError) as ctx:
                registry.download_aweme_video(aweme_id="7480899554267696423", account_connection_id=account_id)

        reopen.assert_called_once()
        self.assertEqual(ctx.exception.code, DownloadErrorCode.RESOLVE_FAILED)
        self.assertNotIn("browser_context_lost", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
