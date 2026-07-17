from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.downloaders.errors import DownloadError, DownloadErrorCode
from src.downloaders.playwright_douyin_video_resolver import RankedPlayUrl
from src.services.douyin_browser_context_registry import DouyinBrowserContextRegistry


class StickyWarmChromiumEnsureLiveTests(unittest.TestCase):
    def test_ensure_live_does_not_kill_orphan_before_first_open(self) -> None:
        from src.api.routes import internal_douyin_download as route

        workspace_id = uuid4()
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            metadata_json={"browser_profile_path": "C:/tmp/.douyin_profiles/main", "browser_profile_id": "main"},
            user_agent="ua",
            proxy_url=None,
        )
        db = MagicMock()

        with (
            patch.object(route, "_account_for_workspace", return_value=account),
            patch.object(route.douyin_browser_context_registry, "has_any_active_context", return_value=False),
            patch.object(
                route.douyin_browser_context_registry,
                "open_profile_for_account",
                return_value=SimpleNamespace(status="active", reason=None),
            ) as open_profile,
            patch.object(route, "terminate_orphaned_chromium_for_profile") as terminate,
        ):
            resolved = route._ensure_live_playwright_context(db=db, workspace_id=workspace_id, account_id=account_id)

        self.assertEqual(resolved, account_id)
        open_profile.assert_called_once()
        terminate.assert_not_called()

    def test_ensure_live_kills_orphan_only_after_lock_style_open_failure(self) -> None:
        from src.api.routes import internal_douyin_download as route

        workspace_id = uuid4()
        account_id = uuid4()
        account = SimpleNamespace(
            id=account_id,
            metadata_json={"browser_profile_path": "C:/tmp/.douyin_profiles/main", "browser_profile_id": "main"},
            user_agent="ua",
            proxy_url=None,
        )
        db = MagicMock()
        first = SimpleNamespace(status="invalid", reason="profile_locked_by_existing_process:Error")
        second = SimpleNamespace(status="active", reason=None)

        with (
            patch.object(route, "_account_for_workspace", return_value=account),
            patch.object(route.douyin_browser_context_registry, "has_any_active_context", return_value=False),
            patch.object(
                route.douyin_browser_context_registry,
                "open_profile_for_account",
                side_effect=[first, second],
            ),
            patch.object(route, "terminate_orphaned_chromium_for_profile", return_value=1) as terminate,
            patch("time.sleep", return_value=None),
        ):
            resolved = route._ensure_live_playwright_context(db=db, workspace_id=workspace_id, account_id=account_id)

        self.assertEqual(resolved, account_id)
        terminate.assert_called_once()


class NoLogoPhaseBeforeWatermarkTests(unittest.TestCase):
    def test_does_not_try_watermarked_until_all_no_logo_exhausted(self) -> None:
        registry = DouyinBrowserContextRegistry()
        page = MagicMock()
        forbidden = MagicMock()
        forbidden.status = 403
        forbidden.body.return_value = b""
        ok = MagicMock()
        ok.status = 200
        ok.body.return_value = b"logo-bytes"

        # First two calls: no-logo candidates → 403; third: watermarked → 200 (only when allowed)
        page.context.request.get.side_effect = [forbidden, forbidden, ok]

        candidates = [
            RankedPlayUrl("https://cdn.example/nl-high.mp4", "download_addr", 1080, 1920, 5000, True),
            RankedPlayUrl("https://cdn.example/nl-low.mp4", "download_addr", 720, 1280, 2000, True),
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
        self.assertFalse(watermark_free)
        self.assertFalse(format_id.startswith("download_addr") and "watermark" in format_id)
        urls_tried = [call.args[0] for call in page.context.request.get.call_args_list]
        self.assertEqual(
            urls_tried,
            [
                "https://cdn.example/nl-high.mp4",
                "https://cdn.example/nl-low.mp4",
                "https://cdn.example/wm.mp4",
            ],
        )


class DetailFirstSkipGotoTests(unittest.TestCase):
    def test_skips_goto_when_detail_api_returns_no_logo_candidates(self) -> None:
        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        now = datetime.now(UTC)
        page = MagicMock()
        page.url = "https://www.douyin.com/"
        page.on = MagicMock()
        page.goto = MagicMock()
        page.wait_for_timeout = MagicMock()
        page.content = MagicMock(return_value="<html></html>")
        page.remove_listener = MagicMock()
        page.evaluate = MagicMock(
            return_value={
                "aweme_detail": {
                    "video": {
                        "bit_rate": [
                            {
                                "bit_rate": 4000,
                                "play_addr": {
                                    "url_list": ["https://cdn.example/hq.mp4"],
                                    "height": 1080,
                                },
                            }
                        ],
                        "download_addr": {
                            "url_list": ["https://cdn.example/mps/logo/wm.mp4"],
                            "height": 720,
                        },
                    }
                }
            }
        )
        ok = MagicMock()
        ok.status = 200
        ok.body.return_value = b"hq-bytes"
        page.context.request.get.return_value = ok

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
            user_agent="ua",
            proxy_url=None,
            status="active",
            started_at=now,
            last_used_at=now,
            last_validated_at=None,
            reason=None,
        )
        registry._records[record.runtime_context_id] = record

        with (
            patch.object(registry, "_record_for_account", return_value=record),
            patch.object(registry, "_ensure_usable", return_value=SimpleNamespace(status="active", reason=None)),
            patch.object(registry, "_fetch_cdn_bytes_in_page", return_value=None),
        ):
            downloaded = registry.download_aweme_video(
                aweme_id="7480899554267696423",
                account_connection_id=account_id,
            )

        self.assertEqual(downloaded.content, b"hq-bytes")
        self.assertEqual(downloaded.play_url, "https://cdn.example/hq.mp4")
        self.assertTrue(downloaded.watermark_free)
        page.goto.assert_not_called()

    def test_reopen_after_loss_does_not_preemptively_kill_orphan(self) -> None:
        registry = DouyinBrowserContextRegistry()
        account_id = uuid4()
        workspace_id = uuid4()
        record = SimpleNamespace(
            runtime_context_id="dead",
            account_connection_id=account_id,
            workspace_id=workspace_id,
            browser_profile_id="main",
            browser_profile_path="C:/tmp/.douyin_profiles/main",
            user_agent="ua",
            proxy_url=None,
            reason="browser_context_lost:TargetClosedError",
        )
        recovered = SimpleNamespace(runtime_context_id="live")

        with (
            patch(
                "src.services.douyin_playwright_orphan_release.terminate_orphaned_chromium_for_profile"
            ) as terminate,
            patch.object(
                registry,
                "open_profile_for_account",
                return_value=SimpleNamespace(status="active", reason=None, managed_runtime_status="managed_runtime_active"),
            ) as open_profile,
            patch.object(registry, "_record_for_account", return_value=recovered),
        ):
            out = registry._reopen_context_after_download_loss(record)

        self.assertIs(out, recovered)
        terminate.assert_not_called()
        open_profile.assert_called_once()
        self.assertTrue(open_profile.call_args.kwargs.get("allow_orphan_release"))
        # Interactive connect paths stay headed; download recovery uses settings headless.


if __name__ == "__main__":
    unittest.main()
