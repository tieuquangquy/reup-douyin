from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

from src.schemas.douyin_extension import DouyinExtensionHandshakeRequest
from src.services.douyin_extension_setup_service import (
    DouyinExtensionSetupError,
    DouyinExtensionSetupService,
    reset_douyin_extension_setup_state,
)


class DouyinExtensionSetupServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_douyin_extension_setup_state()

    def tearDown(self) -> None:
        reset_douyin_extension_setup_state()

    def test_status_reports_not_connected_before_handshake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = DouyinExtensionSetupService(
                now=datetime(2026, 4, 26, 16, 0, tzinfo=UTC),
                extension_dist_dir=Path(tmp) / "missing-dist",
            )

            status = service.status()

            self.assertEqual(status.status, "not_installed_or_not_connected")
            self.assertFalse(status.connected)
            self.assertEqual(status.version_status, "unknown")
            self.assertEqual(status.recommended_next_action, "build_extension")
            self.assertFalse(status.download_available)

    def test_handshake_reports_connected_for_supported_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "manifest.json").write_text('{"version":"0.1.0"}', encoding="utf-8")
            service = DouyinExtensionSetupService(
                now=datetime(2026, 4, 26, 16, 1, tzinfo=UTC),
                extension_dist_dir=dist,
            )

            status = service.record_handshake(
                DouyinExtensionHandshakeRequest(
                    install_id="install-fixture-1",
                    extension_id="extension-fixture",
                    extension_version="0.1.0",
                    browser_family="edge",
                    api_base_url="http://127.0.0.1:8000",
                    client_time=datetime(2026, 4, 26, 16, 1, tzinfo=UTC),
                )
            )

            self.assertEqual(status.status, "connected")
            self.assertTrue(status.connected)
            self.assertTrue(status.compatible)
            self.assertEqual(status.version_status, "compatible")
            self.assertEqual(status.browser_family, "edge")
            self.assertEqual(status.extension_version, "0.1.0")
            self.assertEqual(status.recommended_next_action, "open_douyin_and_capture")
            self.assertTrue(status.download_available)

    def test_handshake_reports_version_mismatch(self) -> None:
        now = datetime(2026, 4, 26, 16, 2, tzinfo=UTC)
        service = DouyinExtensionSetupService(now=now, extension_dist_dir=Path("missing"))

        status = service.record_handshake(
            DouyinExtensionHandshakeRequest(
                install_id="install-fixture-2",
                extension_version="9.9.9",
                browser_family="chrome",
            )
        )

        self.assertEqual(status.status, "version_mismatch")
        self.assertFalse(status.connected)
        self.assertFalse(status.compatible)
        self.assertEqual(status.version_status, "version_mismatch")
        self.assertEqual(status.recommended_next_action, "update_extension")

    def test_status_reports_stale_connection_after_threshold(self) -> None:
        first = datetime(2026, 4, 26, 16, 3, tzinfo=UTC)
        DouyinExtensionSetupService(now=first, extension_dist_dir=Path("missing")).record_handshake(
            DouyinExtensionHandshakeRequest(
                install_id="install-fixture-3",
                extension_version="0.1.0",
                browser_family="chromium",
            )
        )

        status = DouyinExtensionSetupService(
            now=first + timedelta(seconds=121),
            extension_dist_dir=Path("missing"),
        ).status()

        self.assertEqual(status.status, "stale_connection")
        self.assertFalse(status.connected)
        self.assertTrue(status.compatible)
        self.assertEqual(status.recommended_next_action, "open_extension_and_check_connection")

    def test_build_download_zip_requires_existing_dist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = DouyinExtensionSetupService(extension_dist_dir=Path(tmp) / "missing-dist")

            with self.assertRaises(DouyinExtensionSetupError) as ctx:
                service.build_download_zip()

            self.assertEqual(ctx.exception.code, "extension_build_missing")
            self.assertIn("npm run extension:build", ctx.exception.message)
            self.assertFalse(service.download_available())

    def test_status_reports_download_unavailable_for_empty_dist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            service = DouyinExtensionSetupService(extension_dist_dir=dist)

            status = service.status()

            self.assertFalse(status.download_available)
            self.assertFalse(service.download_available())
            with self.assertRaises(DouyinExtensionSetupError) as ctx:
                service.build_download_zip()
            self.assertEqual(ctx.exception.code, "extension_build_empty")

    def test_build_download_zip_packages_dist_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            nested = dist / "nested"
            nested.mkdir(parents=True)
            (dist / "manifest.json").write_text('{"version":"0.1.0"}', encoding="utf-8")
            (nested / "popup.js").write_text("console.log('ok');", encoding="utf-8")
            service = DouyinExtensionSetupService(extension_dist_dir=dist)

            content, filename = service.build_download_zip()

            self.assertTrue(service.download_available())
            self.assertEqual(filename, "reup-douyin-extension-0.1.0.zip")
            zip_path = Path(tmp) / filename
            zip_path.write_bytes(content)
            with ZipFile(zip_path) as archive:
                self.assertEqual(sorted(archive.namelist()), ["manifest.json", "nested/popup.js"])

    def test_handshake_records_manager_history(self) -> None:
        now = datetime(2026, 4, 26, 16, 4, tzinfo=UTC)
        service = DouyinExtensionSetupService(now=now, extension_dist_dir=Path("missing"))

        service.record_handshake(
            DouyinExtensionHandshakeRequest(
                install_id="install-fixture-4",
                extension_version="0.1.0",
                browser_family="chrome",
            )
        )

        history = service.history()
        self.assertEqual(history.total_count, 1)
        self.assertEqual(history.items[0].event_type, "handshake")
        self.assertEqual(history.items[0].status, "success")
        self.assertEqual(history.items[0].recommended_next_action, "open_douyin_and_capture")

    def test_detect_and_capture_results_are_recorded_in_history(self) -> None:
        now = datetime(2026, 4, 26, 16, 5, tzinfo=UTC)
        service = DouyinExtensionSetupService(now=now, extension_dist_dir=Path("missing"))

        service.record_detect_result(
            SimpleNamespace(
                detected_page_type="profile_feed_page",
                page_url="https://www.douyin.com/user/MS4fixture",
                title="Fixture profile",
                supported_capture=True,
                recommended_action="capture_current_page",
                recommended_action_label="Capture current page.",
                diagnostics_id="detect-diagnostics",
            )
        )
        source_profile_id = uuid4()
        service.record_capture_result(
            SimpleNamespace(
                detected_page_type="profile_feed_page",
                current_page_url="https://www.douyin.com/user/MS4fixture",
                current_page_title="Fixture profile",
                source_profile_id=source_profile_id,
                videos_discovered_count=2,
                videos_created_count=1,
                videos_updated_count=1,
                candidates_matched_count=1,
                warning=None,
                diagnostics_id="capture-diagnostics",
            )
        )

        history = service.history()
        self.assertEqual(history.total_count, 2)
        self.assertEqual(history.items[0].event_type, "capture")
        self.assertEqual(history.items[0].imported_profile_count, 1)
        self.assertEqual(history.items[0].videos_discovered_count, 2)
        self.assertEqual(history.items[0].candidates_matched_count, 1)
        self.assertEqual(history.items[1].event_type, "detect")
        self.assertTrue(history.items[1].supported_capture)

    def test_failure_history_is_short_and_actionable(self) -> None:
        service = DouyinExtensionSetupService(extension_dist_dir=Path("missing"))

        service.record_failure(
            event_type="capture",
            error_code="extension_challenge_page_not_capturable",
            error_message="Challenge page cannot be captured." * 50,
            page_type="challenge_page",
            diagnostics_id="failure-diagnostics",
        )

        item = service.history().items[0]
        self.assertEqual(item.event_type, "capture")
        self.assertEqual(item.status, "failed")
        self.assertEqual(item.page_type, "challenge_page")
        self.assertEqual(item.error_code, "extension_challenge_page_not_capturable")
        self.assertLessEqual(len(item.error_message or ""), 300)
        self.assertIn("Solve the Douyin challenge", item.recommended_next_action_label or "")

    def test_history_is_limited_and_ordered_newest_first(self) -> None:
        service = DouyinExtensionSetupService(extension_dist_dir=Path("missing"))

        for index in range(25):
            service.record_history_event(
                event_type="detect",
                status="success",
                diagnostics_id=f"diagnostics-{index}",
            )

        history = service.history(limit=50)
        self.assertEqual(history.total_count, 20)
        self.assertEqual(len(history.items), 20)
        self.assertEqual(history.items[0].diagnostics_id, "diagnostics-24")
        self.assertEqual(history.items[-1].diagnostics_id, "diagnostics-5")


if __name__ == "__main__":
    unittest.main()
